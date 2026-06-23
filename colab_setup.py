#!/usr/bin/env python3
"""
Orbit Wars — Colab VM Setup Script

Usage (from local machine):
    colab new
    colab exec -f colab_setup.py
"""

import subprocess
import os
import sys
import time

def run(cmd, **kw):
    """Run a command, print it, and check for errors."""
    print(f"\n$ {cmd if isinstance(cmd, str) else ' '.join(cmd)}")
    if "shell" not in kw:
        kw["shell"] = isinstance(cmd, str)
    return subprocess.run(cmd, check=True, **kw)

print("=" * 60)
print("ORBIT WARS — PUFFERLIB COLAB SETUP")
print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
print("=" * 60)

# ------------------------------------------------------------------
# 1. Clone repository
# ------------------------------------------------------------------
print("\n--- [1/3] Cloning repository ---")
if os.path.exists("pufferlib"):
    run("rm -rf pufferlib")
run("git clone https://github.com/eig1n/PufferLib-OrbitWars.git pufferlib")

# ------------------------------------------------------------------
# 2. Install system dependencies
# ------------------------------------------------------------------
print("\n--- [2/3] Installing system dependencies (clang, openmp) ---")
run("apt-get update -qq && apt-get install -y -qq clang libomp-dev > /dev/null 2>&1", shell=True)

# ------------------------------------------------------------------
# 3. Install Python dependencies
# ------------------------------------------------------------------
print("\n--- [3/3] Installing Python dependencies ---")
try:
    run("curl -LsSf https://astral.sh/uv/install.sh | sh", shell=True)
    os.environ["PATH"] += os.pathsep + os.path.expanduser("~/.local/bin")
    run("uv pip install --system pybind11 numpy rich kaggle-environments wandb -e pufferlib 2>/dev/null || pip install pybind11 numpy rich kaggle-environments wandb -e pufferlib", shell=True)
except Exception:
    run("pip install pybind11 numpy rich kaggle-environments wandb -e pufferlib", shell=True)

print("\n" + "=" * 60)
print("SETUP COMPLETED SUCCESSFULLY")
print("=" * 60)
