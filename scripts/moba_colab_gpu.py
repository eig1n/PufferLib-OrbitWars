#!/usr/bin/env python3
"""
Moba Colab GPU runner.
Assumes colab_setup.py has been run.
Pulls latest changes, builds the CUDA backend for moba, runs a short training job for 1 minute,
and saves its own console log.
"""

import os
import subprocess
import sys
import time

REPO_DIR = "pufferlib"


class Tee:
    def __init__(self, filename):
        self.file = open(filename, "w")
        self.stdout = sys.stdout

    def write(self, data):
        self.file.write(data)
        self.stdout.write(data)

    def flush(self):
        self.file.flush()
        self.stdout.flush()


def run(cmd, cwd=None, check=True, env=None):
    print(f"\n$ {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    sys.stdout.flush()
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        shell=isinstance(cmd, str),
    )
    print(proc.stdout, end="")
    sys.stdout.flush()
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd, output=proc.stdout)
    return proc


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
            sys.stdout.flush()
            lines.append(line)
        if proc.poll() is not None:
            rest = proc.stdout.read()
            if rest:
                print(rest, end="")
                sys.stdout.flush()
                lines.append(rest)
            return proc.returncode, "".join(lines)
        if timeout and time.time() - start > timeout:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            return 124, "".join(lines)


# Initialize Tee logging
log_dir = os.path.join(REPO_DIR, "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "moba_colab_gpu.log")
sys.stdout = Tee(log_file)
sys.stderr = sys.stdout

print("=" * 72)
print("MOBA ENVIRONMENT - COLAB GPU RUN")
print(f"Started UTC: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}")
print("=" * 72)

# Git pull to fetch latest code
run(["git", "pull", "--ff-only"], cwd=REPO_DIR)
run(["git", "log", "--oneline", "-3"], cwd=REPO_DIR)

env = os.environ.copy()
env["PATH"] = os.path.expanduser("~/.local/bin") + os.pathsep + env.get("PATH", "")

# Build CUDA for moba
run(["bash", "build.sh", "moba"], cwd=REPO_DIR, env=env)

# Train for 60 seconds (1 minute)
train_cmd = [
    sys.executable,
    "-m",
    "pufferlib.pufferl",
    "train",
    "moba",
]
code, train_log = run_stream(train_cmd, cwd=REPO_DIR, timeout=60, env=env)
print(f"Training finished with exit code {code}")
print(f"CONSOLE_LOG_FILE=/content/pufferlib/logs/moba_colab_gpu.log")
print("=" * 72)
