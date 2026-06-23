# TODO — Decouple Raw State Parity from Neural Network Observation Scaling

## 🎯 Goal
Currently, observation normalization and scaling (such as dividing ship counts by `1000.0f` or planet radius by `5.0f`) are hardcoded directly inside the C simulator's `ow_compute_observations` function and mirrored in the Python test suite's `compute_reference_observation` function. 

This coupling means any experiment with a new feature representation or scaling factor (e.g., using log scaling or a different divisor) requires modifying both the C engine and the Python parity tests.

We need to **decouple the physical simulator logic/state verification from the neural network observation scaling layer**. Parity tests should only assert the raw state, while the feature scaling should live in a separate, easily configurable layer.

---

## 🛠️ Proposed Architecture

### 1. Define a "Raw State Observation"
The core C engine should output observations containing only **raw physical values** without any normalization:
- Positions: raw float coordinates `x`, `y` (e.g., in `[0.0, 100.0]`)
- Sizes: raw float radius (e.g., `10.0`, `1.0`, etc.)
- Armies: raw integer ship counts (no `/ 1000.0f`)
- Production: raw integer rates (no `/ 5.0f`)
- Timesteps: raw integer current step (no `/ 500.0f`)

### 2. Update Parity Verification to Test Raw State
- The parity test suite ([test_orbit_wars_parity.py](file:///home/dima/dev/PufferLib-4.0/tests/test_orbit_wars_parity.py)) will compare these raw C observations directly against the reference Python observations.
- This ensures the parity assertions check the *physics* correctness, and will remain 100% stable regardless of how you choose to scale inputs for model training.

### 3. Implement a Separate Feature Scaling Layer
Create a modular feature engineering/scaling function (or class wrapper):
- **Option A (C-side scaling function)**: Define a wrapper function in [orbit_wars.h](file:///home/dima/dev/PufferLib-4.0/ocean/orbit_wars/orbit_wars.h) (e.g., `ow_engineer_features`) that copies raw state observations to the final scaled/normalized float array exposed to PufferLib.
- **Option B (Python wrapper)**: Perform the scaling in Python before passing observations to the neural network.

---

## 🔍 Code Walkthrough: What to Modify

### File 1: [ocean/orbit_wars/orbit_wars.h](file:///home/dima/dev/PufferLib-4.0/ocean/orbit_wars/orbit_wars.h)
1. **Locate `ow_compute_observations`**:
   Find where observation arrays are populated:
   ```c
   static void ow_compute_observations(OrbitWars* env) { ... }
   ```
2. **Remove Scaling**:
   Remove divisors and normalization math. For example:
   - Change `pl->x / OW_BOARD_SIZE` to `pl->x`.
   - Change `(float)pl->ships / 1000.0f` to `(float)pl->ships`.
   - Change `env->angular_velocity / 0.05f` to `env->angular_velocity`.
3. **Add `ow_engineer_features`**:
   If using C-side scaling, implement it at the end of the observation loop to populate the final buffer exposed via `env->obs_ptr[a]`.

### File 2: [tests/test_orbit_wars_parity.py](file:///home/dima/dev/PufferLib-4.0/tests/test_orbit_wars_parity.py)
1. **Locate `compute_reference_observation`**:
   Remove matching scaling divisors from the reference observations:
   ```python
   def compute_reference_observation(c_env, player_id, num_agents):
       # Remove all divisions (/ 1000.0, / 5.0, / OW_BOARD_SIZE)
   ```
2. **Verify Check Bounds**:
   Update `np.allclose(ref_obs, c_obs_arr, atol=1e-4)` to run on raw values.

### File 3: [tests/test_orbit_wars.py](file:///home/dima/dev/PufferLib-4.0/tests/test_orbit_wars.py)
1. **Locate `[Test 4] Observation range validation`**:
   Adjust the range validation check since raw observations (e.g., ship counts, coordinates) will now exceed the standard `[-5.0, 5.0]` bounding box.

---

## 🚀 How to Verify
After refactoring:
1. Run local environment tests:
   ```bash
   .venv/bin/python tests/test_orbit_wars.py
   ```
2. Run local parity tests:
   ```bash
   .venv/bin/python tests/test_orbit_wars_parity.py
   ```
3. Run Colab verification runners:
   ```bash
   colab exec -f colab_build.py
   colab exec -f colab_parity.py
   ```
   All checks must pass without any assertion errors.
