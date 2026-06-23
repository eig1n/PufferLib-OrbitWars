# AI Agent Context — Orbit Wars PufferLib Environment

Welcome! If you are an AI coding agent resuming development or starting a new task on the Orbit Wars environment, **this document serves as your complete entry point and context map.**

---

## 🗺️ Codebase File Directory Map

Here is where the various components live and what you should look for in each file:

### Core Simulator
- **[ocean/orbit_wars/orbit_wars.h](file:///home/dima/dev/PufferLib-4.0/ocean/orbit_wars/orbit_wars.h)**: Contains the core C simulator engine. Look here for game state definitions (`OrbitWars`, `PlanetC`, `FleetC`, `CometGroupC`), turn execution phases (movement, continuous swept-pair collision, production, combat, game-over checks), and observation calculation.
- **[ocean/orbit_wars/binding.c](file:///home/dima/dev/PufferLib-4.0/ocean/orbit_wars/binding.c)**: PufferLib 4.0 C-binding layer. Look here for memory routing (`my_setup_perm`), player permutations for self-play matchmaking, and environment tag configurations.

### Training Configuration
- **[config/orbit_wars.ini](file:///home/dima/dev/PufferLib-4.0/config/orbit_wars.ini)**: Self-play training options. Look here to configure training dimensions, player count (1v1 vs. 4v4), and parallel worker thread counts.

### Verification and Parity Test Suites
- **[tests/test_orbit_wars.py](file:///home/dima/dev/PufferLib-4.0/tests/test_orbit_wars.py)**: PufferLib standard vectorization, smoke stepping, observation range, and benchmark runner.
- **[tests/test_orbit_wars_parity.py](file:///home/dima/dev/PufferLib-4.0/tests/test_orbit_wars_parity.py)**: C vs. Python parity verification suite. Contains single-step state injections, independent 500-step rollout comparisons, and unit scenario testing.

### Google Colab Runners (Decoupled)
- **[colab_setup.py](file:///home/dima/dev/PufferLib-4.0/colab_setup.py)**: Clones the repository and performs one-time package installation on Colab.
- **[colab_build.py](file:///home/dima/dev/PufferLib-4.0/colab_build.py)**: Pulls latest commits, compiles the environment, and runs environment tests.
- **[colab_parity.py](file:///home/dima/dev/PufferLib-4.0/colab_parity.py)**: Runs the parity checks using the pre-compiled C library.

---

## 📖 Key Specifications and Next Steps

Before you begin writing code, read the following files:

1. **[ORBIT_WARS_TECHNICAL_SPECIFICATION.md](file:///home/dima/dev/PufferLib-4.0/ORBIT_WARS_TECHNICAL_SPECIFICATION.md)**: 
   Read this to understand the physics engine, memory structure packing, non-linear fleet speeds, continuous swept-pair checks, perspective observations, ELO scoring, and local/Colab command cheat sheets.
2. **[ORBIT_WARS_TODO.md](file:///home/dima/dev/PufferLib-4.0/ORBIT_WARS_TODO.md)**:
   Read this to review your immediate next mission: refactoring observation scaling to decouple physics verification from neural network feature engineering.

---

## 🚀 Status Summary
- **Verification**: The C simulator has been fully verified for 100% mathematical parity against Python across multiple seeds and custom scenarios. All local and Colab builds/smoke tests pass (`✅ ALL TESTS PASSED`).
- **Performance**: The simulator achieves **~143,000 agent-steps/sec** on CPU vectors.
- **Repository**: Code is pushed and tracked at [https://github.com/eig1n/PufferLib-OrbitWars](https://github.com/eig1n/PufferLib-OrbitWars).
