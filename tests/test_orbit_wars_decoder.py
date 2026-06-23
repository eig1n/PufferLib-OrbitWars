#!/usr/bin/env python3
import ctypes
import math

import numpy as np

from tests.test_orbit_wars_parity import (
    OW_MAX_COMET_GROUPS,
    OW_MAX_FLEETS,
    OW_MAX_PLANETS,
    OrbitWarsStruct,
    compile_and_load,
)


def make_env(lib, planets, num_agents=2):
    env = OrbitWarsStruct()
    lib.init(ctypes.byref(env))
    env.num_agents = num_agents
    env.max_steps = 500
    env.current_step = 0
    env.num_comet_groups = 0
    for i in range(num_agents):
        env.slot_for_color[i] = i
    for i in range(OW_MAX_PLANETS):
        env.planets[i].active = 0
        env.planet_orbits[i] = 0
    for i in range(OW_MAX_FLEETS):
        env.fleets[i].active = 0
    for i in range(OW_MAX_COMET_GROUPS):
        env.comet_groups[i].active = 0
    env.num_planets = len(planets)
    for i, row in enumerate(planets):
        pid, owner, x, y, ships, prod = row
        env.planets[i].id = pid
        env.planets[i].owner = owner
        env.planets[i].x = x
        env.planets[i].y = y
        env.planets[i].radius = 1.0 + math.log(max(prod, 1))
        env.planets[i].ships = ships
        env.planets[i].production = prod
        env.planets[i].active = 1
        env.planet_angle[i] = math.atan2(y - 50.0, x - 50.0)
        env.planet_orbital_radius[i] = math.hypot(x - 50.0, y - 50.0)
        env.planet_orbits[i] = 0
    return env


def configure(lib):
    lib.test_interval_pair_strength.argtypes = [
        ctypes.c_float,
        ctypes.c_float,
        ctypes.c_float,
        ctypes.c_float,
    ]
    lib.test_interval_pair_strength.restype = ctypes.c_float
    lib.test_planet_slots_by_id.argtypes = [
        ctypes.POINTER(OrbitWarsStruct),
        ctypes.POINTER(ctypes.c_int),
    ]
    lib.test_planet_slots_by_id.restype = None
    lib.test_decode_interval_actions_for_slot.argtypes = [
        ctypes.POINTER(OrbitWarsStruct),
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_float),
    ]
    lib.test_decode_interval_actions_for_slot.restype = ctypes.c_int
    lib.test_aim_angle_to_planet.argtypes = [
        ctypes.POINTER(OrbitWarsStruct),
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_double),
    ]
    lib.test_aim_angle_to_planet.restype = ctypes.c_int
    lib.test_validate_launch_angle.argtypes = [
        ctypes.POINTER(OrbitWarsStruct),
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_double,
    ]
    lib.test_validate_launch_angle.restype = ctypes.c_int


def decode(lib, env, pairs):
    actions = np.zeros(OW_MAX_PLANETS * 2, dtype=np.float32)
    for slot, x, r in pairs:
        actions[2 * slot] = x
        actions[2 * slot + 1] = r
    launches = lib.test_decode_interval_actions_for_slot(
        ctypes.byref(env),
        0,
        actions.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
    )
    return launches


def raw_actions(env, player=0):
    return [env.raw_actions[player][i] for i in range(env.num_raw_actions[player])]


def aim(lib, env, src_idx, tgt_idx, ships):
    out = ctypes.c_double()
    ok = lib.test_aim_angle_to_planet(ctypes.byref(env), src_idx, tgt_idx, ships, ctypes.byref(out))
    return ok, out.value


def set_orbiting(env, idx, angular_velocity=0.05):
    pl = env.planets[idx]
    env.angular_velocity = angular_velocity
    env.planet_orbits[idx] = 1
    env.planet_orbital_radius[idx] = math.hypot(pl.x - 50.0, pl.y - 50.0)
    env.planet_angle[idx] = math.atan2(pl.y - 50.0, pl.x - 50.0) + angular_velocity


def set_comet_path(env, idx, points):
    pl = env.planets[idx]
    pl.is_comet = 1
    pl.radius = 1.0
    pl.x, pl.y = points[0]
    env.planet_orbits[idx] = 0
    env.num_comet_groups = 1
    cg = env.comet_groups[0]
    cg.active = 1
    cg.path_index = 0
    cg.num_steps = len(points)
    for m in range(4):
        cg.planet_ids[m] = -100 - m
    cg.planet_ids[0] = pl.id
    for k, (x, y) in enumerate(points):
        cg.paths_x[0][k] = x
        cg.paths_y[0][k] = y


def test_slot_ordering_is_ascending_planet_id():
    lib = compile_and_load()
    configure(lib)
    env = make_env(lib, [(9, 0, 10, 10, 20, 1), (2, -1, 20, 20, 5, 1), (7, 1, 30, 30, 5, 1)])
    out = (ctypes.c_int * OW_MAX_PLANETS)()
    lib.test_planet_slots_by_id(ctypes.byref(env), out)
    assert [env.planets[out[i]].id for i in range(3)] == [2, 7, 9]


def test_interval_overlap_rewards_tight_matches():
    lib = compile_and_load()
    configure(lib)
    tight = lib.test_interval_pair_strength(0.0, 0.1, 0.05, -0.1)
    broad = lib.test_interval_pair_strength(0.0, 0.8, 0.05, -0.8)
    miss = lib.test_interval_pair_strength(-0.9, 0.1, 0.9, -0.1)
    assert tight > broad
    assert miss == 0.0


def test_source_sink_signs_and_noops():
    lib = compile_and_load()
    configure(lib)
    env = make_env(lib, [(0, 0, 20, 20, 20, 1), (1, -1, 80, 20, 5, 1)])
    assert decode(lib, env, [(0, 0.0, 0.5), (1, 0.0, 0.5)]) == 0
    assert env.num_raw_actions[0] == 0
    assert decode(lib, env, [(0, 0.0, 0.5), (1, 0.0, -0.5)]) == 1
    assert raw_actions(env)[0].from_planet_id == 0


def test_multi_source_capture_and_ship_clamping():
    lib = compile_and_load()
    configure(lib)
    env = make_env(
        lib,
        [
            (0, 0, 20, 20, 8, 1),
            (1, 0, 20, 30, 50, 1),
            (2, 1, 80, 20, 30, 1),
        ],
    )
    launches = decode(lib, env, [(0, 0.0, 0.4), (1, 0.0, 0.4), (2, 0.0, -0.4)])
    acts = raw_actions(env)
    assert launches == 2
    assert {a.from_planet_id for a in acts} == {0, 1}
    assert sum(a.ships for a in acts) >= 31
    assert next(a.ships for a in acts if a.from_planet_id == 0) <= 7


def test_owned_sink_reinforcement():
    lib = compile_and_load()
    configure(lib)
    env = make_env(lib, [(0, 0, 20, 20, 30, 1), (1, 0, 80, 20, 2, 3)])
    launches = decode(lib, env, [(0, 0.2, 0.5), (1, 0.2, -0.5)])
    acts = raw_actions(env)
    assert launches == 1
    assert acts[0].from_planet_id == 0
    assert acts[0].ships > 0


def test_validated_static_aim_hits_direct_target():
    lib = compile_and_load()
    configure(lib)
    env = make_env(lib, [(0, 0, 20, 20, 40, 1), (1, -1, 80, 20, 5, 1)])
    ok, angle = aim(lib, env, 0, 1, 10)
    assert ok == 1
    assert abs(angle) < 1e-4
    assert lib.test_validate_launch_angle(ctypes.byref(env), 0, 1, 10, angle) == 1


def test_blocker_rejection_and_no_launch_fallback():
    lib = compile_and_load()
    configure(lib)
    env = make_env(
        lib,
        [
            (0, 0, 20, 20, 40, 1),
            (1, -1, 50, 20, 5, 3),
            (2, -1, 80, 20, 5, 1),
        ],
    )
    ok, _ = aim(lib, env, 0, 2, 10)
    assert ok == 0
    assert decode(lib, env, [(0, 0.0, 0.5), (2, 0.0, -0.5)]) == 0
    assert env.num_raw_actions[0] == 0


def test_orbiting_target_intercept_is_validated():
    lib = compile_and_load()
    configure(lib)
    env = make_env(lib, [(0, 0, 20, 20, 80, 1), (1, -1, 80, 50, 5, 1)])
    set_orbiting(env, 1, angular_velocity=0.05)
    ok, angle = aim(lib, env, 0, 1, 20)
    direct = math.atan2(env.planets[1].y - env.planets[0].y, env.planets[1].x - env.planets[0].x)
    assert ok == 1
    assert abs(angle - direct) > 1e-3
    assert lib.test_validate_launch_angle(ctypes.byref(env), 0, 1, 20, angle) == 1


def test_comet_path_indexed_aim_is_validated():
    lib = compile_and_load()
    configure(lib)
    env = make_env(lib, [(0, 0, 20, 90, 100, 1), (1, -1, 80, 20, 5, 1)])
    points = [(80.0, 20.0 + 0.8 * k) for k in range(90)]
    set_comet_path(env, 1, points)
    ok, angle = aim(lib, env, 0, 1, 40)
    direct = math.atan2(env.planets[1].y - env.planets[0].y, env.planets[1].x - env.planets[0].x)
    assert ok == 1
    assert abs(angle - direct) > 1e-3
    assert lib.test_validate_launch_angle(ctypes.byref(env), 0, 1, 40, angle) == 1
