"""
Experiment 2: Market Structure + ICT/SMC Strategy
Order Blocks, Fair Value Gaps, Break of Structure, Liquidity Sweeps
"""
NAME = "market-structure"
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import logging
import numpy as np
import pandas as pd
import pandas_ta as ta

import config_practice as config

logger = logging.getLogger("exp_market_struct")

def detect_swing_points(df, lookback=5):
    """Detect swing highs and lows"""
    highs = df['max'].values
    lows = df['min'].values
    n = len(df)
    
    swing_highs = np.full(n, False)
    swing_lows = np.full(n, False)
    
    for i in range(lookback, n - lookback):
        if highs[i] == max(highs[i-lookback:i+lookback+1]):
            swing_highs[i] = True
        if lows[i] == min(lows[i-lookback:i+lookback+1]):
            swing_lows[i] = True
    
    return swing_highs, swing_lows

def detect_order_blocks(df, swing_highs, swing_lows):
    """Detect Order Blocks (last candle before a swing point)"""
    n = len(df)
    order_blocks_high = np.full(n, np.nan)
    order_blocks_low = np.full(n, np.nan)
    ob_types = np.full(n, "", dtype=object)
    
    close = df['close'].values
    open_p = df['open'].values
    high = df['max'].values
    low = df['min'].values
    
    for i in range(1, n):
        if swing_highs[i]:
            # Bullish OB: last bearish candle before a swing high
            if close[i-1] < open_p[i-1]:
                order_blocks_high[i-1] = high[i-1]
                order_blocks_low[i-1] = low[i-1]
                ob_types[i-1] = "bullish"
        if swing_lows[i]:
            # Bearish OB: last bullish candle before a swing low
            if close[i-1] > open_p[i-1]:
                order_blocks_high[i-1] = high[i-1]
                order_blocks_low[i-1] = low[i-1]
                ob_types[i-1] = "bearish"
    
    return order_blocks_high, order_blocks_low, ob_types

def detect_fvg(df):
    """Detect Fair Value Gaps (3-candle gap in wicks)"""
    n = len(df)
    fvg_up = np.full(n, np.nan)
    fvg_dn = np.full(n, np.nan)
    fvg_up_high = np.full(n, np.nan)
    fvg_up_low = np.full(n, np.nan)
    fvg_dn_high = np.full(n, np.nan)
    fvg_dn_low = np.full(n, np.nan)
    
    for i in range(2, n):
        # Bullish FVG: candle i-2 high < candle i low (gap up)
        if df['max'].iloc[i-2] < df['min'].iloc[i]:
            fvg_up[i] = 1
            fvg_up_high[i] = df['max'].iloc[i-2]
            fvg_up_low[i] = df['min'].iloc[i]
        
        # Bearish FVG: candle i-2 low > candle i high (gap down)
        if df['min'].iloc[i-2] > df['max'].iloc[i]:
            fvg_dn[i] = 1
            fvg_dn_high[i] = df['min'].iloc[i-2]
            fvg_dn_low[i] = df['max'].iloc[i]
    
    return fvg_up, fvg_dn, fvg_up_high, fvg_up_low, fvg_dn_high, fvg_dn_low

def detect_break_of_structure(df, swing_highs, swing_lows):
    """Detect Break of Structure (BOS)"""
    n = len(df)
    bos_up = np.full(n, False)
    bos_dn = np.full(n, False)
    
    sh_idx = np.where(swing_highs)[0]
    sl_idx = np.where(swing_lows)[0]
    
    if len(sh_idx) >= 2:
        last_sh = sh_idx[-1]
        prev_sh = sh_idx[-2]
        if df['close'].iloc[last_sh] > df['max'].iloc[prev_sh]:
            bos_up[last_sh] = True
    
    if len(sl_idx) >= 2:
        last_sl = sl_idx[-1]
        prev_sl = sl_idx[-2]
        if df['close'].iloc[last_sl] < df['min'].iloc[prev_sl]:
            bos_dn[last_sl] = True
    
    return bos_up, bos_dn

def detect_liquidity_sweeps(df, swing_highs, swing_lows, lookback=10):
    """Detect liquidity sweeps"""
    n = len(df)
    liq_sweep_up = np.full(n, False)
    liq_sweep_dn = np.full(n, False)
    
    close = df['close'].values
    high = df['max'].values
    low = df['min'].values
    
    for i in range(lookback, n):
        recent_sh_high = [high[j] for j in range(max(0, i-lookback), i) if swing_highs[j]]
        recent_sl_low = [low[j] for j in range(max(0, i-lookback), i) if swing_lows[j]]
        
        if recent_sh_high and high[i] > max(recent_sh_high):
            liq_sweep_up[i] = True
        if recent_sl_low and low[i] < min(recent_sl_low):
            liq_sweep_dn[i] = True
    
    return liq_sweep_up, liq_sweep_dn

def evaluate_signal(candles_ltf, candles_htf, asset):
    """ICT/SMC signal evaluation"""
    df = pd.DataFrame(candles_ltf)
    if len(df) < 30:
        return None
    
    close = df['close'].values
    high = df['max'].values
    low = df['min'].values
    
    # Detect structures
    swing_highs, swing_lows = detect_swing_points(df, lookback=5)
    ob_high, ob_low, ob_types = detect_order_blocks(df, swing_highs, swing_lows)
    fvg_up, fvg_dn, fvg_up_h, fvg_up_l, fvg_dn_h, fvg_dn_l = detect_fvg(df)
    bos_up, bos_dn = detect_break_of_structure(df, swing_highs, swing_lows)
    liq_sweep_up, liq_sweep_dn = detect_liquidity_sweeps(df, swing_highs, swing_lows)
    
    last_idx = len(df) - 1
    signals = []
    
    # Signal 1: Liquidity sweep + Order Block reaction
    if liq_sweep_dn[max(0,last_idx-4):last_idx+1].any():
        # Check if any bullish OB nearby
        ob_recent = ob_types[max(0,last_idx-5):last_idx+1].tolist()
        if "bullish" in ob_recent:
            signals.append("call")
    if liq_sweep_up[max(0,last_idx-4):last_idx+1].any():
        ob_recent = ob_types[max(0,last_idx-5):last_idx+1].tolist()
        if "bearish" in ob_recent:
            signals.append("put")
    
    # Signal 2: FVG + BOS
    if bos_up[max(0,last_idx-4):last_idx+1].any() and not np.isnan(fvg_up[last_idx]):
        signals.append("call")
    if bos_dn[max(0,last_idx-4):last_idx+1].any() and not np.isnan(fvg_dn[last_idx]):
        signals.append("put")
    
    # Signal 3: Price approaching Order Block
    if ob_types[last_idx] == "bullish" and not np.isnan(ob_high[last_idx]):
        if close[last_idx] <= ob_high[last_idx] and close[last_idx] >= ob_low[last_idx]:
            signals.append("call")
    if ob_types[last_idx] == "bearish" and not np.isnan(ob_low[last_idx]):
        if close[last_idx] >= ob_low[last_idx] and close[last_idx] <= ob_high[last_idx]:
            signals.append("put")
    
    # Signal 4: FVG retracement
    if not np.isnan(fvg_up[last_idx]) and fvg_up_l[last_idx] >= close[last_idx] >= fvg_up_h[last_idx]:
        signals.append("call")
    if not np.isnan(fvg_dn[last_idx]) and fvg_dn_h[last_idx] >= close[last_idx] >= fvg_dn_l[last_idx]:
        signals.append("put")
    
    if not signals:
        return None
    
    calls = signals.count("call")
    puts = signals.count("put")
    
    direction = "call" if calls > puts else "put" if puts > calls else None
    if direction is None:
        return None
    
    # HTF filter
    df_htf = pd.DataFrame(candles_htf)
    if len(df_htf) >= 55:
        htf_close = df_htf['close']
        htf_ema50 = ta.ema(htf_close, length=50)
        if htf_ema50 is not None and not htf_ema50.empty and not htf_ema50.isna().iloc[-1]:
            if direction == "call" and htf_close.iloc[-1] <= htf_ema50.iloc[-1]:
                return None
            if direction == "put" and htf_close.iloc[-1] >= htf_ema50.iloc[-1]:
                return None
    
    logger.info(f"[MS] {asset} {direction.upper()} ({len(signals)} signals: {signals})")
    return direction

def analyze(api, asset, candles):
    """Wrapper for experiment runner compatibility"""
    direction = evaluate_signal(candles, candles, asset)
    conf = 65.0  # default confidence for market structure
    if direction == "call":
        return "call", conf
    elif direction == "put":
        return "put", conf
    return None, 0.0


def run(iq, stats, active_trades, active_trades_lock, last_traded_timestamp):
    pass
