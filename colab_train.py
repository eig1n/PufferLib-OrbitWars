#!/usr/bin/env python3
"""
Orbit Wars — Colab Training Verification Runner

Usage (from local machine):
    colab exec -f colab_train.py
"""

import subprocess
import os
import sys
import time

print("=" * 60)
print("ORBIT WARS — COLAB TRAINING VERIFICATION")
print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
print("=" * 60)

# Navigate to pufferlib directory
if not os.path.exists("pufferlib"):
    print("Error: 'pufferlib' directory not found! Run colab_setup.py first.")
    sys.exit(1)

os.chdir("pufferlib")

# Run PufferLib Training
print("\n>>> Starting PufferLib training loop for 10 seconds... <<<")
sys.stdout.flush()

# Open the log file for writing (in the parent directory)
log_file = open("../colab_train_run.log", "w")

process = subprocess.Popen(
    [sys.executable, "-m", "pufferlib.pufferl", "train", "orbit_wars", "--slowly"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1
)

# Monitor the training process for 10 seconds
start_time = time.time()
success = True

# Make stdout non-blocking to read dynamically without hanging
os.set_blocking(process.stdout.fileno(), False)

while time.time() - start_time < 10.0:
    ret = process.poll()
    if ret is not None:
        print(f"\n❌ Training process terminated early with exit code {ret}!")
        success = False
        break

    try:
        data = process.stdout.read()
        if data:
            sys.stdout.write(data)
            sys.stdout.flush()
            log_file.write(data)
            log_file.flush()
    except IOError:
        pass
    time.sleep(0.1)

# If still running, terminate it successfully (this is a pass)
if process.poll() is None:
    print("\nTraining ran successfully for 10 seconds. Terminating process...")
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()

# Read remaining data
try:
    os.set_blocking(process.stdout.fileno(), True)
    data = process.stdout.read()
    if data:
        sys.stdout.write(data)
        sys.stdout.flush()
        log_file.write(data)
        log_file.flush()
except Exception:
    pass

log_file.close()

print("\n" + "=" * 60)
print("TRAINING VERIFICATION SUMMARY")
print("=" * 60)
print(f"  Training Status:   {'✅ PASSED' if success else '❌ FAILED'}")
print("=" * 60)

sys.exit(0 if success else 1)
