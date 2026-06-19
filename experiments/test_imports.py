#!/usr/bin/env python3
"""Quick import check for all experiment strategies"""
import sys
sys.path.insert(0, '/root/iqoption-bot')

from experiments.ml_strategy.strategy import evaluate_signal as ml_eval
print(f'ML OK: {ml_eval}')

from experiments.market_structure.strategy import evaluate_signal as ms_eval
print(f'Market Structure OK: {ms_eval}')

from experiments.ensemble.strategy import evaluate_signal as en_eval
print(f'Ensemble OK: {en_eval}')

from experiments.v2.strategy import evaluate_signal as v2_eval
print(f'V2 OK: {v2_eval}')

print('\nAll strategies import successfully!')
