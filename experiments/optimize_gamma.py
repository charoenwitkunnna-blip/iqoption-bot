#!/usr/bin/env python3
"""Parameter optimizer for GAMMA breakout — finds best ADX/depth/pressure params."""
import sys, os, time, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(__file__))

from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD
from iqoptionapi.stable_api import IQ_Option

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

def test_gamma(closes, highs, lows, candles, adx_t, depth_pct, pressure_pct):
    """Test gamma params. Returns direction or None."""
    if len(closes) < 30: return None
    ax = adx(highs, lows, closes, 14)
    if ax is None or ax < adx_t: return None
    
    dh = np.array([np.max(highs[max(0,i-9):i+1]) for i in range(len(highs))])
    dl = np.array([np.min(lows[max(0,i-9):i+1]) for i in range(len(lows))])
    av = atr(highs, lows, closes, 10)
    if av is None: return None
    
    ph = dh[-2]; pl = dl[-2]; cc = closes[-1]; pc = closes[-2]
    
    # Chop
    if len(closes) >= 5:
        l3 = [closes[i] > closes[i-1] for i in range(-3,0)]
        if sum(l3) in (1,2): return None
    
    # CALL
    if cc > ph and cc > pc:
        cr = ph - pl
        if cr > 0 and pc < (ph - cr * pressure_pct): return None  # Pressure
        bd = cc - ph
        if av[-1] > 0 and bd < av[-1] * depth_pct: return None  # Depth
        if highs[-1] <= highs[-2]: return None  # Range extension
        crsi = rsi(closes, 10)
        if crsi is None or crsi < 50 or crsi > 65: return None
        return "call"
    
    # PUT
    if cc < pl and cc < pc:
        cr = ph - pl
        if cr > 0 and pc > (pl + cr * pressure_pct): return None
        bd = pl - cc
        if av[-1] > 0 and bd < av[-1] * depth_pct: return None
        if lows[-1] >= lows[-2]: return None
        crsi = rsi(closes, 10)
        if crsi is None or crsi < 35 or crsi > 50: return None
        return "put"
    
    return None

api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
api.connect(); api.change_balance("PRACTICE"); time.sleep(2)

all_a = api.get_all_open_time()
pairs = {x:v for x,v in all_a['turbo'].items() if v['open']}
paying = {}
for a in list(pairs.keys())[:60]:
    try:
        p = api.get_digital_payout(a)
        if p and p>=85: paying[a]=p
    except: pass
assets = sorted(paying, key=paying.get, reverse=True)

adx_vals = [20, 22, 25, 28, 30]
depth_pcts = [0.05, 0.10, 0.15, 0.20]
pressure_pcts = [0.15, 0.20, 0.25, 0.30]

results = {}
for at in adx_vals:
    for dp in depth_pcts:
        for pp in pressure_pcts:
            results[(at, dp, pp)] = [0, 0]

for asset in assets:
    try:
        c = api.get_candles(asset, 60, 80, time.time())
        if not c or len(c) < 35: continue
    except: continue
    
    for offset in range(30, len(c)-2):
        window = c[offset-30:offset+1]
        closes = np.array([x['close'] for x in window], float)
        highs = np.array([x['max'] for x in window], float)
        lows = np.array([x['min'] for x in window], float)
        oc = c[offset+1]['close']; eo = c[offset]['close']
        
        for (at, dp, pp), score in results.items():
            d = test_gamma(closes, highs, lows, window, at, dp, pp)
            if d is None: continue
            win = (oc > eo) if d == 'call' else (oc < eo)
            if win: score[0] += 1
            else: score[1] += 1
    time.sleep(0.3)

ranked = [(k, v[0], v[1]) for k, v in results.items() if v[0]+v[1] >= 5]
ranked.sort(key=lambda x: x[1]/(x[1]+x[2]), reverse=True)

print(f"{'ADX':>4s} {'Depth':>6s} {'Press':>6s} {'W':>5s} {'L':>5s} {'WR':>6s}")
print("-" * 40)
for (at, dp, pp), w, l in ranked[:10]:
    t = w+l; wr = w/t*100
    print(f"{at:>4d} {dp:>5.0%} {pp:>5.0%} {w:>5d} {l:>5d} {wr:>5.0f}%")

if ranked:
    best = ranked[0]
    print(f"\nBest: ADX={best[0][0]}, Depth={best[0][1]:.0%}, Pressure={best[0][2]:.0%}")
    print(f"Score: {best[1]}/{best[1]+best[2]} = {best[1]/(best[1]+best[2])*100:.0f}%")
