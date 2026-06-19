"""
NU VOLATILITY — ATR Spike Momentum
====================================
When ATR suddenly spikes (volatility explosion),
bet on the direction of the explosion.
No RSI, no trend — just pure volatility momentum.
"""
NAME = "nu_volatility"

import numpy as np

def atr(highs, lows, closes, period=5):
    if len(closes) < period+1: return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        trs.append(tr)
    trs = np.array(trs)
    av = np.zeros(len(trs))
    av[period-1] = np.mean(trs[:period])
    for i in range(period, len(trs)):
        av[i] = (av[i-1]*(period-1)+trs[i])/period
    return av

def analyze(api, asset, candles, htf_candles=None):
    closes = np.array([c['close'] for c in candles], dtype=float)
    highs = np.array([c['max'] for c in candles], dtype=float)
    lows = np.array([c['min'] for c in candles], dtype=float)

    if len(closes) < 15: return None,0

    av = atr(highs, lows, closes, 5)
    if av is None or len(av) < 4: return None,0

    # ATR spike: current ATR > 1.8x average of last 4 ATRs
    avg_atr = np.mean(av[-5:-1])
    cur_atr = av[-1]
    atr_spike = avg_atr > 0 and cur_atr > avg_atr * 1.8

    if not atr_spike: return None,0

    # Direction: current candle body direction
    cur_body = closes[-1] - candles[-1]['open']
    prev_body = closes[-2] - candles[-2]['open']

    # Body must be > 50% of total range (real conviction)
    total_range = highs[-1] - lows[-1]
    if total_range > 0 and abs(cur_body) / total_range < 0.5: return None,0

    # Body must be 2x+ average body
    avg_body = np.mean([abs(closes[i]-candles[i]['open']) for i in range(-7, -1)])
    if avg_body > 0 and abs(cur_body) < avg_body * 1.5: return None,0

    if cur_body > 0 and prev_body > 0:
        return "call", 65
    if cur_body < 0 and prev_body < 0:
        return "put", 65

    return None,0
