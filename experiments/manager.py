"""
UNIVERSAL TRADE MANAGER
=======================
Lightweight execution engine. Takes a strategy module that exports
generate_signals(), executes the top signal, manages logging.

Usage:
  python3 manager.py <strategy_name>
  python3 manager.py rho_bounce_v2

New pattern: strategy exports generate_signals(api) -> [signals]
Legacy pattern: strategy exports analyze(api, asset, candles, htf) -> (dir, conf)

The manager handles all execution, logging, and error recovery.
"""
import sys
import os
import json
import time
import importlib.util

# --- Config ---
AMOUNT = 5
EXPIRY = 1          # Minutes
CONFIDENCE_FLOOR = 60
BALANCE = 'PRACTICE'
LOG_DIR = os.path.join(os.path.dirname(__file__), 'results')
os.makedirs(LOG_DIR, exist_ok=True)


def log(msg, log_file=None):
    ts = time.strftime('%H:%M:%S')
    line = f"{ts} {msg}"
    if log_file:
        with open(log_file, 'a') as f:
            f.write(line + '\n')
    print(line)


def check_win(api, trade_id):
    """Safely check trade result — handles array return from API."""
    try:
        result = api.check_win_digital_v2(trade_id)
        if isinstance(result, (list, tuple)):
            return bool(result[0])
        return bool(result)
    except:
        return False


def execute_signal(api, signal, log_file):
    """Execute a single trade signal. Returns the trade dict."""
    asset = signal['asset']
    direction = signal['direction']
    confidence = signal.get('confidence', 50)
    amount = signal.get('amount', AMOUNT)

    try:
        ok, trade_id = api.buy(amount, asset, direction, EXPIRY)
        if not ok:
            log(f"  {asset} {direction.upper()} FAIL: {trade_id}", log_file)
            return None
    except Exception as e:
        log(f"  {asset} {direction.upper()} ERROR: {e}", log_file)
        return None

    time.sleep(EXPIRY * 60 + 5)
    win = check_win(api, trade_id)

    payout_pct = signal.get('payout', 87)
    profit = amount * (payout_pct / 100) if win else -amount

    trade = {
        "time": time.strftime('%Y-%m-%d %H:%M:%S'),
        "asset": asset,
        "direction": direction,
        "amount": amount,
        "confidence": confidence,
        "payout": payout_pct,
        "profit": round(profit, 2),
        "win": win,
        "trade_id": trade_id,
    }
    return trade


def load_strategy(name):
    path = os.path.join(os.path.dirname(__file__), 'new_algos', name, 'strategy.py')
    if not os.path.exists(path):
        path = os.path.join(os.getcwd(), 'new_algos', name, 'strategy.py')
    if not os.path.exists(path):
        print(f"ERROR: Strategy not found at {path}")
        sys.exit(1)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def trade_and_log(api, signals, strat_name):
    """Take best signal, execute, log result."""
    log_file = os.path.join(LOG_DIR, f"{strat_name}_live.log")
    trades_file = os.path.join(LOG_DIR, f"{strat_name}_live_trades.json")

    trades = []
    if os.path.exists(trades_file):
        try:
            with open(trades_file) as f:
                trades = json.load(f)
        except:
            trades = []

    if not signals:
        log("No signals", log_file)
        w = sum(1 for t in trades if t['win']) if trades else 0
        t = len(trades)
        pnl = sum(t['profit'] for t in trades) if trades else 0.0
        print(f"DONE: {t}t {w}w/{t-w}l {pnl:+.1f}")
        return

    # Take top signal
    signal = signals[0]
    trade = execute_signal(api, signal, log_file)
    if trade is None:
        w = sum(1 for t in trades if t['win']) if trades else 0
        t = len(trades)
        pnl = sum(t['profit'] for t in trades) if trades else 0.0
        print(f"DONE: {t}t {w}w/{t-w}l {pnl:+.1f}")
        return

    trades.append(trade)
    with open(trades_file, 'w') as f:
        json.dump(trades, f, indent=2)
    w = sum(1 for t in trades if t['win'])
    t_total = len(trades)
    pnl = sum(t['profit'] for t in trades)
    log(f"  {trade['asset']} {trade['direction'].upper()} "
        f"{'WIN' if trade['win'] else 'LOSS'} "
        f"now={w}/{t_total} {w/t_total*100:.0f}% pnl={pnl:+.1f}", log_file)
    print(f"Done: {t_total}t {w}w/{t_total-w}l {pnl:+.1f}")


def run_signals_mode(strat):
    """New pattern: strategy's generate_signals() scans and returns signals."""
    from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD
    from iqoptionapi.stable_api import IQ_Option

    api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
    api.connect()
    api.change_balance(BALANCE)
    time.sleep(2)

    signals = strat.generate_signals(api)
    trade_and_log(api, signals, strat.NAME)

    api._close_connect = lambda: None
    api._close_connect()


def run_legacy_mode(strat):
    """Old pattern: manager scans, calls analyze() per asset."""
    from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD
    from iqoptionapi.stable_api import IQ_Option

    api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
    api.connect()
    api.change_balance(BALANCE)
    time.sleep(2)

    # Scan all assets
    paying = {}
    signals = []
    try:
        all_open = api.get_all_open_time()
        candidates = {k: v for k, v in all_open.get('turbo', {}).items() if v.get('open')}
        paying = {}
        for asset in list(candidates.keys())[:60]:
            try:
                p = api.get_digital_payout(asset)
                if p and p >= 80:
                    paying[asset] = p
            except:
                continue
    except:
        print("Failed to get asset list")
        signals = []
        return

    for asset in sorted(candidates.keys()):
        try:
            candles = api.get_candles(asset, 60, 50, time.time())
            if not candles or len(candles) < 30:
                continue
        except:
            continue
        try:
            htf = None
            try:
                htf = api.get_candles(asset, 300, 10, time.time())
            except:
                pass
            direction, confidence = strat.analyze(api, asset, candles, htf)
        except:
            continue
        if direction and confidence >= CONFIDENCE_FLOOR:
            signals.append({
                "asset": asset,
                "direction": direction,
                "confidence": confidence,
                "payout": paying.get(asset, 87),
                "strategy": strat.NAME,
                "timestamp": time.time()
            })

    signals.sort(key=lambda s: s['confidence'], reverse=True)
    if signals:
        print(f"[signal] {signals[0]['asset']} {signals[0]['direction']} conf={signals[0]['confidence']}")
    trade_and_log(api, signals, strat.NAME)

    api._close_connect = lambda: None
    api._close_connect()


def run_strategy(strat_name):
    """Dispatch: detect strategy pattern and run."""
    strat = load_strategy(strat_name)
    print(f"Loaded strategy: {strat.NAME}")

    if hasattr(strat, 'generate_signals'):
        print("  Using generate_signals() pattern")
        run_signals_mode(strat)
    elif hasattr(strat, 'analyze'):
        print("  Using legacy analyze() pattern")
        run_legacy_mode(strat)
    else:
        print(f"ERROR: Strategy has no generate_signals() or analyze()")
        sys.exit(1)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 manager.py <strategy_name>")
        sys.exit(1)
    run_strategy(sys.argv[1])
