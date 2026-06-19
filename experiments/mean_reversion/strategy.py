"""
Mean Reversion Ensemble Strategy — Designed for Ranging/Low-Volatility Markets (ADX < 25)
=======================================================================================

Combines 4 mean-reversion sub-strategies with weighted voting. All sub-strategies are 
designed for ADX < 25 conditions (no trend required). Works specifically for 1-minute
binary options expiry.

Sub-Strategies (all mean-reversion):
  1. Bollinger Band Mean Reversion (weight: 3) — Primary
  2. Fast RSI(5) Extreme (weight: 2) — Secondary
  3. Williams %R Extreme (weight: 2) — Secondary
  4. CCI Extreme Reversal (weight: 2) — Tertiary

Voting: CALL if score >= +3, PUT if score <= -3
"""
import sys
import os
import time
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import talib
from datetime import datetime

import config_practice as config

NAME = "mean-reversion"

# ---------------------------------------------------------------------------
# Parameters (tunable)
# ---------------------------------------------------------------------------
BB_PERIOD = 20
BB_STDDEV = 2.0
RSI_FAST_PERIOD = 5
RSI_SLOW_PERIOD = 14
WILLIAMS_PERIOD = 14
CCI_PERIOD = 14
STOCH_K = 5
STOCH_D = 3
STOCH_SLOW = 3

# Thresholds
RSI_CALL_OVERSOLD = 25
RSI_PUT_OVERBOUGHT = 75
WILLIAMS_CALL = -85
WILLIAMS_PUT = -15
CCI_CALL = -150
CCI_PUT = 150

# Voting weights
WEIGHT_BB = 3
WEIGHT_RSI = 2
WEIGHT_WILLIAMS = 2
WEIGHT_CCI = 2

# Entry threshold
SCORE_CALL_THRESHOLD = 3
SCORE_PUT_THRESHOLD = -3

# Risk state
_MAX_CONSECUTIVE_LOSSES = 3
_MAX_DAILY_TRADES = 30
consecutive_losses = 0
daily_trades = 0
last_trade_day = None
trade_cooldown_until = 0

logger = logging.getLogger("exp_mean_reversion")
if not logger.handlers:
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(ch)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def is_doji(open_p, close, high, low):
    body = abs(close - open_p)
    candle_range = high - low
    if candle_range == 0:
        return False
    return body / candle_range < 0.1


def calculate_bb(closes):
    upper, middle, lower = talib.BBANDS(closes, timeperiod=BB_PERIOD, nbdevup=BB_STDDEV, nbdevdn=BB_STDDEV)
    return upper, middle, lower


def calculate_fast_rsi(closes):
    return talib.RSI(closes, timeperiod=RSI_FAST_PERIOD)


def calculate_slow_rsi(closes):
    return talib.RSI(closes, timeperiod=RSI_SLOW_PERIOD)


def calculate_williams_r(highs, lows, closes):
    return talib.WILLR(highs, lows, closes, timeperiod=WILLIAMS_PERIOD)


def calculate_cci(highs, lows, closes):
    return talib.CCI(highs, lows, closes, timeperiod=CCI_PERIOD)


def calculate_adx(highs, lows, closes):
    return talib.ADX(highs, lows, closes, timeperiod=14)


def check_circuit_breakers():
    """Return (can_trade: bool, reason: str)"""
    global consecutive_losses, daily_trades, last_trade_day, trade_cooldown_until

    today = datetime.now().date()
    if last_trade_day != today:
        consecutive_losses = 0
        daily_trades = 0
        trade_cooldown_until = 0
        last_trade_day = today

    if daily_trades >= _MAX_DAILY_TRADES:
        return False, "Daily trade limit (%d)" % _MAX_DAILY_TRADES

    if consecutive_losses >= _MAX_CONSECUTIVE_LOSSES:
        return False, "Consecutive losses (%d)" % consecutive_losses

    if time.time() < trade_cooldown_until:
        remaining = int(trade_cooldown_until - time.time())
        return False, "Cooldown %ds remaining" % remaining

    return True, "ok"


def record_trade_outcome(won):
    global consecutive_losses, daily_trades
    if won:
        consecutive_losses = 0
    else:
        consecutive_losses += 1
    daily_trades += 1


def set_cooldown(seconds=60):
    global trade_cooldown_until
    trade_cooldown_until = time.time() + seconds


# ---------------------------------------------------------------------------
# Sub-Strategy 1: Bollinger Band Mean Reversion (weight: 3)
# ---------------------------------------------------------------------------

def bb_mean_reversion(closes, highs, lows):
    """
    CALL: Price touches/closes below lower band, then closes back inside.
           RSI(14) < 45 ensures not catching a falling knife.
           BB width not expanding (no breakout).
    PUT:  Price touches/closes above upper band, then closes back inside.
           RSI(14) > 55 ensures not catching a rising knife.
           BB width not expanding (no breakout).
    """
    if len(closes) < BB_PERIOD + 5:
        return 0
    
    upper, middle, lower = calculate_bb(closes)
    rsi_slow = calculate_slow_rsi(closes)
    
    if np.isnan(upper[-1]) or np.isnan(lower[-1]) or np.isnan(rsi_slow[-1]):
        return 0
    
    bb_width_current = (upper[-1] - lower[-1]) / middle[-1] if middle[-1] != 0 else 0
    bb_width_prev = (upper[-5] - lower[-5]) / middle[-5] if middle[-5] != 0 else 0
    
    # Skip if volatility is expanding (breakout, not reversion)
    if bb_width_current > bb_width_prev * 1.15:
        return 0
    if bb_width_current > 0.15:
        return 0  # too wide, likely volatile breakout
    
    score = 0
    
    # CALL: Price breached lower band and snapped back inside
    price_breached_lower = closes[-2] < lower[-2] or lows[-2] < lower[-2]
    price_back_inside = closes[-1] > lower[-1]
    
    if price_breached_lower and price_back_inside and rsi_slow[-1] < 45:
        score = WEIGHT_BB
    
    # PUT: Price breached upper band and snapped back inside
    price_breached_upper = closes[-2] > upper[-2] or highs[-2] > upper[-2]
    price_back_inside_upper = closes[-1] < upper[-1]
    
    if price_breached_upper and price_back_inside_upper and rsi_slow[-1] > 55:
        score = -WEIGHT_BB
    
    # Alternative: Doji/reversal candle at band edge (lower confidence)
    if score == 0 and len(closes) >= 3:
        if is_doji(opens[-2], closes[-2], highs[-2], lows[-2]):
            if closes[-2] <= lower[-2] + (upper[-2] - lower[-2]) * 0.02 and rsi_slow[-2] < 50:
                score = WEIGHT_BB // 2
            elif closes[-2] >= upper[-2] - (upper[-2] - lower[-2]) * 0.02 and rsi_slow[-2] > 50:
                score = -(WEIGHT_BB // 2)
    
    return score


# ---------------------------------------------------------------------------
# Sub-Strategy 2: Fast RSI(5) Mean Reversion (weight: 2)
# ---------------------------------------------------------------------------

def fast_rsi_reversion(closes):
    """
    CALL: RSI(5) < oversold threshold AND rising AND current candle is green
    PUT:  RSI(5) > overbought threshold AND falling AND current candle is red
    """
    if len(closes) < RSI_FAST_PERIOD + 3:
        return 0
    
    rsi_fast = calculate_fast_rsi(closes)
    
    if np.isnan(rsi_fast[-1]) or np.isnan(rsi_fast[-2]):
        return 0
    
    # CALL: oversold bounce — RSI was low, now rising, candle is green
    if (rsi_fast[-2] <= RSI_CALL_OVERSOLD and
        rsi_fast[-1] > rsi_fast[-2] and
        closes[-1] > closes[-2]):
        
        # Stronger signal if RSI was VERY oversold
        if rsi_fast[-2] <= 15:
            return WEIGHT_RSI
        return WEIGHT_RSI
    
    # PUT: overbought drop — RSI was high, now falling, candle is red
    if (rsi_fast[-2] >= RSI_PUT_OVERBOUGHT and
        rsi_fast[-1] < rsi_fast[-2] and
        closes[-1] < closes[-2]):
        
        if rsi_fast[-2] >= 85:
            return -WEIGHT_RSI
        return -WEIGHT_RSI
    
    return 0


# ---------------------------------------------------------------------------
# Sub-Strategy 3: Williams %R Extreme (weight: 2)
# ---------------------------------------------------------------------------

def williams_extreme(highs, lows, closes):
    """
    CALL: Williams %R < -85 AND rising (crossing back up)
    PUT:  Williams %R > -15 AND falling (crossing back down)
    """
    if len(closes) < WILLIAMS_PERIOD + 3:
        return 0
    
    wr = calculate_williams_r(highs, lows, closes)
    
    if np.isnan(wr[-1]) or np.isnan(wr[-2]):
        return 0
    
    if wr[-2] <= WILLIAMS_CALL and wr[-1] > wr[-2]:
        return WEIGHT_WILLIAMS
    
    if wr[-2] >= WILLIAMS_PUT and wr[-1] < wr[-2]:
        return -WEIGHT_WILLIAMS
    
    return 0


# ---------------------------------------------------------------------------
# Sub-Strategy 4: CCI Extreme Reversal (weight: 2)
# ---------------------------------------------------------------------------

def cci_extreme(highs, lows, closes):
    """
    CALL: CCI < -150 AND now rising (reversal)
    PUT:  CCI > 150 AND now falling (reversal)
    """
    if len(closes) < CCI_PERIOD + 3:
        return 0
    
    cci = calculate_cci(highs, lows, closes)
    
    if np.isnan(cci[-1]) or np.isnan(cci[-2]):
        return 0
    
    if cci[-2] <= CCI_CALL and cci[-1] > cci[-2]:
        return WEIGHT_CCI
    
    if cci[-2] >= CCI_PUT and cci[-1] < cci[-2]:
        return -WEIGHT_CCI
    
    return 0


# ---------------------------------------------------------------------------
# Main Strategy Entry Point
# ---------------------------------------------------------------------------

opens = None  # will be set in evaluate_signal

def evaluate_signal(candles_ltf, candles_htf, asset):
    """
    Main signal evaluation function.
    Returns "call" or "put" if valid signal, None otherwise.
    """
    if len(candles_ltf) < 60:
        return None
    
    # Extract arrays
    global opens
    closes = np.array([c['close'] for c in candles_ltf], dtype=float)
    highs = np.array([c['max'] for c in candles_ltf], dtype=float)
    lows = np.array([c['min'] for c in candles_ltf], dtype=float)
    opens = np.array([c['open'] for c in candles_ltf], dtype=float)
    
    # Circuit breakers
    can_trade, reason = check_circuit_breakers()
    if not can_trade:
        return None
    
    # Market regime detection (for reference only)
    adx = calculate_adx(highs, lows, closes)
    adx_val = adx[-1] if not np.isnan(adx[-1]) else 0
    
    # Get votes from all sub-strategies
    score = 0
    signals_fired = []
    
    # 1. BB Mean Reversion (best for ranging markets)
    bb_score = bb_mean_reversion(closes, highs, lows)
    if bb_score != 0:
        signals_fired.append("BB=%(d)s(%(w)d)" % {"d": "CALL" if bb_score > 0 else "PUT", "w": abs(bb_score)})
    score += bb_score
    
    # 2. Fast RSI(5)
    rsi_score = fast_rsi_reversion(closes)
    if rsi_score != 0:
        signals_fired.append("RSI=%(d)s(%(w)d)" % {"d": "CALL" if rsi_score > 0 else "PUT", "w": abs(rsi_score)})
    score += rsi_score
    
    # 3. Williams %R
    wr_score = williams_extreme(highs, lows, closes)
    if wr_score != 0:
        signals_fired.append("WR=%(d)s(%(w)d)" % {"d": "CALL" if wr_score > 0 else "PUT", "w": abs(wr_score)})
    score += wr_score
    
    # 4. CCI
    cci_score = cci_extreme(highs, lows, closes)
    if cci_score != 0:
        signals_fired.append("CCI=%(d)s(%(w)d)" % {"d": "CALL" if cci_score > 0 else "PUT", "w": abs(cci_score)})
    score += cci_score
    
    # HTF Context Filter (lightweight)
    if candles_htf and len(candles_htf) >= 55 and score != 0:
        htf_closes = np.array([c['close'] for c in candles_htf[-55:]], dtype=float)
        htf_sma50 = np.mean(htf_closes[-50:]) if len(htf_closes) >= 50 else np.mean(htf_closes)
        htf_last_close = htf_closes[-1]
        
        # Only filter if HTF strongly against direction
        if score > 0 and htf_last_close < htf_sma50 * 0.98:
            if score < SCORE_CALL_THRESHOLD + 2:
                score = 0
        elif score < 0 and htf_last_close > htf_sma50 * 1.02:
            if score > SCORE_PUT_THRESHOLD - 2:
                score = 0
    
    # Decision
    if score >= SCORE_CALL_THRESHOLD:
        logger.debug("[MR] %s CALL (score=%d, adx=%.0f, signals=%s)" % (asset, score, adx_val, signals_fired))
        return "call"
    
    elif score <= SCORE_PUT_THRESHOLD:
        logger.debug("[MR] %s PUT (score=%d, adx=%.0f, signals=%s)" % (asset, score, adx_val, signals_fired))
        return "put"
    
    return None


# ---------------------------------------------------------------------------
# Compatibility with experiment_runner.py
# ---------------------------------------------------------------------------

def analyze(api, asset, candles):
    """Wrapper for experiment runner compatibility."""
    direction = evaluate_signal(candles, candles, asset)
    conf = 70.0
    if direction == "call":
        return "call", conf
    elif direction == "put":
        return "put", conf
    return None, 0.0


def run(iq, stats, active_trades, active_trades_lock, last_traded_timestamp):
    """No-op for background runner compatibility."""
    pass
