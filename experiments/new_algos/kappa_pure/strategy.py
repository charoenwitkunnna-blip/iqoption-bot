"""
KAPPA PURE — RSI(2) Cross Only
===============================
Ultra-simple: RSI(2) crosses above 25 → CALL
RSI(2) crosses below 75 → PUT
No trend, no ADX, no chop. Just the cross.
"""
NAME = "kappa_pure"

import numpy as np

def rsi(data, period=2):
    if len(data) < period+1: return None
    d=np.diff(data); g=np.where(d>0,d,0); l=np.where(d<0,-d,0)
    ag=np.mean(g[:period]); al=np.mean(l[:period])
    if al==0: return 100
    return 100-(100/(1+ag/al))

def analyze(api, asset, candles, htf_candles=None):
    closes = np.array([c['close'] for c in candles], dtype=float)
    if len(closes) < 10: return None,0

    rsi_now = rsi(closes, 2)
    rsi_prev = rsi(closes[:-1], 2) if len(closes) > 10 else None
    if rsi_now is None: return None,0

    # CALL: RSI crosses up through 25
    if rsi_prev is not None and rsi_prev < 25 and rsi_now >= 25:
        return "call", 55

    # PUT: RSI crosses down through 75
    if rsi_prev is not None and rsi_prev > 75 and rsi_now <= 75:
        return "put", 55

    return None,0
