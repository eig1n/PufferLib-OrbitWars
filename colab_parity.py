#!/usr/bin/env python3
"""
Orbit Wars — Colab Parity Test Runner

Usage (from local machine):
    colab exec -f colab_parity.py
"""

import subprocess
import os
import sys
import time

def run_stream(args):
    """Run a subprocess and stream stdout/stderr in real-time."""
    print(f"\n$ {' '.join(args)}")
    sys.stdout.flush()
    process = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    for line in process.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
    process.wait()
    return process.returncode


print("=" * 60)
print("ORBIT WARS — COLAB PARITY TEST RUNNER")
print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
print("=" * 60)

# Navigate to pufferlib directory
if not os.path.exists("pufferlib"):
    print("Error: 'pufferlib' directory not found! Run colab_setup.py first.")
    sys.exit(1)

os.chdir("pufferlib")

# Run Parity Test Suite
print("\n>>> Running Parity Test Suite (test_orbit_wars_parity.py) <<<")
code_parity = run_stream([sys.executable, "tests/test_orbit_wars_parity.py"])

print("\n" + "=" * 60)
print("PARITY TEST SUMMARY")
print("=" * 60)
print(f"  Parity Test Status: {'✅ PASSED' if code_parity == 0 else '❌ FAILED'}")
print("=" * 60)

sys.exit(code_parity)
