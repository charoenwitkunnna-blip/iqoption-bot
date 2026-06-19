#!/bin/bash
# Run all experiment strategies in parallel
cd /root/iqoption-bot
source venv/bin/activate

EXPERIMENTS_DIR=/root/iqoption-bot/experiments
DURATION=30

echo "Starting all experiments for ${DURATION} minutes each..."
echo ""

# Strategy name -> module path mapping
declare -A STRATS
STRATS[ml]="ml_strategy.strategy"
STRATS[market-structure]="market_structure.strategy"
STRATS[ensemble]="ensemble.strategy"
STRATS[v2]="v2.strategy"
STRATS[mean-reversion]="mean_reversion.strategy"

for name in ml market-structure ensemble v2 mean-reversion; do
    modpath="${STRATS[$name]}"
    echo "[$(date +%H:%M:%S)] Launching ${name} (${modpath})..."
    
    python3 -c "
import sys, os, importlib
sys.path.insert(0, '${EXPERIMENTS_DIR}')
os.chdir('${EXPERIMENTS_DIR}')
from experiment_runner import run_experiment, get_logger
mod = importlib.import_module('${modpath}')
log = get_logger('${name}')
run_experiment('${name}', mod, ${DURATION}, log)
" > ${EXPERIMENTS_DIR}/${name}_run.log 2>&1 &
    
    echo "  PID: $!"
    sleep 2
done

echo ""
echo "All 5 strategies launched. Each runs ${DURATION} min."
echo "Watch: tail -f ${EXPERIMENTS_DIR}/{ml,market-structure,ensemble,v2,mean-reversion}_results.log"
