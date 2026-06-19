#!/usr/bin/env python3
"""
Experiment Quick Start — run an experiment or compare all
Usage:
  python3 run_experiment.py ml --duration 60     # Run ML strategy for 60 min
  python3 run_experiment.py compare --duration 15  # Compare all for 15 min each
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse

parser = argparse.ArgumentParser(description='Run IQ Option bot experiments')
parser.add_argument('action', choices=['ml', 'v2', 'ensemble', 'market-structure', 'compare'],
                    help='Strategy or compare mode')
parser.add_argument('--duration', type=int, default=60,
                    help='Duration in minutes (default: 60)')
parser.add_argument('--logfile', type=str, default=None,
                    help='Custom log file path')

args = parser.parse_args()

if args.action == 'compare':
    from experiments.compare import run_experiment, print_comparison
    STRATEGIES = {
        'ml': 'ml-strategy.strategy',
        'market-structure': 'market-structure.strategy',
        'ensemble': 'ensemble.strategy',
        'v2': 'v2.strategy',
    }
    results = []
    for name, mod_path in STRATEGIES.items():
        print(f"\n>>>> Running {name} for {args.duration} min <<<<")
        r = run_experiment(name, mod_path, args.duration * 60)
        results.append(r)
    print_comparison(results)
else:
    from experiments.experiment_runner import main
    main(args.action, args.duration)
