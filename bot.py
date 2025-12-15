import os
import json
import time
import asyncio
import urllib.request
from dataclasses import dataclass, asdict
from typing import List, Optional

from fastapi import FastAPI

# =========================
# CONFIG (Render Env Vars)
# =========================
SYMBOL = os.getenv("SYMBOL", "BTCUSDT").upper()
INTERVAL = os.getenv("INTERVAL", "5m")          # 1m, 3m, 5m, 15m, 1h...
KLINES_LIMIT = int(os.getenv("KLINES_LIMIT", "200"))

LOOP_SECONDS = float(os.getenv("LOOP_SECONDS", "30"))  # how often we poll Binance
EMA_PERIOD = int(os.getenv("EMA_PERIOD", "13"))        # classic Elder Bull/Bear Power uses EMA(13)
STRONG_TH = float(os.getenv("STRONG_TH", "0"))         # threshold around 0; you can set e.g. 50, 100...

# Paper sizing (your rule)
BASE_USD = float(os.getenv("BASE_USD", "500"))       # base entry
ADD_USD = float(os.getenv("ADD_USD", "20"))          # add-ons
MAX_CAPITAL = float(os.getenv("MAX_CAPITAL", "800")) # total allocated

# DCA rule (when price moves against position)
ADD_STEP_PCT = float(os.getenv("ADD_STEP_PCT", "0.25")) / 100.0  # 0.25% default

# =========================
# STATE
# =========================
@dataclass
class Position:
    side: str                      # "long" or "short"
    qty: float                     # position quantity in asset (BTC)
    avg_price: float               # average entry price
    used_usd: float                # allocated USD (base + adds)
    adds: int                      # number of add-ons

@dataclass
class BotState:
    symbol: str = SYMBOL
    interval: str = INTERVAL
    last_price: Optional[float] = None
    last_signal: Optional[str] = None          # "long" / "short" / None
    last_action: Optional[str] = None          # text
    last_update_ts: Optional[int] = None

    # indicators
    ema: Optional[float] = None
    bull_power: Optional[float] = None
    bear_power: Optional[float] = None
    bull_power_prev: Optional[float] = None
    bear_power_prev: Optional[float] = None

    # paper account
    cash_usd: float = 0.0
    realized_pnl: float = 0.0
    position: Optional[Position] = None

state = BotState(cash_usd=0.0)

app = FastAPI()

# =========================
# BINANCE (public)
# =========================
def fetch_klines(symbol: str, interval: str, limit: int) -> List[list]:
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "paper-bot/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)

def parse_hlc(klines: List[list]):
    highs, lows, closes = [], [], []
    for k in klines:
        highs.append(float(k[2]))
        lows.append(float(k[3]))
        closes.append(float(k[4]))
    return highs, lows, closes

def ema_last(values: List[float], period: int) -> float:
    if len(values) < period:
        return sum(values) / max(1, len(values))
    k = 2 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
    return ema

# =========================
# SIGNAL LOGIC (reversal)
# =========================
def calc_bull_bear(highs, lows, closes, period):
    ema = ema_last(closes, period)
    bull = highs[-1] - ema
    bear = lows[-1] - ema
    return ema, bull, bear

def decide_signal(bull_prev, bear_prev, bull, bear, strong_th=0.0):
    """
    Simple reversal logic:
    - LONG when bull crosses above 0 AND bear is improving (rising).
    - SHORT when bear crosses below 0 AND bull is worsening (falling).
    strong_th can be used to require bull/bear beyond a threshold.
    """
    if bull_prev is None or bear_prev is None:
        return None

    long_cross = (bull_prev <= 0.0 and bull > 0.0 and bear > bear_prev)
    short_cross = (bear_prev >= 0.0 and bear < 0.0 and bull < bull_prev)

    # optional "strong" filter
    if strong_th > 0:
        long_cross = long_cross and (bull > strong_th)
        short_cross = short_cross and (abs(bear) > strong_th)

    if long_cross:
        return


ong"
    if short_cross:
        return "short"
    return None

# =========================
# PAPER TRADING
# =========================
def usd_to_qty(usd: float, price: float) -> float:
    if price <= 0:
        return 0.0
    return usd / price

def close_position(pos: Position, price: float) -> float:
    """Return realized PnL in USD for closing at price."""
    if pos.qty == 0:
        return 0.0
    if pos.side == "long":
        return (price - pos.avg_price) * pos.qty
    else:
        return (pos.avg_price - price) * pos.qty

def open_position(side: str, price: float) -> Position:
    qty = usd_to_qty(BASE_USD, price)
    return Position(side=side, qty=qty, avg_price=price, used_usd=BASE_USD, adds=0)

def add_to_position(pos: Position, price: float) -> Position:
    add_usd = min(ADD_USD, MAX_CAPITAL - pos.used_usd)
    if add_usd <= 0:
        return pos
    add_qty = usd_to_qty(add_usd, price)
    new_qty = pos.qty + add_qty
    if new_qty <= 0:
        return pos
    new_avg = (pos.avg_price * pos.qty + price * add_qty) / new_qty
    pos.qty = new_qty
    pos.avg_price = new_avg
    pos.used_usd += add_usd
    pos.adds += 1
    return pos

def maybe_dca(pos: Position, price: float) -> bool:
    """Add 20 USD if price moved against position by ADD_STEP_PCT from avg."""
    if pos.used_usd >= MAX_CAPITAL:
        return False

    if pos.side == "long":
        # adverse move: price below avg
        if price < pos.avg_price * (1 - ADD_STEP_PCT):
            add_to_position(pos, price)
            return True
    else:
        # adverse move: price above avg
        if price > pos.avg_price * (1 + ADD_STEP_PCT):
            add_to_position(pos, price)
            return True

    return False

# =========================
# MAIN LOOP
# =========================
async def bot_loop():
    while True:
        try:
            klines = fetch_klines(SYMBOL, INTERVAL, KLINES_LIMIT)
            highs, lows, closes = parse_hlc(klines)

            price = closes[-1]
            ema, bull, bear = calc_bull_bear(highs, lows, closes, EMA_PERIOD)

            # store previous indicator
            state.bull_power_prev = state.bull_power
            state.bear_power_prev = state.bear_power

            # update state
            state.last_price = price
            state.ema = ema
            state.bull_power = bull
            state.bear_power = bear
            state.last_update_ts = int(time.time())

            # decide signal
            sig = decide_signal(
                state.bull_power_prev,
                state.bear_power_prev,
                bull,
                bear,
                STRONG_TH
            )

            action = None

            # trading logic (reversal)
            if sig:
                state.last_signal = sig

                if state.position is None:
                    state.position = open_position(sig, price)
                    action = f"OPEN {sig.upper()} base={BASE_USD}$ @ {price:.2f}"
                else:
                    # if opposite signal -> close & reverse
                    if state.position.side != sig:
                        pnl = close_position(state.position, price)
                        state.realized_pnl += pnl
                        action = f"CLOSE {state.position.side.upper()} @ {price:.2f} | PnL={pnl:.2f}$ -> REVERSE to {sig.upper()}"
                        state.position = open_position(sig, price)
                        action += f" | OPEN base={BASE_USD}$ @ {price:.2f}"
                    else:
                        action = f"SIGNAL {sig.upper()} but already in position -> HOLD"

            # DCA add-on logic
            if state.position is not None:
                did_add = maybe_dca(state.position, price)
                if did_add:
                    action = (action + " | " if action else "") + \
                             f"ADD +{ADD_USD}$ (used={state.position.used_usd:.0f}$, adds={state.position.adds}) avg={state.position.avg_price:.2f}"

            if action:
                state.last_action = action
                print(


f"[{time.strftime('%H:%M:%S')}] {SYMBOL} {INTERVAL} "
                    f"price={price:.2f} ema={ema:.2f} bull={bull:.2f} bear={bear:.2f} :: {action}",
                    flush=True
                )

        except Exception as e:
            state.last_action = f"ERROR: {e}"
            print(f"[ERROR] {e}", flush=True)

        await asyncio.sleep(LOOP_SECONDS)

@app.on_event("startup")
async def _startup():
    # start background loop
    asyncio.create_task(bot_loop())

# =========================
# HTTP ENDPOINTS
# =========================
@app.get("/")
def root():
    return {"status": "ok", "service": "paper-bullbear-bot", "symbol": SYMBOL, "interval": INTERVAL}

@app.get("/status")
def status():
    d = asdict(state)
    # position is dataclass too, but stored inside state as object -> convert safely
    if state.position is not None:
        d["position"] = asdict(state.position)
        # unrealized pnl
        if state.last_price:
            upnl = close_position(state.position, state.last_price)
            d["unrealized_pnl"] = upnl
            d["equity_pnl_total"] = state.realized_pnl + upnl
    else:
        d["position"] = None
        d["unrealized_pnl"] = 0.0
        d["equity_pnl_total"] = state.realized_pnl
    return d

@app.get("/health")
def health():
    return {"ok": True}"l
