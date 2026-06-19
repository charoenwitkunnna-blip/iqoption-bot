"""
ALPHA MOMENTUM — Multi-timeframe MACD + RSI Confluence
=======================================================
5-min trend + 1-min momentum must agree.
"""
NAME = "alpha_momentum"

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

def analyze(api, asset, candles, htf_candles=None):
    """
    HTF (5-min): MACD trend direction + RSI zone
    LTF (1-min): MACD cross + RSI momentum
    Only trade when BOTH agree.
    """
    closes = np.array([c['close'] for c in candles], dtype=float)

    if len(closes) < 30:
        return None, 0

    # === LTF (1-min) signals ===
    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    if ema12 is None or ema26 is None:
        return None, 0
    macd_line = ema12 - ema26
    # Signal line = EMA9 of MACD
    sig_alpha = 2.0 / 10.0
    signal_line = np.zeros(len(macd_line))
    signal_line[0] = macd_line[0]
    for i in range(1, len(macd_line)):
        signal_line[i] = sig_alpha * macd_line[i] + (1 - sig_alpha) * signal_line[i-1]

    macd_hist = macd_line - signal_line

    # MACD cross: histogram changes sign
    ltf_bullish = macd_hist[-1] > 0 and macd_hist[-2] <= 0
    ltf_bearish = macd_hist[-1] < 0 and macd_hist[-2] >= 0

    # RSI for momentum confirmation
    ltf_rsi = rsi(closes, 9)
    if ltf_rsi is None:
        return None, 0

    # === HTF (5-min) trend ===
    if htf_candles is not None and len(htf_candles) >= 30:
        htf_closes = np.array([c['close'] for c in htf_candles], dtype=float)
        htf_ema20 = ema(htf_closes, 20)
        htf_ema50 = ema(htf_closes, 50)
        if htf_ema20 is not None and htf_ema50 is not None:
            htf_bullish = htf_ema20[-1] > htf_ema50[-1]
            htf_bearish = htf_ema20[-1] < htf_ema50[-1]
        else:
            htf_bullish = htf_bearish = False
    else:
        htf_bullish = htf_bearish = False

    # === CONFLUENCE: HTF + LTF must agree ===
    if htf_bullish and ltf_bullish:
        direction = "call"
        confidence = 65
        # Bonus: RSI not overbought
        if 45 < ltf_rsi < 65:
            confidence += 10
    elif htf_bearish and ltf_bearish:
        direction = "put"
        confidence = 65
        if 35 < ltf_rsi < 55:
            confidence += 10
    else:
        return None, 0

    return direction, confidence
