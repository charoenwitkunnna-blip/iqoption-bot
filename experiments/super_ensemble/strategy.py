#!/usr/bin/env python3
"""Ensemble strategy: VOTE of ALL working strategies"""
import sys, os, json, importlib
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

NAME = "super_ensemble"

# Load sub-strategies once
_strategies = {}
_dir = os.path.dirname(os.path.abspath(__file__))

for s in ["v2", "replica_exact", "market_structure"]:
    try:
        spec = importlib.util.spec_from_file_location(s, f"{_dir}/../{s}/strategy.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _strategies[s] = mod
    except:
        pass

def analyze(api, asset, candles):
    """Requires 3 strategies to agree (or all available)"""
    if len(_strategies) == 0:
        return None
    
    votes_call = 0
    votes_put = 0
    total_confidence = 0
    
    for name, strat in _strategies.items():
        try:
            result = strat.analyze(api, asset, candles)
            if isinstance(result, (tuple, list)):
                direction, conf = result[0], int(result[1]) if len(result) > 1 else 50
            else:
                direction, conf = result, 50
            
            if direction == "call":
                votes_call += 1
                total_confidence += conf
            elif direction == "put":
                votes_put += 1
                total_confidence += conf
        except:
            continue
    
    min_votes = max(2, len(_strategies) - 1)  # Need at least 2 to agree
    
    if votes_call >= min_votes:
        avg_conf = total_confidence / votes_call if votes_call else 70
        return "call", min(99, int(avg_conf))
    elif votes_put >= min_votes:
        avg_conf = total_confidence / votes_put if votes_put else 70
        return "put", min(99, int(avg_conf))
    
    return None
