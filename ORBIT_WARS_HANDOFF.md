# Orbit Wars Handoff

## Current Goal
Implement the initial 1v1 fast training interface for Orbit Wars:
- Keep C simulator physics and raw Kaggle-style parity path intact.
- Use compact planet-centric production observations for training.
- Use all-continuous interval actions: one `(x, r)` pair per canonical planet slot.
- Start with 1v1 training; 4-player parity support remains in tests.
- Repository base has been synced to upstream `PufferAI/PufferLib` commit `9a4eb87`, with Orbit Wars files overlaid in this same working directory.

## Important Files
- `ocean/orbit_wars/orbit_wars.h`: Core C simulator, game state, turn phases, observation builders, interval action decoder, raw-action physics path.
- `ocean/orbit_wars/binding.c`: PufferLib binding constants and pointer setup. Production build currently exposes `OBS_SIZE=872`, `NUM_ATNS=96`, `ACT_SIZES={1...}`. `PARITY_TESTING` keeps `OBS_SIZE=6484`.
- `tests/test_orbit_wars.py`: Local vector/runtime/range/termination/perf check. Now emits continuous random actions when all action sizes are `1`.
- `tests/test_orbit_wars_parity.py`: C vs Python physics/raw-observation parity suite. Compiles helper with `-DPARITY_TESTING`.
- `tests/orbit_wars_test_lib.c`: C helper exports for parity and decoder tests.
- `tests/test_orbit_wars_decoder.py`: Focused direct decoder assertions for interval matching and validated aiming.
- `todo.md`: Current implementation checklist with concrete instructions for follow-up agents.
- `scripts/orbit_wars_local_checks.sh`: Runs build, decoder, runtime, and parity checks with logs saved to `logs/orbit_wars/<timestamp>/`.
- `config/orbit_wars.ini`: Main training config. For local/CPU training, set `selfplay.enabled=0`.
- `orbit-wars/orbit_wars.py`: Reference Kaggle Python implementation. Do not treat as training code.
- `orbit-wars/puffer_agent/policy_adapter.py`: First-pass Python mirror for running Puffer-trained checkpoints in Kaggle-style Python. Not used by C training.

## Repo Map
- Entry points:
  - `build.sh orbit_wars --cpu`: builds CPU extension.
  - `tests/test_orbit_wars.py`: runtime smoke/perf suite.
  - `tests/test_orbit_wars_parity.py`: C/Python parity suite.
  - `scripts/orbit_wars_local_checks.sh`: logged local check runner.
- Config:
  - `config/orbit_wars.ini`: env, vec, self-play, policy, training hyperparameters.
- Core modules:
  - `ocean/orbit_wars/orbit_wars.h`: simulator and interface logic.
  - `ocean/orbit_wars/binding.c`: exported PufferLib dimensions and lifecycle binding.
  - `src/vecenv.h`: generic vecenv plumbing used by bindings.
- Reference/deployment:
  - `orbit-wars/orbit_wars.py`: reference game implementation.
  - `orbit-wars/main.py`: simple reference agent.
  - `orbit-wars/producer_agent/orbit_lite/`: standalone Python planning/deployment helpers.
  - `orbit-wars/puffer_agent/`: deployment helpers for policies trained with the PufferLib C env.
- Tests:
  - `tests/test_orbit_wars.py`
  - `tests/test_orbit_wars_parity.py`
  - `tests/test_orbit_wars_decoder.py`
  - `tests/orbit_wars_test_lib.c`
- Colab:
  - `scripts/orbit_wars_colab_setup.py`
  - `scripts/orbit_wars_colab_build.py`
  - `scripts/orbit_wars_colab_parity.py`
  - `scripts/orbit_wars_colab_train.py`
  - `scripts/orbit_wars_colab_test.py`

## Decisions Made
- Planet slots are canonicalized by ascending planet id and padded to 48.
- Production action space is continuous: `NUM_ATNS = 96`, `ACT_SIZES` all `1`.
- Each planet slot has:
  - `x`: learned 1D line position, clamped to `[-1, 1]`.
  - `r`: signed interval radius/intent, clamped to `[-1, 1]`.
- `r > 1/32` means owned-source signal; `r < -1/32` means sink/target signal; otherwise inactive.
- Source/sink pairs match by interval overlap. Narrower intervals receive a precision preference.
- Targets are ranked by accumulated pair strength.
- Decoder supports attack/capture and owned-planet reinforcement.
- Decoder launches are emitted as existing `RawActionC {from_planet_id, angle, ships}` only after C aiming validates the intended target is hit before blockers/sun/OOB. Raw simulator physics stays unchanged.
- Production observations are compact and planet-centric: `872 = 48*18 + 8`.
- `PARITY_TESTING` keeps raw 6484-float observations and parity comparisons intact.

## What Was Done
- Added compact production observation path in C.
- Preserved raw observation parity path under `PARITY_TESTING`.
- Replaced production discrete launch action decoding with interval decoding.
- Added validated C aiming for decoded launches:
  - Static target: analytic direct aim with blocker/sun/OOB validation.
  - Orbiting target: fixed-point/Newton-style time solve plus swept validation.
  - Comet target: path-indexed time solve plus swept validation.
  - Decoder skips launch if no validated intercept exists.
- Added decoder test hooks and focused tests for static aim, blocker rejection/no-launch fallback, orbiting intercept, and comet path aim.
- Updated runtime tests for continuous actions.
- Added `scripts/orbit_wars_local_checks.sh` and saved latest local test logs.
- Added first-pass Python policy deployment adapter.
- Moved Orbit Wars Colab scripts from repo root to `scripts/orbit_wars_colab_*.py`.
- Rebased the working tree contents onto upstream PufferLib source while preserving Orbit Wars-specific files.

## Python Policy Adapter
- Location: `orbit-wars/puffer_agent/policy_adapter.py`.
- Name rationale: this is not a baseline agent and should not live under `producer_agent`. It is a policy adapter for Puffer-trained checkpoints. The current action format is interval-based, but the module name describes its role instead of the implementation detail.
- `compact_features(obs, player_id)` converts a Kaggle observation dict into the same 872-float compact policy observation exposed by the production C env.
- `policy_actions_to_moves(actions, obs, player_id)` converts one 96-float policy action vector into Kaggle moves `[[from_planet_id, angle, ships], ...]`.
- The decoder uses the same current abstraction as C: ascending-id planet slots, `(x, r)` per slot, positive `r` as owned-source intent, negative `r` as sink intent, overlap-based source/target matching, safe source drain, and max 16 launches.
- It is first-pass only. It still needs validated projection and C aiming parity before serious checkpoint evaluation in Kaggle Python.

## Validation Commands
- `PATH=.venv/bin:$PATH bash build.sh orbit_wars --cpu`
  - Builds the production CPU extension.
- `.venv/bin/python -c 'import tests.test_orbit_wars_decoder as t; [getattr(t, n)() for n in dir(t) if n.startswith("test_")]'`
  - Tests interval matching, source/sink behavior, validated static/orbiting/comet aiming, blocker rejection, and no-launch fallback.
- `PYTHONUNBUFFERED=1 .venv/bin/python tests/test_orbit_wars.py`
  - Tests build, vec reset, random continuous stepping, observation range, episode termination, and local throughput.
- `PYTHONUNBUFFERED=1 .venv/bin/python tests/test_orbit_wars_parity.py`
  - Tests raw C physics and raw observations against the Kaggle/Python implementation, including 4-player and comet parity.
- `bash scripts/orbit_wars_local_checks.sh`
  - Intended logged wrapper for the above checks.
- Latest final run: build, decoder tests, runtime suite, and full parity suite passed.

Latest saved logs:
- `logs/orbit_wars_build_cpu.log`
- `logs/orbit_wars_decoder.log`
- `logs/orbit_wars_runtime.log`
- `logs/orbit_wars_parity.log`

## Known Errors / Environment Notes
- Running `bash build.sh orbit_wars --cpu` without `.venv/bin` on `PATH` failed with `python: command not found`.
- Running the build in the sandbox failed because `ccache` writes outside the workspace. It passed with escalation.
- `pytest` is not installed in `.venv`; decoder tests were run by directly invoking test functions.
- Kaggle/LiteLLM emitted network warnings while importing tests; tests still passed.
- Current local runtime after validated aiming: about `4,072` agent-steps/sec in `tests/test_orbit_wars.py` with 64 agents, 1 thread, and dense random continuous actions. This benchmark is intentionally harsh because random actions activate many interval sources/sinks.
- Target is roughly `700k` agent-steps/sec on a rented Vast.ai 5090-class instance. Do not assume current speed is enough; benchmark on that hardware before long training.
- Easiest high-impact speedups without changing public action/obs dimensions:
  - Reduce decoded work: cap decoded launches lower than raw `OW_MAX_ACTIONS_PER_PLAYER=16`, e.g. 2-4 launches/player/step.
  - Top-K filter active source/sink intervals before aiming, or raise the active `r` threshold during early training.
  - Bias policy action head toward noops/small `r` so early random policy is sparse.
  - Reduce `OW_MAX_TARGETS` / `OW_MAX_SOURCES_PER_TARGET` for training decoder only.
  - Use `num_threads > 1`, larger `total_agents`, release/native compiler flags, and profile on the target CPU.
- Most promising speedups while keeping raw parity correct:
  - Keep `c_step_core` unchanged and parity-tested; optimize only decoder/projection/training interface.
  - Add cheap broad-phase caches for source-target visibility/blockers and moving target intercept candidates.
  - Use a staged decoder: cheap top-K pair selection first, validated aiming only for final candidates.
  - Add metrics for launches/step, noop rate, invalid/no-launch rate, capture/reinforce split, and SPS so speed/learning tradeoffs are visible.

## Next Steps
See `todo.md` for concrete implementation instructions. Priority summary:
1. Add projection features using the same validated hit logic so compact observations report truthful incoming ETA/pressure.
2. Improve decoder performance until training SPS is viable; keep raw parity intact and rerun parity after every simulator-touching change.
3. Mirror validated aiming/projection in `orbit-wars/puffer_agent/policy_adapter.py`.
4. Run Colab CPU build/parity/short train, then GPU short train. Functionally ready now; performance may still need tuning before long runs.
5. Evaluate exported checkpoints locally in the original Kaggle environment against random, nearest-sniper, and producer baselines.

## Do Not Reread Unless Needed
- `vendor/**`: external/generated dependency code.
- `orbit-wars/orbit_wars.py`: reference implementation; only reread when debugging C/Python parity or Kaggle semantics.
- `ORBIT_WARS_GAME_RULES.md`: game rules reference; reread only for rule questions.
- Long older root docs (`ORBIT_WARS_CONTEXT.md`, `ORBIT_WARS_TECHNICAL_SPECIFICATION.md`) are superseded for handoff purposes by this file.

## Implementation Commit Scope
Implementation files from this task:
- `ocean/orbit_wars/binding.c`
- `ocean/orbit_wars/orbit_wars.h`
- `tests/orbit_wars_test_lib.c`
- `tests/test_orbit_wars.py`
- `tests/test_orbit_wars_decoder.py`
- `orbit-wars/puffer_agent/policy_adapter.py`
- `orbit-wars/puffer_agent/__init__.py`
- `scripts/orbit_wars_local_checks.sh`
- `scripts/orbit_wars_colab_setup.py`
- `scripts/orbit_wars_colab_build.py`
- `scripts/orbit_wars_colab_parity.py`
- `scripts/orbit_wars_colab_train.py`
- `scripts/orbit_wars_colab_test.py`
- `ORBIT_WARS_HANDOFF.md`
- `todo.md`
