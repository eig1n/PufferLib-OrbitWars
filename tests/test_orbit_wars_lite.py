#!/usr/bin/env python3
import ctypes
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

PUFFERLIB_ROOT = Path(__file__).resolve().parents[1]
os.chdir(PUFFERLIB_ROOT)
sys.path.insert(0, str(PUFFERLIB_ROOT))

from tests.test_orbit_wars_decoder import make_env
from tests.test_orbit_wars_parity import OrbitWarsStruct

EXPECTED_OBS_SIZE = 848
EXPECTED_NUM_ATNS = 30


def board_to_action(v):
    return float(v) / 50.0 - 1.0


def float_view(ptr, count):
    array_t = ctypes.c_float * count
    return np.ctypeslib.as_array(array_t.from_address(ptr))


def compile_lite_helper():
    src_path = PUFFERLIB_ROOT / "tests/orbit_wars_lite_test_lib.c"
    so_path = PUFFERLIB_ROOT / "tests/orbit_wars_lite_test_lib.so"
    subprocess.run(
        [
            "cc",
            "-std=c99",
            "-shared",
            "-fPIC",
            "-O2",
            "-I",
            str(PUFFERLIB_ROOT),
            "-I",
            str(PUFFERLIB_ROOT / "raylib-5.5_linux_amd64/include"),
            "-o",
            str(so_path),
            str(src_path),
            "-lm",
        ],
        check=True,
    )
    lib = ctypes.CDLL(str(so_path))
    lib.init.argtypes = [ctypes.POINTER(OrbitWarsStruct)]
    lib.init.restype = None
    lib.test_lite_obs_size.restype = ctypes.c_int
    lib.test_lite_num_atns.restype = ctypes.c_int
    lib.test_lite_amount_to_ships.argtypes = [ctypes.c_float, ctypes.c_int]
    lib.test_lite_amount_to_ships.restype = ctypes.c_int
    lib.test_decode_lite_actions_for_slot.argtypes = [
        ctypes.POINTER(OrbitWarsStruct),
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_float),
    ]
    lib.test_decode_lite_actions_for_slot.restype = ctypes.c_int
    return lib


def test_lite_decoder_one_fleet_per_source():
    lib = compile_lite_helper()
    assert lib.test_lite_obs_size() == EXPECTED_OBS_SIZE
    assert lib.test_lite_num_atns() == EXPECTED_NUM_ATNS
    assert lib.test_lite_amount_to_ships(0.0, 100) == 0
    assert lib.test_lite_amount_to_ships(0.1, 100) == 20
    assert lib.test_lite_amount_to_ships(0.6, 300) == 120
    assert lib.test_lite_amount_to_ships(1.0, 100) == 100

    env = make_env(
        lib,
        [
            (0, 0, 20, 20, 100, 1),
            (1, 0, 20, 30, 100, 1),
            (2, 1, 80, 20, 5, 1),
        ],
    )
    actions = np.zeros(EXPECTED_NUM_ATNS, dtype=np.float32)
    slots = [
        (1.0, 1.0, 0.0, 20, 20),
        (0.5, 1.0, 0.0, 21, 20),
        (0.9, 0.0, 1.0, 20, 30),
    ]
    for i, (amount, dir_x, dir_y, sx, sy) in enumerate(slots):
        base = i * 5
        actions[base + 0] = amount
        actions[base + 1] = dir_x
        actions[base + 2] = dir_y
        actions[base + 3] = board_to_action(sx)
        actions[base + 4] = board_to_action(sy)

    launches = lib.test_decode_lite_actions_for_slot(
        ctypes.byref(env),
        0,
        actions.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
    )
    assert launches == 2
    assert env.num_raw_actions[0] == 2
    assert {env.raw_actions[0][i].from_planet_id for i in range(2)} == {0, 1}
    angles = {env.raw_actions[0][i].from_planet_id: env.raw_actions[0][i].angle for i in range(2)}
    assert abs(angles[0]) < 1e-5
    assert abs(angles[1] - np.pi / 2.0) < 1e-5


def test_lite_build_and_step():
    env = os.environ.copy()
    venv_bin = PUFFERLIB_ROOT / ".venv/bin"
    env["PATH"] = f"{venv_bin}{os.path.pathsep}{env.get('PATH', '')}"
    subprocess.run(["bash", "build.sh", "orbit_wars_lite", "--cpu"], cwd=PUFFERLIB_ROOT, env=env, check=True)

    import pufferlib._C as cmod

    assert cmod.env_name == "orbit_wars_lite"
    args = {
        "vec": {
            "total_agents": 64.0,
            "num_buffers": 1.0,
            "num_threads": 1.0,
        },
        "env": {
            "num_agents": 2.0,
        },
    }
    vec = cmod.create_vec(args, 0)
    try:
        vec.reset()
        assert vec.obs_size == EXPECTED_OBS_SIZE
        assert vec.num_atns == EXPECTED_NUM_ATNS
        assert all(sz == 1 for sz in vec.act_sizes)

        actions = np.random.uniform(-1.0, 1.0, size=(64, vec.num_atns)).astype(np.float32)
        obs = float_view(vec.obs_ptr, 64 * vec.obs_size).reshape(64, vec.obs_size)
        for _ in range(500):
            actions[:] = np.random.uniform(-1.0, 1.0, size=actions.shape).astype(np.float32)
            vec.cpu_step(actions.ctypes.data)

        obs_min = float(obs.min())
        obs_max = float(obs.max())
        assert obs_min >= -5.0
        assert obs_max <= 5.0

        vec.reset()
        bench_steps = 2000
        start = time.perf_counter()
        for _ in range(bench_steps):
            actions[:] = np.random.uniform(-1.0, 1.0, size=actions.shape).astype(np.float32)
            vec.cpu_step(actions.ctypes.data)
        elapsed = time.perf_counter() - start
        sps = bench_steps * 64 / elapsed
        print(f"orbit_wars_lite local random-action SPS: {sps:,.0f}")
    finally:
        vec.close()


def main():
    test_lite_build_and_step()
    test_lite_decoder_one_fleet_per_source()
    print("orbit_wars_lite tests passed")


if __name__ == "__main__":
    main()
