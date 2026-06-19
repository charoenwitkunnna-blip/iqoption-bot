"""
THETA RSI-2 — Larry Connors 2-Period RSI
==========================================
Classic mean reversion: RSI(2) < 5 → CALL, RSI(2) > 95 → PUT
Only in trending markets (ADX >= 20) with trend alignment.
"""
NAME = "theta_rsi2"

import numpy as np

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

def analyze(api, asset, candles, htf_candles=None):
    closes = np.array([c['close'] for c in candles], dtype=float)
    if len(closes) < 20: return None,0

    # RSI(2)
    rsi2 = rsi(closes, 2)
    if rsi2 is None: return None,0

    # Trend: EMA(20)
    e20 = ema(closes, 20)
    if e20 is None: return None,0
    trend_up = closes[-1] > e20[-1]
    trend_down = closes[-1] < e20[-1]

    # RSI(2) extreme + trend alignment
    if rsi2 < 8 and trend_up:
        # Oversold in uptrend = buy the dip
        if closes[-1] > closes[-2]:  # Confirmation candle
            return "call", 70

    if rsi2 > 92 and trend_down:
        # Overbought in downtrend = sell the rip
        if closes[-1] < closes[-2]:
            return "put", 70

    return None,0
