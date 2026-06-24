#!/usr/bin/env python3
"""Measure pure C vecenv cpu_step throughput for one compiled Puffer env."""

from __future__ import annotations

import argparse
import importlib
import sys
import time

import numpy as np

from pufferlib.pufferl import load_config


def make_actions(rng: np.random.Generator, total_agents: int, act_sizes: list[int], mode: str) -> np.ndarray:
    actions = np.zeros((total_agents, len(act_sizes)), dtype=np.float32)
    if mode == "noop":
        return actions

    for i, size in enumerate(act_sizes):
        if size == 1:
            actions[:, i] = rng.uniform(-1.0, 1.0, size=total_agents)
        else:
            actions[:, i] = rng.integers(0, size, size=total_agents)
    return actions


def run_once(args: argparse.Namespace, mode: str) -> float:
    cmod = importlib.import_module("pufferlib._C")
    old_argv = sys.argv
    try:
        sys.argv = [old_argv[0]]
        cfg = load_config(args.env_name)
    finally:
        sys.argv = old_argv
    cfg["vec"]["total_agents"] = args.total_agents
    cfg["vec"]["num_buffers"] = args.num_buffers
    cfg["vec"]["num_threads"] = args.num_threads

    if args.continuous is not None:
        cfg["env"]["continuous"] = bool(args.continuous)
    if args.num_drones is not None:
        cfg["env"]["num_drones"] = args.num_drones
    if args.num_agents is not None:
        cfg["env"]["num_agents"] = args.num_agents

    rng = np.random.default_rng(args.seed)
    vec = cmod.create_vec(cfg, 0)
    try:
        vec.reset()
        act_sizes = list(vec.act_sizes)
        actions = make_actions(rng, vec.total_agents, act_sizes, mode)

        for _ in range(args.warmup):
            vec.cpu_step(actions.ctypes.data)

        start = time.perf_counter()
        for _ in range(args.steps):
            vec.cpu_step(actions.ctypes.data)
        elapsed = time.perf_counter() - start

        sps = (args.steps * vec.total_agents) / elapsed
        print(
            f"{args.env_name:16s} mode={mode:6s} "
            f"agents={vec.total_agents:5d} obs={vec.obs_size:5d} "
            f"actions={len(act_sizes):3d} elapsed={elapsed:7.3f}s sps={sps:,.0f}"
        )
        return sps
    finally:
        vec.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("env_name")
    parser.add_argument("--total-agents", type=int, default=4096)
    parser.add_argument("--num-buffers", type=int, default=1)
    parser.add_argument("--num-threads", type=int, default=1)
    parser.add_argument("--steps", type=int, default=2000)
    parser.add_argument("--warmup", type=int, default=200)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--continuous", type=int, choices=[0, 1], default=None)
    parser.add_argument("--num-drones", type=int, default=None)
    parser.add_argument("--num-agents", type=int, default=None)
    parser.add_argument("--modes", nargs="+", choices=["noop", "random"], default=["noop", "random"])
    args = parser.parse_args()

    for mode in args.modes:
        run_once(args, mode)


if __name__ == "__main__":
    main()
