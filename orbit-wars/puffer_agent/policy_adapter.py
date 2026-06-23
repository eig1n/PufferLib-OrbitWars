"""Adapter for running Puffer-trained Orbit Wars policies in Kaggle Python.

This module mirrors the production C environment interface:
- Kaggle observation dict -> compact 872-float policy observation.
- 96-float policy action vector -> Kaggle move list.

The current action vector uses the interval abstraction from the C decoder
(`x, r` per canonical planet slot), but this file is named for its role rather
than that implementation detail.
"""

from __future__ import annotations

import math
from typing import Any, Iterable

MAX_PLANETS = 48
PLANET_FEATS = 18
GLOBAL_FEATS = 8
OBS_SIZE = MAX_PLANETS * PLANET_FEATS + GLOBAL_FEATS
NUM_ATNS = MAX_PLANETS * 2
BOARD_SIZE = 100.0
CENTER = 50.0
ROTATION_RADIUS_LIMIT = 50.0
MAX_STEPS = 500
MAX_SPEED = 6.0
INTERVAL_EPS = 1.0 / 32.0
MAX_TARGETS = 6
MAX_SOURCES_PER_TARGET = 3
MAX_LAUNCHES = 16


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def _fleet_speed(ships: int) -> float:
    if ships <= 1:
        return 1.0
    ratio = min(math.log(float(ships)) / math.log(1000.0), 1.0)
    return 1.0 + (MAX_SPEED - 1.0) * (ratio ** 1.5)


def _player_count(planets: Iterable[list[Any]], fleets: Iterable[list[Any]], player_id: int) -> int:
    owners = [int(player_id)]
    owners.extend(int(p[1]) for p in planets if len(p) >= 2 and int(p[1]) >= 0)
    owners.extend(int(f[1]) for f in fleets if len(f) >= 2 and int(f[1]) >= 0)
    return 4 if max(owners, default=0) >= 2 else 2


def _planet_slots(obs: dict[str, Any]) -> list[list[Any]]:
    planets = [list(p[:7]) for p in obs.get("planets", []) if len(p) >= 7]
    planets.sort(key=lambda p: int(p[0]))
    return planets[:MAX_PLANETS]


def _interval_strength(xs: float, rs: float, xt: float, rt: float) -> float:
    ars = abs(rs)
    art = abs(rt)
    overlap = ars + art - abs(xs - xt)
    if overlap <= 0.0:
        return 0.0
    denom = ars + art
    if denom < 1e-6:
        return 0.0
    broadness = _clamp((ars + art) * 0.5, 0.0, 1.0)
    return _clamp((overlap / denom) / (0.25 + broadness), 0.0, 1.0)


def compact_features(obs: dict[str, Any], player_id: int) -> list[float]:
    """Build the 872-float production observation used by the C env."""
    planets = _planet_slots(obs)
    fleets = [list(f[:7]) for f in obs.get("fleets", []) if len(f) >= 7]
    comet_ids = {int(pid) for pid in obs.get("comet_planet_ids", [])}
    num_agents = _player_count(planets, fleets, player_id)
    step = int(obs.get("step", 0))
    angular_velocity = float(obs.get("angular_velocity", 0.03))
    max_steps = int(obs.get("episode_steps", MAX_STEPS))

    features = [0.0] * OBS_SIZE
    own_pressure = [0.0] * len(planets)
    enemy_pressure = [0.0] * len(planets)
    earliest_eta = [MAX_STEPS + 1] * len(planets)
    earliest_owner = [-1] * len(planets)
    own_ships = enemy_ships = own_prod = enemy_prod = 0

    for p in planets:
        owner = int(p[1])
        ships = int(p[5])
        prod = int(p[6])
        if owner == player_id:
            own_ships += ships
            own_prod += prod
        elif owner >= 0:
            enemy_ships += ships
            enemy_prod += prod

    for f in fleets:
        owner = int(f[1])
        ships = int(f[6])
        if owner == player_id:
            own_ships += ships
        elif owner >= 0:
            enemy_ships += ships

        fx, fy, angle = float(f[2]), float(f[3]), float(f[4])
        speed = _fleet_speed(ships)
        vx = math.cos(angle) * speed
        vy = math.sin(angle) * speed
        best_i = -1
        best_t = float(MAX_STEPS + 1)
        for i, p in enumerate(planets):
            px, py, radius = float(p[2]), float(p[3]), float(p[4])
            if px < 0.0:
                continue
            rx = fx - px
            ry = fy - py
            acoef = vx * vx + vy * vy
            bcoef = 2.0 * (rx * vx + ry * vy)
            ccoef = rx * rx + ry * ry - radius * radius
            disc = bcoef * bcoef - 4.0 * acoef * ccoef
            if disc < 0.0 or acoef < 1e-6:
                continue
            sq = math.sqrt(disc)
            t = (-bcoef - sq) / (2.0 * acoef)
            if t < 0.0:
                t = (-bcoef + sq) / (2.0 * acoef)
            if 0.0 <= t < best_t:
                best_t = t
                best_i = i
        if best_i >= 0 and best_t <= max_steps - step:
            if owner == player_id:
                own_pressure[best_i] += ships
            else:
                enemy_pressure[best_i] += ships
            eta = int(math.ceil(best_t))
            if eta < earliest_eta[best_i]:
                earliest_eta[best_i] = eta
                earliest_owner[best_i] = owner

    for i, p in enumerate(planets):
        idx = i * PLANET_FEATS
        pid, owner, x, y, _radius, ships, prod = p
        owner = int(owner)
        x = float(x)
        y = float(y)
        ships = int(ships)
        prod = int(prod)
        dx = x - CENTER
        dy = y - CENTER
        orbital_r = math.hypot(dx, dy)
        theta = math.atan2(dy, dx)
        eta = min(earliest_eta[i], MAX_STEPS)
        projected = float(ships + (prod * eta if owner >= 0 else 0))
        net_own = (projected if owner == player_id else 0.0) + own_pressure[i]
        net_enemy = (projected if owner >= 0 and owner != player_id else 0.0) + enemy_pressure[i]
        projected_owner = 0.0
        projected_garrison = projected
        if net_own > net_enemy and (owner == player_id or own_pressure[i] > 0.0):
            projected_owner = 1.0
            projected_garrison = net_own - net_enemy
        elif net_enemy > net_own and ((owner >= 0 and owner != player_id) or enemy_pressure[i] > 0.0):
            projected_owner = -1.0
            projected_garrison = net_enemy - net_own
        if owner == player_id:
            need = max(0.0, enemy_pressure[i] - projected + 1.0)
        else:
            need = max(0.0, projected + enemy_pressure[i] - own_pressure[i] + 1.0)

        features[idx:idx + PLANET_FEATS] = [
            1.0,
            1.0 if int(pid) in comet_ids else 0.0,
            1.0 if owner == player_id else -1.0 if owner >= 0 else 0.0,
            _clamp(prod / 5.0, 0.0, 1.0),
            _clamp(ships / 100.0, 0.0, 1.0),
            _clamp(orbital_r / ROTATION_RADIUS_LIMIT, 0.0, 1.0),
            math.sin(theta),
            math.cos(theta),
            0.0 if int(pid) in comet_ids else (1.0 if orbital_r + float(p[4]) < ROTATION_RADIUS_LIMIT else 0.0),
            _clamp(own_pressure[i] / 100.0, 0.0, 1.0),
            _clamp(enemy_pressure[i] / 100.0, 0.0, 1.0),
            projected_owner,
            _clamp(projected_garrison / 100.0, 0.0, 1.0),
            _clamp(eta / MAX_STEPS, 0.0, 1.0),
            _clamp(need / 100.0, 0.0, 1.0),
            _clamp(dx / CENTER, -1.0, 1.0),
            _clamp(dy / CENTER, -1.0, 1.0),
            1.0 if earliest_owner[i] == player_id else -1.0 if earliest_owner[i] >= 0 else 0.0,
        ]

    idx = MAX_PLANETS * PLANET_FEATS
    features[idx:idx + GLOBAL_FEATS] = [
        _clamp(angular_velocity / 0.05, 0.0, 1.0),
        _clamp(step / MAX_STEPS, 0.0, 1.0),
        _clamp((MAX_STEPS - step) / MAX_STEPS, 0.0, 1.0),
        _clamp(own_ships / 1000.0, 0.0, 1.0),
        _clamp(enemy_ships / 1000.0, 0.0, 1.0),
        _clamp(own_prod / 50.0, 0.0, 1.0),
        _clamp(enemy_prod / 50.0, 0.0, 1.0),
        1.0 if num_agents == 2 else 0.0,
    ]
    return features


def _aim(source: list[Any], target: list[Any]) -> float:
    return math.atan2(float(target[3]) - float(source[3]), float(target[2]) - float(source[2])) % (2.0 * math.pi)


def policy_actions_to_moves(actions: Iterable[float], obs: dict[str, Any], player_id: int) -> list[list[Any]]:
    """Decode one 96-float policy action vector into Kaggle move lists."""
    act = list(actions)
    if len(act) < NUM_ATNS:
        act.extend([0.0] * (NUM_ATNS - len(act)))
    planets = _planet_slots(obs)
    sources: list[dict[str, Any]] = []
    sinks: list[dict[str, Any]] = []
    budgets: dict[int, int] = {}

    for slot, p in enumerate(planets):
        x = _clamp(float(act[2 * slot]), -1.0, 1.0)
        r = _clamp(float(act[2 * slot + 1]), -1.0, 1.0)
        owner = int(p[1])
        ships = int(p[5])
        if r > INTERVAL_EPS and owner == player_id and ships > 1:
            budgets[slot] = ships - 1
            sources.append({"slot": slot, "planet": p, "x": x, "r": r})
        elif r < -INTERVAL_EPS:
            sinks.append({"slot": slot, "planet": p, "x": x, "r": r, "strength": 0.0})

    for sink in sinks:
        sink["strength"] = sum(
            _interval_strength(src["x"], src["r"], sink["x"], sink["r"])
            for src in sources
            if src["slot"] != sink["slot"]
        )

    moves: list[list[Any]] = []
    for sink in sorted(sinks, key=lambda s: s["strength"], reverse=True)[:MAX_TARGETS]:
        if sink["strength"] <= 0.0 or len(moves) >= MAX_LAUNCHES:
            break
        ranked = []
        for src in sources:
            if src["slot"] == sink["slot"] or budgets.get(src["slot"], 0) <= 0:
                continue
            strength = _interval_strength(src["x"], src["r"], sink["x"], sink["r"])
            if strength > 0.0:
                ranked.append((strength, src))
        ranked.sort(key=lambda item: item[0], reverse=True)
        ranked = ranked[:MAX_SOURCES_PER_TARGET]
        total = sum(strength for strength, _src in ranked)
        if total <= 0.0:
            continue
        target = sink["planet"]
        if int(target[1]) == player_id:
            need = max(2, int(target[6]) * 4 + 1)
        else:
            need = int(target[5]) + 1 + (int(target[6]) * 3 if int(target[1]) >= 0 else 0)
        planned = []
        planned_total = 0
        for strength, src in ranked:
            slot = src["slot"]
            share = min(int(math.ceil(need * (strength / total))), budgets.get(slot, 0))
            planned.append([strength, src, max(0, share)])
            planned_total += max(0, share)
        remaining = need - planned_total
        while remaining > 0:
            candidates = [p for p in planned if p[2] < budgets.get(p[1]["slot"], 0)]
            if not candidates:
                break
            best = max(candidates, key=lambda p: p[0])
            add = min(remaining, budgets[best[1]["slot"]] - best[2])
            best[2] += add
            remaining -= add
        for _strength, src, ships in planned:
            if ships <= 0 or len(moves) >= MAX_LAUNCHES:
                continue
            slot = src["slot"]
            budgets[slot] -= ships
            moves.append([int(src["planet"][0]), _aim(src["planet"], target), int(ships)])
    return moves


interval_actions_to_moves = policy_actions_to_moves
