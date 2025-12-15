from fastapi import FastAPI, Request, HTTPException
import os

app = FastAPI()

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

@app.get("/")
def root():
    return {"status": "ok"}

"/webhook"
async def webhook(request: Request):
    data = await request.json()

    # проверка секрета
    if WEBHOOK_SECRET and data.get("secret") != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Bad secret")

    print("WEBHOOK RECEIVED:", data)

    signal = data.get("signal")
    return {"ok": True, "signal": signal}
