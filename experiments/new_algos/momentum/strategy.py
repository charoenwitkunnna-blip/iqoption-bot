NAME = "momentum"
import numpy as np

def adx(highs, lows, closes, period=14):
    n = len(closes)
    if n < period + 1: return None
    tr = np.zeros(n)
    pd = np.zeros(n)
    nd = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        u = highs[i] - highs[i-1]
        d = lows[i-1] - lows[i]
        pd[i] = u if (u > d and u > 0) else 0
        nd[i] = d if (d > u and d > 0) else 0
    ts = np.zeros(n)
    ps = np.zeros(n)
    ns = np.zeros(n)
    ts[period] = sum(tr[1:period + 1])
    ps[period] = sum(pd[1:period + 1])
    ns[period] = sum(nd[1:period + 1])
    for i in range(period + 1, n):
        ts[i] = ts[i-1] - ts[i-1] / period + tr[i]
        ps[i] = ps[i-1] - ps[i-1] / period + pd[i]
        ns[i] = ns[i-1] - ns[i-1] / period + nd[i]
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
    return ax[-1]

def analyze(api, asset, candles, htf_candles=None):
    closes = np.array([c['close'] for c in candles], dtype=float)
    highs = np.array([c['max'] for c in candles], dtype=float)
    lows = np.array([c['min'] for c in candles], dtype=float)
    opens = np.array([c['open'] for c in candles], dtype=float)
    if len(closes) < 10: return None, 0
    cur_adx = adx(highs, lows, closes, 14)
    if cur_adx is None or cur_adx >= 30: return None, 0
    # Check last 3 candles
    bodies = [closes[i] - opens[i] for i in range(-3, 0)]
    sizes = [abs(b) for b in bodies]
    # 3 bearish = PUT (continuation)
    if all(b < 0 for b in bodies):
        if sizes[-1] > sizes[-2] > sizes[-3]:
            return "put", 70
        return "put", 60
    return None, 0
