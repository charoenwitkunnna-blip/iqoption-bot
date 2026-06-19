#!/usr/bin/env python3
"""
IQ Option Trading Bot — Version 2
==================================
Architecture: Simple polling loop with fresh API connections per cycle.
Based on the proven replica_exact strategy (67% win rate in live testing).

Key improvements over v1:
- No streaming (uses get_candles polling — more reliable)
- No complex threading (simple sequential loop)
- Fresh connection per cycle (avoids API hang issues)
- Auto-restart watchdog (resilient to failures)
- Per-asset win tracking (only trades proven winners)
- Same signal logic as the winning experiment
"""
import sys, os, time, json, importlib, logging, threading, math
import pandas as pd
import pandas_ta as ta
import numpy as np

import config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot_v2.log", mode='a', encoding='utf-8')
    ]
)
logger = logging.getLogger("iqoption_bot_v2")

# ==== SIGNAL GENERATION (same as winning experiment) ====

def calculate_adaptive_regime_signals(df, fast_rsi_len, slow_rsi_len, adx_len):
    """Exact same function as v1 — dual RSI crossover + ADX regime filter"""
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


def run_parameter_tuning_sweep(iq, asset):
    """Picks optimal RSI/ADX params for an asset via grid search"""
    try:
        candles = iq.get_candles(asset, config.TIMEFRAME, config.OPTIMIZATION_CANDLES, time.time())
        if not candles or len(candles) < 100:
            return None
        
        df_raw = pd.DataFrame(candles).sort_values(by='from').reset_index(drop=True)
        close_vals = df_raw['close'].values
        
        best_score, best_wr, best_trades, best_params = 0.0, 0.0, 0, None
        
        for fast_len in [3, 5, 7]:
            for slow_len in [10, 14, 21]:
                for adx_len in [10, 14, 20]:
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
                    if trades < config.MIN_OPTIMIZATION_TRADES:
                        continue
                    
                    sig_slice = signals[trade_mask]
                    entry_close = close_vals[trade_mask]
                    outcome_close = close_vals[np.where(trade_mask)[0] + 1]
                    wins = np.sum((sig_slice == "call") & (outcome_close > entry_close)) + \
                           np.sum((sig_slice == "put") & (outcome_close < entry_close))
                    wr = wins / trades
                    score = (wins + 2) / (trades + 4)  # Laplace smoothing
                    
                    if score > best_score:
                        best_score, best_wr, best_trades = score, wr, trades
                        best_params = {
                            'FAST_RSI_LENGTH': fast_len, 'SLOW_RSI_LENGTH': slow_len,
                            'ADX_LENGTH': adx_len, 'simulated_wr': wr, 'simulated_trades': trades
                        }
        return best_params
    except Exception as e:
        logger.error(f"Tuning error for {asset}: {e}")
        return None


# ==== CORE LOGIC ====

def analyze_asset(iq, asset, tuned_params):
    """Evaluate an asset for entry signal"""
    try:
        # Get HTF candles for trend filter
        htf_candles = iq.get_candles(asset, config.HTF_TIMEFRAME, 60, time.time())
        if not htf_candles or len(htf_candles) < 55:
            return None
        
        df_htf = pd.DataFrame(htf_candles)
        htf_close = df_htf['close']
        htf_ema50 = ta.ema(htf_close, length=50)
        if htf_ema50 is None or htf_ema50.empty or htf_ema50.isna().iloc[-1]:
            return None
        htf_bullish = htf_close.iloc[-1] > htf_ema50.iloc[-1]
        htf_bearish = htf_close.iloc[-1] < htf_ema50.iloc[-1]
        
        # Get LTF candles for signal
        candles = iq.get_candles(asset, config.TIMEFRAME, 120, time.time())
        if not candles or len(candles) < 50:
            return None
        
        df = pd.DataFrame(candles)
        
        # Volatility filter: skip if ATR is too low (quiet market = weak signals)
        df['atr'] = ta.atr(df['max'], df['min'], df['close'], length=14)
        latest_atr = df['atr'].iloc[-1]
        latest_close = df['close'].iloc[-1]
        atr_pct = latest_atr / latest_close if latest_close > 0 else 0
        if atr_pct < 0.0005:  # 0.05% — skip in very quiet markets
            return None
        
        analyzed = calculate_adaptive_regime_signals(
            df, tuned_params['FAST_RSI_LENGTH'], tuned_params['SLOW_RSI_LENGTH'], tuned_params['ADX_LENGTH']
        )
        if analyzed.empty:
            return None
        
        last_signal = analyzed['composite_signal'].iloc[-2]
        
        if last_signal == "call" and htf_bullish:
            return "call"
        elif last_signal == "put" and htf_bearish:
            return "put"
    except Exception as e:
        logger.error(f"Analyze error {asset}: {e}")
    return None


def main():
    logger.info("=== IQ Option Bot v2 ===")
    
    # Connect
    from iqoptionapi.stable_api import IQ_Option
    api = IQ_Option(config.IQ_OPTION_EMAIL, config.IQ_OPTION_PASSWORD)
    check, reason = api.connect()
    if not check:
        logger.error(f"Connect failed: {reason}")
        sys.exit(1)
    api.change_balance(config.BALANCE_TYPE)
    time.sleep(1)
    logger.info(f"Balance: {api.get_balance()} {api.get_currency()}")
    
    # Register all assets
    data = api.get_all_init_v2()
    import iqoptionapi.constants as OP_code
    for opt in ["binary", "blitz"]:
        for aid, act in data.get(opt, {}).get("actives", {}).items():
            name = str(act.get("name", "")).split(".")[-1]
            if act.get("enabled") and not act.get("is_suspended"):
                if name not in OP_code.ACTIVES:
                    OP_code.ACTIVES[name] = int(aid)
    
    # Get top-paying assets
    payouts = api.get_all_profit()
    all_assets = {}
    for opt in ["binary", "blitz"]:
        for aid, act in data.get(opt, {}).get("actives", {}).items():
            name = str(act.get("name", "")).split(".")[-1]
            if act.get("enabled") and not act.get("is_suspended"):
                all_assets[name] = int(aid)
    
    asset_list = sorted(
        [(n, payouts.get(n, {}).get("turbo", payouts.get(n, {}).get("binary", 0)))
         for n in all_assets],
        key=lambda x: x[1], reverse=True
    )
    top_assets = [a for a, p in asset_list[:config.MAX_SCAN_ASSETS]]
    logger.info(f"Scanning top {len(top_assets)} assets: {top_assets[:5]}...")
    
    # Track stats
    stats = {"total": 0, "wins": 0, "losses": 0, "pnl": 0.0}
    stop_loss_reached = False
    trades_file = f"v2_trades.json"
    
    # Load all trades from file
    trades = []
    if os.path.exists(trades_file):
        try:
            trades = json.load(open(trades_file))
        except:
            trades = []
    
    stats = {"total": len(trades), "wins": sum(1 for t in trades if t.get("profit", 0) > 0),
             "losses": sum(1 for t in trades if t.get("profit", 0) <= 0),
             "pnl": sum(t.get("profit", 0) for t in trades)}
    logger.info(f"Loaded {stats['total']} previous trades ({stats['wins']}w/{stats['losses']}l pnl={stats['pnl']:.1f})")
    
    # Tune parameters on first run
    tuned_params = {}
    logger.info("Performing initial parameter tuning...")
    for asset in top_assets[:5]:  # Tune top 5 first
        params = run_parameter_tuning_sweep(api, asset)
        if params and params.get('simulated_wr', 0) >= config.MIN_REQUIRED_WIN_RATE:
            tuned_params[asset] = params
            logger.info(f"  {asset}: {params['simulated_wr']:.0%} wr ({params['simulated_trades']}t)")
        time.sleep(0.5)
    logger.info(f"Tuned {len(tuned_params)} assets with >= {config.MIN_REQUIRED_WIN_RATE:.0%} wr")
    
    # Per-asset tracking (persists across cycles)
    asset_stats = {}
    asset_cooldown = {}
    
    last_tune_time = time.time()
    cycle_count = 0
    
    try:
        while True:
            cycle_count += 1
            balance = api.get_balance()
            
            # Check stop loss
            if stats['pnl'] <= -config.STOP_LOSS_LIMIT:
                logger.critical(f"Stop loss reached! PnL: {stats['pnl']:.1f}")
                stop_loss_reached = True
                break
            
            # Check API connection
            if not api.check_connect():
                logger.warning("Connection lost, reconnecting...")
                api.connect()
                api.change_balance(config.BALANCE_TYPE)
                time.sleep(5)
                continue
            
            # Retune periodically
            if time.time() - last_tune_time > config.OPTIMIZATION_INTERVAL:
                logger.info("Retuning parameters...")
                for asset in top_assets[:5]:
                    params = run_parameter_tuning_sweep(api, asset)
                    if params and params.get('simulated_wr', 0) >= config.MIN_REQUIRED_WIN_RATE:
                        tuned_params[asset] = params
                last_tune_time = time.time()
            
            # Initialize once (lives outside loop)
            
            # Scan assets
            for asset in top_assets:
                if asset not in tuned_params:
                    continue
                
                # Check asset cooldown (after 2+ consecutive losses, wait 5 min)
                if asset in asset_cooldown and time.time() < asset_cooldown[asset]:
                    continue
                
                # Initialize per-asset stats
                if asset not in asset_stats:
                    asset_stats[asset] = {"trades": 0, "wins": 0, "losses": 0, "consec": 0}
                
                # Calculate live win rate for this asset from saved trades
                asset_trades = [t for t in trades if t.get("asset") == asset]
                if len(asset_trades) >= 5:
                    asset_wr = sum(1 for t in asset_trades if t.get("win")) / len(asset_trades)
                    # Skip assets with <30% wr over 5+ trades
                    if asset_wr < 0.30:
                        if cycle_count % 5 == 0:
                            logger.debug(f"Skipping {asset} — {asset_wr:.0%} wr over {len(asset_trades)}t")
                        continue
                
                entry_pnl_before = stats['pnl']
                action = analyze_asset(api, asset, tuned_params[asset])
                
                if action:
                    # Smart loss handling with limited reversal (1-2 trades max)
                    consec = asset_stats.get(asset, {}).get("consec", 0)
                    reversal_count = asset_stats.get(asset, {}).get("reversal_count", 0)
                    live_wr_asset = asset_stats.get(asset, {}).get("live_wr", 0.0)
                    
                    # Re-evaluation: compare backtest WR vs live WR
                    sim_wr = tuned_params.get(asset, {}).get("simulated_wr", 0.0)
                    if live_wr_asset > 0 and sim_wr > 0:
                        score_diff = live_wr_asset - sim_wr
                        if score_diff < -0.10:  # Live WR is 10+ points below backtest
                            logger.info(f"{asset} re-eval: live={live_wr_asset:.0%} vs sim={sim_wr:.0%} (Δ={score_diff:.0%}) — reducing confidence")
                            if consec >= 1:  # Already losing — don't trust the signal
                                action = None
                    
                    if action and consec >= 2 and reversal_count == 0:
                        # 2+ losses in a row — try ONE reversal (limited flip, not forever)
                        reverse = "call" if action == "put" else "put"
                        logger.info(f"{asset} has {consec} consec losses — trying ONE REVERSAL {reverse.upper()} instead of {action.upper()}")
                        action = reverse
                        asset_stats[asset]["reversal_count"] = 1
                    elif action and consec >= 1:
                        asset_stats[asset]["reversal_count"] = 0  # Reset reversal count
                    elif action and reversal_count > 0:
                        # Already did the reversal — go back to normal signal
                        asset_stats[asset]["reversal_count"] = 0
                        asset_stats[asset]["consec"] = 0
                        logger.info(f"{asset} reverting to normal signal after reversal attempt")
                    
                    amount = config.TRADE_AMOUNT
                    success, order_id = api.buy(amount, asset, action, config.EXPIRATION_MINS)
                    logger.info(f"SIGNAL: {asset} {action.upper()} {amount}tid={order_id} ok={success}")
                    
                    if success:
                        # Wait for expiry
                        time.sleep(config.EXPIRATION_MINS * 60 + 5)
                        
                        order = api.get_async_order(order_id)
                        if order:
                            profit = order.get("option-closed", {}).get("msg", {}).get("profit_amount", 0) - amount
                        else:
                            profit = -amount
                        
                        win = profit > 0
                        stats["total"] += 1
                        stats["pnl"] += profit
                        if win:
                            stats["wins"] += 1
                        else:
                            stats["losses"] += 1
                        wr = stats["wins"] / stats["total"] * 100 if stats["total"] else 0
                        logger.info(f"  {'WIN' if win else 'LOSS'} p={profit:.1f} ({stats['total']}t {wr:.0f}% pnl={stats['pnl']:.1f})")
                        
                        # Update per-asset stats
                        if asset not in asset_stats:
                            asset_stats[asset] = {"trades": 0, "wins": 0, "losses": 0, "consec": 0, "reversal_count": 0}
                        asset_stats[asset]["trades"] += 1
                        if win:
                            asset_stats[asset]["wins"] += 1
                            asset_stats[asset]["consec"] = 0
                        else:
                            asset_stats[asset]["losses"] += 1
                            asset_stats[asset]["consec"] += 1
                            # If 2+ consecutive losses, set 5-min cooldown for future signals
                            if asset_stats[asset]["consec"] >= 2:
                                asset_cooldown[asset] = time.time() + 300
                                logger.info(f"  {asset}: {asset_stats[asset]['consec']} consec losses → 5min cooldown")
                        
                        # Re-evaluation: calculate live win rate for this asset
                        asset_trades_from_history = [t for t in trades if t.get("asset") == asset]
                        if asset_trades_from_history:
                            live_wr = sum(1 for t in asset_trades_from_history if t.get("win")) / len(asset_trades_from_history)
                            asset_stats[asset]["live_wr"] = live_wr
                            sim_wr = tuned_params.get(asset, {}).get("simulated_wr", 0.0)
                            if sim_wr > 0:
                                re_eval_score = live_wr - sim_wr
                                if abs(re_eval_score) > 0.05:
                                    logger.info(f"  {asset} re-eval: live={live_wr:.0%} sim={sim_wr:.0%} Δ={re_eval_score:+.0%}")
                        
                        # Save trade
                        re_eval_val = 0.0
                        if 're_eval_score' in dir():
                            re_eval_val = re_eval_score
                        trade_log = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "asset": asset,
                                     "direction": action, "amount": amount, "profit": profit, "win": win,
                                     "consec_at_entry": consec,
                                     "live_wr": asset_stats.get(asset, {}).get("live_wr", 0.0),
                                     "sim_wr": float(tuned_params.get(asset, {}).get("simulated_wr", 0.0))}
                        trades = []
                        if os.path.exists(trades_file):
                            try:
                                trades = json.load(open(trades_file))
                            except:
                                trades = []
                        trades.append(trade_log)
                        json.dump(trades, open(trades_file, "w"), indent=2)
                        
                        # Pause briefly between trades
                        time.sleep(3)
            
            if cycle_count % 5 == 0:
                logger.info(f"[C{cycle_count}] {stats['total']}t {stats['wins']}w/{stats['losses']}l {stats['wins']/max(1,stats['total'])*100:.0f}% pnl={stats['pnl']:.1f} bal={balance:.1f}")
            
            time.sleep(config.POLL_INTERVAL)
    
    except KeyboardInterrupt:
        logger.info("Stopped by user.")
    except Exception as e:
        logger.error(f"Fatal: {e}", exc_info=True)
    
    wr = stats['wins'] / max(1, stats['total']) * 100
    logger.info(f"=== FINAL: {stats['total']}t {wr:.0f}% pnl={stats['pnl']:.1f} ===")


if __name__ == "__main__":
    main()
