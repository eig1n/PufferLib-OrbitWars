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
