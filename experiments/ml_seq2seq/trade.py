#!/usr/bin/env python3
"""
ML SEQ2SEQ LIVE TRADER — predicts next 20 candles + direction confidence.
Uses trained LSTM model with direction head. Trades on PRACTICE.

Strategy:
  1. Pull 50 5-sec candles for each paying asset
  2. Run through model → get predicted 20 candles + direction probability
  3. If direction confidence is high and trend is clear → trade 1-min digital

Usage: source ../../venv/bin/activate && python3 trade.py
"""
import sys, os, time, json
import numpy as np
import torch
import torch.nn as nn

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "models")
RESULTS_DIR = os.path.join(BASE_DIR, "results")
LOG_FILE = os.path.join(RESULTS_DIR, "seq2seq_trader.log")
TRADES_FILE = os.path.join(RESULTS_DIR, "seq2seq_trades.json")

sys.path.insert(0, os.path.join(BASE_DIR, '..'))
from config_practice import IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD
from iqoptionapi.stable_api import IQ_Option

os.makedirs(RESULTS_DIR, exist_ok=True)

AMOUNT = 5      # PRACTICE amount
MIN_DIR_CONFIDENCE = 0.60   # Minimum direction probability to trade

# ============================================================
# MODEL DEFINITION (same as train.py)
# ============================================================
class Seq2SeqLSTM(nn.Module):
    def __init__(self, input_size=4, hidden_size=128, num_layers=2, output_steps=20):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.output_steps = output_steps
        self.encoder = nn.LSTM(input_size, hidden_size, num_layers,
                                batch_first=True, dropout=0.2 if num_layers > 1 else 0)
        self.decoder = nn.LSTM(input_size, hidden_size, num_layers,
                                batch_first=True, dropout=0.2 if num_layers > 1 else 0)
        self.candle_out = nn.Linear(hidden_size, input_size)
        self.dir_head = nn.Sequential(
            nn.Linear(hidden_size, 32),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(32, 1),
        )

    def forward(self, x):
        _, (hidden, cell) = self.encoder(x)
        decoder_input = x[:, -1:, :]
        outputs = []
        for t in range(self.output_steps):
            out, (hidden, cell) = self.decoder(decoder_input, (hidden, cell))
            pred = self.candle_out(out)
            outputs.append(pred)
            decoder_input = pred

        candle_preds = torch.cat(outputs, dim=1)
        dir_logit = self.dir_head(hidden[-1])
        dir_prob = torch.sigmoid(dir_logit)
        return candle_preds, dir_prob


# ============================================================
# LOAD MODEL
# ============================================================
model_path = os.path.join(MODEL_DIR, "best_model.pth")
if not os.path.exists(model_path):
    model_path = os.path.join(MODEL_DIR, "final_model.pth")
if not os.path.exists(model_path):
    print(f"ERROR: No model found in {MODEL_DIR}/")
    print("Run train.py first!")
    sys.exit(1)

checkpoint = torch.load(model_path, map_location='cpu')
model = Seq2SeqLSTM()
model.load_state_dict(checkpoint['model_state_dict'])
model.eval()
print(f"Model loaded from {model_path}")
print(f"  (best val loss: {checkpoint.get('val_loss', '?'):.5f})")


def log(msg):
    with open(LOG_FILE, "a") as fh:
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        fh.write(f"{ts} {msg}\n")
    print(msg)


def predict(model, candles_50):
    """
    Given 50 candles, predict next 20 candles + direction.

    Returns:
      pred_candles_denorm: (20, 4) array in original price scale
      dir_prob: float, probability of UP (0-1)
      trend_pct: float, % change in predicted close over 20 candles
      consistency: float, fraction of steps moving in trend direction
    """
    opens = np.array([c['open'] for c in candles_50[-50:]], dtype=np.float32)
    highs = np.array([c['high'] for c in candles_50[-50:]], dtype=np.float32)
    lows = np.array([c['low'] for c in candles_50[-50:]], dtype=np.float32)
    closes = np.array([c['close'] for c in candles_50[-50:]], dtype=np.float32)

    inp_raw = np.column_stack([opens, highs, lows, closes])
    norm = closes[-1]

    if norm <= 0:
        return None, 0, 0, 0

    inp_n = inp_raw / norm
    inp_t = torch.tensor(inp_n).unsqueeze(0).float()

    with torch.no_grad():
        c_pred, d_prob = model(inp_t)
        c_pred = c_pred.squeeze(0).numpy()   # (20, 4)
        d_prob = d_prob.item()                # float

    pred_denorm = c_pred * norm

    # Trend metrics
    close_start = pred_denorm[0, 3]
    close_end = pred_denorm[-1, 3]
    trend_pct = (close_end - close_start) / max(close_start, 0.001) * 100

    # Consistency: fraction of candle-to-candle steps in the dominant direction
    diffs = np.diff(pred_denorm[:, 3])
    cons_up = np.sum(diffs > 0) / len(diffs)
    cons_down = np.sum(diffs < 0) / len(diffs)
    consistency = max(cons_up, cons_down)

    return pred_denorm, d_prob, trend_pct, consistency


# ============================================================
# TRADING LOOP
# ============================================================
log("=== SEQ2SEQ TRADER STARTING ===")

trades = json.load(open(TRADES_FILE)) if os.path.exists(TRADES_FILE) else []

api = IQ_Option(IQ_OPTION_EMAIL, IQ_OPTION_PASSWORD)
api.connect()
api.change_balance("PRACTICE")
time.sleep(2)
balance = api.get_balance()
log(f"Balance: {balance:.2f} PRACTICE")

# Scan assets
all_a = api.get_all_open_time()
pairs = {x: v for x, v in all_a['turbo'].items() if v['open']}
paying = {}
for a in list(pairs.keys())[:60]:
    try:
        p = api.get_digital_payout(a)
        if p and p >= 80:
            paying[a] = p
    except:
        pass

top_assets = sorted(paying, key=paying.get, reverse=True)
log(f"Assets: {len(top_assets)} with payout >= 80%")

trades_done = 0

for asset in top_assets:
    if trades_done >= 1:
        break  # One trade per run

    try:
        candles = api.get_candles(asset, 5, 55, time.time())
        if not candles or len(candles) < 55:
            continue
    except Exception as e:
        continue

    result = predict(model, candles)
    if result[0] is None:
        continue

    pred_c, dir_prob, trend_pct, consistency = result

    # Decision
    if dir_prob >= MIN_DIR_CONFIDENCE:
        direction = "call"
        dir_str = "CALL"
    elif dir_prob <= 1.0 - MIN_DIR_CONFIDENCE:
        direction = "put"
        dir_str = "PUT"
    else:
        log(f"  {asset}: dir_conf={dir_prob:.3f} (needs >={MIN_DIR_CONFIDENCE} or <={1-MIN_DIR_CONFIDENCE}) — SKIP")
        continue

    # Also check the predicted candles are consistent with direction
    predicted_up = trend_pct > 0
    trade_up = (direction == "call")
    if predicted_up != trade_up:
        log(f"  {asset}: dir_conf={dir_prob:.3f} says {dir_str} but trend={trend_pct:+.3f}% conflicting — SKIP")
        continue

    if consistency < 0.55:
        log(f"  {asset}: consistency={consistency:.2f} too low — SKIP")
        continue

    if abs(trend_pct) < 0.03:
        log(f"  {asset}: trend={trend_pct:+.3f}% too weak — SKIP")
        continue

    log(f"  {asset}: {dir_str} dir_conf={dir_prob:.3f} trend={trend_pct:+.3f}% consist={consistency:.2f}")
    log(f"    → TRADING {AMOUNT} THB")

    try:
        ok, tid = api.buy(AMOUNT, asset, direction, 1)  # 1-min expiry
        if not ok:
            log(f"    └─ FAIL: {tid}")
            continue
    except Exception as e:
        log(f"    └─ ERROR: {e}")
        continue

    log(f"    └─ Order #{tid} placed")

    time.sleep(75)  # Wait 1-min expiry + buffer

    try:
                result = api.check_win_digital_v2(tid)
        if isinstance(result, (list, tuple)):
            win = bool(result[0])
        else:
            win = bool(result)
    except:
        win = False

    payout_pct = paying.get(asset, 87)
    profit = AMOUNT * (payout_pct / 100) if win else -AMOUNT
    balance += profit

    trade = {
        "time": time.strftime('%Y-%m-%d %H:%M:%S'),
        "asset": asset,
        "direction": direction,
        "amount": AMOUNT,
        "dir_prob": round(dir_prob, 3),
        "trend_pct": round(trend_pct, 4),
        "consistency": round(consistency, 3),
        "profit": profit,
        "win": win,
        "payout": payout_pct,
        "balance": round(balance, 2),
    }
    trades.append(trade)
    json.dump(trades, open(TRADES_FILE, "w"), indent=2)

    w = sum(1 for t in trades if t['win'])
    pnl = sum(t['profit'] for t in trades)
    wr = f"{w}/{len(trades)} ({w/len(trades)*100:.0f}%)"
    log(f"    └─ {'WIN' if win else 'LOSS'} | WR: {wr} | PnL: {pnl:+.1f} | Bal: {balance:.2f}")
    trades_done += 1

w = sum(1 for t in trades if t['win']) if trades else 0
pnl = sum(t['profit'] for t in trades) if trades else 0
t = len(trades)
log(f"=== DONE: {t} trades | {w}W/{t-w}L | PnL: {pnl:+.1f} | Bal: {balance:.2f} ===")

api.close_connect()
