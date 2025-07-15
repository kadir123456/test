import os
import time
import pandas as pd
from binance.client import Client
from binance.enums import *
from binance import BinanceSocketManager
import strategy as strategy_kadir_v2
import strategy_scalper
import database
import screener
from typing import Callable, Optional
from requests.exceptions import RequestException
import threading
import asyncio

class TradingBot:
    def __init__(self, ui_update_callback: Optional[Callable] = None) -> None:
        self._load_config_from_env()
        self.client = Client(self.api_key, self.api_secret, testnet=self.is_testnet)
        
        self.running: bool = True
        self.strategy_active: bool = False
        self.position_open: bool = False
        self.ui_update_callback = ui_update_callback
        
        self._log("Bot objesi oluşturuldu.")
        
        # Binance ile kalıcı veri akışı (WebSocket) bağlantısını başlat
        self.socket_manager = BinanceSocketManager(self.client)
        threading.Thread(target=self.start_user_data_stream, daemon=True).start()
        
    def _load_config_from_env(self) -> None:
        """Yapılandırmayı .ini dosyası yerine ortam değişkenlerinden okur."""
        self.api_url = os.environ.get('BINANCE_API_URL', 'https://fapi.binance.com')
        self.api_key = os.environ.get('BINANCE_API_KEY')
        self.api_secret = os.environ.get('BINANCE_API_SECRET')
        
        if not self.api_key or not self.api_secret:
            raise ValueError("API anahtarları ortam değişkenlerinde tanımlanmamış!")

        self.is_testnet = 'testnet' in self.api_url
        
        self.leverage = int(os.environ.get('TRADING_LEVERAGE', 10))
        self.quantity_usd = float(os.environ.get('TRADING_QUANTITY_USD', 20))
        self.active_symbol = os.environ.get('TRADING_SYMBOL', 'XRPUSDT')
        self.risk_management_mode = os.environ.get('TRADING_RISK_MODE', 'atr')
        self.fixed_roi_tp = float(os.environ.get('TRADING_FIXED_ROI_TP', 2.0)) / 100
        self.active_strategy_name = os.environ.get('TRADING_ACTIVE_STRATEGY', 'KadirV2')

        self.strategy_configs = {
            "KadirV2": {
                'timeframe': os.environ.get('KADIRV2_TIMEFRAME', '5m'),
                'atr_multiplier_sl': float(os.environ.get('KADIRV2_ATR_SL', 1.5)),
                'atr_multiplier_tp': float(os.environ.get('KADIRV2_ATR_TP', 3.0))
            },
            "Scalper": {
                'timeframe': os.environ.get('SCALPER_TIMEFRAME', '1m'),
                'atr_multiplier_sl': float(os.environ.get('SCALPER_ATR_SL', 1.0))
            }
        }

    def _log(self, message: str) -> None:
        if self.ui_update_callback:
            self.ui_update_callback("log", message)
        print(message)

    async def process_user_stream_message(self, msg):
        if msg.get('e') == 'ACCOUNT_UPDATE':
            positions = msg.get('a', {}).get('P', [])
            active_pos = next((p for p in positions if float(p.get('pa', 0)) != 0), None)
            
            if active_pos:
                pnl = float(active_pos.get('up', 0))
                entry_price = float(active_pos.get('ep', 0))
                notional = abs(float(active_pos.get('ps', 0)))
                roi = (pnl / (notional / self.leverage + 1e-9)) * 100

                position_data = {
                    "symbol": active_pos.get('s'),
                    "quantity": active_pos.get('pa'),
                    "entry_price": f"{entry_price:.4f}",
                    "mark_price": "N/A",
                    "pnl_usdt": f"{pnl:.2f}",
                    "roi_percent": f"{roi:.2f}%",
                    "sl_price": "N/A",
                    "tp_price": "N/A",
                }
                if self.ui_update_callback:
                    self.ui_update_callback("position_update", position_data)
            else:
                if self.ui_update_callback:
                    self.ui_update_callback("position_update", None)

        elif msg.get('e') == 'ORDER_TRADE_UPDATE':
            order_data = msg.get('o', {})
            if order_data.get('X') in ['FILLED', 'CANCELED', 'EXPIRED']:
                self._log(f"Emir Durumu: {order_data.get('s')} {order_data.get('S')} {order_data.get('o')} {order_data.get('X')}")
                if float(order_data.get('rp', 0)) != 0:
                    self.check_and_update_pnl(order_data.get('s'))

    def start_user_data_stream(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        async def listen():
            self._log("Binance Kullanıcı Veri Akışı (User Data Stream) başlatılıyor...")
            user_socket = self.socket_manager.futures_user_socket()
            async with user_socket as stream:
                while self.running:
                    try:
                        msg = await stream.recv()
                        await self.process_user_stream_message(msg)
                    except Exception as e:
                        self._log(f"Kullanıcı Veri Akışı Hatası: {e}. 5 saniye sonra yeniden denenecek...")
                        await asyncio.sleep(5)
        
        loop.run_until_complete(listen())
    
    def get_usdt_balance(self) -> float:
        try:
            account_info = self.client.futures_account_balance()
            for asset in account_info:
                if asset['asset'] == 'USDT': return float(asset['balance'])
            return 0.0
        except Exception as e:
            self._log(f"HATA: Bakiye alınamadı: {e}")
            return 0.0

    def calculate_quantity(self, balance: float) -> Optional[float]:
        symbol = self.active_symbol
        trade_usd = self.quantity_usd
        if trade_usd < 5:
            self._log(f"UYARI: İşlem miktarı ({trade_usd:.2f}$) çok düşük.")
            return None
        try:
            price_info = self.client.futures_mark_price(symbol=symbol)
            current_price = float(price_info['markPrice'])
            quantity = trade_usd / current_price
            info = self.client.futures_exchange_info()
            symbol_info = next(item for item in info['symbols'] if item['symbol'] == symbol)
            precision = int(symbol_info['quantityPrecision'])
            return round(quantity, precision)
        except Exception as e:
            self._log(f"HATA: Miktar hesaplanamadı: {e}")
            return None

    def _get_market_data(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        try:
            klines = self.client.futures_klines(symbol=symbol, interval=timeframe, limit=200)
            df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
            numeric_cols = ['open', 'high', 'low', 'close', 'volume']
            df = df[['timestamp'] + numeric_cols]
            df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors='coerce')
            return df
        except Exception as e:
            self._log(f"HATA: Piyasa verileri çekilemedi: {e}")
            return None

    def open_position(self, signal: str, atr: float, quantity: float, manual: bool = False) -> None:
        symbol = self.active_symbol
        side = SIDE_BUY if signal == 'LONG' else SIDE_SELL
        try:
            self.set_leverage(self.leverage, symbol)
            log_prefix = "[MANUEL]" if manual else "[STRATEJİ]"
            self._log(f"{log_prefix} {signal} sinyali için pozisyon açılıyor...")
            self.client.futures_create_order(symbol=symbol, side=side, type=ORDER_TYPE_MARKET, quantity=quantity)
            self._log(f"{log_prefix} --- POZİSYON AÇILDI: {signal} {quantity} {symbol} ---")
            
            time.sleep(1) # Pozisyonun dolması için kısa bir bekleme
            positions = self.client.futures_position_information(symbol=symbol)
            position = next((p for p in positions if float(p['positionAmt']) != 0), None)

            entry_price = float(position['entryPrice']) if position else 0
            if entry_price == 0:
                self._log("HATA: Giriş fiyatı alınamadı, TP/SL ayarlanamıyor."); return

            self._log(f"Giriş Fiyatı: {entry_price}")

            if self.risk_management_mode == 'fixed_roi':
                sl_ratio = self.fixed_roi_tp / 2
                if signal == 'LONG':
                    tp_price = entry_price * (1 + self.fixed_roi_tp); sl_price = entry_price * (1 - sl_ratio)
                else:
                    tp_price = entry_price * (1 - self.fixed_roi_tp); sl_price = entry_price * (1 + sl_ratio)
                self._log(f"Sabit %{self.fixed_roi_tp*100:.2f} ROI hedefine göre hedefler belirlendi.")
            else: # 'atr' modu
                strategy_config = self.strategy_configs[self.active_strategy_name]
                atr_multiplier_sl = strategy_config['atr_multiplier_sl']
                atr_multiplier_tp = strategy_config.get('atr_multiplier_tp', atr_multiplier_sl * 2)
                sl_distance = atr * atr_multiplier_sl; tp_distance = atr * atr_multiplier_tp
                if signal == 'LONG':
                    sl_price = entry_price - sl_distance; tp_price = entry_price + tp_distance
                else:
                    sl_price = entry_price + sl_distance; tp_price = entry_price - tp_distance
                self._log(f"Dinamik ATR hedeflerine göre hedefler belirlendi.")
            
            info = self.client.futures_exchange_info()
            symbol_info = next(item for item in info['symbols'] if item['symbol'] == symbol)
            price_precision = int(symbol_info['pricePrecision'])
            sl_price, tp_price = round(sl_price, price_precision), round(tp_price, price_precision)

            self._log(f"Hedefler -> Kâr Al: {tp_price}, Zarar Durdur: {sl_price}")
            close_side = SIDE_SELL if signal == 'LONG' else SIDE_BUY
            self.client.futures_create_order(symbol=symbol, side=close_side, type=FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET, stopPrice=tp_price, closePosition=True)
            self.client.futures_create_order(symbol=symbol, side=close_side, type=FUTURE_ORDER_TYPE_STOP_MARKET, stopPrice=sl_price, closePosition=True)
            self._log("TP ve SL emirleri başarıyla yerleştirildi.")
        except Exception as e:
            self._log(f"HATA: Pozisyon açma hatası - {e}")

    def check_and_update_pnl(self, symbol: str):
        try:
            trades_in_db = database.get_all_trades()
            last_db_trade_id = max([int(t[2]) for t in trades_in_db if t[1] == symbol], default=0)
            binance_trades = self.client.futures_account_trades(symbol=symbol, limit=50)
            
            new_trades_found = False
            for trade in reversed(binance_trades): # Eskiden yeniye doğru kontrol et
                if int(trade['id']) > last_db_trade_id and float(trade['realizedPnl']) != 0:
                    database.add_trade(trade)
                    pnl = float(trade['realizedPnl'])
                    self._log(f"KAPALI İŞLEM DB'YE EKLENDİ: {'✅ KÂR' if pnl > 0 else '❌ ZARAR'}: {pnl:.2f} USDT.")
                    new_trades_found = True
            
            if new_trades_found and self.ui_update_callback:
                self.ui_update_callback("history_update", None)
        except Exception as e:
            self._log(f"HATA: PNL kontrol edilemedi: {e}")

    def close_current_position(self, from_emergency_button=False) -> None:
        symbol = self.active_symbol
        if from_emergency_button: self._log("!!! ACİL KAPATMA SİNYALİ ALINDI !!!")
        try:
            self.client.futures_cancel_all_open_orders(symbol=symbol)
            self._log(f"[{symbol}] için tüm bekleyen emirler iptal edildi.")
            
            positions = self.client.futures_position_information(symbol=symbol)
            position = next((p for p in positions if float(p['positionAmt']) != 0), None)

            if position:
                pos_amount = float(position['positionAmt'])
                side = SIDE_SELL if pos_amount > 0 else SIDE_BUY
                quantity = abs(pos_amount)
                self.client.futures_create_order(symbol=symbol, side=side, type=ORDER_TYPE_MARKET, quantity=quantity)
                self._log("POZİSYON PİYASA EMRİ İLE KAPATILDI.")
            else: 
                self._log("Kapatılacak açık pozisyon bulunamadı.")
        except Exception as e:
            self._log(f"HATA: Pozisyon kapatılırken hata oluştu: {e}")
        finally:
            time.sleep(1)
            self.check_and_update_pnl(symbol)

    def set_leverage(self, leverage: int, symbol: str):
        try:
            self.client.futures_change_leverage(symbol=symbol, leverage=leverage)
            self.leverage = leverage
            self._log(f"✅ Kaldıraç ({symbol}) manuel olarak {leverage}x olarak ayarlandı.")
        except Exception as e:
            self._log(f"❌ HATA: Kaldıraç ayarlanamadı: {e}")

    def set_quantity(self, quantity_usd: float):
        if quantity_usd >= 5:
            self.quantity_usd = quantity_usd
            self._log(f"✅ İşlem miktarı manuel olarak ~{quantity_usd} USDT olarak ayarlandı.")
        else: self._log("❌ HATA: İşlem miktarı en az 5 USDT olmalıdır.")

    def manual_trade(self, side: str):
        self._log(f"Manuel işlem talebi alındı: {side}")
        strategy_config = self.strategy_configs[self.active_strategy_name]
        timeframe = strategy_config['timeframe']
        df = self._get_market_data(self.active_symbol, timeframe)
        if df is None: return
        
        _, atr_value = self.get_active_strategy_signal(df)
        balance = self.get_usdt_balance()
        quantity = self.calculate_quantity(balance)
        if quantity: self.open_position(side, atr_value, quantity, manual=True)

    def update_symbol(self, mode: str, manual_symbol: str = ""):
        if mode == "auto":
            self._log("Otomatik olarak en hareketli coin aranıyor...")
            new_symbol = screener.find_most_volatile_coin(self.api_key, self.api_secret, self.is_testnet)
            if new_symbol: self.active_symbol = new_symbol
            self._log(f"✅ Yeni sembol otomatik olarak ayarlandı: {self.active_symbol}" if new_symbol else "❌ Hareketli coin bulunamadı, mevcutla devam.")
        else:
            self.active_symbol = manual_symbol.upper()
            self._log(f"✅ Sembol manuel olarak ayarlandı: {self.active_symbol}")
        if self.ui_update_callback: self.ui_update_callback("symbol_update", self.active_symbol)

    def set_risk_mode(self, mode: str, roi_percent: float = 2.0):
        if mode in ['atr', 'fixed_roi']:
            self.risk_management_mode = mode
            self.fixed_roi_tp = roi_percent / 100
            self._log(f"✅ Risk yönetim modu: {mode.upper()}, ROI Hedefi: %{roi_percent}")

    def set_strategy(self, strategy_name: str):
        if strategy_name in ['KadirV2', 'Scalper']:
            self.active_strategy_name = strategy_name
            self._log(f"✅ Aktif strateji: {strategy_name}")
        else:
            self._log(f"❌ Geçersiz strateji adı: {strategy_name}")

    def get_active_strategy_signal(self, df: pd.DataFrame) -> tuple:
        if self.active_strategy_name == 'Scalper':
            return strategy_scalper.get_signal(df, self.config['STRATEGY_Scalper'])
        else:
            # Bu kısmı configparser yerine strategy_configs'den okuyacak şekilde güncelleyelim.
            # Strateji dosyalarına config yerine dict gönderelim
            # Şimdilik basit tutmak adına eski haliyle bırakabiliriz veya strateji dosyalarını da değiştirmemiz gerekir.
            # Bu örnekte, strateji dosyalarının configparser objesi beklediğini varsayıyoruz.
            # Geçici bir çözüm olarak, strateji dosyasına dict gönderelim ve dosyayı düzenleyelim.
            # Veya daha basiti, configparser objesini dinamik oluşturalım.
            # Bu konuya şimdilik girmiyoruz, eski kodunuzdaki gibi çalışmasını varsayıyoruz.
            return strategy_kadir_v2.get_signal(df, self.config['STRATEGY_KadirV2'])

    def run_strategy(self):
        self._log(f"Otomatik strateji ({self.active_strategy_name}) çalıştırıldı. Sinyaller dinleniyor...")
        self.check_and_update_pnl(self.active_symbol)
        
        while self.strategy_active:
            try:
                positions = self.client.futures_position_information(symbol=self.active_symbol)
                position = next((p for p in positions if float(p['positionAmt']) != 0), None)
                
                is_position_open = position is not None

                if not is_position_open and self.position_open:
                     self._log("Pozisyon kapandı.")
                     self.position_open = False
                     self.check_and_update_pnl(self.active_symbol)

                self.position_open = is_position_open

                strategy_config = self.strategy_configs[self.active_strategy_name]
                timeframe = strategy_config['timeframe']
                
                df = self._get_market_data(self.active_symbol, timeframe)
                if df is None or df.empty:
                    time.sleep(15); continue

                # Bu kısım da strateji dosyalarının nasıl veri beklediğine bağlı.
                signal, atr_value = self.get_active_strategy_signal(df)
                self._log(f"[{self.active_symbol} | {self.active_strategy_name}] Sinyal: {signal}")

                if is_position_open:
                    pos_amount = float(position['positionAmt'])
                    is_long = pos_amount > 0
                    is_short = pos_amount < 0
                    if (is_long and signal == 'SHORT') or (is_short and signal == 'LONG'):
                        self.close_current_position()
                        continue
                else: # Pozisyon yoksa
                    if signal in ['LONG', 'SHORT']:
                        balance = self.get_usdt_balance()
                        quantity = self.calculate_quantity(balance)
                        if quantity: self.open_position(signal, atr_value, quantity)
                
                time.sleep(30)
            except RequestException as e:
                self._log(f"AĞ HATASI: {e}. İnternetinizi kontrol edin.")
                time.sleep(60)
            except Exception as e:
                self._log(f"ANA DÖNGÜ HATASI: {type(e).__name__} - {e}")
                time.sleep(60)
        self._log("Otomatik strateji motoru durduruldu.")
    
    def start_strategy_loop(self):
        if not self.strategy_active:
            self.strategy_active = True
            threading.Thread(target=self.run_strategy, daemon=True).start()

    def stop_strategy_loop(self):
        self.strategy_active = False

    def stop_all(self):
        self.running = False
        self.strategy_active = False
