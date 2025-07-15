# strategy_scalper.py (Düzeltilmiş Hali)

import pandas as pd
import pandas_ta as ta
import configparser
from typing import Tuple

def get_signal(df: pd.DataFrame, config: configparser.SectionProxy) -> Tuple[str, float]:
    """
    Ani hacim artışları ve güçlü momentum mumlarına dayalı hızlı bir scalping stratejisi.
    """
    # Strateji parametrelerini config'den oku
    vol_ma_len = int(config['volume_ma_length'])
    vol_thresh = float(config['volume_threshold'])
    candle_body_ratio = float(config['candle_body_ratio'])
    atr_len = int(config['atr_length'])

    # İndikatörleri hesapla
    df.ta.sma(close=df['volume'], length=vol_ma_len, append=True)
    df.ta.atr(length=atr_len, append=True)
    
    vol_sma_col = f"SMA_{vol_ma_len}"
    atr_col = f"ATRr_{atr_len}"

    # Son kapanan mumun verilerini al
    latest = df.iloc[-2]
    
    # Koşulları Hesapla
    # 1. Hacim Anormal Derecede Yüksek mi?
    is_volume_spike = latest['volume'] > (latest[vol_sma_col] * vol_thresh)
    
    # 2. Mum Gövdesi Güçlü mü? (Fitillerin kısa, gövdenin uzun olması)
    candle_range = latest['high'] - latest['low']
    body_size = abs(latest['close'] - latest['open'])
    is_strong_candle = (body_size / (candle_range + 1e-9)) >= candle_body_ratio

    # 3. Mumun Yönü
    is_bullish_candle = latest['close'] > latest['open']
    is_bearish_candle = latest['close'] < latest['open']

    # Nihai Sinyali Oluştur
    if is_volume_spike and is_strong_candle and is_bullish_candle:
        return 'LONG', latest[atr_col]
    
    if is_volume_spike and is_strong_candle and is_bearish_candle:
        return 'SHORT', latest[atr_col]
        
    return 'WAIT', 0
