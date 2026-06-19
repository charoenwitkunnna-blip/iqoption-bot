#!/usr/bin/env python3
"""ML BTC feature engineering — transforms candles into model features."""
import math

def ema(data, period):
    if len(data) < period: return []
    k = 2 / (period + 1)
    result = [sum(data[:period]) / period]
    for val in data[period:]:
        result.append(val * k + result[-1] * (1 - k))
    return result

def sma(data, period):
    if len(data) < period: return []
    return [sum(data[i:i+period]) / period for i in range(len(data) - period + 1)]

def rsi_series(closes, period=14):
    """Full RSI series."""
    if len(closes) < period + 1: return []
    deltas = [closes[i+1] - closes[i] for i in range(len(closes)-1)]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    result = []
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            result.append(100)
        else:
            result.append(100 - (100 / (1 + avg_gain / avg_loss)))
    return result

def bollinger_bands(closes, period=20, std_mult=2):
    if len(closes) < period: return [], [], []
    uppers, mids, lowers = [], [], []
    for i in range(period, len(closes) + 1):
        w = closes[i-period:i]
        mid = sum(w) / period
        std = math.sqrt(sum((x - mid)**2 for x in w) / period)
        uppers.append(mid + std_mult * std)
        mids.append(mid)
        lows_val = mid - std_mult * std
        lowers.append(lows_val)
    return uppers, mids, lowers

def atr_series(candles, period=14):
    if len(candles) < period + 1: return []
    trs = []
    for i in range(1, len(candles)):
        h, l, pc = candles[i]['max'], candles[i]['min'], candles[i-1]['close']
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    result = []
    for i in range(period, len(trs) + 1):
        result.append(sum(trs[i-period:i]) / period)
    return result

def make_features(candles):
    """Turn raw candles into a feature dict for the LATEST candle only."""
    if len(candles) < 50:
        return None
    
    closes = [c['close'] for c in candles]
    highs = [c['max'] for c in candles]
    lows = [c['min'] for c in candles]
    price = closes[-1]
    
    feats = {}
    
    # Price-based
    for lag in [1, 2, 3, 5, 10]:
        if len(closes) > lag:
            feats[f'return_{lag}'] = (closes[-1] / closes[-lag-1] - 1) * 100
    
    # Candle body/features
    body = closes[-1] - candles[-1]['open']
    wick_up = highs[-1] - max(closes[-1], candles[-1]['open'])
    wick_down = min(closes[-1], candles[-1]['open']) - lows[-1]
    rng = highs[-1] - lows[-1]
    feats['body_pct'] = (body / price) * 100 if price else 0
    feats['wick_up_pct'] = (wick_up / price) * 100 if price else 0
    feats['wick_down_pct'] = (wick_down / price) * 100 if price else 0
    feats['body_ratio'] = body / rng if rng > 0 else 0
    
    # RSI
    rsi_vals = rsi_series(closes, 14)
    if rsi_vals:
        feats['rsi'] = rsi_vals[-1]
        if len(rsi_vals) > 3:
            feats['rsi_slope'] = rsi_vals[-1] - rsi_vals[-4]
    
    # MACD
    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    if ema12 and ema26:
        diff = len(ema12) - len(ema26)
        if diff > 0: ema12 = ema12[diff:]
        macd_line = [f - s for f, s in zip(ema12, ema26)]
        sig = ema(macd_line, 9)
        if sig and len(macd_line) >= len(sig):
            feats['macd'] = macd_line[-1]
            feats['macd_signal'] = sig[-1]
            feats['macd_hist'] = macd_line[-1] - sig[-1]
    
    # Bollinger
    uppers, mids, lowers = bollinger_bands(closes, 20, 2)
    if uppers:
        bb_width = (uppers[-1] - lowers[-1]) / mids[-1] * 100
        bb_pos = (price - lowers[-1]) / (uppers[-1] - lowers[-1]) if uppers[-1] != lowers[-1] else 0.5
        feats['bb_width'] = bb_width
        feats['bb_position'] = bb_pos
    
    # EMAs
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    if ema9 and ema21:
        feats['ema_cross'] = (ema9[-1] / ema21[-1] - 1) * 100
    
    # SMA trend
    sma50 = sma(closes, 50)
    if sma50:
        feats['sma50_dist'] = (price / sma50[-1] - 1) * 100
    
    # ATR volatility
    atr_vals = atr_series(candles, 14)
    if atr_vals:
        feats['atr_pct'] = (atr_vals[-1] / price) * 100
    
    # Volume proxy — candle range
    ranges = [highs[i] - lows[i] for i in range(-20, 0)]
    feats['avg_range'] = sum(ranges) / len(ranges)
    feats['range_ratio'] = rng / feats['avg_range'] if feats['avg_range'] > 0 else 1
    
    # Momentum
    for period in [5, 10, 20]:
        if len(closes) > period:
            feats[f'mom_{period}'] = closes[-1] - closes[-period-1]
    
    return feats

def make_training_features(candles, forward=3):
    """Create labeled training data. Label: 1 if price goes up in `forward` candles."""
    if len(candles) < 50 + forward:
        return []
    
    rows = []
    for i in range(50, len(candles) - forward):
        sub = candles[:i+1]
        feats = make_features(sub)
        if feats is None:
            continue
        future_close = candles[i + forward]['close']
        current_close = candles[i]['close']
        label = 1 if future_close > current_close else 0
        feats['label'] = label
        rows.append(feats)
    
    return rows
