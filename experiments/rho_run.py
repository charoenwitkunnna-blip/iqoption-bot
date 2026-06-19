#!/usr/bin/env python3
"""
RHO BOUNCE — persistent runner.
Continually scans all paying assets and trades rho_bounce signals.
1-min expiry, 5 THB practice.
"""
import sys, os, time, json, importlib

AMOUNT = 5
STOP_LOSS = -100
BASE_DIR = "/root/iqoption-bot/experiments"
RESULTS = os.path.join(BASE_DIR, "results")
os.makedirs(RESULTS, exist_ok=True)
LOG_FILE = os.path.join(RESULTS, "rho_bounce.log")
TRADES_FILE = os.path.join(RESULTS, "rho_bounce_trades.json")

sys.path.insert(0, BASE_DIR)
from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD
from iqoptionapi.stable_api import IQ_Option

strat = importlib.import_module("new_algos.rho_bounce.strategy")

def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

def load_trades():
    if os.path.exists(TRADES_FILE):
        try:
            return json.load(open(TRADES_FILE))
        except: pass
    return []

def save_trades(trades):
    json.dump(trades, open(TRADES_FILE, "w"), indent=2)

# Main loop
trades = load_trades()
first = True

while True:
    try:
        api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
        api.connect()
        api.change_balance("PRACTICE")
        time.sleep(2)

        # Stop loss check
        total_pnl = sum(t['profit'] for t in trades)
        if total_pnl <= STOP_LOSS:
            log(f"STOP LOSS HIT: {total_pnl}")
            api._close_connect = lambda: None; api._close_connect()
            time.sleep(60)
            continue

        # Find paying assets
        all_open = api.get_all_open_time()
        open_assets = {k: v for k, v in all_open.get('turbo', {}).items() if v.get('open')}
        paying = {}
        for asset in list(open_assets.keys())[:60]:
            try:
                p = api.get_digital_payout(asset)
                if p and p >= 85: paying[asset] = p
            except: pass

        if not paying:
            if first:
                log(f"NO PAYING ASSETS — waiting")
                first = False
            api._close_connect = lambda: None; api._close_connect()
            time.sleep(30)
            continue

        first = False
        top = sorted(paying, key=paying.get, reverse=True)
        traded = False

        for asset in top:
            # Check balance
            try:
                balance = api.get_balance()
            except:
                balance = 0
            if balance < AMOUNT:
                log(f"BALANCE TOO LOW: {balance:.1f}")
                break

            # Get candles & analyze
            try:
                candles = api.get_candles(asset, 60, 50, time.time())
                if not candles or len(candles) < 30: continue
            except: continue

            try:
                direction, confidence = strat.analyze(api, asset, candles)
            except: continue
            if direction is None: continue

            # TRADE
            try:
                ok, tid = api.buy(AMOUNT, asset, direction, 1)
                if not ok:
                    log(f"  {asset} {direction} FAIL: {tid}")
                    continue
            except:
                log(f"  {asset} {direction} BUY EXCEPTION")
                continue

            # Wait for expiry
            time.sleep(68)

            # Check result
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
            num = len(trades)
            wr = w / num * 100 if num > 0 else 0
            log(f"  {asset} {direction.upper()} {'WIN' if win else 'LOSS'} now={w}/{num} {wr:.0f}% pnl={sum(t['profit'] for t in trades):+.1f}")
            traded = True
            break  # One trade per cycle

        if not traded:
            log("NO SIGNAL")

        api._close_connect = lambda: None; api._close_connect()

    except Exception as e:
        log(f"ERROR: {e}")
        try:
            api._close_connect = lambda: None; api._close_connect()
        except: pass

    time.sleep(15)
