#!/usr/bin/env python3
"""Enhanced vectorized features — multi-TF, patterns, lags."""
import numpy as np

def ema_np(data, period):
    k = 2 / (period + 1)
    out = np.full(len(data), np.nan)
    start = 0; count = 0
    for i in range(len(data)):
        if not np.isnan(data[i]):
            count += 1
            if count >= period:
                start = i - period + 1; break
        else:
            count = 0
    else:
        return out
    out[start + period - 1] = np.mean(data[start:start + period])
    for i in range(start + period, len(data)):
        out[i] = data[i] * k + out[i-1] * (1 - k) if not np.isnan(data[i]) else out[i-1]
    return out

def sma_np(data, period):
    out = np.full(len(data), np.nan)
    if len(data) < period: return out
    cs = np.cumsum(data)
    out[period-1:] = (cs[period-1:] - np.concatenate([[0], cs[:-period]])) / period
    return out

def rsi_np(closes, period=14):
    d = np.diff(closes)
    g = np.where(d > 0, d, 0)
    l = np.where(d < 0, -d, 0)
    ag = np.full(len(g), np.nan)
    al = np.full(len(g), np.nan)
    ag[period-1] = np.mean(g[:period])
    al[period-1] = np.mean(l[:period])
    for i in range(period, len(g)):
        ag[i] = (ag[i-1] * (period-1) + g[i]) / period
        al[i] = (al[i-1] * (period-1) + l[i]) / period
    rs = np.where(al > 0, ag / al, 100)
    return np.concatenate([[np.nan], 100 - (100 / (1 + rs))])

def atr_np(h, l, c, period=14):
    tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    out = np.full(len(tr), np.nan)
    out[period-1] = np.mean(tr[:period])
    for i in range(period, len(tr)):
        out[i] = (out[i-1] * (period-1) + tr[i]) / period
    return np.concatenate([[np.nan], out])

def make_all_features(candles, candles_5m=None):
    """Enhanced features including multi-TF, patterns, lags."""
    n = len(candles)
    if n < 60:
        return None, None, None
    
    c = np.array([x['close'] for x in candles])
    h = np.array([x['max'] for x in candles])
    l = np.array([x['min'] for x in candles])
    o = np.array([x['open'] for x in candles])
    
    f = {}
    
    # --- Price returns ---
    for lag in [1,2,3,5,10,15,20,30]:
        r = np.full(n, np.nan)
        r[lag:] = (c[lag:] / c[:-lag] - 1) * 100
        f[f'ret_{lag}'] = r
    
    # --- Candle shape ---
    body = c - o
    rng = h - l
    f['body_pct'] = np.where(c > 0, body / c * 100, 0)
    f['body_ratio'] = np.where(rng > 0, body / rng, 0)
    f['upper_wick'] = np.where(c > 0, (h - np.maximum(c, o)) / c * 100, 0)
    f['lower_wick'] = np.where(c > 0, (np.minimum(c, o) - l) / c * 100, 0)
    
    # --- Candle patterns ---
    # Doji: small body relative to range
    f['is_doji'] = (np.abs(body) / (rng + 1e-10) < 0.1).astype(float)
    # Hammer: small body at top, long lower wick
    f['is_hammer'] = ((np.abs(body) < rng * 0.3) & ((np.minimum(c,o) - l) > np.abs(body) * 2)).astype(float)
    # Engulfing: current body engulfs previous
    prev_body = np.roll(body, 1); prev_body[0] = 0
    f['bullish_engulf'] = ((body > 0) & (prev_body < 0) & (np.abs(body) > np.abs(prev_body))).astype(float)
    f['bearish_engulf'] = ((body < 0) & (prev_body > 0) & (np.abs(body) > np.abs(prev_body))).astype(float)
    
    # --- Consecutive direction ---
    up = (c > o).astype(int)
    consec_up = np.zeros(n)
    consec_down = np.zeros(n)
    for i in range(1, n):
        consec_up[i] = (consec_up[i-1] + 1) if up[i] else 0
        consec_down[i] = (consec_down[i-1] + 1) if not up[i] else 0
    f['consec_up'] = consec_up
    f['consec_down'] = consec_down
    
    # --- RSI ---
    rsi_vals = rsi_np(c, 14)
    f['rsi'] = rsi_vals
    for lag in [1,2,3,5]:
        f[f'rsi_lag{lag}'] = np.roll(rsi_vals, lag)
    f['rsi_slope3'] = rsi_vals - np.roll(rsi_vals, 3)
    f['rsi_slope5'] = rsi_vals - np.roll(rsi_vals, 5)
    
    # --- MACD ---
    ema12 = ema_np(c, 12)
    ema26 = ema_np(c, 26)
    macd_line = ema12 - ema26
    macd_sig = ema_np(macd_line, 9)
    f['macd'] = macd_line
    f['macd_signal'] = macd_sig
    f['macd_hist'] = macd_line - macd_sig
    f['macd_hist_lag1'] = np.roll(macd_line - macd_sig, 1)
    # Crossover
    cross = np.full(n, np.nan)
    for i in range(1, n):
        if not np.isnan(macd_line[i]) and not np.isnan(macd_sig[i]):
            if macd_line[i-1] < macd_sig[i-1] and macd_line[i] > macd_sig[i]:
                cross[i] = 1
            elif macd_line[i-1] > macd_sig[i-1] and macd_line[i] < macd_sig[i]:
                cross[i] = -1
            else:
                cross[i] = 0
    f['macd_cross'] = cross
    
    # --- Bollinger ---
    mid = sma_np(c, 20)
    std20 = np.full(n, np.nan)
    for i in range(19, n):
        std20[i] = np.std(c[i-19:i+1], ddof=0)
    bb_u = mid + 2 * std20
    bb_l = mid - 2 * std20
    f['bb_width'] = np.where(mid > 0, (bb_u - bb_l) / mid * 100, np.nan)
    f['bb_pos'] = np.where((bb_u - bb_l) > 0, (c - bb_l) / (bb_u - bb_l), 0.5)
    f['bb_squeeze'] = (f['bb_width'] < np.roll(f['bb_width'], 10)).astype(float)
    
    # --- EMAs ---
    ema9 = ema_np(c, 9)
    ema21 = ema_np(c, 21)
    ema50 = ema_np(c, 50)
    f['ema9_21'] = np.where(ema21 > 0, (ema9 / ema21 - 1) * 100, np.nan)
    f['ema9_50'] = np.where(ema50 > 0, (ema9 / ema50 - 1) * 100, np.nan)
    f['price_vs_ema21'] = np.where(ema21 > 0, (c / ema21 - 1) * 100, np.nan)
    f['price_vs_ema50'] = np.where(ema50 > 0, (c / ema50 - 1) * 100, np.nan)
    
    # --- ATR / Volatility ---
    atr_vals = atr_np(h, l, c, 14)
    f['atr_pct'] = np.where(c > 0, atr_vals / c * 100, np.nan)
    f['atr_pct_lag5'] = np.roll(f['atr_pct'], 5)
    # Volatility expanding or contracting
    f['vol_expanding'] = (atr_vals > np.roll(atr_vals, 5)).astype(float)
    
    # --- Range ---
    rng20 = sma_np(rng, 20)
    f['range_ratio'] = np.where(rng20 > 0, rng / rng20, 1)
    
    # --- Momentum ---
    for p in [3, 5, 10, 20]:
        f[f'mom_{p}'] = np.full(n, np.nan) if p >= n else np.concatenate([np.full(p, np.nan), c[p:] - c[:-p]])
    
    # --- Higher highs / lower lows ---
    f['hh3'] = ((h > np.roll(h,1)) & (np.roll(h,1) > np.roll(h,2))).astype(float)
    f['ll3'] = ((l < np.roll(l,1)) & (np.roll(l,1) < np.roll(l,2))).astype(float)
    
    # --- Support/Resistance proximity ---
    for lookback in [20, 50]:
        sr_dist = np.full(n, np.nan)
        for i in range(lookback, n):
            recent_high = np.max(h[i-lookback:i])
            recent_low = np.min(l[i-lookback:i])
            dist_h = abs(c[i] - recent_high) / c[i] * 100
            dist_l = abs(c[i] - recent_low) / c[i] * 100
            sr_dist[i] = min(dist_h, dist_l)
        f[f'sr_prox_{lookback}'] = sr_dist
    
    # --- Multi-timeframe features (5m indicators mapped to 1m) ---
    if candles_5m and len(candles_5m) > 60:
        c5 = np.array([x['close'] for x in candles_5m])
        rsi5 = rsi_np(c5, 14)
        ema9_5 = ema_np(c5, 9)
        ema21_5 = ema_np(c5, 21)
        
        # Map 5m indicators to 1m by repeating each 5m value 5 times
        # Each 1m candle i maps to 5m candle i//5
        for i_1m in range(n):
            i_5m = min(i_1m // 5, len(c5) - 1)
            if i_5m < len(rsi5) and not np.isnan(rsi5[i_5m]):
                pass  # will set below
        
        rsi5_mapped = np.array([rsi5[min(i//5, len(rsi5)-1)] if min(i//5, len(rsi5)-1) < len(rsi5) else np.nan for i in range(n)])
        ema_cross_5 = np.where(
            np.array([ema21_5[min(i//5, len(ema21_5)-1)] if min(i//5, len(ema21_5)-1) < len(ema21_5) else np.nan for i in range(n)]) > 0,
            (np.array([ema9_5[min(i//5, len(ema9_5)-1)] if min(i//5, len(ema9_5)-1) < len(ema9_5) else np.nan for i in range(n)]) /
             np.array([ema21_5[min(i//5, len(ema21_5)-1)] if min(i//5, len(ema21_5)-1) < len(ema21_5) else np.nan for i in range(n)]) - 1) * 100,
            np.nan
        )
        f['mtf_rsi5'] = rsi5_mapped
        f['mtf_ema_cross5'] = ema_cross_5
    
    # Stack
    names = sorted(f.keys())
    matrix = np.column_stack([f[k] for k in names])
    valid = ~np.any(np.isnan(matrix), axis=1)
    
    return matrix, names, valid

def make_training_labels(candles, forward=3):
    c = np.array([x['close'] for x in candles])
    n = len(c)
    labels = np.full(n, np.nan)
    labels[:n-forward] = (c[forward:] > c[:n-forward]).astype(float)
    return labels
