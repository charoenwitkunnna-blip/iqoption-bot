import sys
import os
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from iqoptionapi.stable_api import IQ_Option
import pandas as pd
import pandas_ta as ta
import numpy as np

import config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", mode='a', encoding='utf-8')
    ]
)
logger = logging.getLogger("iqoption_bot")

# Thread-safe global storage for self-tuned parameters
tuned_params_lock = threading.Lock()
tuned_params = {}  # asset -> {'FAST_RSI_LENGTH': x, 'SLOW_RSI_LENGTH': y, 'ADX_LENGTH': z, 'simulated_wr': w}

# Global lock to serialize websocket candle requests and prevent race conditions
get_candles_lock = threading.Lock()

# Shared asset lists managed by main thread, read by optimizer
open_assets_lock = threading.Lock()
open_assets = []

def process_realtime_candles(candles_dict):
    """
    Converts iqoptionapi's dict-based get_realtime_candles format
    into a sorted list of standard dictionary candles using optimized comprehensions.
    """
    if not candles_dict or not isinstance(candles_dict, dict):
        return []
    
    try:
        candles_list = [
            {
                'from': int(ts),
                'open': float(val.get('open', 0)),
                'close': float(val.get('close', 0)),
                'min': float(val.get('min', 0)),
                'max': float(val.get('max', 0)),
                'volume': float(val.get('volume', 0))
            }
            for ts, val in candles_dict.items() if ts.isdigit()
        ]
        candles_list.sort(key=lambda x: x['from'])
        return candles_list
    except Exception:
        # Fallback parsing in case of unexpected websocket data structures
        candles_list = []
        for timestamp, val in candles_dict.items():
            try:
                ts = int(timestamp)
            except ValueError:
                continue
                
            candles_list.append({
                'from': ts,
                'open': float(val.get('open', 0.0)),
                'close': float(val.get('close', 0.0)),
                'min': float(val.get('min', 0.0)),
                'max': float(val.get('max', 0.0)),
                'volume': float(val.get('volume', 0.0))
            })
        candles_list.sort(key=lambda x: x['from'])
        return candles_list

def calculate_adaptive_regime_signals(df, fast_rsi_len, slow_rsi_len, adx_len):
    """
    Calculates indicator values and returns signals for a specific parameter combination.
    Highly optimized using purely vectorized Pandas and NumPy operations.
    """
    if len(df) < max(fast_rsi_len, slow_rsi_len, adx_len) + 15:
        return pd.DataFrame()

    close = df['close']
    high = df['max']
    low = df['min']

    # 1. Trend Strength (ADX)
    adx_df = ta.adx(high, low, close, length=adx_len)
    if adx_df is None or adx_df.empty:
        return pd.DataFrame()
    adx_col = [col for col in adx_df.columns if "ADX" in col][0]
    adx = adx_df[adx_col]

    # 2. Dual RSI momentum lines
    fast_rsi = ta.rsi(close, length=fast_rsi_len)
    slow_rsi = ta.rsi(close, length=slow_rsi_len)

    if fast_rsi is None or slow_rsi is None or fast_rsi.empty or slow_rsi.empty:
        return pd.DataFrame()

    # Vectorized crossover identification
    fast_rsi_prev = fast_rsi.shift(1)
    slow_rsi_prev = slow_rsi.shift(1)
    
    cross_up = ((fast_rsi_prev <= slow_rsi_prev) & (fast_rsi > slow_rsi)).fillna(False)
    cross_dn = ((fast_rsi_prev >= slow_rsi_prev) & (fast_rsi < slow_rsi)).fillna(False)

    # 3. Vectorized Signal Generation
    regime = np.where(adx > 25, "trending", "ranging")
    signals = np.full(len(df), "neutral", dtype=object)

    is_ranging = (regime == "ranging")
    is_trending = (regime == "trending")

    # Range Conditions (Mean Reversion Hooks)
    call_ranging = is_ranging & (slow_rsi < 40) & cross_up
    put_ranging = is_ranging & (slow_rsi > 60) & cross_dn

    # Trend Conditions (Momentum Pullback Continuations)
    call_trending = is_trending & (slow_rsi > 50) & cross_up
    put_trending = is_trending & (slow_rsi < 50) & cross_dn

    # Set composite values
    signals[call_ranging | call_trending] = "call"
    signals[put_ranging | put_trending] = "put"

    # Enforce indicator warm-up phase (first 20 bars, or where slow_rsi is invalid)
    warmup_mask = (np.arange(len(df)) < 20) | slow_rsi.isna()
    signals[warmup_mask] = "neutral"

    # Construct and return output dataframe swiftly
    return pd.DataFrame({
        'close': close,
        'adx': adx,
        'regime': regime,
        'fast_rsi': fast_rsi,
        'slow_rsi': slow_rsi,
        'cross_up': cross_up,
        'cross_dn': cross_dn,
        'composite_signal': signals
    })

def run_parameter_tuning_sweep(iq, asset):
    """
    Downloads historical data and simulates combinations to find the
    optimal parameters. Uses get_candles_lock to prevent I/O race conditions.
    """
    try:
        # Serialize the manual websocket requests to prevent thread clashes
        with get_candles_lock:
            time.sleep(0.1)  # Brief sleep to allow the socket buffer to settle
            candles = iq.get_candles(asset, config.TIMEFRAME, config.OPTIMIZATION_CANDLES, time.time())
            
        if not candles or len(candles) < 100:
            return None
            
        df_raw = pd.DataFrame(candles)
        df_raw = df_raw.sort_values(by='from').reset_index(drop=True)
        
        best_score = 0.0
        best_wr = 0.0
        best_trades = 0
        best_params = None
        
        # Grid search parameters (27 combinations - fast & lightweight)
        fast_options = [3, 5, 7]
        slow_options = [10, 14, 21]
        adx_options = [10, 14, 20]
        
        close_vals = df_raw['close'].values
        
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
                    
                    # Vectorized backtest: evaluate signals from index 20 up to n-2 (inclusive)
                    trade_mask = np.zeros(n, dtype=bool)
                    trade_mask[20:-1] = (signals[20:-1] != "neutral")
                    
                    trades = np.sum(trade_mask)
                    # Enforce the minimum trade count limit
                    if trades < config.MIN_OPTIMIZATION_TRADES:
                        continue
                        
                    # Extract signals, entry closings, and respective outcomes (shift 1)
                    sig_slice = signals[trade_mask]
                    entry_close = close_vals[trade_mask]
                    outcome_close = close_vals[np.where(trade_mask)[0] + 1]
                    
                    wins_call = (sig_slice == "call") & (outcome_close > entry_close)
                    wins_put = (sig_slice == "put") & (outcome_close < entry_close)
                    wins = np.sum(wins_call) + np.sum(wins_put)
                    
                    wr = wins / trades
                    
                    # Bayesian Laplace Smoothing: (wins + 2) / (trades + 4)
                    # This score mathematically rewards setups with high trade density/sample sizes
                    score = (wins + 2) / (trades + 4)
                    
                    if score > best_score:
                        best_score = score
                        best_wr = wr
                        best_trades = trades
                        best_params = {
                            'FAST_RSI_LENGTH': fast_len,
                            'SLOW_RSI_LENGTH': slow_len,
                            'ADX_LENGTH': adx_len,
                            'simulated_wr': wr,
                            'simulated_trades': trades
                        }
                            
        return best_params
    except Exception as e:
        logger.error(f"Error executing parameter optimizer for {asset}: {e}")
        return None

def dynamic_optimization_worker(iq, active_trades_lock, active_trades):
    """
    Concurrently retunes indicator parameters every 5 minutes using a thread pool.
    """
    logger.info("Background dynamic optimization worker thread started.")
    while True:
        try:
            if not iq.check_connect():
                time.sleep(10)
                continue
                
            with open_assets_lock:
                assets_to_optimize = list(open_assets)
                
            if not assets_to_optimize:
                time.sleep(5)
                continue
            
            # Filter out assets with current trades actively running
            with active_trades_lock:
                assets_to_optimize = [a for a in assets_to_optimize if a not in active_trades]
                
            logger.debug(f"[Optimizer] Initiating parallel parameter tuning sweep for: {assets_to_optimize}")
            
            # Execute parameter optimization concurrently
            optimized_results = {}
            with ThreadPoolExecutor(max_workers=min(8, len(assets_to_optimize))) as executor:
                futures = {
                    executor.submit(run_parameter_tuning_sweep, iq, asset): asset 
                    for asset in assets_to_optimize
                }
                for future in as_completed(futures):
                    asset = futures[future]
                    try:
                        params = future.result()
                        optimized_results[asset] = params
                    except Exception as err:
                        logger.error(f"Error processing sweep task for {asset}: {err}")
            
            # Apply optimization updates
            for asset in assets_to_optimize:
                params = optimized_results.get(asset)
                if params:
                    with tuned_params_lock:
                        tuned_params[asset] = params
                    
                    status_text = "APPROVED" if params['simulated_wr'] >= config.MIN_REQUIRED_WIN_RATE else "SUSPENDED (Under 70%)"
                    logger.info(
                        f"[Optimizer] Training complete for {asset}! "
                        f"Optimized WR: {params['simulated_wr']:.2%} "
                        f"({params['simulated_trades']} trades). "
                        f"Status: {status_text} "
                        f"(FastRSI={params['FAST_RSI_LENGTH']}, SlowRSI={params['SLOW_RSI_LENGTH']}, ADX={params['ADX_LENGTH']})"
                    )
                else:
                    with tuned_params_lock:
                        if asset not in tuned_params:
                            tuned_params[asset] = {
                                'FAST_RSI_LENGTH': 5, 
                                'SLOW_RSI_LENGTH': 14, 
                                'ADX_LENGTH': 14, 
                                'simulated_wr': 0.0
                            }
                    logger.warning(f"[Optimizer] Could not find any valid parameter sets for {asset} with at least {config.MIN_OPTIMIZATION_TRADES} trades. Suspending until next sweep.")
                            
            time.sleep(config.OPTIMIZATION_INTERVAL)
        except Exception as e:
            logger.error(f"Critical error in optimization worker thread: {e}")
            time.sleep(30)

def evaluate_smc_strategy(candles_ltf, candles_htf, asset):
    """
    Evaluates the SMC strategy with MTF filters and dynamically trained parameters.
    """
    df_htf = pd.DataFrame(candles_htf)
    if df_htf.empty or len(df_htf) < 55:
        return None
    
    # Input is already pre-sorted from process_realtime_candles
    htf_close = df_htf['close']
    htf_ema50 = ta.ema(htf_close, length=50)
    
    if htf_ema50 is None or htf_ema50.empty or htf_ema50.isna().iloc[-1]:
        return None
        
    htf_bullish = htf_close.iloc[-1] > htf_ema50.iloc[-1]
    htf_bearish = htf_close.iloc[-1] < htf_ema50.iloc[-1]

    with tuned_params_lock:
        asset_cfg = tuned_params.get(asset)

    if not asset_cfg:
        logger.debug(f"Skipping trade evaluation for {asset} - waiting for initial parameter tuning sweep.")
        return None

    simulated_wr = asset_cfg.get('simulated_wr', 0.0)
    if simulated_wr < config.MIN_REQUIRED_WIN_RATE:
        logger.debug(f"Skipping trade evaluation for {asset} - optimized win rate ({simulated_wr:.2%}) is under the 70% threshold.")
        return None

    df = pd.DataFrame(candles_ltf)
    analyzed_df = calculate_adaptive_regime_signals(
        df, 
        fast_rsi_len=asset_cfg['FAST_RSI_LENGTH'], 
        slow_rsi_len=asset_cfg['SLOW_RSI_LENGTH'], 
        adx_len=asset_cfg['ADX_LENGTH']
    )
    
    if analyzed_df.empty:
        return None
        
    last_signal = analyzed_df['composite_signal'].iloc[-2]
    
    if last_signal == "call" and htf_bullish:
        return "call"
    elif last_signal == "put" and htf_bearish:
        return "put"
        
    return None

def connect_to_iq():
    logger.info("Initializing connection to IQ Option...")
    iq = IQ_Option(config.IQ_OPTION_EMAIL, config.IQ_OPTION_PASSWORD)
    
    check, reason = iq.connect()
    if not check:
        logger.error(f"Failed to connect. Reason: {reason}")
        return None
        
    logger.info("Successfully connected to IQ Option!")
    logger.info(f"Switching balance type to {config.BALANCE_TYPE}...")
    iq.change_balance(config.BALANCE_TYPE)
    
    balance = iq.get_balance()
    currency = iq.get_currency()
    logger.info(f"Starting {config.BALANCE_TYPE} Balance: {balance} {currency}")
    return iq

class Stats:
    def __init__(self):
        self.lock = threading.Lock()
        self.total_trades = 0
        self.wins = 0
        self.losses = 0
        self.net_profit = 0.0
        
    def record_trade(self, profit):
        with self.lock:
            self.total_trades += 1
            if profit > 0:
                self.wins += 1
            else:
                self.losses += 1
            self.net_profit += profit
            
    def get_summary(self):
        with self.lock:
            win_rate = (self.wins / self.total_trades * 100) if self.total_trades > 0 else 0.0
            avg_profit = (self.net_profit / self.total_trades) if self.total_trades > 0 else 0.0
            return {
                "total": self.total_trades,
                "wins": self.wins,
                "losses": self.losses,
                "win_rate": win_rate,
                "net_profit": self.net_profit,
                "avg_profit": avg_profit
            }

def check_win_friendly(iq, order_id, timeout=120):
    start_time = time.time()
    while time.time() - start_time < timeout:
        if not iq.check_connect():
            time.sleep(2)
            continue
        try:
            order_data = iq.get_async_order(order_id)
            if order_data and order_data.get("option-closed") != {}:
                msg = order_data["option-closed"]["msg"]
                profit_amount = msg["profit_amount"]
                amount = msg["amount"]
                return profit_amount - amount
        except Exception:
            pass
        time.sleep(1)
    return None

def get_supported_open_assets(iq):
    """
    Retrieves all open assets and dynamically injects them into the API Constants dictionary.
    """
    try:
        binary_data = iq.get_all_init_v2()
        if not binary_data:
            return []
            
        import iqoptionapi.constants as OP_code
        all_open_actives = set()
        
        for option in ["binary", "blitz"]:
            actives = binary_data.get(option, {}).get("actives", {})
            for actives_id, active in actives.items():
                name_field = active.get("name", "")
                parts = str(name_field).split(".")
                name = parts[1] if len(parts) > 1 else parts[0]
                enabled = active.get("enabled", False)
                suspended = active.get("is_suspended", False)
                
                try:
                    if name not in OP_code.ACTIVES:
                        OP_code.ACTIVES[name] = int(actives_id)
                except Exception:
                    pass
                    
                if enabled and not suspended:
                    all_open_actives.add(name)
        
        return sorted(list(all_open_actives))
    except Exception as e:
        logger.error(f"Error getting supported open assets: {e}")
        return []

def monitor_trade_worker(iq, asset, action, amount, stats, active_trades, active_trades_lock):
    logger.info(f"Background worker started for {asset} -> {action.upper()}. Placing trade...")
    try:
        success, order_id = iq.buy(amount, asset, action, config.EXPIRATION_MINS)
        if not success:
            logger.error(f"Failed to place trade on {asset}: {order_id}")
            with active_trades_lock:
                active_trades.discard(asset)
            return

        logger.info(f"Trade successfully placed! Order ID: {order_id}. Monitoring result in background...")
        profit = check_win_friendly(iq, order_id)
        
        if profit is not None:
            stats.record_trade(profit)
            summary = stats.get_summary()
            currency = iq.get_currency()
            status_str = "WIN" if profit > 0 else "LOSS"
            logger.info(f"*** TRADE finalized on {asset} ({action.upper()}): {status_str} | Net Profit: {profit:.2f} {currency} ***")
            logger.info(f"=== PERFORMANCE STATISTICS ===")
            logger.info(f"Total Trades: {summary['total']} | Wins: {summary['wins']} | Losses: {summary['losses']}")
            logger.info(f"Win Rate: {summary['win_rate']:.2f}% | Cumulative Profit: {summary['net_profit']:.2f} {currency}")
            logger.info(f"Average Profit/Trade: {summary['avg_profit']:.2f} {currency}")
            logger.info(f"==============================")
            
            if summary['net_profit'] <= -config.STOP_LOSS_LIMIT:
                logger.critical(f"=== [STOP LOSS REACHED] Net Profit {summary['net_profit']:.2f} <= -{config.STOP_LOSS_LIMIT:.2f}. Shutting down! ===")
                os._exit(0)
        else:
            logger.warning(f"Timeout checking result for trade {order_id} on {asset}.")
            
    except Exception as e:
        logger.error(f"Error in trade worker for {asset}: {e}", exc_info=True)
    finally:
        with active_trades_lock:
            active_trades.discard(asset)

def scan_asset_task(iq, asset, active_trades, active_trades_lock, last_traded_timestamp, stats):
    """
    Scans a single asset concurrently. Evaluates indicators and manages strategy checks.
    """
    with active_trades_lock:
        if asset in active_trades:
            return False, False  # (scanned, triggered)
            
    # Retrieve real-time stream buffers locally
    candles_ltf_raw = iq.get_realtime_candles(asset, config.TIMEFRAME)
    candles_htf_raw = iq.get_realtime_candles(asset, config.HTF_TIMEFRAME)
    
    candles_ltf = process_realtime_candles(candles_ltf_raw)
    candles_htf = process_realtime_candles(candles_htf_raw)
    
    if len(candles_ltf) < 55 or len(candles_htf) < 55:
        return False, False

    closed_candle_time = candles_ltf[-2]['from']
    
    # Thread-safe double-trade validation check
    with active_trades_lock:
        if last_traded_timestamp.get(asset) == closed_candle_time:
            return True, False
            
    with tuned_params_lock:
        current_tuning = tuned_params.get(asset)
        
    if not current_tuning:
        return True, False
        
    if current_tuning.get('simulated_wr', 0.0) < config.MIN_REQUIRED_WIN_RATE:
        return True, False
        
    try:
        action = evaluate_smc_strategy(candles_ltf, candles_htf, asset)
    except Exception as e:
        logger.error(f"Error evaluating SMC strategy for {asset}: {e}")
        return True, False
        
    if action:
        logger.info(
            f"*** SMC SIGNAL TRIGGERED FOR {asset} "
            f"[Approved Model WR: {current_tuning.get('simulated_wr'):.2%}]: "
            f"{action.upper()} ***"
        )
        
        with active_trades_lock:
            if asset in active_trades:
                logger.info(f"Already have an active trade on {asset}. Skipping signal.")
                return True, False
            if last_traded_timestamp.get(asset) == closed_candle_time:
                return True, False
            active_trades.add(asset)
            last_traded_timestamp[asset] = closed_candle_time
        
        # Spawn execution worker
        worker = threading.Thread(
            target=monitor_trade_worker,
            args=(iq, asset, action, config.TRADE_AMOUNT, stats, active_trades, active_trades_lock)
        )
        worker.daemon = True
        worker.start()
        return True, True
        
    return True, False

def main():
    if config.IQ_OPTION_EMAIL == "your_email@example.com" or config.IQ_OPTION_PASSWORD == "your_password_here":
        logger.error("Please configure your actual credentials in your .env file before running.")
        sys.exit(1)
        
    iq = connect_to_iq()
    if iq is None:
        logger.error("Could not establish initial connection. Exiting.")
        sys.exit(1)
        
    logger.info("Bot started in Dynamic Self-Optimizing Multi-Asset Scanning mode.")
    logger.info(f"LTF (Lower Timeframe): {config.TIMEFRAME}s candles.")
    logger.info(f"HTF (Higher Timeframe): {config.HTF_TIMEFRAME}s candles.")
    logger.info(f"Strategy: Self-Tuning SMC Hybrid Dual-Engine")
    
    stats = Stats()
    active_trades = set()
    active_trades_lock = threading.Lock()
    last_traded_timestamp = {}
    
    last_asset_check = 0
    subscribed_assets = set()
    
    # Start background Dynamic Parameter Optimization thread
    opt_thread = threading.Thread(
        target=dynamic_optimization_worker, 
        args=(iq, active_trades_lock, active_trades), 
        daemon=True
    )
    opt_thread.start()
    
    try:
        while True:
            if not iq.check_connect():
                logger.warning("Connection lost! Attempting to reconnect...")
                check, reason = iq.connect()
                if check:
                    logger.info("Reconnected successfully.")
                    iq.change_balance(config.BALANCE_TYPE)
                else:
                    logger.error(f"Reconnection failed: {reason}. Retrying in 10 seconds...")
                    time.sleep(10)
                    continue
            
            current_time = time.time()
            if current_time - last_asset_check > 60:
                logger.info("Refreshing list of open assets and managing streams...")
                raw_open_assets = get_supported_open_assets(iq)
                
                try:
                    payouts = iq.get_all_profit()
                except Exception:
                    payouts = {}
                
                asset_payouts_list = []
                for asset in raw_open_assets:
                    asset_payouts = payouts.get(asset, {}) if payouts else {}
                    payout = asset_payouts.get('turbo', asset_payouts.get('binary', 0))
                    if payout >= config.MIN_PAYOUT_THRESHOLD:
                        asset_payouts_list.append((asset, payout))
                
                asset_payouts_list.sort(key=lambda x: x[1], reverse=True)
                selected_assets = [item[0] for item in asset_payouts_list[:config.MAX_SCAN_ASSETS]]
                
                with open_assets_lock:
                    global open_assets
                    open_assets = selected_assets
                
                last_asset_check = current_time
                logger.info(f"Selected top {len(open_assets)} highest-paying assets for scanning (Limit: {config.MAX_SCAN_ASSETS}): {open_assets}")
                
                for asset in open_assets:
                    if asset not in subscribed_assets:
                        logger.info(f"Subscribing to streams for {asset}...")
                        iq.start_candles_stream(asset, config.TIMEFRAME, config.CANDLE_COUNT)
                        iq.start_candles_stream(asset, config.HTF_TIMEFRAME, config.CANDLE_COUNT)
                        subscribed_assets.add(asset)
                
                for asset in list(subscribed_assets):
                    if asset not in open_assets:
                        logger.info(f"Stopping streams for {asset}...")
                        try:
                            iq.stop_candles_stream(asset, config.TIMEFRAME)
                            iq.stop_candles_stream(asset, config.HTF_TIMEFRAME)
                        except Exception:
                            pass
                        subscribed_assets.discard(asset)
                
                logger.info("Allowing 5 seconds for streaming buffers to warm up...")
                time.sleep(5)
                
            with open_assets_lock:
                assets_to_scan = list(open_assets)
                
            if not assets_to_scan:
                logger.warning("No active tradeable assets found. Retrying in 10 seconds...")
                time.sleep(10)
                continue
                
            summary = stats.get_summary()
            current_profit = summary['net_profit']
            
            if current_profit <= -config.STOP_LOSS_LIMIT:
                logger.critical(f"=== [STOP LOSS REACHED] Net Profit {current_profit:.2f} <= -{config.STOP_LOSS_LIMIT:.2f}. Shutting down! ===")
                sys.exit(0)
                
            with active_trades_lock:
                active_count = len(active_trades)
            
            remaining_loss_allowance = config.STOP_LOSS_LIMIT + current_profit
            max_allowed_trades = max(0, int(remaining_loss_allowance / config.TRADE_AMOUNT))
            
            if active_count >= max_allowed_trades:
                logger.debug(f"Risk exposure control: Active trades ({active_count}) >= Max allowed ({max_allowed_trades}). Skipping scan.")
                time.sleep(config.POLL_INTERVAL)
                continue
                
            # Scan assets in parallel
            scan_start = time.time()
            scanned_count = 0
            
            with ThreadPoolExecutor(max_workers=min(10, len(assets_to_scan))) as executor:
                futures = {
                    executor.submit(
                        scan_asset_task, iq, asset, active_trades, active_trades_lock, last_traded_timestamp, stats
                    ): asset for asset in assets_to_scan
                }
                for future in as_completed(futures):
                    try:
                        scanned, triggered = future.result()
                        if scanned:
                            scanned_count += 1
                    except Exception as e:
                        asset = futures[future]
                        logger.error(f"Error scanning asset {asset} concurrently: {e}")
                    
            scan_duration = time.time() - scan_start
            logger.info(f"Scan cycle completed: {scanned_count}/{len(assets_to_scan)} approved assets scanned in {scan_duration:.2f}s.")
            time.sleep(config.POLL_INTERVAL)
            
    except KeyboardInterrupt:
        logger.info("Stopping real-time candle streams...")
        with open_assets_lock:
            assets_to_stop = list(open_assets)
        for asset in assets_to_stop:
            try:
                iq.stop_candles_stream(asset, config.TIMEFRAME)
                iq.stop_candles_stream(asset, config.HTF_TIMEFRAME)
            except Exception:
                pass
        logger.info("Shutting down the trading bot. Goodbye!")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Unhandled exception occurred: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
