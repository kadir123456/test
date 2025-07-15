import pandas as pd
import pandas_ta as ta
from typing import Tuple, Dict, Any

def get_signal(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[str, float]:
    """
    Ani hacim artışları ve güçlü momentum mumlarına dayalı hızlı bir scalping stratejisi.
    """

    # Parametreleri config sözlüğünden al
    vol_ma_len = int(config.get('volume_ma_length', 20))
    vol_thresh = float(config.get('volume_threshold', 1.5))
    candle_body_ratio = float(config.get('candle_body_ratio', 0.6))
    atr_len = int(config.get('atr_length', 14))

    # İndikatör hesaplamaları
    df.ta.sma(close=df['volume'], length=vol_ma_len, append=True)
    df.ta.atr(length=atr_len, append=True)

    vol_sma_col = f"SMA_{vol_ma_len}"
    atr_col = f"ATRr_{atr_len}"

    # Veri kontrolü
    if df.shape[0] < 2 or any(col not in df.columns for col in [vol_sma_col, atr_col]):
        return 'WAIT', 0

    latest = df.iloc[-2]

    # 1. Hacim artışı kontrolü
    is_volume_spike = latest['volume'] > (latest[vol_sma_col] * vol_thresh)

    # 2. Güçlü mum gövdesi kontrolü
    candle_range = latest['high'] - latest['low']
    body_size = abs(latest['close'] - latest['open'])
    is_strong_candle = (body_size / (candle_range + 1e-9)) >= candle_body_ratio

    # 3. Mumun yönü
    is_bullish_candle = latest['close'] > latest['open']
    is_bearish_candle = latest['close'] < latest['open']

    # Sinyal üretimi
    if is_volume_spike and is_strong_candle and is_bullish_candle:
        return 'LONG', latest[atr_col]
    
    if is_volume_spike and is_strong_candle and is_bearish_candle:
        return 'SHORT', latest[atr_col]

    return 'WAIT', 0
