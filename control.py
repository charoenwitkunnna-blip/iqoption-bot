#!/usr/bin/env python3
"""Control script for the IQ Option bot - manages start/stop via PID file"""
import os
import sys
import signal
import subprocess
import time

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
PID_FILE = os.path.join(BOT_DIR, "bot.pid")
VENV_PYTHON = os.path.join(BOT_DIR, "venv", "bin", "python3")
BOT_SCRIPT = os.path.join(BOT_DIR, "bot.py")
LOG_FILE = os.path.join(BOT_DIR, "bot.log")

def get_pid():
    """Read the PID file"""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                return int(f.read().strip())
        except:
            return None
    return None

def is_running():
    """Check if the bot is running"""
    pid = get_pid()
    if pid:
        try:
            os.kill(pid, 0)  # Signal 0 just checks existence
            return True
        except OSError:
            # PID exists but process doesn't
            try:
                os.remove(PID_FILE)
            except:
                pass
    return False

def start():
    """Start the bot in the background"""
    if is_running():
        print("Bot is already running (PID: {})".format(get_pid()))
        return True
    
    with open(LOG_FILE, "a") as log:
        log.write("\n--- Bot started by control script ---\n")
    
    # Use nohup to keep running after parent exits
    cmd = "cd {} && {} {} >> {} 2>&1 & echo $! > {}".format(
        BOT_DIR, VENV_PYTHON, BOT_SCRIPT, LOG_FILE, PID_FILE
    )
    subprocess.run(cmd, shell=True, executable="/bin/bash")
    
    time.sleep(3)
    if is_running():
        print("Bot started successfully (PID: {})".format(get_pid()))
        return True
    else:
        print("Bot failed to start")
        return False

def stop():
    """Stop the bot gracefully"""
    pid = get_pid()
    if not pid:
        print("Bot is not running")
        return True
    
    # Try graceful shutdown first
    try:
        os.kill(pid, signal.SIGINT)  # Simulates Ctrl+C
        for _ in range(30):  # Wait up to 30 seconds
            time.sleep(1)
            if not is_running():
                break
        else:
            # Force kill
            os.kill(pid, signal.SIGTERM)
            time.sleep(2)
            if is_running():
                os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    
    # Clean up PID file
    try:
        os.remove(PID_FILE)
    except:
        pass
    
    with open(LOG_FILE, "a") as log:
        log.write("--- Bot stopped by control script ---\n")
    
    print("Bot stopped")
    return True

def restart():
    """Restart the bot"""
    stop()
    time.sleep(2)
    return start()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: {} <start|stop|restart|status>".format(sys.argv[0]))
        sys.exit(1)
    
    action = sys.argv[1]
    
    if action == "start":
        success = start()
        sys.exit(0 if success else 1)
    elif action == "stop":
        stop()
        sys.exit(0)
    elif action == "restart":
        success = restart()
        sys.exit(0 if success else 1)
    elif action == "status":
        running = is_running()
        pid = get_pid()
        print("Bot {} running{}".format(
            "is" if running else "is NOT",
            " (PID: {})".format(pid) if pid else ""
        ))
        sys.exit(0 if running else 1)
    else:
        print("Unknown action: {}".format(action))
        sys.exit(1)
