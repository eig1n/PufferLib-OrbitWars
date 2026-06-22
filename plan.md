# Orbit Wars PufferLib C Implementation Plan

This document outlines a foolproof, detailed, step-by-step plan to implement the Kaggle Orbit Wars environment in fast, efficient C, compatible with PufferLib 4.0. It details the PufferLib vectorization model, self-play design, interface requirements, parity testing strategy, and remote Google Colab verification.

---

## *IMPORTANT RULE:* NEVER CHANGE THE CORE CODE OF PUFFER LIB, YOU CAN ONLY CREATE NEW FILES TO IMPLEMENT THE ENVIRONEMNT AND TESTS, BUT NEVER CHANGE OR MODIFY THE PUFFER LIB CODE

## 1. Directory and File Reference Overview

When implementing the C environment, refer to the following key files in the codebase for patterns and specifications:

*   **Game Rules & Reference Implementation**:
    *   [orbit-wars/README.md](file:///home/dima/dev/PufferLib-4.0/orbit-wars/README.md): Detailed specifications of planets, fleets, comets, speed equations, turn order, and combat physics.
    *   [orbit-wars/main.py](file:///home/dima/dev/PufferLib-4.0/orbit-wars/main.py): Reference Python agent demonstrating how coordinates, named tuples, and action coordinates are structured.
*   **PufferLib Multi-Agent & Binding References**:
    *   [ocean/target/target.h](file:///home/dima/dev/PufferLib-4.0/ocean/target/target.h): Gold standard template for multi-agent C environments, listing standard structs (`Log`, `Client`), lifecycle functions (`c_reset`, `c_step`, `c_render`, `c_close`), and base pointer mappings.
    *   [ocean/slimevolley/slimevolley.h](file:///home/dima/dev/PufferLib-4.0/ocean/slimevolley/slimevolley.h): Example of a 2-agent simultaneous action environment utilizing PufferLib bindings.
    *   [ocean/chess/chess.h](file:///home/dima/dev/PufferLib-4.0/ocean/chess/chess.h) & [ocean/chess/binding.c](file:///home/dima/dev/PufferLib-4.0/ocean/chess/binding.c): Template for advanced self-play tagging, custom pointer mappings, ELO logging, and swap alignment.
*   **Core PufferLib Vectorization Backend**:
    *   [src/vecenv.h](file:///home/dima/dev/PufferLib-4.0/src/vecenv.h): The C vectorization engine managing memory strides, OMP thread pools, and the compilation configuration boundaries.
    *   [pufferlib/selfplay.py](file:///home/dima/dev/PufferLib-4.0/pufferlib/selfplay.py): The Python self-play permutations (`agent_perm`) and TAG configuration builder.

---

## 2. PufferLib Architecture and Vectorization Model

### A. Flat-Memory Vectorization
PufferLib utilizes flat, contiguous, pre-allocated buffers on CPU or GPU host memory to store observations, actions, rewards, and terminals:
*   `vec->observations`: Flat array of size `total_agents * OBS_SIZE`
*   `vec->actions`: Flat array of size `total_agents * NUM_ATNS`
*   `vec->rewards`: Flat float array of size `total_agents`
*   `vec->terminals`: Flat float array of size `total_agents`

### B. Pointer Permutation (`my_setup_perm`)
PufferLib uses an `agent_perm` array to route observations and actions to different networks (e.g. primary training network vs. frozen historical policies). 
To support this, we must define `MY_USES_PERM` in `binding.c` and implement the routing setup:

```c
void my_setup_perm(StaticVec* vec, Env* env, int slot_base) {
    size_t obs_elem_size = obs_element_size();
    for (int s = 0; s < env->num_agents; s++) {
        int phys = vec->agent_perm ? vec->agent_perm[slot_base + s] : (slot_base + s);
        env->obs_ptr[s]         = (uint8_t*)vec->observations + (size_t)phys * OBS_SIZE * obs_elem_size;
        env->action_mask_ptr[s] = vec->action_mask + (size_t)phys * MY_ACTION_MASK;
        env->action_ptr[s]      = vec->actions + (size_t)phys * NUM_ATNS;
        env->reward_ptr[s]      = vec->rewards + phys;
        env->terminal_ptr[s]    = vec->terminals + phys;
    }
}
```

The C code simulates the game step by reading actions from `env->action_ptr[a]` and writing outputs directly to `env->obs_ptr[a]`, `env->reward_ptr[a]`, and `env->terminal_ptr[a]`.

### C. Perspective-Symmetric Observation Computations
To allow a single network policy to generalize and play from any starting slot, observations must be computed *relative to the observing agent*.
1.  **Loop-Driven Perspective Calculations**: 
    In `compute_observations`, we loop over each observing player `a = 0 .. env->num_agents - 1`. The observation for index `a` is written into `env->obs_ptr[a]`.
2.  **Observer-Relative Owner Normalization**:
    Any object owner ID (planets, fleets) is normalized relative to the observing player `a`:
    *   `0`: Ego (the player `a` itself)
    *   `1..3`: Opponents (`(p_owner - a + num_players) % num_players`)
    *   `-1`: Neutral
3.  **Observer-Relative Feature Computations**:
    If we decide to add player-specific features later (e.g., "distance from planet `X` to the closest planet owned by the player"), we compute this dynamically *relative to observer `a`*:
    ```c
    // Hypothetical observer-relative planet distance feature
    float get_dist_to_closest_owned_planet(OrbitWars* env, int observer_idx, float px, float py) {
        float min_dist = INF;
        for (int i = 0; i < MAX_PLANETS; i++) {
            PlanetC* p = &env->planets[i];
            if (p->active && p->owner == observer_idx) {
                float d = hypotf(px - p->x, py - p->y);
                if (d < min_dist) min_dist = d;
            }
        }
        return min_dist;
    }
    ```
    Because this calculation is parameterized by the observer index `a`, the network always receives a spatially symmetric representation relative to its own assets.

---

## 3. Self-Play Integration

Orbit Wars will train policies for 1v1 and 4v4 separately. 

### A. Environment Tagging & Episode Boundaries
To support training against historical snapshots (managed by `pufferlib/selfplay.py`), the `OrbitWars` struct must declare `int tag` and `int boundary_reached` and opt in via `#define MY_USES_TAGS` in `binding.c`:
*   `tag`: Used by Python to categorize the environment (`0` for selfplay, `>0` representing frozen historical banks).
*   `boundary_reached`: Set to `1` by C when the game terminates. Python uses this to swap frozen opponents on episode boundaries.

When the game ends:
1.  Set all agents' terminals to `1`: `*env->terminal_ptr[i] = 1`.
2.  Set `boundary_reached = 1`.
3.  Call `c_reset(env)` immediately to reset the environment state so the next step can execute seamlessly.

---

## 4. Necessary C Structs (`orbit_wars.h`)

We include all structs required to manage the simulation and Raylib binding.

```c
#define MAX_PLANETS 48
#define MAX_FLEETS 128
#define MAX_COMET_GROUPS 5
#define BOARD_SIZE 100.0f
#define SUN_RADIUS 10.0f
#define ROTATION_RADIUS_LIMIT 50.0f
#define MAX_SPEED 6.0f

// Required PufferLib Log struct. Only use floats!
typedef struct {
    float perf;             // 0-1 normalized performance metric
    float score;            // Unnormalized score
    float episode_return;   // Sum of agent rewards
    float episode_length;   // Length of the episode in ticks
    float n;                // Required count of steps / episodes logged
} Log;

// Struct to store client textures and configurations
typedef struct {
    void* dummy_window_handle; // Stub for drawing
} Client;

typedef struct {
    int id;
    int owner;
    float x;
    float y;
    float radius;
    int ships;
    int production;
    int is_comet;
    int active;
} PlanetC;

typedef struct {
    int id;
    int owner;
    float x;
    float y;
    float angle;
    int from_planet_id;
    int ships;
    float speed;
    int active;
} FleetC;

typedef struct {
    int planet_ids[4];
    int path_index;
    int steps;
    float paths_x[4][100];
    float paths_y[4][100];
    int active;
} CometGroupC;

typedef struct {
    int from_planet_id;
    float angle;
    int ships;
} RawActionC;

typedef struct {
    Log log;
    Client* client;
    
    // Binding Pointers
    float* observations;
    float* actions;
    float* rewards;
    float* terminals;

    // Permissions and Selfplay Tags
    int tag;
    int boundary_reached;
    int slot_for_color[4];

    // Pointer Arrays for Permuted Vectorization
    float* obs_ptr[4];
    unsigned char* action_mask_ptr[4];
    float* action_ptr[4];
    float* reward_ptr[4];
    float* terminal_ptr[4];

    // Core Game State
    PlanetC planets[MAX_PLANETS];
    FleetC fleets[MAX_FLEETS];
    CometGroupC comet_groups[MAX_COMET_GROUPS];
    RawActionC raw_actions[4][16];
    int num_raw_actions[4];

    float angular_velocity;
    int next_fleet_id;
    int next_planet_id;
    int current_step;
    unsigned int rng;
    int num_agents; // 2 or 4
} OrbitWars;
```

---

## 5. Required Lifecycle Functions

Implement the following environment interface functions:

*   `void init(OrbitWars* env)`: Allocates extra memory if needed (in our case, we only initialize structural pointers to NULL).
*   `void c_reset(OrbitWars* env)`: Seeds the RNG, places planets and comets, resets ship counts and ticks, and computes initial observations.
*   `void c_step(OrbitWars* env)`: 
    *   Decodes multidiscrete policy actions from `env->action_ptr[i]` and saves them into `env->raw_actions[i]`.
    *   Calls `c_step_core(env)`.
*   `void c_step_core(OrbitWars* env)`: Performs the actual physics, movement, planet rotation, comet elliptical propagation, combat resolution, and writes outputs to PufferLib buffers.
*   `void c_render(OrbitWars* env)`: Empty stub function.
*   `void c_close(OrbitWars* env)`: Frees any references.

---

## 6. Parity Testing via Direct Raw Actions

We will bypass discrete action decoding during parity testing to test the physics of the simulator directly against Kaggle.

### A. Python Parity Test Setup (`tests/orbit_wars_parity.py`)
We set up a python script that instantiates both the Kaggle environment and the compiled PufferLib C environment:

```python
from kaggle_environments import make
import pufferlib
import ctypes
import numpy as np

# Load compiled C extension
cmod = pufferlib.environments.load("orbit_wars_1v1") # or 4v4
args = {
    "vec": {"total_agents": 2, "num_buffers": 1, "num_threads": 1},
    "env": {}
}
vec = cmod.create_vec(args, 0)

# Instantiate Kaggle env
kaggle_env = make("orbit_wars", configuration={"seed": 42})
kaggle_env.reset()

# helper to access raw C memory structure
class RawActionStruct(ctypes.Structure):
    _fields_ = [("from_planet_id", ctypes.c_int),
                ("angle", ctypes.c_float),
                ("ships", ctypes.c_int)]

class OrbitWarsStruct(ctypes.Structure):
    # Map fields aligning with C memory layout to allow direct state writes
    pass
```

### B. State Injection and Execution Loop
At the start of the test, we copy the exact planet positions, comets, and angular velocities from the Kaggle environment's observation dictionary directly into the C struct pointer.

For 500 steps:
1.  Obtain actions from reference agents in Python (represented as `[[from_planet_id, angle, ships], ...]`).
2.  Write these raw actions directly into the C environment's `raw_actions` array:
    ```python
    # Example using ctypes to write raw actions to agent p
    c_env_ptr = ctypes.cast(vec.env_ptr, ctypes.POINTER(OrbitWarsStruct))
    c_env_ptr.contents.num_raw_actions[p] = len(kaggle_actions)
    for idx, (from_id, angle, ships) in enumerate(kaggle_actions):
        c_env_ptr.contents.raw_actions[p][idx].from_planet_id = from_id
        c_env_ptr.contents.raw_actions[p][idx].angle = angle
        c_env_ptr.contents.raw_actions[p][idx].ships = ships
    ```
3.  Step both environments:
    *   In Kaggle: `kaggle_env.step(actions)`
    *   In C: Call `c_step_core` directly via ctypes or custom bound method.
4.  Assert that after each step, all planet coordinates (`atol=1e-5`), ship counts, owner IDs, active fleets, and comets match exactly.

---

## 7. Remote Google Colab Setup (CLI Instructions)

### Step 1: Create a GitHub Repository
```bash
git init (if not done already)
git add .
git commit -m "Add Orbit Wars C environment and parity tests"

gh repo create PufferLib-OrbitWars --public --source=. --remote=origin --push
```

### Step 2: Create a Colab Runner Script
Create `colab_test.py` locally, an example but *don't forget logging* also, include steps per second for our C implementation:
```python
# colab_test.py
import subprocess
import os

print("--- Cloning codebase ---")
subprocess.run(["git", "clone", "https://github.com/eig1n/Puffer-OrbitWars.git", "orbit_wars"], check=True)
os.chdir("orbit_wars")

print("--- Installing uv ---")
subprocess.run("curl -LsSf https://astral.sh/uv/install.sh | sh", shell=True, check=True)
os.environ["PATH"] += os.pathsep + os.path.expanduser("~/.local/bin")

print("--- Installing dependencies ---")
subprocess.run(["uv", "pip", "install", "--system", "kaggle-environments>=1.28.0", "pybind11", "numpy", "rich"], check=True)

print("--- Testing 1v1 parity ---")
subprocess.run(["bash", "build.sh", "orbit_wars_1v1", "--cpu"], check=True)
subprocess.run(["python3", "tests/orbit_wars_parity.py", "--env", "1v1"], check=True)

print("--- Testing 4v4 parity ---")
subprocess.run(["bash", "build.sh", "orbit_wars_4v4", "--cpu"], check=True)
subprocess.run(["python3", "tests/orbit_wars_parity.py", "--env", "4v4"], check=True)

print("--- All tests completed successfully! ---")
```

### Step 3: Run Remotely
```bash
colab new
colab exec -f colab_test.py
# Do not forget to download a log from vm using colab download NAME_OF_THE_FILE_ON_REMOTE_VM LOCAL_NAME (For easiest use make the names the same)
# then just
colab stop
```
