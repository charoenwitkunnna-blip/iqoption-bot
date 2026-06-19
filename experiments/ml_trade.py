#!/usr/bin/env python3
"""
ML LIVE TRADER — uses trained XGBoost model to trade on PRACTICE.
Waits for 1-min candle close, extracts features, predicts 3-min direction.
"""
import sys, os, time, json, pickle
import numpy as np

AMOUNT = 5  # PRACTICE — small amount
BASE_DIR = "/root/iqoption-bot/experiments"
RESULTS_DIR = os.path.join(BASE_DIR, "results")
LOG_FILE = os.path.join(RESULTS_DIR, "ml_trader.log")
TRADES_FILE = os.path.join(RESULTS_DIR, "ml_trader_trades.json")
MODEL_DIR = os.path.join(BASE_DIR, "ml_models")

sys.path.insert(0, BASE_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, '..'))
from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD
from iqoptionapi.stable_api import IQ_Option

# Load model + scaler + feature names
with open(os.path.join(MODEL_DIR, "xgboost_model.pkl"), "rb") as f:
    model = pickle.load(f)
with open(os.path.join(MODEL_DIR, "scaler.pkl"), "rb") as f:
    scaler = pickle.load(f)
with open(os.path.join(MODEL_DIR, "feature_names.json")) as f:
    feature_names = json.load(f)

print(f"Loaded model. Features: {len(feature_names)}")

# ---------- feature functions (same as ml_train.py) ----------
def _rsi(data, period):
    if len(data) < period + 1: return None
    d = np.diff(data); g = np.where(d > 0, d, 0); l = np.where(d < 0, -d, 0)
    ag = np.mean(g[:period]); al = np.mean(l[:period])
    if al == 0: return 100.0
    return 100.0 - (100.0 / (1.0 + ag / al))

def _ema(data, period):
    if len(data) < period: return None
    a = 2.0 / (period + 1.0); r = np.zeros(len(data)); r[0] = data[0]
    for i in range(1, len(data)): r[i] = a * data[i] + (1 - a) * r[i - 1]
    return r

def _macd(closes, fast=12, slow=26, signal=9):
    if len(closes) < slow + signal: return None, None, None
    e_fast = _ema(closes, fast); e_slow = _ema(closes, slow)
    if e_fast is None or e_slow is None: return None, None, None
    ml = e_fast - e_slow; sl = _ema(ml, signal)
    if sl is None: return None, None, None
    return ml[-1], sl[-1], ml[-1] - sl[-1]

def _bb(closes, period=20, std=2):
    if len(closes) < period: return None, None, None
    ma = np.mean(closes[-period:]); s = np.std(closes[-period:])
    u = ma + std * s; l = ma - std * s
    pct = (closes[-1] - l) / (u - l) if (u - l) > 0 else 0.5
    bw = (u - l) / ma if ma > 0 else 0
    return pct, bw, ma

def _atr(h, l, c, period=14):
    if len(c) < period + 1: return None
    trs = [max(h[i] - l[i], abs(h[i] - c[i-1]), abs(l[i] - c[i-1])) for i in range(1, len(c))]
    trs = np.array(trs); av = np.zeros(len(trs)); av[period-1] = np.mean(trs[:period])
    for i in range(period, len(trs)): av[i] = (av[i-1] * (period-1) + trs[i]) / period
    return av[-1]

def _adx(h, l, c, period=14):
    n = len(c)
    if n < period + 1: return None
    tr = np.zeros(n); pd = np.zeros(n); nd = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i-1]), abs(l[i] - c[i-1]))
        u = h[i] - h[i-1]; d = l[i-1] - l[i]
        pd[i] = u if (u > d and u > 0) else 0; nd[i] = d if (d > u and d > 0) else 0
    ts = np.zeros(n); ps = np.zeros(n); ns = np.zeros(n)
    ts[period] = sum(tr[1:period+1]); ps[period] = sum(pd[1:period+1]); ns[period] = sum(nd[1:period+1])
    for i in range(period+1, n):
        ts[i] = ts[i-1] - ts[i-1]/period + tr[i]; ps[i] = ps[i-1] - ps[i-1]/period + pd[i]; ns[i] = ns[i-1] - ns[i-1]/period + nd[i]
    pi = np.zeros(n); ni = np.zeros(n); dx = np.zeros(n); ax = np.zeros(n)
    for i in range(period+1, n):
        if ts[i] > 0: pi[i] = 100 * ps[i] / ts[i]; ni[i] = 100 * ns[i] / ts[i]
        if pi[i] + ni[i] > 0: dx[i] = 100 * abs(pi[i] - ni[i]) / (pi[i] + ni[i])
    ax[period*2] = np.mean(dx[period+1:period*2+1])
    for i in range(period*2+1, n): ax[i] = (ax[i-1] * (period-1) + dx[i]) / period
    if n > period*2+1: return ax[-1], ax[-2]
    return ax[-1], None

def _stoch(h, l, c, kp=14):
    if len(c) < kp: return None, None
    hh = np.max(h[-kp:]); ll = np.min(l[-kp:])
    if hh == ll: return 50.0, 50.0
    k = 100 * (c[-1] - ll) / (hh - ll)
    return k, k

def predict(candles):
    """Extract features from candles and return prediction (0=DOWN, 1=UP) + confidence."""
    c = np.array([x['close'] for x in candles], float)
    h = np.array([x['max'] for x in candles], float)
    l = np.array([x['min'] for x in candles], float)

    if len(c) < 55:
        return None, 0

    i = len(c) - 2  # Use last COMPLETED candle (index -2)
    window_c = c[max(0, i-50):i+1]
    window_h = h[max(0, i-50):i+1]
    window_l = l[max(0, i-50):i+1]

    cur_close = c[i]; cur_high = h[i]; cur_low = l[i]
    f = {}

    for p in [2, 5, 7, 10, 14]:
        r = _rsi(window_c, p)
        f[f'rsi_{p}'] = r if r is not None else 50.0

    ml, sl, hist = _macd(window_c)
    f['macd_line'] = ml if ml is not None else 0.0
    f['macd_signal'] = sl if sl is not None else 0.0
    f['macd_hist'] = hist if hist is not None else 0.0
    f['macd_cross'] = 1.0 if (ml is not None and sl is not None and ml > sl) else 0.0

    pct_b, bw, bma = _bb(window_c)
    f['bb_pct_b'] = pct_b if pct_b is not None else 0.5
    f['bb_width'] = bw if bw is not None else 0.0
    f['bb_ma'] = bma if bma is not None else cur_close

    a14 = _atr(window_h, window_l, window_c, 14)
    a7 = _atr(window_h, window_l, window_c, 7)
    f['atr_14'] = a14 if a14 is not None else 0.0
    f['atr_7'] = a7 if a7 is not None else 0.0
    f['atr_ratio'] = (a7 / a14) if (a14 and a14 > 0) else 1.0

    ax, axp = _adx(window_h, window_l, window_c, 14)
    f['adx'] = ax if ax is not None else 20.0
    f['adx_rising'] = 1.0 if (ax is not None and axp is not None and ax > axp) else 0.0

    e5 = _ema(window_c, 5); e10 = _ema(window_c, 10); e20 = _ema(window_c, 20)
    if e5 is not None and e10 is not None:
        f['ema_5_10_cross'] = 1.0 if e5[-1] > e10[-1] else 0.0
        f['ema_5_10_dist'] = (e5[-1] - e10[-1]) / cur_close if cur_close > 0 else 0.0
    else:
        f['ema_5_10_cross'] = 0.0; f['ema_5_10_dist'] = 0.0
    f['ema_10_20_cross'] = 1.0 if (e10 is not None and e20 is not None and e10[-1] > e20[-1]) else 0.0

    f['above_ema5'] = 1.0 if (e5 is not None and cur_close > e5[-1]) else 0.0
    f['above_ema10'] = 1.0 if (e10 is not None and cur_close > e10[-1]) else 0.0
    f['above_ema20'] = 1.0 if (e20 is not None and cur_close > e20[-1]) else 0.0

    for p in [1, 3, 5, 10]:
        if i >= p:
            ret = (cur_close - c[i-p]) / c[i-p] if c[i-p] > 0 else 0.0
        else:
            ret = 0.0
        f[f'return_{p}'] = ret

    body = cur_close - window_c[-2] if len(window_c) > 1 else 0.0
    crange = cur_high - cur_low
    f['body'] = body
    f['body_pct'] = abs(body) / cur_close if cur_close > 0 else 0.0
    f['range'] = crange
    f['range_pct'] = crange / cur_close if cur_close > 0 else 0.0

    if crange > 0:
        if body >= 0:
            f['upper_wick'] = (cur_high - cur_close) / crange
            f['lower_wick'] = (window_c[-2] - cur_low) / crange if len(window_c) > 1 else 0.0
        else:
            f['upper_wick'] = (cur_high - window_c[-2]) / crange if len(window_c) > 1 else 0.0
            f['lower_wick'] = (cur_close - cur_low) / crange
    else:
        f['upper_wick'] = 0.0; f['lower_wick'] = 0.0

    sk, sd = _stoch(window_h, window_l, window_c)
    f['stoch_k'] = sk if sk is not None else 50.0
    f['stoch_d'] = sd if sd is not None else 50.0

    hh20 = np.max(window_h[-20:]) if len(window_h) >= 20 else cur_high
    ll20 = np.min(window_l[-20:]) if len(window_l) >= 20 else cur_low
    f['pos_in_range'] = (cur_close - ll20) / (hh20 - ll20) if hh20 > ll20 else 0.5

    if len(window_c) >= 5:
        up_count = sum(1 for j in range(-4, 0) if window_c[j] > window_c[j-1])
        f['trend_up5'] = up_count / 4.0
    else:
        f['trend_up5'] = 0.5

    f['vol_expanding'] = 1.0 if (a7 is not None and a14 is not None and a14 > 0 and a7 > a14) else 0.0

    # Build feature vector
    X = np.array([[f[k] for k in feature_names]], dtype=float)
    X_s = scaler.transform(X)
    proba = model.predict_proba(X_s)[0]
    pred = int(np.argmax(proba))
    confidence = float(max(proba))
    return pred, confidence


# ============================================================
#  TRADING LOOP
# ============================================================

def log(msg):
    with open(LOG_FILE, "a") as fh:
        fh.write(f"{time.strftime('%H:%M:%S')} {msg}\n")

trades = json.load(open(TRADES_FILE)) if os.path.exists(TRADES_FILE) else []

api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
api.connect()
api.change_balance("PRACTICE")
time.sleep(2)
balance = api.get_balance()

log(f"START: bal={balance:.1f} model_loaded")

all_a = api.get_all_open_time()
pairs = {x: v for x, v in all_a['turbo'].items() if v['open']}
paying = {}
for a in list(pairs.keys())[:80]:
    try:
        p = api.get_digital_payout(a)
        if p and p >= 80:
            paying[a] = p
    except: pass

top = sorted(paying, key=paying.get, reverse=True)
log(f"  Scanned: {len(top)} paying assets")

for asset in top:
    try:
        candles = api.get_candles(asset, 60, 55, time.time())
        if not candles or len(candles) < 55:
            continue
    except:
        continue

    pred, confidence = predict(candles)
    if pred is None:
        continue

    # Confidence floor
    if confidence < 0.55:
        continue

    direction = "call" if pred == 1 else "put"

    try:
        ok, tid = api.buy(AMOUNT, asset, direction, 3)  # 3-min expiry
        if not ok:
            log(f"  {asset} {direction} FAIL: {tid}")
            continue
    except Exception as e:
        log(f"  {asset} {direction} ERROR: {e}")
        continue

    time.sleep(185)  # Wait for 3-min expiry
    try:
                result = api.check_win_digital_v2(tid)
        if isinstance(result, (list, tuple)):
            win = bool(result[0])
        else:
            win = bool(result)
    except:
        win = False

    payout_pct = paying.get(asset, 87)
    profit = AMOUNT * (payout_pct / 100) if win else -AMOUNT
    trade = {
        "time": time.strftime('%Y-%m-%d %H:%M:%S'),
        "asset": asset, "direction": direction,
        "amount": AMOUNT, "confidence": round(confidence, 3),
        "profit": profit, "win": win, "payout": payout_pct
    }
    trades.append(trade)
    json.dump(trades, open(TRADES_FILE, "w"), indent=2)

    w = sum(1 for t in trades if t['win'])
    log(f"  {asset} {direction.upper()} {'WIN' if win else 'LOSS'} conf={confidence:.2f} now={w}/{len(trades)} {w/len(trades)*100:.0f}% pnl={sum(t['profit'] for t in trades):+.1f} bal={balance+profit:.1f}")
    break

w = sum(1 for t in trades if t['win'])
t = len(trades)
pnl = sum(t['profit'] for t in trades)
wr = f"{w/t*100:.0f}%" if t > 0 else "0%"
log(f"DONE: {t}t {w}w/{t-w}l {wr} pnl={pnl:+.1f}")
api.close_connect()
