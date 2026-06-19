#!/usr/bin/env python3
"""Quant BTC/USD strategy — multi-indicator scoring."""
import json, os, math

# --- Indicator helpers ---

def ema(data, period):
    """Exponential moving average."""
    if len(data) < period:
        return []
    k = 2 / (period + 1)
    result = [sum(data[:period]) / period]
    for val in data[period:]:
        result.append(val * k + result[-1] * (1 - k))
    return result

def sma(data, period):
    """Simple moving average."""
    if len(data) < period:
        return []
    return [sum(data[i:i+period]) / period for i in range(len(data) - period + 1)]

def rsi(closes, period=14):
    """Relative Strength Index."""
    if len(closes) < period + 1:
        return None
    deltas = [closes[i+1] - closes[i] for i in range(len(closes)-1)]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def macd(closes, fast=12, slow=26, signal=9):
    """MACD line, signal line, histogram."""
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    if not ema_fast or not ema_slow:
        return None, None, None
    # Align lengths
    diff = len(ema_fast) - len(ema_slow)
    if diff > 0:
        ema_fast = ema_fast[diff:]
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    sig = ema(macd_line, signal)
    if not sig:
        return macd_line[-1], None, None
    diff2 = len(macd_line) - len(sig)
    if diff2 > 0:
        macd_line = macd_line[diff2:]
    hist = macd_line[-1] - sig[-1]
    return macd_line[-1], sig[-1], hist

def bollinger(closes, period=20, std_mult=2):
    """Bollinger Bands — upper, middle, lower."""
    if len(closes) < period:
        return None, None, None
    window = closes[-period:]
    mid = sum(window) / period
    variance = sum((x - mid) ** 2 for x in window) / period
    std = math.sqrt(variance)
    return mid + std_mult * std, mid, mid - std_mult * std

def atr(candles, period=14):
    """Average True Range."""
    if len(candles) < period + 1:
        return None
    trs = []
    for i in range(1, len(candles)):
        h = candles[i]['max']
        l = candles[i]['min']
        pc = candles[i-1]['close']
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    if len(trs) < period:
        return None
    return sum(trs[-period:]) / period

def support_resistance(candles, lookback=20):
    """Find nearest S/R levels from recent swing highs/lows."""
    if len(candles) < lookback:
        return [], []
    highs = [c['max'] for c in candles[-lookback:]]
    lows = [c['min'] for c in candles[-lookback:]]
    price = candles[-1]['close']
    
    # Find swing highs (local maxima)
    sr_highs = []
    sr_lows = []
    for i in range(2, len(highs) - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            sr_highs.append(highs[i])
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            sr_lows.append(lows[i])
    
    return sr_highs, sr_lows


# --- Main analysis ---

def analyze(api, asset, candles):
    """
    Analyze BTC/USD candles and return (direction, confidence).
    direction: 'call' or 'put' or None
    confidence: 0-100
    """
    if not candles or len(candles) < 50:
        return None, 0
    
    closes = [c['close'] for c in candles]
    price = closes[-1]
    
    score = 0  # positive = CALL, negative = PUT
    signals = []
    
    # --- RSI ---
    r = rsi(closes, 14)
    if r is not None:
        if r < 30:
            score += 2
            signals.append(f"RSI={r:.0f} oversold")
        elif r > 70:
            score -= 2
            signals.append(f"RSI={r:.0f} overbought")
        elif r < 40:
            score += 1
            signals.append(f"RSI={r:.0f} low")
        elif r > 60:
            score -= 1
            signals.append(f"RSI={r:.0f} high")
    
    # --- MACD ---
    macd_val, sig_val, hist = macd(closes)
    if macd_val is not None and sig_val is not None:
        if hist > 0 and macd_val > 0:
            score += 1
            signals.append("MACD bullish")
        elif hist < 0 and macd_val < 0:
            score -= 1
            signals.append("MACD bearish")
        # Crossover detection
        if len(closes) > 2:
            prev_macd, prev_sig, _ = macd(closes[:-1])
            if prev_macd is not None and prev_sig is not None:
                if prev_macd < prev_sig and macd_val > sig_val:
                    score += 2
                    signals.append("MACD bullish cross")
                elif prev_macd > prev_sig and macd_val < sig_val:
                    score -= 2
                    signals.append("MACD bearish cross")
    
    # --- Bollinger Bands ---
    upper, mid, lower = bollinger(closes, 20, 2)
    if upper is not None:
        if price <= lower:
            score += 2
            signals.append(f"Price at lower BB ({lower:.0f})")
        elif price >= upper:
            score -= 2
            signals.append(f"Price at upper BB ({upper:.0f})")
        elif price < mid:
            score += 0.5
        elif price > mid:
            score -= 0.5
    
    # --- EMA crossover (9/21) ---
    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    if ema9 and ema21:
        if ema9[-1] > ema21[-1]:
            score += 1
            signals.append("EMA9>EMA21")
        else:
            score -= 1
            signals.append("EMA9<EMA21")
    
    # --- Support/Resistance proximity ---
    highs, lows = support_resistance(candles, 20)
    sr_threshold = price * 0.001  # 0.1% proximity
    near_support = any(abs(price - l) < sr_threshold for l in lows)
    near_resistance = any(abs(price - h) < sr_threshold for h in highs)
    if near_support:
        score += 1.5
        signals.append("Near support")
    if near_resistance:
        score -= 1.5
        signals.append("Near resistance")
    
    # --- ATR volatility filter ---
    a = atr(candles, 14)
    if a is not None:
        volatility_pct = (a / price) * 100
        if volatility_pct > 2:
            signals.append(f"High vol ({volatility_pct:.1f}%)")
        elif volatility_pct < 0.3:
            signals.append(f"Low vol ({volatility_pct:.1f}%)")
            score *= 0.5  # reduce confidence in low vol
    
    # --- Trend (50-period SMA) ---
    sma50 = sma(closes, 50)
    if sma50:
        if price > sma50[-1]:
            score += 0.5
            signals.append("Above SMA50")
        else:
            score -= 0.5
            signals.append("Below SMA50")
    
    # --- Decision ---
    abs_score = abs(score)
    
    # Need minimum 3 confirming signals
    if abs_score < 3:
        return None, 0
    
    direction = 'call' if score > 0 else 'put'
    # Map score to confidence (3 = 70, 5 = 80, 7+ = 90)
    confidence = min(70 + (abs_score - 3) * 5, 95)
    
    # Save analysis for debugging
    debug = {
        "price": price,
        "score": score,
        "signals": signals,
        "rsi": r,
        "macd": macd_val,
        "bb": (upper, mid, lower),
    }
    
    return direction, confidence
