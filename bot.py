from fastapi import FastAPI, Request, HTTPException
import os
import time

app = FastAPI()

# ===== НАСТРОЙКИ =====
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

START_BALANCE = 800.0
BASE_SIZE = 500.0
STEP_SIZE = 20.0

# ===== СОСТОЯНИЕ =====
state = {
    "balance": START_BALANCE,
    "equity": START_BALANCE,
    "position": None,        # "long" / "short"
    "entry_price": None,
    "position_size": 0.0,
    "flip_count": 0,
    "last_signal": None,
    "last_ts": None,
}

# ===== HEALTH CHECK =====
@app.get("/")
def root():
    return {"status": "paper trading bot is alive"}

# ===== WEBHOOK =====
"/webhook"
async def webhook(request: Request):
    data = await request.json()

    secret = str(data.get("secret", ""))
    if WEBHOOK_SECRET and secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret")

    signal = data.get("signal")
    if signal not in ("long", "short"):
        raise HTTPException(status_code=400, detail="Invalid signal")

    # логика фиксации сигнала (пока без реального трейдинга)
    state["last_signal"] = signal
    state["last_ts"] = int(time.time())
    state["flip_count"] += 1
    state["position"] = signal
    state["position_size"] = BASE_SIZE + state["flip_count"] * STEP_SIZE

    return {
        "ok": True,
        "received": data,
        "state": state
    }
