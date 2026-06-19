"""
ZETA HEIKIN-ASHI — Smoothed Candle Reversal Patterns
=====================================================
Heikin-Ashi candles filter noise. Look for:
- Doji → trend weakness → reversal
- HA color change after trend = reversal signal
- Shadow-less candles = strong momentum
"""
NAME = "zeta_heikinashi"

import numpy as np

def heikin_ashi(opens, highs, lows, closes):
    """Compute Heikin-Ashi candles"""
    n = len(closes)
    ha_open = np.zeros(n)
    ha_close = np.zeros(n)
    ha_high = np.zeros(n)
    ha_low = np.zeros(n)

    ha_open[0] = opens[0]
    ha_close[0] = (opens[0] + closes[0] + highs[0] + lows[0]) / 4

    for i in range(1, n):
        ha_open[i] = (ha_open[i-1] + ha_close[i-1]) / 2
        ha_close[i] = (opens[i] + closes[i] + highs[i] + lows[i]) / 4
        ha_high[i] = max(highs[i], ha_open[i], ha_close[i])
        ha_low[i] = min(lows[i], ha_open[i], ha_close[i])

    return ha_open, ha_close, ha_high, ha_low

def ema(data, period):
    if len(data) < period: return None
    a = 2.0/(period+1.0)
    r = np.zeros(len(data)); r[0]=data[0]
    for i in range(1,len(data)): r[i]=a*data[i]+(1-a)*r[i-1]
    return r

def analyze(api, asset, candles, htf_candles=None):
    opens = np.array([c['open'] for c in candles], dtype=float)
    closes = np.array([c['close'] for c in candles], dtype=float)
    highs = np.array([c['max'] for c in candles], dtype=float)
    lows = np.array([c['min'] for c in candles], dtype=float)

    if len(closes) < 15: return None,0

    # Heikin-Ashi
    ha_o, ha_c, ha_h, ha_l = heikin_ashi(opens, highs, lows, closes)

    # Body sizes
    ha_body = np.abs(ha_c - ha_o)
    ha_upper_shadow = ha_h - np.maximum(ha_o, ha_c)
    ha_lower_shadow = np.minimum(ha_o, ha_c) - ha_l
    ha_color = ha_c >= ha_o  # True = green/bullish

    # Trend: EMA of HA close
    ha_ema = ema(ha_c, 10)
    if ha_ema is None: return None,0
    trend_up = ha_c[-1] > ha_ema[-1]
    trend_down = ha_c[-1] < ha_ema[-1]

    # === SIGNAL 1: HA Doji in trend → reversal ===
    avg_body = np.mean(ha_body[-10:])
    is_doji = ha_body[-1] < avg_body * 0.3

    if is_doji and ha_body[-1] > 0:
        # Doji after uptrend = bearish reversal
        if trend_up and ha_color[-1] == False:
            return "put", 60
        # Doji after downtrend = bullish reversal
        if trend_down and ha_color[-1] == True:
            return "call", 60

    # === SIGNAL 2: HA Color Change with strong candle ===
    color_changed = ha_color[-1] != ha_color[-2]
    strong_candle = ha_body[-1] > avg_body * 1.5

    if color_changed and strong_candle:
        if ha_color[-1] == True and ha_lower_shadow[-1] < ha_body[-1] * 0.2:
            # Strong green with no lower wick
            return "call", 70
        if ha_color[-1] == False and ha_upper_shadow[-1] < ha_body[-1] * 0.2:
            # Strong red with no upper wick
            return "put", 70

    # === SIGNAL 3: 3+ same color then reversal candle ===
    if len(ha_color) >= 4:
        last3 = ha_color[-4:-1]
        if np.all(last3) and ha_color[-1] == False:
            # 3 green then red = reversal
            return "put", 55
        if np.all(~last3) and ha_color[-1] == True:
            # 3 red then green = reversal
            return "call", 55

    return None,0
