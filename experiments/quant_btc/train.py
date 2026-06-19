#!/usr/bin/env python3
"""Fast BTC ML trainer — vectorized features, max data."""
import sys, os, time, json, pickle
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE_DIR, '..'))

_env = os.path.join(BASE_DIR, '..', '..', '.env')
if os.path.exists(_env):
    for _line in open(_env):
        _line = _line.strip()
        if _line and not _line.startswith('#') and '=' in _line:
            _k, _v = _line.split('=', 1)
            os.environ.setdefault(_k.strip(), _v.strip())

from iqoptionapi.stable_api import IQ_Option
from quant_btc.features_vec import make_all_features, make_training_labels

RESULTS = os.path.join(BASE_DIR, "results")
os.makedirs(RESULTS, exist_ok=True)
MODEL_PATH = os.path.join(RESULTS, "btc_model.pkl")
DATA_PATH = os.path.join(RESULTS, "btc_candles.json")

def connect_api():
    api = IQ_Option(os.environ.get('IQ_OPTION_EMAIL',''), os.environ.get('IQ_OPTION_PASSWORD',''))
    ok, _ = api.connect()
    if ok:
        api.change_balance('PRACTICE')
        time.sleep(1)
    return api if ok else None

def collect_candles(api, asset='BTCUSD', period=60, batches=100):
    all_candles = []
    seen = set()
    for i in range(batches):
        try:
            offset = time.time() - (i + 1) * 100 * period
            c = api.get_candles(asset, period, 100, offset)
            if c:
                new = 0
                for x in c:
                    t = x.get('from', 0)
                    if t not in seen:
                        seen.add(t)
                        all_candles.append({"close": x.get("close",0), "max": x.get("max",0),
                                            "min": x.get("min",0), "open": x.get("open",0), "time": t})
                        new += 1
                if new == 0:
                    break
                if (i+1) % 20 == 0:
                    print(f"  Batch {i+1}: {len(all_candles)} candles")
            else:
                break
            time.sleep(0.3)
        except Exception as e:
            print(f"  Batch {i+1} err: {e}")
            time.sleep(1)
    all_candles.sort(key=lambda c: c['time'])
    return all_candles

def train_and_evaluate(candles, forward, label_name):
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import classification_report
    
    print(f"\n--- {label_name} ---")
    
    t0 = time.time()
    matrix, names, valid = make_all_features(candles)
    labels = make_training_labels(candles, forward)
    
    # Only use valid rows with valid labels
    mask = valid & ~np.isnan(labels)
    X = matrix[mask]
    y = labels[mask].astype(int)
    
    print(f"Features computed in {time.time()-t0:.1f}s")
    print(f"Samples: {len(X)}, Features: {len(names)}")
    print(f"Balance: {sum(y)}/{len(y)} = {sum(y)/len(y)*100:.1f}% up")
    
    if len(X) < 200:
        print("Too few samples")
        return None
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    tscv = TimeSeriesSplit(n_splits=5)
    
    models = {
        'RF-300-d8': RandomForestClassifier(n_estimators=300, max_depth=8, min_samples_leaf=20, random_state=42, n_jobs=-1),
        'RF-500-d10': RandomForestClassifier(n_estimators=500, max_depth=10, min_samples_leaf=10, random_state=42, n_jobs=-1),
        'GB-200-d4': GradientBoostingClassifier(n_estimators=200, max_depth=4, learning_rate=0.05, random_state=42),
        'GB-300-d5': GradientBoostingClassifier(n_estimators=300, max_depth=5, learning_rate=0.03, random_state=42),
    }
    
    best_model, best_score, best_name = None, 0, ""
    for name, model in models.items():
        scores = []
        for tri, tsi in tscv.split(X_scaled):
            model.fit(X_scaled[tri], y[tri])
            scores.append(model.score(X_scaled[tsi], y[tsi]))
        m = np.mean(scores)
        print(f"  {name}: {m:.3f} (+/- {np.std(scores):.3f})")
        if m > best_score:
            best_score, best_model, best_name = m, model, name
    
    print(f"Best: {best_name} = {best_score:.3f}")
    
    # Retrain on all
    best_model.fit(X_scaled, y)
    
    # Feature importance
    if hasattr(best_model, 'feature_importances_'):
        imp = sorted(zip(names, best_model.feature_importances_), key=lambda x: -x[1])
        print("Top features:")
        for n, v in imp[:8]:
            print(f"    {n}: {v:.3f}")
    
    return best_model, scaler, names, best_name, best_score, len(X)

def main():
    print("=== BTC ML Trainer (FAST, MAX DATA) ===\n")
    
    # Check for cached data
    if os.path.exists(DATA_PATH):
        print("Loading cached candle data...")
        with open(DATA_PATH) as f:
            data = json.load(f)
        candles_1m = data.get('1m', [])
        candles_5m = data.get('5m', [])
        print(f"  1m: {len(candles_1m)}, 5m: {len(candles_5m)}")
    else:
        print("Connecting...")
        api = connect_api()
        if not api:
            print("Failed!"); return
        
        print("Collecting 1m candles...")
        candles_1m = collect_candles(api, 'BTCUSD', 60, 100)
        print(f"Got {len(candles_1m)} 1m candles")
        
        print("Collecting 5m candles...")
        candles_5m = collect_candles(api, 'BTCUSD', 300, 100)
        print(f"Got {len(candles_5m)} 5m candles")
        
        with open(DATA_PATH, 'w') as f:
            json.dump({'1m': candles_1m, '5m': candles_5m}, f)
        print("Data saved")
    
    results = []
    
    # Train on 1m with different forwards
    for fwd in [3, 5, 10]:
        r = train_and_evaluate(candles_1m, fwd, f"1m-{fwd}candle")
        if r: results.append(('1m', fwd, r))
    
    # Train on 5m
    for fwd in [3, 5]:
        r = train_and_evaluate(candles_5m, fwd, f"5m-{fwd}candle")
        if r: results.append(('5m', fwd, r))
    
    if not results:
        print("\nNo viable models!"); return
    
    best = max(results, key=lambda x: x[2][4])
    tf, fwd, (model, scaler, features, name, score, nsamp) = best
    
    print(f"\n{'='*40}")
    print(f"BEST: {name} on {tf}, {fwd}-forward, CV={score:.3f}, n={nsamp}")
    
    bundle = {
        'model': model, 'scaler': scaler, 'features': features,
        'name': name, 'score': score, 'timeframe': tf, 'forward': fwd,
        'trained_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'n_samples': nsamp,
    }
    with open(MODEL_PATH, 'wb') as f:
        pickle.dump(bundle, f)
    print(f"Saved to {MODEL_PATH}")

if __name__ == '__main__':
    main()
