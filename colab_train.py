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

# Load WANDB_API_KEY from .env or env_file if present
wandb_key = None
for path in [".env", "../.env", "../../.env", "env_file", "../env_file", "../../env_file"]:
    if os.path.exists(path):
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() == "WANDB_API_KEY":
                        wandb_key = v.strip().strip('"').strip("'")
                        break
        if wandb_key:
            break

cmd = [sys.executable, "-m", "pufferlib.pufferl", "train", "orbit_wars", "--slowly", "--vec.total-agents", "64", "--selfplay.enabled", "0"]
if wandb_key:
    os.environ["WANDB_API_KEY"] = wandb_key
    try:
        import wandb
        print("Logging in to Weights & Biases...")
        wandb.login(key=wandb_key)
    except Exception as e:
        print(f"Warning: Failed to login to wandb via client: {e}")
    cmd.append("--wandb")
    print("Enabled Weights & Biases logging (--wandb) using key from .env")

# Run PufferLib Training
print("\n>>> Starting PufferLib training loop for up to 60 seconds... <<<")
sys.stdout.flush()

# Open the log file for writing (in the parent directory)
log_file = open("../colab_train_run.log", "w")

process = subprocess.Popen(
    cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    bufsize=1
)

# Monitor the training process for up to 60 seconds
start_time = time.time()
success = True

# Make stdout non-blocking to read dynamically without hanging
os.set_blocking(process.stdout.fileno(), False)

while time.time() - start_time < 60.0:
    ret = process.poll()
    if ret is not None:
        if ret == 0:
            print(f"\n✅ Training process completed naturally with exit code 0.")
            success = True
        else:
            print(f"\n❌ Training process terminated early with exit code {ret}!")
            success = False
        break

    try:
        data = process.stdout.read()
        if data:
            text = data.decode('utf-8', errors='ignore')
            sys.stdout.write(text)
            sys.stdout.flush()
            log_file.write(text)
            log_file.flush()
    except IOError:
        pass
    time.sleep(0.1)

# If still running, terminate it successfully (this is a pass)
if process.poll() is None:
    print("\nTraining process is still running after 60 seconds. Terminating process...")
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()

# Read remaining data
try:
    os.set_blocking(process.stdout.fileno(), True)
    data = process.stdout.read()
    if data:
        text = data.decode('utf-8', errors='ignore')
        sys.stdout.write(text)
        sys.stdout.flush()
        log_file.write(text)
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
