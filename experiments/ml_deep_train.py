#!/usr/bin/env python3
"""ML Deep Training — 5000+ candles per asset, top 10 assets"""
import sys, os, time, json, importlib
import numpy as np
import pandas as pd

sys.path.insert(0, '/root/iqoption-bot/experiments')
BASE = '/root/iqoption-bot/experiments/results'
LOG = os.path.join(BASE, 'ml_deep_training.log')
CACHE_DIR = os.path.join(BASE, 'ml_data')

def log(msg):
    with open(LOG, 'a') as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")
    print(msg)

os.makedirs(CACHE_DIR, exist_ok=True)
log("=== ML DEEP TRAINING START ===")

from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD, BALANCE_TYPE
from iqoptionapi.stable_api import IQ_Option

api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
check, reason = api.connect()
assert check, f"Connection failed: {reason}"
api.change_balance(BALANCE_TYPE)
time.sleep(1)
log(f"Connected. Balance: {api.get_balance()}")

# Load ML
spec = importlib.util.spec_from_file_location('ml', '/root/iqoption-bot/experiments/ml_strategy/strategy.py')
ml = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ml)
ml.ml_strategy.confidence_threshold = 50  # lower for this test

# Get top 10 assets
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
top = [a for a, p in tradable[:10]]
log(f"Top 10 assets: {top}")

def fetch_candles(asset, target=5000):
    """Fetch historical candles, returns sorted DataFrame"""
    cache_file = os.path.join(CACHE_DIR, f"{asset}.csv")
    
    # Try cache first
    if os.path.exists(cache_file):
        df = pd.read_csv(cache_file)
        df['close'] = df['close'].astype(float)
        df['high'] = df['max'].astype(float)
        df['low'] = df['min'].astype(float)
        df['open'] = df['open'].astype(float)
        df['volume'] = df['volume'].astype(float)
        if len(df) >= target:
            log(f"  Loaded {len(df)} from cache")
            return df
        log(f"  Cache has {len(df)}, fetching more...")
    
    all_c = []
    t = time.time()
    batch_size = 200
    gap = 60  # 1 minute
    seen_ids = set()
    
    # IQ Option API returns latest candles from a given timestamp.
    # To get older candles, we step backwards in time.
    for i in range(30):  # 30 batches = 6000 possible candles
        try:
            offset_seconds = i * batch_size * gap + (i * 2)  # slight gap to avoid overlaps
            candles = api.get_candles(asset, 60, batch_size, t - offset_seconds)
            if not candles:
                break
            for c in candles:
                if c['id'] not in seen_ids:
                    seen_ids.add(c['id'])
                    all_c.append(c)
            if i > 0 and len(candles) < batch_size * 0.8:
                break  # Hit the start of available data
            time.sleep(0.2)
        except Exception as e:
            log(f"  Fetch error at batch {i}: {e}")
            break
    
    # Sort and dedup
    all_c.sort(key=lambda x: x['id'])
    log(f"  Fetched {len(all_c)} unique candles for {asset}")
    
    if not all_c:
        return None
    
    df = pd.DataFrame(all_c)
    df['close'] = df['close'].astype(float)
    df['open'] = df['open'].astype(float)
    df['high'] = df['max'].astype(float)
    df['low'] = df['min'].astype(float)
    df['volume'] = df['volume'].astype(float)
    df = df.sort_values('id').reset_index(drop=True)
    
    # Cache
    df.to_csv(cache_file, index=False)
    log(f"  Cached {len(df)} rows")
    return df

def train_and_test(df, asset):
    """Train ML on df and return metrics"""
    ml.ml_strategy.model = None
    ml.ml_strategy.scaler = None
    
    ok = ml.ml_strategy.train(df)
    if not ok:
        return None, None, 0.0
    
    # Test on latest data (last 20% as test set)
    split = int(len(df) * 0.8)
    test_df = df.iloc[split:].reset_index(drop=True)
    
    correct = 0
    total = 0
    for idx in range(50, len(test_df)):
        segment = test_df.iloc[idx-50:idx]
        # Rebuild candle format
        seg_dict = segment.to_dict('records')
        d, conf = ml.analyze(api, asset, seg_dict)
        if d:
            total += 1
            actual_next = test_df.iloc[idx]['close'] - test_df.iloc[idx-1]['close']
            actual_dir = 'call' if actual_next > 0 else 'put'
            if d == actual_dir:
                correct += 1
    
    acc = correct / total * 100 if total > 0 else 0
    
    # Get latest prediction
    latest = api.get_candles(asset, 60, 120, time.time())
    d, conf = ml.analyze(api, asset, latest)
    
    return ml.ml_strategy.model, d, conf, acc, total

# Fetch and train each asset
results = {}
for asset in top:
    log(f"\n=== {asset} ===")
    df = fetch_candles(asset, 5000)
    if df is None or len(df) < 200:
        log(f"  SKIP — insufficient data")
        continue
    
    log(f"  Training on {len(df)} candles...")
    model, direction, confidence, accuracy, test_count = train_and_test(df, asset)
    
    results[asset] = {
        'candles': len(df),
        'direction': direction,
        'confidence': confidence,
        'accuracy': accuracy,
        'test_trades': test_count,
        'features': len(ml.ml_strategy.features) if hasattr(ml.ml_strategy, 'features') and ml.ml_strategy.features else 0
    }
    
    status = f"{'TRAINED' if model else 'FAILED'} | {direction or 'N/A'} ({confidence:.0f}%) | Test: {test_count}samples {accuracy:.0f}%"
    log(f"  {status}")
    
    # Save model per asset
    if model:
        import joblib
        model_dir = os.path.join(BASE, 'ml_models')
        os.makedirs(model_dir, exist_ok=True)
        joblib.dump({'model': model, 'scaler': ml.ml_strategy.scaler, 'features': ml.ml_strategy.features}, 
                     os.path.join(model_dir, f"{asset}.pkl"))
        log(f"  Model saved")

# Summary
log("\n" + "="*60)
log("TRAINING SUMMARY")
log("="*60)
for asset, r in results.items():
    log(f"  {asset:25s} | {r['candles']:5d} candles | dir={str(r['direction']):5s} | conf={r['confidence']:.0f}% | test_acc={r['accuracy']:.0f}%")
log("="*60)

# Now run a PRACTICE test with threshold 50
log("\n=== PRACTICE TEST ===")

# Reload best models
trades = []
tf = os.path.join(BASE, 'ml_deep_trades.json')
bal = api.get_balance()
log(f"Starting balance: {bal}")

import joblib
model_dir = os.path.join(BASE, 'ml_models')

for cycle in range(10):
    for asset in top:
        model_path = os.path.join(model_dir, f"{asset}.pkl")
        if not os.path.exists(model_path):
            continue
        
        # Re-predict
        c = api.get_candles(asset, 60, 120, time.time())
        if not c or len(c) < 50:
            continue
        
        d, conf = ml.analyze(api, asset, c)
        if d and conf >= 50:
            # Check if good enough
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
                log(f"  {'WIN' if win else 'LOSS'} p={profit:.1f} ({len(trades)}t {wr:.0f}% pnl={pnl:.1f})")
                with open(tf, 'w') as f:
                    json.dump(trades, f, indent=2)
                time.sleep(3)
    if cycle < 9:
        time.sleep(15)

bal = api.get_balance()
w = sum(1 for t in trades if t['win'])
wr = w / len(trades) * 100 if trades else 0
pnl = sum(t['profit'] for t in trades)
log(f"=== COMPLETE: {len(trades)} trades {wr:.0f}% wr pnl={pnl:.1f} balance={bal:.1f} ===")
print(f"\nDone! {len(trades)} trades, {wr:.0f}% WR, PnL: {pnl:.1f}")
