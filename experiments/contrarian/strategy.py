#!/usr/bin/env python3
"""
Experiment 8: Contrarian Inverse
Takes the opposite of whatever the replica_exact strategy predicts.
If replica says CALL, this goes PUT and vice versa.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from replica_exact.strategy import analyze as base_analyze

NAME = "contrarian"

def analyze(api, asset, candles):
    result = base_analyze(api, asset, candles)
    if result == "call":
        return "put"
    elif result == "put":
        return "call"
    return None
