#!/usr/bin/env python3
"""Worker: subprocess for candle/payout fetching. Static asset list, no open_time calls."""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from iqoptionapi.stable_api import IQ_Option

email = os.environ.get('IQ_EMAIL', '')
pwd = os.environ.get('IQ_PASSWORD', '')
mode = sys.argv[1]

ASSETS = [
    'EURUSD-OTC','GBPUSD-OTC','USDCHF-OTC','USDJPY-OTC','AUDUSD-OTC',
    'USDCAD-OTC','NZDUSD-OTC','EURGBP-OTC','EURJPY-OTC','GBPJPY-OTC',
    'EURCHF-OTC','AUDJPY-OTC','CADJPY-OTC','CHFJPY-OTC','NZDJPY-OTC',
    'XAUUSD-OTC','GER30-OTC','UK100-OTC','NOKJPY-OTC','ETHUSD-OTC','XRPUSD-OTC',
    'EURUSD','GBPUSD','USDCHF','USDJPY','AUDUSD','USDCAD','NZDUSD','EURGBP',
    'ETHUSD','XRPUSD','XAUUSD','GER30','UK100',
]

api = IQ_Option(email, pwd)
ok, r = api.connect()
if not ok:
    print(f'CONNECT_FAIL: {r}', file=sys.stderr)
    sys.exit(1)

api.change_balance('PRACTICE')
time.sleep(1)

if mode == 'open':
    # Return all assets with default payout — candles will filter out closed ones
    paying = {a: 87 for a in ASSETS}
    print(json.dumps(paying))

elif mode == 'candles':
    asset = sys.argv[2]
    period = int(sys.argv[3])
    count = int(sys.argv[4])
    try:
        c = api.get_candles(asset, period, count, time.time())
        if c:
            print(json.dumps([[x.get('close',0), x.get('max',0), x.get('min',0), x.get('open',0)] for x in c]))
        else:
            print('[]')
    except Exception as e:
        print(f'CANDLE_ERROR: {e}', file=sys.stderr)
        print('[]')
