import pandas as pd
import pandas_ta as ta
from typing import Tuple, Dict, Any

def get_signal(df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[str, float]:
    """
    Daha hızlı işlem yapmak için tasarlanmış, EMA kesişimi ve RSI onayına dayalı
    agresif bir momentum stratejisi.
    """

    # Strateji parametrelerini config sözlüğünden al
    ema_fast_len = int(config.get('ema_length_fast', 9))
    ema_slow_len = int(config.get('ema_length_slow', 21))
    rsi_len = int(config.get('rsi_length', 14))
    rsi_ob = int(config.get('rsi_overbought', 70))
    rsi_os = int(config.get('rsi_oversold', 30))
    atr_len = int(config.get('atr_length', 14))

    # İndikatörleri hesapla
    df.ta.ema(length=ema_fast_len, append=True)
    df.ta.ema(length=ema_slow_len, append=True)
    df.ta.rsi(length=rsi_len, append=True)
    df.ta.atr(length=atr_len, append=True)

    # Kolon adları
    ema_fast_col = f"EMA_{ema_fast_len}"
    ema_slow_col = f"EMA_{ema_slow_len}"
    rsi_col = f"RSI_{rsi_len}"
    atr_col = f"ATRr_{atr_len}"

    # Veri kontrolü
    if df.shape[0] < 3 or any(col not in df.columns for col in [ema_fast_col, ema_slow_col, rsi_col, atr_col]):
        return 'WAIT', 0

    # Son kapanan mumun verilerini al
    latest = df.iloc[-2]
    prev = df.iloc[-3]

    # Sinyal Koşulları
    ema_bull_cross = latest[ema_fast_col] > latest[ema_slow_col] and prev[ema_fast_col] <= prev[ema_slow_col]
    ema_bear_cross = latest[ema_fast_col] < latest[ema_slow_col] and prev[ema_fast_col] >= prev[ema_slow_col]
    rsi_confirm_long = latest[rsi_col] > rsi_os
    rsi_confirm_short = latest[rsi_col] < rsi_ob

    # Sinyal üret
    if ema_bull_cross and rsi_confirm_long:
        return 'LONG', latest[atr_col]

    if ema_bear_cross and rsi_confirm_short:
        return 'SHORT', latest[atr_col]

    return 'WAIT', 0
