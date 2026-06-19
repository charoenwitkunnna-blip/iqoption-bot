# IQ Option Bot — Strategy Experiments

Experiments to improve the trading bot, tested on PRACTICE account.

## Strategies

| Folder | Strategy | Approach |
|--------|----------|---------|
| `ml_strategy/` | **ML** | Random Forest classifier using 20+ features (RSI, ADX, MACD, BB, volume, volatility). Trains on historical data, predicts direction with confidence threshold. |
| `market_structure/` | **ICT/SMC** | Market structure analysis: swing points, order blocks, fair value gaps, break of structure, liquidity sweeps. Trades based on structural confluences. |
| `ensemble/` | **Ensemble** | 4 sub-strategies vote: RSI/ADX, Bollinger squeeze, volume momentum, ICT patterns. Only trades when 2+ agree with strong majority. |
| `v2/` | **V2 Adaptive** | Clean rewrite with adaptive position sizing (confidence-based), martingale-light recovery (1.5x after loss, reset on win), consecutive loss protection (stop after 3). |

## Config

All experiments use `config_practice.py`:
- **Balance type:** PRACTICE
- **Trade amount:** 5 (small)
- **Stop loss:** 50
- **Min payout:** 75%

## Running

```bash
# Run one strategy for N minutes
source venv/bin/activate
python3 run_experiment.py ml --duration 60        # ML for 60 min
python3 run_experiment.py v2 --duration 120       # V2 for 2 hours
python3 run_experiment.py ensemble --duration 30  # Ensemble for 30 min

# Compare all strategies back-to-back
python3 run_experiment.py compare --duration 30   # Each runs for 30 min
```

Results are logged to `{strategy}_results.log` in the experiments folder.

## Notes
- Each experiment uses its own IQ Option connection
- Active trades are tracked per-strategy (no overlap)
- HTF (15min) EMA50 used as trend filter across all strategies
