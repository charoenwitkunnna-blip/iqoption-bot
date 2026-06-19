#!/usr/bin/env python3
"""GitHub Actions — runs continuously, dynamic assets, subprocess candle fetch."""
import sys, os, time, json, importlib, subprocess, logging
logging.disable(logging.CRITICAL)

AMOUNT = 5
EXPIRY = 1
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(BASE_DIR, "results")
os.makedirs(RESULTS, exist_ok=True)
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, ".."))

strat = importlib.import_module("new_algos.rho_bounce.strategy")
log_file = os.path.join(RESULTS, "rho_practice.log")
trades_file = os.path.join(RESULTS, "rho_practice_trades.json")
worker = os.path.join(BASE_DIR, "_candle_worker.py")

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

def run_worker(args, timeout=25):
    env = {**os.environ, "PYTHONPATH": BASE_DIR + ":" + os.path.join(BASE_DIR, "..")}
    try:
        r = subprocess.run(["python3", worker] + args, capture_output=True, text=True, timeout=timeout, env=env, cwd=BASE_DIR)
        if r.stderr:
            for line in r.stderr.strip().split("\n")[:5]:
                log(f"  WORKER: {line}")
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
        else:
            log(f"  WORKER exit={r.returncode}")
    except subprocess.TimeoutExpired:
        log(f"  WORKER TIMEOUT after {timeout}s")
    except Exception as e:
        log(f"  WORKER ERROR: {e}")
    return None

def get_open_assets():
    result = run_worker(["open"], timeout=30)
    if result:
        try: return json.loads(result)
        except: pass
    return {}

def get_candles(asset, period=60, count=50):
    result = run_worker(["candles", asset, str(period), str(count)], timeout=25)
    if result:
        try:
            data = json.loads(result)
            return [{"close": d[0], "max": d[1], "min": d[2], "open": d[3]} for d in data]
        except: pass
    return None

trades = load_trades()
start_time = time.time()
MAX_RUNTIME = 4.5 * 3600  # 4.5 hours

log("Starting continuous bot...")
cycle = 0

while time.time() - start_time < MAX_RUNTIME:
    cycle += 1
    log(f"Cycle {cycle}")

    # Get dynamic open assets
    paying = get_open_assets()
    if not paying:
        log("No open assets, waiting 60s...")
        time.sleep(60)
        continue
    log(f"Found {len(paying)} paying assets")

    # Scan for signals
    top = sorted(paying.keys(), key=paying.get, reverse=True)
    found_signal = False

    for asset in top:
        if time.time() - start_time > MAX_RUNTIME:
            break

        candles = get_candles(asset)
        if not candles or len(candles) < 30:
            continue  # skip 0-candle assets

        try:
            direction, confidence = strat.analyze(None, asset, candles)
        except:
            continue
        if direction is None:
            continue

        log(f"SIGNAL: {asset} {direction} conf={confidence}")

        # Connect for trade
        from iqoptionapi.stable_api import IQ_Option
        email = os.environ.get("IQ_EMAIL", "")
        pwd = os.environ.get("IQ_PASSWORD", "")
        api = IQ_Option(email, pwd)
        ok, r = api.connect()
        if not ok:
            log(f"Connect failed: {r}")
            break

        api.change_balance("PRACTICE")
        time.sleep(2)

        try:
            ok, tid = api.buy(AMOUNT, asset, direction, EXPIRY)
            if not ok:
                log(f"Buy failed: {tid}")
                break
        except Exception as e:
            log(f"Buy error: {e}")
            break

        log(f"Placed: {asset} {direction} TID={tid}")
        time.sleep(68)

        try:
            result = api.check_win_v4(tid)
            win = result[0] == "win"
        except:
            win = False

        payout = paying.get(asset, 87)
        profit = AMOUNT * (payout / 100) if win else -AMOUNT
        trade = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "asset": asset, "direction": direction,
            "amount": AMOUNT, "confidence": confidence,
            "profit": profit, "win": win,
            "payout": payout,
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
        log("No signals found, waiting 30s...")
    
    # Rate limit backoff — if too many 0-candle results, wait longer
    elapsed = time.time() - start_time
    if elapsed > 3600:  # After 1 hour, take longer breaks
        time.sleep(60)
    else:
        time.sleep(30)

    # Wait between cycles
    time.sleep(30)

log(f"Done after {cycle} cycles, {len(trades)} total trades")
