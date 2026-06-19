NAME = "pullback"
import numpy as np

def ema(data, period):
    if len(data) < period: return None
    a = 2.0 / (period + 1.0)
    r = np.zeros(len(data))
    r[0] = data[0]
    for i in range(1, len(data)):
        r[i] = a * data[i] + (1 - a) * r[i - 1]
    return r

def rsi(closes, period=2):
    if len(closes) < period + 1: return None
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0: return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def analyze(api, asset, candles, htf_candles=None):
    closes = np.array([c['close'] for c in candles], dtype=float)
    if len(closes) < 25: return None, 0
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    if ema9 is None or ema21 is None: return None, 0
    cur_rsi = rsi(closes, 2)
    if cur_rsi is None: return None, 0
    # Downtrend + overbought = PUT
    if ema9[-1] < ema21[-1] and cur_rsi > 90:
        return "put", 70
    # Uptrend + oversold = CALL (disabled)
    return None, 0
