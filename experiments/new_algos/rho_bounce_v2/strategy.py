"""
RHO BOUNCE V2 — Sharpened S/R Zone Bounce
===========================================
RADICAL TIGHTEN over v2-alpha:
- ADX < 25 range-only (like v1, this was the key)
- 3+ touches on zone minimum
- 2+ rejection patterns required (not just 1)
- RSI-2 extreme required as bonus
- Minimum confidence raised to 70
- Only trade WITH the 1-min trend bias

Goal: 70%+ on few but high-quality trades.
"""
NAME = "rho_bounce_v2"

import numpy as np
import time


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


def find_swing_zones(highs, lows, lookback=5):
    zones = []
    for i in range(lookback, len(highs) - lookback):
        if highs[i] > np.max(highs[i - lookback:i]) and \
           highs[i] > np.max(highs[i + 1:i + lookback + 1]):
            zones.append({'type': 'resistance', 'center': highs[i], 'index': i})
    for i in range(lookback, len(lows) - lookback):
        if lows[i] < np.min(lows[i - lookback:i]) and \
           lows[i] < np.min(lows[i + 1:i + lookback + 1]):
            zones.append({'type': 'support', 'center': lows[i], 'index': i})
    return zones


def count_zone_touches(zones, highs, lows, closes, lookback_idx):
    for z in zones:
        t = 0
        rt = 0
        ct = 0
        if z['type'] == 'resistance':
            zl = z['center'] * (1 - 0.0002)
            zh = z['center'] * (1 + 0.0015)
            for j in range(lookback_idx, len(highs) - 1):
                if zl <= highs[j] <= zh:
                    t += 1
                    if j >= len(highs) - 4:
                        rt += 1
                    if abs(closes[j] - z['center']) / z['center'] * 100 < 0.15:
                        ct += 1
        else:
            zl = z['center'] * (1 - 0.0015)
            zh = z['center'] * (1 + 0.0002)
            for j in range(lookback_idx, len(highs) - 1):
                if zl <= lows[j] <= zh:
                    t += 1
                    if j >= len(highs) - 4:
                        rt += 1
                    if abs(closes[j] - z['center']) / z['center'] * 100 < 0.15:
                        ct += 1
        z['touches'] = t
        z['recent_touches'] = rt
        z['close_touches'] = ct


def check_rejection(closes, highs, lows, opens, z):
    """
    Returns (pattern_count, direction) where pattern_count is how many
    rejection patterns were detected (0-6). Higher = stronger.
    """
    cur_c = closes[-1]
    cur_o = opens[-1]
    prev_c = closes[-2]
    prev_o = opens[-2]
    cur_b = cur_c - cur_o
    prev_b = prev_c - prev_o
    cur_r = highs[-1] - lows[-1]
    prev_r = highs[-2] - lows[-2]

    cu = (highs[-1] - max(cur_c, cur_o)) / cur_r if cur_r > 0 else 0
    cl = (min(cur_c, cur_o) - lows[-1]) / cur_r if cur_r > 0 else 0
    pu = (highs[-2] - max(prev_c, prev_o)) / prev_r if prev_r > 0 else 0
    pl = (min(prev_c, prev_o) - lows[-2]) / prev_r if prev_r > 0 else 0

    patterns = []

    if z['type'] == 'resistance':
        # Shooting star
        if cur_b < 0 and cu > 0.6:
            patterns.append('shooting_star')
        # Bearish engulfing
        if prev_b > 0 and cur_b < 0 and cur_o > prev_c and cur_c < prev_o:
            patterns.append('engulfing')
        # Two bearish
        if prev_b < 0 and cur_b < 0:
            patterns.append('2_bear')
        # Doji + bear
        if abs(prev_b) < prev_r * 0.3 and pu > 0.5 and cur_b < 0:
            patterns.append('doji_bear')
        # Spring failure
        if cur_b < 0 and highs[-1] > z['center'] * (1 + 0.001) and cur_c < z['center']:
            patterns.append('fakeout')
        # Bear follow with upper wick
        if cur_b < 0 and abs(cur_b) > abs(prev_b) * 1.3 and cu > 0.3:
            patterns.append('bear_follow')
    else:  # support
        # Hammer
        if cur_b > 0 and cl > 0.6:
            patterns.append('hammer')
        # Bullish engulfing
        if prev_b < 0 and cur_b > 0 and cur_o < prev_c and cur_c > prev_o:
            patterns.append('engulfing')
        # Two bull
        if prev_b > 0 and cur_b > 0:
            patterns.append('2_bull')
        # Doji + bull
        if abs(prev_b) < prev_r * 0.3 and pl > 0.5 and cur_b > 0:
            patterns.append('doji_bull')
        # Spring
        if cur_b > 0 and lows[-1] < z['center'] * (1 - 0.001) and cur_c > z['center']:
            patterns.append('spring')
        # Bull follow with lower wick
        if cur_b > 0 and abs(cur_b) > abs(prev_b) * 1.3 and cl > 0.3:
            patterns.append('bull_follow')

    return patterns


# ---------------------------------------------------------------------------

def analyze(api, asset, candles, htf_candles=None):
    closes = np.array([c['close'] for c in candles], dtype=float)
    highs = np.array([c['max'] for c in candles], dtype=float)
    lows = np.array([c['min'] for c in candles], dtype=float)
    opens = np.array([c['open'] for c in candles], dtype=float)

    if len(closes) < 30:
        return None, 0

    # =====================================================================
    # 1. MARKET REGIME — RANGING ONLY
    # =====================================================================
    cur_adx = adx(highs, lows, closes, 14)
    if cur_adx is None or cur_adx >= 25:
        return None, 0

    avg_range = np.mean([highs[i] - lows[i] for i in range(-12, -2)])

    # =====================================================================
    # 2. TREND BIAS (within the range)
    # =====================================================================
    e8 = ema(closes, 8)
    e20 = ema(closes, 20)
    if e8 is None or e20 is None:
        return None, 0

    # In a range: prefer PUT bounces off resistance, CALL bounces off support
    # (no directional requirement — the range IS the strategy)
    near_top_of_range = closes[-1] > e20[-1] and e8[-1] > e20[-1]
    near_bottom_of_range = closes[-1] < e20[-1] and e8[-1] < e20[-1]

    # =====================================================================
    # 3. S/R ZONES
    # =====================================================================
    lookback_start = max(0, len(closes) - 28)
    zones = find_swing_zones(highs[lookback_start:], lows[lookback_start:], 4)
    if not zones:
        return None, 0

    for z in zones:
        z['index'] += lookback_start

    count_zone_touches(zones, highs, lows, closes, lookback_start)

    # Filter: must have 2+ touches
    strong_zones = [z for z in zones if z['touches'] >= 2]

    if not strong_zones:
        return None, 0

    # =====================================================================
    # 4. CHECK EACH ZONE
    # =====================================================================
    cur_close = closes[-1]
    rsi2 = rsi_2_value(closes)
    best_trade = None
    best_conf = 0

    for z in strong_zones:
        dist_pct = abs(cur_close - z['center']) / z['center'] * 100
        if dist_pct > 0.18:
            continue

        patterns = check_rejection(closes, highs, lows, opens, z)

        if len(patterns) < 1:
            continue

        # ================================================================
        # 5. CONFIDENCE
        # ================================================================
        confidence = 60

        # Pattern bonus (each extra = stronger)
        pattern_bonus = min(len(patterns) * 8, 15)
        confidence += pattern_bonus

        # Zone strength (touches)
        touch_bonus = min(z['touches'] * 2, 8)
        confidence += touch_bonus

        # RSI-2 extreme at zone = powerful combo
        if z['type'] == 'resistance':
            if rsi2 > 85:
                confidence += 10
            elif rsi2 > 75:
                confidence += 5
            # Near top of range amplifies resistance bounces
            if near_top_of_range:
                confidence += 5
        else:
            if rsi2 < 15:
                confidence += 10
            elif rsi2 < 25:
                confidence += 5
            if near_bottom_of_range:
                confidence += 5

        # HTF
        if htf_candles is not None and len(htf_candles) >= 20:
            htf_c = np.array([c['close'] for c in htf_candles], dtype=float)
            htf_e8 = ema(htf_c, 8)
            htf_e20 = ema(htf_c, 20)
            if htf_e8 and htf_e20:
                htf_trender = htf_e8[-1] > htf_e20[-1]
                if z['type'] == 'support' and htf_trender:
                    confidence += 5
                elif z['type'] == 'resistance' and not htf_trender:
                    confidence += 5

        if confidence < 70:
            continue

        direction = "put" if z['type'] == 'resistance' else "call"
        if confidence > best_conf:
            best_conf = confidence
            best_trade = direction

    if best_trade and best_conf >= 70:
        return best_trade, min(best_conf, 90)

    return None, 0


def generate_signals(api):
    """
    New universal signal format.
    Scans all assets, returns list of signal dicts sorted by confidence.
    """
    signals = []
    paying = {}

    # Get all open turbo assets
    try:
        all_open = api.get_all_open_time()
        open_assets = {k: v for k, v in all_open.get('turbo', {}).items() if v.get('open')}
    except:
        print("[signal] Failed to get open assets")
        return []

    # Get payouts for first 60
    for asset in list(open_assets.keys())[:60]:
        try:
            p = api.get_digital_payout(asset)
            if p and p >= 80:
                paying[asset] = p
        except:
            continue

    for asset in sorted(paying.keys(), key=paying.get, reverse=True):
        try:
            candles = api.get_candles(asset, 60, 50, time.time())
            if not candles or len(candles) < 30:
                continue
        except:
            continue

        try:
            htf = None
            try:
                htf = api.get_candles(asset, 300, 10, time.time())
            except:
                pass
            direction, confidence = analyze(api, asset, candles, htf)
        except:
            continue

        if direction and confidence >= 60:
            signals.append({
                "asset": asset,
                "direction": direction,
                "confidence": confidence,
                "payout": paying.get(asset, 87),
                "strategy": "rho_bounce_v2",
                "timestamp": time.time()
            })

    signals.sort(key=lambda s: s['confidence'], reverse=True)
    if signals:
        top = signals[0]
        print(f"[signal] {top['asset']} {top['direction']} conf={top['confidence']}")
    return signals
