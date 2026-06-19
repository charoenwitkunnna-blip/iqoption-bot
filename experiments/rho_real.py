#!/usr/bin/env python3
"""RHO BOUNCE — Optimized for low API calls. SQLite trade storage."""
import sys, os, time, json, importlib, sqlite3, random

AMOUNT = 30
base_amount = 30
consecutive_losses = 0
STOP_LOSS = -90
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(BASE_DIR, "results")
os.makedirs(RESULTS, exist_ok=True)

sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, '..'))
# Load .env if present
_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
if os.path.exists(_env):
    for _line in open(_env):
        _line = _line.strip()
        if _line and not _line.startswith('#') and '=' in _line:
            _k, _v = _line.split('=', 1)
            os.environ.setdefault(_k.strip(), _v.strip())

IQ_OPTION_EMAIL = os.environ.get("IQ_EMAIL", "") or os.environ.get("IQ_OPTION_EMAIL", "")

from iqoptionapi.stable_api import IQ_Option

strat = importlib.import_module("new_algos.rho_bounce.strategy")

# --- Debug log ---
log_file = os.path.join(RESULTS, "rho_real.log")
def log(msg):
    with open(log_file, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

# --- SQLite DB ---
db_path = os.path.join(RESULTS, "trades.db")
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
            utc_hour INTEGER
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS idx_time ON trades(time)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_asset ON trades(asset)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_win ON trades(win)")
    db.commit()
    db.close()

def db_insert_trade(t):
    db = get_db()
    db.execute(
        "INSERT INTO trades (time, asset, direction, amount, confidence, profit, win, payout, balance, utc_hour) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (t["time"], t["asset"], t["direction"], t["amount"], t.get("confidence"),
         t["profit"], int(t["win"]), t.get("payout"), t.get("balance"), t.get("utc_hour"))
    )
    db.commit()
    db.close()

def db_get_stats():
    db = get_db()
    row = db.execute("SELECT COUNT(*), SUM(CASE WHEN win=1 THEN 1 ELSE 0 END), SUM(profit) FROM trades").fetchone()
    db.close()
    total, wins, pnl = row
    wins = wins or 0
    pnl = pnl or 0
    return int(total), int(wins), pnl

def db_get_win_counts():
    db = get_db()
    rows = db.execute("SELECT asset, SUM(CASE WHEN win=1 THEN 1 ELSE 0 END) as wins FROM trades GROUP BY asset").fetchall()
    db.close()
    return {r[0]: r[1] for r in rows}

init_db()

# --- Martingale state ---
state_file = os.path.join(RESULTS, "rho_state.json")
def load_state():
    if os.path.exists(state_file):
        try:
            s = json.load(open(state_file))
            return s.get("consecutive_losses", 0)
        except: pass
    return 0

def save_state(cl):
    json.dump({"consecutive_losses": cl}, open(state_file, "w"))

consecutive_losses = load_state()
AMOUNT = min(base_amount * (1.5 ** consecutive_losses), 200)

# --- Cache ---
cache = {
    'open_assets': None,
    'open_assets_time': 0,
    'paying': None,
    'paying_time': 0,
}
OPEN_TTL = 30 * 60
PAYING_TTL = 10 * 60

def refresh_open_assets(api):
    now = time.time()
    if cache['open_assets'] and (now - cache['open_assets_time']) < OPEN_TTL:
        return cache['open_assets']
    try:
        all_open = api.get_all_open_time()
        cache['open_assets'] = {k: v for k, v in all_open.get('turbo', {}).items() if v.get('open')}
        cache['open_assets_time'] = now
        log(f"Cache: {len(cache['open_assets'])} open assets")
    except:
        pass
    return cache['open_assets'] or {}

def refresh_paying(api, open_assets):
    now = time.time()
    if cache['paying'] and (now - cache['paying_time']) < PAYING_TTL:
        return cache['paying']
    paying = {}
    assets = sorted(open_assets.keys())[:30]
    for asset in assets:
        try:
            p = api.get_digital_payout(asset)
            if p and p >= 85:
                paying[asset] = p
        except: pass
    cache['paying'] = paying
    cache['paying_time'] = now
    log(f"Cache: {len(paying)} paying assets")
    return paying

# --- Main loop ---
MAX_CYCLES = int(os.environ.get("MAX_CYCLES", "0"))
cycle_count = 0
while True:
    cycle_count += 1
    if MAX_CYCLES > 0 and cycle_count > MAX_CYCLES:
        log(f"MAX_CYCLES reached ({MAX_CYCLES})")
        break
    api = None
    try:
        api = IQ_Option(IQ_OPTION_EMAIL, os.environ.get("IQ_OPTION_PASSWORD", ""))
        ok, msg = api.connect()
        if not ok:
            log(f"CONNECT FAIL: {msg}")
            time.sleep(60)
            continue
        api.change_balance("REAL")
        time.sleep(2)

        bal = api.get_balance()
        if bal < AMOUNT:
            log(f"BALANCE LOW: {bal}")
            try: api._close_connect = lambda: None; api._close_connect()
            except: pass
            time.sleep(60)
            continue

        total, wins, pnl = db_get_stats()
        if pnl <= STOP_LOSS:
            log(f"STOP LOSS: {pnl}")
            break

        open_assets = refresh_open_assets(api)
        paying = refresh_paying(api, open_assets)

        if not paying:
            log("NO ASSETS")
            try: api._close_connect = lambda: None; api._close_connect()
            except: pass
            time.sleep(30)
            continue

        # 3 top by wins, 3 top by payout, 3 random = 9 total
        win_counts = db_get_win_counts()
        by_wins = sorted(paying.keys(), key=lambda a: win_counts.get(a, 0), reverse=True)[:3]
        by_payout = sorted(paying.keys(), key=paying.get, reverse=True)[:3]
        pool = [a for a in paying.keys() if a not in by_wins and a not in by_payout]
        rand = random.sample(pool, min(3, len(pool)))
        top = list(dict.fromkeys(by_wins + by_payout + rand))
        random.shuffle(top)

        for asset in top:
            try:
                candles = api.get_candles(asset, 60, 50, time.time())
                if not candles or len(candles) < 30: continue
            except: continue

            try:
                direction, confidence = strat.analyze(api, asset, candles)
            except: continue
            if direction is None: continue

            try:
                ok, tid = api.buy(int(AMOUNT), asset, direction, 1)
                if not ok: continue
            except: continue

            log(f"  {asset} {direction} conf={confidence} TID={tid} bet={int(AMOUNT)}")
            time.sleep(68)

            try:
                result = api.check_win_v4(tid)
                win = result[0] == 'win'
            except:
                win = False

            profit = AMOUNT * (paying.get(asset, 87) / 100) if win else -AMOUNT
            trade = {"time": time.strftime('%Y-%m-%d %H:%M:%S'),
                     "asset": asset, "direction": direction,
                     "amount": int(AMOUNT), "confidence": confidence,
                     "profit": profit, "win": win,
                     "payout": paying.get(asset, 87),
                     "balance": bal,
                     "utc_hour": int(time.strftime('%H', time.gmtime()))}
            db_insert_trade(trade)

            # Martingale
            if win:
                consecutive_losses = 0
                AMOUNT = base_amount
            else:
                consecutive_losses += 1
                AMOUNT = min(base_amount * (1.5 ** consecutive_losses), 200)
            save_state(consecutive_losses)

            total, wins, pnl = db_get_stats()
            wr = wins / total * 100 if total > 0 else 0
            log(f"  {asset} {direction.upper()} {'WIN' if win else 'LOSS'} now={wins}/{total} {wr:.0f}% pnl={pnl:+.1f} next_bet={int(AMOUNT)}")
            break

        try: api._close_connect = lambda: None; api._close_connect()
        except: pass

    except Exception as e:
        log(f"ERR: {e}")
        try:
            if api: api._close_connect = lambda: None; api._close_connect()
        except: pass

    time.sleep(20)
