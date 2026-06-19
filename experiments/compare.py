"""
Compare all strategies: run each sequentially for N minutes and output a comparison table
"""
import sys, os, time, json, importlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from iqoptionapi.stable_api import IQ_Option
import config_practice as config

STRATEGIES = {
    'ml': 'ml_strategy.strategy',
    'market-structure': 'market_structure.strategy',
    'ensemble': 'ensemble.strategy',
    'v2': 'v2.strategy',
}

def run_experiment(name, module_path, duration_secs):
    """Run a strategy and return results"""
    print(f"\n{'='*60}")
    print(f"  RUNNING: {name}")
    print(f"{'='*60}")
    
    mod = importlib.import_module(module_path)
    
    # Connect
    iq = IQ_Option(config.IQ_OPTION_EMAIL, config.IQ_OPTION_PASSWORD)
    check, reason = iq.connect()
    if not check:
        return {'name': name, 'error': f'Connection failed: {reason}'}
    iq.change_balance("PRACTICE")
    balance = iq.get_balance()
    print(f"  Connected. PRACTICE Balance: {balance}")
    
    results = {
        'name': name,
        'trades': 0,
        'wins': 0,
        'losses': 0,
        'net': 0.0,
        'balance_start': balance,
        'balance_end': balance,
    }
    
    # Setup shared state
    from experiment_runner import Stats, scan_strategy, get_supported_open_assets
    stats = {'trades': 0, 'wins': 0, 'losses': 0, 'net': 0.0}
    active_trades = set()
    at_lock = __import__('threading').Lock()
    last_traded = {}
    
    end_time = time.time() + duration_secs
    cycles = 0
    
    while time.time() < end_time:
        if not iq.check_connect():
            iq.connect()
            iq.change_balance("PRACTICE")
            time.sleep(5)
            continue
        
        scanned, triggered = scan_strategy(name, iq, stats, active_trades, at_lock, last_traded, mod.evaluate_signal)
        cycles += 1
        
        if cycles % 5 == 0:
            results.update({
                'trades': stats['trades'],
                'wins': stats['wins'],
                'losses': stats['losses'],
                'net': stats['net'],
            })
            wr = (stats['wins'] / max(stats['trades'], 1)) * 100
            remaining = int(end_time - time.time())
            print(f"    [{name}] {remaining}s left | Trades: {stats['trades']} | WR: {wr:.1f}% | Net: {stats['net']:.2f}")
        
        time.sleep(config.POLL_INTERVAL)
    
    results['balance_end'] = iq.get_balance()
    results.update({
        'trades': stats['trades'],
        'wins': stats['wins'],
        'losses': stats['losses'],
        'net': stats['net'],
    })
    
    return results

def print_comparison(all_results):
    """Print a comparison table of all strategy results"""
    print(f"\n{'='*70}")
    print(f"  STRATEGY COMPARISON RESULTS")
    print(f"{'='*70}")
    print(f"{'Strategy':<20} {'Trades':<8} {'Wins':<8} {'Losses':<8} {'WR%':<8} {'Net':<10} {'Rating'}")
    print(f"{'-'*70}")
    
    sorted_results = sorted(all_results, key=lambda r: r.get('net', 0), reverse=True)
    
    for r in sorted_results:
        if 'error' in r:
            print(f"{r['name']:<20} ERROR: {r['error']}")
            continue
        wr = (r['wins'] / max(r['trades'], 1)) * 100
        rating = ''

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--duration', type=int, default=15, help='Minutes per strategy')
    args = parser.parse_args()
    
    all_results = []
    for name, mod_path in STRATEGIES.items():
        result = run_experiment(name, mod_path, args.duration * 60)
        all_results.append(result)
        print(f"\n  {name.upper()} results: {result.get('trades', 0)} trades, {result.get('net', 0):.2f} net")
    
    print_comparison(all_results)
