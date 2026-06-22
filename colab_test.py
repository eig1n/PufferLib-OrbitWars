#!/usr/bin/env python3
"""
Orbit Wars — Colab Test Runner

Usage (from local machine):
    colab new
    colab exec -f colab_test.py 2>&1 | tee colab_output.log
    colab stop
"""

import subprocess
import os
import sys
import time

def run(cmd, **kw):
    """Run a command, print it, and check for errors."""
    print(f"\n$ {cmd if isinstance(cmd, str) else ' '.join(cmd)}")
    return subprocess.run(cmd, shell=isinstance(cmd, str), check=True, **kw)

print("=" * 60)
print("ORBIT WARS — PUFFERLIB COLAB TEST")
print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
print("=" * 60)

# ------------------------------------------------------------------
# 1. Clone repository
# ------------------------------------------------------------------
print("\n--- [1/5] Cloning repository ---")
if os.path.exists("pufferlib"):
    run("rm -rf pufferlib")
run("git clone https://github.com/eig1n/PufferLib-OrbitWars.git pufferlib")
os.chdir("pufferlib")
run("git log --oneline -5")

# ------------------------------------------------------------------
# 2. Install system dependencies
# ------------------------------------------------------------------
print("\n--- [2/5] Installing system dependencies ---")
run("apt-get update -qq && apt-get install -y -qq clang libomp-dev > /dev/null 2>&1", shell=True)

# ------------------------------------------------------------------
# 3. Install Python dependencies
# ------------------------------------------------------------------
print("\n--- [3/5] Installing Python dependencies ---")
# Try uv first, fall back to pip
try:
    run("curl -LsSf https://astral.sh/uv/install.sh | sh", shell=True)
    os.environ["PATH"] += os.pathsep + os.path.expanduser("~/.local/bin")
    run("uv pip install --system pybind11 numpy rich 2>/dev/null || pip install pybind11 numpy rich", shell=True)
except Exception:
    run("pip install pybind11 numpy rich", shell=True)

# ------------------------------------------------------------------
# 4. Build orbit_wars
# ------------------------------------------------------------------
print("\n--- [4/5] Building orbit_wars environment ---")
t0 = time.time()
run(["bash", "build.sh", "orbit_wars", "--cpu"])
build_time = time.time() - t0
print(f"Build completed in {build_time:.1f}s")

# ------------------------------------------------------------------
# 5. Run tests
# ------------------------------------------------------------------
print("\n--- [5/5] Running test suite ---")
t0 = time.time()
result = subprocess.run([sys.executable, "tests/test_orbit_wars.py"])
test_time = time.time() - t0

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"  Build time:     {build_time:.1f}s")
print(f"  Test time:      {test_time:.1f}s")
print(f"  Test exit code: {result.returncode}")
print(f"  Status:         {'✅ ALL PASSED' if result.returncode == 0 else '❌ FAILED'}")
print(f"  Finished:       {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
print("=" * 60)

sys.exit(result.returncode)
