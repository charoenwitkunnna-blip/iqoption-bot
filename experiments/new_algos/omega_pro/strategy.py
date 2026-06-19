"""
OMEGA PRO — Strong Price Acceleration
======================================
Tighter version: only strong, sustained acceleration.
ROC must be meaningful, bodies must grow, trend must confirm.
"""
NAME = "omega_pro"

import numpy as np

def rsi(data, period=10):
    if len(data) < period+1: return None
    d=np.diff(data); g=np.where(d>0,d,0); l=np.where(d<0,-d,0)
    ag=np.mean(g[:period]); al=np.mean(l[:period])
    if al==0: return 100
    return 100-(100/(1+ag/al))

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

    if len(closes) < 20: return None,0

    # Rate of Change
    roc5 = ((closes[-1] - closes[-6]) / closes[-6]) * 100 if closes[-6]!=0 else 0
    roc3 = ((closes[-1] - closes[-4]) / closes[-4]) * 100 if closes[-4]!=0 else 0

    # Stronger: ROC(3) must be at least 2x ROC(5) (real acceleration)
    strong_accel_up = roc3 > 0.08 and roc3 > roc5 * 1.5
    strong_accel_down = roc3 < -0.08 and roc3 < roc5 * 1.5

    cur_rsi = rsi(closes, 10)
    cur_adx = adx(highs, lows, closes, 14)
    if cur_adx is None or cur_adx < 20: return None,0

    # Bodies must be growing (acceleration)
    bodies = [abs(closes[i] - candles[i]['open']) for i in range(-4, 0)]
    bodies_growing = len(bodies) >= 3 and bodies[-1] > bodies[-2] > bodies[-3]

    # Call: strong acceleration up + growing bodies + RSI momentum
    if strong_accel_up and cur_rsi and 50 < cur_rsi < 68:
        if closes[-1] > closes[-2] and closes[-2] > closes[-3]:
            conf = 60
            if bodies_growing: conf += 10
            if cur_adx > 25: conf += 5
            return "call", conf

    # Put: strong acceleration down + growing bodies + RSI momentum
    if strong_accel_down and cur_rsi and 32 < cur_rsi < 50:
        if closes[-1] < closes[-2] and closes[-2] < closes[-3]:
            conf = 60
            if bodies_growing: conf += 10
            if cur_adx > 25: conf += 5
            return "put", conf

    return None,0
