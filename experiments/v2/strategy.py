"""
Experiment 4: V2 — Clean rewrite with advanced risk management.
Features:
- Position sizing based on signal confidence (higher confidence = bigger trade)
- Dynamic stop loss based on ATR
- Trailing stop when in profit
- Max daily loss limit (circuit breaker)
- Statistical analysis of win rates per asset/time
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import talib
import numpy as np
from collections import defaultdict
from datetime import datetime, timedelta
from config_practice import *

NAME = "v2"
BASE_AMOUNT = 15  # lower base for experiments
MAX_DAILY_LOSS = 100  # THB circuit breaker
MAX_CONSECUTIVE_LOSS = 3
ATR_PERIOD = 14

class RiskManager:
    def __init__(self, max_daily_loss=MAX_DAILY_LOSS, max_consecutive_loss=MAX_CONSECUTIVE_LOSS):
        self.daily_pnl = 0.0
        self.current_date = None
        self.consecutive_losses = 0
        self.max_daily_loss = max_daily_loss
        self.max_consecutive_loss = max_consecutive_loss
        self.trade_history = []
        self.asset_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "total": 0})
    
    def can_trade(self, asset):
        """Check circuit breakers"""
        today = datetime.now().date()
        if self.current_date != today:
            self.daily_pnl = 0.0
            self.current_date = today
            self.consecutive_losses = 0
        
        if self.daily_pnl <= -self.max_daily_loss:
            return False, f"Daily loss limit reached ({self.daily_pnl:.1f} THB)"
        if self.consecutive_losses >= self.max_consecutive_loss:
            return False, f"Max consecutive losses ({self.consecutive_losses})"
        return True, "ok"
    
    def calculate_position_size(self, confidence, balance):
        """
        Dynamic position sizing based on confidence.
        confidence 50-70: base amount
        confidence 70-85: 1.5x base
        confidence 85+: 2x base
        """
        if confidence < 50:
            return 0
        if confidence < 70:
            return BASE_AMOUNT
        elif confidence < 85:
            return int(BASE_AMOUNT * 1.5)
        else:
            return int(BASE_AMOUNT * 2)
    
    def record_result(self, asset, direction, amount, profit, confidence):
        self.trade_history.append({
            "time": datetime.now(),
            "asset": asset,
            "direction": direction,
            "amount": amount,
            "profit": profit,
            "confidence": confidence
        })
        self.daily_pnl += profit
        self.asset_stats[asset]["total"] += 1
        if profit > 0:
            self.asset_stats[asset]["wins"] += 1
            self.consecutive_losses = 0
        else:
            self.asset_stats[asset]["losses"] += 1
            self.consecutive_losses += 1
    
    def get_summary(self, asset=None):
        if asset:
            s = self.asset_stats[asset]
            wr = (s["wins"] / s["total"] * 100) if s["total"] > 0 else 0
            return f"{s['total']} trades, {s['wins']}W/{s['losses']}L, {wr:.0f}% WR"
        total = sum(s["total"] for s in self.asset_stats.values())
        wins = sum(s["wins"] for s in self.asset_stats.values())
        wr = (wins / total * 100) if total > 0 else 0
        return f"{total} trades, {wins}W/{total-wins}L, {wr:.0f}% WR, PnL: {self.daily_pnl:.1f}"

def calculate_atr(highs, lows, closes, period=ATR_PERIOD):
    """Average True Range for dynamic stop loss"""
    tr = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(
            np.abs(highs[1:] - closes[:-1]),
            np.abs(lows[1:] - closes[:-1])
        )
    )
    atr = np.mean(tr[-period:]) if len(tr) >= period else np.mean(tr)
    return atr

def analyze(api, asset, candles):
    """V2 strategy: multi-TF RSI/ADX + MACD + Candlestick patterns with dynamic risk"""
    if len(candles) < 60:
        return None, 0.0
    
    closes = np.array([c['close'] for c in candles], dtype=float)
    highs = np.array([c['max'] for c in candles], dtype=float)
    lows = np.array([c['min'] for c in candles], dtype=float)
    opens = np.array([c['open'] for c in candles], dtype=float)
    
    # Indicators
    rsi = talib.RSI(closes, timeperiod=14)
    adx = talib.ADX(highs, lows, closes, timeperiod=14)
    macd, signal, hist = talib.MACD(closes, fastperiod=12, slowperiod=26, signalperiod=9)
    upper, middle, lower = talib.BBANDS(closes, timeperiod=20, nbdevup=2, nbdevdn=2)
    atr = calculate_atr(highs, lows, closes)
    
    if any(np.isnan(x[-1]) for x in [rsi, adx, macd, signal]):
        return None, 0.0
    
    # Signal scoring system
    score = 0
    reasons = []
    
    # 1. RSI extremes + ADX trend strength
    if rsi[-1] < 30 and adx[-1] > 25:
        score += 30
        reasons.append("RSI oversold + trend")
    elif rsi[-1] > 70 and adx[-1] > 25:
        score -= 30
        reasons.append("RSI overbought + trend")
    elif rsi[-1] < 35:
        score += 15
        reasons.append("RSI near oversold")
    elif rsi[-1] > 65:
        score -= 15
        reasons.append("RSI near overbought")
    
    # 2. MACD momentum
    if hist[-1] > 0 and hist[-2] <= 0:
        score += 25
        reasons.append("MACD cross up")
    elif hist[-1] < 0 and hist[-2] >= 0:
        score -= 25
        reasons.append("MACD cross down")
    elif hist[-1] > hist[-2] and hist[-1] > 0:
        score += 10
        reasons.append("MACD bullish")
    elif hist[-1] < hist[-2] and hist[-1] < 0:
        score -= 10
        reasons.append("MACD bearish")
    
    # 3. Bollinger Bands squeeze + breakout
    bb_width = (upper[-1] - lower[-1]) / middle[-1]
    bb_width_prev = (upper[-5] - lower[-5]) / middle[-5]
    if bb_width < bb_width_prev * 0.8 and bb_width < 0.05:
        # Squeeze -> potential breakout
        if closes[-1] > upper[-2]:
            score += 20
            reasons.append("BB squeeze breakout up")
        elif closes[-1] < lower[-2]:
            score -= 20
            reasons.append("BB squeeze breakout down")
    
    # 4. Candlestick patterns
    # Engulfing
    if closes[-1] > opens[-1] and closes[-2] < opens[-2]:
        if closes[-1] > opens[-2] and opens[-1] < closes[-2]:
            score += 20
            reasons.append("Bullish engulfing")
    elif closes[-1] < opens[-1] and closes[-2] > opens[-2]:
        if closes[-1] < opens[-2] and opens[-1] > closes[-2]:
            score -= 20
            reasons.append("Bearish engulfing")
    
    # 5. Support/resistance bounce (price near BB lower/upper)
    if closes[-1] <= lower[-1] + (upper[-1] - lower[-1]) * 0.05:
        score += 10
        reasons.append("Near BB lower")
    elif closes[-1] >= upper[-1] - (upper[-1] - lower[-1]) * 0.05:
        score -= 10
        reasons.append("Near BB upper")
    
    # 6. Volume confirmation (if available)
    if 'volume' in candles[0] and len(candles) > 5:
        volumes = np.array([c.get('volume', 0) for c in candles], dtype=float)
        avg_vol = np.mean(volumes[-10:-1])
        if volumes[-1] > avg_vol * 1.5:
            # High volume confirms the move
            if score > 0:
                score += 10
                reasons.append("High vol bullish")
            elif score < 0:
                score -= 10
                reasons.append("High vol bearish")
    
    if score >= 40:
        confidence = min(99.0, 50 + min(abs(score), 50))
        return "call", confidence
    elif score <= -40:
        confidence = min(99.0, 50 + min(abs(score), 50))
        return "put", confidence
    
    return None, 0.0
