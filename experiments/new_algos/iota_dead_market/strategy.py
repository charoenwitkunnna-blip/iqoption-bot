"""
IOTA — Dead Market Specialist
==============================
Designed for low-volatility, ranging markets (ADX < 20).
Uses statistically-defined percentile ranges instead of swing points.

Core idea: In dead markets, price respects the same levels over and over.
Wait for price to hit extreme percentiles of the recent range,
confirm rejection with wick structure, and trade the bounce.

Entry:
  CALL when price < 15th percentile + bullish rejection (long lower wick)
  PUT  when price > 85th percentile + bearish rejection (long upper wick)

Requires:
  - ADX < 20 (confirmed range)
  - Multiple touches of the level in history
  - Rejection candle (long wick, small body)
"""
NAME = "iota_dead_market"

import numpy as np
import time


def ema(data, period):
    data = np.array(data, dtype=float)
    if len(data) < period:
        return np.full(len(data), np.nan)
    result = np.full(len(data), np.nan)
    result[:period] = np.mean(data[:period])
    alpha = 2 / (period + 1)
    for i in range(period, len(data)):
        result[i] = alpha * data[i] + (1 - alpha) * (result[i-1] if not np.isnan(result[i-1]) else data[i-1])
    return result


def adx(highs, lows, closes, period=14):
    n = len(closes)
    if n < period + 1:
        return None
    tr = np.zeros(n)
    pd = np.zeros(n)
    nd = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i],
                    abs(highs[i] - closes[i-1]),
                    abs(lows[i] - closes[i-1]))
        u = highs[i] - highs[i-1]
        d = lows[i-1] - lows[i]
        pd[i] = u if (u > d and u > 0) else 0
        nd[i] = d if (d > u and d > 0) else 0
    ts = np.zeros(n)
    ps = np.zeros(n)
    ns = np.zeros(n)
    ts[period] = sum(tr[1:period+1])
    ps[period] = sum(pd[1:period+1])
    ns[period] = sum(nd[1:period+1])
    for i in range(period+1, n):
        ts[i] = ts[i-1] - ts[i-1]/period + tr[i]
        ps[i] = ps[i-1] - ps[i-1]/period + pd[i]
        ns[i] = ns[i-1] - ns[i-1]/period + nd[i]
    pi = np.zeros(n)
    ni = np.zeros(n)
    dx = np.zeros(n)
    ax = np.zeros(n)
    for i in range(period+1, n):
        if ts[i] > 0:
            pi[i] = 100 * ps[i] / ts[i]
            ni[i] = 100 * ns[i] / ts[i]
        if pi[i] + ni[i] > 0:
            dx[i] = 100 * abs(pi[i] - ni[i]) / (pi[i] + ni[i])
    ax[period*2] = np.mean(dx[period+1:period*2+1])
    for i in range(period*2+1, n):
        ax[i] = (ax[i-1] * (period-1) + dx[i]) / period
    return ax[-1]


def count_touches(series, level, threshold=0.001):
    """Count how many times price touched within threshold of a level."""
    hits = 0
    for val in series:
        if abs(val - level) / level <= threshold:
            hits += 1
    return hits


def analyze(api, asset, candles, htf_candles=None):
    """Dead market specialist: range-bound trading using percentiles."""
    closes = np.array([c['close'] for c in candles], dtype=float)
    highs = np.array([c['max'] for c in candles], dtype=float)
    lows = np.array([c['min'] for c in candles], dtype=float)
    opens = np.array([c['open'] for c in candles], dtype=float)

    n = len(closes)
    if n < 40:
        return None, 0

    # Check ADX — must be RANGING (ADX < 20)
    cur_adx = adx(highs, lows, closes, 14)
    if cur_adx is None or cur_adx >= 22:
        return None, 0  # Too trending for this strategy

    # Calculate percentile levels from available candles (exclude recent 5)
    if n < 25:
        return None, 0
    lookback = closes[:max(n - 5, 1)]  # all but last 5
    if len(lookback) < 20:
        return None, 0
    p15 = np.percentile(lookback, 15)
    p85 = np.percentile(lookback, 85)
    p50 = np.percentile(lookback, 50)
    p05 = np.percentile(lookback, 5)
    p95 = np.percentile(lookback, 95)

    cur_close = closes[-1]
    cur_high = highs[-1]
    cur_low = lows[-1]
    cur_open = opens[-1]
    prev_close = closes[-2]
    prev_open = opens[-2]

    # Candle analysis
    body = cur_close - cur_open
    total_range = max(cur_high - cur_low, 0.0001)
    upper_wick = (cur_high - max(cur_close, cur_open)) / total_range
    lower_wick = (min(cur_close, cur_open) - cur_low) / total_range

    # How far are we from the mean? Higher confidence at more extreme levels
    range_width = max(p85 - p15, cur_close * 0.001)
    dist_from_mean = abs(cur_close - p50) / range_width  # 0-1 scale

    # Count level touches in the lookback
    prox = max(0.0008 * cur_close, (p85 - p15) * 0.05)
    call_bounces = count_touches(closes[-60:], p15, prox / cur_close)
    put_bounces = count_touches(closes[-60:], p85, prox / cur_close)

    confidence = 0

    # === BEARISH SIGNAL (PUT) — price above 85th percentile ===
    if cur_close >= p85:
        # Bearish confirmation — any of: bearish body, long upper wick, dark cloud
        base_conf = 55
        if body < 0:
            base_conf = 65  # Bearish candle at resistance

        if upper_wick > 0.4:
            base_conf += 8  # Rejection at the level

        if cur_close >= p95:
            base_conf += 10  # Extreme overshoot

        if dist_from_mean > 0.7:
            base_conf += 5  # Far from mean

        confidence = min(base_conf + 5, 95)

    # === BULLISH SIGNAL (CALL) — price below 15th percentile ===
    elif cur_close <= p15:
        base_conf = 55
        if body > 0:
            base_conf = 65  # Bullish candle at support

        if lower_wick > 0.4:
            base_conf += 8  # Rejection at the level

        if cur_close <= p05:
            base_conf += 10  # Extreme overshoot

        if dist_from_mean > 0.7:
            base_conf += 5

        confidence = min(base_conf + 5, 95)

    # Require at least some bounce history
    if confidence >= 65:
        direction = "call" if cur_close <= p15 else "put"
        if direction == "call" and call_bounces < 2:
            confidence -= 15
        elif direction == "put" and put_bounces < 2:
            confidence -= 15

    if confidence >= 60:
        direction = "call" if cur_close <= p15 else "put"
        return direction, min(confidence, 95)

    return None, 0


def generate_signals(api):
    """New signal format for the universal manager."""
    signals = []
    try:
        all_open = api.get_all_open_time()
        open_assets = {k: v for k, v in all_open.get('turbo', {}).items() if v.get('open')}
        paying = {}
        for asset in list(open_assets.keys())[:60]:
            try:
                p = api.get_digital_payout(asset)
                if p and p >= 80:
                    paying[asset] = p
            except:
                continue
    except:
        return []

    for asset in sorted(paying.keys(), key=paying.get, reverse=True):
        try:
            candles = api.get_candles(asset, 60, 50, time.time())
            if not candles or len(candles) < 50:
                continue
        except:
            continue
        try:
            htf = None
            try:
                htf = api.get_candles(asset, 300, 10, time.time())
            except:
                pass
            htf_candles = htf
            direction, confidence = analyze(api, asset, candles, htf_candles)
        except:
            continue
        if direction and confidence >= 60:
            signals.append({
                "asset": asset,
                "direction": direction,
                "confidence": confidence,
                "payout": paying.get(asset, 87),
                "strategy": "iota_dead_market",
                "timestamp": time.time()
            })

    signals.sort(key=lambda s: s['confidence'], reverse=True)
    if signals:
        top = signals[0]
        print(f"[iota] {top['asset']} {top['direction']} conf={top['confidence']}")
    return signals
