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
3. `PYTHONUNBUFFERED=1 .venv/bin/python tests/test_orbit_wars_parity.py`
   - Run after touching shared/copied physics logic. The original `orbit_wars` parity target must stay correct.

If build fails with `ccache: Read-only file system`, rerun with escalation/approval.

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

Do not evaluate a lite checkpoint in Kaggle until the Python adapter is updated.

Required adapter work:
1. Update `orbit-wars/puffer_agent/policy_adapter.py` for the lite `848` observation and `30` action contract.
2. Convert Kaggle observations into the same planet/grid/top-fleet layout.
3. Decode the 6 proposals into Kaggle moves with the same nearest-source/nearest-target/ray-validation semantics.
4. Add a tiny local test comparing C lite helper outputs with Python adapter outputs on hand-built states.

Baseline check once adapter exists:

```bash
.venv/bin/python - <<'PY'
from kaggle_environments import make

def run(agent_a, agent_b, seeds=range(20)):
    wins = [0, 0]
    ties = 0
    for seed in seeds:
        env = make("orbit_wars", configuration={"seed": seed}, debug=True)
        env.run([agent_a, agent_b])
        rewards = [s.reward for s in env.steps[-1]]
        if rewards[0] > rewards[1]:
            wins[0] += 1
        elif rewards[1] > rewards[0]:
            wins[1] += 1
        else:
            ties += 1
        print(seed, rewards, [s.status for s in env.steps[-1]])
    print({"agent0_wins": wins[0], "agent1_wins": wins[1], "ties": ties})

run("orbit-wars/puffer_agent/main.py", "orbit-wars/main.py")
PY
```

`orbit-wars/main.py` is the nearest-planet sniper baseline.

## Next Optimization Pass

Highest leverage:
- Add metrics to lite `my_log`: launches/step, noop proposal rate, rejected validation rate, fleets active.
- Profile dense-random actions on target CPU. Local laptop numbers after the latest pass were about `26k` random-action agent-SPS and `100k-146k` noop agent-SPS.
- If random-action decode is still too slow, keep 6 proposal outputs but validate only the top-K positive `send_amount` proposals during early training. Document any cap in this file and config.

Guardrails:
- Keep `orbit_wars_lite` action count `30` and observation size `848` unless explicitly changing the training contract.
- Keep original `orbit_wars` parity tests passing.
- Do not use the old interval `policy_adapter.py` for lite checkpoints.
