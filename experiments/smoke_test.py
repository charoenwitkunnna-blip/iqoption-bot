#!/usr/bin/env python3
"""Quick signal test for all strategies — efficient version"""
import sys, os, time
sys.path.insert(0, '/root/iqoption-bot')
sys.path.insert(0, '/root/iqoption-bot/experiments')

from experiments.market_structure.strategy import evaluate_signal as ms_eval
from experiments.ensemble.strategy import evaluate_signal as en_eval
from experiments.v2.strategy import evaluate_signal as v2_eval
from experiments.config_practice import *
from experiments.experiment_runner import connect_iq, get_supported_open_assets, process_candles, get_logger

logger = get_logger("smoke_test")
logger.info("=== SIGNAL TEST ===")

iq = connect_iq(logger)
if not iq:
    sys.exit(1)

logger.info("Getting assets...")
assets = get_supported_open_assets(iq)
logger.info(f"Found {len(assets)} open assets")

logger.info("Getting payouts...")
payouts = iq.get_all_profit()

qualified = []
for a in assets:
    p = payouts.get(a, {}).get('turbo', payouts.get(a, {}).get('binary', 0))
    if p >= MIN_PAYOUT_THRESHOLD:
        qualified.append((a, p))

qualified.sort(key=lambda x: x[1], reverse=True)
top = [a[0] for a in qualified[:5]]
logger.info(f"Top 5: {top}")

logger.info("Subscribing to streams...")
for a in top:
    try:
        iq.start_candles_stream(a, TIMEFRAME, CANDLE_COUNT)
        iq.start_candles_stream(a, HTF_TIMEFRAME, CANDLE_COUNT)
    except:
        pass

logger.info("Waiting 8s for buffers...")
time.sleep(8)

strategies = [("MS", ms_eval), ("Ens", en_eval), ("V2", v2_eval)]
signals_found = 0

for asset in top:
    ltf = process_candles(iq.get_realtime_candles(asset, TIMEFRAME))
    htf = process_candles(iq.get_realtime_candles(asset, HTF_TIMEFRAME))
    
    if len(ltf) < 55:
        logger.info(f"{asset}: only {len(ltf)} LTF candles - skipping")
        continue
    
    sigs = []
    for name, fn in strategies:
        try:
            s = fn(ltf, htf, asset)
            if s:
                signals_found += 1
            sigs.append(f"{name}={s or '--'}")
        except Exception as e:
            sigs.append(f"{name}=ERR({e})")
    logger.info(f"{asset}: {' | '.join(sigs)}")

for a in top:
    try: iq.stop_candles_stream(a, TIMEFRAME)
    except: pass
    try: iq.stop_candles_stream(a, HTF_TIMEFRAME)
    except: pass

logger.info(f"Total signals: {signals_found}")
logger.info("=== DONE ===")
