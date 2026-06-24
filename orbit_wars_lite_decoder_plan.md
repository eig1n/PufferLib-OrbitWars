# Orbit Wars Lite Decoder Plan

Context: `orbit_wars_lite` should be the cheap, learnable fork. It should not use the slower target/intercept/validated-shot semantics from full `orbit_wars`.

## Action Contract

Keep public size unchanged: `30` continuous floats = `6` proposals of `5` floats.

Use option B:

```text
(amount, dir_x, dir_y, source_x, source_y)
```

Decoder semantics:

1. Clamp all action values to `[-1, 1]`.
2. `amount <= 0` means noop.
3. Convert `source_x/source_y` from `[-1, 1]` to board coordinates.
4. Pick nearest owned active planet with enough ships.
5. Convert `(dir_x, dir_y)` to launch angle with `atan2(dir_y, dir_x)`.
6. If direction vector is near zero, skip proposal.
7. Launch immediately. Do not select target, solve intercept, or validate hit.
8. Keep at most one successful launch per source planet per step.

This intentionally allows missed shots. The model must learn useful aiming from observations.

## Amount Mapping

Planet ship observation is currently normalized as `ships / 200`, clamped to `[0, 5]`.

Preferred simple mapping:

```text
requested_ships = round(clamp(amount, 0, 1) * 200)
ships = min(requested_ships, source.ships - 1)
```

Reasoning:
- The action uses the same rough ship scale as planet observations.
- It gives precise-enough control in the important `0..200` range.
- Large garrisons can still send bigger chunks only if this is later extended, but keep this simple first.

Alternative if stronger large-garrison use is needed later:

```text
ships = round(clamp(amount, 0, 1) * (source.ships - 1))
```

Do not use the current nonlinear amount mapping unless there is a measured reason.

## Observation Contract

Keep observations normalized and near `[-1, 1]` where practical.

Keep cartesian coordinates everywhere for now:
- Planet position should remain normalized cartesian relative to sun/board.
- Action source coordinates are cartesian.
- Fleet positions are cartesian.

Keep global angular velocity in observations.
Keep moving/orbiting indicator in planet observations.

## Clean Fleet Observations

Current clean fleet slots are top-8 by `ships + enemy_bonus`; replace this with soft coverage sampling or rotation.

Goal:
- The recurrent policy should periodically see every active fleet in clean slots.
- Priority is useful, but coverage matters more than always showing only the largest fleets.
- Empty slots remain all zeros.

Suggested cheap priority score for sampling:

```text
score = base
      + smooth_ship_weight
      + smooth_cell_crowding_weight
      + cheap_grid_trajectory_weight
      + small_random_or_rotating_tiebreak
```

Guidelines:
- Weight by ship count smoothly, not overwhelmingly.
- Increase probability for fleets sharing a 10x10 grid cell with other fleets.
- Use the existing 10x10 grid pass to derive crowding almost for free.
- If adding trajectory priority, use cheap grid-level direction only. Do not run all-fleet/all-planet intercept calculations.
- Keep probabilities fairly even so small/isolated fleets still appear.

Implementation options:
- Deterministic rotating reservoir over active fleets, with score-biased ordering.
- Hash/randomized weighted reservoir seeded by env step and fleet id.
- Simpler first pass: rotate through active fleet list and use score only to break ties.

## Required Adapter/Test Work

After changing C decoder:

1. Update `orbit-wars/puffer_agent/policy_adapter.py` to match `(amount, dir_x, dir_y, source_x, source_y)`.
2. Update `tests/test_adapter_parity.py` expected action decode behavior.
3. Update `tests/test_orbit_wars_lite.py` decoder tests.
4. Run:
   - `PATH=.venv/bin:$PATH bash build.sh orbit_wars_lite --cpu`
   - `.venv/bin/python tests/test_orbit_wars_lite.py`
   - `.venv/bin/python tests/test_adapter_parity.py`
   - `PYTHONUNBUFFERED=1 .venv/bin/python tests/test_orbit_wars_parity.py` if shared/copied physics logic was touched.

## Do Not Do

- Do not change public action count or observation size unless explicitly requested.
- Do not add target selection, intercept solving, or validated launch checks to lite actions.
- Do not add expensive all-fleet/all-planet projection observations.
- Do not modify raw `orbit_wars` parity behavior while working on lite.
