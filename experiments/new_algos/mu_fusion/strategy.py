"""
MU FUSION — RSI-2 + Price Acceleration Confluence
===================================================
Only trades when theta_pro AND omega_pro agree.
Two independent signals confirming = highest confidence.
"""
NAME = "mu_fusion"

import numpy as np

def rsi(data, period):
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

    if len(closes) < 25: return None,0

    cur_adx = adx(highs, lows, closes, 14)
    if cur_adx is None or cur_adx < 20: return None,0

    # === Theta check: RSI(2) extreme ===
    rsi2 = rsi(closes, 2)
    e20 = ema(closes, 20)
    if rsi2 is None or e20 is None: return None,0

    theta_call = (rsi2 < 8 and closes[-1] > e20[-1] and closes[-1] > closes[-2])
    theta_put = (rsi2 > 92 and closes[-1] < e20[-1] and closes[-1] < closes[-2])

    # === Omega check: price acceleration ===
    roc5 = ((closes[-1]-closes[-6])/closes[-6])*100 if closes[-6]!=0 else 0
    roc3 = ((closes[-1]-closes[-4])/closes[-4])*100 if closes[-4]!=0 else 0
    cur_rsi = rsi(closes, 10)

    omega_call = (roc3 > 0.08 and roc3 > roc5*1.5 and cur_rsi and 50<cur_rsi<68
                  and closes[-1]>closes[-2] and closes[-2]>closes[-3])
    omega_put = (roc3 < -0.08 and roc3 < roc5*1.5 and cur_rsi and 32<cur_rsi<50
                 and closes[-1]<closes[-2] and closes[-2]<closes[-3])

    # === Confluence: both must agree ===
    if theta_call and omega_call:
        return "call", 75
    if theta_put and omega_put:
        return "put", 75

    return None,0
