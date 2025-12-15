from fastapi import FastAPI
import requests

app = FastAPI()

@app.get("/")
def root():
    return {"status": "paper trading bot is alive"}

@app.get("/price")
def get_price(symbol: str = "BTCUSDT"):
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    r = requests.get(url, timeout=5)
    r.raise_for_status()
    return r.json()
