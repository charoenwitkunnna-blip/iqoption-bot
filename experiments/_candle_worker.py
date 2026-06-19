#!/usr/bin/env python3
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
asset = sys.argv[1]
period = int(sys.argv[2])
count = int(sys.argv[3])
from iqoptionapi.stable_api import IQ_Option
email = os.environ.get("IQ_EMAIL", "")
pwd = os.environ.get("IQ_PASSWORD", "")
api = IQ_Option(email, pwd)
ok, r = api.connect()
if ok:
    api.change_balance("PRACTICE")
    time.sleep(2)
    c = api.get_candles(asset, period, count, time.time())
    if c:
        print(json.dumps([[x.get("close",0), x.get("max",0), x.get("min",0), x.get("open",0)] for x in c]))
