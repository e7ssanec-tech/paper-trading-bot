========================
def compute_bull_bear_strong(ts, o, h, l, c) -> Dict[str, Any]:
    """
    Compute EMA13, Bull/Bear Power and STRONG via ATR14.
    Returns dict with signal ("long"/"short"/None) + metrics.
    """
    if len(c) < 30:
        return {"ok": False, "reason": "not_enough_bars"}

    ema13 = ema_series(c, 13)[-1]
    atr14 = atr_last(h, l, c, 14)
    if atr14 is None or atr14 == 0:
        return {"ok": False, "reason": "not_enough_atr"}

    bull = h[-1] - ema13
    bear = l[-1] - ema13

    bull_strong = bull > (K_STRONG * atr14)
    bear_strong = bear < (-K_STRONG * atr14)

    signal = None
    if bull_strong and not bear_strong:
        signal = "long"
    elif bear_strong and not bull_strong:
        signal = "short"

    return {
        "ok": True,
        "bar_ts": ts[-1],
        "price": c[-1],
        "ema13": ema13,
        "atr14": atr14,
        "bullPower": bull,
        "bearPower": bear,
        "k": K_STRONG,
        "bullStrong": bull_strong,
        "bearStrong": bear_strong,
        "signal": signal,
    }

def close_position(price: float):
    if trade["position"] is None:
        trade["last_close_pnl"] = 0.0
        return
    pnl = unrealized_pnl(trade["position"], trade["entry_price"], price, trade["position_size"])
    trade["balance"] += pnl
    trade["last_close_pnl"] = pnl
    trade["position"] = None
    trade["entry_price"] = None
    trade["position_size"] = 0.0

def open_position(side: str, price: float):
    # Лесенка: 500 + 20*flip_count
    size = BASE_SIZE + STEP_SIZE * trade["flip_count"]

    # Если хочешь строго “не больше депо”, оставляем ограничение:
    if size > trade["balance"]:
        size = trade["balance"]

    trade["position"] = side
    trade["entry_price"] = price
    trade["position_size"] = float(size)

def apply_paper_logic(signal: Optional[str], price: float):
    """
    Rules:
    - If no signal: no open/flip action, only update equity
    - If no position and signal exists: open with BASE_SIZE (flip_count=0 => 500)
    - If signal == current position: hold
    - If signal opposite: close -> flip_count += 1 -> open new with increased size
    """
    global _last_action_signal

    # Update last price anyway
    trade["last_price"] = price

    if signal is None:
        # Only mark equity
        u = unrealized_pnl(trade["position"], trade["entry_price"], price, trade["position_size"])
        trade["equity"] = trade["balance"] + u
        return

    # Avoid repeating the same action if bot polls multiple times within same bar
    # (i.e., if signal stays "long", we don't re-open every minute)
    if signal == _last_action_signal and trade["position"] == signal:
        u = unrealized_pnl(trade["position"], trade["entry_price"], price, trade["position_size"])
        trade["equity"] = trade["balance"] + u
        return

    if trade["position"] is None:
        trade["last_signal"] = signal
        open_position(signal, price)
        _last_action_signal = signal

    elif trade["position"] == signal:
        trade["last_signal"] = signal
        _last_action_signal = signal

    else:
        # flip
        close_position(price)
        trade["flip_count"] += 1
        trade["last_signal"] = signal
        open_position(signal, price)
        _last_action_signal = signal

    u = unrealized_pnl(trade["position"], trade["entry_price"], price, trade["position_size"])
    trade["equity"] = trade["balance"] + u

def tick_once() -> Dict[str, Any]:
    """
    Single tick: fetch klines -> compute signal -> apply paper logic -> return snapshot.
    """
    ts, o, h, l, c = fetch_klines(SYMBOL, INTERVAL_MIN, LIMIT)
    metrics = compute_bull_bear_strong(ts, o, h, l, c)

    trade["last_tick_ts"] = int(time.time())
    trade["last_bar_ts"] = metrics.get("bar_ts")

    if metrics.get("ok"):
        apply_paper_logic(metrics["signal"], metrics["price"])
    else:
        # still mark equity if price exists
        if c:
            apply_paper_logic(None, c[-1])

    snapshot = {
        "metrics": metrics,
        "trade": trade,
    }

    # Ло


ги в Render:
    print("TICK:", snapshot, flush=True)
    return snapshot

# =========================
# FASTAPI ROUTES
# =========================
@app.api_route("/", methods=["GET", "HEAD"])
def root():
    return {
        "status": "ok",
        "symbol": SYMBOL,
        "tf_min": INTERVAL_MIN,
        "k_strong": K_STRONG,
        "paper": {"start_balance": START_BALANCE, "base_size": BASE_SIZE, "step_size": STEP_SIZE},
    }

@app.get("/state")
def state():
    # текущее состояние без форс-труда
    return {"trade": trade}

@app.get("/check")
def check():
    # ручной тик (удобно проверять, что всё работает)
    return tick_once()

# =========================
# BACKGROUND LOOP
# =========================
@app.on_event("startup")
def startup():
    def loop():
        while True:
            try:
                tick_once()
            except Exception as e:
                print("ERROR:", repr(e), flush=True)
            time.sleep(POLL_SEC)

    t = threading.Thread(target=loop, daemon=True)
    t.start() =
