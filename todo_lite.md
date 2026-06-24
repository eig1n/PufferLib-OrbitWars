# Orbit Wars Lite TODO

Read `ORBIT_WARS_HANDOFF.md` first if you need broad context. `orbit_wars_lite` is a fast-training fork of `ocean/orbit_wars`; do not change raw `orbit_wars` parity code while working on lite.

## Current Lite Contract

- Env: `orbit_wars_lite`
- Config: `config/orbit_wars_lite.ini`
- Observations: `848` floats
  - `48 * 8` planet slots: active, owner, dx, dy, ships, production, comet, orbiting.
  - `10 * 10 * 4` fleet grid: own mass, enemy mass, net dx, net dy.
  - `8 * 7` top fleets: active, owner, x, y, cos, sin, ships.
  - `8` globals.
- Actions: `30` continuous floats = `6` launch proposals.
  - Each proposal is `(send_amount, source_x, source_y, aim_x, aim_y)`.
  - `send_amount <= 0` means noop.
  - `send_amount > 0` maps to ships, with extra resolution in the 1-200 ship range.
  - Source is nearest owned planet to `(source_x, source_y)`.
  - Target is nearest active non-source planet to `(aim_x, aim_y)`.
  - At most one successful fleet per source planet per step.
  - The shot is launched only if the action ray validates against the intended target before blockers/sun/OOB.

## Always Run Locally

1. `PATH=.venv/bin:$PATH bash build.sh orbit_wars_lite --cpu`
   - Builds the CPU lite extension.
2. `.venv/bin/python tests/test_orbit_wars_lite.py`
   - Tests dimensions, amount mapping, one-fleet-per-source behavior, runtime stepping, obs range, and local SPS.
3. `.venv/bin/python tests/test_adapter_parity.py`
   - Tests Python Kaggle adapter observation/action parity against the C lite helper.
4. `PYTHONUNBUFFERED=1 .venv/bin/python tests/test_orbit_wars_parity.py`
   - Run after touching shared/copied physics logic. The original `orbit_wars` parity target must stay correct.

If build fails with `ccache: Read-only file system`, rerun with escalation/approval.

Latest known local verification:
- `tests/test_adapter_parity.py`: passed with 0 observation mismatches and action decode parity.
- `tests/test_orbit_wars_parity.py`: passed after the lite optimization pass.
- `tests/test_orbit_wars_lite.py`: passed; optimized local random-action SPS was about `28.5k` on the test CPU, up from about `26.1k`.

## Colab GPU Smoke Train

Run from local machine:

```bash
colab new --gpu T4
colab exec -f scripts/orbit_wars_lite_colab_gpu.py
```

The script clones/pulls `eig1n/PufferLib-OrbitWars`, builds `orbit_wars_lite` with CUDA, runs `tests/test_orbit_wars_lite.py`, runs a short GPU train, and prints `NEWEST_CHECKPOINT=...`.

Download the checkpoint:

```bash
colab download pufferlib/checkpoints/orbit_wars_lite/<run_id>/<step>.bin
```

Record:
- GPU type
- train SPS
- checkpoint path
- terminal score / episode return
- any crash or invalid observation/action warning

## Kaggle Local Evaluation

The lite Python adapter exists and has C parity coverage:
- `orbit-wars/puffer_agent/main.py` loads the checkpoint on CPU, including Kaggle `exec()` path fallback.
- `orbit-wars/puffer_agent/policy_adapter.py` maps Kaggle obs to `848` floats and decodes `30` actions into moves.
- `tests/test_adapter_parity.py` compares C lite helper obs/actions against the Python adapter.

Current smoke checkpoint:
- `checkpoints/orbit_wars_lite/colab_t4_smoke/0000000006291456.bin`
- Trained for only about `4.2M` steps on Colab T4. Treat it as a pipeline checkpoint, not a strong policy.

Baseline check:

```bash
.venv/bin/python scripts/evaluate_agent.py
```

`orbit-wars/main.py` is the nearest-planet sniper baseline.

Latest known 20-game CPU Kaggle run against nearest sniper:
- `puffer_agent`: 2 wins
- `baseline_sniper`: 18 wins
- crashes/warnings: none

Interpretation: deployment path works, but the checkpoint is too short/small to judge final learnability. Train longer before making strategy conclusions.

## Performance Status

Current lite speed work is useful and should be kept:
- Env-scoped `EnvCache` on `env->client`.
- Cached future planet positions for aim validation.
- Active-fleet list and precomputed fleet `cos/sin` in observation building.
- Precomputed per-player production totals.
- Cached fleet velocity in movement.
- `_POSIX_C_SOURCE` added for clean `rand_r` declaration.

Why this is good:
- It keeps the public lite contract unchanged: `848` obs, `30` actions.
- It optimizes duplicated math and inactive-fleet loops instead of approximating physics.
- It preserves raw `orbit_wars` parity and adapter parity.

Limit:
- The measured gain was about `9.3%` in local random-action tests. That is real but not enough by itself for the target around `700k` CPU SPS on a rented 5090 host.

Next speed checks:
1. Benchmark on the actual target CPU before rewriting more code.
2. Record SPS for noop actions, dense random actions, and trained-policy actions; dense random is the harshest case.
3. Log active fleets, launches/step, rejected proposals, and episode length so slowdowns can be tied to game state.
4. If trained-policy SPS collapses with many fleets, profile movement/collision and fleet allocation first.

## Next Optimization Pass

Highest leverage:
- Add metrics to lite `my_log`: launches/step, noop proposal rate, rejected validation rate, fleets active.
- Profile dense-random actions on target CPU. Latest optimized local random-action number was about `28.5k` agent-SPS.
- If random-action decode is still too slow, keep 6 proposal outputs but validate only the top-K positive `send_amount` proposals during early training. Document any cap in this file and config.
- Consider fleet-pressure observation only if it can be implemented from already-computed fleet/grid passes. Do not add expensive all-fleet/all-planet projection unless profiling proves there is budget.
- Keep the 10x10 fleet grid and 8 top-fleet view for now. They are the intended low-cost substitute for massive fleet observations.

Guardrails:
- Keep `orbit_wars_lite` action count `30` and observation size `848` unless explicitly changing the training contract.
- Keep original `orbit_wars` parity tests passing.
- Keep `tests/test_adapter_parity.py` passing after any adapter or lite decoder change.

## Next Training Step

Run a longer GPU job with the same checked-in config unless deliberately changing model size:
1. Increase `train.total_timesteps` enough to judge learning, not just pipeline health.
2. Save checkpoint, SPS, score, episode return, win rate against nearest sniper.
3. Re-run the 20-game Kaggle local eval. If the policy still loses badly after a meaningful run, inspect action statistics before changing architecture.
