#!/usr/bin/env python3
"""Parameter optimizer — finds best zeta params from recent candle data."""
import sys, os, time, numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(__file__))

from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD
from iqoptionapi.stable_api import IQ_Option

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

def test_params(closes, highs, lows, rsi_thresh, adx_thresh, recovery=True, chop=True):
    """Test a parameter combo on this candle data. Returns (direction, None) or (None, None)."""
    if len(closes) < 30: return None
    r2 = rsi(closes, 2)
    if r2 is None: return None
    r2p = rsi(closes[:-1], 2) if len(closes) > 31 else None
    e10 = ema(closes, 10)
    if e10 is None: return None
    ax = adx(highs, lows, closes, 14)
    if ax is None or ax < adx_thresh: return None
    if chop and len(closes) >= 5:
        l3 = [closes[i] > closes[i-1] for i in range(-3,0)]
        if sum(l3) in (1,2): return None
    tu = closes[-1] > e10[-1]; td = closes[-1] < e10[-1]
    mu = closes[-1] > closes[-2]; md = closes[-1] < closes[-2]
    if r2 < rsi_thresh and tu and mu:
        if recovery and r2p and r2 <= r2p: return None
        return "call"
    if r2 > (100 - rsi_thresh) and td and md:
        if recovery and r2p and r2 >= r2p: return None
        return "put"
    return None

# Connect
api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
api.connect(); api.change_balance("PRACTICE"); time.sleep(2)

# Get assets
all_a = api.get_all_open_time()
pairs = {x:v for x,v in all_a['turbo'].items() if v['open']}
paying = {}
for a in list(pairs.keys())[:60]:
    try:
        p = api.get_digital_payout(a)
        if p and p>=85: paying[a]=p
    except: pass
assets = sorted(paying, key=paying.get, reverse=True)

# Parameter grid
adx_values = [15, 18, 20, 22, 25]
rsi_values = [10, 12, 15, 18, 20]
recovery_values = [True, False]
chop_values = [True, False]

results = {}
for adx_t in adx_values:
    for rsi_t in rsi_values:
        for rec in recovery_values:
            for chp in chop_values:
                key = (adx_t, rsi_t, rec, chp)
                results[key] = [0, 0]  # w, l

# Test every combo on every asset
for asset in assets:
    try:
        c = api.get_candles(asset, 60, 80, time.time())
        if not c or len(c) < 35: continue
    except: continue
    
    # Walk forward: test on each candle pair
    for offset in range(30, len(c)-2):
        window = c[offset-30:offset+1]
        closes = np.array([x['close'] for x in window], float)
        highs = np.array([x['max'] for x in window], float)
        lows = np.array([x['min'] for x in window], float)
        outcome_close = c[offset+1]['close']
        entry_close = c[offset]['close']
        
        for (adx_t, rsi_t, rec, chp), score in results.items():
            d = test_params(closes, highs, lows, rsi_t, adx_t, rec, chp)
            if d is None: continue
            win = (outcome_close > entry_close) if d == 'call' else (outcome_close < entry_close)
            if win: score[0] += 1
            else: score[1] += 1
    time.sleep(0.3)

# Rank by WR (min 10 signals)
ranked = [(k, v[0], v[1]) for k, v in results.items() if v[0]+v[1] >= 10]
ranked.sort(key=lambda x: x[1]/(x[1]+x[2]), reverse=True)

print(f"{'ADX':>4s} {'RSI':>4s} {'Rec':>4s} {'Chop':>5s} {'W':>5s} {'L':>5s} {'WR':>6s}")
print("-" * 40)
for (adx_t, rsi_t, rec, chp), w, l in ranked[:10]:
    t = w+l; wr = w/t*100
    print(f"{adx_t:>4d} {rsi_t:>4d} {str(rec):>4s} {str(chp):>5s} {w:>5d} {l:>5d} {wr:>5.0f}%")

# Best overall
if ranked:
    best = ranked[0]
    print(f"\nBest: ADX={best[0][0]}, RSI<{best[0][1]}, recovery={best[0][2]}, chop={best[0][3]}")
    print(f"Score: {best[1]}/{best[1]+best[2]} = {best[1]/(best[1]+best[2])*100:.0f}%")
