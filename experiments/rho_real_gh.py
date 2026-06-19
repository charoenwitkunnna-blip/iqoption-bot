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
    "EURUSD-OTC":86,"GBPUSD-OTC":85,"USDCHF-OTC":85,"USDJPY-OTC":85,
    "AUDUSD-OTC":85,"USDCAD-OTC":85,"NZDUSD-OTC":85,"EURGBP-OTC":85,
    "EURJPY-OTC":87,"GBPJPY-OTC":85,"EURCHF-OTC":85,"AUDJPY-OTC":85,
    "CADJPY-OTC":85,"CHFJPY-OTC":85,"NZDJPY-OTC":85,"EURAUD-OTC":85,
    "EURCAD-OTC":85,"EURNZD-OTC":85,"GBPNZD-OTC":85,"AUDCHF-OTC":85,
    "AUDCAD-OTC":85,"AUDNZD-OTC":85,"CADCHF-OTC":85,"NZDCHF-OTC":85,
    "NZDCAD-OTC":85,"BTCUSD-OTC-op":87,"ETHUSD-OTC":86,"XRPUSD-OTC":86,
    "SOLUSD-OTC":86,"XAUUSD-OTC":85,"GER30-OTC":85,"UK100-OTC":85,"NOKJPY-OTC":85,
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

def get_candles_timeout(api, asset, period, count, timeout=5):
    """get_candles with timeout."""
    import threading
    result = [None]
    def worker():
        try:
            result[0] = api.get_candles(asset, period, count, time.time())
        except:
            pass
    t = threading.Thread(target=worker)
    t.daemon = True
    t.start()
    t.join(timeout)
    return result[0]

top = sorted(PAYING.keys(), key=PAYING.get, reverse=True)
for asset in top:
    candles = get_candles_timeout(api, asset, 60, 50, timeout=8)
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
