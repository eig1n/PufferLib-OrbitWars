#define _DEFAULT_SOURCE
#include "ocean/orbit_wars/orbit_wars.h"

int get_sizeof_orbit_wars() {
    return sizeof(OrbitWars);
}

void test_compute_observations(OrbitWars* env) {
    ow_compute_observations(env);
}

float test_interval_pair_strength(float xs, float rs, float xt, float rt) {
    return ow_interval_pair_strength(xs, rs, xt, rt);
}

void test_planet_slots_by_id(OrbitWars* env, int* out_slots) {
    ow_planet_slots_by_id(env, out_slots);
}

int test_decode_interval_actions_for_slot(OrbitWars* env, int slot, const float* actions) {
    for (int p = 0; p < OW_MAX_PLAYERS; p++) env->num_raw_actions[p] = 0;
    return ow_decode_interval_actions_for_slot(env, slot, actions);
}

int test_aim_angle_to_planet(OrbitWars* env, int src_idx, int tgt_idx, int ships, double* out_angle) {
    float angle = 0.0f;
    int ok = ow_aim_angle_to_planet(env, src_idx, tgt_idx, ships, &angle);
    if (out_angle) *out_angle = (double)angle;
    return ok;
}

int test_validate_launch_angle(OrbitWars* env, int src_idx, int tgt_idx, int ships, double angle) {
    return ow_validate_launch_angle(env, src_idx, tgt_idx, ships, (float)angle, NULL);
}
