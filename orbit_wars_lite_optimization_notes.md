# Orbit Wars Lite Optimization Notes

Scope: implementation-only speedups that keep the lite public contract intact unless a separate task explicitly changes it. Decoder validation optimizations are omitted here because the current validated aim-point decoder should be replaced with the simpler intended lite action semantics.

## Highest-Leverage Fixed-Cost Work

1. DONE: Cache sorted planet slots once per env step.
   - Observation code no longer recomputes ID-sorted planet slots per player with the branchy `O(P^3)` helper.
   - `EnvCache` stores `planet_slots[48]` and rebuilds on step/signature change.
   - Reset invalidates the cache; the active/id signature protects direct test mutations in the same step.

2. Track active fleets explicitly.
   - Current movement and observation paths scan all `1024` fleet slots.
   - Maintain `active_fleet_indices[]` and `num_active_fleets`, or rebuild once per step and reuse.
   - Use it for movement, ship totals, fleet grid, top fleets, game-over asset checks, and terminal scoring.

3. DONE: Add no-fleet fast paths.
   - Fleet movement skips slot scans before any launch and when no active fleets remain.
   - Observation building skips the fleet-slot scan before the first launch.
   - If `num_active_fleets == 0`, lite observations skip fleet-grid and clean-fleet work; the zeroed obs buffer represents empty fleet features.
   - Normal movement/observation scans are bounded by `min(next_fleet_id, OW_MAX_FLEETS)` before all fleet slots have ever been used.

4. PARTIAL: Avoid repeated per-player observation work.
   - Fleet grid summaries are built once per observation pass, then converted into each player-relative view.
   - Planet slot sorting is cached once per step.
   - Remaining candidate: precompute player-independent planet feature scalars if profiling still points at observation construction.

## Fleet Collision Broadphase

5. Add swept AABB rejection before exact fleet-planet collision.
   - For each active fleet segment, compute a segment AABB.
   - For each active planet swept segment, compute an expanded AABB by planet radius.
   - If AABBs do not overlap, skip expensive swept-circle math.
   - This preserves exact collision semantics.

6. Consider a spatial grid for planets only if AABB is not enough.
   - Build a small per-step grid from swept planet AABBs.
   - Query only candidate cells touched by each fleet segment.
   - To preserve current priority behavior, collect candidate planet indices and process them in ascending planet index before exact collision checks.

7. Reuse next-position planet data.
   - Movement currently computes projected next positions, and rotation/comet code also updates related positions.
   - Cache per-step `planet_next_x/y` and active/in-board flags.

## Memory And Reset Costs

8. Reduce large clears when safe.
   - `arriving_ships` is small and fine to clear.
   - Avoid clearing/copying larger cached arrays by using generation counters where practical.
   - Keep reset logic simple unless profiling shows it matters.

9. Keep observations as `848` floats for now, but make construction cheaper.
   - Raw memory bandwidth for 848 floats is not the main issue on modern CPUs.
   - The slow part is repeated summary construction, sorting, slot scans, clamps, and branch-heavy loops.

## Metrics To Add Before Bigger Rewrites

10. Add lite perf counters to `Log` / `my_log`.
    - Active fleets.
    - Launches per step.
    - Positive action proposals.
    - Accepted launches.
    - Episode length.
    - Optional: collision pair checks and AABB rejects during profiling builds.

11. Benchmark three modes after each pass.
    - Noop actions: fixed simulation/observation floor.
    - Dense random actions: worst-case exploration and launch pressure.
    - Trained policy actions: realistic production speed.

## Guardrails

- Keep raw `orbit_wars` parity untouched.
- Keep lite Kaggle adapter parity updated after any lite contract change.
- Prefer exact broadphase skips over approximate physics shortcuts.
- Document any intentional lite divergence in `todo_lite.md`.
