"""
RHO BOUNCE — Original config + TDI + HMA filters.
PUT only, ADX<25, lookback=5, wick>0.5, dist<0.2%
+ TDI overbought/oversold confirmation
+ HMA trend direction filter
"""
NAME = "rho_bounce"

import numpy as np


def ema(data, period):
    if len(data) < period:
        return np.array([])
    multiplier = 2 / (period + 1)
    result = np.zeros(len(data))
    result[0] = data[0]
    for i in range(1, len(data)):
        result[i] = (data[i] - result[i-1]) * multiplier + result[i-1]
    return result


def wma(data, period):
    if len(data) < period:
        return np.array([])
    weights = np.arange(1, period + 1)
    result = np.zeros(len(data))
    for i in range(period - 1, len(data)):
        result[i] = np.sum(data[i - period + 1:i + 1] * weights) / np.sum(weights)
    return result


def hma(data, period=20):
    """Hull Moving Average — fast, smooth, low lag."""
    if len(data) < period:
        return np.array([])
    half_period = max(period // 2, 1)
    sqrt_period = max(int(np.sqrt(period)), 1)
    wma_half = wma(data, half_period)
    wma_full = wma(data, period)
    diff = 2 * wma_half - wma_full
    hma_val = wma(diff, sqrt_period)
    return hma_val


def rsi(closes, period=14):
    if len(closes) < period + 1:
        return np.array([])
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.zeros(len(gains))
    avg_loss = np.zeros(len(losses))
    avg_gain[period-1] = np.mean(gains[:period])
    avg_loss[period-1] = np.mean(losses[:period])
    for i in range(period, len(gains)):
        avg_gain[i] = (avg_gain[i-1] * (period-1) + gains[i]) / period
        avg_loss[i] = (avg_loss[i-1] * (period-1) + losses[i]) / period
    rs = avg_gain / (avg_loss + 1e-10)
    return 100 - (100 / (1 + rs))


def tdi_check(closes):
    """Check TDI conditions. Returns 'overbought', 'oversold', or None."""
    rsi_line = rsi(closes, 13)
    if len(rsi_line) < 40:
        return None
    
    rsi_valid = rsi_line[13:]
    if len(rsi_valid) < 34:
        return None
    
    # BB on RSI
    bb_mid = ema(rsi_valid, 34)
    bb_std = np.zeros(len(rsi_valid))
    for i in range(33, len(rsi_valid)):
        bb_std[i] = np.std(rsi_valid[i-33:i+1])
    upper = bb_mid + 1.618 * bb_std
    lower = bb_mid - 1.618 * bb_std
    
    # Signal line
    signal = ema(rsi_valid, 2)
    
    cur = rsi_valid[-1]
    prev = rsi_valid[-2] if len(rsi_valid) > 1 else cur
    cur_upper = upper[-1]
    cur_lower = lower[-1]
    cur_signal = signal[-1]
    prev_signal = signal[-2] if len(signal) > 1 else cur_signal
    
    # Overbought: RSI above upper BB, or RSI crossing down from above
    if cur > cur_upper or (cur < cur_signal and prev > prev_signal and prev > 60):
        return 'overbought'
    
    # Oversold: RSI below lower BB, or RSI crossing up from below
    if cur < cur_lower or (cur > cur_signal and prev < prev_signal and prev < 40):
        return 'oversold'
    
    return None


def find_swing_highs(highs, lookback=5):
    swings = []
    for i in range(lookback, len(highs) - lookback):
        left = highs[i - lookback:i]
        right = highs[i + 1:i + lookback + 1]
        if highs[i] > np.max(left) and highs[i] > np.max(right):
            swings.append((i, highs[i]))
    return swings


def adx(highs, lows, closes, period=14):
    if len(closes) < period + 1:
        return None
    tr = np.maximum(highs[1:] - lows[1:],
                    np.maximum(np.abs(highs[1:] - closes[:-1]),
                               np.abs(lows[1:] - closes[:-1])))
    plus_dm = np.where((highs[1:] - highs[:-1]) > (lows[:-1] - lows[1:]),
                       np.maximum(highs[1:] - highs[:-1], 0), 0)
    minus_dm = np.where((lows[:-1] - lows[1:]) > (highs[1:] - highs[:-1]),
                        np.maximum(lows[:-1] - lows[1:], 0), 0)
    atr = np.convolve(tr, np.ones(period)/period, mode='valid')
    plus_di = 100 * np.convolve(plus_dm, np.ones(period)/period, mode='valid') / (atr + 1e-10)
    minus_di = 100 * np.convolve(minus_dm, np.ones(period)/period, mode='valid') / (atr + 1e-10)
    dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
    adx_val = np.convolve(dx, np.ones(period)/period, mode='valid')
    return adx_val[-1] if len(adx_val) > 0 else None


def analyze(api, asset, candles, htf_candles=None):
    closes = np.array([c['close'] for c in candles], dtype=float)
    highs = np.array([c['max'] for c in candles], dtype=float)
    lows = np.array([c['min'] for c in candles], dtype=float)
    opens = np.array([c['open'] for c in candles], dtype=float)

    if len(closes) < 30:
        return None, 0

    # ADX < 25
    cur_adx = adx(highs, lows, closes, 14)
    if cur_adx is None or cur_adx >= 25:
        return None, 0

    # HMA trend filter — only trade with the trend
    hma_val = hma(closes, 20)
    if len(hma_val) < 2:
        return None, 0
    
    # For PUT: HMA should be bearish (price below HMA)
    if closes[-1] > hma_val[-1]:
        return None, 0  # skip if price above HMA (bullish)

    # TDI filter — need overbought confirmation for PUT
    tdi_signal = tdi_check(closes)
    if tdi_signal != 'overbought':
        return None, 0  # skip if not overbought

    # Original rho_bounce logic
    lookback = 5
    search = highs[-20:-2]
    swing_highs = find_swing_highs(search, lookback)
    if not swing_highs:
        return None, 0

    cur_close = closes[-1]
    cur_high = highs[-1]
    cur_low = lows[-1]
    prev_close = closes[-2]
    cur_body = cur_close - opens[-1]
    prev_body = prev_close - opens[-2]
    total_range = cur_high - cur_low

    if total_range <= 0:
        return None, 0

    upper_wick = (cur_high - max(cur_close, opens[-1])) / total_range

    # RESISTANCE BOUNCE — PUT only
    for idx, level in swing_highs:
        age = len(candles) - 20 + idx
        if age < 2:
            continue

        dist_pct = abs(cur_close - level) / cur_close * 100
        if dist_pct > 0.2:
            continue

        if cur_close < level * 1.001:
            if cur_body < 0:
                if total_range > 0 and upper_wick > 0.5:
                    if prev_body < 0:
                        return "put", 70

    return None, 0
