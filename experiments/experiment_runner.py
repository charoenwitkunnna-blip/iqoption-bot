"""
Experiment Runner — Run any strategy with full stream management + logging
"""
import sys, os, time, logging, threading, json, argparse, importlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from iqoptionapi.stable_api import IQ_Option
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
import pandas_ta as ta
import numpy as np

import config_practice as config

# Per-strategy state
stats = {}
all_assets = {}
subscribed = {}
iq_connection = {}

def get_logger(name):
    """Create a logger with experiment-specific file"""
    logger = logging.getLogger(f"exp_{name}")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        fh = logging.FileHandler(os.path.join(os.path.dirname(__file__), f"{name}_results.log"), mode='a')
        fh.setFormatter(fmt)
        logger.addHandler(fh)
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(ch)
    return logger

def connect():
    """Connect and return (iq, logger)"""
    iq = IQ_Option(config.IQ_OPTION_EMAIL, config.IQ_OPTION_PASSWORD)
    check, reason = iq.connect()
    if not check:
        return None, None
    iq.change_balance("PRACTICE")
    return iq, get_logger("runner")

def get_assets(iq):
    """Get top-paying open assets"""
    try:
        binary_data = iq.get_all_init_v2()
        if not binary_data:
            return [], {}
        import iqoptionapi.constants as OP_code
        raw = []
        for option in ["binary", "blitz"]:
            actives = binary_data.get(option, {}).get("actives", {})
            for aid, active in actives.items():
                parts = str(active.get("name", "")).split(".")
                name = parts[1] if len(parts) > 1 else parts[0]
                enabled = active.get("enabled", False)
                suspended = active.get("is_suspended", False)
                try:
                    if name not in OP_code.ACTIVES:
                        OP_code.ACTIVES[name] = int(aid)
                except:
                    pass
                if enabled and not suspended:
                    raw.append(name)
        payouts = iq.get_all_profit()
        qualified = {}
        for a in raw:
            p = payouts.get(a, {}).get('turbo', payouts.get(a, {}).get('binary', 0))
            if p >= config.MIN_PAYOUT_THRESHOLD:
                qualified[a] = p
        sorted_assets = sorted(qualified.keys(), key=lambda x: qualified[x], reverse=True)[:config.MAX_SCAN_ASSETS]
        return sorted_assets, payouts
    except Exception as e:
        return [], {}

def process_candles(candles_dict):
    if not candles_dict or not isinstance(candles_dict, dict):
        return []
    result = []
    for ts, val in candles_dict.items():
        try:
            ts_int = int(ts)
            result.append({
                'from': ts_int, 'open': float(val.get('open', 0)),
                'close': float(val.get('close', 0)), 'min': float(val.get('min', 0)),
                'max': float(val.get('max', 0)), 'volume': float(val.get('volume', 0))
            })
        except:
            pass
    result.sort(key=lambda x: x['from'])
    return result

def check_trade(iq, order_id, timeout=120):
    start = time.time()
    while time.time() - start < timeout:
        if not iq.check_connect():
            time.sleep(2)
            continue
        try:
            data = iq.get_async_order(order_id)
            if data and data.get("option-closed") != {}:
                msg = data["option-closed"]["msg"]
                return msg["profit_amount"] - msg["amount"]
        except:
            pass
        time.sleep(1)
    return None

def place_trade(iq, asset, action, amount, logger, stats):
    """Place and monitor trade. Returns profit or None."""
    try:
        success, order_id = iq.buy(amount, asset, action, config.EXPIRATION_MINS)
        if not success:
            logger.error(f"Failed: {asset} {action} -> {order_id}")
            return None
        logger.info(f"Placed: {asset} {action} ID={order_id}")
        profit = check_trade(iq, order_id)
        if profit is not None:
            stats['trades'] += 1
            if profit > 0:
                stats['wins'] += 1
            else:
                stats['losses'] += 1
            stats['net'] += profit
            wr = (stats['wins'] / max(stats['trades'], 1)) * 100
            logger.info(f"RESULT: {asset} {'WIN' if profit>0 else 'LOSS'} | "
                        f"P/L:{profit:.2f} | WR:{wr:.1f}% | "
                        f"T:{stats['trades']} W:{stats['wins']} L:{stats['losses']}")
        else:
            logger.warning(f"Timeout: {asset} {action}")
        return profit
    except Exception as e:
        logger.error(f"Trade error: {asset} {action} -> {e}")
        return None

def run_experiment(name, strategy_module, duration_minutes, logger):
    """Run one experiment with full lifecycle management"""
    logger.info(f"=== {name.upper()} START ({duration_minutes} min) ===")
    
    iq = IQ_Option(config.IQ_OPTION_EMAIL, config.IQ_OPTION_PASSWORD)
    check, reason = iq.connect()
    if not check:
        logger.error(f"Connection failed: {reason}")
        return None
    iq.change_balance("PRACTICE")
    
    bal = iq.get_balance()
    logger.info(f"Connected. PRACTICE Balance: {bal}")
    
    evaluate_fn = strategy_module.evaluate_signal
    stats = {'trades': 0, 'wins': 0, 'losses': 0, 'net': 0.0}
    active_trades = set()
    at_lock = threading.Lock()
    
    # Get initial assets and subscribe
    assets, payouts = get_assets(iq)
    if not assets:
        logger.error("No qualified assets")
        return stats
    
    logger.info(f"Top {len(assets)} assets: {assets[:3]}...")
    
    subscribed_set = set()
    for a in assets:
        try:
            iq.start_candles_stream(a, config.TIMEFRAME, config.CANDLE_COUNT)
            iq.start_candles_stream(a, config.HTF_TIMEFRAME, config.CANDLE_COUNT)
            subscribed_set.add(a)
        except:
            pass
    
    logger.info(f"Subscribed to {len(subscribed_set)} assets. Warming buffers...")
    time.sleep(10)
    
    end_time = time.time() + duration_minutes * 60
    cycles = 0
    
    while time.time() < end_time:
        if not iq.check_connect():
            logger.warning("Reconnecting...")
            iq.connect()
            iq.change_balance("PRACTICE")
            time.sleep(5)
            continue
        
        # Refresh asset list every 60s
        if cycles % 12 == 0:
            new_assets, _ = get_assets(iq)
            for a in new_assets:
                if a not in subscribed_set:
                    try:
                        iq.start_candles_stream(a, config.TIMEFRAME, config.CANDLE_COUNT)
                        iq.start_candles_stream(a, config.HTF_TIMEFRAME, config.CANDLE_COUNT)
                        subscribed_set.add(a)
                    except:
                        pass
            # Update assets list
            assets = new_assets
        
        with at_lock:
            if len(active_trades) >= 3:
                time.sleep(config.POLL_INTERVAL)
                continue
        
        # Scan each asset
        for asset in assets[:10]:
            with at_lock:
                if asset in active_trades:
                    continue
            
            try:
                candles_ltf = process_candles(iq.get_realtime_candles(asset, config.TIMEFRAME))
                candles_htf = process_candles(iq.get_realtime_candles(asset, config.HTF_TIMEFRAME))
                
                if len(candles_ltf) < 55:
                    continue
                
                signal = evaluate_fn(candles_ltf, candles_htf, asset)
                
                if signal:
                    with at_lock:
                        if asset not in active_trades:
                            active_trades.add(asset)
                        else:
                            continue
                    
                    # Place and monitor trade
                    def trade_worker():
                        profit = place_trade(iq, asset, signal, config.TRADE_AMOUNT, logger, stats)
                        with at_lock:
                            active_trades.discard(asset)
                    
                    t = threading.Thread(target=trade_worker, daemon=True)
                    t.start()
            except Exception as e:
                logger.warning(f"Error scanning {asset}: {e}")
        
        cycles += 1
        if cycles % 10 == 0:
            remaining = int(end_time - time.time())
            wr = (stats['wins'] / max(stats['trades'], 1)) * 100
            logger.info(f"[HB] {name} | {remaining}s left | Trades:{stats['trades']} WR:{wr:.1f}% Net:{stats['net']:.2f}")
        
        time.sleep(config.POLL_INTERVAL)
    
    final_balance = iq.get_balance()
    logger.info(f"=== {name.upper()} DONE ===")
    logger.info(f"Trades:{stats['trades']} Wins:{stats['wins']} Losses:{stats['losses']}")
    wr = (stats['wins'] / max(stats['trades'], 1)) * 100
    logger.info(f"WR:{wr:.1f}% Net:{stats['net']:.2f}")
    logger.info(f"Balance: {bal} -> {final_balance}")
    
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('strategy', choices=['ml', 'market-structure', 'ensemble', 'v2', 'mean-reversion', 'all'])
    parser.add_argument('--duration', type=int, default=30, help='Minutes per strategy')
    args = parser.parse_args()
    
    strategy_map = {
        'ml': 'ml_strategy.strategy',
        'market-structure': 'market_structure.strategy',
        'ensemble': 'ensemble.strategy',
        'mean-reversion': 'mean_reversion.strategy',
        'v2': 'v2.strategy',
    }
    
    log = get_logger("runner")
    
    if args.strategy == 'all':
        results = []
        for name, mod_path in strategy_map.items():
            log.info(f"\n{'='*60}\n  Starting: {name}\n{'='*60}")
            mod = importlib.import_module(mod_path)
            result = run_experiment(name, mod, args.duration, get_logger(name))
            results.append((name, result))
            if result:
                wr = (result['wins'] / max(result['trades'], 1)) * 100
                log.info(f"\n>>> {name.upper()}: {result['trades']}t WR={wr:.1f}% Net={result['net']:.2f}")
        
        # Final comparison
        log.info(f"\n{'='*70}")
        log.info("  FINAL COMPARISON")
        log.info(f"{'='*70}")
        results.sort(key=lambda x: x[1]['net'] if x[1] else -9999, reverse=True)
        for name, r in results:
            if r and r['trades'] > 0:
                wr = (r['wins'] / r['trades']) * 100
                score = round(r['net'] * wr / 100, 2) if wr > 0 else 0
                log.info(f"  {name:.<20} {r['trades']:>4}t | WR:{wr:>5.1f}% | Net:{r['net']:>+7.2f} | Score:{score:>+7.2f}")
        
        best = results[0]
        log.info(f"\n  BEST: {best[0].upper()} — Net {best[1]['net']:.2f} @ {(best[1]['wins']/best[1]['trades'])*100:.1f}% WR")
    else:
        mod = importlib.import_module(strategy_map[args.strategy])
        run_experiment(args.strategy, mod, args.duration, log)
