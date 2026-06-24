"""Adapter for running Puffer-trained Orbit Wars Lite policies in Kaggle Python.

This module mirrors the production C environment interface:
- Kaggle observation dict -> compact 848-float policy observation.
- 30-float policy action vector -> Kaggle move list.
"""

from __future__ import annotations

import math
from typing import Any, Iterable

MAX_PLANETS = 48
BOARD_SIZE = 100.0
CENTER = 50.0
SUN_RADIUS = 10.0
FLEET_SPAWN_OFFSET = 0.1
OBS_SIZE = 848
NUM_ATNS = 30


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def _fleet_speed(ships: int) -> float:
    if ships <= 1:
        return 1.0
    ratio = min(math.log(float(ships)) / math.log(1000.0), 1.0)
    return 1.0 + (6.0 - 1.0) * (ratio ** 1.5)


def _player_count(planets: Iterable[list[Any]], fleets: Iterable[list[Any]], player_id: int) -> int:
    owners = [int(player_id)]
    owners.extend(int(p[1]) for p in planets if len(p) >= 2 and int(p[1]) >= 0)
    owners.extend(int(f[1]) for f in fleets if len(f) >= 2 and int(f[1]) >= 0)
    return 4 if max(owners, default=0) >= 2 else 2


def _planet_slots(obs: dict[str, Any]) -> list[list[Any]]:
    planets = [list(p[:7]) for p in obs.get("planets", []) if len(p) >= 7]
    planets.sort(key=lambda p: int(p[0]))
    return planets[:MAX_PLANETS]


def _aim_horizon_turns(step: int, speed: float) -> int:
    horizon = 500 - step
    if horizon <= 0:
        return 0
    if horizon > 500:
        horizon = 500
    if speed < 1e-6:
        return horizon
    board_horizon = int(math.ceil(160.0 / speed)) + 2
    if board_horizon < 1:
        board_horizon = 1
    if horizon > board_horizon:
        horizon = board_horizon
    return horizon


def _ray_circle_distance(x: float, y: float, dx: float, dy: float, cx: float, cy: float, r: float) -> float:
    fx = x - cx
    fy = y - cy
    b = 2.0 * (fx * dx + fy * dy)
    c = fx * fx + fy * fy - r * r
    if c <= 0.0:
        return 0.0
    a = dx * dx + dy * dy
    if a < 1e-15:
        return -1.0
    disc = b * b - 4.0 * a * c
    if disc < 0.0:
        return -1.0
    sq = math.sqrt(disc)
    d1 = (-b - sq) * 0.5 / a
    d2 = (-b + sq) * 0.5 / a
    if d1 >= 0.0:
        return d1
    if d2 >= 0.0:
        return d2
    return -1.0


def _ray_oob_distance(x: float, y: float, dx: float, dy: float) -> float:
    if x < 0.0 or x > BOARD_SIZE or y < 0.0 or y > BOARD_SIZE:
        return 0.0
    best = 1e30
    if dx > 1e-12:
        d = (BOARD_SIZE - x) / dx
        if d >= 0.0 and d < best:
            best = d
    elif dx < -1e-12:
        d = (0.0 - x) / dx
        if d >= 0.0 and d < best:
            best = d
    if dy > 1e-12:
        d = (BOARD_SIZE - y) / dy
        if d >= 0.0 and d < best:
            best = d
    elif dy < -1e-12:
        d = (0.0 - y) / dy
        if d >= 0.0 and d < best:
            best = d
    return best if best < 1e29 else -1.0


def _segment_oob_t(x0: float, y0: float, x1: float, y1: float) -> float:
    if x0 < 0.0 or x0 > BOARD_SIZE or y0 < 0.0 or y0 > BOARD_SIZE:
        return 0.0
    if 0.0 <= x1 <= BOARD_SIZE and 0.0 <= y1 <= BOARD_SIZE:
        return -1.0
    best = 2.0
    dx = x1 - x0
    dy = y1 - y0
    if dx < 0.0:
        t = (0.0 - x0) / dx
        if 0.0 <= t <= 1.0 and t < best:
            best = t
    elif dx > 0.0:
        t = (BOARD_SIZE - x0) / dx
        if 0.0 <= t <= 1.0 and t < best:
            best = t
    if dy < 0.0:
        t = (0.0 - y0) / dy
        if 0.0 <= t <= 1.0 and t < best:
            best = t
    elif dy > 0.0:
        t = (BOARD_SIZE - y0) / dy
        if 0.0 <= t <= 1.0 and t < best:
            best = t
    return best if best <= 1.0 else 0.0


def _segment_circle_t(x1: float, y1: float, x2: float, y2: float, cx: float, cy: float, r: float) -> float:
    dx = x2 - x1
    dy = y2 - y1
    fx = x1 - cx
    fy = y1 - cy
    a = dx * dx + dy * dy
    c = fx * fx + fy * fy - r * r
    if a < 1e-15:
        return 0.0 if c <= 0.0 else -1.0
    b = 2.0 * (fx * dx + fy * dy)
    disc = b * b - 4.0 * a * c
    if disc < 0.0:
        return -1.0
    sqd = math.sqrt(disc)
    t1 = (-b - sqd) / (2.0 * a)
    t2 = (-b + sqd) / (2.0 * a)
    if 0.0 <= t1 <= 1.0:
        return t1
    if 0.0 <= t2 <= 1.0:
        return t2
    if c <= 0.0:
        return 0.0
    return -1.0


def _swept_pair_t(ax: float, ay: float, bx: float, by: float, px0: float, py0: float, px1: float, py1: float, r: float) -> float:
    d0x = ax - px0
    d0y = ay - py0
    dvx = (bx - ax) - (px1 - px0)
    dvy = (by - ay) - (py1 - py0)
    a = dvx * dvx + dvy * dvy
    b = 2.0 * (d0x * dvx + d0y * dvy)
    c = d0x * d0x + d0y * d0y - r * r
    if c <= 0.0:
        return 0.0
    if a < 1e-15:
        return -1.0
    disc = b * b - 4.0 * a * c
    if disc < 0.0:
        return -1.0
    sq = math.sqrt(disc)
    t1 = (-b - sq) / (2.0 * a)
    t2 = (-b + sq) / (2.0 * a)
    if 0.0 <= t1 <= 1.0:
        return t1
    if 0.0 <= t2 <= 1.0:
        return t2
    return -1.0


def _planet_pos_at_tick(planet: list, angular_velocity: float, tick: int) -> tuple[float, float]:
    px, py = float(planet[2]), float(planet[3])
    is_comet = planet[7]
    is_orbiting = planet[8]

    if is_comet:
        return px, py

    if is_orbiting:
        if tick <= 0:
            return px, py
        else:
            dx = px - CENTER
            dy = py - CENTER
            orbital_r = math.hypot(dx, dy)
            angle_0 = math.atan2(dy, dx)
            angle = angle_0 + angular_velocity * float(tick)
            return CENTER + orbital_r * math.cos(angle), CENTER + orbital_r * math.sin(angle)

    return px, py


def _planet_segment_for_turn(planet: list, angular_velocity: float, turn: int) -> tuple[float, float, float, float]:
    x0, y0 = _planet_pos_at_tick(planet, angular_velocity, turn)
    x1, y1 = _planet_pos_at_tick(planet, angular_velocity, turn + 1)
    return x0, y0, x1, y1


def _validate_launch_angle(src_planet: list, tgt_planet: list, ships: int, angle: float, step: int, angular_velocity: float, planets: list) -> bool:
    src_x, src_y, src_r = float(src_planet[2]), float(src_planet[3]), float(src_planet[4])
    tgt_r = float(tgt_planet[4])

    dx = math.cos(angle)
    dy = math.sin(angle)

    x = src_x + (src_r + FLEET_SPAWN_OFFSET) * dx
    y = src_y + (src_r + FLEET_SPAWN_OFFSET) * dy
    speed = _fleet_speed(ships)
    horizon = _aim_horizon_turns(step, speed)
    if horizon <= 0:
        return False

    for turn in range(horizon):
        nx = x + speed * dx
        ny = y + speed * dy
        target_t = -1.0
        blocker_t = -1.0
        blocker_pid = -1

        for p in planets:
            pid = p[0]
            pr = float(p[4])
            px0, py0, px1, py1 = _planet_segment_for_turn(p, angular_velocity, turn)
            hit_t = _swept_pair_t(x, y, nx, ny, px0, py0, px1, py1, pr)
            if hit_t < 0.0:
                continue

            if pid == tgt_planet[0]:
                if target_t < 0.0 or hit_t < target_t:
                    target_t = hit_t
            else:
                if blocker_t < 0.0 or hit_t < blocker_t:
                    blocker_t = hit_t
                    blocker_pid = pid

        oob_t = _segment_oob_t(x, y, nx, ny)
        sun_t = _segment_circle_t(x, y, nx, ny, CENTER, CENTER, SUN_RADIUS)
        eps = 1e-5

        if target_t >= 0.0:
            if blocker_t >= 0.0 and (blocker_t <= target_t + eps or blocker_pid < tgt_planet[0]):
                return False
            if oob_t >= 0.0 and oob_t <= target_t + eps:
                return False
            if sun_t >= 0.0 and sun_t <= target_t + eps:
                return False
            return True

        if blocker_t >= 0.0 or oob_t >= 0.0 or sun_t >= 0.0:
            return False

        x = nx
        y = ny

    return False


def _validate_static_target_angle(src_planet: list, tgt_planet: list, ships: int, angle: float, step: int, angular_velocity: float, planets: list) -> bool:
    src_x, src_y, src_r = float(src_planet[2]), float(src_planet[3]), float(src_planet[4])
    tgt_x, tgt_y, tgt_r = float(tgt_planet[2]), float(tgt_planet[3]), float(tgt_planet[4])

    dx = math.cos(angle)
    dy = math.sin(angle)

    x = src_x + (src_r + FLEET_SPAWN_OFFSET) * dx
    y = src_y + (src_r + FLEET_SPAWN_OFFSET) * dy
    speed = _fleet_speed(ships)
    horizon = _aim_horizon_turns(step, speed)
    if horizon <= 0:
        return False

    target_dist = _ray_circle_distance(x, y, dx, dy, tgt_x, tgt_y, tgt_r)
    if target_dist < 0.0:
        return False
    target_time = target_dist / speed
    if target_time > float(horizon) + 1e-6:
        return False

    oob_dist = _ray_oob_distance(x, y, dx, dy)
    if oob_dist >= 0.0 and oob_dist <= target_dist + 1e-5:
        return False

    sun_dist = _ray_circle_distance(x, y, dx, dy, CENTER, CENTER, SUN_RADIUS)
    if sun_dist >= 0.0 and sun_dist <= target_dist + 1e-5:
        return False

    for p in planets:
        pid = p[0]
        if pid == tgt_planet[0]:
            continue
        is_comet = p[7]
        is_orbiting = p[8]
        if is_orbiting or is_comet:
            continue
        px, py, pr = float(p[2]), float(p[3]), float(p[4])
        blocker_dist = _ray_circle_distance(x, y, dx, dy, px, py, pr)
        if blocker_dist >= 0.0 and blocker_dist <= target_dist + 1e-5:
            return False

    max_turn = int(math.ceil(target_time))
    if max_turn > horizon:
        max_turn = horizon

    fx = x
    fy = y
    for turn in range(max_turn + 1):
        nx = fx + speed * dx
        ny = fy + speed * dy
        for p in planets:
            pid = p[0]
            if pid == tgt_planet[0]:
                continue
            is_comet = p[7]
            is_orbiting = p[8]
            if not is_orbiting and not is_comet:
                continue
            pr = float(p[4])
            px0, py0, px1, py1 = _planet_segment_for_turn(p, angular_velocity, turn)
            hit_t = _swept_pair_t(fx, fy, nx, ny, px0, py0, px1, py1, pr)
            if hit_t >= 0.0 and float(turn) + float(hit_t) <= target_time + 1e-5:
                return False
        fx = nx
        fy = ny

    return True


def action_to_board(v: float) -> float:
    v = _clamp(v, -1.0, 1.0)
    return 50.0 * (v + 1.0)


def amount_to_ships(amount: float, available: int) -> int:
    if available <= 0 or amount <= 0.0:
        return 0
    u = _clamp(amount, 0.0, 1.0)
    ships = int(u * 200.0 + 0.5)
    if ships > available:
        ships = available
    return ships


def compact_features(obs: dict[str, Any], player_id: int) -> list[float]:
    """Build the 848-float production observation used by the C env."""
    raw_planets = obs.get("planets", [])
    raw_fleets = obs.get("fleets", [])
    comet_ids = set(obs.get("comet_planet_ids", []))
    step = int(obs.get("step", 0))
    angular_velocity = float(obs.get("angular_velocity", 0.03))

    sorted_planets = [list(p[:7]) for p in raw_planets if len(p) >= 7]
    sorted_planets.sort(key=lambda p: int(p[0]))
    sorted_planets = sorted_planets[:MAX_PLANETS]

    # Pre-calculate comet and orbiting flags for positioning
    for p in sorted_planets:
        pid = int(p[0])
        px, py, radius = float(p[2]), float(p[3]), float(p[4])
        is_comet = pid in comet_ids
        dx = px - CENTER
        dy = py - CENTER
        orbital_r = math.hypot(dx, dy)
        is_orbiting = (orbital_r + radius < 50.0) and not is_comet
        p.append(is_comet)
        p.append(is_orbiting)

    num_agents = _player_count(raw_planets, raw_fleets, player_id)

    own_ships = enemy_ships = own_prod = enemy_prod = 0
    for p in sorted_planets:
        owner = int(p[1])
        ships = int(p[5])
        prod = int(p[6])
        if owner == player_id:
            own_ships += ships
            own_prod += prod
        elif owner >= 0:
            enemy_ships += ships
            enemy_prod += prod

    for f in raw_fleets:
        if len(f) < 7:
            continue
        owner = int(f[1])
        ships = int(f[6])
        if owner == player_id:
            own_ships += ships
        elif owner >= 0:
            enemy_ships += ships

    features = []

    # 1. Planet slots (48 * 8 = 384 floats)
    for s in range(MAX_PLANETS):
        if s < len(sorted_planets):
            p = sorted_planets[s]
            owner = int(p[1])
            px, py, radius = float(p[2]), float(p[3]), float(p[4])
            ships, prod, is_comet, is_orbiting = int(p[5]), int(p[6]), p[7], p[8]
            owner_rel = 0.0
            if owner == player_id:
                owner_rel = 1.0
            elif owner >= 0:
                owner_rel = -1.0
            dx = px - CENTER
            dy = py - CENTER

            features.extend([
                1.0,
                owner_rel,
                _clamp(dx / CENTER, -1.0, 1.0),
                _clamp(dy / CENTER, -1.0, 1.0),
                _clamp(float(ships) / 200.0, 0.0, 5.0),
                _clamp(float(prod) / 5.0, 0.0, 1.0),
                1.0 if is_comet else 0.0,
                1.0 if is_orbiting else 0.0
            ])
        else:
            features.extend([0.0] * 8)

    # 2. Fleet grid (10 * 10 * 4 = 400 floats)
    fleet_grid = [0.0] * 400
    for f in raw_fleets:
        if len(f) < 7:
            continue
        owner = int(f[1])
        fx, fy = float(f[2]), float(f[3])
        angle = float(f[4])
        ships = int(f[6])

        gx = int(fx / 10.0)
        gy = int(fy / 10.0)
        gx = min(max(gx, 0), 9)
        gy = min(max(gy, 0), 9)

        base = (gy * 10 + gx) * 4
        mass = _clamp(float(ships) / 100.0, 0.0, 5.0)
        dir_x = math.cos(angle) * mass
        dir_y = math.sin(angle) * mass

        if owner == player_id:
            fleet_grid[base + 0] += mass
            fleet_grid[base + 2] += dir_x
            fleet_grid[base + 3] += dir_y
        else:
            fleet_grid[base + 1] += mass
            fleet_grid[base + 2] -= dir_x
            fleet_grid[base + 3] -= dir_y

    for val in fleet_grid:
        features.append(_clamp(val, -5.0, 5.0))

    # 3. Clean fleet slots (8 * 7 = 56 floats), rotating for coverage.
    active_fleets = []
    for idx, f in enumerate(raw_fleets):
        if len(f) < 7:
            continue
        active_fleets.append(f)

    clean_fleets = []
    if active_fleets:
        start = (step + player_id * 8) % len(active_fleets)
        count = min(len(active_fleets), 8)
        for k in range(count):
            clean_fleets.append(active_fleets[(start + k) % len(active_fleets)])

    for k in range(8):
        if k < len(clean_fleets):
            f = clean_fleets[k]
            owner = int(f[1])
            fx, fy = float(f[2]), float(f[3])
            angle = float(f[4])
            ships = int(f[6])

            owner_rel = 1.0 if owner == player_id else -1.0

            features.extend([
                1.0,
                owner_rel,
                _clamp((fx - CENTER) / CENTER, -1.0, 1.0),
                _clamp((fy - CENTER) / CENTER, -1.0, 1.0),
                math.cos(angle),
                math.sin(angle),
                _clamp(float(ships) / 200.0, 0.0, 5.0)
            ])
        else:
            features.extend([0.0] * 7)

    # 4. Globals (8 floats)
    features.extend([
        _clamp(angular_velocity / 0.05, 0.0, 1.0),
        _clamp(float(step) / 500.0, 0.0, 1.0),
        _clamp(float(500 - step) / 500.0, 0.0, 1.0),
        _clamp(float(own_ships) / 1000.0, 0.0, 1.0),
        _clamp(float(enemy_ships) / 1000.0, 0.0, 1.0),
        _clamp(float(own_prod) / 50.0, 0.0, 1.0),
        _clamp(float(enemy_prod) / 50.0, 0.0, 1.0),
        1.0 if num_agents == 2 else 0.0
    ])

    return features


def policy_actions_to_moves(actions: Iterable[float], obs: dict[str, Any], player_id: int) -> list[list[Any]]:
    """Decode one 30-float policy action vector into Kaggle move lists."""
    act = list(actions)
    if len(act) < NUM_ATNS:
        act.extend([0.0] * (NUM_ATNS - len(act)))

    raw_planets = obs.get("planets", [])
    comet_ids = set(obs.get("comet_planet_ids", []))

    planets = [list(p[:7]) for p in raw_planets if len(p) >= 7]
    planets.sort(key=lambda p: int(p[0]))
    planets = planets[:MAX_PLANETS]

    for p in planets:
        pid = int(p[0])
        px, py, radius = float(p[2]), float(p[3]), float(p[4])
        is_comet = pid in comet_ids
        dx = px - CENTER
        dy = py - CENTER
        orbital_r = math.hypot(dx, dy)
        is_orbiting = (orbital_r + radius < 50.0) and not is_comet
        p.append(is_comet)
        p.append(is_orbiting)

    slots_with_amount = []
    for s in range(6):
        base = s * 5
        amount = _clamp(float(act[base + 0]), -1.0, 1.0)
        if amount > 0.0:
            slots_with_amount.append((amount, s))

    slots_with_amount.sort(key=lambda x: x[0], reverse=True)

    moves = []
    source_used_ids = set()
    launches = 0

    for amount, s in slots_with_amount:
        if launches >= 16:
            break

        base = s * 5
        dir_x = _clamp(float(act[base + 1]), -1.0, 1.0)
        dir_y = _clamp(float(act[base + 2]), -1.0, 1.0)
        if dir_x * dir_x + dir_y * dir_y < 1e-6:
            continue

        sx = action_to_board(act[base + 3])
        sy = action_to_board(act[base + 4])

        src_id = -1
        best_d2 = 1e30
        for p in planets:
            pid, owner, px, py, radius, ships, production, is_comet, is_orbiting = p
            if owner != player_id or ships <= 1 or pid in source_used_ids:
                continue
            dx = px - sx
            dy = py - sy
            d2 = dx * dx + dy * dy
            if d2 < best_d2:
                best_d2 = d2
                src_id = pid

        if src_id < 0:
            continue

        src_planet = next(p for p in planets if p[0] == src_id)
        available = src_planet[5] - 1
        ships = amount_to_ships(amount, available)
        if ships <= 0:
            continue

        angle = math.atan2(dir_y, dir_x) % (2.0 * math.pi)

        moves.append([int(src_id), angle, int(ships)])
        source_used_ids.add(src_id)
        launches += 1

    return moves


interval_actions_to_moves = policy_actions_to_moves
