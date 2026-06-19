#!/usr/bin/env python3
"""
ML TRAINER — feature engineering + XGBoost model.
Reads ml_data/*.json, engineers ~60 features, trains classifier.
Target: predict price direction in 3 minutes (for 3-min digital options).

Usage: source ../venv/bin/activate && python3 ml_train.py
"""
import os, json, time, pickle
import numpy as np
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, accuracy_score
import xgboost as xgb

DATA_DIR = "/root/iqoption-bot/experiments/ml_data"
MODEL_DIR = "/root/iqoption-bot/experiments/ml_models"
os.makedirs(MODEL_DIR, exist_ok=True)

# ============================================================
#  FEATURE ENGINEERING
# ============================================================

def rsi(closes, period):
    if len(closes) < period + 1:
        return None
    d = np.diff(closes)
    g = np.where(d > 0, d, 0)
    l = np.where(d < 0, -d, 0)
    ag = np.mean(g[:period])
    al = np.mean(l[:period])
    if al == 0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + ag / al))

def ema(data, period):
    if len(data) < period:
        return None
    a = 2.0 / (period + 1.0)
    result = np.zeros(len(data))
    result[0] = data[0]
    for i in range(1, len(data)):
        result[i] = a * data[i] + (1 - a) * result[i - 1]
    return result

def macd(closes, fast=12, slow=26, signal=9):
    if len(closes) < slow + signal:
        return None, None, None
    e_fast = ema(closes, fast)
    e_slow = ema(closes, slow)
    if e_fast is None or e_slow is None:
        return None, None, None
    macd_line = e_fast - e_slow
    sig_line = ema(macd_line, signal)
    if sig_line is None:
        return None, None, None
    hist = macd_line - sig_line
    return macd_line[-1], sig_line[-1], hist[-1]

def bollinger(closes, period=20, std=2):
    if len(closes) < period:
        return None, None, None
    ma = np.mean(closes[-period:])
    s = np.std(closes[-period:])
    upper = ma + std * s
    lower = ma - std * s
    pct_b = (closes[-1] - lower) / (upper - lower) if (upper - lower) > 0 else 0.5
    bw = (upper - lower) / ma if ma > 0 else 0
    return pct_b, bw, ma

def atr(highs, lows, closes, period=14):
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i - 1]),
                 abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    trs = np.array(trs)
    av = np.zeros(len(trs))
    av[period - 1] = np.mean(trs[:period])
    for i in range(period, len(trs)):
        av[i] = (av[i - 1] * (period - 1) + trs[i]) / period
    return av[-1]

def adx(highs, lows, closes, period=14):
    n = len(closes)
    if n < period + 1:
        return None
    tr = np.zeros(n)
    pd = np.zeros(n)
    nd = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i],
                    abs(highs[i] - closes[i - 1]),
                    abs(lows[i] - closes[i - 1]))
        u = highs[i] - highs[i - 1]
        d = lows[i - 1] - lows[i]
        pd[i] = u if (u > d and u > 0) else 0
        nd[i] = d if (d > u and d > 0) else 0
    ts = np.zeros(n)
    ps = np.zeros(n)
    ns = np.zeros(n)
    ts[period] = sum(tr[1:period + 1])
    ps[period] = sum(pd[1:period + 1])
    ns[period] = sum(nd[1:period + 1])
    for i in range(period + 1, n):
        ts[i] = ts[i - 1] - ts[i - 1] / period + tr[i]
        ps[i] = ps[i - 1] - ps[i - 1] / period + pd[i]
        ns[i] = ns[i - 1] - ns[i - 1] / period + nd[i]
    pi = np.zeros(n)
    ni = np.zeros(n)
    dx = np.zeros(n)
    ax = np.zeros(n)
    for i in range(period + 1, n):
        if ts[i] > 0:
            pi[i] = 100 * ps[i] / ts[i]
            ni[i] = 100 * ns[i] / ts[i]
        if pi[i] + ni[i] > 0:
            dx[i] = 100 * abs(pi[i] - ni[i]) / (pi[i] + ni[i])
    ax[period * 2] = np.mean(dx[period + 1:period * 2 + 1])
    for i in range(period * 2 + 1, n):
        ax[i] = (ax[i - 1] * (period - 1) + dx[i]) / period
    # Return last 2 for direction
    if n > period * 2 + 1:
        return ax[-1], ax[-2]
    return ax[-1], None

def stochastic(highs, lows, closes, k_period=14, d_period=3):
    if len(closes) < k_period:
        return None
    hh = np.max(highs[-k_period:])
    ll = np.min(lows[-k_period:])
    if hh == ll:
        return 50.0, 50.0
    k = 100 * (closes[-1] - ll) / (hh - ll)
    # Simplified: just return K
    return k, k  # K and D (simplified for speed)

def extract_features(closes, highs, lows, i):
    """
    Extract features at position i (looking at data up to i).
    Target is whether closes[i+3] > closes[i] (for 3-min prediction).
    """
    window_c = closes[max(0, i - 50):i + 1]
    window_h = highs[max(0, i - 50):i + 1]
    window_l = lows[max(0, i - 50):i + 1]

    if len(window_c) < 30:
        return None

    features = {}

    # Price at point i
    cur_close = closes[i]
    cur_high = highs[i]
    cur_low = lows[i]

    # ---- RSI ----
    for p in [2, 5, 7, 10, 14]:
        r = rsi(window_c, p)
        features[f'rsi_{p}'] = r if r is not None else 50.0

    # ---- MACD ----
    ml, sl, h = macd(window_c)
    features['macd_line'] = ml if ml is not None else 0.0
    features['macd_signal'] = sl if sl is not None else 0.0
    features['macd_hist'] = h if h is not None else 0.0
    features['macd_cross'] = 1.0 if (ml is not None and sl is not None and ml > sl) else 0.0

    # ---- Bollinger Bands ----
    pct_b, bw, bma = bollinger(window_c)
    features['bb_pct_b'] = pct_b if pct_b is not None else 0.5
    features['bb_width'] = bw if bw is not None else 0.0
    features['bb_ma'] = bma if bma is not None else cur_close

    # ---- ATR (volatility) ----
    a14 = atr(window_h, window_l, window_c, 14)
    a7 = atr(window_h, window_l, window_c, 7)
    features['atr_14'] = a14 if a14 is not None else 0.0
    features['atr_7'] = a7 if a7 is not None else 0.0
    features['atr_ratio'] = (a7 / a14) if (a14 and a14 > 0) else 1.0

    # ---- ADX ----
    ax, ax_prev = adx(window_h, window_l, window_c, 14)
    features['adx'] = ax if ax is not None else 20.0
    features['adx_rising'] = 1.0 if (ax is not None and ax_prev is not None and ax > ax_prev) else 0.0

    # ---- EMA crossovers ----
    e5 = ema(window_c, 5)
    e10 = ema(window_c, 10)
    e20 = ema(window_c, 20)
    if e5 is not None and e10 is not None:
        features['ema_5_10_cross'] = 1.0 if e5[-1] > e10[-1] else 0.0
        features['ema_5_10_dist'] = (e5[-1] - e10[-1]) / cur_close if cur_close > 0 else 0.0
    else:
        features['ema_5_10_cross'] = 0.0
        features['ema_5_10_dist'] = 0.0
    if e10 is not None and e20 is not None:
        features['ema_10_20_cross'] = 1.0 if e10[-1] > e20[-1] else 0.0
    else:
        features['ema_10_20_cross'] = 0.0

    # ---- Price above/below EMA ----
    features['above_ema5'] = 1.0 if (e5 is not None and cur_close > e5[-1]) else 0.0
    features['above_ema10'] = 1.0 if (e10 is not None and cur_close > e10[-1]) else 0.0
    features['above_ema20'] = 1.0 if (e20 is not None and cur_close > e20[-1]) else 0.0

    # ---- Price momentum (returns) ----
    for p in [1, 3, 5, 10]:
        if i >= p:
            ret = (cur_close - closes[i - p]) / closes[i - p] if closes[i - p] > 0 else 0.0
        else:
            ret = 0.0
        features[f'return_{p}'] = ret

    # ---- Candle features ----
    body = cur_close - window_c[-2] if len(window_c) > 1 else 0.0
    candle_range = cur_high - cur_low
    features['body'] = body
    features['body_pct'] = abs(body) / cur_close if cur_close > 0 else 0.0
    features['range'] = candle_range
    features['range_pct'] = candle_range / cur_close if cur_close > 0 else 0.0

    # Upper/lower wick ratios
    if candle_range > 0:
        if body >= 0:
            features['upper_wick'] = (cur_high - cur_close) / candle_range
            features['lower_wick'] = (window_c[-2] - cur_low) / candle_range if len(window_c) > 1 else 0.0
        else:
            features['upper_wick'] = (cur_high - window_c[-2]) / candle_range if len(window_c) > 1 else 0.0
            features['lower_wick'] = (cur_close - cur_low) / candle_range
    else:
        features['upper_wick'] = 0.0
        features['lower_wick'] = 0.0

    # ---- Stochastic ----
    sk, sd = stochastic(window_h, window_l, window_c)
    features['stoch_k'] = sk if sk is not None else 50.0
    features['stoch_d'] = sd if sd is not None else 50.0

    # ---- Position in recent range ----
    hh20 = np.max(window_h[-20:]) if len(window_h) >= 20 else cur_high
    ll20 = np.min(window_l[-20:]) if len(window_l) >= 20 else cur_low
    if hh20 > ll20:
        features['pos_in_range'] = (cur_close - ll20) / (hh20 - ll20)
    else:
        features['pos_in_range'] = 0.5

    # ---- Trend direction (last 5 candles) ----
    if len(window_c) >= 5:
        up_count = sum(1 for j in range(-4, 0) if window_c[j] > window_c[j - 1])
        features['trend_up5'] = up_count / 4.0
    else:
        features['trend_up5'] = 0.5

    # ---- Volatility expansion ----
    if a7 is not None and a14 is not None and a14 > 0:
        features['vol_expanding'] = 1.0 if a7 > a14 else 0.0
    else:
        features['vol_expanding'] = 0.0

    return features


# ============================================================
#  MAIN: LOAD DATA, EXTRACT FEATURES, TRAIN
# ============================================================

print("Loading data...")
data_files = [f for f in os.listdir(DATA_DIR) if f.endswith('.json')]
print(f"Found {len(data_files)} asset files")

X_list, y_list = [], []
total_samples = 0

for fname in data_files:
    path = os.path.join(DATA_DIR, fname)
    with open(path) as f:
        candles = json.load(f)

    if len(candles) < 60:
        continue

    closes = np.array([c['close'] for c in candles], dtype=float)
    highs = np.array([c['max'] for c in candles], dtype=float)
    lows = np.array([c['min'] for c in candles], dtype=float)

    # Slide window: at each position i, extract features and label if i+3 exists
    for i in range(50, len(candles) - 3):
        feats = extract_features(closes, highs, lows, i)
        if feats is None:
            continue

        # Target: does price go up in 3 candles?
        target = 1 if closes[i + 3] > closes[i] else 0

        X_list.append(feats)
        y_list.append(target)
        total_samples += 1

    if total_samples % 5000 == 0 and total_samples > 0:
        print(f"  Processed {total_samples} samples...")

print(f"\nTotal samples: {total_samples}")

# Convert to arrays
feature_names = sorted(X_list[0].keys())
X = np.array([[d[k] for k in feature_names] for d in X_list], dtype=float)
y = np.array(y_list, dtype=int)

print(f"Feature matrix: {X.shape}")
print(f"Class balance: {np.mean(y):.1%} UP / {1-np.mean(y):.1%} DOWN")

# Save feature names for later use
with open(os.path.join(MODEL_DIR, "feature_names.json"), "w") as f:
    json.dump(feature_names, f)

# Split
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

# Scale
scaler = StandardScaler()
X_train_s = scaler.fit_transform(X_train)
X_test_s = scaler.transform(X_test)

# ============================================================
#  TRAIN XGBOOST
# ============================================================

print("\nTraining XGBoost...")
print("(This may take a few minutes...)")

model = xgb.XGBClassifier(
    n_estimators=500,
    max_depth=8,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    min_child_weight=2,
    gamma=0.1,
    reg_alpha=0.1,
    reg_lambda=1.0,
    scale_pos_weight=1.0,
    objective='binary:logistic',
    eval_metric='logloss',
    random_state=42,
    n_jobs=-1,
    early_stopping_rounds=30,
)

model.fit(
    X_train_s, y_train,
    eval_set=[(X_test_s, y_test)],
    verbose=False
)

# Evaluate
train_acc = accuracy_score(y_train, model.predict(X_train_s))
test_acc = accuracy_score(y_test, model.predict(X_test_s))

print(f"\n=== RESULTS ===")
print(f"Train accuracy: {train_acc:.3f}")
print(f"Test accuracy:  {test_acc:.3f}")
print(f"\n{classification_report(y_test, model.predict(X_test_s), target_names=['DOWN', 'UP'])}")

# Cross-validation
print("5-fold CV...")
cv_scores = cross_val_score(model, scaler.fit_transform(X), y, cv=5, n_jobs=-1)
print(f"CV accuracy: {cv_scores.mean():.3f} +/- {cv_scores.std():.3f}")

# Feature importance
importances = model.feature_importances_
indices = np.argsort(importances)[::-1]
print("\n=== TOP 20 FEATURES ===")
for i in range(min(20, len(feature_names))):
    idx = indices[i]
    print(f"  {feature_names[idx]:20s}  {importances[idx]:.4f}")

# Save model
model_path = os.path.join(MODEL_DIR, "xgboost_model.pkl")
scaler_path = os.path.join(MODEL_DIR, "scaler.pkl")

with open(model_path, "wb") as f:
    pickle.dump(model, f)
with open(scaler_path, "wb") as f:
    pickle.dump(scaler, f)

print(f"\nModel saved to {model_path}")
print(f"Scaler saved to {scaler_path}")
print(f"\nDone! Ready for ml_trade.py")
