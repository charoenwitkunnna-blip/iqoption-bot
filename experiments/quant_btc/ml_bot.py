#!/usr/bin/env python3
"""ML BTC/USD live trading bot — practice mode."""
import sys, os, time, json, pickle, sqlite3, threading

AMOUNT = 10
base_amount = 10
STOP_LOSS = -100
ASSET = 'BTCUSD'
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(BASE_DIR, "results")
MODEL_PATH = os.path.join(RESULTS, "btc_model.pkl")

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
from quant_btc.features_vec import make_all_features

# --- Log ---
log_file = os.path.join(RESULTS, "ml_btc.log")
def log(msg):
    ts = time.strftime('%H:%M:%S')
    with open(log_file, "a") as f:
        f.write(f"{ts} {msg}\n")
    print(f"{ts} {msg}", flush=True)

# --- DB ---
db_path = os.path.join(RESULTS, "ml_btc.db")
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
            confidence REAL,
            profit REAL NOT NULL,
            win INTEGER NOT NULL,
            payout REAL,
            balance REAL,
            model_prob REAL,
            features TEXT
        )
    """)
    db.commit(); db.close()

def db_insert(t):
    db = get_db()
    db.execute("INSERT INTO trades (time,asset,direction,amount,confidence,profit,win,payout,balance,model_prob,features) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (t['time'], t['asset'], t['direction'], t['amount'], t.get('confidence'),
         t['profit'], int(t['win']), t.get('payout'), t.get('balance'), t.get('model_prob'), t.get('features')))
    db.commit(); db.close()

def db_stats():
    db = get_db()
    r = db.execute("SELECT COUNT(*), SUM(CASE WHEN win=1 THEN 1 ELSE 0 END), SUM(profit) FROM trades").fetchone()
    db.close()
    return int(r[0] or 0), int(r[1] or 0), float(r[2] or 0)

# --- State ---
state_file = os.path.join(RESULTS, "ml_state.json")
def load_state():
    try: return json.load(open(state_file)).get("consecutive_losses", 0)
    except: return 0
def save_state(cl):
    json.dump({"consecutive_losses": cl}, open(state_file, "w"))

init_db()
consecutive_losses = load_state()
AMOUNT = min(base_amount * (1.5 ** consecutive_losses), 100)

# --- Load model ---
if not os.path.exists(MODEL_PATH):
    print(f"No model at {MODEL_PATH} — run train.py first!")
    sys.exit(1)

with open(MODEL_PATH, 'rb') as f:
    bundle = pickle.load(f)

model = bundle['model']
scaler = bundle['scaler']
feature_names = bundle['features']
log(f"Loaded model: {bundle['name']} (CV={bundle['score']:.3f}, {bundle['n_samples']} samples)")

# --- Connect helper with timeout ---
def connect_api():
    api = IQ_Option(os.environ.get('IQ_OPTION_EMAIL',''), os.environ.get('IQ_OPTION_PASSWORD',''))
    ok, msg = api.connect()
    if ok:
        api.change_balance('PRACTICE')
        time.sleep(1)
    return api if ok else None

# --- Main loop ---
log(f"Starting ML BTC bot | amount={AMOUNT}")

cycle = 0
while True:
    cycle += 1
    api = None
    try:
        api = connect_api()
        if not api:
            log("Connect failed")
            time.sleep(30)
            continue

        bal = api.get_balance()
        total, wins, pnl = db_stats()
        if pnl <= STOP_LOSS:
            log(f"STOP LOSS: {pnl:.1f}")
            break

        # Get candles (multiple batches for enough history)
        try:
            all_candles = []
            for batch in range(5):
                raw = api.get_candles(ASSET, 60, 100, time.time() - batch * 100 * 60)
                if raw:
                    all_candles = [{"close": x.get("close",0), "max": x.get("max",0),
                                    "min": x.get("min",0), "open": x.get("open",0)} for x in raw] + all_candles
            candles = all_candles
        except Exception as e:
            log(f"Candle err: {e}")
            time.sleep(10)
            continue

        if not candles or len(candles) < 100:
            log(f"Few candles: {len(candles) if candles else 0}")
            time.sleep(10)
            continue

        # Get 5m candles for multi-TF
        try:
            raw5 = api.get_candles(ASSET, 300, 100, time.time())
            candles_5m = [{"close": x.get("close",0), "max": x.get("max",0),
                           "min": x.get("min",0), "open": x.get("open",0)} for x in raw5] if raw5 else None
        except:
            candles_5m = None

        # Features (vectorized)
        matrix, feat_names, valid = make_all_features(candles, candles_5m)
        if matrix is None or not valid[-1]:
            log("No features")
            time.sleep(15)
            continue

        # Use last row, forward-fill any remaining NaN
        import numpy as np
        x = matrix[-1:].copy()
        x = np.nan_to_num(x, nan=0.0)
        x_scaled = scaler.transform(x)
        prob = model.predict_proba(x_scaled)[0]
        p_up = prob[1]
        p_down = prob[0]

        # Decision: only trade with high confidence (>=0.60 = 56.5% accuracy)
        threshold = 0.60
        if p_up > threshold:
            direction = 'call'
            confidence = p_up
        elif p_down > threshold:
            direction = 'put'
            confidence = p_down
        else:
            if cycle % 5 == 0:
                log(f"Cycle {cycle}: no edge (up={p_up:.2f} down={p_down:.2f})")
            time.sleep(15)
            continue

        # Trade
        log(f"SIGNAL: {ASSET} {direction} prob={confidence:.2f} bet={int(AMOUNT)}")
        try:
            ok, tid = api.buy(int(AMOUNT), ASSET, direction, 1)
            if not ok:
                log(f"Buy failed: {tid}")
                time.sleep(10)
                continue
        except Exception as e:
            log(f"Buy err: {e}")
            time.sleep(10)
            continue

        log(f"Placed TID={tid}")
        time.sleep(68)

        try:
            result = api.check_win_v4(tid)
            win = result[0] == 'win'
        except:
            win = False

        profit = AMOUNT * 0.87 if win else -AMOUNT
        trade = {
            "time": time.strftime('%Y-%m-%d %H:%M:%S'),
            "asset": ASSET, "direction": direction,
            "amount": int(AMOUNT), "confidence": confidence,
            "profit": profit, "win": win, "payout": 87,
            "balance": bal, "model_prob": confidence,
            "features": json.dumps({"p_up": p_up, "p_down": p_down}),
        }
        db_insert(trade)

        if win:
            consecutive_losses = 0
            AMOUNT = base_amount
        else:
            consecutive_losses += 1
            AMOUNT = min(base_amount * (1.5 ** consecutive_losses), 100)
        save_state(consecutive_losses)

        total, wins, pnl = db_stats()
        wr = wins / total * 100 if total > 0 else 0
        log(f"{'WIN' if win else 'LOSS'} {direction.upper()} now={wins}/{total} {wr:.0f}% pnl={pnl:+.1f} next={int(AMOUNT)}")

        try: api._close_connect = lambda: None; api._close_connect()
        except: pass

    except Exception as e:
        log(f"ERR: {e}")
        try:
            if api: api._close_connect = lambda: None; api._close_connect()
        except: pass

    time.sleep(15)
