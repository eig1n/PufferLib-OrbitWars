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

#### 3. Run Google Colab Verification (From Local Machine) (Not necessary to do that unless want to test for speed or higher workloads for tests)
The Colab setup and test scripts are decoupled to prevent cell execution timeouts. Run them in order:
```bash
# 1. Start a new Colab session and install dependencies
colab new
colab exec -f colab_setup.py

# 2. Compile latest changes and run Vector/Benchmark checks (saves to colab_build_run.log)
colab exec -f colab_build.py 2>&1 | tee colab_build_run.log

# 3. Run full physical and observation parity verification (saves to colab_parity_run.log)
colab exec -f colab_parity.py 2>&1 | tee colab_parity_run.log
```

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

- Physics and Observation Parity: 100% achieved. The C simulator has been mathematically verified against Python on multiple seed rollouts, 22 custom scenarios, and 4 ported symmetry tests. All tests pass successfully.
- Execution Performance: Achieving approximately 143,000 agent-steps/sec on CPU vectors.
- Git State: Git tracking is set up with remote branch main at github.com:eig1n/PufferLib-OrbitWars.git.

---

## 3. Roadmap of Next Tasks

Immediate upcoming missions:

### Mission A: Correctness, Quality, and Efficiency Review
- Goal: Audit the C environment implementation for code quality, architectural efficiency, and potential edge-case mismatches with the Python reference.
- Areas to inspect:
  - Review ocean/orbit_wars/orbit_wars.h for memory leaks, buffer safety, and math optimization.
  - Check continuous swept-pair hit calculations (ow_swept_pair_hit) for correct float bounds.
  - Make sure array constraints (MAX_PLANETS, MAX_FLEETS) are not overflowed during high-army runs.

### Mission B: Historical Self-Play Audit and Integration
- Goal: Verify that self-play matchmaking and Opponent swapping function correctly at turn boundaries.
- Areas to inspect:
  - Check the selfplay settings in config/orbit_wars.ini (enabled = 1, swap_winrate, min_games).
  - Inspect ocean/orbit_wars/binding.c to see how agent permutations are mapped in my_setup_perm and how #define MY_USES_TAGS interacts with env->tag.
  - Verify that env->boundary_reached is set to 1 when the episode finishes, and that the state immediately triggers a clean reset.

### Mission C: Decoupling Parity Checks from Observation Scaling
- Goal: Currently, observation scaling (e.g. division of ship counts by 1000.0) is hardcoded inside both the C engine and Python test suites. Any experimental change to scaling breaks the parity tests. We must refactor the parity checks to test raw unscaled state/observations, and move normalization into a separate feature engineering layer.
- Instruction Guide: A detailed step-by-step refactoring plan has been written in [ORBIT_WARS_TODO.md](file:///home/dima/dev/PufferLib-4.0/ORBIT_WARS_TODO.md). Read this file to begin this task.

### Mission D: Policy Training
- Goal: Start and evaluate reinforcement learning policy training on CPU/GPU.
- Areas to look:
  - Set the player configuration in config/orbit_wars.ini (e.g. num_agents = 2 for 1v1, num_agents = 4 for 4v4).
  - Adjust vector dimensions (total_agents under [vec]) based on hardware memory availability.
  - Run training using the command: puffer train orbit_wars.

---

## 4. Core Reference Documents

For deeper details, consult these specification files located in the root directory:
1. [ORBIT_WARS_GAME_RULES.md](file:///home/dima/dev/PufferLib-4.0/ORBIT_WARS_GAME_RULES.md): Master reference for game design, orbit dynamics, speed scaling curves, comet spawns, and combat resolution math.
2. [ORBIT_WARS_TECHNICAL_SPECIFICATION.md](file:///home/dima/dev/PufferLib-4.0/ORBIT_WARS_TECHNICAL_SPECIFICATION.md): Master technical reference for memory structures, ctypes mapping, turn phases sequence, swept-pair checks, observation layout indices, and build/run command cheat sheets.
3. [ORBIT_WARS_TODO.md](file:///home/dima/dev/PufferLib-4.0/ORBIT_WARS_TODO.md): Walkthrough and todo list for the observation scaling decoupling task.
