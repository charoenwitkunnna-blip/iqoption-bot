"""
APEX ENSEMBLE — Regime-Switching Super Strategy
================================================
Detects market regime and picks the right sub-strategy:
- TRENDING (ADX >= 25): gamma breakout
- RANGING (ADX < 20): omega momentum (price acceleration)
- TRANSITION (20-25): both must agree (conservative)
"""
NAME = "apex_ensemble"

import numpy as np

# === Sub-strategy: gamma breakout (for trending) ===
def _gamma(closes, highs, lows, atr_vals, cur_adx, cur_rsi, candles):
    n = len(closes)
    donchian_high = np.array([np.max(highs[max(0,i-9):i+1]) for i in range(n)])
    donchian_low = np.array([np.min(lows[max(0,i-9):i+1]) for i in range(n)])

    prev_high = donchian_high[-2]
    prev_low = donchian_low[-2]
    cur_close = closes[-1]
    prev_close = closes[-2]

    # Chop filter
    last3_dir = [closes[i] > closes[i-1] for i in range(-3, 0)]
    if sum(last3_dir) in (1, 2): return None, 0

    # CALL
    if cur_close > prev_high and cur_close > prev_close:
        depth = cur_close - prev_high
        if atr_vals[-1] > 0 and depth < atr_vals[-1] * 0.10: return None, 0
        conf = 50
        if cur_adx > 35: conf += 10
        if cur_rsi and 50 < cur_rsi < 70: conf += 10
        if atr_vals[-1] > atr_vals[-2]: conf += 5
        return "call", conf

    # PUT
    if cur_close < prev_low and cur_close < prev_close:
        depth = prev_low - cur_close
        if atr_vals[-1] > 0 and depth < atr_vals[-1] * 0.10: return None, 0
        conf = 50
        if cur_adx > 35: conf += 10
        if cur_rsi and 30 < cur_rsi < 50: conf += 10
        if atr_vals[-1] > atr_vals[-2]: conf += 5
        return "put", conf

    return None, 0

# === Sub-strategy: omega momentum (for ranging) ===
def _omega(closes, cur_rsi):
    roc3 = ((closes[-1] - closes[-4]) / closes[-4]) * 100 if closes[-4] != 0 else 0
    roc5 = ((closes[-1] - closes[-6]) / closes[-6]) * 100 if closes[-6] != 0 else 0

    accel_up = roc3 > roc5 and roc3 > 0.05
    accel_down = roc3 < roc5 and roc3 < -0.05

    if accel_up and cur_rsi and 45 < cur_rsi < 70:
        if closes[-1] > closes[-2] and closes[-2] > closes[-3]:
            return "call", 55
    if accel_down and cur_rsi and 30 < cur_rsi < 55:
        if closes[-1] < closes[-2] and closes[-2] < closes[-3]:
            return "put", 55
    return None, 0

# === Shared helpers ===
def rsi(data, period=10):
    if len(data) < period+1: return None
    d=np.diff(data); g=np.where(d>0,d,0); l=np.where(d<0,-d,0)
    ag=np.mean(g[:period]); al=np.mean(l[:period])
    if al==0: return 100
    return 100-(100/(1+ag/al))

def adx(highs, lows, closes, period=14):
    n=len(closes)
    if n<period+1: return None
    tr=np.zeros(n); pd=np.zeros(n); nd=np.zeros(n)
    for i in range(1,n):
        tr[i]=max(highs[i]-lows[i],abs(highs[i]-closes[i-1]),abs(lows[i]-closes[i-1]))
        u=highs[i]-highs[i-1]; d=lows[i-1]-lows[i]
        pd[i]=u if(u>d and u>0)else 0; nd[i]=d if(d>u and d>0)else 0
    ts=np.zeros(n); ps=np.zeros(n); ns=np.zeros(n)
    ts[period]=sum(tr[1:period+1]); ps[period]=sum(pd[1:period+1]); ns[period]=sum(nd[1:period+1])
    for i in range(period+1,n):
        ts[i]=ts[i-1]-ts[i-1]/period+tr[i]; ps[i]=ps[i-1]-ps[i-1]/period+pd[i]; ns[i]=ns[i-1]-ns[i-1]/period+nd[i]
    pi=np.zeros(n); ni=np.zeros(n); dx=np.zeros(n); ax=np.zeros(n)
    for i in range(period+1,n):
        if ts[i]>0: pi[i]=100*ps[i]/ts[i]; ni[i]=100*ns[i]/ts[i]
        if pi[i]+ni[i]>0: dx[i]=100*abs(pi[i]-ni[i])/(pi[i]+ni[i])
    ax[period*2]=np.mean(dx[period+1:period*2+1])
    for i in range(period*2+1,n): ax[i]=(ax[i-1]*(period-1)+dx[i])/period
    return ax[-1]

def atr(highs, lows, closes, period=10):
    if len(closes)<period+1: return None
    trs=[max(highs[i]-lows[i],abs(highs[i]-closes[i-1]),abs(lows[i]-closes[i-1])) for i in range(1,len(closes))]
    trs=np.array(trs); av=np.zeros(len(trs)); av[period-1]=np.mean(trs[:period])
    for i in range(period,len(trs)): av[i]=(av[i-1]*(period-1)+trs[i])/period
    return av

def analyze(api, asset, candles, htf_candles=None):
    closes = np.array([c['close'] for c in candles], dtype=float)
    highs = np.array([c['max'] for c in candles], dtype=float)
    lows = np.array([c['min'] for c in candles], dtype=float)

    if len(closes) < 30: return None, 0

    cur_adx = adx(highs, lows, closes, 14)
    if cur_adx is None: return None, 0

    cur_rsi = rsi(closes, 10)
    atr_vals = atr(highs, lows, closes, 10)
    if atr_vals is None: return None, 0

    regime = "TRENDING" if cur_adx >= 25 else ("RANGING" if cur_adx < 20 else "TRANSITION")

    if regime == "TRENDING":
        return _gamma(closes, highs, lows, atr_vals, cur_adx, cur_rsi, candles)
    elif regime == "RANGING":
        return _omega(closes, cur_rsi)
    else:  # TRANSITION: both must agree
        g = _gamma(closes, highs, lows, atr_vals, cur_adx, cur_rsi, candles)
        o = _omega(closes, cur_rsi)
        if g[0] and o[0] and g[0] == o[0]:
            return g[0], (g[1] + o[1]) // 2
        return None, 0
