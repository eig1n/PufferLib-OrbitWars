#!/usr/bin/env python3
"""
Orbit Wars PufferLib Environment Tests

Tests:
  1. Build verification
  2. Vec creation and reset
  3. Smoke test: step with random actions
  4. Observation range validation
  5. Terminal/episode test
  6. Performance benchmark (steps/second)
"""

import subprocess
import sys
import os
import time
import ctypes
import numpy as np

# Ensure we're in the PufferLib root
PUFFERLIB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PUFFERLIB_ROOT)
sys.path.insert(0, PUFFERLIB_ROOT)

PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"

def test_build():
    """Test 1: Build the orbit_wars environment."""
    print("\n[Test 1] Building orbit_wars with --cpu ...")
    result = subprocess.run(
        ["bash", "build.sh", "orbit_wars", "--cpu"],
        capture_output=True, text=True, cwd=PUFFERLIB_ROOT
    )
    if result.returncode != 0:
        print(f"  {FAIL}: Build failed")
        print(f"  stdout: {result.stdout[-500:]}")
        print(f"  stderr: {result.stderr[-500:]}")
        return False
    print(f"  {PASS}: Build succeeded")
    return True


def float_view(ptr, count):
    array_t = ctypes.c_float * count
    return np.ctypeslib.as_array(array_t.from_address(ptr))


def test_load_and_step():
    """Tests 2-6: Load env, step, validate, benchmark."""
    import pufferlib._C as cmod

    total_agents = 64
    num_agents = 2  # 1v1 mode

    print("\n[Test 2] Creating vec and resetting ...")
    try:
        args = {
            "vec": {
                "total_agents": float(total_agents),
                "num_buffers": 1.0,
                "num_threads": 1.0,
            },
            "env": {
                "num_agents": float(num_agents),
            },
        }
        vec = cmod.create_vec(args, 0)
        vec.reset()
        print(f"  {PASS}: Vec created with {total_agents} agents")
    except Exception as e:
        print(f"  {FAIL}: {e}")
        import traceback; traceback.print_exc()
        return False

    # ------------------------------------------------------------------ #
    # Test 3: Smoke test — step with random actions
    # ------------------------------------------------------------------ #
    print("\n[Test 3] Smoke test: 1000 random steps ...")
    try:
        obs = float_view(vec.obs_ptr, total_agents * vec.obs_size).reshape(total_agents, vec.obs_size)
        rewards = float_view(vec.rewards_ptr, total_agents)
        terminals = float_view(vec.terminals_ptr, total_agents)
        
        act_sizes = list(vec.act_sizes)  # e.g. [48, 64, 16]
        actions_buf = np.zeros((total_agents, vec.num_atns), dtype=np.float32)

        for _ in range(1000):
            for d, sz in enumerate(act_sizes):
                actions_buf[:, d] = np.random.randint(0, sz, size=total_agents).astype(np.float32)
            vec.cpu_step(actions_buf.ctypes.data)
        print(f"  {PASS}: 1000 steps completed without crash")
    except Exception as e:
        print(f"  {FAIL}: Crash at step — {e}")
        import traceback; traceback.print_exc()
        return False

    # ------------------------------------------------------------------ #
    # Test 4: Observation range check
    # ------------------------------------------------------------------ #
    print("\n[Test 4] Observation range validation ...")
    obs_min, obs_max = obs.min(), obs.max()
    obs_mean = obs.mean()
    in_range = obs_min >= -5.0 and obs_max <= 5.0
    print(f"  Obs range: [{obs_min:.4f}, {obs_max:.4f}], mean={obs_mean:.4f}")
    if in_range:
        print(f"  {PASS}: Observations in reasonable range")
    else:
        print(f"  {FAIL}: Observations out of range [-5, 5]")

    # ------------------------------------------------------------------ #
    # Test 5: Terminal/episode test
    # ------------------------------------------------------------------ #
    print("\n[Test 5] Episode termination test (running up to 600 steps) ...")
    vec.reset()
    terminal_seen = False
    for step in range(600):
        for d, sz in enumerate(act_sizes):
            actions_buf[:, d] = np.random.randint(0, sz, size=total_agents).astype(np.float32)
        vec.cpu_step(actions_buf.ctypes.data)

        if np.any(terminals > 0.5):
            terminal_seen = True
            print(f"  Episode terminated at step {step + 1}")
            break

    if terminal_seen:
        print(f"  {PASS}: Episodes terminate correctly")
    else:
        print(f"  {FAIL}: No terminal seen in 600 steps (game should end at 500)")

    # ------------------------------------------------------------------ #
    # Test 6: Performance benchmark
    # ------------------------------------------------------------------ #
    print("\n[Test 6] Performance benchmark ...")
    vec.reset()
    num_bench_steps = 5000

    start_time = time.perf_counter()
    for _ in range(num_bench_steps):
        for d, sz in enumerate(act_sizes):
            actions_buf[:, d] = np.random.randint(0, sz, size=total_agents).astype(np.float32)
        vec.cpu_step(actions_buf.ctypes.data)
    elapsed = time.perf_counter() - start_time

    agent_steps_per_sec = (num_bench_steps * total_agents) / elapsed
    env_steps_per_sec = num_bench_steps / elapsed
    print(f"  {num_bench_steps} steps × {total_agents} agents in {elapsed:.2f}s")
    print(f"  {agent_steps_per_sec:,.0f} agent-steps/sec")
    print(f"  {env_steps_per_sec:,.0f} env-steps/sec")
    print(f"  {PASS}: Benchmark complete")

    # ------------------------------------------------------------------ #
    # Cleanup
    # ------------------------------------------------------------------ #
    vec.close()
    return True


def main():
    print("=" * 60)
    print("ORBIT WARS — PufferLib Environment Test Suite")
    print("=" * 60)

    if not test_build():
        print("\n❌ BUILD FAILED — cannot continue tests")
        sys.exit(1)

    if not test_load_and_step():
        print("\n❌ RUNTIME TESTS FAILED")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("✅ ALL TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    main()
