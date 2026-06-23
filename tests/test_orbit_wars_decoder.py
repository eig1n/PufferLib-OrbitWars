#!/usr/bin/env python3
import ctypes
import math

import numpy as np

from tests.test_orbit_wars_parity import (
    OW_MAX_PLANETS,
    OrbitWarsStruct,
    compile_and_load,
)


def make_env(lib, planets, num_agents=2):
    env = OrbitWarsStruct()
    lib.init(ctypes.byref(env))
    env.num_agents = num_agents
    env.max_steps = 500
    for i in range(num_agents):
        env.slot_for_color[i] = i
    for i in range(OW_MAX_PLANETS):
        env.planets[i].active = 0
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
    env = make_env(lib, [(0, 0, 20, 50, 20, 1), (1, -1, 80, 50, 5, 1)])
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
            (0, 0, 20, 50, 8, 1),
            (1, 0, 20, 60, 50, 1),
            (2, 1, 80, 50, 30, 1),
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
    env = make_env(lib, [(0, 0, 20, 50, 30, 1), (1, 0, 80, 50, 2, 3)])
    launches = decode(lib, env, [(0, 0.2, 0.5), (1, 0.2, -0.5)])
    acts = raw_actions(env)
    assert launches == 1
    assert acts[0].from_planet_id == 0
    assert acts[0].ships > 0
