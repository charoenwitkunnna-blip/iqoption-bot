#!/usr/bin/env python3
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

mode = sys.argv[1]  # "open" or "candles"
from iqoptionapi.stable_api import IQ_Option

email = os.environ.get("IQ_EMAIL", "")
pwd = os.environ.get("IQ_PASSWORD", "")
api = IQ_Option(email, pwd)
ok, r = api.connect()
if not ok:
    sys.exit(1)

api.change_balance("PRACTICE")
time.sleep(2)

if mode == "open":
    # Hardcoded assets — skip get_all_open_time (crashes on GH Actions)
    assets = [
        "EURUSD-OTC","GBPUSD-OTC","USDCHF-OTC","USDJPY-OTC","AUDUSD-OTC",
        "USDCAD-OTC","NZDUSD-OTC","EURGBP-OTC","EURJPY-OTC","GBPJPY-OTC",
        "EURCHF-OTC","AUDJPY-OTC","CADJPY-OTC","CHFJPY-OTC","NZDJPY-OTC",
        "XAUUSD-OTC","GER30-OTC","UK100-OTC","NOKJPY-OTC","ETHUSD-OTC",
        "XRPUSD-OTC","SOLUSD-OTC","BTCUSD-OTC-op","EURAUD-OTC","EURCAD-OTC",
        "EURNZD-OTC","GBPAUD-OTC","GBPCAD-OTC","GBPNZD-OTC","AUDCHF-OTC",
        "AUDCAD-OTC","AUDNZD-OTC","NZDCHF-OTC","NZDCAD-OTC"
    ]
    paying = {}
    for asset in assets:
        try:
            p = api.get_digital_payout(asset)
            if p and p >= 85:
                paying[asset] = p
        except:
            pass
    print(json.dumps(paying))

elif mode == "candles":
    asset = sys.argv[2]
    period = int(sys.argv[3])
    count = int(sys.argv[4])
    c = api.get_candles(asset, period, count, time.time())
    if c:
        print(json.dumps([[x.get("close",0), x.get("max",0), x.get("min",0), x.get("open",0)] for x in c]))
