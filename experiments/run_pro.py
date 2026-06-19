#!/usr/bin/env python3
"""
RELIABLE RUNNER - Auto-restarts on crash. 
Runs the winning replica_exact strategy.
"""
import sys, os, time, json, importlib

STRAT_NAME = "replica_exact"
AMOUNT = 8
BASE_DIR = "/root/iqoption-bot/experiments"
RESULTS_FILE = f"{BASE_DIR}/results/{STRAT_NAME}_trades.json"

def run():
    LOG_FILE = f"{BASE_DIR}/results/{STRAT_NAME}_pro.log"
    
    def log(msg):
        with open(LOG_FILE, "a") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

    log(f"=== {STRAT_NAME} PRO RUNNER ===")

    sys.path.insert(0, BASE_DIR)
    from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD, BALANCE_TYPE
    from iqoptionapi.stable_api import IQ_Option

    api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
    check, reason = api.connect()
    log(f"Connect: {check}")
    if not check:
        time.sleep(30)
        return False
    api.change_balance(BALANCE_TYPE)
    time.sleep(1)
    log(f"Balance: {api.get_balance()}")

    # Register all assets
    data = api.get_all_init_v2()
    import iqoptionapi.constants as OP_code
    for opt in ["binary", "blitz"]:
        for aid, act in data.get(opt, {}).get("actives", {}).items():
            name = str(act.get("name", "")).split(".")[-1]
            if name not in OP_code.ACTIVES and act.get("enabled") and not act.get("is_suspended"):
                OP_code.ACTIVES[name] = int(aid)

    # Get top assets
    payouts = api.get_all_profit()
    all_assets = {}
    for opt in ["binary", "blitz"]:
        for aid, act in data.get(opt, {}).get("actives", {}).items():
            name = str(act.get("name", "")).split(".")[-1]
            if act.get("enabled") and not act.get("is_suspended"):
                all_assets[name] = int(aid)

    top_assets = sorted(
        [(n, payouts.get(n, {}).get("turbo", payouts.get(n, {}).get("binary", 0)))
         for n in all_assets],
        key=lambda x: x[1], reverse=True
    )[:10]
    top_assets = [a for a, p in top_assets]

    # Load strategy
    spec = importlib.util.spec_from_file_location(STRAT_NAME, f"{BASE_DIR}/{STRAT_NAME}/strategy.py")
    strat = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(strat)
    log(f"Strategy: {strat.NAME} [{','.join(top_assets[:3])}...]")

    # Load history
    trades = []
    if os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE) as f:
                trades = json.load(f)
        except:
            trades = []

    stats = {"total": 0, "wins": 0, "losses": 0, "pnl": 0.0}
    for t in trades:
        stats["total"] += 1
        stats["pnl"] += t.get("profit", 0)
        if t.get("profit", 0) > 0:
            stats["wins"] += 1
        else:
            stats["losses"] += 1
    log(f"Loaded {stats['total']}t")

    start = time.time()
    scan = 0

    try:
        while True:
            scan += 1
            try:
                balance = api.get_balance()
            except:
                log("  Balance fetch failed, reconnecting...")
                time.sleep(5)
                continue

            for asset in top_assets:
                try:
                    candles = api.get_candles(asset, 60, 120, time.time())
                    if not candles or len(candles) < 50:
                        continue

                    result = strat.analyze(api, asset, candles)
                    if isinstance(result, (tuple, list)):
                        direction = result[0]
                        conf = int(result[1]) if len(result) > 1 else 50
                    else:
                        direction = result
                        conf = 50

                    if direction in ["call", "put"]:
                        amount = min(AMOUNT, max(3, int(balance * 0.03)))
                        ok, tid = api.buy(amount, asset, direction, 1)
                        log(f"SIG: {asset} {direction.upper()} {amount} (c={conf}) id={tid} ok={ok}")

                        if ok:
                            time.sleep(65)
                            order = api.get_async_order(tid)
                            if order:
                                msg = order.get("option-closed", {}).get("msg", {})
                                profit = msg.get("profit_amount", 0) - amount
                            else:
                                profit = -amount

                            win = profit > 0
                            trade = {"time": time.strftime("%Y-%m-%d %H:%M:%S"),
                                     "asset": asset, "direction": direction,
                                     "amount": amount, "conf": conf,
                                     "profit": profit, "win": win}
                            trades.append(trade)
                            stats["total"] += 1
                            stats["pnl"] += profit
                            if win:
                                stats["wins"] += 1
                            else:
                                stats["losses"] += 1
                            wr = stats["wins"]/stats["total"]*100 if stats["total"] else 0
                            log(f"  {'WIN' if win else 'LOSS'} p={profit:.1f} ({stats['total']}t {wr:.0f}% pnl={stats['pnl']:.1f})")
                            json.dump(trades, open(RESULTS_FILE, "w"), indent=2)
                            time.sleep(3)
                except Exception as e:
                    log(f"  {asset} E: {type(e).__name__}")
                    continue

            if scan % 6 == 0:
                elapsed = (time.time()-start)/60
                wr = stats["wins"]/stats["total"]*100 if stats["total"] else 0
                log(f"[{scan}] {stats['total']}t {stats['wins']}w/{stats['losses']}l {wr:.0f}% pnl={stats['pnl']:.2f} ({elapsed:.0f}m)")

            time.sleep(15)
    except:
        log("CRASHED - restarting...")
        json.dump(trades, open(RESULTS_FILE, "w"), indent=2)
        return True  # Signal restart

    json.dump(trades, open(RESULTS_FILE, "w"), indent=2)
    return False

# Auto-restart loop
while run():
    print(".", end="", flush=True)
    time.sleep(5)
