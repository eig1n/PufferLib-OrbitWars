#!/usr/bin/env python3
"""
Orbit Wars — Colab Environment Setup Script
Run this once per Colab session.
"""

import os
import subprocess
import sys
import time

REPO_URL = "https://github.com/eig1n/PufferLib-OrbitWars.git"
REPO_DIR = "pufferlib"


def run(cmd, check=True):
    """Run a command, print it, and check for errors."""
    print(f"\n$ {cmd if isinstance(cmd, str) else ' '.join(cmd)}")
    sys.stdout.flush()
    return subprocess.run(cmd, check=check, shell=isinstance(cmd, str))


print("=" * 60)
print("ORBIT WARS — PUFFERLIB COLAB SETUP")
print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
print("=" * 60)

# 1. Install system dependencies
print("\n--- [1/4] Installing system packages ---")
packages = [
    "clang",
    "libomp-dev",
    "ccache",
]
run("apt-get update -qq")
run(f"apt-get install -y -qq {' '.join(packages)}")

# 2. Symlink python -> python3 if missing
print("\n--- [2/4] Setting up python symlink ---")
symlink_cmd = 'command -v python >/dev/null 2>&1 || ln -s "$(which python3)" /usr/local/bin/python'
run(symlink_cmd)

# 3. Install Python dependencies using uv
print("\n--- [3/4] Installing Python dependencies ---")
try:
    run("curl -LsSf https://astral.sh/uv/install.sh | sh")
    os.environ["PATH"] += os.pathsep + os.path.expanduser("~/.local/bin")
    run("uv pip install --system pybind11 numpy rich kaggle-environments wandb 2>/dev/null || pip install pybind11 numpy rich kaggle-environments wandb")
except Exception:
    run("pip install pybind11 numpy rich kaggle-environments wandb")

# 4. Clone and install the repository in editable mode
print("\n--- [4/4] Cloning repository and installing pufferlib ---")
if not os.path.exists(REPO_DIR):
    run(f"git clone {REPO_URL} {REPO_DIR}")
else:
    print(f"Repository already cloned in {REPO_DIR}")

run(f"pip install -e {REPO_DIR}")

print("\n" + "=" * 60)
print("COLAB SETUP COMPLETED SUCCESSFULLY")
print("=" * 60)
