# TODO — Decouple Raw State Parity from Neural Network Observation Scaling

## Goal
Currently, observation normalization and scaling (e.g., dividing ship counts by 1000.0f or coordinates by 100.0f) are hardcoded inside the C simulator's observation generation and mirrored in the Python parity test suite. Any change to the feature scaling for training experiments breaks the parity tests and requires modifying both codebases.

We will decouple them by introducing a raw relative observations buffer in the C struct. The parity tests will assert parity on this raw relative representation, while a separate C function handles the scaling before exposing the data to PufferLib for policy training.

---

## State vs. Observations: What is Checked?
- State: Represents the global, absolute coordinates and physical properties of all entities (e.g., absolute positions of planets/fleets, ship count, owner ID, active state). We verify absolute state in `assert_state_parity` (including physical attributes and parameters like angular velocity).
- Observations: Represents the perspective-relative representation computed per agent (e.g., relative ownership, relative distances, relative headings, total own ships vs total enemy ships). We verify this relative mapping in the observation parity checks.

---

## Decoupled Architecture

### 1. Add raw_observations buffer to OrbitWars Struct
In `ocean/orbit_wars/orbit_wars.h`, add a raw observations buffer to the `OrbitWars` struct definition:
```c
typedef struct {
    // ... existing fields ...
    float raw_observations[4][6484]; // Stores raw, unscaled perspective observations per player
} OrbitWars;
```

### 2. Split Observation Logic in orbit_wars.h
Divide the current `ow_compute_observations` into two distinct steps:
1. `ow_compute_raw_observations(OrbitWars* env)`:
   - Computes perspective-relative values (relative owner, relative coordinates, fleet angles, ship counts, etc.) but stores them **without any normalization scaling** (no divisions by 1000.0f, 5.0f, 100.0f, etc.).
   - Writes the output directly to `env->raw_observations[p]`.
2. `ow_scale_observations(OrbitWars* env)`:
   - Copies `env->raw_observations[p]` to `env->obs_ptr[p]`.
   - Performs the normalization scaling in-place on `env->obs_ptr[p]` (e.g., dividing ship counts by 1000.0f, coordinates by 100.0f, etc.) to match what PufferLib exposes to the neural network for training.
3. Update `c_reset` and `c_step` to run both:
   ```c
   ow_compute_raw_observations(env);
   ow_scale_observations(env);
   ```

### 3. Update ctypes Struct and Parity Tests
1. In `tests/test_orbit_wars_parity.py`, update `OrbitWarsStruct` to include the raw observations buffer:
   ```python
   class OrbitWarsStruct(ctypes.Structure):
       _fields_ = [
           # ... existing fields ...
           ("raw_observations", (ctypes.c_float * OW_OBS_SIZE) * OW_MAX_PLAYERS),
       ]
   ```
2. Remove all scaling divisions from `compute_reference_observation` in the Python test suite to make it output raw unscaled relative values.
3. Update the parity test assertions to compare `c_env.raw_observations[p]` directly against the reference Python observations:
   ```python
   c_raw_obs = np.ctypeslib.as_array(c_env.raw_observations[p])
   assert np.allclose(ref_raw_obs, c_raw_obs, atol=1e-4)
   ```

### 4. Adjust Vector Range Validation Checks
In `tests/test_orbit_wars.py`, adjust `[Test 4] Observation range validation` since the neural network observations will continue to use scaled values in `obs_ptr`, but we must make sure the test target matches our training expectations.

---

## Why this is simple and clean
- Parity tests are completely decoupled: Any change to training scaling factors only requires editing the `ow_scale_observations` function in `orbit_wars.h`.
- The parity test code (`test_orbit_wars_parity.py`) and the reference observation code will never need to be modified when scaling parameters change.
- No Python wrappers or complex routing logic are introduced.
