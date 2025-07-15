import os
import psycopg2
import time
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
                # PostgreSQL'e uygun syntax
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
        # ON CONFLICT... sayesinde aynı trade_id tekrar eklenmez
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

# get_all_trades ve calculate_stats fonksiyonları SQLite versiyonu ile neredeyse aynıdır.
# Sadece cursor kullanımını `with conn.cursor() as cursor:` bloğu içine alarak daha güvenli hale getirebilirsiniz.
# Bu iki fonksiyonu eski database.py dosyanızdan kopyalayabilirsiniz.

# Uygulama başladığında tabloyu kontrol et/oluştur
create_table()