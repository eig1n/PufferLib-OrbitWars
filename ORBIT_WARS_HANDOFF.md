# Orbit Wars Handoff

## Current Goal
Implement the initial 1v1 fast training interface for Orbit Wars:
- Keep C simulator physics and raw Kaggle-style parity path intact.
- Use compact planet-centric production observations for training.
- Use all-continuous interval actions: one `(x, r)` pair per canonical planet slot.
- Start with 1v1 training; 4-player parity support remains in tests.

## Important Files
- `ocean/orbit_wars/orbit_wars.h`: Core C simulator, game state, turn phases, observation builders, interval action decoder, raw-action physics path.
- `ocean/orbit_wars/binding.c`: PufferLib binding constants and pointer setup. Production build currently exposes `OBS_SIZE=872`, `NUM_ATNS=96`, `ACT_SIZES={1...}`. `PARITY_TESTING` keeps `OBS_SIZE=6484`.
- `tests/test_orbit_wars.py`: Local vector/runtime/range/termination/perf check. Now emits continuous random actions when all action sizes are `1`.
- `tests/test_orbit_wars_parity.py`: C vs Python physics/raw-observation parity suite. Compiles helper with `-DPARITY_TESTING`.
- `tests/orbit_wars_test_lib.c`: C helper exports for parity and decoder tests.
- `tests/test_orbit_wars_decoder.py`: Focused direct decoder assertions for slot order, overlap, signs, multi-source capture, reinforcement, clamping, and noops.
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
  - `colab_setup.py`
  - `colab_build.py`
  - `colab_parity.py`
  - `colab_train.py`

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
- Launches are emitted as existing `RawActionC {from_planet_id, angle, ships}` so simulator physics stays unchanged.
- Production observations are compact and planet-centric: `872 = 48*18 + 8`.
- `PARITY_TESTING` keeps raw 6484-float observations and parity comparisons intact.

## What Was Done
- Added compact production observation path in C.
- Preserved raw observation parity path under `PARITY_TESTING`.
- Replaced production discrete launch action decoding with interval decoding.
- Added simple deterministic aiming for static/orbiting/comet targets.
- Added decoder test hooks and focused decoder test file.
- Updated runtime tests for continuous actions.
- Added `scripts/orbit_wars_local_checks.sh` and saved latest local test logs.
- Added first-pass Python policy deployment adapter.

## Python Policy Adapter
- Location: `orbit-wars/puffer_agent/policy_adapter.py`.
- Name rationale: this is not a baseline agent and should not live under `producer_agent`. It is a policy adapter for Puffer-trained checkpoints. The current action format is interval-based, but the module name describes its role instead of the implementation detail.
- `compact_features(obs, player_id)` converts a Kaggle observation dict into the same 872-float compact policy observation exposed by the production C env.
- `policy_actions_to_moves(actions, obs, player_id)` converts one 96-float policy action vector into Kaggle moves `[[from_planet_id, angle, ships], ...]`.
- The decoder uses the same current abstraction as C: ascending-id planet slots, `(x, r)` per slot, positive `r` as owned-source intent, negative `r` as sink intent, overlap-based source/target matching, safe source drain, and max 16 launches.
- It is first-pass only. It still needs validated projection and aiming parity before serious checkpoint evaluation.

## Commands Already Tried
- `PATH=.venv/bin:$PATH bash build.sh orbit_wars --cpu`
- `.venv/bin/python -c 'import tests.test_orbit_wars_decoder as t; [getattr(t, n)() for n in dir(t) if n.startswith("test_")]'`
- `.venv/bin/python tests/test_orbit_wars.py`
- `.venv/bin/python tests/test_orbit_wars_parity.py`
- `bash scripts/orbit_wars_local_checks.sh` was syntax-checked only; the individual commands above were run and logged.

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
- Current runtime performance after compact interface was about 13k agent-steps/sec in `tests/test_orbit_wars.py` on this local run.

## Next Steps
1. Improve engineered projection accuracy:
   - Static planet impact: analytic ray-circle time.
   - Orbiting planet impact: broad-phase plus fixed-iteration root solve and swept validation.
   - Comets: path-index future positions with segment validation.
   - Ignore low-confidence fleet target estimates.
2. Upgrade aiming validation:
   - Static target: direct angle plus blocker validation.
   - Orbiting target: fastest valid intercept with fixed-point/Newton iterations and swept validation.
   - Comet target: path-indexed future position and validation.
   - Skip launches with no validated intercept.
3. Tighten Python deployment mirror:
   - `orbit-wars/puffer_agent/policy_adapter.py` currently mirrors dimensions/features/decoder at a first-pass level.
   - It still needs the same validated projection and aiming semantics as C before checkpoint evaluation.
4. Run Colab CPU checks:
   - Use `uv`/`.venv`.
   - Run `colab_build.py`, `colab_parity.py`, `colab_train.py`.
   - Use `selfplay.enabled=0`, small `total_agents`, and forced checkpoint save.
5. Run short Colab GPU 1v1 train.
6. Download latest `checkpoints/orbit_wars/**/*.bin`.
7. Evaluate checkpoint in original Kaggle Python environment against random, nearest-sniper, and producer baselines.
8. Track winrate, terminal score, invalid/noop rate, launches per step, and capture/reinforce split.

## Do Not Reread Unless Needed
- `vendor/**`: external/generated dependency code.
- `puffer/**`: Puffertank utility files; unrelated to Orbit Wars interface work.
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
- `ORBIT_WARS_HANDOFF.md`
