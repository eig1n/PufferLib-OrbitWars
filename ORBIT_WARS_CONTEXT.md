# AI Agent Onboarding Context: Orbit Wars PufferLib Environment

This document serves as the complete entry point and context map for any AI coding agent starting a new task or resuming development on the Orbit Wars environment.

---
## 0. Dev env related stuff

- using uv everywhere
- using ssh for remote git stuff, but you don't have to worry about that you can just git push origin main, or I will do it manually

### Build & Run Command Cheat Sheet

#### 1. Build PufferLib C Environment (Local Machine)
```bash
# Compile CPU backend
bash build.sh orbit_wars --cpu
```

#### 2. Run Test Suites (Local Machine)
```bash
# Run PufferLib Vectorization and Benchmark Suite
.venv/bin/python tests/test_orbit_wars.py

# Run C vs Python Parity Suite
.venv/bin/python tests/test_orbit_wars_parity.py
```

#### 3. Run Google Colab Verification (From Local Machine)
The Colab setup and test scripts are decoupled to prevent cell execution timeouts. Run them in order:
```bash
# 1. Start a new Colab session and install dependencies
colab new
colab exec -f colab_setup.py

# 2. Compile latest changes and run Vector/Benchmark checks (saves to colab_build_run.log)
colab exec -f colab_build.py 2>&1 | tee colab_build_run.log

# 3. Run full physical and observation parity verification (saves to colab_parity_run.log)
colab exec -f colab_parity.py 2>&1 | tee colab_parity_run.log

# 4. Run RL policy training verification (saves to colab_train_run.log)
colab exec -f colab_train.py 2>&1 | tee colab_train_run.log
```

##### Optional Weights & Biases (WandB) Logging
To log training metrics to WandB on Colab:
1. Create a `.env` file in the root of the project (already ignored by `.gitignore`).
2. Add your API key:
   ```env
   WANDB_API_KEY=your_actual_wandb_api_key
   ```
3. When you run `colab exec -f colab_train.py`, the setup script will install `wandb` and the training runner will automatically log in and enable the `--wandb` flag.

## 1. Codebase Directory Map

The structural layout of the repository and what to look for in each file:

### Core Simulator and Bindings
- [ocean/orbit_wars/orbit_wars.h](file:///home/dima/dev/PufferLib-4.0/ocean/orbit_wars/orbit_wars.h): The core C simulation engine. Contains struct definitions (OrbitWars, PlanetC, FleetC, CometGroupC), turn phase execution functions (c_step_core, movement, continuous swept-pair collision, production, combat), and observation builders.
- [ocean/orbit_wars/binding.c](file:///home/dima/dev/PufferLib-4.0/ocean/orbit_wars/binding.c): PufferLib 4.0 C-binding layer. Contains memory permutation mapping (my_setup_perm), player slot randomization, self-play tagging configurations, and metrics export logging (my_log).

### Original Python Reference
- [orbit-wars/orbit_wars.py](file:///home/dima/dev/PufferLib-4.0/orbit-wars/orbit_wars.py): The original reference Python kaggle_environments Orbit Wars implementation. Contains reference physics calculations, comet path equations, and combat resolution rules.
- [orbit-wars/main.py](file:///home/dima/dev/PufferLib-4.0/orbit-wars/main.py): Reference agent demonstrating the action coordinate/angle representation and state parsing.

### Verification and Test Suites
- [tests/test_orbit_wars.py](file:///home/dima/dev/PufferLib-4.0/tests/test_orbit_wars.py): Standard PufferLib environment checks. Contains environment vectorization, smoke stepping, observation range checks, termination validations, and performance benchmarks.
- [tests/test_orbit_wars_parity.py](file:///home/dima/dev/PufferLib-4.0/tests/test_orbit_wars_parity.py): The C vs. Python mathematical parity suite. Contains single-step state injection comparisons, 500-step rollout parity checks, custom edge-case scenarios (22 tests), and ported rotational symmetry tests.

### Configuration and Colab Scripts
- [config/orbit_wars.ini](file:///home/dima/dev/PufferLib-4.0/config/orbit_wars.ini): Training hyperparameters, self-play settings, and vector dimensions.
- [colab_setup.py](file:///home/dima/dev/PufferLib-4.0/colab_setup.py): Installs package dependencies on remote Colab VMs.
- [colab_build.py](file:///home/dima/dev/PufferLib-4.0/colab_build.py): Compiles the C extension and runs standard vector tests under 30s.
- [colab_parity.py](file:///home/dima/dev/PufferLib-4.0/colab_parity.py): Runs the complete C vs. Python parity test suite under 30s.

---

## 2. Current Project Status

- Physics and Observation Parity: 100% achieved and decoupled. The C simulator has been mathematically verified against Python on multiple seed rollouts, 22 custom scenarios, and 4 ported symmetry tests. Observation scaling is fully decoupled (Mission C complete): raw unscaled observations are verified for parity, and scaling/normalization runs in a separate feature engineering pass.
- Execution Performance: Optimizations from Mission A (precomputing planet/comet projected coordinates, precalculating player ship totals, direct scaled observation pass, and memset zero-clearing) keep execution extremely fast, achieving ~118,000 agent-steps/sec on Colab CPU environments and ~143,000 agent-steps/sec on local setups.
- Git State: Git tracking is set up with remote branch main at github.com:eig1n/PufferLib-OrbitWars.git.

---

## 3. Roadmap of Next Tasks

### DONE: Mission A: Correctness, Quality, and Efficiency Review
- Goal: Audit and optimize the C environment implementation for memory layout and simulation execution speed.
- Completed:
  - Precomputed projected planet and comet positions inside the movement phase (`next_px`/`next_py`) to avoid redundant trigonometric calculations inside nested fleet checks.
  - Precalculated total player ship counts and fleet aggregates once at step start, avoiding redundant iterations during individual agent observations.
  - Implemented `ow_compute_and_scale_observations` to write scaled outputs directly into target memory buffers without copying, with upfront `memset` zero-clears.

### DONE: Mission B: Historical Self-Play Audit and Integration
- Goal: Integrate and test self-play matchmaking configurations and policy-bank logging.
- Completed:
  - Extended the `Log` struct and `binding.c` to support per-bank historical metrics (`hist_score_bank_0` through `hist_score_bank_7` and counts).
  - Wired game over scoring to log primary agent rewards against the opponent bank tagged in `env->tag` by PufferLib's self-play system.
  - Verified that `boundary_reached = 1` is correctly set at turn termination to notify the PufferLib framework for opponent swaps.

### DONE: Mission C: Decoupling Parity Checks from Observation Scaling
- Goal: Separate the core simulation state and raw observation builder from the neural network scaling and normalization.
- Completed: Refactored parity checks to assert exact match on raw unscaled features, moving division/scaling constants into a dedicated post-simulation pass (`ow_process_observations`).

### Mission D: Policy Training
- Goal: Start and evaluate reinforcement learning policy training on CPU/GPU.
- Status: Verified training loops on remote CPU via `colab_train.py` with scaled-down network dimensions (`hidden_size = 32`, `num_layers = 1`) and `--slowly` configuration. Ready for large-scale GPU/CPU setups.

---

## 4. Core Reference Documents

For deeper details, consult these specification files located in the root directory:
1. [ORBIT_WARS_GAME_RULES.md](file:///home/dima/dev/PufferLib-4.0/ORBIT_WARS_GAME_RULES.md): Master reference for game design, orbit dynamics, speed scaling curves, comet spawns, and combat resolution math.
2. [ORBIT_WARS_TECHNICAL_SPECIFICATION.md](file:///home/dima/dev/PufferLib-4.0/ORBIT_WARS_TECHNICAL_SPECIFICATION.md): Master technical reference for memory structures, ctypes mapping, turn phases sequence, swept-pair checks, observation layout indices, and build/run command cheat sheets.
3. [ORBIT_WARS_TODO.md](file:///home/dima/dev/PufferLib-4.0/ORBIT_WARS_TODO.md): Walkthrough and todo list for the observation scaling decoupling task.
