#!/usr/bin/env python3
"""Standalone ML strategy runner"""
import sys, os, importlib, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from experiment_runner import run_experiment, get_logger
mod = importlib.import_module('ml_strategy.strategy')
log = get_logger('ml')
run_experiment('ml', mod, 30, log)
time.sleep(5)  # keep alive briefly
