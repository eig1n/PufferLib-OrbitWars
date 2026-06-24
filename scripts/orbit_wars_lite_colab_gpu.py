#!/usr/bin/env python3
"""
Orbit Wars Lite Colab GPU runner.
Assumes colab_setup.py has been run.
Pulls latest changes, builds the CUDA backend, runs tests, trains for 10 minutes,
and saves its own console log.
"""

import glob
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
log_file = os.path.join(log_dir, "orbit_wars_lite_colab_gpu.log")
sys.stdout = Tee(log_file)
sys.stderr = sys.stdout

print("=" * 72)
print("ORBIT WARS LITE - COLAB GPU RUN")
print(f"Started UTC: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}")
print("=" * 72)

# Git pull to fetch latest code
run(["git", "pull", "--ff-only"], cwd=REPO_DIR)
run(["git", "log", "--oneline", "-3"], cwd=REPO_DIR)

env = os.environ.copy()
env["PATH"] = os.path.expanduser("~/.local/bin") + os.pathsep + env.get("PATH", "")

# Run test suite
test_code, _ = run_stream([sys.executable, "tests/test_orbit_wars_lite.py"], cwd=REPO_DIR, env=env)
if test_code != 0:
    raise SystemExit(test_code)

# Build CUDA for orbit_wars_lite
run(["bash", "build.sh", "orbit_wars_lite"], cwd=REPO_DIR, env=env)

# Train for 10 minutes (600 seconds)
train_cmd = [
    sys.executable,
    "-m",
    "pufferlib.pufferl",
    "train",
    "orbit_wars_lite",
]
code, train_log = run_stream(train_cmd, cwd=REPO_DIR, timeout=600, env=env)
if code != 0 and code != 124:
    print(f"Training command exited with {code}")
    raise SystemExit(code)

checkpoints = sorted(glob.glob(os.path.join(REPO_DIR, "checkpoints", "orbit_wars_lite", "**", "*.bin"), recursive=True))
print("\n" + "=" * 72)
if checkpoints:
    newest = checkpoints[-1]
    print(f"NEWEST_CHECKPOINT={newest}")
    print("Download locally with:")
    print(f"  colab download {newest} checkpoints/orbit_wars_lite/colab_t4_selfplay_128_5/checkpoint.bin")
else:
    print("No checkpoint found under pufferlib/checkpoints/orbit_wars_lite")
print(f"CONSOLE_LOG_FILE=/content/pufferlib/logs/orbit_wars_lite_colab_gpu.log")
print("=" * 72)
