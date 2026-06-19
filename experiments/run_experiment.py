#!/usr/bin/env python3
"""
Experiment Runner — loads and runs strategies on PRACTICE account.
Usage:
    python3 run_experiment.py [strategy_name] [--hours N]
    
Strategies: ml-strategy, market-structure, ensemble, v2, all
If 'all', runs each strategy sequentially for 30 minutes each.
"""
import sys, os, importlib.util, json, time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger(__name__)

EXPERIMENTS_DIR = Path(__file__).parent
RESULTS_DIR = EXPERIMENTS_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# Strategy loader
def load_strategy(strategy_name):
    """Dynamically load a strategy module"""
    # Map display names to directory names
    dir_map = {
        "ml-strategy": "ml_strategy",
        "market-structure": "market_structure",
    }
    dir_name = dir_map.get(strategy_name, strategy_name)
    path = EXPERIMENTS_DIR / dir_name / "strategy.py"
    if not path.exists():
        log.error(f"Strategy not found: {path}")
        return None
    
    mod_name = strategy_name.replace("-", "_")
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

# Import the API
def connect():
    """Connect to IQ Option with PRACTICE account"""
    from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD, BALANCE_TYPE
    
    from iqoptionapi.stable_api import IQ_Option
    api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
    
    check, reason = api.connect()
    if not check:
        log.error(f"Connection failed: {reason}")
        return None
    
    # Switch to PRACTICE
    api.change_balance(BALANCE_TYPE)
    log.info(f"Connected. Balance: {api.get_balance()} {BALANCE_TYPE}")
    return api

def get_assets(api):
    """Get list of tradeable binary assets"""
    try:
        data = api.get_all_init_v2()
        if not data:
            return ["EURUSD-OTC", "GBPUSD-OTC"]
        
        all_assets = set()
        for option in ["binary", "blitz"]:
            actives = data.get(option, {}).get("actives", {})
            for actives_id, active in actives.items():
                name_field = active.get("name", "")
                parts = str(name_field).split(".")
                name = parts[1] if len(parts) > 1 else parts[0]
                enabled = active.get("enabled", False)
                suspended = active.get("is_suspended", False)
                if enabled and not suspended:
                    all_assets.add(name)
        
        sorted_assets = sorted(list(all_assets))
        
        # Sort by payout using get_all_profit()
        try:
            payouts_dict = api.get_all_profit()
        except:
            payouts_dict = {}
        
        asset_payouts = []
        for a in sorted_assets:
            ap = payouts_dict.get(a, {})
            payout = ap.get('turbo', ap.get('binary', 0))
            asset_payouts.append((a, payout))
        
        asset_payouts.sort(key=lambda x: x[1], reverse=True)
        return [a for a, p in asset_payouts[:15] if p >= 10] or [a for a, p in asset_payouts[:5]]
    except Exception as e:
        log.error(f"Error getting assets: {e}")
        return ["EURUSD-OTC", "GBPUSD-OTC"]

def run_strategy(strategy_name, hours=1):
    """Run a single strategy experiment"""
    mod = load_strategy(strategy_name)
    if not mod:
        return
    
    api = connect()
    if not api:
        return
    
    strategy_label = getattr(mod, 'NAME', strategy_name)
    log.info(f"=== Running strategy: {strategy_label} ===")
    
    # Get practice balance
    balance = api.get_balance()
    log.info(f"Starting balance: {balance}")
    
    # Get assets
    assets = get_assets(api)
    log.info(f"Monitoring assets: {', '.join(assets[:5])}... ({len(assets)} total)")
    
    # Setup risk manager if available (V2)
    risk_mgr = None
    if hasattr(mod, 'RiskManager'):
        base_amount = getattr(mod, 'BASE_AMOUNT', 15)
        risk_mgr = mod.RiskManager()
    else:
        base_amount = getattr(mod, 'BASE_AMOUNT', 15)
    
    results_file = RESULTS_DIR / f"{strategy_label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    stats = {
        "strategy": strategy_label,
        "start_time": datetime.now().isoformat(),
        "assets": assets,
        "trades": [],
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "pnl": 0.0
    }
    
    start_time = time.time()
    max_duration = hours * 3600
    candle_cache = {}
    
    try:
        while time.time() - start_time < max_duration:
            for asset in assets:
                # Get candles (1-minute)
                candles = api.get_candles(asset, 60, 120, time.time())
                if not candles or len(candles) < 30:
                    continue
                
                candle_cache[asset] = candles
                
                try:
                    direction, confidence = mod.analyze(api, asset, candles)
                except Exception as e:
                    continue
                
                if not direction or not confidence:
                    continue
                
                # Calculate position size
                if risk_mgr:
                    can, reason = risk_mgr.can_trade(asset)
                    if not can:
                        continue
                    amount = risk_mgr.calculate_position_size(confidence, balance)
                else:
                    amount = base_amount
                
                if amount <= 0:
                    continue
                
                # Check balance
                balance = api.get_balance()
                if balance < amount:
                    continue
                
                # Place trade
                try:
                    trade_id, trade_check = api.buy(amount, asset, direction, 1)
                    if not trade_check:
                        continue
                    
                    # Wait for result
                    time.sleep(65)  # wait for 1-min expiry
                    
                    result = api.get_async_order(trade_id)
                    if result is None:
                        continue
                    
                    profit = result.get('profit', 0) - amount
                    win = profit > 0
                    
                    stats["total_trades"] += 1
                    stats["wins" if win else "losses"] += 1
                    stats["pnl"] += profit
                    
                    trade_record = {
                        "time": datetime.now().isoformat(),
                        "asset": asset,
                        "direction": direction,
                        "amount": amount,
                        "profit": profit,
                        "confidence": confidence,
                        "strategy": strategy_label
                    }
                    stats["trades"].append(trade_record)
                    
                    if risk_mgr:
                        risk_mgr.record_result(asset, direction, amount, profit, confidence)
                    
                    # Save progress
                    with open(results_file, 'w') as f:
                        json.dump(stats, f, indent=2)
                    
                    log.info(f"{'✅' if win else '❌'} {asset} {direction} x{amount} -> {profit:.1f} ({confidence:.0f}% confidence)")
                    
                    # Small delay between trades
                    time.sleep(5)
                    
                except Exception as e:
                    log.error(f"Trade error on {asset}: {e}")
                    continue
            
            # Wait for next scan cycle
            time.sleep(15)
    
    except KeyboardInterrupt:
        log.info("Interrupted by user")
    
    finally:
        stats["end_time"] = datetime.now().isoformat()
        stats["duration_hours"] = (time.time() - start_time) / 3600
        stats["win_rate"] = (stats["wins"] / stats["total_trades"] * 100) if stats["total_trades"] > 0 else 0
        
        with open(results_file, 'w') as f:
            json.dump(stats, f, indent=2)
        
        win_rate = stats["win_rate"]
        log.info(f"=== {strategy_label} Results ===")
        log.info(f"Trades: {stats['total_trades']} | Wins: {stats['wins']} | Losses: {stats['losses']}")
        log.info(f"Win Rate: {win_rate:.1f}% | PnL: {stats['pnl']:.1f} THB")
        log.info(f"Duration: {stats['duration_hours']:.1f}h")
        log.info(f"Results saved: {results_file}")
    
    api.disconnect()

def compare_results():
    """Compare all experiment results"""
    results_dir = RESULTS_DIR
    result_files = list(results_dir.glob("*.json"))
    
    if not result_files:
        log.info("No results to compare yet. Run some experiments first.")
        return
    
    print("\n" + "="*60)
    print(f"{'Strategy':<25} {'Trades':<8} {'Wins':<8} {'Losses':<8} {'WinRate':<10} {'PnL':<10}")
    print("="*60)
    
    for rf in sorted(result_files):
        with open(rf) as f:
            data = json.load(f)
        wr = data.get('win_rate', 0)
        pnl = data.get('pnl', 0)
        print(f"{data['strategy']:<25} {data['total_trades']:<8} {data['wins']:<8} {data['losses']:<8} {wr:<10.1f}% {pnl:<10.1f}")
    
    print("="*60)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run bot strategy experiments")
    parser.add_argument("strategy", nargs="?", default="all",
                        help="Strategy to run: ml-strategy, market-structure, ensemble, v2, all, compare")
    parser.add_argument("--hours", type=float, default=1.0,
                        help="Hours to run each strategy (default: 1)")
    
    args = parser.parse_args()
    
    if args.strategy == "compare":
        compare_results()
    elif args.strategy == "all":
        for s in ["ml-strategy", "market-structure", "ensemble", "v2"]:
            run_strategy(s, hours=args.hours)
        compare_results()
    else:
        run_strategy(args.strategy, hours=args.hours)
