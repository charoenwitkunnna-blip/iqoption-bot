"""
ETA MOMENTUM — Pure Price Action Streak
=========================================
If 4 consecutive candles all close higher → CALL (momentum continues)
If 4 consecutive candles all close lower → PUT
Simple, no indicators. Works when markets trend.
"""
NAME = "eta_momentum"

import numpy as np

def analyze(api, asset, candles, htf_candles=None):
    closes = np.array([c['close'] for c in candles], dtype=float)
    opens = np.array([c['open'] for c in candles], dtype=float)

    if len(closes) < 10: return None,0

    # Last 4 candles
    c4 = closes[-5]; c3 = closes[-4]; c2 = closes[-3]; c1 = closes[-2]; c0 = closes[-1]
    o4 = opens[-5]; o3 = opens[-4]; o2 = opens[-3]; o1 = opens[-2]; o0 = opens[-1]

    # Direction of each candle (close vs open)
    up4 = closes[-5] > opens[-5]
    up3 = closes[-4] > opens[-4]
    up2 = closes[-3] > opens[-3]
    up1 = closes[-2] > opens[-2]
    up0 = closes[-1] > opens[-1]

    # Average body size
    bodies = [abs(closes[i] - opens[i]) for i in range(-6, -1)]
    avg_body = sum(bodies) / len(bodies) if bodies else 0

    # Current candle body
    cur_body = abs(c0 - o0)

    # === CALL: 4 consecutive bullish candles ===
    if up4 and up3 and up2 and up1:
        # Current candle must also be bullish (5th continuation)
        if up0:
            # Bodies must be decent (not dojis)
            if cur_body > avg_body * 0.5:
                # Stronger if accelerating (bodies getting bigger)
                accel = (abs(c0-o0) > abs(c1-o1)) and (abs(c1-o1) > abs(c2-o2))
                conf = 65 if accel else 55
                return "call", conf

    # === PUT: 4 consecutive bearish candles ===
    if not up4 and not up3 and not up2 and not up1:
        if not up0:
            if cur_body > avg_body * 0.5:
                accel = (abs(c0-o0) > abs(c1-o1)) and (abs(c1-o1) > abs(c2-o2))
                conf = 65 if accel else 55
                return "put", conf

    return None,0
