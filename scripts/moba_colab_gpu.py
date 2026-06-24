#!/usr/bin/env python3
"""
Moba Colab GPU runner.
Clones/pulls the repository, builds the CUDA backend for moba, runs a short training job for 1 minute, and displays the SPS.
"""

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
print("MOBA ENVIRONMENT - COLAB GPU RUN")
print(f"Started UTC: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}")
print("=" * 72)

if not os.path.exists(REPO_DIR):
    run(["git", "clone", REPO_URL, REPO_DIR])
else:
    run(["git", "pull", "--ff-only"], cwd=REPO_DIR)

env_vars = os.environ.copy()
env_vars["PATH"] = os.path.expanduser("~/.local/bin") + os.pathsep + env_vars.get("PATH", "")

run("apt-get update -qq && apt-get install -y -qq clang libomp-dev ccache > /dev/null", env=env_vars)
run(
    "python -m pip install -q pybind11 numpy rich kaggle-environments wandb -e .",
    cwd=REPO_DIR,
    env=env_vars,
)

# Build CUDA for moba
run(["bash", "build.sh", "moba"], cwd=REPO_DIR, env=env_vars)

# Train for 60 seconds (1 minute)
train_cmd = [
    sys.executable,
    "-m",
    "pufferlib.pufferl",
    "train",
    "moba",
]
code, train_log = run_stream(train_cmd, cwd=REPO_DIR, timeout=60, env=env_vars)
print(f"Training finished with exit code {code}")
