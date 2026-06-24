#!/usr/bin/env python3
"""
Orbit Wars Lite Colab GPU runner.

Local usage:
    colab new --gpu T4
    colab exec -f scripts/orbit_wars_lite_colab_gpu.py

The script clones/pulls eig1n/PufferLib-OrbitWars on the Colab VM, builds the
CUDA backend for orbit_wars_lite, runs the lite smoke test, runs a short GPU
training job, and prints the newest checkpoint path.
"""

import glob
import os
import subprocess
import sys
import time


REPO_URL = "https://github.com/eig1n/PufferLib-OrbitWars.git"
REPO_DIR = "pufferlib"


def run(cmd, cwd=None, check=True, env=None):
    print(f"\n$ {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    sys.stdout.flush()
    return subprocess.run(cmd, cwd=cwd, check=check, env=env, shell=isinstance(cmd, str))


def run_stream(cmd, cwd=None, timeout=None, env=None):
    print(f"\n$ {' '.join(cmd)}")
    sys.stdout.flush()
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    start = time.time()
    lines = []
    while True:
        line = proc.stdout.readline()
        if line:
            print(line, end="")
            lines.append(line)
        if proc.poll() is not None:
            rest = proc.stdout.read()
            if rest:
                print(rest, end="")
                lines.append(rest)
            return proc.returncode, "".join(lines)
        if timeout and time.time() - start > timeout:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            return 124, "".join(lines)


print("=" * 72)
print("ORBIT WARS LITE - COLAB GPU RUN")
print(f"Started UTC: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}")
print("=" * 72)

if not os.path.exists(REPO_DIR):
    run(["git", "clone", REPO_URL, REPO_DIR])
else:
    run(["git", "pull", "--ff-only"], cwd=REPO_DIR)

run(["git", "log", "--oneline", "-3"], cwd=REPO_DIR)

env = os.environ.copy()
env["PATH"] = os.path.expanduser("~/.local/bin") + os.pathsep + env.get("PATH", "")

run("apt-get update -qq && apt-get install -y -qq clang libomp-dev ccache > /dev/null", env=env)
run(
    "python -m pip install -q pybind11 numpy rich kaggle-environments wandb -e .",
    cwd=REPO_DIR,
    env=env,
)

test_code, _ = run_stream([sys.executable, "tests/test_orbit_wars_lite.py"], cwd=REPO_DIR, env=env)
if test_code != 0:
    raise SystemExit(test_code)

# The smoke test intentionally builds the CPU backend. Rebuild CUDA afterward so
# the training command uses the native GPU backend.
run(["bash", "build.sh", "orbit_wars_lite"], cwd=REPO_DIR, env=env)

train_cmd = [
    sys.executable,
    "-m",
    "pufferlib.pufferl",
    "train",
    "orbit_wars_lite",
    "--selfplay.enabled",
    "0",
    "--vec.total-agents",
    "8192",
    "--vec.num-buffers",
    "4",
    "--vec.num-threads",
    "8",
    "--train.total-timesteps",
    "4194304",
    "--train.minibatch-size",
    "32768",
    "--train.horizon",
    "64",
    "--checkpoint-interval",
    "1",
]
code, train_log = run_stream(train_cmd, cwd=REPO_DIR, timeout=900, env=env)
if code != 0:
    print(f"Training command exited with {code}")
    raise SystemExit(code)

checkpoints = sorted(glob.glob(os.path.join(REPO_DIR, "checkpoints", "orbit_wars_lite", "**", "*.bin"), recursive=True))
print("\n" + "=" * 72)
if checkpoints:
    newest = checkpoints[-1]
    print(f"NEWEST_CHECKPOINT={newest}")
    print("Download locally with:")
    print(f"  colab download {newest}")
else:
    print("No checkpoint found under pufferlib/checkpoints/orbit_wars_lite")
print("=" * 72)
