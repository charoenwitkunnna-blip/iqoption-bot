"""
LAMBDA — CALL-Only Super Filtered
==================================
Data shows CALLS win 52% vs PUTS 44% today.
Only take CALLS when ALL conditions align.
Few signals, high accuracy.
"""
NAME = "lambda_call"

import numpy as np
import time as _time

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

    # 1. RSI(2) deep oversold
    rsi2 = rsi(closes, 2)
    if rsi2 is None or rsi2 >= 8: return None,0

    # 2. Multi-RSI: RSI(6) and RSI(14) also confirm upward momentum
    rsi6 = rsi(closes, 6)
    rsi14 = rsi(closes, 14)
    if rsi6 is None or rsi14 is None: return None,0
    if rsi6 >= 55 or rsi14 >= 55: return None,0  # Not truly oversold on higher TF

    # 3. EMA trend up
    e10 = ema(closes, 10)
    e20 = ema(closes, 20)
    if e10 is None or e20 is None: return None,0
    if closes[-1] < e10[-1] or e10[-1] < e20[-1]: return None,0  # Double EMA confirm

    # 4. ADX: must be trending
    cur_adx = adx(highs, lows, closes, 14)
    if cur_adx is None or cur_adx < 20: return None,0

    # 5. HTF confirm: 5-min candle bullish
    if htf_candles and len(htf_candles) >= 2:
        if htf_candles[-1]['close'] < htf_candles[-1]['open']: return None,0

    # 6. Chop filter
    if len(closes) >= 5:
        last3 = [closes[i] > closes[i-1] for i in range(-3,0)]
        if sum(last3) in (1,2): return None,0

    # 7. Current candle is turning up
    if closes[-1] < closes[-2]: return None,0
    if candles[-1]['close'] < candles[-1]['open']: return None,0

    return "call", 75
