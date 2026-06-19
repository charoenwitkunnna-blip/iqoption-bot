#!/usr/bin/env python3
"""GitHub Actions — persistent connection, no subprocess per candle."""
import sys, os, time, json, logging
logging.disable(logging.CRITICAL)

AMOUNT = 5
EXPIRY = 1
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(BASE_DIR, "results")
os.makedirs(RESULTS, exist_ok=True)
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, ".."))

from new_algos.rho_bounce.strategy import analyze
from iqoptionapi.stable_api import IQ_Option

ASSETS = [
    'EURUSD-OTC','GBPUSD-OTC','USDCHF-OTC','USDJPY-OTC','AUDUSD-OTC',
    'USDCAD-OTC','NZDUSD-OTC','EURGBP-OTC','EURJPY-OTC','GBPJPY-OTC',
    'EURCHF-OTC','AUDJPY-OTC','CADJPY-OTC','CHFJPY-OTC','NZDJPY-OTC',
    'XAUUSD-OTC','GER30-OTC','UK100-OTC','NOKJPY-OTC','ETHUSD-OTC','XRPUSD-OTC',
    'EURUSD','GBPUSD','USDCHF','USDJPY','AUDUSD','USDCAD','NZDUSD','EURGBP',
    'ETHUSD','XRPUSD','XAUUSD','GER30','UK100',
]

log_file = os.path.join(RESULTS, "rho_practice.log")
trades_file = os.path.join(RESULTS, "rho_practice_trades.json")

def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"{ts} {msg}"
    with open(log_file, "a") as f:
        f.write(line + "\n")
    print(line, flush=True)

def load_trades():
    if os.path.exists(trades_file):
        try: return json.load(open(trades_file))
        except: pass
    return []

def save_trades(trades):
    json.dump(trades, open(trades_file, "w"), indent=2)

# Connect once
email = os.environ.get("IQ_EMAIL", "")
pwd = os.environ.get("IQ_PASSWORD", "")
api = IQ_Option(email, pwd)
ok, r = api.connect()
if not ok:
    log(f"CONNECT FAILED: {r}")
    sys.exit(1)

api.change_balance("PRACTICE")
time.sleep(2)
log(f"Connected, starting bot")

trades = load_trades()
start_time = time.time()
MAX_RUNTIME = 4.5 * 3600
cycle = 0

while time.time() - start_time < MAX_RUNTIME:
    cycle += 1
    log(f"Cycle {cycle}")

    found_signal = False
    for asset in ASSETS:
        if time.time() - start_time > MAX_RUNTIME:
            break

        try:
            candles = api.get_candles(asset, 60, 50, time.time())
        except Exception as e:
            continue

        if not candles or len(candles) < 30:
            continue

        candle_list = [{"close": x.get("close",0), "max": x.get("max",0), "min": x.get("min",0), "open": x.get("open",0)} for x in candles]

        try:
            direction, confidence = analyze(None, asset, candle_list)
        except:
            continue
        if direction is None:
            continue

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

        profit = AMOUNT * 0.87 if win else -AMOUNT
        trade = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "asset": asset, "direction": direction,
            "amount": AMOUNT, "confidence": confidence,
            "profit": profit, "win": win, "payout": 87,
        }
        trades.append(trade)
        save_trades(trades)

        w = sum(1 for t in trades if t["win"])
        result_str = "WIN" if win else "LOSS"
        pnl = sum(t["profit"] for t in trades)
        log(f"{result_str} {asset} now={w}/{len(trades)} pnl={pnl:+.1f}")
        found_signal = True
        break

    if not found_signal:
        log("No signals found")

    time.sleep(30)

log(f"Done after {cycle} cycles, {len(trades)} total trades")
