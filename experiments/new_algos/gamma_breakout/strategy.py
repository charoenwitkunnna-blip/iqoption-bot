"""
GAMMA BREAKOUT — Scalping Edition
==================================
Donchian breakout + ADX(7) hook detection.
For 1-min scalping: catches the trend while it's forming, not after it's exhausted.
"""
NAME = "gamma_breakout"

import numpy as np

def adx(highs, lows, closes, period=7):
    """ADX with configurable period. Shorter = less lag, better for scalping."""
    n = len(closes)
    if n < period + 1:
        return None
    tr = np.zeros(n)
    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i],
                    abs(highs[i] - closes[i-1]),
                    abs(lows[i] - closes[i-1]))
        up = highs[i] - highs[i-1]
        down = lows[i-1] - lows[i]
        if up > down and up > 0:
            plus_dm[i] = up
        else:
            plus_dm[i] = 0
        if down > up and down > 0:
            minus_dm[i] = down
        else:
            minus_dm[i] = 0
    tr_smooth = np.zeros(n)
    pdm_smooth = np.zeros(n)
    ndm_smooth = np.zeros(n)
    tr_smooth[period] = np.sum(tr[1:period+1])
    pdm_smooth[period] = np.sum(plus_dm[1:period+1])
    ndm_smooth[period] = np.sum(minus_dm[1:period+1])
    for i in range(period+1, n):
        tr_smooth[i] = tr_smooth[i-1] - tr_smooth[i-1]/period + tr[i]
        pdm_smooth[i] = pdm_smooth[i-1] - pdm_smooth[i-1]/period + plus_dm[i]
        ndm_smooth[i] = ndm_smooth[i-1] - ndm_smooth[i-1]/period + minus_dm[i]
    pdi = np.zeros(n)
    ndi = np.zeros(n)
    dx = np.zeros(n)
    adx_vals = np.zeros(n)
    for i in range(period+1, n):
        if tr_smooth[i] > 0:
            pdi[i] = 100 * pdm_smooth[i] / tr_smooth[i]
            ndi[i] = 100 * ndm_smooth[i] / tr_smooth[i]
        if pdi[i] + ndi[i] > 0:
            dx[i] = 100 * abs(pdi[i] - ndi[i]) / (pdi[i] + ndi[i])
    adx_vals[period*2] = np.mean(dx[period+1:period*2+1])
    for i in range(period*2+1, n):
        adx_vals[i] = (adx_vals[i-1] * (period-1) + dx[i]) / period
    # Return last 3 values for hook detection
    if n > period*2+2:
        return adx_vals[-3], adx_vals[-2], adx_vals[-1]
    return None, None, adx_vals[-1]

def atr(highs, lows, closes, period=10):
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i-1]),
                 abs(lows[i] - closes[i-1]))
        trs.append(tr)
    trs = np.array(trs)
    atr_vals = np.zeros(len(trs))
    atr_vals[period-1] = np.mean(trs[:period])
    for i in range(period, len(trs)):
        atr_vals[i] = (atr_vals[i-1] * (period - 1) + trs[i]) / period
    return atr_vals

def rsi(data, period=5):
    """Short-period RSI for scalping momentum."""
    if len(data) < period + 1:
        return None
    deltas = np.diff(data)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    if avg_loss == 0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))

def analyze(api, asset, candles, htf_candles=None):
    closes = np.array([c['close'] for c in candles], dtype=float)
    highs = np.array([c['max'] for c in candles], dtype=float)
    lows = np.array([c['min'] for c in candles], dtype=float)

    if len(closes) < 25:
        return None, 0

    # ADX(7) — fast hook detection for scalping (completed candles only)
    adx_result = adx(highs[:-1], lows[:-1], closes[:-1], 7)
    if adx_result is None:
        return None, 0
    adx_2ago, adx_1ago, cur_adx = adx_result

    # Hook detection: ADX turning up sharply
    # Enter when ADX is rising from a low base (trend just starting, not exhausted)
    adx_rising = cur_adx > adx_1ago and adx_1ago >= adx_2ago
    adx_hooking = cur_adx > adx_1ago and adx_2ago < 15  # Coming from dead zone

    # Skip dead-flat markets (ADX stuck below 12 — pure noise)
    if cur_adx < 12:
        return None, 0

    # Must be rising — no flat or declining ADX
    if not adx_rising:
        return None, 0

    # ============================================================
    #  USE COMPLETED CANDLES ONLY — no mid-candle reversals
    # ============================================================
    # candles[-1] = current/incomplete (unreliable close)
    # candles[-2] = last COMPLETED candle (the signal candle)
    # candles[-3] = the one before that

    # Donchian Channel (10-period)
    donchian_high = np.array([np.max(highs[max(0,i-9):i+1]) for i in range(len(highs))])
    donchian_low = np.array([np.min(lows[max(0,i-9):i+1]) for i in range(len(lows))])

    # ATR for volatility
    atr_vals = atr(highs, lows, closes, 10)
    if atr_vals is None:
        return None, 0

    # Check Donchian breakout on COMPLETED candle [-2]
    signal_close = closes[-2]       # The completed candle that broke out
    signal_high = highs[-2]
    signal_low = lows[-2]
    prev_close   = closes[-3]       # Candle before the signal
    prev_high_c  = highs[-3]
    prev_low_c   = lows[-3]

    # Donchian channel built up to candle[-3] (before the signal candle)
    dh = donchian_high[-3]  # Channel high BEFORE the breakout candle
    dl = donchian_low[-3]   # Channel low BEFORE the breakout candle

    # Current price (candle[-1]) — use to verify breakout is still holding
    current_price = closes[-1]

    momentum_up = signal_close > prev_close and signal_close > current_price * 0.999
    momentum_down = signal_close < prev_close and signal_close < current_price * 1.001

    # Chop filter (on completed candles)
    if len(closes) >= 6:
        last3_dir = [closes[i] > closes[i-1] for i in range(-4, -1)]
        if sum(last3_dir) in (1, 2):
            return None, 0

    # Short RSI on completed candles only
    cur_rsi = rsi(closes[:-1], 5)

    # === BREAKOUT UP (on completed candle) ===
    if signal_close > dh and momentum_up:
        # Pressure: previous candle near channel top
        channel_range = dh - dl
        if channel_range > 0 and prev_close < (dh - channel_range * 0.20):
            return None, 0

        # Depth: breakout must be meaningful vs ATR
        breakout_depth = signal_close - dh
        atr_ref = atr_vals[-2] if len(atr_vals) > 1 else atr_vals[-1]
        if atr_ref > 0 and breakout_depth < atr_ref * 0.08:
            return None, 0

        # Range extension on signal candle
        if signal_high <= prev_high_c:
            return None, 0

        # Verify breakout still holding — current price hasn't fallen back inside
        if current_price <= dh:
            return None, 0  # Reversed back in — fakeout

        # RSI: must be pushing up through midline
        if cur_rsi is not None and (cur_rsi < 40 or cur_rsi > 75):
            return None, 0

        confidence = 55
        if adx_hooking: confidence += 15
        if cur_rsi and 50 < cur_rsi < 65: confidence += 5
        return "call", confidence

    # === BREAKOUT DOWN (on completed candle) ===
    if signal_close < dl and momentum_down:
        channel_range = dh - dl
        if channel_range > 0 and prev_close > (dl + channel_range * 0.20):
            return None, 0

        break_depth = dl - signal_close
        atr_ref = atr_vals[-2] if len(atr_vals) > 1 else atr_vals[-1]
        if atr_ref > 0 and break_depth < atr_ref * 0.08:
            return None, 0

        if signal_low >= prev_low_c:
            return None, 0

        # Verify breakout still holding
        if current_price >= dl:
            return None, 0

        if cur_rsi is not None and (cur_rsi > 60 or cur_rsi < 25):
            return None, 0

        confidence = 55
        if adx_hooking: confidence += 15
        if cur_rsi and 35 < cur_rsi < 50: confidence += 5
        return "put", confidence

    return None, 0
