"""
BETA REVERSAL — Bollinger Band Mean Reversion
===============================================
Price closes outside BB(20,2), RSI confirms extreme.
Enter when price reverses back inside band.
"""
NAME = "beta_reversal"

import numpy as np

def ema(data, period):
    if len(data) < period:
        return None
    alpha = 2.0 / (period + 1.0)
    result = np.zeros(len(data))
    result[0] = data[0]
    for i in range(1, len(data)):
        result[i] = alpha * data[i] + (1 - alpha) * result[i-1]
    return result

def rsi(data, period=14):
    if len(data) < period + 1:
        return None
    deltas = np.diff(data)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    if avg_loss == 0:
        return 100
    return 100 - (100 / (1 + avg_gain / avg_loss))

def bollinger_bands(data, period=20, std_mult=2.0):
    if len(data) < period:
        return None, None, None
    sma = np.convolve(data, np.ones(period)/period, mode='valid')
    std = np.array([np.std(data[i-period+1:i+1]) for i in range(period-1, len(data))])
    upper = sma + std_mult * std
    lower = sma - std_mult * std
    return upper, sma, lower

def analyze(api, asset, candles, htf_candles=None):
    closes = np.array([c['close'] for c in candles], dtype=float)
    highs = np.array([c['max'] for c in candles], dtype=float)
    lows = np.array([c['min'] for c in candles], dtype=float)

    if len(closes) < 25:
        return None, 0

    # Bollinger Bands (period=20, std=2)
    upper, mid, lower = bollinger_bands(closes, 20, 2.0)
    if upper is None:
        return None, 0

    prev_close = closes[-2]
    cur_close = closes[-1]
    prev_upper = upper[-2]
    prev_lower = lower[-2]
    cur_upper = upper[-1]
    cur_lower = lower[-1]

    # RSI for confirmation
    cur_rsi = rsi(closes, 10)

    # === LONG: price was below lower band, now reversing ===
    # Previous close below lower band, current close above it
    if prev_close < prev_lower and cur_close > cur_lower:
        # RSI must be oversold (< 35)
        if cur_rsi and cur_rsi < 35:
            # Candle must be bullish (close > open)
            if closes[-1] > closes[-2]:
                return "call", 70
        elif cur_rsi and cur_rsi < 45:
            if closes[-1] > closes[-2]:
                return "call", 55

    # === SHORT: price was above upper band, now reversing ===
    if prev_close > prev_upper and cur_close < cur_upper:
        # RSI must be overbought (> 65)
        if cur_rsi and cur_rsi > 65:
            # Candle must be bearish (close < open)
            if closes[-1] < closes[-2]:
                return "put", 70
        elif cur_rsi and cur_rsi > 55:
            if closes[-1] < closes[-2]:
                return "put", 55

    return None, 0
