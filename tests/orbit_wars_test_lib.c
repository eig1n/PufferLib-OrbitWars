#define _DEFAULT_SOURCE
#include "ocean/orbit_wars/orbit_wars.h"

int get_sizeof_orbit_wars() {
    return sizeof(OrbitWars);
}

void test_compute_observations(OrbitWars* env) {
    ow_compute_observations(env);
}
