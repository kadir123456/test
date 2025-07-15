# Gerekli kütüphaneleri ve modülleri içe aktarıyoruz
import os
import asyncio
import secrets
from typing import List, Dict, Any

from fastapi import (
    FastAPI, WebSocket, Request, Depends, 
    HTTPException, status
)
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

# Kendi yazdığımız modülleri içe aktarıyoruz
import database
from trading_bot import TradingBot

# --------------------------------------------------------------------------
# --- 1. UYGULAMA VE GÜVENLİK AYARLARI
# --------------------------------------------------------------------------

# FastAPI uygulamasını oluşturuyoruz
app = FastAPI(title="KadirV2 Pro Trading Terminal")

# HTTP Basic Authentication (tarayıcıda şifre sorma) mekanizmasını oluşturuyoruz
security = HTTPBasic()

# Ortam değişkenlerinden (Environment Variables) uygulama giriş bilgilerini alıyoruz
# Bu değişkenleri Render.com arayüzünden ayarlayacaksınız
APP_USERNAME = os.environ.get("APP_USERNAME")
APP_PASSWORD = os.environ.get("APP_PASSWORD")

# HTML şablonları ve statik dosyalar (CSS, JS) için yolları tanımlıyoruz
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Botumuzun tek bir örneğini ve arayüz güncelleme kuyruğunu oluşturuyoruz
update_queue = asyncio.Queue()
bot_instance = TradingBot(ui_update_callback=lambda type, data: update_queue.put_nowait({"type": type, "data": data}))


# --------------------------------------------------------------------------
# --- 2. KULLANICI DOĞRULAMA FONKSİYONU
# --------------------------------------------------------------------------

# Bu fonksiyon, her istekte kullanıcı adı ve şifrenin doğru olup olmadığını kontrol eder
def authenticate_user(credentials: HTTPBasicCredentials = Depends(security)):
    # Eğer Render.com'da kullanıcı adı ve şifre ayarlanmamışsa, hata ver
    if not APP_USERNAME or not APP_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Sunucu tarafında uygulama için giriş bilgileri ayarlanmamış.",
        )

    # Zamanlama saldırılarına karşı güvenli karşılaştırma yapıyoruz
    is_correct_username = secrets.compare_digest(credentials.username, APP_USERNAME)
    is_correct_password = secrets.compare_digest(credentials.password, APP_PASSWORD)
    
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kullanıcı adı veya şifre yanlış",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# --------------------------------------------------------------------------
# --- 3. API İSTEK MODELLERİ (Pydantic)
# --------------------------------------------------------------------------

# Ayarları değiştirirken tarayıcıdan gelecek verinin yapısını tanımlar
class LeverageRequest(BaseModel):
    leverage: int
class QuantityRequest(BaseModel):
    quantity_usd: float
class SymbolRequest(BaseModel):
    mode: str
    symbol: str = ""
class RiskRequest(BaseModel):
    mode: str
    roi: float
class StrategyRequest(BaseModel):
    strategy_name: str


# --------------------------------------------------------------------------
# --- 4. WEB SAYFASI VE API ENDPOINT'LERİ
# --------------------------------------------------------------------------

# Ana sayfayı sunan endpoint. Artık şifre korumalı.
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, username: str = Depends(authenticate_user)):
    initial_stats = database.calculate_stats()
    initial_history = database.get_all_trades()
    initial_settings = {
        "leverage": bot_instance.leverage,
        "quantity_usd": bot_instance.quantity_usd,
        "active_symbol": bot_instance.active_symbol,
        "risk_mode": bot_instance.risk_management_mode,
        "fixed_roi_tp": bot_instance.fixed_roi_tp * 100,
        "strategy": bot_instance.active_strategy_name
    }
    return templates.TemplateResponse("index.html", {
        "request": request,
        "stats": initial_stats,
        "history": initial_history,
        "settings": initial_settings
    })

# Canlı güncellemeler için WebSocket endpoint'i.
# Ana sayfa korumalı olduğu için bu bağlantı ancak şifre girildikten sonra kurulabilir.
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    async def position_updater():
        while True:
            await bot_instance.stream_position_data_async(update_queue)
            await asyncio.sleep(2)
    
    async def queue_listener():
        while True:
            update = await update_queue.get()
            await websocket.send_json(update)
            update_queue.task_done()

    pos_task = asyncio.create_task(position_updater())
    queue_task = asyncio.create_task(queue_listener())
    
    try:
        await asyncio.gather(pos_task, queue_task)
    except Exception:
        pos_task.cancel()
        queue_task.cancel()
        await websocket.close()


# --- Bot Kontrol API Endpoint'leri (Hepsi Şifre Korumalı) ---

@app.post("/start")
async def start_bot(username: str = Depends(authenticate_user)):
    bot_instance.start_strategy_loop()
    return {"status": "success", "message": "Strateji başlatıldı."}

@app.post("/stop")
async def stop_bot(username: str = Depends(authenticate_user)):
    bot_instance.stop_strategy_loop()
    return {"status": "success", "message": "Strateji durduruldu."}

@app.post("/set-leverage")
async def set_leverage(req: LeverageRequest, username: str = Depends(authenticate_user)):
    bot_instance.set_leverage(req.leverage, bot_instance.active_symbol)
    return {"status": "success", "message": f"Kaldıraç {req.leverage}x olarak ayarlandı."}

@app.post("/set-quantity")
async def set_quantity(req: QuantityRequest, username: str = Depends(authenticate_user)):
    bot_instance.set_quantity(req.quantity_usd)
    return {"status": "success", "message": f"Miktar ~{req.quantity_usd} USDT olarak ayarlandı."}

@app.post("/manual-trade/{side}")
async def manual_trade(side: str, username: str = Depends(authenticate_user)):
    if side.upper() in ["LONG", "SHORT"]:
        bot_instance.manual_trade(side.upper())
        return {"status": "success", "message": f"Manuel {side.upper()} işlemi tetiklendi."}
    return {"status": "error", "message": "Geçersiz işlem yönü."}

@app.post("/emergency-close")
async def emergency_close(username: str = Depends(authenticate_user)):
    bot_instance.close_current_position(from_emergency_button=True)
    return {"status": "success", "message": "Acil kapatma emri gönderildi."}

@app.post("/update-symbol")
async def update_symbol(req: SymbolRequest, username: str = Depends(authenticate_user)):
    bot_instance.update_symbol(req.mode, req.symbol)
    return {"status": "success", "message": "Sembol güncellendi."}

@app.post("/update-risk")
async def update_risk(req: RiskRequest, username: str = Depends(authenticate_user)):
    bot_instance.set_risk_mode(req.mode, req.roi)
    return {"status": "success", "message": "Risk modu güncellendi."}

@app.post("/update-strategy")
async def update_strategy(req: StrategyRequest, username: str = Depends(authenticate_user)):
    bot_instance.set_strategy(req.strategy_name)
    return {"status": "success", "message": "Strateji güncellendi."}


# --- Veri Çekme API Endpoint'leri (Hepsi Şifre Korumalı) ---

@app.get("/get-stats", response_model=Dict[str, Any])
async def get_stats(username: str = Depends(authenticate_user)):
    return database.calculate_stats()

@app.get("/get-history", response_model=List[Any])
async def get_history(username: str = Depends(authenticate_user)):
    return database.get_all_trades()


# --------------------------------------------------------------------------
# --- 5. UYGULAMAYI ÇALIŞTIRMA
# --------------------------------------------------------------------------

# Render.com'un uygulamayı çalıştırması için standart başlangıç bloğu
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main_web:app", host="0.0.0.0", port=port, reload=True)