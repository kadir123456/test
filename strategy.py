# strategy.py (Düzeltilmiş Hali)

import pandas as pd
import pandas_ta as ta
import configparser
from typing import Tuple

# Fonksiyon adını 'get_signal' olarak düzelttik.
def get_signal(df: pd.DataFrame, config: configparser.SectionProxy) -> Tuple[str, float]:
    """
    Daha hızlı işlem yapmak için tasarlanmış, EMA kesişimi ve RSI onayına dayalı
    agresif bir momentum stratejisi.
    """
    # Strateji parametrelerini config'den oku
    # Not: Bu bölüm, gelecekte configparser yerine doğrudan dict alacak şekilde iyileştirilebilir.
    # Şimdilik, trading_bot.py'de bu uyumluluğu sağlıyoruz.
    ema_fast_len = int(config['ema_length_fast'])
    ema_slow_len = int(config['ema_length_slow'])
    rsi_len = int(config['rsi_length'])
    rsi_ob = int(config['rsi_overbought'])
    rsi_os = int(config['rsi_oversold'])
    atr_len = int(config['atr_length'])

    # İndikatörleri hesapla
    df.ta.ema(length=ema_fast_len, append=True)
    df.ta.ema(length=ema_slow_len, append=True)
    df.ta.rsi(length=rsi_len, append=True)
    df.ta.atr(length=atr_len, append=True)
    
    # İsimleri kısaltalım
    ema_fast_col = f"EMA_{ema_fast_len}"
    ema_slow_col = f"EMA_{ema_slow_len}"
    rsi_col = f"RSI_{rsi_len}"
    atr_col = f"ATRr_{atr_len}"

    # Son kapanan mumun verilerini al
    latest = df.iloc[-2]
    prev = df.iloc[-3]

    # Sinyal Koşullarını Belirle
    ema_bull_cross = latest[ema_fast_col] > latest[ema_slow_col] and prev[ema_fast_col] <= prev[ema_slow_col]
    ema_bear_cross = latest[ema_fast_col] < latest[ema_slow_col] and prev[ema_fast_col] >= prev[ema_slow_col]

    rsi_confirm_long = latest[rsi_col] > rsi_os
    rsi_confirm_short = latest[rsi_col] < rsi_ob
    
    # Nihai Sinyali Oluştur
    if ema_bull_cross and rsi_confirm_long:
        return 'LONG', latest[atr_col]
    
    if ema_bear_cross and rsi_confirm_short:
        return 'SHORT', latest[atr_col]
        
    return 'WAIT', 0
