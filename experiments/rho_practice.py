#!/usr/bin/env python3
"""RHO BOUNCE — Optimized for low API calls. Caches everything."""
import sys, os, time, json, importlib

AMOUNT = 5
STOP_LOSS = -90
BASE_DIR = "/root/iqoption-bot/experiments"
RESULTS = os.path.join(BASE_DIR, "results")
os.makedirs(RESULTS, exist_ok=True)

sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, '..'))
from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD
from iqoptionapi.stable_api import IQ_Option

strat = importlib.import_module("new_algos.rho_bounce.strategy")

log_file = os.path.join(RESULTS, "rho_practice.log")
trades_file = os.path.join(RESULTS, "rho_practice_trades.json")

def log(msg):
    with open(log_file, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

def load_trades():
    if os.path.exists(trades_file):
        try: return json.load(open(trades_file))
        except: pass
    return []

def save_trades(trades):
    json.dump(trades, open(trades_file, "w"), indent=2)

trades = load_trades()

# Cache system — reduces API calls dramatically
cache = {
    'open_assets': None,      # refreshed every 30 min
    'open_assets_time': 0,
    'paying': None,            # refreshed every 10 min
    'paying_time': 0,
}

OPEN_TTL = 30 * 60   # 30 min
PAYING_TTL = 10 * 60  # 10 min

def refresh_open_assets(api):
    """Cache open assets — 1 API call every 30 min."""
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
    """Cache paying assets — 1 API call per asset every 10 min."""
    now = time.time()
    if cache['paying'] and (now - cache['paying_time']) < PAYING_TTL:
        return cache['paying']
    paying = {}
    # Only check top 30 by alphabetical (reduce calls)
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

while True:
    api = None
    try:
        api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
        api.connect()
        api.change_balance("PRACTICE")
        time.sleep(2)

        bal = api.get_balance()
        if bal < AMOUNT:
            log(f"BALANCE LOW: {bal}")
            try: api._close_connect = lambda: None; api._close_connect()
            except: pass
            time.sleep(60)
            continue

        total_pnl = sum(t['profit'] for t in trades)
        if total_pnl <= STOP_LOSS:
            log(f"STOP LOSS: {total_pnl}")
            break

        # Get cached data — most cycles make 0 API calls for these
        open_assets = refresh_open_assets(api)
        paying = refresh_paying(api, open_assets)

        if not paying:
            log("NO ASSETS")
            try: api._close_connect = lambda: None; api._close_connect()
            except: pass
            time.sleep(30)
            continue

        top = sorted(paying, key=paying.get, reverse=True)

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
                ok, tid = api.buy(AMOUNT, asset, direction, 1)
                if not ok: continue
            except: continue

            log(f"  {asset} {direction} conf={confidence} TID={tid}")
            time.sleep(68)

            try:
                result = api.check_win_v4(tid)
                win = result[0] == 'win'
            except:
                win = False

            profit = AMOUNT * (paying.get(asset, 87) / 100) if win else -AMOUNT
            trade = {"time": time.strftime('%Y-%m-%d %H:%M:%S'),
                     "asset": asset, "direction": direction,
                     "amount": AMOUNT, "confidence": confidence,
                     "profit": profit, "win": win,
                     "payout": paying.get(asset, 87),
                     "balance": bal,
                     "utc_hour": int(time.strftime('%H', time.gmtime()))}
            trades.append(trade)
            save_trades(trades)

            w = sum(1 for t in trades if t['win'])
            num = len(trades)
            wr = w / num * 100 if num > 0 else 0
            log(f"  {asset} {direction.upper()} {'WIN' if win else 'LOSS'} now={w}/{num} {wr:.0f}% pnl={sum(t['profit'] for t in trades):+.1f}")
            break

        try: api._close_connect = lambda: None; api._close_connect()
        except: pass

    except Exception as e:
        log(f"ERR: {e}")
        try:
            if api: api._close_connect = lambda: None; api._close_connect()
        except: pass

    # 20 seconds between cycles = ~100 calls/min
    time.sleep(20)
