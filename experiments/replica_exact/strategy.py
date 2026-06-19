#!/usr/bin/env python3

import sys, os, time, math, json, copy, numpy as np
import pandas as pd
import pandas_ta as ta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

NAME = "replica_exact"

# Global cache for tuned parameters per asset
_tuned_params_cache = {}
_last_tune_time = {}

def calculate_adaptive_regime_signals(df, fast_rsi_len, slow_rsi_len, adx_len):
    """Exact copy of real bot's signal generation - dual RSI + ADX regime switching"""
    if len(df) < max(fast_rsi_len, slow_rsi_len, adx_len) + 15:
        return pd.DataFrame()

    close = df['close']
    high = df['max']
    low = df['min']

    adx_df = ta.adx(high, low, close, length=adx_len)
    if adx_df is None or adx_df.empty:
        return pd.DataFrame()
    adx_col = [col for col in adx_df.columns if "ADX" in col][0]
    adx = adx_df[adx_col]

    fast_rsi = ta.rsi(close, length=fast_rsi_len)
    slow_rsi = ta.rsi(close, length=slow_rsi_len)

    if fast_rsi is None or slow_rsi is None or fast_rsi.empty or slow_rsi.empty:
        return pd.DataFrame()

    fast_rsi_prev = fast_rsi.shift(1)
    slow_rsi_prev = slow_rsi.shift(1)
    cross_up = ((fast_rsi_prev <= slow_rsi_prev) & (fast_rsi > slow_rsi)).fillna(False)
    cross_dn = ((fast_rsi_prev >= slow_rsi_prev) & (fast_rsi < slow_rsi)).fillna(False)

    regime = np.where(adx > 25, "trending", "ranging")
    signals = np.full(len(df), "neutral", dtype=object)
    is_ranging = (regime == "ranging")
    is_trending = (regime == "trending")

    call_ranging = is_ranging & (slow_rsi < 40) & cross_up
    put_ranging = is_ranging & (slow_rsi > 60) & cross_dn
    call_trending = is_trending & (slow_rsi > 50) & cross_up
    put_trending = is_trending & (slow_rsi < 50) & cross_dn

    signals[call_ranging | call_trending] = "call"
    signals[put_ranging | put_trending] = "put"

    warmup_mask = (np.arange(len(df)) < 20) | slow_rsi.isna()
    signals[warmup_mask] = "neutral"

    return pd.DataFrame({
        'close': close, 'adx': adx, 'regime': regime,
        'fast_rsi': fast_rsi, 'slow_rsi': slow_rsi,
        'cross_up': cross_up, 'cross_dn': cross_dn,
        'composite_signal': signals
    })


def run_parameter_tuning_sweep(candles):
    """Exact copy of real bot's parameter optimizer - tries 27 combos"""
    if not candles or len(candles) < 100:
        return None

    df_raw = pd.DataFrame(candles)
    df_raw = df_raw.sort_values(by='from').reset_index(drop=True)

    best_score = 0.0
    best_params = None
    close_vals = df_raw['close'].values

    fast_options = [3, 5, 7]
    slow_options = [10, 14, 21]
    adx_options = [10, 14, 20]

    for fast_len in fast_options:
        for slow_len in slow_options:
            for adx_len in adx_options:
                analyzed = calculate_adaptive_regime_signals(df_raw, fast_len, slow_len, adx_len)
                if analyzed.empty:
                    continue
                signals = analyzed['composite_signal'].values
                n = len(analyzed)
                if n <= 21:
                    continue

                trade_mask = np.zeros(n, dtype=bool)
                trade_mask[20:-1] = (signals[20:-1] != "neutral")
                trades = np.sum(trade_mask)
                if trades < 5:  # MIN_OPTIMIZATION_TRADES
                    continue

                sig_slice = signals[trade_mask]
                entry_close = close_vals[trade_mask]
                outcome_close = close_vals[np.where(trade_mask)[0] + 1]

                wins_call = (sig_slice == "call") & (outcome_close > entry_close)
                wins_put = (sig_slice == "put") & (outcome_close < entry_close)
                wins = np.sum(wins_call) + np.sum(wins_put)
                wr = wins / trades

                # Bayesian Laplace smoothing
                score = (wins + 2) / (trades + 4)

                if score > best_score:
                    best_score = score
                    best_params = {
                        'FAST_RSI_LENGTH': fast_len, 'SLOW_RSI_LENGTH': slow_len,
                        'ADX_LENGTH': adx_len, 'simulated_wr': wr,
                        'simulated_trades': trades
                    }

    return best_params


def analyze(api, asset, candles):
    """Analyze asset using the exact same logic as the real bot"""
    try:
        global _tuned_params_cache, _last_tune_time

        # ADX regime filter — solid trend required
        if len(candles) >= 30:
            df_adx = pd.DataFrame(candles)
            adx_series = ta.adx(df_adx['max'], df_adx['min'], df_adx['close'], length=14)
            if adx_series is not None and not adx_series.empty:
                adx_val = adx_series.iloc[-1]
                if isinstance(adx_val, (int, float, np.floating)) and not pd.isna(adx_val):
                    if float(adx_val) < 20:
                        return None, 0

        # Check if we need to tune (first time or every 30 min)
        now = time.time()
        last_tune = _last_tune_time.get(asset, 0)
        if asset not in _tuned_params_cache or (now - last_tune) > 1800:
            params = run_parameter_tuning_sweep(candles)
            if params:
                _tuned_params_cache[asset] = params
                _last_tune_time[asset] = now
            elif asset in _tuned_params_cache:
                params = _tuned_params_cache[asset]  # Keep using old params
            else:
                return None
        else:
            params = _tuned_params_cache[asset]

        simulated_wr = params.get('simulated_wr', 0.0)
        if simulated_wr < 0.50:
            return None

        # Get HTF (5-min) candles for trend filter
        try:
            htf_candles = api.get_candles(asset, 300, 60, time.time())
        except:
            return None

        if not htf_candles or len(htf_candles) < 55:
            return None

        df_htf = pd.DataFrame(htf_candles)
        htf_close = df_htf['close']
        htf_ema50 = ta.ema(htf_close, length=50)
        if htf_ema50 is None or htf_ema50.empty or htf_ema50.isna().iloc[-1]:
            return None
            
        htf_bullish = htf_close.iloc[-1] > htf_ema50.iloc[-1]
        htf_bearish = htf_close.iloc[-1] < htf_ema50.iloc[-1]
        if not htf_bullish and not htf_bearish:
            return None

        # Analyze 1-min candles with tuned params
        df = pd.DataFrame(candles)
        analyzed_df = calculate_adaptive_regime_signals(
            df, params['FAST_RSI_LENGTH'], params['SLOW_RSI_LENGTH'], params['ADX_LENGTH']
        )
        if analyzed_df.empty:
            return None

        last_signal = analyzed_df['composite_signal'].iloc[-2]

        if last_signal == "call" and htf_bullish:
            return "call"
        elif last_signal == "put" and htf_bearish:
            return "put"

        return None

    except Exception as e:
        print(f"[REPLICA_EXACT] Error analyzing {asset}: {e}")
        return None
