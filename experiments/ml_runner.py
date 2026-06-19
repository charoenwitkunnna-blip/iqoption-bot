#!/usr/bin/env python3
"""ML Training + Quick PRACTICE Test"""
import sys, os, time, json, importlib
import numpy as np
import pandas as pd

sys.path.insert(0, '/root/iqoption-bot/experiments')
BASE = '/root/iqoption-bot/experiments/results'
LOG_FILE = os.path.join(BASE, 'ml_training.log')

def log(msg):
    with open(LOG_FILE, 'a') as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

log("=== ML TRAINING START ===")

from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD, BALANCE_TYPE
from iqoptionapi.stable_api import IQ_Option

api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
check, reason = api.connect()
api.change_balance(BALANCE_TYPE)
time.sleep(1)
log(f"Connected: {api.get_balance()} PRACTICE")

# Get assets
data = api.get_all_init_v2()
import iqoptionapi.constants as OP_code
all_a = {}
for opt in ['binary', 'blitz']:
    for aid, act in data.get(opt, {}).get('actives', {}).items():
        name = str(act.get('name', '')).split('.')[-1]
        if act.get('enabled') and not act.get('is_suspended'):
            if name not in OP_code.ACTIVES:
                OP_code.ACTIVES[name] = int(aid)
            all_a[name] = int(aid)

payouts = api.get_all_profit()
tradable = [(n, payouts.get(n, {}).get('turbo', 0)) for n in all_a if payouts.get(n, {}).get('turbo', 0) >= 0.5]
tradable.sort(key=lambda x: x[1], reverse=True)
top = [a for a, p in tradable[:3]]
log(f"Top 3: {top}")

# Load ML module
spec = importlib.util.spec_from_file_location('ml', '/root/iqoption-bot/experiments/ml_strategy/strategy.py')
ml = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ml)
ml_strat = ml.ml_strategy

for asset in top:
    log(f"Training {asset}...")
    all_c = []
    t = time.time()
    for i in range(6):
        offset = i * 200 * 60
        c = api.get_candles(asset, 60, 200, t - offset)
        if c and len(c) > 50:
            all_c.extend(c)
        time.sleep(0.3)
    seen = set()
    unique = []
    for c in sorted(all_c, key=lambda x: x['id']):
        if c['id'] not in seen:
            seen.add(c['id'])
            unique.append(c)
    log(f"  Candles: {len(unique)}")
    if len(unique) < 100:
        log("  Skip - not enough data")
        continue
    df = pd.DataFrame(unique)
    df['close'] = df['close'].astype(float)
    df['high'] = df['max'].astype(float)
    df['low'] = df['min'].astype(float)
    df['open'] = df['open'].astype(float)
    df['volume'] = df['volume'].astype(float)
    df = df.sort_values('id').reset_index(drop=True)
    ok = ml_strat.train(df)
    log(f"  Train result: {ok}")
    if ok:
        log(f"  Model OK: {ml_strat.model.n_estimators if ml_strat.model else '?'} trees")
        last_c = api.get_candles(asset, 60, 120, time.time())
        if last_c and len(last_c) > 50:
            d, conf = ml.analyze(api, asset, last_c)
            log(f"  Prediction: {asset} {d} ({conf:.1f}%)")

# Quick test
log("\n=== PRACTICE test ===")
trades = []
tf = os.path.join(BASE, 'ml_trades.json')
bt = api.get_balance()

for cycle in range(5):
    for asset in top:
        try:
            c = api.get_candles(asset, 60, 120, time.time())
            d, conf = ml.analyze(api, asset, c)
            if d and conf >= 70:
                tid, ok = api.buy(5, asset, d, 1)
                log(f"TRADE: {asset} {d} x5 ({conf:.0f}%) id={tid} ok={ok}")
                if ok:
                    time.sleep(65)
                    r = api.get_async_order(tid)
                    profit = r.get('profit', 0) - 5
                    win = profit > 0
                    trades.append({'asset': asset, 'dir': d, 'conf': conf, 'profit': profit, 'win': win})
                    wc = sum(1 for t in trades if t['win'])
                    wr = wc / len(trades) * 100 if trades else 0
                    pnl = sum(t['profit'] for t in trades)
                    status = "WIN" if win else "LOSS"
                    log(f"  {status} p={profit:.1f} ({len(trades)}t {wr:.0f}% pnl={pnl:.1f})")
                    with open(tf, 'w') as f:
                        json.dump(trades, f, indent=2)
                    time.sleep(3)
        except Exception as e:
            log(f"  {asset} ERR: {e}")
    if cycle < 4:
        time.sleep(15)

w = sum(1 for t in trades if t['win'])
wr = w / len(trades) * 100 if trades else 0
pnl = sum(t['profit'] for t in trades)
log(f"=== DONE: {len(trades)}t {wr:.0f}% wr pnl={pnl:.1f} ===")
print("ML training + test complete. Check logs.")
