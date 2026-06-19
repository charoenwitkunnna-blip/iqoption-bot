#!/bin/bash
# Watchdog loop - runs stable_cycle.py every cycle_time seconds forever
set +m  # Disable job control monitors

CYCLE_TIME=45
STRAT_NAME="replica_exact"  # Change to "v2" for V2 strategy
BASE_DIR="/root/iqoption-bot/experiments"
LOG_FILE="${BASE_DIR}/results/${STRAT_NAME}_stable.log"

cd "$BASE_DIR"
source ../venv/bin/activate

echo "=== WATCHDOG STARTED $(date) ===" >> "$LOG_FILE"

while true; do
    timeout 80 python3 -u stable_cycle.py
    EC=$?
    if [ $EC -ne 0 ]; then
        echo "$(date '+%H:%M:%S') WATCHDOG: cycle failed (exit=$EC), waiting..." >> "$LOG_FILE"
    fi
    sleep $CYCLE_TIME
done
