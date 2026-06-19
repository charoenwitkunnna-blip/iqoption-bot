"""
SIGMA — Breakout-Retest + Counter-Trend Momentum
=================================================
Two complementary patterns in one strategy:

PATTERN A — Breakout-Retest (70% weight):
  1. Price BREAKS through a recent swing high/low
  2. Price RETESTS that level (now flipped to support/resistance)
  3. Rejection candle at the retest = entry

PATTERN B — Counter-Trend Pin (30% weight):
  1. EMA ramp (3+ candles same direction off the band)
  2. Wick rejection at the other EMA extreme
  3. Quick counter-trend scalp

Pure 1-min, digital only, no ML.
"""
NAME = "sigma"

import numpy as np


def ema(data, period):
    if len(data) < period:
        return None
    a = 2.0 / (period + 1.0)
    r = np.zeros(len(data))
    r[0] = data[0]
    for i in range(1, len(data)):
        r[i] = a * data[i] + (1 - a) * r[i - 1]
    return r


def adx(highs, lows, closes, period=14):
    n = len(closes)
    if n < period + 1:
        return None
    tr = np.zeros(n)
    pd = np.zeros(n)
    nd = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i],
                    abs(highs[i] - closes[i - 1]),
                    abs(lows[i] - closes[i - 1]))
        u = highs[i] - highs[i - 1]
        d = lows[i - 1] - lows[i]
        pd[i] = u if (u > d and u > 0) else 0
        nd[i] = d if (d > u and d > 0) else 0
    ts = np.zeros(n)
    ps = np.zeros(n)
    ns = np.zeros(n)
    ts[period] = sum(tr[1:period + 1])
    ps[period] = sum(pd[1:period + 1])
    ns[period] = sum(nd[1:period + 1])
    for i in range(period + 1, n):
        ts[i] = ts[i - 1] - ts[i - 1] / period + tr[i]
        ps[i] = ps[i - 1] - ps[i - 1] / period + pd[i]
        ns[i] = ns[i - 1] - ns[i - 1] / period + nd[i]
    pi = np.zeros(n)
    ni = np.zeros(n)
    dx = np.zeros(n)
    ax = np.zeros(n)
    for i in range(period + 1, n):
        if ts[i] > 0:
            pi[i] = 100 * ps[i] / ts[i]
            ni[i] = 100 * ns[i] / ts[i]
        if pi[i] + ni[i] > 0:
            dx[i] = 100 * abs(pi[i] - ni[i]) / (pi[i] + ni[i])
    ax[period * 2] = np.mean(dx[period + 1:period * 2 + 1])
    for i in range(period * 2 + 1, n):
        ax[i] = (ax[i - 1] * (period - 1) + dx[i]) / period
    return ax[-1]


def rsi_2_value(closes):
    if len(closes) < 3:
        return 50.0
    d = np.diff(closes)
    g = np.where(d > 0, d, 0)
    l = np.where(d < 0, -d, 0)
    ag = np.mean(g[:2])
    al = np.mean(l[:2])
    if al == 0:
        return 100.0
    return 100.0 - (100.0 / (1.0 + ag / al))


# ---------------------------------------------------------------------------

def analyze(api, asset, candles, htf_candles=None):
    closes = np.array([c['close'] for c in candles], dtype=float)
    highs = np.array([c['max'] for c in candles], dtype=float)
    lows = np.array([c['min'] for c in candles], dtype=float)
    opens = np.array([c['open'] for c in candles], dtype=float)

    if len(closes) < 30:
        return None, 0

    # ------------------------------------------------------------------
    # 1. BASELINE
    # ------------------------------------------------------------------
    avg_range = np.mean([highs[i] - lows[i] for i in range(-12, -2)])
    bodies = closes - opens
    abs_bodies = np.abs(bodies)
    avg_body = np.mean(abs_bodies[-12:-2])

    e8 = ema(closes, 8)
    e20 = ema(closes, 20)
    if e8 is None or e20 is None:
        return None, 0

    trender = e8[-1] > e20[-1]
    cur_adx = adx(highs, lows, closes, 14)

    # ------------------------------------------------------------------
    # 2. FIND SWING LEVELS (last 20 candles)
    # ------------------------------------------------------------------
    swing_highs = []  # (index, price)
    swing_lows = []
    for i in range(5, len(highs) - 5):
        if highs[i] > np.max(highs[i - 5:i]) and highs[i] > np.max(highs[i + 1:i + 6]):
            swing_highs.append((i, highs[i]))
        if lows[i] < np.min(lows[i - 5:i]) and lows[i] < np.min(lows[i + 1:i + 6]):
            swing_lows.append((i, lows[i]))

    # Only consider swings in last 15 candles (not current)
    recent_sh = [(i, p) for i, p in swing_highs if i >= len(closes) - 15 and i < len(closes) - 2]
    recent_sl = [(i, p) for i, p in swing_lows if i >= len(closes) - 15 and i < len(closes) - 2]

    # ------------------------------------------------------------------
    # 3. PATTERN A: BREAKOUT-RETEST
    # ------------------------------------------------------------------
    cur_close = closes[-1]
    cur_body = bodies[-1]

    # Check for retest of a broken resistance (now support)
    for idx, level in recent_sl:
        # Did price already break ABOVE this support level?
        high_since_level = np.max(highs[idx:])
        if high_since_level < level * 1.003:
            continue  # No breakout yet

        # Has price come BACK DOWN to retest?
        dist = abs(cur_close - level) / level * 100
        if dist > 0.2:
            continue

        # RETEST happening now: price back at level
        # Bullish rejection at the retest
        if cur_body > 0:
            cur_range = highs[-1] - lows[-1]
            lower_wick = (min(cur_close, opens[-1]) - lows[-1]) / cur_range if cur_range > 0 else 0
            if lower_wick > 0.5 or abs(cur_body) > avg_body * 0.6:
                conf = 65
                # RSI oversold = stronger
                rsi2 = rsi_2_value(closes)
                if rsi2 < 30:
                    conf += 10
                if trender:
                    conf += 5  # Uptrend supports retest
                if cur_adx and cur_adx > 20 and cur_adx < 30:
                    conf += 5
                if conf >= 65:
                    return "call", min(conf, 85)

    # Check for retest of a broken support (now resistance)
    for idx, level in recent_sh:
        low_since_level = np.min(lows[idx:])
        if low_since_level > level * 0.997:
            continue

        dist = abs(cur_close - level) / level * 100
        if dist > 0.2:
            continue

        if cur_body < 0:
            cur_range = highs[-1] - lows[-1]
            upper_wick = (highs[-1] - max(cur_close, opens[-1])) / cur_range if cur_range > 0 else 0
            if upper_wick > 0.5 or abs(cur_body) > avg_body * 0.6:
                conf = 65
                rsi2 = rsi_2_value(closes)
                if rsi2 > 70:
                    conf += 10
                if not trender:
                    conf += 5  # Downtrend supports retest
                if cur_adx and cur_adx > 20 and cur_adx < 30:
                    conf += 5
                if conf >= 65:
                    return "put", min(conf, 85)

    # ------------------------------------------------------------------
    # 4. PATTERN B: EMA BOUNCE (counter-trend)
    # ------------------------------------------------------------------
    # Check if price is hugging one EMA and far from the other
    bb_width = e20[-1] - e20[-len(e20) + 1] if len(e20) > 5 else (e8[-1] - e20[-1])

    # Price near upper EMA band (resistance) after a ramp
    if trender and closes[-1] > e8[-1]:
        # 2+ consecutive bullish candles off E8
        bull_count = 0
        for j in range(1, min(4, len(bodies))):
            if bodies[-j] > 0:
                bull_count += 1
            else:
                break
        if bull_count >= 2:
            # Check for upper wick rejection on last candle
            cur_range = highs[-1] - lows[-1]
            upper_wick = (highs[-1] - max(closes[-1], opens[-1])) / cur_range if cur_range > 0 else 0
            if upper_wick > 0.5 or (bodies[-1] < 0 and abs(bodies[-1]) > avg_body * 0.3):
                # Overbought rejection in uptrend = fast put
                rsi2 = rsi_2_value(closes)
                if rsi2 > 75:
                    conf = 60
                    if bull_count >= 3:
                        conf += 5
                    if bodies[-1] < 0:
                        conf += 5
                    if conf >= 60:
                        return "put", min(conf, 75)

    # Price near lower EMA band (support) after a drop
    if not trender and closes[-1] < e8[-1]:
        bear_count = 0
        for j in range(1, min(4, len(bodies))):
            if bodies[-j] < 0:
                bear_count += 1
            else:
                break
        if bear_count >= 2:
            cur_range = highs[-1] - lows[-1]
            lower_wick = (min(closes[-1], opens[-1]) - lows[-1]) / cur_range if cur_range > 0 else 0
            if lower_wick > 0.5 or (bodies[-1] > 0 and abs(bodies[-1]) > avg_body * 0.3):
                rsi2 = rsi_2_value(closes)
                if rsi2 < 25:
                    conf = 60
                    if bear_count >= 3:
                        conf += 5
                    if bodies[-1] > 0:
                        conf += 5
                    if conf >= 60:
                        return "call", min(conf, 75)

    return None, 0
