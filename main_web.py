import os
import asyncio
import secrets
import threading
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

import database
from trading_bot import TradingBot

# --- 1. UYGULAMA VE GÜVENLİK AYARLARI ---
app = FastAPI(title="KadirV2 Pro Trading Terminal")
security = HTTPBasic()

APP_USERNAME = os.environ.get("APP_USERNAME")
APP_PASSWORD = os.environ.get("APP_PASSWORD")

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

update_queue = asyncio.Queue()
bot_instance = TradingBot(ui_update_callback=lambda t, d: update_queue.put_nowait({"type": t, "data": d}))

# --- 2. KULLANICI DOĞRULAMA FONKSİYONU ---
def authenticate_user(credentials: HTTPBasicCredentials = Depends(security)):
    if not APP_USERNAME or not APP_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Sunucu tarafında kullanıcı adı veya şifre tanımlı değil."
        )
    is_user = secrets.compare_digest(credentials.username, APP_USERNAME)
    is_pass = secrets.compare_digest(credentials.password, APP_PASSWORD)
    
    if not (is_user and is_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kullanıcı adı veya şifre yanlış.",
            headers={"WWW-Authenticate": "Basic"}
        )
    return credentials.username

# --- 3. API İSTEK MODELLERİ ---
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

# --- 4. WEB SAYFASI VE API ENDPOINT'LERİ ---
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

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    try:
        while True:
            update = await update_queue.get()
            await websocket.send_json(update)
            update_queue.task_done()
    except Exception:
        print("WebSocket bağlantısı kapandı.")

# --- Bot Kontrolleri ---
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
    return {"status": "success"}

@app.post("/set-quantity")
async def set_quantity(req: QuantityRequest, username: str = Depends(authenticate_user)):
    bot_instance.set_quantity(req.quantity_usd)
    return {"status": "success"}

@app.post("/manual-trade/{side}")
async def manual_trade(side: str, username: str = Depends(authenticate_user)):
    if side.upper() in ["LONG", "SHORT"]:
        threading.Thread(target=bot_instance.manual_trade, args=(side.upper(),), daemon=True).start()
        return {"status": "success"}
    return {"status": "error", "message": "Geçersiz işlem yönü. 'LONG' veya 'SHORT' olmalıdır."}

@app.post("/emergency-close")
async def emergency_close(username: str = Depends(authenticate_user)):
    threading.Thread(target=bot_instance.close_current_position, args=(True,), daemon=True).start()
    return {"status": "success", "message": "Acil kapatma emri gönderildi."}

@app.post("/update-symbol")
async def update_symbol(req: SymbolRequest, username: str = Depends(authenticate_user)):
    bot_instance.update_symbol(req.mode, req.symbol)
    return {"status": "success"}

@app.post("/update-risk")
async def update_risk(req: RiskRequest, username: str = Depends(authenticate_user)):
    bot_instance.set_risk_mode(req.mode, req.roi)
    return {"status": "success"}

@app.post("/update-strategy")
async def update_strategy(req: StrategyRequest, username: str = Depends(authenticate_user)):
    bot_instance.set_strategy(req.strategy_name)
    return {"status": "success"}

@app.get("/get-stats", response_model=Dict[str, Any])
async def get_stats(username: str = Depends(authenticate_user)):
    return database.calculate_stats()

@app.get("/get-history", response_model=List[Any])
async def get_history(username: str = Depends(authenticate_user)):
    return database.get_all_trades()

# --- 5. UYGULAMA BAŞLATICI ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main_web:app", host="0.0.0.0", port=port, reload=True)
