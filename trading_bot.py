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

class TradingBot:
    def __init__(self, ui_update_callback: Optional[Callable] = None) -> None:
        self._load_config_from_env()
        self.client = Client(self.api_key, self.api_secret, testnet=self.is_testnet)

        self.running: bool = True
        self.strategy_active: bool = False
        self.position_open: bool = False
        self.ui_update_callback = ui_update_callback

        self.current_position = None  # Pozisyon bilgisi
        self.socket_manager = BinanceSocketManager(self.client)
        threading.Thread(target=self.start_user_data_stream, daemon=True).start()

        self._log("Bot objesi oluşturuldu.")

    def _load_config_from_env(self) -> None:
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
                'atr_multiplier_tp': float(os.environ.get('KADIRV2_ATR_TP', 3.0)),
                'ema_length_fast': int(os.environ.get('KADIRV2_EMA_FAST', 9)),
                'ema_length_slow': int(os.environ.get('KADIRV2_EMA_SLOW', 21)),
                'rsi_length': int(os.environ.get('KADIRV2_RSI_LENGTH', 14)),
                'rsi_overbought': int(os.environ.get('KADIRV2_RSI_OB', 70)),
                'rsi_oversold': int(os.environ.get('KADIRV2_RSI_OS', 30)),
                'atr_length': int(os.environ.get('KADIRV2_ATR_LEN', 14))
            },
            "Scalper": {
                'timeframe': os.environ.get('SCALPER_TIMEFRAME', '1m'),
                'atr_multiplier_sl': float(os.environ.get('SCALPER_ATR_SL', 1.0)),
                'volume_ma_length': int(os.environ.get('SCALPER_VOL_MA_LEN', 20)),
                'volume_threshold': float(os.environ.get('SCALPER_VOL_THRESHOLD', 2.0)),
                'candle_body_ratio': float(os.environ.get('SCALPER_BODY_RATIO', 0.6)),
                'atr_length': int(os.environ.get('SCALPER_ATR_LEN', 14))
            }
        }

    def _log(self, message: str) -> None:
        if self.ui_update_callback:
            self.ui_update_callback("log", message)
        print(message)

    def start_user_data_stream(self):
        # Kullanıcı dataları (pozisyon, bakiye vs) için websocket başlatılabilir.
        # Şu an boş bırakıldı. İstersen websocket ile gerçek zamanlı veri alınabilir.
        pass

    def get_usdt_balance(self) -> float:
        try:
            account_info = self.client.futures_account()
            for asset in account_info['assets']:
                if asset['asset'] == 'USDT':
                    balance = float(asset['walletBalance'])
                    return balance
        except Exception as e:
            self._log(f"Bakiye alınırken hata: {e}")
        return 0.0

    def calculate_quantity(self, balance: float) -> Optional[float]:
        if balance <= 0:
            return None
        quantity = self.quantity_usd / balance * balance  # Basitçe işlem miktarı = quantity_usd olarak ayarlandı
        return quantity

    def _get_market_data(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        try:
            klines = self.client.futures_klines(symbol=symbol, interval=timeframe, limit=100)
            df = pd.DataFrame(klines, columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_asset_volume", "number_of_trades",
                "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"
            ])
            df['open'] = df['open'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            df['close'] = df['close'].astype(float)
            df['volume'] = df['volume'].astype(float)
            return df
        except Exception as e:
            self._log(f"Piyasa verisi alınamadı: {e}")
            return None

    def open_position(self, signal: str, atr: float, quantity: float, manual: bool = False) -> None:
        try:
            side = SIDE_BUY if signal == "LONG" else SIDE_SELL
            order = self.client.futures_create_order(
                symbol=self.active_symbol,
                side=side,
                type=ORDER_TYPE_MARKET,
                quantity=quantity
            )
            self.position_open = True
            self.current_position = order
            self._log(f"{signal} pozisyonu açıldı. Miktar: {quantity}")
            database.add_trade({
                'symbol': self.active_symbol,
                'id': order['orderId'],
                'side': signal,
                'realizedPnl': 0,
                'time': int(time.time() * 1000)
            })
        except Exception as e:
            self._log(f"Pozisyon açılırken hata: {e}")

    def check_and_update_pnl(self, symbol: str):
        try:
            positions = self.client.futures_position_information(symbol=symbol)
            for pos in positions:
                if float(pos['positionAmt']) != 0:
                    pnl = float(pos['unrealizedProfit'])
                    self._log(f"Açık pozisyon PNL: {pnl}")
                    # UI'yi veya başka yapıyı güncellemek için callback tetiklenebilir
                    return
            self.position_open = False
            self.current_position = None
        except Exception as e:
            self._log(f"PNL kontrolünde hata: {e}")

    def close_current_position(self, from_emergency_button=False) -> None:
        if not self.position_open:
            self._log("Kapatılacak açık pozisyon yok.")
            return
        try:
            side = SIDE_SELL if self.current_position['side'] == SIDE_BUY else SIDE_BUY
            quantity = float(self.current_position['origQty'])
            self.client.futures_create_order(
                symbol=self.active_symbol,
                side=side,
                type=ORDER_TYPE_MARKET,
                quantity=quantity
            )
            self.position_open = False
            self.current_position = None
            self._log("Pozisyon piyasa emriyle kapatıldı.")
        except Exception as e:
            self._log(f"Pozisyon kapatılırken hata: {e}")

    def set_leverage(self, leverage: int, symbol: str):
        try:
            self.client.futures_change_leverage(symbol=symbol, leverage=leverage)
            self.leverage = leverage
            self._log(f"Kaldıraç {leverage}x olarak ayarlandı.")
        except Exception as e:
            self._log(f"Kaldıraç ayarlanırken hata: {e}")

    def set_quantity(self, quantity_usd: float):
        self.quantity_usd = quantity_usd
        self._log(f"İşlem miktarı {quantity_usd} USDT olarak ayarlandı.")

    def manual_trade(self, side: str):
        strategy_config = self.strategy_configs[self.active_strategy_name]
        timeframe = strategy_config['timeframe']
        df = self._get_market_data(self.active_symbol, timeframe)
        if df is None:
            self._log("Manuel işlem için piyasa verisi alınamadı.")
            return

        _, atr_value = self.get_active_strategy_signal(df)
        balance = self.get_usdt_balance()
        quantity = self.calculate_quantity(balance)
        if quantity:
            self.open_position(side, atr_value, quantity, manual=True)

    def update_symbol(self, mode: str, manual_symbol: str = ""):
        if mode == "manual" and manual_symbol:
            self.active_symbol = manual_symbol.upper()
            self._log(f"Manuel sembol olarak {self.active_symbol} ayarlandı.")
        elif mode == "screener":
            screened_symbol = screener.get_best_symbol()
            if screened_symbol:
                self.active_symbol = screened_symbol
                self._log(f"Screener tarafından {self.active_symbol} seçildi.")
            else:
                self._log("Screener sembol seçemedi.")
        else:
            self._log("Sembol güncelleme modu bilinmiyor.")

    def set_risk_mode(self, mode: str, roi_percent: float = 2.0):
        self.risk_management_mode = mode
        self.fixed_roi_tp = roi_percent / 100
        self._log(f"Risk yönetim modu {mode} olarak ayarlandı, ROI: {roi_percent}%")

    def set_strategy(self, strategy_name: str):
        if strategy_name in ['KadirV2', 'Scalper']:
            self.active_strategy_name = strategy_name
            self._log(f"✅ Aktif strateji: {strategy_name}")
        else:
            self._log(f"❌ Geçersiz strateji adı: {strategy_name}")

    def get_active_strategy_signal(self, df: pd.DataFrame) -> tuple:
        config = self.strategy_configs[self.active_strategy_name]
        if self.active_strategy_name == 'Scalper':
            return strategy_scalper.get_signal(df, config)
        else:
            return strategy_kadir_v2.get_signal(df, config)

    def run_strategy(self):
        self._log("Strateji döngüsü başladı.")
        while self.strategy_active and self.running:
            try:
                config = self.strategy_configs[self.active_strategy_name]
                timeframe = config['timeframe']

                df = self._get_market_data(self.active_symbol, timeframe)
                if df is None:
                    self._log("Piyasa verisi alınamadı, bekleniyor...")
                    time.sleep(12)
                    continue

                signal, atr = self.get_active_strategy_signal(df)

                if signal:
                    balance = self.get_usdt_balance()
                    quantity = self.calculate_quantity(balance)
                    if quantity and not self.position_open:
                        self.open_position(signal, atr, quantity)

                if self.position_open:
                    self.check_and_update_pnl(self.active_symbol)

                time.sleep(12)  # API limitine uyacak şekilde bekle

            except Exception as e:
                self._log(f"Hata oluştu: {e}")
                time.sleep(12)

        self._log("Strateji döngüsü durduruldu.")

    def start_strategy_loop(self):
        if not self.strategy_active:
            self.strategy_active = True
            threading.Thread(target=self.run_strategy, daemon=True).start()

    def stop_strategy_loop(self):
        self.strategy_active = False

    def stop_all(self):
        self.running = False
        self.strategy_active = False
