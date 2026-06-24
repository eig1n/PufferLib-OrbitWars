# Orbit Wars Lite TODO

Read `ORBIT_WARS_HANDOFF.md` first if you need broad context. `orbit_wars_lite` is a fast-training fork of `ocean/orbit_wars`; do not change raw `orbit_wars` parity code while working on lite.

For the next lite action/observation rewrite, read `orbit_wars_lite_decoder_plan.md` and `orbit_wars_lite_optimization_notes.md`.

## Current Lite Contract

- Env: `orbit_wars_lite`
- Config: `config/orbit_wars_lite.ini`
- Observations: `848` floats
  - `48 * 8` planet slots: active, owner, dx, dy, ships, production, comet, orbiting.
  - `10 * 10 * 4` fleet grid: own mass, enemy mass, net dx, net dy.
  - `8 * 7` clean fleet slots: active, owner, x, y, cos, sin, ships. These rotate through active fleets for coverage.
  - `8` globals.
- Actions: `30` continuous floats = `6` launch proposals.
  - Each proposal is `(send_amount, dir_x, dir_y, source_x, source_y)`.
  - `send_amount <= 0` means noop.
  - `send_amount > 0` maps linearly to up to 200 ships, capped by `source.ships - 1`.
  - `(dir_x, dir_y)` is clamped to `[-1, 1]`; near-zero direction means noop.
  - Source is nearest owned planet to `(source_x, source_y)`.
  - At most one successful fleet per source planet per step.
  - The shot launches immediately in the requested direction. It intentionally may miss; lite does not select targets or validate hits.

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
- `tests/test_adapter_parity.py`: passed with 0 observation mismatches and direct-action decode parity.
- `tests/test_orbit_wars_parity.py`: passed after the lite direct-decoder rewrite.
- `tests/test_orbit_wars_lite.py`: passed; local random-action SPS in that test was about `47k` after the direct-decoder rewrite.

## Colab GPU Smoke Train & Setup

Run from local machine:

```bash
# 1. Start Colab session
colab new --gpu T4

# 2. Run simplified environment setup (do this once per session)
colab exec --timeout 300 -f scripts/colab_setup.py

# 3. Execute training script (runs instantly, uses cached setup)
colab exec --timeout 900 -f scripts/orbit_wars_lite_colab_gpu.py
```

The setup script installs only the minimal system libraries (`clang`, `libomp-dev`, `ccache`), python dependencies (`pybind11`, `numpy`, `rich`, `kaggle-environments`, `wandb`), and editable pufferlib clone.
The training script pulls latest changes, builds the CUDA backend, runs `tests/test_orbit_wars_lite.py`, trains for 10 minutes, and writes its own log file on the VM.

Download the checkpoint and the log:

```bash
# Download the checkpoint
colab download -s <session_id> /content/pufferlib/checkpoints/orbit_wars_lite/<run_id>/pool/<step>.bin checkpoints/orbit_wars_lite/colab_t4_selfplay_128_5/checkpoint.bin

# Download the training console log
colab download -s <session_id> /content/pufferlib/logs/orbit_wars_lite_colab_gpu.log logs/orbit_wars_lite_colab_gpu.log
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
- `scripts/evaluate_agent.py` is the canonical local strength check against `orbit-wars/main.py`.

Current selfplay checkpoint:
- `checkpoints/orbit_wars_lite/colab_t4_selfplay_128_5/checkpoint.bin`
- Configured with `hidden_size = 128`, `num_layers = 5`, and selfplay enabled.
- Trained for about 10 minutes (~30M steps) on Colab T4.

Baseline checks:

```bash
# Against nearest planet sniper
.venv/bin/python scripts/evaluate_agent.py

# Against built-in random agent
.venv/bin/python scripts/evaluate_against_random.py
```

Latest known 20-game CPU Kaggle runs:
- Against `baseline_sniper`:
  - `puffer_agent`: 4 wins
  - `baseline_sniper`: 16 wins
- Against `random`:
  - `puffer_agent`: 4 wins
  - `random`: 16 wins

Interpretation: The model learns and scales (win rate against sniper baseline doubled from 2 to 4). However, the policy is still in the early stages of learning, performing poorly against random entropy. Train much longer (e.g. overnight) or tune hyper-parameters before making final strategy conclusions.

## Performance Status

Current lite speed work is useful and should be kept:
- Env-scoped `EnvCache` on `env->client`.
- Cached future planet positions for aim validation.
- Active-fleet list and precomputed fleet `cos/sin` in observation building.
- Cached ID-sorted planet observation slots in `EnvCache`, rebuilt once per step/signature instead of once per player.
- Observation fast paths skip fleet-grid and clean-fleet work when no fleets are active, and skip the fleet-slot scan entirely before the first launch.
- Fleet-grid summaries are now built once per observation pass and converted cheaply into each player-relative view.
- Normal movement/observation active-fleet scans are bounded by `min(next_fleet_id, OW_MAX_FLEETS)` before all fleet slots have ever been used.
- Precomputed per-player production totals.
- Cached fleet velocity in movement.
- Fleet movement now has a no-fleet fast path, active-fleet/active-planet local lists, and conservative swept-AABB rejection before exact planet collision checks.
- `_POSIX_C_SOURCE` added for clean `rand_r` declaration.

Why this is good:
- It keeps the public lite contract unchanged: `848` obs, `30` actions.
- It optimizes duplicated math and inactive-fleet loops instead of approximating physics.
- It preserves raw `orbit_wars` parity and adapter parity.

Limit:
- The measured gain was about `9.3%` in local random-action tests. That is real but not enough by itself for the target around `700k` CPU SPS.
- Do not over-focus on target-CPU micro-optimization. First compare against similar Puffer envs and remove algorithmic waste.

Current matched `cpu_step` benchmark command:

```bash
PATH=.venv/bin:$PATH bash build.sh <env> --cpu
OMP_NUM_THREADS=8 .venv/bin/python scripts/benchmark_env_sps.py <env> --total-agents 512 --num-buffers 1 --steps 300 --warmup 50
```

Latest local comparison:
- `orbit_wars_lite`, 848 obs / 30 continuous actions, old validated decoder: `~63k` noop SPS, `~24k` dense-random SPS with `OMP_NUM_THREADS=8`; `~20k` noop, `~11k` random with `OMP_NUM_THREADS=1`.
- `orbit_wars_lite`, direct direction decoder: `~146k` noop SPS, `~75k` dense-random SPS with `OMP_NUM_THREADS=8`, `512` agents, `300` timed steps on the local machine.
- `orbit_wars_lite`, direct decoder plus movement broadphase: longer local run gave `~126k` noop SPS and `~84k` dense-random SPS with `OMP_NUM_THREADS=8`, `512` agents, `1000` timed steps.
- `orbit_wars_lite`, plus cached planet-slot ordering: short local run gave `~183k` noop SPS and `~95k` dense-random SPS with `OMP_NUM_THREADS=8`, `512` agents, `300` timed steps.
- `orbit_wars_lite`, plus observation fleet fast paths, shared grid summaries, and bounded fleet scans: longer local run gave `~275k` noop SPS and `~124k` dense-random SPS with `OMP_NUM_THREADS=8`, `512` agents, `1000` timed steps.
- `moba`, 510 byte obs / 6 discrete actions: `~102k` noop SPS, `~64k` random SPS with default local OpenMP.
- `drone`, 19 obs / 4 continuous actions: `~329k` noop SPS, `~143k` random SPS with default local OpenMP.
- `robocode`, 16 obs / 5 discrete actions, moving bullets/collisions: `~1.2M` noop SPS, `~817k` random SPS with default local OpenMP; explicit thread runs were noisy but still much faster than lite.

Interpretation:
- Other moving Puffer envs are fast because their action/obs contracts are compact and their expensive loops are tightly bounded.
- Orbit Wars Lite used to be slowest when random actions triggered six validated launch attempts per agent. The current direct-direction decoder removes that validation cost and substantially improves both noop and random local benchmarks; re-benchmark on the target CPU before choosing the next optimization.
- The strongest remaining optimization candidates are remaining observation construction, persistent active-fleet bookkeeping if post-launch fleet scans still matter, fleet lifetime/count, and game-over/scoring fleet summaries. Planet slot sorting and fleet-grid summaries are already cached/shared. Avoid expensive all-fleet/all-planet projection features.

Next speed checks:
1. Benchmark on the actual target CPU before rewriting more code, but compare against `moba`/`robocode` too.
2. Record SPS for noop actions, dense random actions, and trained-policy actions; dense random is the harshest case.
3. Log active fleets, launches/step, noop proposals, zero-direction skips, and episode length so slowdowns can be tied to game state.
4. If trained-policy SPS collapses with many fleets, profile movement/collision and fleet allocation first.

## Next Optimization Pass

Highest leverage:
- Add metrics to lite `my_log`: launches/step, noop proposal rate, zero-direction skip rate, fleets active.
- Profile dense-random actions on target CPU. Latest optimized local random-action number was about `28.5k` agent-SPS.
- If random-action decode is still too slow after the direct decoder rewrite, measure source lookup and raw-action application first. Do not reintroduce target validation to lite.
- Consider reducing fleet pressure directly: smaller max active fleets, shorter fleet lifetime/OOB horizon, or lower successful launches per step. Keep the game semantics intentional and document the lite divergence.
- Consider fleet-pressure observation only if it can be implemented from already-computed fleet/grid passes. Do not add expensive all-fleet/all-planet projection unless profiling proves there is budget.
- Keep the 10x10 fleet grid and 8 clean fleet slots for now. They are the intended low-cost substitute for massive fleet observations.

Guardrails:
- Keep `orbit_wars_lite` action count `30` and observation size `848` unless explicitly changing the training contract.
- Keep original `orbit_wars` parity tests passing.
- Keep `tests/test_adapter_parity.py` passing after any adapter or lite decoder change.

## Next Training Step

Run a longer GPU job with the same checked-in config unless deliberately changing model size:
1. Increase `train.total_timesteps` enough to judge learning, not just pipeline health.
2. Save checkpoint, SPS, score, episode return, win rate against nearest sniper.
3. Re-run the 20-game Kaggle local eval. If the policy still loses badly after a meaningful run, inspect action statistics before changing architecture.
