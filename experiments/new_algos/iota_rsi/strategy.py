"""
IOTA RSI — Enter on Recovery, Not Extreme
===========================================
Classic RSI-2 improvement: wait for RSI to cross back
from extreme zone. Enters after the reversal starts,
not at the bottom/top. Higher accuracy.
"""
NAME = "iota_rsi"

import numpy as np

def rsi_series(data, period=2):
    if len(data) < period+1: return None
    d=np.diff(data); g=np.where(d>0,d,0); l=np.where(d<0,-d,0)
    r=np.zeros(len(data))
    al=np.mean(l[:period]) if period<len(l) else 0
    ag=np.mean(g[:period]) if period<len(g) else 0
    for i in range(period, len(data)):
        ag=(ag*(period-1)+g[i-1])/period
        al=(al*(period-1)+l[i-1])/period
        r[i]=100-(100/(1+ag/al)) if al!=0 else 100
    return r

def ema(data, period):
    if len(data) < period: return None
    a=2.0/(period+1.0); r=np.zeros(len(data)); r[0]=data[0]
    for i in range(1,len(data)): r[i]=a*data[i]+(1-a)*r[i-1]
    return r

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

def analyze(api, asset, candles, htf_candles=None):
    closes = np.array([c['close'] for c in candles], dtype=float)
    highs = np.array([c['max'] for c in candles], dtype=float)
    lows = np.array([c['min'] for c in candles], dtype=float)

    if len(closes) < 15: return None,0

    r2 = rsi_series(closes, 2)
    if r2 is None or len(r2) < 5: return None,0

    e10 = ema(closes, 10)
    if e10 is None: return None,0

    cur_adx = adx(highs, lows, closes, 14)
    if cur_adx is None or cur_adx < 18: return None,0

    # CALL: RSI was below 10, now crossed above 30 (recovery started)
    was_oversold = any(r2[i] < 10 for i in range(-5, -1))
    recovery_up = r2[-1] > 30 and r2[-2] < 30
    trend_up = closes[-1] > e10[-1]

    if was_oversold and recovery_up and trend_up and closes[-1] > closes[-2]:
        return "call", 70

    # PUT: RSI was above 90, now crossed below 70 (recovery started)
    was_overbought = any(r2[i] > 90 for i in range(-5, -1))
    recovery_down = r2[-1] < 70 and r2[-2] > 70
    trend_down = closes[-1] < e10[-1]

    if was_overbought and recovery_down and trend_down and closes[-1] < closes[-2]:
        return "put", 70

    return None,0
