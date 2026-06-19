#!/usr/bin/env python3
"""Backtest V2 vs V3 on same data"""
import sys, os, time, json, importlib
import pandas as pd
import numpy as np

BASE_DIR = "/root/iqoption-bot/experiments"
sys.path.insert(0, BASE_DIR)

from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD
from iqoptionapi.stable_api import IQ_Option
api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
api.connect()
api.change_balance("PRACTICE")
time.sleep(1)

# Load both strategies
spec2 = importlib.util.spec_from_file_location("v2", f"{BASE_DIR}/v2/strategy.py")
v2 = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(v2)

spec3 = importlib.util.spec_from_file_location("v3", f"{BASE_DIR}/v3_enhanced/strategy.py")
v3 = importlib.util.module_from_spec(spec3)
spec3.loader.exec_module(v3)

ASSETS = ["EURJPY-OTC", "GBPJPY-OTC", "XAUUSD-OTC", "EURUSD-OTC", "GBPUSD-OTC"]

print(f"{'ASSET':<15} {'V2 SIGS':<10} {'V2 WR':<10} {'V3 SIGS':<10} {'V3 WR':<10}")
print("="*55)

total_v2s, total_v2w, total_v3s, total_v3w = 0,0,0,0

for asset in ASSETS:
    candles = api.get_candles(asset, 60, 1500, time.time())
    if not candles or len(candles) < 200:
        continue
    close = [c['close'] for c in candles]
    
    v2_w, v2_l, v3_w, v3_l = 0,0,0,0
    
    for i in range(150, len(candles)-2):
        window = candles[:i+1]
        
        # V2
        try:
            pred = v2.analyze(api, asset, window)
            if isinstance(pred, (tuple, list)): pred = pred[0]
            if pred in ["call","put"]:
                if (pred=="call" and close[i+1]>close[i]) or (pred=="put" and close[i+1]<close[i]):
                    v2_w += 1
                else:
                    v2_l += 1
        except:
            pass
        
        # V3
        try:
            pred = v3.analyze(api, asset, window)
            if isinstance(pred, (tuple, list)): pred = pred[0]
            if pred in ["call","put"]:
                if (pred=="call" and close[i+1]>close[i]) or (pred=="put" and close[i+1]<close[i]):
                    v3_w += 1
                else:
                    v3_l += 1
        except:
            pass
    
    v2_t = v2_w+v2_l
    v3_t = v3_w+v3_l
    v2r = (v2_w/v2_t*100) if v2_t else 0
    v3r = (v3_w/v3_t*100) if v3_t else 0
    print(f"{asset:<15} {v2_t:<10} {v2r:<10.1f} {v3_t:<10} {v3r:<10.1f}")
    total_v2s += v2_t
    total_v2w += v2_w
    total_v3s += v3_t
    total_v3w += v3_w

print("="*55)
print(f"{'TOTAL':<15} {total_v2s:<10} {(total_v2w/total_v2s*100 if total_v2s else 0):<10.1f} {total_v3s:<10} {(total_v3w/total_v3s*100 if total_v3s else 0):<10.1f}")
