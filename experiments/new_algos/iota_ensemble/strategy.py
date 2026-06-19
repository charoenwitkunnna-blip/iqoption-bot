"""
IOTA ENSEMBLE — Majority Vote Across 6 Strategies
===================================================
Only trades when 3+ sub-strategies agree on direction.
Quality over quantity — fewer signals, higher accuracy.
"""
NAME = "iota_ensemble"

import numpy as np

# === Copy all 6 strategy cores (inlined for speed) ===

def rsi(data, period):
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

def ema(data, period):
    if len(data) < period: return None
    a=2.0/(period+1.0); r=np.zeros(len(data)); r[0]=data[0]
    for i in range(1,len(data)): r[i]=a*data[i]+(1-a)*r[i-1]
    return r

def bollinger(data, period=20, mult=2.0):
    if len(data) < period: return None,None,None
    window = np.lib.stride_tricks.sliding_window_view(data, period)
    sma=np.mean(window,axis=1); std=np.std(window,axis=1)
    return sma+mult*std, sma, sma-mult*std

def atr(highs, lows, closes, period=10):
    if len(closes)<period+1: return None
    trs=[max(highs[i]-lows[i],abs(highs[i]-closes[i-1]),abs(lows[i]-closes[i-1])) for i in range(1,len(closes))]
    trs=np.array(trs); av=np.zeros(len(trs)); av[period-1]=np.mean(trs[:period])
    for i in range(period,len(trs)): av[i]=(av[i-1]*(period-1)+trs[i])/period
    return av

# --- Sub-strategies ---

def _gamma(closes, highs, lows):
    if len(closes) < 30: return None
    cur_adx = adx(highs, lows, closes, 14)
    if cur_adx is None or cur_adx < 20: return None
    dh = np.array([np.max(highs[max(0,i-9):i+1]) for i in range(len(highs))])
    dl = np.array([np.min(lows[max(0,i-9):i+1]) for i in range(len(lows))])
    av = atr(highs, lows, closes, 10)
    if av is None: return None
    if closes[-1] > dh[-2] and closes[-1] > closes[-2]:
        if av[-1] > 0 and (closes[-1]-dh[-2]) >= av[-1]*0.10: return "call"
    if closes[-1] < dl[-2] and closes[-1] < closes[-2]:
        if av[-1] > 0 and (dl[-2]-closes[-1]) >= av[-1]*0.10: return "put"
    return None

def _omega(closes, highs, lows):
    if len(closes) < 20: return None
    roc3 = ((closes[-1]-closes[-4])/closes[-4])*100 if closes[-4]!=0 else 0
    roc5 = ((closes[-1]-closes[-6])/closes[-6])*100 if closes[-6]!=0 else 0
    cr = rsi(closes, 10)
    if roc3>roc5 and roc3>0.05 and cr and 45<cr<70:
        if closes[-1]>closes[-2] and closes[-2]>closes[-3]: return "call"
    if roc3<roc5 and roc3<-0.05 and cr and 30<cr<55:
        if closes[-1]<closes[-2] and closes[-2]<closes[-3]: return "put"
    return None

def _theta(closes, highs, lows):
    if len(closes) < 25: return None
    r2 = rsi(closes, 2); e20 = ema(closes, 20); ca = adx(highs,lows,closes,14)
    if r2 is None or e20 is None or ca is None or ca < 18: return None
    if r2 < 15 and closes[-1] > e20[-1] and closes[-1] > closes[-2]: return "call"
    if r2 > 85 and closes[-1] < e20[-1] and closes[-1] < closes[-2]: return "put"
    return None

def _eta(closes, highs, lows):
    if len(closes) < 6: return None
    ups = [closes[i] > candles_raw[i] for i in range(-5,0)]
    if all(ups[-4:]) and ups[-1] and len(ups)>=5: return "call"
    if not any(ups[-4:]) and not ups[-1] and len(ups)>=5: return "put"
    return None

def _sigma(closes, highs, lows):
    if len(closes) < 30: return None
    ca = adx(highs,lows,closes,14)
    if ca is None or ca >= 25: return None
    upper, mid, lower = bollinger(closes)
    if upper is None: return None
    cr = rsi(closes, 8)
    dl = (closes[-1]-lower[-1])/(mid[-1]-lower[-1]) if mid[-1]!=lower[-1] else 1
    du = (upper[-1]-closes[-1])/(upper[-1]-mid[-1]) if upper[-1]!=mid[-1] else 1
    if dl < 0.5 and cr and cr < 40 and closes[-1] > candles_raw[-1]: return "call"
    if du < 0.5 and cr and cr > 60 and closes[-1] < candles_raw[-1]: return "put"
    return None

def _zeta(closes, highs, lows):
    if len(closes) < 25: return None
    r2 = rsi(closes, 2); e10 = ema(closes, 10); ca = adx(highs,lows,closes,14)
    if r2 is None or e10 is None or ca is None or ca < 18: return None
    if r2 < 15 and closes[-1] > e10[-1] and closes[-1] > closes[-2]: return "call"
    if r2 > 85 and closes[-1] < e10[-1] and closes[-1] < closes[-2]: return "put"
    return None

# Global to pass candles to _eta
candles_raw = []

def analyze(api, asset, candles, htf_candles=None):
    global candles_raw
    candles_raw = [c['open'] for c in candles]

    closes = np.array([c['close'] for c in candles], dtype=float)
    highs = np.array([c['max'] for c in candles], dtype=float)
    lows = np.array([c['min'] for c in candles], dtype=float)

    if len(closes) < 30: return None, 0

    # Get votes from all 6 strategies
    votes = []
    for name, fn in [("gamma",_gamma),("omega",_omega),("theta",_theta),
                      ("eta",_eta),("sigma",_sigma),("zeta",_zeta)]:
        try:
            d = fn(closes, highs, lows)
            if d: votes.append(d)
        except: pass

    calls = votes.count("call")
    puts = votes.count("put")

    # Need 3+ votes and a clear majority
    if calls >= 3 and calls > puts:
        return "call", 50 + calls * 5
    if puts >= 3 and puts > calls:
        return "put", 50 + puts * 5

    return None, 0
