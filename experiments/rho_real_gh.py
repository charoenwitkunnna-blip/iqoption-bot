#!/usr/bin/env python3
"""GitHub Actions version — single run, no infinite loops."""
import sys, os, time, json, importlib, signal

AMOUNT = 5  # practice
EXPIRY = 1
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(BASE_DIR, "results")
os.makedirs(RESULTS, exist_ok=True)

sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, '..'))

IQ_OPTION_EMAIL = os.environ.get("IQ_EMAIL", "agolfhitler3000@gmail.com")
IQ_OPTION_PASSWORD = os.environ.get("IQ_PASSWORD", "")

from iqoptionapi.stable_api import IQ_Option
strat = importlib.import_module("new_algos.rho_bounce.strategy")

log_file = os.path.join(RESULTS, "rho_practice.log")
trades_file = os.path.join(RESULTS, "rho_practice_trades.json")

def log(msg):
    with open(log_file, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    print(msg, flush=True)

def load_trades():
    if os.path.exists(trades_file):
        # Skip get_all_open_time - use hardcoded list
    open_assets = {}
    ASSETS = ["EURUSD-OTC","GBPUSD-OTC","USDCHF-OTC","USDJPY-OTC","AUDUSD-OTC","USDCAD-OTC","NZDUSD-OTC","EURGBP-OTC","EURJPY-OTC","GBPJPY-OTC","EURCHF-OTC","AUDJPY-OTC","CADJPY-OTC","CHFJPY-OTC","NZDJPY-OTC","EURAUD-OTC","EURCAD-OTC","EURNZD-OTC","GBPAUD-OTC","GBPCAD-OTC","GBPNZD-OTC","AUDCHF-OTC","AUDCAD-OTC","AUDNZD-OTC","CADCHF-OTC","NZDCHF-OTC","NZDCAD-OTC","BTCUSD-OTC-op","ETHUSD-OTC","XRPUSD-OTC","SOLUSD-OTC","XAUUSD-OTC","GER30-OTC","UK100-OTC","NOKJPY-OTC"]
    open_assets = {a: True for a in ASSETS}
    try: return json.load(open(trades_file))
        except: pass
    return []

def save_trades(trades):
    json.dump(trades, open(trades_file, "w"), indent=2)

trades = load_trades()

# Single run — connect, scan, trade, exit
log("Starting...")
api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
ok, r = api.connect()
log(f"Connect: {ok} {r}")

if not ok:
    log("FAILED to connect")
    sys.exit(1)

api.change_balance("PRACTICE")
time.sleep(2)
bal = api.get_balance()
log(f"Balance: {bal}")

# Get open assets
# Skip get_all_open_time - use hardcoded list
    open_assets = {}
    ASSETS = ["EURUSD-OTC","GBPUSD-OTC","USDCHF-OTC","USDJPY-OTC","AUDUSD-OTC","USDCAD-OTC","NZDUSD-OTC","EURGBP-OTC","EURJPY-OTC","GBPJPY-OTC","EURCHF-OTC","AUDJPY-OTC","CADJPY-OTC","CHFJPY-OTC","NZDJPY-OTC","EURAUD-OTC","EURCAD-OTC","EURNZD-OTC","GBPAUD-OTC","GBPCAD-OTC","GBPNZD-OTC","AUDCHF-OTC","AUDCAD-OTC","AUDNZD-OTC","CADCHF-OTC","NZDCHF-OTC","NZDCAD-OTC","BTCUSD-OTC-op","ETHUSD-OTC","XRPUSD-OTC","SOLUSD-OTC","XAUUSD-OTC","GER30-OTC","UK100-OTC","NOKJPY-OTC"]
    open_assets = {a: True for a in ASSETS}
    try:
    all_open = api.get_all_open_time()
    open_assets = {k: v for k, v in all_open.get('turbo', {}).items() if v.get('open')}
    log(f"Open assets: {len(open_assets)}")
except Exception as e:
    log(f"get_all_open_time failed: {e}")
    open_assets = {}

# Get paying assets
paying = {}
for asset in list(open_assets.keys())[:18]:
    # Skip get_all_open_time - use hardcoded list
    open_assets = {}
    ASSETS = ["EURUSD-OTC","GBPUSD-OTC","USDCHF-OTC","USDJPY-OTC","AUDUSD-OTC","USDCAD-OTC","NZDUSD-OTC","EURGBP-OTC","EURJPY-OTC","GBPJPY-OTC","EURCHF-OTC","AUDJPY-OTC","CADJPY-OTC","CHFJPY-OTC","NZDJPY-OTC","EURAUD-OTC","EURCAD-OTC","EURNZD-OTC","GBPAUD-OTC","GBPCAD-OTC","GBPNZD-OTC","AUDCHF-OTC","AUDCAD-OTC","AUDNZD-OTC","CADCHF-OTC","NZDCHF-OTC","NZDCAD-OTC","BTCUSD-OTC-op","ETHUSD-OTC","XRPUSD-OTC","SOLUSD-OTC","XAUUSD-OTC","GER30-OTC","UK100-OTC","NOKJPY-OTC"]
    open_assets = {a: True for a in ASSETS}
    try:
        p = api.get_digital_payout(asset)
        if p and p >= 85: paying[asset] = p
    except: pass
log(f"Paying: {len(paying)}")

# Scan for signals
top = sorted(paying, key=paying.get, reverse=True)
for asset in top:
    # Skip get_all_open_time - use hardcoded list
    open_assets = {}
    ASSETS = ["EURUSD-OTC","GBPUSD-OTC","USDCHF-OTC","USDJPY-OTC","AUDUSD-OTC","USDCAD-OTC","NZDUSD-OTC","EURGBP-OTC","EURJPY-OTC","GBPJPY-OTC","EURCHF-OTC","AUDJPY-OTC","CADJPY-OTC","CHFJPY-OTC","NZDJPY-OTC","EURAUD-OTC","EURCAD-OTC","EURNZD-OTC","GBPAUD-OTC","GBPCAD-OTC","GBPNZD-OTC","AUDCHF-OTC","AUDCAD-OTC","AUDNZD-OTC","CADCHF-OTC","NZDCHF-OTC","NZDCAD-OTC","BTCUSD-OTC-op","ETHUSD-OTC","XRPUSD-OTC","SOLUSD-OTC","XAUUSD-OTC","GER30-OTC","UK100-OTC","NOKJPY-OTC"]
    open_assets = {a: True for a in ASSETS}
    try:
        candles = api.get_candles(asset, 60, 50, time.time())
        if not candles or len(candles) < 30: continue
    except: continue

    # Skip get_all_open_time - use hardcoded list
    open_assets = {}
    ASSETS = ["EURUSD-OTC","GBPUSD-OTC","USDCHF-OTC","USDJPY-OTC","AUDUSD-OTC","USDCAD-OTC","NZDUSD-OTC","EURGBP-OTC","EURJPY-OTC","GBPJPY-OTC","EURCHF-OTC","AUDJPY-OTC","CADJPY-OTC","CHFJPY-OTC","NZDJPY-OTC","EURAUD-OTC","EURCAD-OTC","EURNZD-OTC","GBPAUD-OTC","GBPCAD-OTC","GBPNZD-OTC","AUDCHF-OTC","AUDCAD-OTC","AUDNZD-OTC","CADCHF-OTC","NZDCHF-OTC","NZDCAD-OTC","BTCUSD-OTC-op","ETHUSD-OTC","XRPUSD-OTC","SOLUSD-OTC","XAUUSD-OTC","GER30-OTC","UK100-OTC","NOKJPY-OTC"]
    open_assets = {a: True for a in ASSETS}
    try:
        direction, confidence = strat.analyze(api, asset, candles)
    except: continue
    if direction is None: continue

    log(f"SIGNAL: {asset} {direction} conf={confidence}")

    # Place trade
    # Skip get_all_open_time - use hardcoded list
    open_assets = {}
    ASSETS = ["EURUSD-OTC","GBPUSD-OTC","USDCHF-OTC","USDJPY-OTC","AUDUSD-OTC","USDCAD-OTC","NZDUSD-OTC","EURGBP-OTC","EURJPY-OTC","GBPJPY-OTC","EURCHF-OTC","AUDJPY-OTC","CADJPY-OTC","CHFJPY-OTC","NZDJPY-OTC","EURAUD-OTC","EURCAD-OTC","EURNZD-OTC","GBPAUD-OTC","GBPCAD-OTC","GBPNZD-OTC","AUDCHF-OTC","AUDCAD-OTC","AUDNZD-OTC","CADCHF-OTC","NZDCHF-OTC","NZDCAD-OTC","BTCUSD-OTC-op","ETHUSD-OTC","XRPUSD-OTC","SOLUSD-OTC","XAUUSD-OTC","GER30-OTC","UK100-OTC","NOKJPY-OTC"]
    open_assets = {a: True for a in ASSETS}
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

    # Skip get_all_open_time - use hardcoded list
    open_assets = {}
    ASSETS = ["EURUSD-OTC","GBPUSD-OTC","USDCHF-OTC","USDJPY-OTC","AUDUSD-OTC","USDCAD-OTC","NZDUSD-OTC","EURGBP-OTC","EURJPY-OTC","GBPJPY-OTC","EURCHF-OTC","AUDJPY-OTC","CADJPY-OTC","CHFJPY-OTC","NZDJPY-OTC","EURAUD-OTC","EURCAD-OTC","EURNZD-OTC","GBPAUD-OTC","GBPCAD-OTC","GBPNZD-OTC","AUDCHF-OTC","AUDCAD-OTC","AUDNZD-OTC","CADCHF-OTC","NZDCHF-OTC","NZDCAD-OTC","BTCUSD-OTC-op","ETHUSD-OTC","XRPUSD-OTC","SOLUSD-OTC","XAUUSD-OTC","GER30-OTC","UK100-OTC","NOKJPY-OTC"]
    open_assets = {a: True for a in ASSETS}
    try:
        result = api.check_win_v4(tid)
        win = result[0] == 'win'
    except:
        win = False

    profit = AMOUNT * (paying.get(asset, 87) / 100) if win else -AMOUNT
    trade = {"time": time.strftime('%Y-%m-%d %H:%M:%S'),
             "asset": asset, "direction": direction,
             "amount": AMOUNT, "confidence": confidence,
             "profit": profit, "win": win}
    trades.append(trade)
    save_trades(trades)

    w = sum(1 for t in trades if t['win'])
    log(f"{'WIN' if win else 'LOSS'} {asset} now={w}/{len(trades)} pnl={sum(t['profit'] for t in trades):+.1f}")
    break

log("Done")
