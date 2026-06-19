#!/usr/bin/env python3
"""Quant BTC/USD bot — multi-indicator, SQLite, practice mode."""
import sys, os, time, json, sqlite3, importlib

AMOUNT = 10
base_amount = 10
consecutive_losses = 0
STOP_LOSS = -100
ASSET = 'BTCUSD'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(BASE_DIR, "results")
os.makedirs(RESULTS, exist_ok=True)

sys.path.insert(0, os.path.join(BASE_DIR, '..'))
# Load .env
_env = os.path.join(BASE_DIR, '..', '..', '.env')
if os.path.exists(_env):
    for _line in open(_env):
        _line = _line.strip()
        if _line and not _line.startswith('#') and '=' in _line:
            _k, _v = _line.split('=', 1)
            os.environ.setdefault(_k.strip(), _v.strip())

from iqoptionapi.stable_api import IQ_Option
from quant_btc.strategy import analyze

# --- Debug log ---
log_file = os.path.join(RESULTS, "quant_btc.log")
def log(msg):
    ts = time.strftime('%H:%M:%S')
    with open(log_file, "a") as f:
        f.write(f"{ts} {msg}\n")
    print(f"{ts} {msg}", flush=True)

# --- SQLite ---
db_path = os.path.join(RESULTS, "quant_btc.db")
def get_db():
    db = sqlite3.connect(db_path)
    db.execute("PRAGMA journal_mode=WAL")
    return db

def init_db():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time TEXT NOT NULL,
            asset TEXT NOT NULL,
            direction TEXT NOT NULL,
            amount REAL NOT NULL,
            confidence INTEGER,
            profit REAL NOT NULL,
            win INTEGER NOT NULL,
            payout REAL,
            balance REAL,
            score REAL,
            signals TEXT
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS idx_time ON trades(time)")
    db.commit()
    db.close()

def db_insert_trade(t):
    db = get_db()
    db.execute(
        "INSERT INTO trades (time, asset, direction, amount, confidence, profit, win, payout, balance, score, signals) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (t["time"], t["asset"], t["direction"], t["amount"], t.get("confidence"),
         t["profit"], int(t["win"]), t.get("payout"), t.get("balance"), t.get("score"), t.get("signals"))
    )
    db.commit()
    db.close()

def db_get_stats():
    db = get_db()
    row = db.execute("SELECT COUNT(*), SUM(CASE WHEN win=1 THEN 1 ELSE 0 END), SUM(profit) FROM trades").fetchone()
    db.close()
    total, wins, pnl = row
    return int(total or 0), int(wins or 0), float(pnl or 0)

# --- Martingale ---
state_file = os.path.join(RESULTS, "quant_state.json")
def load_state():
    if os.path.exists(state_file):
        try:
            s = json.load(open(state_file))
            return s.get("consecutive_losses", 0)
        except: pass
    return 0

def save_state(cl):
    json.dump({"consecutive_losses": cl}, open(state_file, "w"))

init_db()
consecutive_losses = load_state()
AMOUNT = min(base_amount * (1.5 ** consecutive_losses), 100)

# --- Multi-timeframe candles ---
def get_multi_tf(api, asset):
    """Get candles on multiple timeframes for confluence."""
    results = {}
    for tf, count in [(60, 100), (300, 50)]:
        try:
            c = api.get_candles(asset, tf, count, time.time())
            if c and len(c) >= 30:
                results[tf] = [{"close": x.get("close",0), "max": x.get("max",0),
                               "min": x.get("min",0), "open": x.get("open",0)} for x in c]
        except: pass
    return results

# --- Main loop ---
log(f"Starting quant BTC bot | amount={AMOUNT} | stop_loss={STOP_LOSS}")

cycle = 0
while True:
    cycle += 1
    api = None
    try:
        api = IQ_Option(os.environ.get('IQ_OPTION_EMAIL',''), os.environ.get('IQ_OPTION_PASSWORD',''))
        import threading
        connect_result = [False, 'timeout']
        def _connect():
            connect_result[0], connect_result[1] = api.connect()
        t = threading.Thread(target=_connect, daemon=True)
        t.start()
        t.join(timeout=15)
        if t.is_alive():
            log("CONNECT TIMEOUT")
            time.sleep(10)
            continue
        ok, msg = connect_result[0], connect_result[1]
        if not ok:
            log(f"CONNECT FAIL: {msg}")
            time.sleep(30)
            continue
        log("Connected OK"); api.change_balance("PRACTICE")
        time.sleep(2)
        log("Getting balance...")

        bal = api.get_balance()
        log(f"Balance: {bal}")
        if bal < AMOUNT:
            log(f"BALANCE LOW: {bal}")
            time.sleep(60)
            continue

        total, wins, pnl = db_get_stats()
        if pnl <= STOP_LOSS:
            log(f"STOP LOSS HIT: {pnl:.1f} THB")
            break

        # Get multi-timeframe data
        candles_1m = None
        candles_5m = None
        try:
            log("Fetching 1m candles..."); candles_1m = api.get_candles(ASSET, 60, 100, time.time()); log(f"Got {len(candles_1m) if candles_1m else 0} 1m candles")
            log("Fetching 5m candles..."); candles_5m = api.get_candles(ASSET, 300, 50, time.time()); log(f"Got {len(candles_5m) if candles_5m else 0} 5m candles")
        except Exception as e:
            log(f"CANDLE ERR: {e}")
            time.sleep(10)
            continue

        if not candles_1m or len(candles_1m) < 50:
            log(f"Not enough candles: {len(candles_1m) if candles_1m else 0}")
            time.sleep(10)
            continue

        candle_list = [{"close": x.get("close",0), "max": x.get("max",0),
                        "min": x.get("min",0), "open": x.get("open",0)} for x in candles_1m]

        # Analyze
        direction, confidence = analyze(api, ASSET, candle_list)
        
        if direction is None:
            log(f"Cycle {cycle}: no signal")
            time.sleep(15)
            continue

        # Multi-TF confirmation: check 5m agrees
        if candles_5m and len(candles_5m) >= 30:
            candle_5m = [{"close": x.get("close",0), "max": x.get("max",0),
                          "min": x.get("min",0), "open": x.get("open",0)} for x in candles_5m]
            dir_5m, conf_5m = analyze(api, ASSET, candle_5m)
            if dir_5m and dir_5m != direction:
                log(f"MTF conflict: 1m={direction} vs 5m={dir_5m}, skipping")
                time.sleep(15)
                continue
            if dir_5m:
                confidence = min(confidence + 5, 95)
                log(f"MTF confirm: 1m={direction} 5m={dir_5m}")

        # Trade
        log(f"SIGNAL: {ASSET} {direction} conf={confidence} bet={int(AMOUNT)}")
        try:
            ok, tid = api.buy(int(AMOUNT), ASSET, direction, 1)
            if not ok:
                log(f"Buy failed: {tid}")
                time.sleep(10)
                continue
        except Exception as e:
            log(f"Buy error: {e}")
            time.sleep(10)
            continue

        log(f"Placed TID={tid}")
        time.sleep(68)

        try:
            result = api.check_win_v4(tid)
            win = result[0] == 'win'
        except:
            win = False

        payout = 87
        profit = AMOUNT * (payout / 100) if win else -AMOUNT
        trade = {
            "time": time.strftime('%Y-%m-%d %H:%M:%S'),
            "asset": ASSET, "direction": direction,
            "amount": int(AMOUNT), "confidence": confidence,
            "profit": profit, "win": win, "payout": payout,
            "balance": bal, "score": confidence,
            "signals": json.dumps([direction, f"conf={confidence}"]),
        }
        db_insert_trade(trade)

        # Martingale
        if win:
            consecutive_losses = 0
            AMOUNT = base_amount
        else:
            consecutive_losses += 1
            AMOUNT = min(base_amount * (1.5 ** consecutive_losses), 100)
        save_state(consecutive_losses)

        total, wins, pnl = db_get_stats()
        wr = wins / total * 100 if total > 0 else 0
        log(f"{'WIN' if win else 'LOSS'} {ASSET} {direction.upper()} now={wins}/{total} {wr:.0f}% pnl={pnl:+.1f} next_bet={int(AMOUNT)}")

        try: api._close_connect = lambda: None; api._close_connect()
        except: pass

    except Exception as e:
        log(f"ERR: {e}")
        try:
            if api: api._close_connect = lambda: None; api._close_connect()
        except: pass

    time.sleep(15)
