#!/usr/bin/env python3
import os
import sys

# Resolve repository root
current_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.abspath(os.path.join(current_dir, ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from scripts.evaluate_agent import run

if __name__ == "__main__":
    run("orbit-wars/puffer_agent/main.py", "random")
