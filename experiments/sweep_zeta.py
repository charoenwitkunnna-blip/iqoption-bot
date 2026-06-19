#!/usr/bin/env python3
"""Parameter sweep for zeta on 3-min expiry. Tests multiple RSI/ADX combos."""
import sys, os, time, importlib, warnings, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(__file__))
from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD
from iqoptionapi.stable_api import IQ_Option
warnings.filterwarnings("ignore")

# Helpers (copied for standalone)
def rsi_val(data, period=2):
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

def adx_val(highs, lows, closes, period=14):
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

def test_combo(closes, highs, lows, rsi_thresh, adx_thresh, ema_period, chop_on):
    if len(closes) < 20: return None
    r2 = rsi_val(closes, 2)
    if r2 is None: return None
    e = ema(closes, ema_period)
    if e is None: return None
    ax = adx_val(highs, lows, closes, 14)
    if ax is None or ax < adx_thresh: return None

    if chop_on:
        if len(closes) >= 5:
            l3 = [closes[i] > closes[i-1] for i in range(-3,0)]
            if sum(l3) in (1,2): return None

    t_up = closes[-1] > e[-1]
    t_down = closes[-1] < e[-1]
    m_up = closes[-1] > closes[-2]
    m_down = closes[-1] < closes[-2]

    if r2 < rsi_thresh and t_up and m_up: return "call"
    if r2 > (100 - rsi_thresh) and t_down and m_down: return "put"
    return None

# Connect
api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
api.connect(); api.change_balance("PRACTICE"); time.sleep(2)

all_a = api.get_all_open_time()
pairs = {x:v for x,v in all_a['turbo'].items() if v['open']}
paying = {a:p for a in list(pairs.keys()) for _ in [None] if False}
paying = {}
for a in list(pairs.keys()):
    try:
        p = api.get_digital_payout(a)
        if p and p>=85: paying[a]=p
    except: pass
assets = sorted(paying, key=paying.get, reverse=True)  # All assets

# Test combos
combos = []
for rsi_t in [10, 15, 20, 25]:
    for adx_t in [15, 18, 20, 22]:
        for ema_p in [10, 15]:
            for chop in [True, False]:
                combos.append((rsi_t, adx_t, ema_p, chop))

results = {c: [0,0] for c in combos}

for asset in assets:
    try:
        c = api.get_candles(asset, 60, 60, time.time())
        if not c or len(c) < 35: continue
    except: continue

    closes = np.array([x['close'] for x in c[:-1]], float)
    highs = np.array([x['max'] for x in c[:-1]], float)
    lows = np.array([x['min'] for x in c[:-1]], float)
    eo = c[-2]['close']; oc = c[-1]['close']

    for combo in combos:
        rsi_t, adx_t, ema_p, chop = combo
        d = test_combo(closes, highs, lows, rsi_t, adx_t, ema_p, chop)
        if d is None: continue
        win = (oc > eo) if d == 'call' else (oc < eo)
        if win: results[combo][0] += 1
        else: results[combo][1] += 1
    time.sleep(0.05)

# Top 10 by WR (min 5 signals)
ranked = [(c, r[0], r[1]) for c, r in results.items() if r[0]+r[1] >= 2]
ranked.sort(key=lambda x: x[1]/(x[1]+x[2]), reverse=True)

print(f"{'RSI':>4s} {'ADX':>4s} {'EMA':>4s} {'Chop':>5s} {'W':>3s} {'L':>3s} {'Sig':>4s} {'WR':>6s}")
print("-"*42)
for c, w, l in ranked[:12]:
    rsi_t, adx_t, ema_p, chop = c
    t = w+l; wr = w/t*100
    print(f"{rsi_t:>4d} {adx_t:>4d} {ema_p:>4d} {str(chop):>5s} {w:>3d} {l:>3d} {t:>4d} {wr:>5.0f}%")
