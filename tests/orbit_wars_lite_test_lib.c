#include "ocean/orbit_wars_lite/orbit_wars.h"

int get_sizeof_orbit_wars_lite() {
    return sizeof(OrbitWars);
}

int test_lite_obs_size() {
    return OW_OBS_SIZE;
}

int test_lite_num_atns() {
    return OW_NUM_ATNS;
}

int test_lite_amount_to_ships(float intent, int available) {
    return ow_lite_amount_to_ships(intent, available);
}

int test_decode_lite_actions_for_slot(OrbitWars* env, int slot, const float* act) {
    return ow_decode_lite_actions_for_slot(env, slot, act);
}

void test_compute_observations_for_slot(OrbitWars* env, int a, float* out_obs) {
    int na = env->num_agents;
    int total_ships[OW_MAX_PLAYERS] = {0};
    int sum_all_ships = 0;
    for (int p = 0; p < OW_MAX_PLANETS; p++) {
        PlanetC* pl = &env->planets[p];
        if (pl->active && pl->owner >= 0 && pl->owner < na) {
            total_ships[pl->owner] += pl->ships;
        }
    }
    for (int f = 0; f < OW_MAX_FLEETS; f++) {
        FleetC* fl = &env->fleets[f];
        if (fl->active && fl->owner >= 0 && fl->owner < na) {
            total_ships[fl->owner] += fl->ships;
        }
    }
    for (int p = 0; p < na; p++) {
        sum_all_ships += total_ships[p];
    }
    ow_compute_and_scale_observations(env, a, out_obs, total_ships, sum_all_ships);
}
