"""
SIGMA REVERSION — RSI + Bollinger Band Extreme Reversion
==========================================================
Complement to gamma_breakout: trades mean reversion.
Gamma catches trends, sigma catches bounces.
"""
NAME = "sigma_reversion"

import numpy as np

def rsi(data, period=14):
    if len(data) < period + 1: return None
    d = np.diff(data); g = np.where(d>0,d,0); l = np.where(d<0,-d,0)
    ag = np.mean(g[:period]); al = np.mean(l[:period])
    if al == 0: return 100
    return 100 - (100 / (1 + ag/al))

def bollinger_bands(data, period=20, mult=2.0):
    if len(data) < period: return None,None,None
    window = np.lib.stride_tricks.sliding_window_view(data, period)
    sma = np.mean(window, axis=1)
    std = np.std(window, axis=1)
    return sma + mult*std, sma, sma - mult*std

def adx(highs, lows, closes, period=14):
    n = len(closes)
    if n < period + 1: return None
    tr = np.zeros(n); pdm = np.zeros(n); ndm = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        up = highs[i]-highs[i-1]; down = lows[i-1]-lows[i]
        pdm[i] = up if (up>down and up>0) else 0
        ndm[i] = down if (down>up and down>0) else 0
    ts = np.zeros(n); ps = np.zeros(n); ns = np.zeros(n)
    ts[period]=np.sum(tr[1:period+1]); ps[period]=np.sum(pdm[1:period+1]); ns[period]=np.sum(ndm[1:period+1])
    for i in range(period+1,n):
        ts[i]=ts[i-1]-ts[i-1]/period+tr[i]; ps[i]=ps[i-1]-ps[i-1]/period+pdm[i]; ns[i]=ns[i-1]-ns[i-1]/period+ndm[i]
    pdi=np.zeros(n); ndi=np.zeros(n); dx=np.zeros(n); ax=np.zeros(n)
    for i in range(period+1,n):
        if ts[i]>0: pdi[i]=100*ps[i]/ts[i]; ndi[i]=100*ns[i]/ts[i]
        if pdi[i]+ndi[i]>0: dx[i]=100*abs(pdi[i]-ndi[i])/(pdi[i]+ndi[i])
    ax[period*2]=np.mean(dx[period+1:period*2+1])
    for i in range(period*2+1,n): ax[i]=(ax[i-1]*(period-1)+dx[i])/period
    return ax[-1]

def analyze(api, asset, candles, htf_candles=None):
    closes = np.array([c['close'] for c in candles], dtype=float)
    highs = np.array([c['max'] for c in candles], dtype=float)
    lows = np.array([c['min'] for c in candles], dtype=float)

    if len(closes) < 30: return None, 0

    cur_adx = adx(highs, lows, closes, 14)
    if cur_adx is None or cur_adx >= 25: return None, 0

    upper, mid, lower = bollinger_bands(closes, 20, 2.0)
    if upper is None: return None, 0

    cur_close = closes[-1]
    cur_rsi = rsi(closes, 8)

    dist_low = (cur_close - lower[-1]) / (mid[-1] - lower[-1]) if mid[-1] != lower[-1] else 1
    dist_high = (upper[-1] - cur_close) / (upper[-1] - mid[-1]) if upper[-1] != mid[-1] else 1

    # CALL: near lower band + RSI low + bullish candle
    if dist_low < 0.5 and cur_rsi and cur_rsi < 40:
        if closes[-1] > candles[-1]['open']:
            conf = 55
            if cur_rsi < 30: conf += 10
            return "call", conf

    # PUT: near upper band + RSI high + bearish candle
    if dist_high < 0.5 and cur_rsi and cur_rsi > 60:
        if closes[-1] < candles[-1]['open']:
            conf = 55
            if cur_rsi > 70: conf += 10
            return "put", conf

    return None, 0
