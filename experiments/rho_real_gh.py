#!/usr/bin/env python3
"""GitHub Actions version."""
import sys, os, time, json, importlib, logging
logging.disable(logging.ERROR)

AMOUNT = 5
EXPIRY = 1
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(BASE_DIR, "results")
os.makedirs(RESULTS, exist_ok=True)
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, '..'))

IQ_OPTION_EMAIL = os.environ["IQ_EMAIL"]
IQ_OPTION_PASSWORD = os.environ.get("IQ_PASSWORD", "")

from iqoptionapi.stable_api import IQ_Option
strat = importlib.import_module("new_algos.rho_bounce.strategy")
log_file = os.path.join(RESULTS, "rho_practice.log")
trades_file = os.path.join(RESULTS, "rho_practice_trades.json")

PAYING = {
    "EURUSD-OTC":86,"GBPUSD-OTC":85,"USDCHF-OTC":85,
    "EURJPY-OTC":87,"BTCUSD-OTC-op":87,
}

def log(msg):
    with open(log_file, "a") as f:
        f.write(f"{time.strftime(chr(37)+chr(37)+chr(37))} {msg}\n")
    print(msg, flush=True)

def load_trades():
    if os.path.exists(trades_file):
        try: return json.load(open(trades_file))
        except: pass
    return []

def save_trades(trades):
    json.dump(trades, open(trades_file, "w"), indent=2)

trades = load_trades()
log("Starting...")
api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
ok, r = api.connect()
log(f"Connect: {ok}")
if not ok:
    log(f"FAILED: {r}")
    sys.exit(1)
api.change_balance("PRACTICE")
time.sleep(2)
bal = api.get_balance()
log(f"Balance: {bal}")

def get_candles_timeout(asset, period=60, count=50, timeout=8):
    """get_candles via subprocess — kills on hang."""
    import subprocess, json as _json
    code = f"""
import sys, time, json, os; sys.path.insert(0,'.'); sys.path.insert(0,'..')
from iqoptionapi.stable_api import IQ_Option
api = IQ_Option(os.environ.get('IQ_EMAIL',''), os.envi...D',''))
ok, r = api.connect()
if ok:
    api.change_balance('PRACTICE')
    time.sleep(2)
    c = api.get_candles('{asset}', {period}, {count}, time.time())
    if c: print(json.dumps([[x.get('close',0),x.get('max',0),x.get('min',0),x.get('open',0)] for x in c]))
"""
    try:
        r = subprocess.run(['python3', '-c', code], capture_output=True, text=True, timeout=timeout, cwd='.')
        if r.stderr: log(f"  SUBPROCESS STDERR: {r.stderr[:200]}")
        if r.returncode == 0 and r.stdout.strip():
            data = _json.loads(r.stdout.strip())
            return [{'close': d[0], 'max': d[1], 'min': d[2], 'open': d[3]} for d in data]
    except:
        pass
    return None

top = sorted(PAYING.keys(), key=PAYING.get, reverse=True)
for asset in top:
    candles = get_candles_timeout(asset, timeout=25)
    log(f"  {asset}: {len(candles) if candles else 0} candles")
    if not candles or len(candles) < 30:
        continue
    try:
        direction, confidence = strat.analyze(api, asset, candles)
    except: continue
    if direction is None: continue
    log(f"SIGNAL: {asset} {direction} conf={confidence}")
    try:
        ok, tid = api.buy(AMOUNT, asset, direction, EXPIRY)
        if not ok:
            log(f"Buy failed: {tid}")
            continue
    except Exception as e:
        log(f"Buy error: {e}")
        continue
    log(f"Placed: {asset} {direction} TID={tid}")
    time.sleep(68)
    try:
        result = api.check_win_v4(tid)
        win = result[0] == "win"
    except:
        win = False
    payout = PAYING.get(asset, 87)
    profit = AMOUNT * (payout / 100) if win else -AMOUNT
    trade = {"time": time.strftime("%Y-%m-%d %H:%M:%S"),
             "asset": asset, "direction": direction,
             "amount": AMOUNT, "confidence": confidence,
             "profit": profit, "win": win, "payout": payout, "balance": bal}
    trades.append(trade)
    save_trades(trades)
    w = sum(1 for t in trades if t["win"])
    result_str = "WIN" if win else "LOSS"
    pnl = sum(t["profit"] for t in trades)
    log(f"{result_str} {asset} now={w}/{len(trades)} pnl={pnl:+.1f}")
    break
log("Done")
