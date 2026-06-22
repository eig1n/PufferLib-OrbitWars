#!/usr/bin/env python3
"""
Orbit Wars — Colab Test Runner

Usage (from local machine):
    colab exec -f colab_test.py 2>&1 | tee colab_test_run.log
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
print("ORBIT WARS — PUFFERLIB COLAB TEST RUNNER")
print(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
print("=" * 60)

# Navigate to pufferlib directory
if not os.path.exists("pufferlib"):
    print("Error: 'pufferlib' directory not found! Run colab_setup.py first.")
    sys.exit(1)

os.chdir("pufferlib")

# ------------------------------------------------------------------
# 1. Pull latest code changes
# ------------------------------------------------------------------
print("\n--- [1/3] Pulling latest code changes from GitHub ---")
run("git pull")
run("git log --oneline -5")

# ------------------------------------------------------------------
# 2. Build orbit_wars
# ------------------------------------------------------------------
print("\n--- [2/3] Building orbit_wars environment ---")
t0 = time.time()
run(["bash", "build.sh", "orbit_wars", "--cpu"])
build_time = time.time() - t0
print(f"Build completed in {build_time:.1f}s")

# ------------------------------------------------------------------
# 3. Run tests
# ------------------------------------------------------------------
print("\n--- [3/3] Running test suites ---")
t0 = time.time()

print("\n>>> Running Environment Test Suite (test_orbit_wars.py) <<<")
code_env = run_stream([sys.executable, "tests/test_orbit_wars.py"])

print("\n>>> Running Parity Test Suite (test_orbit_wars_parity.py) <<<")
code_parity = run_stream([sys.executable, "tests/test_orbit_wars_parity.py"])

test_time = time.time() - t0
exit_code = 0 if (code_env == 0 and code_parity == 0) else 1

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"  Build time:        {build_time:.1f}s")
print(f"  Test time:         {test_time:.1f}s")
print(f"  Env Test Status:   {'✅ PASSED' if code_env == 0 else '❌ FAILED'}")
print(f"  Parity Test Status: {'✅ PASSED' if code_parity == 0 else '❌ FAILED'}")
print(f"  Overall Status:    {'✅ ALL PASSED' if exit_code == 0 else '❌ FAILED'}")
print(f"  Finished:          {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
print("=" * 60)

sys.exit(exit_code)
