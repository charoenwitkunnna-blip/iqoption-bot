#!/usr/bin/env python3
"""Train ML model on historical data for each asset, then test on PRACTICE"""
import sys, os, time, json, importlib, numpy as np
sys.path.insert(0, '/root/iqoption-bot/experiments')

LOG_FILE = "/root/iqoption-bot/experiments/results/ml_training.log"

def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

log("=== ML Training & Test started ===")

from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD, BALANCE_TYPE
from iqoptionapi.stable_api import IQ_Option

api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
check, reason = api.connect()
api.change_balance(BALANCE_TYPE)
time.sleep(1)
log(f"Connected. Balance: {api.get_balance()} PRACTICE")

# Get assets
data = api.get_all_init_v2()
import iqoptionapi.constants as OP_code
all_assets = {}
for opt in ["binary", "blitz"]:
    for aid, act in data.get(opt, {}).get("actives", {}).items():
        name = str(act.get("name", "")).split(".")[-1]
        if act.get("enabled") and not act.get("is_suspended"):
            if name not in OP_code.ACTIVES:
                OP_code.ACTIVES[name] = int(aid)
            all_assets[name] = int(aid)

payouts = api.get_all_profit()
tradable = [(n, payouts.get(n, {}).get("turbo", payouts.get(n, {}).get("binary", 0)))
            for n in all_assets if payouts.get(n, {}).get("turbo", 0) >= 0.5]
tradable.sort(key=lambda x: x[1], reverse=True)
top_assets = [a for a, p in tradable[:5]]
log(f"Top 5 assets: {top_assets}")

# Load ML strategy module
spec = importlib.util.spec_from_file_location("ml_strategy", "/root/iqoption-bot/experiments/ml_strategy/strategy.py")
ml = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ml)
ml_strategy = ml.ml_strategy
ml_strategy.confidence_threshold = 70

import pandas as pd

trained_count = 0
for asset in top_assets:
    log(f"Training {asset}...")
    
    # Fetch ~12 hours of 1-min candles (720 candles)
    all_candles = []
    try:
        for _ in range(6):
            c = api.get_candles(asset, 60, 200, time.time())
            if c and len(c) > 50:
                all_candles.extend(c)
            time.sleep(0.5)
    except Exception as e:
        log(f"  Failed candles: {e}")
        continue
    
    if not all_candles or len(all_candles) < 100:
        log(f"  Not enough data: {len(all_candles) if all_candles else 0}")
        continue
    
    log(f"  Got {len(all_candles)} candles, deduplicating...")
    
    # Deduplicate and sort by timestamp
    seen = set()
    unique = []
    for c in sorted(all_candles, key=lambda x: x['id']):
        if c['id'] not in seen:
            seen.add(c['id'])
            unique.append(c)
    
    log(f"  Unique: {len(unique)} candles")
    
    # Convert to DataFrame
    df = pd.DataFrame(unique)
    df['close'] = df['close'].astype(float)
    df['high'] = df['max'].astype(float) 
    df['low'] = df['min'].astype(float)
    df['open'] = df['open'].astype(float)
    df['volume'] = df['volume'].astype(float)
    df = df.sort_values('id').reset_index(drop=True)
    
    # Train!
    success = ml_strategy.train(df)
    if success:
        trained_count += 1
        log(f"  Trained OK! {len(X)} samples, {X.shape[1]} features")
    else:
        log(f"  Training failed")

log(f"\nTrained {trained_count}/{len(top_assets)} assets")

# Now test on PRACTICE - scan and trade
log("\n=== Starting PRACTICE trading ===")

trades_file = "/root/iqoption-bot/experiments/results/ml_trades.json"
trades_hist = []
if os.path.exists(trades_file):
    try:
        with open(trades_file) as f:
            trades_hist = json.load(f)
    except:
        trades_hist = []

trades = trades_hist
start_balance = api.get_balance()
log(f"Start balance: {start_balance}")

test_runs = 0
while test_runs < 10:
    test_runs += 1
    balance = api.get_balance()
    
    for asset in top_assets:
        try:
            candles = api.get_candles(asset, 60, 120, time.time())
            if not candles or len(candles) < 50:
                continue
            
            direction, confidence = ml.analyze(api, asset, candles)
            if direction and confidence >= 70:
                amount = 5
                tid, success = api.buy(amount, asset, direction, 1)
                log(f"ML: {asset} {direction.upper()} x{amount} (conf={confidence:.0f}%) id={tid}")
                
                if success:
                    time.sleep(65)
                    result = api.get_async_order(tid)
                    profit = result.get("profit", 0) - amount
                    win = profit > 0
                    trades.append({
                        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "asset": asset, "direction": direction,
                        "amount": amount, "confidence": float(confidence),
                        "profit": profit, "win": win
                    })
                    total_pnl = sum(t["profit"] for t in trades)
                    wins = sum(1 for t in trades if t["win"])
                    wr = (wins / len(trades) * 100) if trades else 0
                    log(f"  {'WIN' if win else 'LOSS'} p={profit:.1f} ({len(trades)}t {wr:.0f}% wr pnl={total_pnl:.1f})")
                    
                    with open(trades_file, "w") as f:
                        json.dump(trades, f, indent=2)
                    time.sleep(3)
        except Exception as e:
            log(f"  {asset} ERR: {e}")
            continue
    
    if test_runs < 10:
        time.sleep(15)

final_bal = api.get_balance()
total_pnl = sum(t["profit"] for t in trades)
wins = sum(1 for t in trades if t["win"])
wr = (wins / len(trades) * 100) if trades else 0
log(f"\n=== FINAL: {len(trades)} trades {wr:.0f}% wr pnl={total_pnl:.1f} bal={final_bal:.1f} ===")
with open(trades_file, "w") as f:
    json.dump(trades, f, indent=2)
