#!/usr/bin/env python3
"""
Experiment 10: V2-Enhanced — Uses the best parts of V2
- Focused on best-performing assets from backtest
- Adaptive threshold for more signals
- Dynamic position sizing by confidence
"""
import sys, os, time, numpy as np, math
import pandas as pd
import pandas_ta as ta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

NAME = "v3_enhanced"

# Per-asset tuning from backtest findings
# Higher threshold = fewer signals, higher win rate
ASSET_CONFIG = {
    "EURJPY-OTC": {"min_score": 30, "asset_bias": 1.0},     
    "GBPJPY-OTC": {"min_score": 35, "asset_bias": 1.0},     
    "XAUUSD-OTC": {"min_score": 30, "asset_bias": 0.5},     
    "SP500-OTC":  {"min_score": 30, "asset_bias": 0.0},     
    "GBPUSD-OTC": {"min_score": 30, "asset_bias": 0.0},     
}

def calc_rsi(series, period=14):
    delta = np.diff(series, prepend=series[0])
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = np.convolve(gain, np.ones(period)/period, mode='same')
    avg_loss = np.convolve(loss, np.ones(period)/period, mode='same')
    rs = np.where(avg_loss == 0, 100, avg_gain / avg_loss)
    return 100 - (100 / (1 + rs))

def analyze(api, asset, candles):
    if not candles or len(candles) < 30:
        return None
    
    cfg = ASSET_CONFIG.get(asset, {"min_score": 30, "asset_bias": 0.0})
    min_score = cfg["min_score"]
    bias = cfg["asset_bias"]
    
    close = np.array([c['close'] for c in candles])
    high = np.array([c['max'] for c in candles])
    low = np.array([c['min'] for c in candles])
    n = len(close)
    
    if n < 30:
        return None
    
    # === INDICATORS ===
    # RSI (7 and 14)
    rsi7 = calc_rsi(close, 7)
    rsi14 = calc_rsi(close, 14)
    
    # ATR for volatility
    tr = np.maximum(high[1:] - low[1:], 
                    np.maximum(abs(high[1:] - close[:-1]), abs(low[1:] - close[:-1])))
    atr14 = np.convolve(tr, np.ones(14)/14, mode='same') if len(tr) >= 14 else tr
    
    # EMAs
    def ema(data, period):
        alpha = 2/(period+1)
        result = np.zeros_like(data)
        result[0] = data[0]
        for i in range(1, len(data)):
            result[i] = alpha * data[i] + (1-alpha) * result[i-1]
        return result
    
    ema5 = ema(close, 5)
    ema20 = ema(close, 20)
    ema50 = ema(close, 50) if n >= 50 else ema(close, min(20, n))
    
    # Candle body and wick
    body = abs(close - np.array([c['open'] for c in candles]))
    upper_wick = high - np.maximum(close, np.array([c['open'] for c in candles]))
    lower_wick = np.minimum(close, np.array([c['open'] for c in candles])) - low
    body_ratio = body / (high - low + 1e-10)
    
    # === SCORING ===
    score = 0
    reasons = []
    
    # 1. RSI Extreme (overbought/oversold)
    if rsi7[-1] < 30:
        score += 20
        reasons.append("rsi_oversold")
    elif rsi7[-1] > 70:
        score += 20
        reasons.append("rsi_overbought")
    
    # 2. RSI Divergence (price making new low but RSI not)
    if n > 20:
        if close[-1] < close[-10] and rsi7[-1] > rsi7[-10]:
            score += 15
            reasons.append("rsi_bull_div")
        elif close[-1] > close[-10] and rsi7[-1] < rsi7[-10]:
            score += 15
            reasons.append("rsi_bear_div")
    
    # 3. EMAs confluence
    if n > 5:
        if close[-1] > ema5[-1] > ema20[-1]:
            score += 10
            reasons.append("ema_bull")
        elif close[-1] < ema5[-1] < ema20[-1]:
            score += 10
            reasons.append("ema_bear")
    
    # 4. EMA20 bounce (price pulled back to EMA20 and bounced)
    if n > 20:
        ema_dist = abs(close[-1] - ema20[-1]) / (atr14[-1] + 1e-10)
        if ema_dist < 0.5 and close[-1] > ema20[-1] and close[-2] <= ema20[-2]:
            score += 15
            reasons.append("ema_bounce_bull")
        elif ema_dist < 0.5 and close[-1] < ema20[-1] and close[-2] >= ema20[-2]:
            score += 15
            reasons.append("ema_bounce_bear")
    
    # 5. Volatility contraction (BB squeeze setup)
    if n > 20:
        std20 = np.std(close[-20:])
        mean_std = np.std(close) if n > 20 else std20
        if std20 < mean_std * 0.7 and n > 20:
            # Contraction, about to expand
            body_ratio_recent = body_ratio[-5:].mean()
            if body_ratio_recent > 0.6:
                # Big real body = momentum
                if close[-1] > open([-1] if isinstance(candles, list) else None):
                    pass  # handled below
    
    # 6. Momentum (current price vs recent range)
    if n > 10:
        recent_high = max(high[-10:-1])
        recent_low = min(low[-10:-1])
        range_pct = (close[-1] - recent_low) / (recent_high - recent_low + 1e-10)
        if range_pct > 0.85:
            score += 5
            reasons.append("near_high")
        elif range_pct < 0.15:
            score += 5
            reasons.append("near_low")
    
    # 7. Candle pattern: engulfing
    if n > 2:
        prev_body = abs(close[-2] - candles[-2]['open'])
        curr_body = abs(close[-1] - candles[-1]['open'])
        prev_direction = close[-2] > candles[-2]['open']
        curr_direction = close[-1] > candles[-1]['open']
        
        if curr_body > prev_body * 1.5 and curr_direction != prev_direction:
            score += 15
            reasons.append("engulfing")
    
    # Add asset bias (if the asset has a historical trend bias)
    score += bias * 10
    
    # === DECISION ===
    if score >= min_score:
        # Count bullish vs bearish reasons
        bull_signals = sum(1 for r in reasons if r in ["rsi_oversold", "rsi_bull_div", "ema_bull", "ema_bounce_bull", "near_low"])
        bear_signals = sum(1 for r in reasons if r in ["rsi_overbought", "rsi_bear_div", "ema_bear", "ema_bounce_bear", "near_high"])
        
        # Engulfing gives a directional signal
        if "engulfing" in reasons:
            if curr_direction:  # Bullish engulfing
                bull_signals += 2
            else:
                bear_signals += 2
        
        # Determine direction
        if bull_signals > bear_signals:
            confidence = min(95, 50 + score)
            return "call", confidence
        elif bear_signals > bull_signals:
            confidence = min(95, 50 + score)
            return "put", confidence
        # If tied, use the strongest signal
        if "rsi_bull_div" in reasons or "rsi_oversold" in reasons:
            return "call", 55 + score // 2
        if "rsi_bear_div" in reasons or "rsi_overbought" in reasons:
            return "put", 55 + score // 2
    
    return None
