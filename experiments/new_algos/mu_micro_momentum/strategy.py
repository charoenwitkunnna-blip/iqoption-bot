"""
Mu v3 (μ) — Micro-Reversal Predictor
======================================
In dead markets, price doesn't trend — it ping-pongs.
After 3-5 candles in one direction on 5-sec data, the next
3-5 reverse. This detects those micro-reversals.

Logic: if the last 10 candles had a clear micro-trend but
the candle before that was already at an extreme, the move
has exhausted and price will revert in the next 60 seconds.
"""
NAME = "mu_micro_momentum"

import numpy as np
import time


def linreg_slope(values):
    x = np.arange(len(values), dtype=float)
    y = np.array(values, dtype=float)
    n = len(y)
    if n < 3:
        return 0
    sx, sy, sxx, sxy = np.sum(x), np.sum(y), np.sum(x*x), np.sum(x*y)
    denom = n * sxx - sx * sx
    return (n * sxy - sx * sy) / denom if denom else 0


def analyze(api, asset, candles=None, htf_candles=None):
    """Micro-reversal detection on 5-second candles."""
    try:
        candles5 = api.get_candles(asset, 5, 50, time.time())
    except:
        return None, 0

    if not candles5 or len(candles5) < 30:
        return None, 0

    closes = np.array([c['close'] for c in candles5], dtype=float)
    highs = np.array([c['max'] for c in candles5], dtype=float)
    lows = np.array([c['min'] for c in candles5], dtype=float)
    opens = np.array([c['open'] for c in candles5], dtype=float)
    n = len(closes)

    # Overall volatility
    vol = np.std(closes[-20:]) + 0.000001

    # ---- Micro-trend detection ----
    # "Recent" = last 10 candles (50 sec) — the move we might fade
    recent_slope = linreg_slope(closes[-10:])
    recent_norm = recent_slope / vol

    # "Prior" = 10 candles before that (50-100 sec ago) — the baseline
    prior_slope = linreg_slope(closes[-20:-10]) if n >= 20 else 0
    prior_norm = prior_slope / vol

    # ---- Micro-move magnitude ----
    # How far has price moved in the last 10 candles?
    move = closes[-1] - closes[-10]
    move_norm = move / (vol * 3)

    # ---- Position in recent range ----
    r_high = max(highs[-20:])
    r_low = min(lows[-20:])
    r_range = max(r_high - r_low, 0.0001)
    r_pos = (closes[-1] - r_low) / r_range

    # Extreme: at or near the edge of the range
    at_top = r_pos >= 0.82
    at_bot = r_pos <= 0.18

    # ---- Exhaustion check ----
    # Last 3 candles losing steam compared to 3 before that
    late_slope = linreg_slope(closes[-3:]) if n >= 3 else 0
    early_slope = linreg_slope(closes[-6:-3]) if n >= 6 else 0

    # ---- Candle wick check ----
    last_body = abs(closes[-1] - opens[-1])
    last_range = max(highs[-1] - lows[-1], 0.0001)
    wick_ratio = 1 - (last_body / last_range)  # >0.5 = long wick = rejection

    # === PUT SIGNAL: recent move UP, now at top, exhausting ===
    call_score = 0
    put_score = 0

    if recent_norm > 0.3 and at_top:
        # Recent micro-trend was up and price is at range top
        put_score += 35

        # Moving into resistance — prior slope was flatter/negative
        if prior_norm < recent_norm:
            put_score += 15

        # Exhaustion: late candles slower than early
        if abs(late_slope) < abs(early_slope):
            put_score += 15

        # Rejection wick on last candle
        if wick_ratio > 0.5:
            put_score += 15

        # Total move was significant (enough to revert from)
        if move_norm > 0.5:
            put_score += 10

    # === CALL SIGNAL: recent move DOWN, now at bottom, exhausting ===
    if recent_norm < -0.3 and at_bot:
        call_score += 35

        if prior_norm > recent_norm:
            call_score += 15

        if abs(late_slope) < abs(early_slope):
            call_score += 15

        if wick_ratio > 0.5:
            call_score += 15

        if move_norm < -0.5:
            call_score += 10

    # === Volatility calm filter ===
    vol_recent = np.std(closes[-10:])
    vol_overall = np.std(closes[-30:]) + 0.000001
    if vol_recent / vol_overall > 1.5:
        # Spiking vol = unpredictable, reduce confidence
        call_score = int(call_score * 0.6)
        put_score = int(put_score * 0.6)

    confidence = max(call_score, put_score)
    if confidence < 50:
        return None, 0

    if call_score > put_score:
        return "call", min(confidence + 10, 95)
    else:
        return "put", min(confidence + 10, 95)


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

    for asset in sorted(paying.keys(), key=paying.get, reverse=True)[:30]:
        try:
            dir, conf = analyze(api, asset)
        except:
            continue
        if dir and conf >= 50:
            signals.append({
                "asset": asset,
                "direction": dir,
                "confidence": conf,
                "payout": paying.get(asset, 87),
                "strategy": "mu_micro_momentum",
                "timestamp": time.time()
            })

    signals.sort(key=lambda s: s['confidence'], reverse=True)
    if signals:
        top = signals[0]
        print(f"[mu] {top['asset']} {top['direction']} conf={top['confidence']}")
    return signals
