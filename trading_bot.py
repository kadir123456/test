# trading_bot.py (Düzenlenmiş ve configparser yerine dict kullanan versiyon)

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

        self.socket_manager = BinanceSocketManager(self.client)
        threading.Thread(target=self.start_user_data_stream, daemon=True).start()

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
                'ema_length_fast': os.environ.get('KADIRV2_EMA_FAST', 9),
                'ema_length_slow': os.environ.get('KADIRV2_EMA_SLOW', 21),
                'rsi_length': os.environ.get('KADIRV2_RSI_LENGTH', 14),
                'rsi_overbought': os.environ.get('KADIRV2_RSI_OB', 70),
                'rsi_oversold': os.environ.get('KADIRV2_RSI_OS', 30),
                'atr_length': os.environ.get('KADIRV2_ATR_LEN', 14)
            },
            "Scalper": {
                'timeframe': os.environ.get('SCALPER_TIMEFRAME', '1m'),
                'atr_multiplier_sl': float(os.environ.get('SCALPER_ATR_SL', 1.0)),
                'volume_ma_length': os.environ.get('SCALPER_VOL_MA_LEN', 20),
                'volume_threshold': os.environ.get('SCALPER_VOL_THRESHOLD', 2.0),
                'candle_body_ratio': os.environ.get('SCALPER_BODY_RATIO', 0.6),
                'atr_length': os.environ.get('SCALPER_ATR_LEN', 14)
            }
        }

    def _log(self, message: str) -> None:
        if self.ui_update_callback:
            self.ui_update_callback("log", message)
        print(message)

    async def process_user_stream_message(self, msg):
        # Aynı
        pass

    def start_user_data_stream(self):
        # Aynı
        pass

    def get_usdt_balance(self) -> float:
        # Aynı
        pass

    def calculate_quantity(self, balance: float) -> Optional[float]:
        # Aynı
        pass

    def _get_market_data(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        # Aynı
        pass

    def open_position(self, signal: str, atr: float, quantity: float, manual: bool = False) -> None:
        # Aynı
        pass

    def check_and_update_pnl(self, symbol: str):
        # Aynı
        pass

    def close_current_position(self, from_emergency_button=False) -> None:
        # Aynı
        pass

    def set_leverage(self, leverage: int, symbol: str):
        # Aynı
        pass

    def set_quantity(self, quantity_usd: float):
        # Aynı
        pass

    def manual_trade(self, side: str):
        strategy_config = self.strategy_configs[self.active_strategy_name]
        timeframe = strategy_config['timeframe']
        df = self._get_market_data(self.active_symbol, timeframe)
        if df is None: return

        _, atr_value = self.get_active_strategy_signal(df)
        balance = self.get_usdt_balance()
        quantity = self.calculate_quantity(balance)
        if quantity: self.open_position(side, atr_value, quantity, manual=True)

    def update_symbol(self, mode: str, manual_symbol: str = ""):
        # Aynı
        pass

    def set_risk_mode(self, mode: str, roi_percent: float = 2.0):
        # Aynı
        pass

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
        # Aynı mantıkla devam eder
        pass

    def start_strategy_loop(self):
        if not self.strategy_active:
            self.strategy_active = True
            threading.Thread(target=self.run_strategy, daemon=True).start()

    def stop_strategy_loop(self):
        self.strategy_active = False

    def stop_all(self):
        self.running = False
        self.strategy_active = False
