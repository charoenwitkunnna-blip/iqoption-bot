"""
EPSILON DIVERGENCE — RSI Price Divergence
==========================================
When price makes higher high but RSI makes lower high = bearish.
When price makes lower low but RSI makes higher low = bullish.
Classic reversal signal with strong statistical edge.
"""
NAME = "epsilon_divergence"

import numpy as np

def rsi_series(data, period=14):
    if len(data) < period+1: return np.array([])
    d = np.diff(data)
    g = np.where(d>0,d,0); l = np.where(d<0,-d,0)
    r = np.zeros(len(data))
    r[period] = 100-(100/(1+np.mean(g[:period])/np.mean(l[:period]))) if np.mean(l[:period])!=0 else 100
    ag=np.mean(g[:period]); al=np.mean(l[:period])
    for i in range(period+1, len(data)):
        ag = (ag*(period-1)+g[i-1])/period
        al = (al*(period-1)+l[i-1])/period
        r[i] = 100-(100/(1+ag/al)) if al!=0 else 100
    return r

def analyze(api, asset, candles, htf_candles=None):
    closes = np.array([c['close'] for c in candles], dtype=float)

    if len(closes) < 25: return None,0

    # RSI series for lookback
    rsi_vals = rsi_series(closes, 10)
    if len(rsi_vals) < 15: return None,0

    # Look back ~5-6 candles for swing points
    lookback = 5

    # Bearish divergence: price HH, RSI LH → PUT
    for i in range(len(closes)-lookback, len(closes)-2):
        window = closes[max(0,i-lookback):i+1]
        peak_idx = np.argmax(window) + max(0,i-lookback)
        if peak_idx < len(rsi_vals):
            price_peak = closes[peak_idx]
            rsi_peak = rsi_vals[peak_idx]

            # Current price near that peak
            if closes[-1] >= price_peak * 0.998:
                # Current RSI lower than peak RSI
                if len(rsi_vals) > 0 and rsi_vals[-1] < rsi_peak - 5:
                    # Also check: current RSI is bearish zone (50-70)
                    if 50 < rsi_vals[-1] < 70:
                        return "put", 65

    # Bullish divergence: price LL, RSI HL → CALL
    for i in range(len(closes)-lookback, len(closes)-2):
        window = closes[max(0,i-lookback):i+1]
        trough_idx = np.argmin(window) + max(0,i-lookback)
        if trough_idx < len(rsi_vals):
            price_trough = closes[trough_idx]
            rsi_trough = rsi_vals[trough_idx]

            if closes[-1] <= price_trough * 1.002:
                if len(rsi_vals) > 0 and rsi_vals[-1] > rsi_trough + 5:
                    if 30 < rsi_vals[-1] < 50:
                        return "call", 65

    return None,0
