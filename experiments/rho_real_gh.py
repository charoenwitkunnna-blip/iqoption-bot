#!/usr/bin/env python3
import sys, os, time, json, importlib, logging, subprocess
logging.disable(logging.CRITICAL)
AMOUNT = 5
EXPIRY = 1
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(BASE_DIR, "results")
os.makedirs(RESULTS, exist_ok=True)
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, ".."))
IQ_OPTION_EMAIL = os.environ.get("IQ_EMAIL", "")
IQ_OPTION_PASSWORD = os.environ.get("IQ_PASSWORD", "")
from iqoptionapi.stable_api import IQ_Option
strat = importlib.import_module("new_algos.rho_bounce.strategy")
log_file = os.path.join(RESULTS, "rho_practice.log")
trades_file = os.path.join(RESULTS, "rho_practice_trades.json")
PAYING = {"EURUSD-OTC":86,"GBPUSD-OTC":85,"USDCHF-OTC":85,"USDJPY-OTC":85,"AUDUSD-OTC":85,"USDCAD-OTC":85,"NZDUSD-OTC":85,"EURGBP-OTC":85,"EURJPY-OTC":87,"GBPJPY-OTC":85,"EURCHF-OTC":85,"AUDJPY-OTC":85,"CADJPY-OTC":85,"CHFJPY-OTC":85,"NZDJPY-OTC":85,"XAUUSD-OTC":85,"GER30-OTC":85,"UK100-OTC":85,"NOKJPY-OTC":85,"ETHUSD-OTC":86,"XRPUSD-OTC":86}

def log(msg):
    ts = time.strftime("%H:%M:%S")
    with open(log_file, "a") as f:
        f.write(f"{ts} {msg}")
    print(msg, flush=True)

def load_trades():
    if os.path.exists(trades_file):
        try: return json.load(open(trades_file))
        except: pass
    return []

def save_trades(trades):
    json.dump(trades, open(trades_file, "w"), indent=2)

def get_candles_timeout(asset, period=60, count=50, timeout=25):
    worker = os.path.join(BASE_DIR, "_candle_worker.py")
    env = {**os.environ, "PYTHONPATH": BASE_DIR + ":" + os.path.join(BASE_DIR, "..")}
    try:
        r = subprocess.run(["python3", worker, asset, str(period), str(count)], capture_output=True, text=True, timeout=timeout, env=env)
        if r.returncode == 0 and r.stdout.strip():
            data = json.loads(r.stdout.strip())
            return [{"close": d[0], "max": d[1], "min": d[2], "open": d[3]} for d in data]
    except: pass
    return None

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

top = sorted(PAYING.keys(), key=PAYING.get, reverse=True)
for asset in top:
    candles = get_candles_timeout(asset)
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
    except: win = False
    payout = PAYING.get(asset, 87)
    profit = AMOUNT * (payout / 100) if win else -AMOUNT
    trade = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "asset": asset, "direction": direction, "amount": AMOUNT, "confidence": confidence, "profit": profit, "win": win, "payout": payout, "balance": bal}
    trades.append(trade)
    save_trades(trades)
    w = sum(1 for t in trades if t["win"])
    rs = "WIN" if win else "LOSS"
    pnl = sum(t["profit"] for t in trades)
    log(f"{rs} {asset} now={w}/{len(trades)} pnl={pnl:+.1f}")
    break
log("Done")
