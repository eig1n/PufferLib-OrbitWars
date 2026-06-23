# Orbit Wars TODO

Read `ORBIT_WARS_HANDOFF.md` first, then this file. Keep public action and observation dimensions unchanged unless explicitly asked. Keep raw `PARITY_TESTING` physics/observation parity intact.

## Always Run

After C simulator or decoder changes:

1. `PATH=.venv/bin:$PATH bash build.sh orbit_wars --cpu`
   - Builds the CPU extension.
2. `.venv/bin/python -c 'import tests.test_orbit_wars_decoder as t; [getattr(t, n)() for n in dir(t) if n.startswith("test_")]'`
   - Tests interval decoder and validated aiming.
3. `PYTHONUNBUFFERED=1 .venv/bin/python tests/test_orbit_wars.py`
   - Tests vec runtime, random continuous actions, observation range, termination, and local SPS.
4. `PYTHONUNBUFFERED=1 .venv/bin/python tests/test_orbit_wars_parity.py`
   - Tests raw C physics/observations against Kaggle Python. This must pass after any physics-touching change.

If build fails with `ccache: Read-only file system`, rerun with approval/escalation. `pytest` is not installed; use the direct decoder command above.

## Priority 1: Projection Features

Goal: make compact observations' incoming pressure/ETA truthful.

Files:
- `ocean/orbit_wars/orbit_wars.h`
- `tests/test_orbit_wars_decoder.py` or a new focused projection test file

Instructions:
1. Reuse the validated hit helpers near `ow_aim_angle_to_planet`.
2. Replace the current simple fleet ETA estimate in `ow_compute_and_scale_observations` with validated first-hit logic:
   - For each active fleet, project along its real heading and speed.
   - Find the first planet it would hit before sun/OOB.
   - Include static, orbiting, and comet planets.
   - Ignore fleets with no validated hit.
3. Update `own_pressure`, `enemy_pressure`, `earliest_eta`, and `earliest_owner` from that validated target only.
4. Add focused tests for static incoming, moving/orbiting incoming if feasible, sun/OOB rejection, and blocker-first target selection.
5. Run all commands in `Always Run`.

Do not change raw observation layout or compact observation size.

## Priority 2: Decoder Performance

Current local runtime: about `4,072` agent-steps/sec in `tests/test_orbit_wars.py` with 64 agents, 1 thread, dense random actions. Target: roughly `700k` agent-steps/sec on rented Vast.ai hardware. First measure on target hardware before large rewrites.

Fastest safe options:
1. Add a training-only decoded launch cap, e.g. `OW_MAX_DECODED_ACTIONS_PER_PLAYER = 2` or `4`, while leaving raw `OW_MAX_ACTIONS_PER_PLAYER = 16` for parity.
2. Top-K filter source and sink intervals before aiming:
   - Keep only strongest owned sources and strongest sinks per player.
   - Run pair scoring/aim validation only for final candidate pairs.
3. Raise active interval threshold or add a sparsity/noop bias so random early policies do not activate most slots.
4. Reduce `OW_MAX_TARGETS` and/or `OW_MAX_SOURCES_PER_TARGET` for decoded training.
5. Add cheap broad-phase caches for static blockers and moving target candidates.

Rules:
- `c_step_core` raw physics should remain unchanged unless fixing parity-tested physics.
- If launch count semantics change, document it in `ORBIT_WARS_HANDOFF.md`.
- Keep `NUM_ATNS=96`, `OBS_SIZE=872`, and `PARITY_TESTING OBS_SIZE=6484`.
- Track SPS, launches/step, noop rate, invalid/no-launch rate, and capture/reinforce split.

## Priority 3: Python Policy Adapter Parity

Goal: Kaggle evaluation should use the same semantics as C production decoder.

File:
- `orbit-wars/puffer_agent/policy_adapter.py`

Instructions:
1. Mirror C validated aiming:
   - Static direct aim with blocker/sun/OOB validation.
   - Orbiting target intercept solve.
   - Comet path-indexed aim.
   - Skip move if no validated intercept exists.
2. Mirror projection features after Priority 1 lands.
3. Add lightweight Python tests comparing policy adapter moves/features against C helper results on hand-built states.
4. Do not use this adapter for training; it is for Kaggle checkpoint evaluation.

## Priority 4: Colab CPU/GPU Smoke Training

Status: functionally ready to run short Colab tests now. Performance is the main risk, so keep runs short until SPS and launch metrics are known.

Run:
1. `scripts/orbit_wars_colab_setup.py`
2. `scripts/orbit_wars_colab_build.py`
3. `scripts/orbit_wars_colab_parity.py`
4. `scripts/orbit_wars_colab_train.py`
   - Start CPU, `selfplay.enabled=0`, small `total_agents`, short total steps, force checkpoint save.
5. Repeat short run on GPU after CPU works.

Record:
- SPS
- launches/step
- noop rate
- invalid/no-launch rate
- capture vs reinforce split
- terminal score / episode return
- checkpoint path

## Priority 5: Local Kaggle Evaluation

Goal: evaluate a trained checkpoint inside the original Kaggle Python environment against baseline agents.

Instructions:
1. Export/download latest `checkpoints/orbit_wars/**/*.bin`.
2. Load policy through `orbit-wars/puffer_agent/policy_adapter.py`.
3. Build a local evaluator that runs original Kaggle `orbit_wars` games against:
   - random
   - nearest-sniper/simple heuristic
   - existing producer baseline
4. Report winrate, terminal score, invalid/noop rate, launches/step, and common failure cases.
5. If adapter/C mismatch appears, fix adapter parity before drawing training conclusions.

## Guardrails

- Do not edit `vendor/**`.
- Do not change action/observation public dimensions without explicit instruction.
- Do not weaken `tests/test_orbit_wars_parity.py`.
- Keep changes small and rerun focused tests first.
- If a model is unsure, inspect `ocean/orbit_wars/orbit_wars.h` and the decoder tests before editing.
