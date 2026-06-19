"""
PI ENSEMBLE — Zeta + Theta HTF Confluence
===========================================
Only trades when BOTH zeta_hybrid AND theta_htf agree.
Two independent strategies confirming = ultra-high confidence.
"""
NAME = "pi_ensemble"

import numpy as np

# === Zeta logic ===
def rsi(data, period=2):
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

    # === ZETA signal ===
    rsi2 = rsi(closes, 2)
    rsi2_prev = rsi(closes[:-1], 2) if len(closes) > 26 else None
    if rsi2 is None: zeta_dir = None
    else:
        e10 = ema(closes, 10)
        ax = adx(highs, lows, closes, 14)
        if e10 is None or ax is None or ax < 22:
            zeta_dir = None
        else:
            if len(closes)>=5:
                l3=[closes[i]>closes[i-1] for i in range(-3,0)]
                if sum(l3) in (1,2): zeta_dir = None
            tu=closes[-1]>e10[-1]; td=closes[-1]<e10[-1]
            mu=closes[-1]>closes[-2]; md=closes[-1]<closes[-2]
            if rsi2<15 and tu and mu and (rsi2_prev is None or rsi2>rsi2_prev):
                zeta_dir = "call"
            elif rsi2>85 and td and md and (rsi2_prev is None or rsi2<rsi2_prev):
                zeta_dir = "put"
            else:
                zeta_dir = None

    if zeta_dir is None: return None,0

    # === HTF signal (from 5-min candle) ===
    htf_dir = None
    if htf_candles and len(htf_candles) >= 2:
        htf_close = htf_candles[-1]['close']
        htf_open = htf_candles[-1]['open']
        if htf_close > htf_open: htf_dir = "call"
        elif htf_close < htf_open: htf_dir = "put"

    # Both must agree
    if zeta_dir and htf_dir and zeta_dir == htf_dir:
        return zeta_dir, 75

    return None,0
