#!/usr/bin/env python3
"""
Orbit Wars Parity Tests

Compares the fast C simulator physics and observations against
the original Python kaggle_environments Orbit Wars simulator.
"""

import os
import sys
import math
import subprocess
import ctypes
import numpy as np
from pathlib import Path
from kaggle_environments import make
from kaggle_environments.envs.orbit_wars.orbit_wars import Planet, Fleet

# Setup pathing
PUFFERLIB_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PUFFERLIB_ROOT))

# Constants
OW_MAX_PLANETS = 48
OW_MAX_FLEETS = 1024
OW_MAX_COMET_GROUPS = 5
OW_MAX_STEPS = 500
OW_MAX_PLAYERS = 4
OW_MAX_ACTIONS_PER_PLAYER = 16
OW_COMET_PATH_LEN = 100
OW_BOARD_SIZE = 100.0
OW_SUN_X = 50.0
OW_SUN_Y = 50.0
OW_SUN_RADIUS = 10.0
OW_ROTATION_RADIUS_LIMIT = 50.0
COMET_SPAWN_STEPS = [50, 150, 250, 350, 450]
OW_OBS_SIZE = OW_MAX_PLANETS * 7 + OW_MAX_FLEETS * 6 + 4

# ------------------------------------------------------------------ #
# ctypes Struct Definitions
# ------------------------------------------------------------------ #

class PlanetC(ctypes.Structure):
    _fields_ = [
        ("id", ctypes.c_int),
        ("owner", ctypes.c_int),
        ("x", ctypes.c_double),
        ("y", ctypes.c_double),
        ("radius", ctypes.c_double),
        ("ships", ctypes.c_int),
        ("production", ctypes.c_int),
        ("is_comet", ctypes.c_int),
        ("active", ctypes.c_int),
    ]

class FleetC(ctypes.Structure):
    _fields_ = [
        ("id", ctypes.c_int),
        ("owner", ctypes.c_int),
        ("x", ctypes.c_double),
        ("y", ctypes.c_double),
        ("angle", ctypes.c_double),
        ("from_planet_id", ctypes.c_int),
        ("ships", ctypes.c_int),
        ("speed", ctypes.c_double),
        ("active", ctypes.c_int),
    ]

class CometGroupC(ctypes.Structure):
    _fields_ = [
        ("planet_ids", ctypes.c_int * 4),
        ("path_index", ctypes.c_int),
        ("num_steps", ctypes.c_int),
        ("paths_x", (ctypes.c_double * OW_COMET_PATH_LEN) * 4),
        ("paths_y", (ctypes.c_double * OW_COMET_PATH_LEN) * 4),
        ("active", ctypes.c_int),
    ]

class RawActionC(ctypes.Structure):
    _fields_ = [
        ("from_planet_id", ctypes.c_int),
        ("angle", ctypes.c_double),
        ("ships", ctypes.c_int),
    ]

class Log(ctypes.Structure):
    _fields_ = [
        ("perf", ctypes.c_float),
        ("score", ctypes.c_float),
        ("episode_return", ctypes.c_float),
        ("episode_length", ctypes.c_float),
        ("n", ctypes.c_float),
    ]

class OrbitWarsStruct(ctypes.Structure):
    _fields_ = [
        ("log", Log),
        ("client", ctypes.c_void_p),
        ("observations", ctypes.c_void_p),
        ("actions", ctypes.c_void_p),
        ("rewards", ctypes.c_void_p),
        ("terminals", ctypes.c_void_p),

        ("tag", ctypes.c_int),
        ("boundary_reached", ctypes.c_int),

        ("obs_ptr", ctypes.c_void_p * OW_MAX_PLAYERS),
        ("action_ptr", ctypes.c_void_p * OW_MAX_PLAYERS),
        ("reward_ptr", ctypes.c_void_p * OW_MAX_PLAYERS),
        ("terminal_ptr", ctypes.c_void_p * OW_MAX_PLAYERS),

        ("slot_for_color", ctypes.c_int * OW_MAX_PLAYERS),

        ("num_agents", ctypes.c_int),
        ("max_steps", ctypes.c_int),
        ("rng", ctypes.c_uint),

        ("planets", PlanetC * OW_MAX_PLANETS),
        ("num_planets", ctypes.c_int),

        ("fleets", FleetC * OW_MAX_FLEETS),

        ("comet_groups", CometGroupC * OW_MAX_COMET_GROUPS),
        ("num_comet_groups", ctypes.c_int),

        ("raw_actions", (RawActionC * OW_MAX_ACTIONS_PER_PLAYER) * OW_MAX_PLAYERS),
        ("num_raw_actions", ctypes.c_int * OW_MAX_PLAYERS),

        ("angular_velocity", ctypes.c_double),
        ("next_fleet_id", ctypes.c_int),
        ("next_planet_id", ctypes.c_int),
        ("current_step", ctypes.c_int),

        ("planet_angle", ctypes.c_double * OW_MAX_PLANETS),
        ("planet_orbital_radius", ctypes.c_double * OW_MAX_PLANETS),
        ("planet_orbits", ctypes.c_int * OW_MAX_PLANETS),

        ("arriving_ships", (ctypes.c_int * OW_MAX_PLAYERS) * OW_MAX_PLANETS),
        ("prevent_reset", ctypes.c_int),
    ]

# ------------------------------------------------------------------ #
# Compilation & Loading
# ------------------------------------------------------------------ #

def compile_and_load():
    src_path = PUFFERLIB_ROOT / "tests/orbit_wars_test_lib.c"
    so_path = PUFFERLIB_ROOT / "tests/orbit_wars_test_lib.so"
    
    # Run compiler
    subprocess.run(
        [
            "cc", "-std=c99", "-shared", "-fPIC", "-O2",
            "-I", str(PUFFERLIB_ROOT),
            "-I", str(PUFFERLIB_ROOT / "raylib-5.5_linux_amd64/include"),
            "-o", str(so_path),
            str(src_path),
            "-lm"
        ],
        check=True
    )
    
    lib = ctypes.CDLL(str(so_path))
    
    # Configure argument/return types
    lib.get_sizeof_orbit_wars.argtypes = []
    lib.get_sizeof_orbit_wars.restype = ctypes.c_int
    
    lib.init.argtypes = [ctypes.POINTER(OrbitWarsStruct)]
    lib.init.restype = None
    
    lib.c_reset.argtypes = [ctypes.POINTER(OrbitWarsStruct)]
    lib.c_reset.restype = None
    
    lib.c_step_core.argtypes = [ctypes.POINTER(OrbitWarsStruct)]
    lib.c_step_core.restype = None
    
    lib.test_compute_observations.argtypes = [ctypes.POINTER(OrbitWarsStruct)]
    lib.test_compute_observations.restype = None
    
    return lib

# ------------------------------------------------------------------ #
# State Copying / Injection Helpers
# ------------------------------------------------------------------ #

def copy_state_py_to_c(obs, c_env, num_agents):
    """
    Copies the Python kaggle_environments observation state into the C struct.
    """
    # 1. Planets
    raw_planets = obs.get("planets", []) if isinstance(obs, dict) else obs.planets
    # Sort planets by ID to ensure stable ordering matching observations
    sorted_planets = sorted(raw_planets, key=lambda p: p[0])
    
    c_env.num_planets = len(sorted_planets)
    
    # Clear active status for all planet slots
    for i in range(OW_MAX_PLANETS):
        c_env.planets[i].active = 0
        c_env.planet_orbits[i] = 0
        
    comet_pids = obs.get("comet_planet_ids", []) if isinstance(obs, dict) else obs.comet_planet_ids
    comet_pid_set = set(comet_pids)
    
    for i, p in enumerate(sorted_planets):
        p_id, owner, x, y, radius, ships, production = p
        
        c_env.planets[i].id = p_id
        c_env.planets[i].owner = owner
        c_env.planets[i].x = x
        c_env.planets[i].y = y
        c_env.planets[i].radius = radius
        c_env.planets[i].ships = ships
        c_env.planets[i].production = production
        c_env.planets[i].is_comet = 1 if p_id in comet_pid_set else 0
        c_env.planets[i].active = 1
        
        # Planet rotation properties
        dx = x - OW_SUN_X
        dy = y - OW_SUN_Y
        r = math.sqrt(dx*dx + dy*dy)
        c_env.planet_orbital_radius[i] = r
        
        calc_angle = math.atan2(dy, dx)
        
        # It orbits if it's not a comet and orbital_radius + radius < ROTATION_RADIUS_LIMIT
        if p_id not in comet_pid_set and (r + radius < OW_ROTATION_RADIUS_LIMIT):
            c_env.planet_orbits[i] = 1
            step = obs.get("step", 0) if isinstance(obs, dict) else obs.step
            if step > 0:
                ang_vel = obs.get("angular_velocity", 0.0) if isinstance(obs, dict) else obs.angular_velocity
                c_env.planet_angle[i] = calc_angle + ang_vel
            else:
                c_env.planet_angle[i] = calc_angle
        else:
            c_env.planet_orbits[i] = 0
            c_env.planet_angle[i] = calc_angle

    # 2. Fleets
    raw_fleets = obs.get("fleets", []) if isinstance(obs, dict) else obs.fleets
    # Sort fleets by ID
    sorted_fleets = sorted(raw_fleets, key=lambda f: f[0])
    
    for i in range(OW_MAX_FLEETS):
        c_env.fleets[i].active = 0
        
    for i, f in enumerate(sorted_fleets):
        if i >= OW_MAX_FLEETS:
            break
        f_id, owner, x, y, angle, from_pid, ships = f
        
        c_env.fleets[i].id = f_id
        c_env.fleets[i].owner = owner
        c_env.fleets[i].x = x
        c_env.fleets[i].y = y
        c_env.fleets[i].angle = angle
        c_env.fleets[i].from_planet_id = from_pid
        c_env.fleets[i].ships = ships
        # Speed: speed = 1.0 + (MAX_SPEED - 1.0) * pow(log(ships) / log(1000), 1.5)
        # speed = min(speed, MAX_SPEED)
        if ships <= 1:
            speed = 1.0
        else:
            ratio = math.log(ships) / math.log(1000.0)
            ratio = min(ratio, 1.0)
            speed = 1.0 + (6.0 - 1.0) * math.pow(ratio, 1.5)
        c_env.fleets[i].speed = speed
        c_env.fleets[i].active = 1

    # 3. Comets
    raw_comets = obs.get("comets", []) if isinstance(obs, dict) else obs.comets
    c_env.num_comet_groups = len(raw_comets)
    
    for i in range(OW_MAX_COMET_GROUPS):
        c_env.comet_groups[i].active = 0
        
    for i, g in enumerate(raw_comets):
        if i >= OW_MAX_COMET_GROUPS:
            break
        # g is a dict/namespace: planet_ids, paths, path_index
        pids = g.get("planet_ids", []) if isinstance(g, dict) else g.planet_ids
        paths = g.get("paths", []) if isinstance(g, dict) else g.paths
        path_idx = g.get("path_index", -1) if isinstance(g, dict) else g.path_index
        
        cg = c_env.comet_groups[i]
        for m in range(min(len(pids), 4)):
            cg.planet_ids[m] = pids[m]
            
        cg.path_index = path_idx
        cg.num_steps = len(paths[0]) if paths else 0
        
        for m in range(min(len(paths), 4)):
            for k in range(min(len(paths[m]), OW_COMET_PATH_LEN)):
                cg.paths_x[m][k] = paths[m][k][0]
                cg.paths_y[m][k] = paths[m][k][1]
                
        cg.active = 1

    # 4. Globals
    c_env.angular_velocity = obs.get("angular_velocity", 0.0) if isinstance(obs, dict) else obs.angular_velocity
    c_env.next_fleet_id = obs.get("next_fleet_id", 0) if isinstance(obs, dict) else obs.next_fleet_id
    c_env.current_step = obs.get("step", 0) if isinstance(obs, dict) else obs.step
    
    if sorted_planets:
        c_env.next_planet_id = max(p[0] for p in sorted_planets) + 1
    else:
        c_env.next_planet_id = 0
        
    c_env.num_agents = num_agents
    
    # Slot/color mapping should be identity for direct obs verification
    for i in range(num_agents):
        c_env.slot_for_color[i] = i

def copy_comets_py_to_c(obs, c_env):
    """
    Overwrites C comet planet structures and comet groups with Python's spawned comets.
    """
    raw_planets = obs.get("planets", []) if isinstance(obs, dict) else obs.planets
    comet_pids = obs.get("comet_planet_ids", []) if isinstance(obs, dict) else obs.comet_planet_ids
    comet_pid_set = set(comet_pids)
    
    # Copy comet planets
    for p in raw_planets:
        p_id = p[0]
        if p_id in comet_pid_set:
            # Find or append in C planets
            found_idx = -1
            for idx in range(c_env.num_planets):
                if c_env.planets[idx].id == p_id:
                    found_idx = idx
                    break
            if found_idx == -1:
                found_idx = c_env.num_planets
                c_env.num_planets += 1
                
            p_id, owner, x, y, radius, ships, production = p
            c_env.planets[found_idx].id = p_id
            c_env.planets[found_idx].owner = owner
            c_env.planets[found_idx].x = x
            c_env.planets[found_idx].y = y
            c_env.planets[found_idx].radius = radius
            c_env.planets[found_idx].ships = ships
            c_env.planets[found_idx].production = production
            c_env.planets[found_idx].is_comet = 1
            c_env.planets[found_idx].active = 1
            c_env.planet_orbits[found_idx] = 0
            c_env.planet_orbital_radius[found_idx] = 0.0
            c_env.planet_angle[found_idx] = 0.0

    # Copy comet groups
    raw_comets = obs.get("comets", []) if isinstance(obs, dict) else obs.comets
    c_env.num_comet_groups = len(raw_comets)
    for i, g in enumerate(raw_comets):
        if i >= OW_MAX_COMET_GROUPS:
            break
        pids = g.get("planet_ids", []) if isinstance(g, dict) else g.planet_ids
        paths = g.get("paths", []) if isinstance(g, dict) else g.paths
        path_idx = g.get("path_index", -1) if isinstance(g, dict) else g.path_index
        
        cg = c_env.comet_groups[i]
        for m in range(min(len(pids), 4)):
            cg.planet_ids[m] = pids[m]
        cg.path_index = path_idx
        cg.num_steps = len(paths[0]) if paths else 0
        for m in range(min(len(paths), 4)):
            for k in range(min(len(paths[m]), OW_COMET_PATH_LEN)):
                cg.paths_x[m][k] = paths[m][k][0]
                cg.paths_y[m][k] = paths[m][k][1]
        cg.active = 1

# ------------------------------------------------------------------ #
# Observation Builder (Python Reference)
# ------------------------------------------------------------------ #

def compute_reference_observation(c_env, player_id, num_agents):
    """
    Reference Python implementation of observation generation.
    Matches the C implementation feature layout.
    """
    obs_size = OW_OBS_SIZE
    features = np.zeros(obs_size, dtype=np.float32)
    idx = 0
    
    # 48 planets × 7 features
    for p_slot in range(OW_MAX_PLANETS):
        cp = c_env.planets[p_slot]
        if cp.active:
            # owner_relative
            owner = cp.owner
            if owner == -1:
                rel = -1.0 / num_agents
            elif owner == player_id:
                rel = 0.0
            else:
                rel_val = (owner - player_id + num_agents) % num_agents
                rel = float(rel_val) / float(num_agents - 1)
                
            features[idx + 0] = rel
            features[idx + 1] = cp.x / OW_BOARD_SIZE
            features[idx + 2] = cp.y / OW_BOARD_SIZE
            features[idx + 3] = cp.radius / 5.0
            features[idx + 4] = float(cp.ships) / 1000.0
            features[idx + 5] = float(cp.production) / 5.0
            features[idx + 6] = 1.0
        idx += 7
        
    # 128 fleets × 6 features
    for f_slot in range(OW_MAX_FLEETS):
        cf = c_env.fleets[f_slot]
        if cf.active:
            owner = cf.owner
            # owner_relative
            if owner == player_id:
                rel = 0.0
            else:
                rel_val = (owner - player_id + num_agents) % num_agents
                rel = float(rel_val) / float(num_agents - 1)
                
            features[idx + 0] = rel
            features[idx + 1] = cf.x / OW_BOARD_SIZE
            features[idx + 2] = cf.y / OW_BOARD_SIZE
            features[idx + 3] = cf.angle / (2.0 * math.pi)
            features[idx + 4] = float(cf.ships) / 1000.0
            features[idx + 5] = 1.0
        idx += 6
        
    # Global features (4)
    features[idx + 0] = c_env.angular_velocity / 0.05
    features[idx + 1] = float(c_env.current_step) / float(OW_MAX_STEPS)
    
    my_ships = 0
    enemy_ships = 0
    for p_slot in range(OW_MAX_PLANETS):
        cp = c_env.planets[p_slot]
        if cp.active:
            owner = cp.owner
            ships = cp.ships
            if owner == player_id:
                my_ships += ships
            elif owner != -1:
                enemy_ships += ships
            
    for f_slot in range(OW_MAX_FLEETS):
        cf = c_env.fleets[f_slot]
        if cf.active:
            owner = cf.owner
            ships = cf.ships
            if owner == player_id:
                my_ships += ships
            else:
                enemy_ships += ships
            
    features[idx + 2] = float(my_ships) / 1000.0
    features[idx + 3] = float(enemy_ships) / 1000.0
    
    return features

# ------------------------------------------------------------------ #
# Parity Verification Loops
# ------------------------------------------------------------------ #

def assert_state_parity(step, py_obs, c_env, atol=1e-4):
    """
    Asserts that the C environment state matches Python's state exactly.
    """
    py_planets = sorted(py_obs.planets, key=lambda p: p[0])
    
    # 1. Compare planets count
    assert len(py_planets) == c_env.num_planets, (
        f"Step {step}: Planet count mismatch. Py: {len(py_planets)}, C: {c_env.num_planets}"
    )
    
    # 2. Compare planet details
    for i, py_p in enumerate(py_planets):
        cp = c_env.planets[i]
        assert cp.active == 1, f"Step {step}: Expected planet index {i} to be active in C."
        assert cp.id == py_p[0], f"Step {step}: Planet ID mismatch. Py: {py_p[0]}, C: {cp.id}"
        assert cp.owner == py_p[1], f"Step {step}: Planet owner mismatch (ID {cp.id}). Py: {py_p[1]}, C: {cp.owner}"
        assert abs(cp.x - py_p[2]) <= atol, f"Step {step}: Planet X mismatch (ID {cp.id}). Py: {py_p[2]}, C: {cp.x}"
        assert abs(cp.y - py_p[3]) <= atol, f"Step {step}: Planet Y mismatch (ID {cp.id}). Py: {py_p[3]}, C: {cp.y}"
        assert abs(cp.radius - py_p[4]) <= atol, f"Step {step}: Planet radius mismatch (ID {cp.id}). Py: {py_p[4]}, C: {cp.radius}"
        assert cp.ships == py_p[5], f"Step {step}: Planet ships mismatch (ID {cp.id}). Py: {py_p[5]}, C: {cp.ships}"
        assert cp.production == py_p[6], f"Step {step}: Planet production mismatch (ID {cp.id}). Py: {py_p[6]}, C: {cp.production}"

    # 3. Compare fleets count
    py_fleets = sorted(py_obs.fleets, key=lambda f: f[0])
    c_active_fleets = sorted([f for f in c_env.fleets if f.active], key=lambda f: f.id)
    
    assert len(py_fleets) == len(c_active_fleets), (
        f"Step {step}: Fleet count mismatch. Py: {len(py_fleets)}, C: {len(c_active_fleets)}"
    )
    
    # 4. Compare fleet details
    for i, py_f in enumerate(py_fleets):
        cf = c_active_fleets[i]
        assert cf.id == py_f[0], f"Step {step}: Fleet ID mismatch. Py: {py_f[0]}, C: {cf.id}"
        assert cf.owner == py_f[1], f"Step {step}: Fleet owner mismatch (ID {cf.id}). Py: {py_f[1]}, C: {cf.owner}"
        assert abs(cf.x - py_f[2]) <= atol, f"Step {step}: Fleet X mismatch (ID {cf.id}). Py: {py_f[2]}, C: {cf.x}"
        assert abs(cf.y - py_f[3]) <= atol, f"Step {step}: Fleet Y mismatch (ID {cf.id}). Py: {py_f[3]}, C: {cf.y}"
        assert abs(cf.angle - py_f[4]) <= atol, f"Step {step}: Fleet angle mismatch (ID {cf.id}). Py: {py_f[4]}, C: {cf.angle}"
        assert cf.from_planet_id == py_f[5], f"Step {step}: Fleet from_planet_id mismatch (ID {cf.id}). Py: {py_f[5]}, C: {cf.from_planet_id}"
        assert cf.ships == py_f[6], f"Step {step}: Fleet ships mismatch (ID {cf.id}). Py: {py_f[6]}, C: {cf.ships}"


def test_parity_single_step(lib, seed, num_agents):
    """
    Tests single-step physics transition parity by copying Python state
    into C before every step, stepping both, and comparing output states.
    """
    print(f"Running single-step parity test on seed {seed} ...")
    kaggle_env = make("orbit_wars", configuration={"seed": seed})
    state = kaggle_env.reset()
    obs = state[0].observation
    
    # Create C struct and initialize
    c_env = OrbitWarsStruct()
    ctypes.memset(ctypes.byref(c_env), 0, ctypes.sizeof(c_env))
    lib.init(ctypes.byref(c_env))
    
    # Set up observation, action, reward, terminal memory buffers for C
    obs_buf = (ctypes.c_float * (OW_OBS_SIZE * 4))()
    action_buf = (ctypes.c_float * (3 * 4))()
    reward_buf = (ctypes.c_float * 4)()
    terminal_buf = (ctypes.c_float * 4)()
    
    for i in range(4):
        c_env.obs_ptr[i] = ctypes.addressof(obs_buf) + i * OW_OBS_SIZE * 4
        c_env.action_ptr[i] = ctypes.addressof(action_buf) + i * 3 * 4
        c_env.reward_ptr[i] = ctypes.addressof(reward_buf) + i * 4
        c_env.terminal_ptr[i] = ctypes.addressof(terminal_buf) + i * 4
        
    for step in range(1, 500):
        # 1. Get agent actions
        actions = []
        for p in range(num_agents):
            agent_obs = state[p].observation
            # Select random launch moves from owned planets
            moves = []
            for planet in agent_obs.planets:
                if planet[1] == p and planet[5] > 10:
                    angle = (step * 0.17 + p * 0.5) % (2.0 * math.pi)
                    ships = planet[5] // 2
                    moves.append([planet[0], angle, ships])
            actions.append(moves[:OW_MAX_ACTIONS_PER_PLAYER])
            
        # 2. Sync C struct to current Python state
        copy_state_py_to_c(obs, c_env, num_agents)
        
        # 3. Inject actions into C struct
        for p in range(num_agents):
            c_env.num_raw_actions[p] = len(actions[p])
            for idx, move in enumerate(actions[p]):
                c_env.raw_actions[p][idx].from_planet_id = move[0]
                c_env.raw_actions[p][idx].angle = move[1]
                c_env.raw_actions[p][idx].ships = move[2]
                
        # 4. Step both simulators
        state = kaggle_env.step(actions)
        obs = state[0].observation
        
        # Keep copy of C state before stepping for debugging
        c_planets_before = [PlanetC(
            id=p.id, owner=p.owner, x=p.x, y=p.y, radius=p.radius,
            ships=p.ships, production=p.production, is_comet=p.is_comet, active=p.active
        ) for p in c_env.planets]
        c_raw_actions = []
        for p in range(num_agents):
            c_raw_actions.append([
                (c_env.raw_actions[p][idx].from_planet_id, c_env.raw_actions[p][idx].angle, c_env.raw_actions[p][idx].ships)
                for idx in range(c_env.num_raw_actions[p])
            ])
            
        lib.c_step_core(ctypes.byref(c_env))
        
        # If comets just spawned in Python, overwrite C comets and comet planets
        if step in COMET_SPAWN_STEPS:
            copy_comets_py_to_c(obs, c_env)
            lib.test_compute_observations(ctypes.byref(c_env))
        
        # 5. Check state parity
        try:
            assert_state_parity(step, obs, c_env)
        except AssertionError as e:
            print(f"\n--- DEBUG: Mismatch at Step {step} ---")
            print("Python Actions sent:", actions)
            print("C Injected Actions:", c_raw_actions)
            for i, py_p in enumerate(sorted(obs.planets, key=lambda p: p[0])):
                cp_before = c_planets_before[i]
                cp_after = c_env.planets[i]
                if py_p[5] != cp_after.ships:
                    print(f"Planet ID {py_p[0]}:")
                    print(f"  Py: owner={py_p[1]}, ships={py_p[5]}, pos=({py_p[2]:.2f}, {py_p[3]:.2f})")
                    print(f"  C Before: owner={cp_before.owner}, ships={cp_before.ships}, active={cp_before.active}, pos=({cp_before.x:.2f}, {cp_before.y:.2f})")
                    print(f"  C After: owner={cp_after.owner}, ships={cp_after.ships}, active={cp_after.active}, pos=({cp_after.x:.2f}, {cp_after.y:.2f})")
            raise e
            
        # 6. Check observation parity
        for p in range(num_agents):
            ref_obs = compute_reference_observation(c_env, p, num_agents)
            c_obs_arr = np.ctypeslib.as_array(
                (ctypes.c_float * OW_OBS_SIZE).from_address(c_env.obs_ptr[p])
            )
            
            if not np.allclose(ref_obs, c_obs_arr, atol=1e-4):
                print(f"Observation mismatch at step {step} for agent {p}!")
                for idx in range(OW_OBS_SIZE):
                    if not math.isclose(ref_obs[idx], c_obs_arr[idx], abs_tol=1e-4):
                        print(f"Index {idx}: Py={ref_obs[idx]:.5f}, C={c_obs_arr[idx]:.5f}")
                        break
                raise AssertionError("Observation mismatch.")
                
    print(f"  ✓ Seed {seed} single-step parity passed.")


def test_parity_rollout(lib, seed, num_agents):
    """
    Tests multi-step rollout parity. Copy state once on reset, then step
    both environments for 500 steps, checking parity at each step.
    (Comets are injected on their spawning step to keep shapes synchronized,
    but otherwise physics runs entirely independently).
    """
    print(f"Running rollout parity test on seed {seed} ...")
    kaggle_env = make("orbit_wars", configuration={"seed": seed})
    state = kaggle_env.reset()
    obs = state[0].observation
    
    # Create C struct and initialize
    c_env = OrbitWarsStruct()
    ctypes.memset(ctypes.byref(c_env), 0, ctypes.sizeof(c_env))
    lib.init(ctypes.byref(c_env))
    
    obs_buf = (ctypes.c_float * (OW_OBS_SIZE * 4))()
    action_buf = (ctypes.c_float * (3 * 4))()
    reward_buf = (ctypes.c_float * 4)()
    terminal_buf = (ctypes.c_float * 4)()
    
    for i in range(4):
        c_env.obs_ptr[i] = ctypes.addressof(obs_buf) + i * OW_OBS_SIZE * 4
        c_env.action_ptr[i] = ctypes.addressof(action_buf) + i * 3 * 4
        c_env.reward_ptr[i] = ctypes.addressof(reward_buf) + i * 4
        c_env.terminal_ptr[i] = ctypes.addressof(terminal_buf) + i * 4
        
    # Copy state once at the start
    copy_state_py_to_c(obs, c_env, num_agents)
    
    COMET_SPAWN_STEPS = [50, 150, 250, 350, 450]
    
    for step in range(1, 500):
        # 1. Get agent actions
        actions = []
        for p in range(num_agents):
            agent_obs = state[p].observation
            moves = []
            for planet in agent_obs.planets:
                if planet[1] == p and planet[5] > 10:
                    angle = (step * 0.17 + p * 0.5) % (2.0 * math.pi)
                    ships = planet[5] // 2
                    moves.append([planet[0], angle, ships])
            actions.append(moves[:OW_MAX_ACTIONS_PER_PLAYER])
            
        # 2. Inject actions into C struct
        for p in range(num_agents):
            c_env.num_raw_actions[p] = len(actions[p])
            for idx, move in enumerate(actions[p]):
                c_env.raw_actions[p][idx].from_planet_id = move[0]
                c_env.raw_actions[p][idx].angle = move[1]
                c_env.raw_actions[p][idx].ships = move[2]
                
        # 3. Step both simulators
        state = kaggle_env.step(actions)
        obs = state[0].observation
        
        lib.c_step_core(ctypes.byref(c_env))
        
        # If comets just spawned in Python, inject them into C so they stay synced
        if step in COMET_SPAWN_STEPS:
            copy_comets_py_to_c(obs, c_env)
            lib.test_compute_observations(ctypes.byref(c_env))
        
        # 4. Check state parity
        assert_state_parity(step, obs, c_env)
        
        # 5. Check observation parity
        for p in range(num_agents):
            ref_obs = compute_reference_observation(c_env, p, num_agents)
            c_obs_arr = np.ctypeslib.as_array(
                (ctypes.c_float * OW_OBS_SIZE).from_address(c_env.obs_ptr[p])
            )
            assert np.allclose(ref_obs, c_obs_arr, atol=1e-4), (
                f"Observation mismatch at step {step} for agent {p} during rollout!"
            )
            
    print(f"  ✓ Seed {seed} rollout parity passed.")


# ------------------------------------------------------------------ #
# Custom Scenario Parity (Mock States from Original Unit Tests)
# ------------------------------------------------------------------ #

def copy_state_py_to_c_with_speed(obs, c_env, num_agents, ship_speed=6.0):
    """
    Copies a mocked observation state into the C struct, utilizing a custom ship_speed configuration.
    """
    # 1. Planets
    raw_planets = obs.get("planets", []) if isinstance(obs, dict) else obs.planets
    sorted_planets = sorted(raw_planets, key=lambda p: p[0])
    
    c_env.num_planets = len(sorted_planets)
    for i in range(OW_MAX_PLANETS):
        c_env.planets[i].active = 0
        c_env.planet_orbits[i] = 0
        
    comet_pids = obs.get("comet_planet_ids", []) if isinstance(obs, dict) else obs.comet_planet_ids
    comet_pid_set = set(comet_pids)
    
    for i, p in enumerate(sorted_planets):
        p_id, owner, x, y, radius, ships, production = p
        
        c_env.planets[i].id = p_id
        c_env.planets[i].owner = owner
        c_env.planets[i].x = x
        c_env.planets[i].y = y
        c_env.planets[i].radius = radius
        c_env.planets[i].ships = ships
        c_env.planets[i].production = production
        c_env.planets[i].is_comet = 1 if p_id in comet_pid_set else 0
        c_env.planets[i].active = 1
        
        dx = x - OW_SUN_X
        dy = y - OW_SUN_Y
        r = math.sqrt(dx*dx + dy*dy)
        c_env.planet_orbital_radius[i] = r
        
        calc_angle = math.atan2(dy, dx)
        
        if p_id not in comet_pid_set and (r + radius < OW_ROTATION_RADIUS_LIMIT):
            c_env.planet_orbits[i] = 1
            step = obs.get("step", 0) if isinstance(obs, dict) else obs.step
            if step > 0:
                ang_vel = obs.get("angular_velocity", 0.0) if isinstance(obs, dict) else obs.angular_velocity
                c_env.planet_angle[i] = calc_angle + ang_vel
            else:
                c_env.planet_angle[i] = calc_angle
        else:
            c_env.planet_orbits[i] = 0
            c_env.planet_angle[i] = calc_angle

    # 2. Fleets
    raw_fleets = obs.get("fleets", []) if isinstance(obs, dict) else obs.fleets
    sorted_fleets = sorted(raw_fleets, key=lambda f: f[0])
    
    for i in range(OW_MAX_FLEETS):
        c_env.fleets[i].active = 0
        
    for i, f in enumerate(sorted_fleets):
        if i >= OW_MAX_FLEETS:
            break
        f_id, owner, x, y, angle, from_pid, ships = f
        
        c_env.fleets[i].id = f_id
        c_env.fleets[i].owner = owner
        c_env.fleets[i].x = x
        c_env.fleets[i].y = y
        c_env.fleets[i].angle = angle
        c_env.fleets[i].from_planet_id = from_pid
        c_env.fleets[i].ships = ships
        if ships <= 1:
            speed = 1.0
        else:
            ratio = math.log(ships) / math.log(1000.0)
            ratio = min(ratio, 1.0)
            speed = 1.0 + (ship_speed - 1.0) * math.pow(ratio, 1.5)
        c_env.fleets[i].speed = speed
        c_env.fleets[i].active = 1

    # 3. Comets
    raw_comets = obs.get("comets", []) if isinstance(obs, dict) else obs.comets
    c_env.num_comet_groups = len(raw_comets)
    for i in range(OW_MAX_COMET_GROUPS):
        c_env.comet_groups[i].active = 0
    for i, g in enumerate(raw_comets):
        if i >= OW_MAX_COMET_GROUPS:
            break
        pids = g.get("planet_ids", []) if isinstance(g, dict) else g.planet_ids
        paths = g.get("paths", []) if isinstance(g, dict) else g.paths
        path_idx = g.get("path_index", -1) if isinstance(g, dict) else g.path_index
        
        cg = c_env.comet_groups[i]
        for m in range(min(len(pids), 4)):
            cg.planet_ids[m] = pids[m]
        cg.path_index = path_idx
        cg.num_steps = len(paths[0]) if paths else 0
        for m in range(min(len(paths), 4)):
            for k in range(min(len(paths[m]), OW_COMET_PATH_LEN)):
                cg.paths_x[m][k] = paths[m][k][0]
                cg.paths_y[m][k] = paths[m][k][1]
        cg.active = 1

    # 4. Globals
    c_env.angular_velocity = obs.get("angular_velocity", 0.0) if isinstance(obs, dict) else obs.angular_velocity
    c_env.next_fleet_id = obs.get("next_fleet_id", 0) if isinstance(obs, dict) else obs.next_fleet_id
    c_env.current_step = obs.get("step", 0) if isinstance(obs, dict) else obs.step
    if sorted_planets:
        c_env.next_planet_id = max(p[0] for p in sorted_planets) + 1
    else:
        c_env.next_planet_id = 0
    c_env.num_agents = num_agents
    for i in range(num_agents):
        c_env.slot_for_color[i] = i


def run_parity_step_for_scenario(lib, planets, fleets, num_agents=2, step=1, angular_velocity=0.01, config=None):
    from types import SimpleNamespace
    from kaggle_environments.envs.orbit_wars.orbit_wars import interpreter
    
    if config is None:
        config = {"shipSpeed": 6.0, "episodeSteps": 500.0, "cometSpeed": 4.0}
    
    # 1. Create Python state
    init_planets_list = []
    for p in planets:
        p_id, owner, x, y, radius, ships, production = p
        dx = x - OW_SUN_X
        dy = y - OW_SUN_Y
        r = math.sqrt(dx*dx + dy*dy)
        if (r + radius < OW_ROTATION_RADIUS_LIMIT):
            calc_angle = math.atan2(dy, dx)
            if step > 0:
                back_angle = calc_angle - (step - 1) * angular_velocity
            else:
                back_angle = calc_angle
            back_x = OW_SUN_X + r * math.cos(back_angle)
            back_y = OW_SUN_Y + r * math.sin(back_angle)
            init_planets_list.append([p_id, owner, back_x, back_y, radius, ships, production])
        else:
            init_planets_list.append(p[:])

    state = [
        SimpleNamespace(
            observation=SimpleNamespace(
                step=step,
                planets=[p[:] for p in planets],
                fleets=[f[:] for f in fleets],
                next_fleet_id=100,
                angular_velocity=angular_velocity,
                initial_planets=init_planets_list,
                comets=[],
                comet_planet_ids=[],
            ),
            action=[],
            status="ACTIVE",
            reward=0,
        )
    ]
    for i in range(1, num_agents):
        state.append(
            SimpleNamespace(
                observation=SimpleNamespace(player=i),
                action=[],
                status="ACTIVE",
                reward=0,
            )
        )
        
    env = SimpleNamespace(
        configuration=SimpleNamespace(
            shipSpeed=config["shipSpeed"], 
            episodeSteps=config["episodeSteps"], 
            cometSpeed=config["cometSpeed"]
        ),
        done=False,
    )
    
    # 2. Create C environment and initialize
    c_env = OrbitWarsStruct()
    ctypes.memset(ctypes.byref(c_env), 0, ctypes.sizeof(c_env))
    lib.init(ctypes.byref(c_env))
    
    obs_buf = (ctypes.c_float * (OW_OBS_SIZE * 4))()
    action_buf = (ctypes.c_float * (3 * 4))()
    reward_buf = (ctypes.c_float * 4)()
    terminal_buf = (ctypes.c_float * 4)()
    
    for i in range(4):
        c_env.obs_ptr[i] = ctypes.addressof(obs_buf) + i * OW_OBS_SIZE * 4
        c_env.action_ptr[i] = ctypes.addressof(action_buf) + i * 3 * 4
        c_env.reward_ptr[i] = ctypes.addressof(reward_buf) + i * 4
        c_env.terminal_ptr[i] = ctypes.addressof(terminal_buf) + i * 4

    # 3. Copy initial state to C
    copy_state_py_to_c_with_speed(state[0].observation, c_env, num_agents, ship_speed=config["shipSpeed"])
    c_env.max_steps = int(config["episodeSteps"]) - 2
    c_env.prevent_reset = 1
    
    # 4. Step Python environment
    new_state = interpreter(state, env)
    next_step = getattr(new_state[0].observation, "step", 0) + 1
    for agent_state in new_state:
        agent_state.observation.step = next_step
    py_obs = new_state[0].observation
    
    # 5. Step C environment
    lib.c_step_core(ctypes.byref(c_env))

    # 6. Check state parity
    assert_state_parity(step, py_obs, c_env)
    
    # 7. Check reward and terminal parity
    for p in range(num_agents):
        py_reward = new_state[p].reward
        py_status = new_state[p].status
        
        slot = -1
        for s in range(c_env.num_agents):
            if c_env.slot_for_color[s] == p:
                slot = s
                break
        if slot == -1:
            slot = p
            
        c_reward = ctypes.c_float.from_address(c_env.reward_ptr[slot]).value
        c_terminal = ctypes.c_float.from_address(c_env.terminal_ptr[slot]).value
        
        # Check expected C reward if provided, otherwise fallback to mapped py_reward
        expected_c_rewards = config.get("expected_c_rewards") if config else None
        if expected_c_rewards is not None:
            expected_c = expected_c_rewards[p]
        else:
            if py_reward == 1:
                expected_c = 1.0
            elif py_reward == -1:
                expected_c = 0.0
            else:
                expected_c = 0.0
            
        assert math.isclose(c_reward, expected_c, abs_tol=1e-5), (
            f"Reward mismatch for agent {p}: expected {expected_c}, got C={c_reward} (Py={py_reward})"
        )
        expected_terminal = 1.0 if py_status == "DONE" else 0.0
        assert math.isclose(c_terminal, expected_terminal, abs_tol=1e-5), (
            f"Terminal mismatch for agent {p}: Py_status={py_status}, C_terminal={c_terminal}"
        )
        
    return new_state, c_env


def test_custom_scenarios_parity(lib):
    print("Running original unit test scenario parity suite ...")
    from types import SimpleNamespace
    from kaggle_environments.envs.orbit_wars.orbit_wars import interpreter
    
    def assert_planet(py_obs, c_env, id, owner, ships):
        py_p = next(p for p in py_obs.planets if p[0] == id)
        assert py_p[1] == owner, f"Python Planet {id} owner mismatch: expected {owner}, got {py_p[1]}"
        assert py_p[5] == ships, f"Python Planet {id} ships mismatch: expected {ships}, got {py_p[5]}"
        
        found = False
        for idx in range(c_env.num_planets):
            cp = c_env.planets[idx]
            if cp.active and cp.id == id:
                assert cp.owner == owner, f"C Planet {id} owner mismatch: expected {owner}, got {cp.owner}"
                assert cp.ships == ships, f"C Planet {id} ships mismatch: expected {ships}, got {cp.ships}"
                found = True
                break
        assert found, f"Planet {id} not found in C environment"

    def assert_fleet_count(state, c_env, count):
        assert len(state[0].observation.fleets) == count, f"Python fleet count expected {count}, got {len(state[0].observation.fleets)}"
        assert len([f for f in c_env.fleets if f.active]) == count, f"C active fleet count expected {count}"

    def assert_rewards(state, c_env, p0_reward, p1_reward, status):
        assert state[0].reward == p0_reward
        assert state[1].reward == p1_reward
        assert state[0].status == status

    def assert_rewards_4p(state, c_env, p0_reward, p1_reward, p2_reward, p3_reward, status):
        assert state[0].reward == p0_reward
        assert state[1].reward == p1_reward
        assert state[2].reward == p2_reward
        assert state[3].reward == p3_reward
        assert state[0].status == status

    scenarios = [
        {
            "name": "combat_resolution_user_example",
            "num_agents": 4,
            "planets": [[0, -1, 80.0, 80.0, 5.0, 10, 0]],
            "fleets": [
                [0, 0, 76.0, 80.0, 0.0, 1, 41],
                [1, 1, 76.0, 80.0, 0.0, 2, 20],
                [2, 1, 76.0, 80.0, 0.0, 2, 20],
                [3, 2, 76.0, 80.0, 0.0, 3, 42],
            ],
            "step": 1,
            "angular_velocity": 0.01,
            "config": {"shipSpeed": 5.0, "episodeSteps": 500.0, "cometSpeed": 4.0, "expected_c_rewards": [0.5, 0.5, 0.5, 0.5]},
            "asserts": lambda state, c_env: [
                assert_planet(state[0].observation, c_env, id=0, owner=-1, ships=9),
                assert_fleet_count(state, c_env, 0)
            ]
        },
        {
            "name": "fleet_does_not_tunnel_through_rotating_planet",
            "num_agents": 2,
            "planets": [[0, -1, 50.0, 52.0, 1.0, 10, 0]],
            "fleets": [[0, 0, 49.0, 50.0, 0.0, 1, 1000]],
            "step": 1,
            "angular_velocity": math.pi,
            "config": {"shipSpeed": 2.0, "episodeSteps": 500.0, "cometSpeed": 4.0},
            "asserts": lambda state, c_env: [
                assert_planet(state[0].observation, c_env, id=0, owner=0, ships=990),
                assert_fleet_count(state, c_env, 0)
            ]
        },
        {
            "name": "rewards_set_at_max_steps",
            "num_agents": 2,
            "planets": [
                [0, 0, 80.0, 80.0, 3.0, 50, 1],
                [1, 1, 20.0, 20.0, 3.0, 30, 1],
            ],
            "fleets": [],
            "step": 498,
            "angular_velocity": 0.01,
            "config": {"shipSpeed": 6.0, "episodeSteps": 500.0, "cometSpeed": 4.0, "expected_c_rewards": [1.0, 0.0]},
            "asserts": lambda state, c_env: [
                assert_rewards(state, c_env, 1, -1, "DONE")
            ]
        },
        {
            "name": "reward_elimination_winner_and_loser",
            "num_agents": 2,
            "planets": [
                [0, 0, 80.0, 80.0, 3.0, 50, 1],
            ],
            "fleets": [],
            "step": 1,
            "angular_velocity": 0.01,
            "config": {"shipSpeed": 6.0, "episodeSteps": 500.0, "cometSpeed": 4.0, "expected_c_rewards": [1.0, 0.0]},
            "asserts": lambda state, c_env: [
                assert_rewards(state, c_env, 1, -1, "DONE")
            ]
        },
        {
            "name": "reward_elimination_via_fleets_only",
            "num_agents": 2,
            "planets": [
                [0, 0, 80.0, 80.0, 3.0, 50, 1],
            ],
            "fleets": [
                [0, 1, 30.0, 30.0, 0.0, 99, 10],
            ],
            "step": 1,
            "angular_velocity": 0.01,
            "config": {"shipSpeed": 6.0, "episodeSteps": 500.0, "cometSpeed": 4.0, "expected_c_rewards": [0.0, 0.0]},
            "asserts": lambda state, c_env: [
                assert_rewards(state, c_env, 0, 0, "ACTIVE")
            ]
        },
        {
            "name": "reward_tie_at_max_steps",
            "num_agents": 2,
            "planets": [
                [0, 0, 80.0, 80.0, 3.0, 30, 1],
                [1, 1, 20.0, 20.0, 3.0, 30, 1],
            ],
            "fleets": [],
            "step": 498,
            "angular_velocity": 0.01,
            "config": {"shipSpeed": 6.0, "episodeSteps": 500.0, "cometSpeed": 4.0, "expected_c_rewards": [0.5, 0.5]},
            "asserts": lambda state, c_env: [
                assert_rewards(state, c_env, 1, 1, "DONE")
            ]
        },
        {
            "name": "reward_all_eliminated",
            "num_agents": 2,
            "planets": [
                [0, -1, 80.0, 80.0, 3.0, 50, 1],
            ],
            "fleets": [],
            "step": 1,
            "angular_velocity": 0.01,
            "config": {"shipSpeed": 6.0, "episodeSteps": 500.0, "cometSpeed": 4.0, "expected_c_rewards": [0.5, 0.5]},
            "asserts": lambda state, c_env: [
                assert_rewards(state, c_env, -1, -1, "DONE")
            ]
        },
        {
            "name": "reward_4_player_elimination",
            "num_agents": 4,
            "planets": [
                [0, 2, 80.0, 80.0, 3.0, 40, 1],
            ],
            "fleets": [],
            "step": 1,
            "angular_velocity": 0.01,
            "config": {"shipSpeed": 6.0, "episodeSteps": 500.0, "cometSpeed": 4.0, "expected_c_rewards": [0.0, 0.0, 1.0, 0.0]},
            "asserts": lambda state, c_env: [
                assert_rewards_4p(state, c_env, -1, -1, 1, -1, "DONE")
            ]
        },
        {
            "name": "reward_includes_fleet_ships",
            "num_agents": 2,
            "planets": [
                [0, 0, 80.0, 80.0, 3.0, 10, 1],
                [1, 1, 20.0, 20.0, 3.0, 30, 1],
            ],
            "fleets": [
                [0, 0, 50.0, 30.0, 0.0, 0, 50],
            ],
            "step": 498,
            "angular_velocity": 0.01,
            "config": {"shipSpeed": 6.0, "episodeSteps": 500.0, "cometSpeed": 4.0, "expected_c_rewards": [1.0, 0.0]},
            "asserts": lambda state, c_env: [
                assert_rewards(state, c_env, 1, -1, "DONE")
            ]
        },
        {
            "name": "fleet_removed_when_hitting_sun",
            "num_agents": 2,
            "planets": [[0, 0, 80.0, 50.0, 3.0, 50, 1]],
            "fleets": [[0, 0, 60.0, 50.0, math.pi, 0, 10]],
            "step": 1,
            "angular_velocity": 0.01,
            "config": {"shipSpeed": 6.0, "episodeSteps": 500.0, "cometSpeed": 4.0, "expected_c_rewards": [1.0, 0.0]},
            "asserts": lambda state, c_env: [
                assert_fleet_count(state, c_env, 0)
            ]
        },
        {
            "name": "fleet_removed_when_leaving_board",
            "num_agents": 2,
            "planets": [[0, 0, 80.0, 50.0, 3.0, 50, 1]],
            "fleets": [[0, 0, 99.5, 50.0, 0.0, 0, 10]],
            "step": 1,
            "angular_velocity": 0.01,
            "config": {"shipSpeed": 6.0, "episodeSteps": 500.0, "cometSpeed": 4.0, "expected_c_rewards": [1.0, 0.0]},
            "asserts": lambda state, c_env: [
                assert_fleet_count(state, c_env, 0)
            ]
        },
        {
            "name": "fleet_survives_inside_board",
            "num_agents": 2,
            "planets": [[0, 0, 80.0, 80.0, 3.0, 50, 1]],
            "fleets": [[0, 0, 50.0, 30.0, 0.0, 0, 10]],
            "step": 1,
            "angular_velocity": 0.01,
            "config": {"shipSpeed": 6.0, "episodeSteps": 500.0, "cometSpeed": 4.0, "expected_c_rewards": [1.0, 0.0]},
            "asserts": lambda state, c_env: [
                assert_fleet_count(state, c_env, 1)
            ]
        },
        {
            "name": "fast_fleet_hits_planet_before_leaving_board",
            "num_agents": 2,
            "planets": [[0, 1, 98.0, 50.0, 2.0, 50, 1]],
            "fleets": [[0, 0, 95.0, 50.0, 0.0, 99, 1000]],
            "step": 1,
            "angular_velocity": 0.01,
            "config": {"shipSpeed": 6.0, "episodeSteps": 500.0, "cometSpeed": 4.0, "expected_c_rewards": [1.0, 0.0]},
            "asserts": lambda state, c_env: [
                assert_planet(state[0].observation, c_env, id=0, owner=0, ships=1000 - 51),
                assert_fleet_count(state, c_env, 0)
            ]
        },
        {
            "name": "fast_fleet_hits_planet_before_sun",
            "num_agents": 2,
            "planets": [[0, 1, 62.0, 50.0, 2.0, 50, 1]],
            "fleets": [[0, 0, 65.0, 50.0, math.pi, 99, 1000]],
            "step": 1,
            "angular_velocity": 0.0,
            "config": {"shipSpeed": 6.0, "episodeSteps": 500.0, "cometSpeed": 4.0, "expected_c_rewards": [1.0, 0.0]},
            "asserts": lambda state, c_env: [
                assert_planet(state[0].observation, c_env, id=0, owner=0, ships=1000 - 51),
                assert_fleet_count(state, c_env, 0)
            ]
        },
        {
            "name": "combat_simple_capture",
            "num_agents": 2,
            "planets": [[0, -1, 80.0, 50.0, 3.0, 10, 1]],
            "fleets": [[0, 0, 76.0, 50.0, 0.0, 99, 30]],
            "step": 1,
            "angular_velocity": 0.01,
            "config": {"shipSpeed": 6.0, "episodeSteps": 500.0, "cometSpeed": 4.0, "expected_c_rewards": [1.0, 0.0]},
            "asserts": lambda state, c_env: [
                assert_planet(state[0].observation, c_env, id=0, owner=0, ships=20)
            ]
        },
        {
            "name": "combat_simple_reinforce",
            "num_agents": 2,
            "planets": [[0, 0, 80.0, 50.0, 3.0, 10, 1]],
            "fleets": [[0, 0, 76.0, 50.0, 0.0, 99, 25]],
            "step": 1,
            "angular_velocity": 0.01,
            "config": {"shipSpeed": 6.0, "episodeSteps": 500.0, "cometSpeed": 4.0, "expected_c_rewards": [1.0, 0.0]},
            "asserts": lambda state, c_env: [
                assert_planet(state[0].observation, c_env, id=0, owner=0, ships=36)
            ]
        },
        {
            "name": "combat_attacker_insufficient",
            "num_agents": 2,
            "planets": [[0, -1, 80.0, 50.0, 3.0, 20, 1]],
            "fleets": [[0, 0, 76.0, 50.0, 0.0, 99, 5]],
            "step": 1,
            "angular_velocity": 0.01,
            "config": {"shipSpeed": 6.0, "episodeSteps": 500.0, "cometSpeed": 4.0, "expected_c_rewards": [0.5, 0.5]},
            "asserts": lambda state, c_env: [
                assert_planet(state[0].observation, c_env, id=0, owner=-1, ships=15)
            ]
        },
        {
            "name": "combat_two_attackers_winner_captures",
            "num_agents": 2,
            "planets": [[0, -1, 80.0, 50.0, 3.0, 10, 1]],
            "fleets": [
                [0, 0, 76.0, 50.0, 0.0, 99, 50],
                [1, 1, 76.0, 50.0, 0.0, 99, 30],
            ],
            "step": 1,
            "angular_velocity": 0.01,
            "config": {"shipSpeed": 6.0, "episodeSteps": 500.0, "cometSpeed": 4.0, "expected_c_rewards": [1.0, 0.0]},
            "asserts": lambda state, c_env: [
                assert_planet(state[0].observation, c_env, id=0, owner=0, ships=10)
            ]
        },
        {
            "name": "combat_two_attackers_tie_all_destroyed",
            "num_agents": 2,
            "planets": [[0, -1, 80.0, 50.0, 3.0, 10, 1]],
            "fleets": [
                [0, 0, 76.0, 50.0, 0.0, 99, 30],
                [1, 1, 76.0, 50.0, 0.0, 99, 30],
            ],
            "step": 1,
            "angular_velocity": 0.01,
            "config": {"shipSpeed": 6.0, "episodeSteps": 500.0, "cometSpeed": 4.0, "expected_c_rewards": [0.5, 0.5]},
            "asserts": lambda state, c_env: [
                assert_planet(state[0].observation, c_env, id=0, owner=-1, ships=10)
            ]
        },
        {
            "name": "combat_winner_reinforces_own_planet",
            "num_agents": 2,
            "planets": [[0, 0, 80.0, 50.0, 3.0, 15, 1]],
            "fleets": [
                [0, 0, 76.0, 50.0, 0.0, 99, 40],
                [1, 1, 76.0, 50.0, 0.0, 99, 25],
            ],
            "step": 1,
            "angular_velocity": 0.01,
            "config": {"shipSpeed": 6.0, "episodeSteps": 500.0, "cometSpeed": 4.0, "expected_c_rewards": [1.0, 0.0]},
            "asserts": lambda state, c_env: [
                assert_planet(state[0].observation, c_env, id=0, owner=0, ships=31)
            ]
        },
        {
            "name": "combat_winner_attacks_enemy_planet",
            "num_agents": 3,
            "planets": [[0, 1, 80.0, 50.0, 3.0, 5, 1]],
            "fleets": [
                [0, 0, 76.0, 50.0, 0.0, 99, 50],
                [1, 2, 76.0, 50.0, 0.0, 99, 20],
            ],
            "step": 1,
            "angular_velocity": 0.01,
            "config": {"shipSpeed": 6.0, "episodeSteps": 500.0, "cometSpeed": 4.0, "expected_c_rewards": [1.0, 0.0, 0.0]},
            "asserts": lambda state, c_env: [
                assert_planet(state[0].observation, c_env, id=0, owner=0, ships=24)
            ]
        },
        {
            "name": "combat_multiple_fleets_same_owner",
            "num_agents": 2,
            "planets": [[0, -1, 80.0, 50.0, 3.0, 10, 1]],
            "fleets": [
                [0, 0, 76.0, 50.0, 0.0, 99, 20],
                [1, 0, 76.0, 50.0, 0.0, 99, 15],
            ],
            "step": 1,
            "angular_velocity": 0.01,
            "config": {"shipSpeed": 6.0, "episodeSteps": 500.0, "cometSpeed": 4.0, "expected_c_rewards": [1.0, 0.0]},
            "asserts": lambda state, c_env: [
                assert_planet(state[0].observation, c_env, id=0, owner=0, ships=25)
            ]
        }
    ]

    for sc in scenarios:
        name = sc["name"]
        print(f"  - Testing scenario: {name} ...")
        
        # 1. Run single step check
        py_state, c_env = run_parity_step_for_scenario(
            lib, 
            sc["planets"], 
            sc["fleets"], 
            num_agents=sc["num_agents"],
            step=sc["step"],
            angular_velocity=sc["angular_velocity"],
            config=sc.get("config")
        )
        
        # Execute scenario specific assertions
        sc["asserts"](py_state, c_env)
        
        # 2. Run a 5-step rollout from this mock state (if not already completed/DONE)
        if py_state[0].status == "ACTIVE":
            env = SimpleNamespace(
                configuration=SimpleNamespace(
                    shipSpeed=sc.get("config", {}).get("shipSpeed", 6.0),
                    episodeSteps=sc.get("config", {}).get("episodeSteps", 500.0),
                    cometSpeed=sc.get("config", {}).get("cometSpeed", 4.0)
                ),
                done=False,
            )
            for r_step in range(1, 6):
                # Apply simple actions (e.g. launch half-ships from owned planets)
                actions = []
                for p in range(sc["num_agents"]):
                    agent_obs = py_state[p].observation
                    moves = []
                    for planet in agent_obs.planets:
                        if planet[1] == p and planet[5] > 10:
                            # launch towards center
                            angle = (r_step * 0.17 + p * 0.5) % (2.0 * math.pi)
                            ships = planet[5] // 2
                            moves.append([planet[0], angle, ships])
                    actions.append(moves[:OW_MAX_ACTIONS_PER_PLAYER])
                
                # Apply to C raw actions
                for p in range(sc["num_agents"]):
                    py_state[p].action = actions[p]
                    c_env.num_raw_actions[p] = len(actions[p])
                    for idx, move in enumerate(actions[p]):
                        c_env.raw_actions[p][idx].from_planet_id = move[0]
                        c_env.raw_actions[p][idx].angle = move[1]
                        c_env.raw_actions[p][idx].ships = move[2]
                
                # Step both
                py_state = interpreter(py_state, env)
                next_step = getattr(py_state[0].observation, "step", 0) + 1
                for agent_state in py_state:
                    agent_state.observation.step = next_step
                lib.c_step_core(ctypes.byref(c_env))
                
                # Verify parity
                assert_state_parity(sc["step"] + r_step, py_state[0].observation, c_env)
                
                # Verify rewards and status
                for p in range(sc["num_agents"]):
                    py_reward = py_state[p].reward
                    py_status = py_state[p].status
                    
                    slot = -1
                    for s in range(c_env.num_agents):
                        if c_env.slot_for_color[s] == p:
                            slot = s
                            break
                    if slot == -1:
                        slot = p
                        
                    c_reward = ctypes.c_float.from_address(c_env.reward_ptr[slot]).value
                    c_terminal = ctypes.c_float.from_address(c_env.terminal_ptr[slot]).value
                    
                    expected_c_rewards = sc.get("config", {}).get("expected_c_rewards")
                    if expected_c_rewards is not None:
                        expected_c = expected_c_rewards[p]
                    else:
                        if py_reward == 1:
                            expected_c = 1.0
                        elif py_reward == -1:
                            expected_c = 0.0
                        else:
                            expected_c = 0.0
                        
                    assert math.isclose(c_reward, expected_c, abs_tol=1e-5), (
                        f"Rollout step {r_step} Reward mismatch for agent {p}: expected {expected_c}, got C={c_reward} (Py={py_reward})"
                    )
                    expected_terminal = 1.0 if py_status == "DONE" else 0.0
                    assert math.isclose(c_terminal, expected_terminal, abs_tol=1e-5), (
                        f"Rollout step {r_step} Terminal mismatch for agent {p}: Py_status={py_status}, C_terminal={c_terminal}"
                    )
                
                if py_state[0].status == "DONE":
                    break

    print("  ✓ All custom scenario parity tests passed.")


def run_interpreter_rollout_parity(lib, py_state, c_env, num_agents, ship_speed=6.0, episode_steps=500.0, comet_speed=4.0):
    from types import SimpleNamespace
    from kaggle_environments.envs.orbit_wars.orbit_wars import interpreter
    
    env = SimpleNamespace(
        configuration=SimpleNamespace(
            shipSpeed=ship_speed,
            episodeSteps=episode_steps,
            cometSpeed=comet_speed
        ),
        done=False,
    )
    
    for r_step in range(1, 6):
        # Generate actions
        actions = []
        for p in range(num_agents):
            agent_obs = py_state[p].observation
            moves = []
            for planet in agent_obs.planets:
                if planet[1] == p and planet[5] > 10:
                    angle = (r_step * 0.17 + p * 0.5) % (2.0 * math.pi)
                    ships = planet[5] // 2
                    moves.append([planet[0], angle, ships])
            actions.append(moves[:OW_MAX_ACTIONS_PER_PLAYER])
            
        # Inject into Python
        for p in range(num_agents):
            py_state[p].action = actions[p]
            
        # Inject into C
        for p in range(num_agents):
            c_env.num_raw_actions[p] = len(actions[p])
            for idx, move in enumerate(actions[p]):
                c_env.raw_actions[p][idx].from_planet_id = move[0]
                c_env.raw_actions[p][idx].angle = move[1]
                c_env.raw_actions[p][idx].ships = move[2]
                
        # Step Python
        py_state = interpreter(py_state, env)
        next_step = getattr(py_state[0].observation, "step", 0) + 1
        for agent_state in py_state:
            agent_state.observation.step = next_step
            
        # Step C
        lib.c_step_core(ctypes.byref(c_env))
        
        # Verify state parity
        assert_state_parity(next_step, py_state[0].observation, c_env)


def test_symmetry_parity(lib, seed):
    print(f"Running symmetry parity test on seed {seed} ...")
    kaggle_env = make("orbit_wars", configuration={"seed": seed, "episodeSteps": 500})
    state = kaggle_env.reset()
    obs = state[0].observation
    
    # Check Python symmetry
    planets = obs.planets
    assert len(planets) >= 4, f"Expected >= 4 planets, got {len(planets)}"
    assert len(planets) % 4 == 0, f"Expected planets count to be multiple of 4, got {len(planets)}"
    for i in range(0, len(planets), 4):
        p0 = planets[i]
        p3 = planets[i + 3]
        assert math.isclose(p0[2] + p3[2], 100.0, abs_tol=1e-5), f"Symmetry X mismatch: {p0[2]} and {p3[2]}"
        assert math.isclose(p0[3] + p3[3], 100.0, abs_tol=1e-5), f"Symmetry Y mismatch: {p0[3]} and {p3[3]}"
        assert p0[4] == p3[4], f"Radius mismatch: {p0[4]} and {p3[4]}"

    # Setup C
    c_env = OrbitWarsStruct()
    ctypes.memset(ctypes.byref(c_env), 0, ctypes.sizeof(c_env))
    lib.init(ctypes.byref(c_env))
    
    obs_buf = (ctypes.c_float * (OW_OBS_SIZE * 4))()
    action_buf = (ctypes.c_float * (3 * 4))()
    reward_buf = (ctypes.c_float * 4)()
    terminal_buf = (ctypes.c_float * 4)()
    for i in range(4):
        c_env.obs_ptr[i] = ctypes.addressof(obs_buf) + i * OW_OBS_SIZE * 4
        c_env.action_ptr[i] = ctypes.addressof(action_buf) + i * 3 * 4
        c_env.reward_ptr[i] = ctypes.addressof(reward_buf) + i * 4
        c_env.terminal_ptr[i] = ctypes.addressof(terminal_buf) + i * 4

    copy_state_py_to_c(obs, c_env, num_agents=2)

    # Check C symmetry
    assert c_env.num_planets == len(planets)
    for i in range(0, c_env.num_planets, 4):
        cp0 = c_env.planets[i]
        cp3 = c_env.planets[i + 3]
        assert math.isclose(cp0.x + cp3.x, 100.0, abs_tol=1e-5)
        assert math.isclose(cp0.y + cp3.y, 100.0, abs_tol=1e-5)
        assert cp0.radius == cp3.radius

    # Parity check at step 0
    assert_state_parity(0, obs, c_env)

    # Rollout check
    # Wrap in list so it behaves like py_state in run_interpreter_rollout_parity
    from types import SimpleNamespace
    py_state = [
        SimpleNamespace(observation=obs, action=[], status="ACTIVE", reward=0),
        SimpleNamespace(observation=state[1].observation, action=[], status="ACTIVE", reward=0)
    ]
    run_interpreter_rollout_parity(lib, py_state, c_env, num_agents=2, ship_speed=6.0)
    print(f"  ✓ Symmetry parity passed on seed {seed}.")


def test_4_player_initialization_parity(lib, seed):
    print(f"Running 4-player initialization parity test on seed {seed} ...")
    from types import SimpleNamespace
    from kaggle_environments.envs.orbit_wars.orbit_wars import interpreter
    
    state = [
        SimpleNamespace(
            observation=SimpleNamespace(step=0),
            action=[],
            status="ACTIVE",
            reward=0,
        )
    ]
    for i in range(1, 4):
        state.append(
            SimpleNamespace(
                observation=SimpleNamespace(player=i),
                action=[],
                status="ACTIVE",
                reward=0,
            )
        )
        
    env = SimpleNamespace(
        configuration=SimpleNamespace(shipSpeed=6.0, episodeSteps=500.0, cometSpeed=4.0, seed=seed),
        done=False,
    )
    
    py_state = interpreter(state, env)
    for agent_state in py_state:
        agent_state.observation.step = 1
    obs = py_state[0].observation
    planets = obs.planets
    
    # Assert Python ownership
    owned = [p for p in planets if p[1] != -1]
    assert len(owned) == 4, f"Expected 4 owned home planets, got {len(owned)}"
    owners = set(p[1] for p in owned)
    assert owners == {0, 1, 2, 3}, f"Expected owners {0,1,2,3}, got {owners}"
    
    # Setup C
    c_env = OrbitWarsStruct()
    ctypes.memset(ctypes.byref(c_env), 0, ctypes.sizeof(c_env))
    lib.init(ctypes.byref(c_env))
    
    obs_buf = (ctypes.c_float * (OW_OBS_SIZE * 4))()
    action_buf = (ctypes.c_float * (3 * 4))()
    reward_buf = (ctypes.c_float * 4)()
    terminal_buf = (ctypes.c_float * 4)()
    for i in range(4):
        c_env.obs_ptr[i] = ctypes.addressof(obs_buf) + i * OW_OBS_SIZE * 4
        c_env.action_ptr[i] = ctypes.addressof(action_buf) + i * 3 * 4
        c_env.reward_ptr[i] = ctypes.addressof(reward_buf) + i * 4
        c_env.terminal_ptr[i] = ctypes.addressof(terminal_buf) + i * 4

    copy_state_py_to_c(obs, c_env, num_agents=4)
    c_env.max_steps = 500 - 2
    c_env.prevent_reset = 1
    
    # Assert C ownership
    c_owned = [c_env.planets[i] for i in range(c_env.num_planets) if c_env.planets[i].owner != -1]
    assert len(c_owned) == 4
    c_owners = set(cp.owner for cp in c_owned)
    assert c_owners == {0, 1, 2, 3}
    
    # Parity check
    assert_state_parity(1, obs, c_env)
    
    # Rollout check
    run_interpreter_rollout_parity(lib, py_state, c_env, num_agents=4, ship_speed=6.0)
    print(f"  ✓ 4-player initialization parity passed on seed {seed}.")


def test_4p_home_planets_rotationally_symmetric_parity(lib, seed):
    print(f"Running 4p home planets rotational symmetry parity test on seed {seed} ...")
    from types import SimpleNamespace
    from kaggle_environments.envs.orbit_wars.orbit_wars import interpreter
    
    state = [
        SimpleNamespace(
            observation=SimpleNamespace(step=0),
            action=[],
            status="ACTIVE",
            reward=0,
        )
    ]
    for i in range(1, 4):
        state.append(
            SimpleNamespace(
                observation=SimpleNamespace(player=i),
                action=[],
                status="ACTIVE",
                reward=0,
            )
        )
        
    env = SimpleNamespace(
        configuration=SimpleNamespace(shipSpeed=6.0, episodeSteps=500.0, cometSpeed=4.0, seed=seed),
        done=False,
    )
    
    py_state = interpreter(state, env)
    for agent_state in py_state:
        agent_state.observation.step = 1
    obs = py_state[0].observation
    planets = obs.planets
    
    # Assert Python rotational symmetry
    owned = [p for p in planets if p[1] != -1]
    assert len(owned) == 4
    positions = [(p[2], p[3]) for p in owned]
    for x, y in positions:
        rx = 50.0 - (y - 50.0)
        ry = 50.0 + (x - 50.0)
        assert any(math.isclose(rx, px, abs_tol=1e-5) and math.isclose(ry, py, abs_tol=1e-5) for px, py in positions), \
            f"Home planets set not 4-fold rotationally symmetric: {positions}"
            
    # Setup C
    c_env = OrbitWarsStruct()
    ctypes.memset(ctypes.byref(c_env), 0, ctypes.sizeof(c_env))
    lib.init(ctypes.byref(c_env))
    
    obs_buf = (ctypes.c_float * (OW_OBS_SIZE * 4))()
    action_buf = (ctypes.c_float * (3 * 4))()
    reward_buf = (ctypes.c_float * 4)()
    terminal_buf = (ctypes.c_float * 4)()
    for i in range(4):
        c_env.obs_ptr[i] = ctypes.addressof(obs_buf) + i * OW_OBS_SIZE * 4
        c_env.action_ptr[i] = ctypes.addressof(action_buf) + i * 3 * 4
        c_env.reward_ptr[i] = ctypes.addressof(reward_buf) + i * 4
        c_env.terminal_ptr[i] = ctypes.addressof(terminal_buf) + i * 4

    copy_state_py_to_c(obs, c_env, num_agents=4)
    c_env.max_steps = 500 - 2
    c_env.prevent_reset = 1
    
    # Assert C rotational symmetry
    c_owned = [c_env.planets[i] for i in range(c_env.num_planets) if c_env.planets[i].owner != -1]
    assert len(c_owned) == 4
    c_positions = [(cp.x, cp.y) for cp in c_owned]
    for x, y in c_positions:
        rx = 50.0 - (y - 50.0)
        ry = 50.0 + (x - 50.0)
        assert any(math.isclose(rx, px, abs_tol=1e-5) and math.isclose(ry, py, abs_tol=1e-5) for px, py in c_positions)
        
    # Parity check
    assert_state_parity(1, obs, c_env)
    
    # Rollout check
    run_interpreter_rollout_parity(lib, py_state, c_env, num_agents=4, ship_speed=6.0)
    print(f"  ✓ 4p home planets rotational symmetry parity passed on seed {seed}.")


def test_comet_spawn_keeps_initial_planets_synced_parity(lib, seed):
    print(f"Running comet spawn sync parity test on seed {seed} ...")
    from types import SimpleNamespace
    from kaggle_environments.envs.orbit_wars.orbit_wars import interpreter
    
    import random
    random.seed(seed)
    
    state = [
        SimpleNamespace(
            observation=SimpleNamespace(step=0),
            action=[],
            status="ACTIVE",
            reward=0,
        )
    ]
    for i in range(1, 4):
        state.append(
            SimpleNamespace(
                observation=SimpleNamespace(player=i),
                action=[],
                status="ACTIVE",
                reward=0,
            )
        )
        
    env = SimpleNamespace(
        configuration=SimpleNamespace(shipSpeed=6.0, episodeSteps=120.0, cometSpeed=4.0, seed=seed),
        done=False,
    )
    
    py_state = interpreter(state, env)
    for agent_state in py_state:
        agent_state.observation.step = 1
        
    # Setup C
    c_env = OrbitWarsStruct()
    ctypes.memset(ctypes.byref(c_env), 0, ctypes.sizeof(c_env))
    lib.init(ctypes.byref(c_env))
    
    obs_buf = (ctypes.c_float * (OW_OBS_SIZE * 4))()
    action_buf = (ctypes.c_float * (3 * 4))()
    reward_buf = (ctypes.c_float * 4)()
    terminal_buf = (ctypes.c_float * 4)()
    for i in range(4):
        c_env.obs_ptr[i] = ctypes.addressof(obs_buf) + i * OW_OBS_SIZE * 4
        c_env.action_ptr[i] = ctypes.addressof(action_buf) + i * 3 * 4
        c_env.reward_ptr[i] = ctypes.addressof(reward_buf) + i * 4
        c_env.terminal_ptr[i] = ctypes.addressof(terminal_buf) + i * 4

    copy_state_py_to_c(py_state[0].observation, c_env, num_agents=4)
    c_env.max_steps = 120 - 2
    c_env.prevent_reset = 1
    
    for r_step in range(1, 50):
        py_state = interpreter(py_state, env)
        next_step = getattr(py_state[0].observation, "step", 0) + 1
        for agent_state in py_state:
            agent_state.observation.step = next_step
            
        lib.c_step_core(ctypes.byref(c_env))
        
        if next_step in COMET_SPAWN_STEPS:
            copy_comets_py_to_c(py_state[0].observation, c_env)
            lib.test_compute_observations(ctypes.byref(c_env))
            
        assert_state_parity(next_step, py_state[0].observation, c_env)
        
    obs0 = py_state[0].observation
    
    # Assert Python comet sync
    assert obs0.comets, "Expected comets to have spawned by step 50"
    assert len(obs0.initial_planets) == len(obs0.planets)
    for other_state in py_state[1:]:
        other_obs = other_state.observation
        assert obs0.comet_planet_ids == other_obs.comet_planet_ids
        assert obs0.initial_planets == other_obs.initial_planets
        
    # Assert C comet sync
    c_comets_count = sum(1 for cp in c_env.planets if cp.active and cp.is_comet)
    assert c_comets_count > 0, "C comets count should be > 0"
    assert c_env.num_planets == len(obs0.planets)
    
    # Rollout check
    run_interpreter_rollout_parity(lib, py_state, c_env, num_agents=4, ship_speed=6.0)
    print(f"  ✓ Comet spawn sync parity passed on seed {seed}.")


# ------------------------------------------------------------------ #
# Main Entry Point
# ------------------------------------------------------------------ #

def main():
    print("=" * 60)
    print("ORBIT WARS — Physics & Observation Parity Test Suite")
    print("=" * 60)
    
    # 1. Compile test library
    print("Compiling test library...")
    lib = compile_and_load()
    print("Test library loaded successfully.")
    
    # 2. Sanity size check
    c_size = lib.get_sizeof_orbit_wars()
    py_size = ctypes.sizeof(OrbitWarsStruct)
    print(f"Structure size: C={c_size} bytes, Python={py_size} bytes")
    assert c_size == py_size, (
        f"Structure size mismatch! C: {c_size}, Python: {py_size}. "
        "Check ctypes struct fields alignment/order."
    )
    print("✓ Structure size match check passed.")
    
    # 3. Run custom scenarios parity tests
    try:
        test_custom_scenarios_parity(lib)
    except AssertionError as e:
        print(f"✗ Custom scenario parity failed: {e}")
        import traceback; traceback.print_exc()
        sys.exit(1)

    # 4. Run single-step parity tests (1v1 mode)
    for seed in [42, 101, 102, 103]:
        try:
            test_parity_single_step(lib, seed, num_agents=2)
        except AssertionError as e:
            print(f"✗ Single-step parity failed for seed {seed}: {e}")
            sys.exit(1)
            
    # 5. Run rollout parity tests (1v1 mode)
    for seed in [42, 101, 102]:
        try:
            test_parity_rollout(lib, seed, num_agents=2)
        except AssertionError as e:
            print(f"✗ Rollout parity failed for seed {seed}: {e}")
            sys.exit(1)
            
    # 6. Run new symmetry, 4-player initialization, and comet spawn parity tests
    for seed in [0, 42, 101]:
        try:
            test_symmetry_parity(lib, seed)
            test_4_player_initialization_parity(lib, seed)
            test_4p_home_planets_rotationally_symmetric_parity(lib, seed)
            test_comet_spawn_keeps_initial_planets_synced_parity(lib, seed)
        except AssertionError as e:
            print(f"✗ New parity test failed for seed {seed}: {e}")
            import traceback; traceback.print_exc()
            sys.exit(1)
            
    print("\n" + "=" * 60)
    print("✅ ALL PARITY TESTS PASSED")
    print("=" * 60)

if __name__ == "__main__":
    main()
