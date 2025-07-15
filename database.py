# database.py (Tam ve Düzeltilmiş Versiyon)

import os
import psycopg2
from typing import List, Dict, Any, Tuple

# Render, veritabanı URL'sini bu ortam değişkeniyle sağlar
DATABASE_URL = os.environ.get('DATABASE_URL')

def create_connection():
    """PostgreSQL veritabanı bağlantısı oluşturur."""
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
    except psycopg2.OperationalError as e:
        print(f"Veritabanı bağlantı hatası: {e}")
    return conn

def create_table():
    """'trades' tablosunu, eğer mevcut değilse, oluşturur."""
    conn = create_connection()
    if conn is not None:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS trades (
                        id SERIAL PRIMARY KEY,
                        symbol TEXT NOT NULL,
                        trade_id BIGINT UNIQUE NOT NULL,
                        side TEXT NOT NULL,
                        pnl REAL NOT NULL,
                        timestamp BIGINT NOT NULL
                    );
                """)
                conn.commit()
        except psycopg2.Error as e:
            print(f"Tablo oluşturma hatası: {e}")
        finally:
            conn.close()

def add_trade(trade_data: Dict[str, Any]):
    """Veritabanına yeni bir tamamlanmış işlem ekler."""
    conn = create_connection()
    if conn is not None:
        sql = ''' INSERT INTO trades(symbol, trade_id, side, pnl, timestamp)
                  VALUES(%s, %s, %s, %s, %s) ON CONFLICT (trade_id) DO NOTHING;'''
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, (
                    trade_data['symbol'],
                    trade_data['id'],
                    trade_data['side'],
                    float(trade_data['realizedPnl']),
                    int(trade_data['time'])
                ))
                conn.commit()
        except psycopg2.Error as e:
            print(f"İşlem ekleme hatası: {e}")
        finally:
            conn.close()

# ----- YENİ EKLENEN FONKSİYONLAR -----

def get_all_trades() -> List[Tuple]:
    """Tüm işlem kayıtlarını veritabanından çeker."""
    conn = create_connection()
    trades = []
    if conn is not None:
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id, symbol, trade_id, side, pnl, timestamp FROM trades ORDER BY timestamp DESC")
                trades = cursor.fetchall()
        except psycopg2.Error as e:
            print(f"İşlemleri getirme hatası: {e}")
        finally:
            conn.close()
    return trades

def calculate_stats() -> Dict[str, Any]:
    """Veritabanındaki verilere göre performans istatistikleri hesaplar."""
    trades = get_all_trades()
    if not trades:
        return {"total_pnl": 0, "win_rate": 0, "total_trades": 0, "wins": 0, "losses": 0}

    # Veritabanı sütun sırası: 0:id, 1:symbol, 2:trade_id, 3:side, 4:pnl, 5:timestamp
    total_pnl = sum(trade[4] for trade in trades)
    wins = sum(1 for trade in trades if trade[4] > 0)
    total_trades = len(trades)
    losses = total_trades - wins
    win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
    
    return {
        "total_pnl": total_pnl,
        "win_rate": win_rate,
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses
    }

# Uygulama başladığında tabloyu kontrol et/oluştur
create_table()
