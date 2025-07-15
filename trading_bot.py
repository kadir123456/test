import os
import time
import pandas as pd
from binance.client import Client
from binance.enums import *
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
        # Pozisyon akışı artık web soketi üzerinden yönetilecek.
        
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

        # Strateji ayarları da ortam değişkenlerinden okunabilir
        self.strategy_configs = {
            "KadirV2": {
                'timeframe': os.environ.get('KADIRV2_TIMEFRAME', '5m'),
                'atr_multiplier_sl': float(os.environ.get('KADIRV2_ATR_SL', 1.5)),
                'atr_multiplier_tp': float(os.environ.get('KADIRV2_ATR_TP', 3.0))
                # Diğer KadirV2 ayarlarını da buraya ekleyebilirsiniz...
            },
            "Scalper": {
                'timeframe': os.environ.get('SCALPER_TIMEFRAME', '1m'),
                'atr_multiplier_sl': float(os.environ.get('SCALPER_ATR_SL', 1.0))
                 # Diğer Scalper ayarlarını da buraya ekleyebilirsiniz...
            }
        }


    def _log(self, message: str) -> None:
        # Callback fonksiyonu ile logları ana uygulamaya (FastAPI) gönderir
        if self.ui_update_callback:
            self.ui_update_callback("log", message)
        print(message) # Sunucu logları için konsola da yazdır

    # ... (get_usdt_balance, calculate_quantity, _get_market_data fonksiyonları aynı kalabilir) ...
    # Bu fonksiyonları aynen eski trading_bot.py dosyanızdan kopyalayın

    def open_position(self, signal: str, atr: float, quantity: float, manual: bool = False) -> None:
        # Bu fonksiyon da büyük ölçüde aynı kalabilir, sadece config okuma şekli değişir
        symbol = self.active_symbol
        side = SIDE_BUY if signal == 'LONG' else SIDE_SELL
        try:
            # ...
            strategy_config = self.strategy_configs[self.active_strategy_name] # Değişiklik
            # ... geri kalan mantık aynı ...
        except Exception as e:
            self._log(f"HATA: Pozisyon açma hatası - {e}")
    
    # ... (check_and_update_pnl, close_current_position, set_leverage, vb. fonksiyonları da
    # büyük ölçüde aynı kalacak, sadece loglama ve config okuma kısımları yukarıdaki gibi
    # _log() ve self.strategy_configs kullanacak şekilde güncellenmeli)

    def run_strategy(self):
        # Bu fonksiyonun içeriği neredeyse tamamen aynı kalacak.
        # Sadece config okuma şekli değiştiği için ona göre düzenlenmeli.
        self._log(f"Otomatik strateji ({self.active_strategy_name}) çalıştırıldı...")
        while self.strategy_active:
            try:
                # ...
                strategy_config = self.strategy_configs[self.active_strategy_name] # Değişiklik
                timeframe = strategy_config['timeframe']
                # ... geri kalan mantık aynı
            except Exception as e:
                self._log(f"ANA DÖNGÜ HATASI: {e}")
                time.sleep(60)
    
    # ... Geri kalan tüm trading_bot.py fonksiyonlarını buraya kopyalayın
    # ve config okuma kısımlarını yukarıdaki gibi güncelleyin.
    # Önemli olan, artık configparser yerine self.değişkenler veya self.strategy_configs kullanmak.
    
    async def stream_position_data_async(self, queue: asyncio.Queue):
        """Web soketine veri göndermek için asenkron versiyon."""
        try:
            account_info = self.client.futures_account()
            positions = [p for p in account_info['positions'] if float(p['positionAmt']) != 0]
            if positions:
                # ... (eski _stream_position_data fonksiyonunuzdaki mantığın aynısı)
                position_data = { ... }
                await queue.put({"type": "position_update", "data": position_data})
            else:
                await queue.put({"type": "position_update", "data": None})
        except Exception as e:
            await queue.put({"type": "log", "data": f"Pozisyon verisi alınamadı: {e}"})

    def start_strategy_loop(self):
        if not self.strategy_active:
            self.strategy_active = True
            # run_strategy senkron bir fonksiyon olduğu için thread içinde çalıştırıyoruz
            threading.Thread(target=self.run_strategy, daemon=True).start()

    def stop_strategy_loop(self):
        self.strategy_active = False
        self._log("Otomatik strateji durdurma sinyali alındı.")