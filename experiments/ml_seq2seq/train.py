#!/usr/bin/env python3
"""
ML SEQ2SEQ TRAINER — LSTM encoder-decoder with direction head.
Predicts next 20 candles from 50 input candles (5-sec each).

Two outputs:
  - candle_preds: (batch, 20, 4) — OHLC for each of the next 20 candles
  - direction: (batch, 1) — binary UP(1)/DOWN(0) probability at period end

Combined loss: MSE(OHLC) + BCE(direction)

Usage: source ../../venv/bin/activate && python3 train.py
"""
import os, json, sys, glob
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
MODEL_DIR = os.path.join(BASE_DIR, "models")
os.makedirs(MODEL_DIR, exist_ok=True)

# Config
SEQ_IN = 50
SEQ_OUT = 20
FEATURES = 4       # open, high, low, close
BATCH_SIZE = 128
EPOCHS = 100
HIDDEN_SIZE = 128
NUM_LAYERS = 2
LR = 0.001
DEVICE = torch.device("cpu")

print(f"Using device: {DEVICE}")

# ============================================================
# DATASET
# ============================================================
class CandleSequenceDataset(Dataset):
    """Sliding window: 50 candles in → 20 candles out + direction label."""

    def __init__(self, data_dir, seq_in=SEQ_IN, seq_out=SEQ_OUT):
        self.samples = []
        files = sorted(glob.glob(os.path.join(data_dir, "*.json")))
        files = [f for f in files if not f.endswith('_meta.json')]

        print(f"Loading {len(files)} asset files...")
        for fpath in files:
            with open(fpath) as f:
                candles = json.load(f)

            if len(candles) < seq_in + seq_out + 5:
                continue

            opens = np.array([c['open'] for c in candles], dtype=np.float64)
            highs = np.array([c['high'] for c in candles], dtype=np.float64)
            lows = np.array([c['low'] for c in candles], dtype=np.float64)
            closes = np.array([c['close'] for c in candles], dtype=np.float64)

            asset_windows = 0
            for i in range(0, len(candles) - seq_in - seq_out + 1, 2):
                inp_s = slice(i, i + seq_in)
                tgt_s = slice(i + seq_in, i + seq_in + seq_out)

                inp_raw = np.column_stack([opens[inp_s], highs[inp_s],
                                            lows[inp_s], closes[inp_s]])
                tgt_raw = np.column_stack([opens[tgt_s], highs[tgt_s],
                                            lows[tgt_s], closes[tgt_s]])

                norm = closes[i + seq_in - 1]
                if norm <= 0:
                    continue

                inp_n = inp_raw / norm
                tgt_n = tgt_raw / norm

                # Direction: UP(1) if close[-1] > close[0] else DOWN(0)
                direction = 1.0 if tgt_raw[-1, 3] > tgt_raw[0, 3] else 0.0

                self.samples.append({
                    'input': inp_n.astype(np.float32),
                    'target': tgt_n.astype(np.float32),
                    'direction': direction,
                })
                asset_windows += 1

            print(f"  {os.path.basename(fpath)}: {asset_windows} windows")

        print(f"\nTotal samples: {len(self.samples)}")

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        s = self.samples[idx]
        return {
            'input': torch.tensor(s['input']),           # (50, 4)
            'target': torch.tensor(s['target']),          # (20, 4)
            'direction': torch.tensor([s['direction']]),  # (1,)
        }


# ============================================================
# MODEL — Seq2Seq LSTM with direction head
# ============================================================
class Seq2SeqLSTM(nn.Module):
    """
    LSTM encoder-decoder that predicts:
      - Next 20 OHLC candles (autoregressive)
      - Binary direction at period end (classification head)
    """
    def __init__(self, input_size=FEATURES, hidden_size=HIDDEN_SIZE,
                 num_layers=NUM_LAYERS, output_steps=SEQ_OUT):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.output_steps = output_steps

        self.encoder = nn.LSTM(input_size, hidden_size, num_layers,
                                batch_first=True, dropout=0.2 if num_layers > 1 else 0)
        self.decoder = nn.LSTM(input_size, hidden_size, num_layers,
                                batch_first=True, dropout=0.2 if num_layers > 1 else 0)
        self.candle_out = nn.Linear(hidden_size, input_size)

        # Direction head: takes final decoder hidden state → binary
        self.dir_head = nn.Sequential(
            nn.Linear(hidden_size, 32),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(32, 1),
        )

    def forward(self, x):
        # x: (batch, 50, 4)
        _, (hidden, cell) = self.encoder(x)

        decoder_input = x[:, -1:, :]  # (batch, 1, 4) — start token
        outputs = []
        for t in range(self.output_steps):
            out, (hidden, cell) = self.decoder(decoder_input, (hidden, cell))
            pred = self.candle_out(out)  # (batch, 1, 4)
            outputs.append(pred)
            decoder_input = pred

        candle_preds = torch.cat(outputs, dim=1)  # (batch, 20, 4)

        # Direction: use last decoder hidden state (top layer)
        dir_logit = self.dir_head(hidden[-1])  # (batch, 1)
        dir_prob = torch.sigmoid(dir_logit)

        return candle_preds, dir_prob


# ============================================================
# LOSS
# ============================================================
class CombinedLoss(nn.Module):
    def __init__(self, alpha=0.7):
        """alpha: weight for candle MSE, (1-alpha) for direction BCE."""
        super().__init__()
        self.alpha = alpha
        self.mse = nn.MSELoss()
        self.bce = nn.BCELoss()

    def forward(self, candle_pred, candle_tgt, dir_pred, dir_tgt):
        loss_candle = self.mse(candle_pred, candle_tgt)
        loss_dir = self.bce(dir_pred, dir_tgt)
        return self.alpha * loss_candle + (1 - self.alpha) * loss_dir, loss_candle.item(), loss_dir.item()


# ============================================================
# METRICS
# ============================================================
def trend_accuracy(candle_pred, candle_tgt):
    """Fraction where predicted trend direction matches actual."""
    p = (candle_pred[:, -1, 3] - candle_pred[:, 0, 3])
    t = (candle_tgt[:, -1, 3] - candle_tgt[:, 0, 3])
    return (p * t > 0).float().mean().item()

def mape_score(candle_pred, candle_tgt, eps=1e-8):
    """MAPE on close prices."""
    ae = torch.abs((candle_pred[:, :, 3] - candle_tgt[:, :, 3]) / (candle_tgt[:, :, 3] + eps))
    return ae.mean().item()


# ============================================================
# TRAINING
# ============================================================
print("Loading dataset...")
dataset = CandleSequenceDataset(DATA_DIR)
if len(dataset) == 0:
    print("ERROR: No data! Run collect.py first.")
    sys.exit(1)

split = int(0.8 * len(dataset))
train_ds, val_ds = torch.utils.data.random_split(
    dataset, [split, len(dataset) - split],
    generator=torch.Generator().manual_seed(42)
)

train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True, num_workers=0)
val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=0)

print(f"Train: {len(train_ds)} | Val: {len(val_ds)}")

model = Seq2SeqLSTM().to(DEVICE)
n_params = sum(p.numel() for p in model.parameters())
print(f"Model params: {n_params:,} ({n_params/1000:.0f}K)")

criterion = CombinedLoss(alpha=0.7)
optimizer = optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-5)
scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=5, factor=0.5)

best_val_loss = float('inf')
no_improve = 0

# Count direction balance
n_up = sum(1 for b in val_ds if b['direction'].item() == 1)
n_down = len(val_ds) - n_up
print(f"Val direction balance: UP={n_up} DOWN={n_down} ({n_up/len(val_ds)*100:.0f}%/{n_down/len(val_ds)*100:.0f}%)")

print(f"\n{'Epoch':>5} | {'Train':>9} | {'Val':>9} | {'DirAcc':>7} | {'TrAcc':>6} | {'MAPE':>6} | {'CndL':>6} | {'DirL':>6} | {'LR':>8}")
print("-" * 75)

for epoch in range(1, EPOCHS + 1):
    # --- TRAIN ---
    model.train()
    train_loss = 0
    for batch in train_loader:
        x = batch['input'].to(DEVICE)
        y = batch['target'].to(DEVICE)
        d = batch['direction'].to(DEVICE)

        optimizer.zero_grad()
        c_pred, d_pred = model(x)
        loss, lc, ld = criterion(c_pred, y, d_pred, d)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        train_loss += loss.item() * x.size(0)
    train_loss /= len(train_ds)

    # --- VAL ---
    model.eval()
    val_loss = 0
    dir_correct = 0
    tr_acc = 0
    ma = 0
    n = 0
    with torch.no_grad():
        for batch in val_loader:
            x = batch['input'].to(DEVICE)
            y = batch['target'].to(DEVICE)
            d = batch['direction'].to(DEVICE)

            c_pred, d_pred = model(x)
            loss, lc, ld = criterion(c_pred, y, d_pred, d)
            val_loss += loss.item() * x.size(0)

            # Direction accuracy
            pred_label = (d_pred > 0.5).float()
            dir_correct += (pred_label == d).float().sum().item()

            tr_acc += trend_accuracy(c_pred, y) * x.size(0)
            ma += mape_score(c_pred, y) * x.size(0)
            n += x.size(0)

    val_loss /= n
    dir_acc = dir_correct / n
    tr_acc /= n
    ma /= n

    scheduler.step(val_loss)
    lr_val = optimizer.param_groups[0]['lr']

    print(f"{epoch:>5} | {train_loss:.5f} | {val_loss:.5f} | {dir_acc:.4f} | {tr_acc:.4f} | {ma:.4f} | {lc:.4f} | {ld:.4f} | {lr_val:.1e}")

    # Save best
    if val_loss < best_val_loss:
        best_val_loss = val_loss
        no_improve = 0
        torch.save({
            'epoch': epoch,
            'model_state_dict': model.state_dict(),
            'optimizer_state_dict': optimizer.state_dict(),
            'val_loss': val_loss,
            'dir_acc': dir_acc,
            'trend_acc': tr_acc,
        }, os.path.join(MODEL_DIR, "best_model.pth"))
    else:
        no_improve += 1
        if no_improve >= 20:
            print(f"Early stopping at epoch {epoch}")
            break

# Save final
torch.save({
    'model_state_dict': model.state_dict(),
    'hidden_size': HIDDEN_SIZE,
    'num_layers': NUM_LAYERS,
    'seq_in': SEQ_IN,
    'seq_out': SEQ_OUT,
}, os.path.join(MODEL_DIR, "final_model.pth"))

print(f"\nDone! Best val loss: {best_val_loss:.5f}")
print(f"Models saved to {MODEL_DIR}/")
