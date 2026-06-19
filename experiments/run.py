#!/usr/bin/env python3
"""Run a single experiment strategy. Usage: python3 run.py ml|ensemble|v2|market-structure [duration_minutes]"""
import sys, os, importlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

strategy = sys.argv[1] if len(sys.argv) > 1 else 'ml'
duration = int(sys.argv[2]) if len(sys.argv) > 2 else 30

module_map = {
    'ml': 'ml_strategy.strategy',
    'market-structure': 'market_structure.strategy',
    'ensemble': 'ensemble.strategy',
    'v2': 'v2.strategy',
}

mod = importlib.import_module(module_map[strategy])
from experiment_runner import run_experiment, get_logger
log = get_logger(strategy)
run_experiment(strategy, mod, duration, log)
