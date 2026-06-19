#!/usr/bin/env python3
"""
Launch all 4 strategies as background daemon processes
Each runs for 30 min and logs to experiments/{name}_results.log
"""
import subprocess, sys, time, os

experiments_dir = '/root/iqoption-bot/experiments'
activate = 'source /root/iqoption-bot/venv/bin/activate'

strategies = [
    ('ml', 'ml_strategy.strategy'),
    ('market-structure', 'market_structure.strategy'),
    ('ensemble', 'ensemble.strategy'),
    ('v2', 'v2.strategy'),
]

pids = []
for name, modpath in strategies:
    script = f"""
import sys, os, importlib
sys.path.insert(0, '{experiments_dir}')
os.chdir('{experiments_dir}')
from experiment_runner import run_experiment, get_logger
mod = importlib.import_module('{modpath}')
log = get_logger('{name}')
run_experiment('{name}', mod, 30, log)
"""
    cmd = [
        'bash', '-c',
        f'cd /root/iqoption-bot && source venv/bin/activate && python3 -c "{script}" > {experiments_dir}/{name}_run.log 2>&1'
    ]
    proc = subprocess.Popen(
        ['bash', '-c', f'cd /root/iqoption-bot && source venv/bin/activate && exec python3 -c \'{script}\' > {experiments_dir}/{name}_run.log 2>&1'],
        start_new_session=True
    )
    pids.append((name, proc.pid))
    print(f"Launched {name} (PID {proc.pid})")
    time.sleep(2)

print(f"\nAll {len(pids)} strategies launched. Running for 30 min.")
print("Check: tail -f experiments/{strategy}_results.log")
sys.stdout.flush()
