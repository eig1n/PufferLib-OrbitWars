#!/usr/bin/env python3
import ctypes
import math
import os
import subprocess
import sys
from pathlib import Path
import numpy as np

# Setup pathing
PUFFERLIB_ROOT = Path(__file__).resolve().parents[1]
os.chdir(PUFFERLIB_ROOT)
sys.path.insert(0, str(PUFFERLIB_ROOT))
sys.path.insert(0, str(PUFFERLIB_ROOT / "orbit-wars"))

from tests.test_orbit_wars_parity import OrbitWarsStruct, compile_and_load
from puffer_agent.policy_adapter import (
    compact_features,
    policy_actions_to_moves,
    OBS_SIZE,
    NUM_ATNS
)


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
    lib.test_compute_observations_for_slot.argtypes = [
        ctypes.POINTER(OrbitWarsStruct),
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_float)
    ]
    lib.test_compute_observations_for_slot.restype = None
    return lib


def make_c_env(lib, planets, fleets=None, comets=None, current_step=0, angular_velocity=0.03):
    env = OrbitWarsStruct()
    lib.init(ctypes.byref(env))
    env.num_agents = 2
    env.max_steps = 500
    env.current_step = current_step
    env.angular_velocity = angular_velocity
    env.num_comet_groups = 0

    for i in range(2):
        env.slot_for_color[i] = i

    for i in range(48):
        env.planets[i].active = 0
        env.planet_orbits[i] = 0

    for i in range(1024):
        env.fleets[i].active = 0

    env.num_planets = len(planets)
    for i, row in enumerate(planets):
        pid, owner, x, y, radius, ships, prod, is_comet, is_orbiting = row
        env.planets[i].id = pid
        env.planets[i].owner = owner
        env.planets[i].x = x
        env.planets[i].y = y
        env.planets[i].radius = radius
        env.planets[i].ships = ships
        env.planets[i].production = prod
        env.planets[i].is_comet = 1 if is_comet else 0
        env.planets[i].active = 1
        env.planet_angle[i] = math.atan2(y - 50.0, x - 50.0)
        env.planet_orbital_radius[i] = math.hypot(x - 50.0, y - 50.0)
        env.planet_orbits[i] = 1 if is_orbiting else 0

    if fleets:
        for i, f in enumerate(fleets):
            fid, owner, x, y, angle, from_pid, ships = f
            env.fleets[i].id = fid
            env.fleets[i].owner = owner
            env.fleets[i].x = x
            env.fleets[i].y = y
            env.fleets[i].angle = angle
            env.fleets[i].from_planet_id = from_pid
            env.fleets[i].ships = ships
            env.fleets[i].active = 1

    return env


def c_env_to_kaggle_obs(env):
    obs = {}
    planets = []
    comet_planet_ids = []
    for i in range(48):
        pl = env.planets[i]
        if pl.active:
            planets.append([
                pl.id,
                pl.owner,
                pl.x,
                pl.y,
                pl.radius,
                pl.ships,
                pl.production
            ])
            if pl.is_comet:
                comet_planet_ids.append(pl.id)

    obs["planets"] = planets
    obs["comet_planet_ids"] = comet_planet_ids

    fleets = []
    for i in range(1024):
        fl = env.fleets[i]
        if fl.active:
            fleets.append([
                fl.id,
                fl.owner,
                fl.x,
                fl.y,
                fl.angle,
                fl.from_planet_id,
                fl.ships
            ])
    obs["fleets"] = fleets
    obs["step"] = env.current_step
    obs["angular_velocity"] = env.angular_velocity
    return obs


def verify_observation_parity(lib, env, player_id):
    # Get C obs
    c_obs_arr = (ctypes.c_float * OBS_SIZE)()
    lib.test_compute_observations_for_slot(ctypes.byref(env), player_id, c_obs_arr)
    c_obs = list(c_obs_arr)

    # Get Py obs
    kaggle_obs = c_env_to_kaggle_obs(env)
    kaggle_obs["player"] = player_id
    py_obs = compact_features(kaggle_obs, player_id)

    # Compare
    assert len(c_obs) == len(py_obs), f"Obs length mismatch: C={len(c_obs)}, Py={len(py_obs)}"
    
    mismatches = []
    for i in range(len(c_obs)):
        if not math.isclose(c_obs[i], py_obs[i], abs_tol=1e-5):
            mismatches.append((i, c_obs[i], py_obs[i]))

    if mismatches:
        print(f"FAILED Observation Parity for Player {player_id}:", file=sys.stderr)
        for idx, cv, pv in mismatches[:20]:
            # Print context about which feature it is
            if idx < 384:
                planet_idx = idx // 8
                feat_idx = idx % 8
                print(f"  Planet {planet_idx} Feat {feat_idx}: C={cv:.6f}, Py={pv:.6f}", file=sys.stderr)
            elif idx < 784:
                grid_idx = idx - 384
                cell_idx = grid_idx // 4
                feat_idx = grid_idx % 4
                print(f"  Grid Cell {cell_idx} Feat {feat_idx}: C={cv:.6f}, Py={pv:.6f}", file=sys.stderr)
            elif idx < 840:
                fleet_idx = (idx - 784) // 7
                feat_idx = (idx - 784) % 7
                print(f"  Top Fleet {fleet_idx} Feat {feat_idx}: C={cv:.6f}, Py={pv:.6f}", file=sys.stderr)
            else:
                global_idx = idx - 840
                print(f"  Global Feat {global_idx}: C={cv:.6f}, Py={pv:.6f}", file=sys.stderr)
        assert False, f"Observation parity failed at {len(mismatches)} indices."
    else:
        print(f"SUCCESS: Observation parity verified for Player {player_id}")


def verify_action_parity(lib, env, player_id, actions):
    # Decode in C
    env_c = make_c_env(
        lib,
        planets=[
            (env.planets[i].id, env.planets[i].owner, env.planets[i].x, env.planets[i].y,
             env.planets[i].radius, env.planets[i].ships, env.planets[i].production,
             env.planets[i].is_comet, env.planet_orbits[i])
            for i in range(48) if env.planets[i].active
        ],
        fleets=[
            (env.fleets[i].id, env.fleets[i].owner, env.fleets[i].x, env.fleets[i].y,
             env.fleets[i].angle, env.fleets[i].from_planet_id, env.fleets[i].ships)
            for i in range(1024) if env.fleets[i].active
        ],
        current_step=env.current_step,
        angular_velocity=env.angular_velocity
    )
    
    # We must set slot_for_color mapping correctly so player_id maps to slot
    # C decoder resolves slot -> player_id using ow_player_for_slot which loops over slot_for_color.
    # We want: env_c.slot_for_color[player_id] = slot
    # Let's map player_id to slot 0: env_c.slot_for_color[player_id] = 0
    env_c.slot_for_color[player_id] = 0
    
    act_arr = (ctypes.c_float * NUM_ATNS)(*actions)
    launches_c = lib.test_decode_lite_actions_for_slot(
        ctypes.byref(env_c),
        0, # slot 0
        act_arr
    )
    
    moves_c = []
    for i in range(env_c.num_raw_actions[player_id]):
        act = env_c.raw_actions[player_id][i]
        moves_c.append([int(act.from_planet_id), float(act.angle), int(act.ships)])

    # Decode in Python
    kaggle_obs = c_env_to_kaggle_obs(env)
    kaggle_obs["player"] = player_id
    moves_py = policy_actions_to_moves(actions, kaggle_obs, player_id)

    # Compare moves
    # Standardize moves for sorting
    moves_c.sort(key=lambda m: (m[0], m[1], m[2]))
    moves_py.sort(key=lambda m: (m[0], m[1], m[2]))

    assert len(moves_c) == len(moves_py), f"Moves count mismatch: C={len(moves_c)} ({moves_c}), Py={len(moves_py)} ({moves_py})"
    for mc, mpy in zip(moves_c, moves_py):
        assert mc[0] == mpy[0], f"Move from_planet mismatch: C={mc[0]}, Py={mpy[0]}"
        assert math.isclose(mc[1], mpy[1], abs_tol=1e-4), f"Move angle mismatch: C={mc[1]}, Py={mpy[1]}"
        assert mc[2] == mpy[2], f"Move ships mismatch: C={mc[2]}, Py={mpy[2]}"

    print(f"SUCCESS: Action parity verified with {len(moves_c)} moves")


def main():
    lib = compile_lite_helper()
    
    # Define test planets
    # pid, owner, x, y, radius, ships, prod, is_comet, is_orbiting
    planets = [
        (0, 0, 20.0, 20.0, 3.0, 100, 3, False, True),  # mine, orbiting
        (1, 1, 10.0, 90.0, 2.0, 10, 1, False, False),  # enemy, static
        (2, -1, 90.0, 90.0, 4.0, 50, 4, False, False), # neutral, static
        (3, -1, 40.0, 40.0, 1.0, 5, 1, True, False),   # comet, static
    ]
    
    # Define test fleets
    # fid, owner, x, y, angle, from_pid, ships
    fleets = [
        (0, 0, 25.0, 25.0, 0.5, 0, 10),
        (1, 1, 75.0, 22.0, 3.14, 1, 5),
    ]

    print("\n--- Running Observation Parity Test 1 (Basic) ---")
    env = make_c_env(lib, planets, fleets)
    verify_observation_parity(lib, env, 0)
    verify_observation_parity(lib, env, 1)

    print("\n--- Running Observation Parity Test 2 (Dense Fleets & Grid) ---")
    # Add many fleets to check grid summing and sorting
    extra_fleets = [
        (i, i % 2, 10.0 + 5.0 * (i % 10), 10.0 + 8.0 * (i // 10), 0.1 * i, 0, 10 + i)
        for i in range(40)
    ]
    env_dense = make_c_env(lib, planets, extra_fleets)
    verify_observation_parity(lib, env_dense, 0)

    print("\n--- Running Action Parity Test 1 (Static Takeover) ---")
    # Action array layout: 6 slots * 5 features
    # Each slot: amount, sx, sy, tx, ty
    # We want Player 0 to target Planet 1 (enemy) from Planet 0 (owned)
    # Source is at 20, 20. Target is at 10, 90.
    actions = [0.0] * 30
    # Slot 0 action
    actions[0] = 0.9  # amount
    actions[1] = float(20.0 / 50.0 - 1.0) # sx (matches 20.0)
    actions[2] = float(20.0 / 50.0 - 1.0) # sy (matches 20.0)
    actions[3] = float(10.0 / 50.0 - 1.0) # tx (matches 10.0)
    actions[4] = float(90.0 / 50.0 - 1.0) # ty (matches 90.0)
    
    verify_action_parity(lib, env, 0, actions)

    print("\n--- Running Action Parity Test 2 (No-op/Blocker/Invalid) ---")
    # Let's send a ray straight through the sun (50, 50)
    # Source: 20, 20. Target: 90, 90 (passing right through center 50,50)
    # This should be blocked by the sun, so 0 moves.
    actions_invalid = [0.0] * 30
    actions_invalid[0] = 0.9
    actions_invalid[1] = float(20.0 / 50.0 - 1.0)
    actions_invalid[2] = float(20.0 / 50.0 - 1.0)
    actions_invalid[3] = float(90.0 / 50.0 - 1.0)
    actions_invalid[4] = float(90.0 / 50.0 - 1.0)
    
    verify_action_parity(lib, env, 0, actions_invalid)

    print("\nALL ADAPTER PARITY TESTS PASSED!")


if __name__ == "__main__":
    main()
