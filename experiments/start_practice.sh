#!/bin/bash
cd /root/iqoption-bot/experiments
source ../venv/bin/activate

while true; do
    echo "$(date -u '+%H:%M:%S') Starting bot for 10 min..."
    timeout 600 python3 -u rho_practice.py
    echo "$(date -u '+%H:%M:%S') Bot stopped. Waiting 5 min..."
    sleep 300
done
