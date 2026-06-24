/*
 * orbit_wars.h — Orbit Wars PufferLib C Environment
 *
 * A real-time strategy game for 2 or 4 players on a 100×100 board.
 * Planets orbit a central sun, fleets travel in straight lines,
 * comets fly through on curved trajectories.
 *
 * Reference: orbit-wars/README.md for full game rules.
 *
 * Follows PufferLib patterns from target.h, slimevolley.h, chess.h.
 * Supports self-play via MY_USES_PERM and MY_USES_TAGS in binding.c.
 */

#define _POSIX_C_SOURCE 200112L

#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdio.h>
#include "raylib.h"

/* ========================================================================
 * Constants
 * ======================================================================== */

#define OW_BOARD_SIZE       100.0
#define OW_SUN_X            50.0
#define OW_SUN_Y            50.0
#define OW_SUN_RADIUS       10.0
#define OW_MAX_SPEED        6.0
#define OW_COMET_SPEED      4.0
#define OW_MAX_PLANETS      48
#define OW_MAX_FLEETS       1024
#define OW_MAX_COMET_GROUPS 5
#define OW_MAX_STEPS        500
#define OW_ROTATION_RADIUS_LIMIT 50.0f
#define OW_MAX_PLAYERS      4
#define OW_MAX_ACTIONS_PER_PLAYER 16
#define OW_COMET_PATH_LEN   100
#define OW_MIN_PLANET_GROUPS 5
#define OW_MAX_PLANET_GROUPS 10
#define OW_COMET_RADIUS     1.0f
#define OW_COMET_PRODUCTION 1
#define OW_FLEET_SPAWN_OFFSET 0.1f

/* Raw parity observation layout: 48 planets × 7 + 1024 fleets × 6 + 4 global */
#define OW_RAW_PLANET_OBS_FEAT  7
#define OW_RAW_FLEET_OBS_FEAT   6
#define OW_RAW_GLOBAL_OBS_FEAT  4
#define OW_RAW_OBS_SIZE (OW_MAX_PLANETS * OW_RAW_PLANET_OBS_FEAT + \
                         OW_MAX_FLEETS * OW_RAW_FLEET_OBS_FEAT + \
                         OW_RAW_GLOBAL_OBS_FEAT)
#define OW_PLANET_OBS_FEAT OW_RAW_PLANET_OBS_FEAT
#define OW_FLEET_OBS_FEAT OW_RAW_FLEET_OBS_FEAT
#define OW_GLOBAL_OBS_FEAT OW_RAW_GLOBAL_OBS_FEAT

/* Lite training observation layout: planets + cheap fleet grid + clean fleet slots. */
#define OW_LITE_LAUNCH_SLOTS       6
#define OW_LITE_ATN_FEAT           5
#define OW_LITE_PLANET_OBS_FEAT    8
#define OW_LITE_GRID_SIZE          10
#define OW_LITE_GRID_FEAT          4
#define OW_LITE_TOP_FLEETS         8
#define OW_LITE_TOP_FLEET_OBS_FEAT 7
#define OW_LITE_GLOBAL_OBS_FEAT    8
#define OW_LITE_AMOUNT_EPS         0.0f
#define OW_LITE_MAX_ACTIVE_SLOTS   OW_LITE_LAUNCH_SLOTS
#define OW_TRAIN_PLANET_OBS_FEAT   OW_LITE_PLANET_OBS_FEAT
#define OW_TRAIN_GLOBAL_OBS_FEAT   OW_LITE_GLOBAL_OBS_FEAT
#define OW_LITE_GRID_OBS_SIZE (OW_LITE_GRID_SIZE * OW_LITE_GRID_SIZE * OW_LITE_GRID_FEAT)
#define OW_LITE_TOP_FLEET_OBS_SIZE (OW_LITE_TOP_FLEETS * OW_LITE_TOP_FLEET_OBS_FEAT)
#define OW_TRAIN_OBS_SIZE (OW_MAX_PLANETS * OW_LITE_PLANET_OBS_FEAT + \
                           OW_LITE_GRID_OBS_SIZE + \
                           OW_LITE_TOP_FLEET_OBS_SIZE + \
                           OW_LITE_GLOBAL_OBS_FEAT)

#ifdef PARITY_TESTING
#define OW_OBS_SIZE OW_RAW_OBS_SIZE
#else
#define OW_OBS_SIZE OW_TRAIN_OBS_SIZE
#endif

/* Action space: 6 launch slots of (send amount, direction x/y, source x/y). */
#define OW_NUM_ATNS          (OW_LITE_LAUNCH_SLOTS * OW_LITE_ATN_FEAT)
#define OW_NUM_ANGLE_BUCKETS 64
#define OW_NUM_SHIP_BUCKETS  16
#define OW_INTERVAL_EPS      (1.0f / 32.0f)
#define OW_MAX_TARGETS       6
#define OW_MAX_SOURCES_PER_TARGET 3

#ifndef M_PI
#define M_PI 3.14159265358979323846f
#endif

/* Comet spawn steps */
static const int OW_COMET_SPAWN_STEPS[] = {50, 150, 250, 350, 450};
#define OW_NUM_COMET_SPAWNS 5

/* ========================================================================
 * Structs
 * ======================================================================== */

typedef struct {
    int id;
    int owner;       /* 0..3 = player, -1 = neutral */
    double x;
    double y;
    double radius;
    int ships;
    int production;
    int is_comet;
    int active;
} PlanetC;

typedef struct {
    int id;
    int owner;
    double x;
    double y;
    double angle;     /* direction of travel (radians) */
    int from_planet_id;
    int ships;
    double speed;
    int active;
} FleetC;

typedef struct {
    int planet_ids[4];
    int path_index;
    int num_steps;
    double paths_x[4][OW_COMET_PATH_LEN];
    double paths_y[4][OW_COMET_PATH_LEN];
    int active;
} CometGroupC;

typedef struct {
    int from_planet_id;
    double angle;
    int ships;
} RawActionC;

#define OW_MAX_BANKS 8

/* Required PufferLib Log struct — only floats! */
typedef struct {
    float perf;
    float score;
    float episode_return;
    float episode_length;
    float hist_score;
    float hist_n;
    float hist_score_bank[OW_MAX_BANKS];
    float hist_n_bank[OW_MAX_BANKS];
    float n;   /* Required as last field */
} Log;

/* Required PufferLib Client struct */
typedef struct {
    void* dummy;
} Client;

/* Main environment struct.
 * FIELD ORDER of the first 6 fields is CRITICAL — vecenv.h assigns
 * observations/actions/rewards/terminals by field name. */
typedef struct {
    Log log;                /* MUST be first */
    Client* client;         /* MUST be second */
    float* observations;    /* base pointer, set by vecenv.h */
    float* actions;         /* base pointer */
    float* rewards;         /* base pointer */
    float* terminals;       /* base pointer */

    /* Self-play tags (for MY_USES_TAGS) */
    int tag;
    int boundary_reached;

    /* Permuted pointer arrays (for MY_USES_PERM).
     * These point into the global vec buffers through permutation. */
    float* obs_ptr[OW_MAX_PLAYERS];
    float* action_ptr[OW_MAX_PLAYERS];
    float* reward_ptr[OW_MAX_PLAYERS];
    float* terminal_ptr[OW_MAX_PLAYERS];

    /* Slot ↔ color mapping for self-play symmetry */
    int slot_for_color[OW_MAX_PLAYERS];

    /* Game configuration */
    int num_agents;         /* 2 (1v1) or 4 (4v4) */
    int max_steps;
    unsigned int rng;

    /* Game state — planets */
    PlanetC planets[OW_MAX_PLANETS];
    int num_planets;

    /* Game state — fleets */
    FleetC fleets[OW_MAX_FLEETS];

    /* Game state — comets */
    CometGroupC comet_groups[OW_MAX_COMET_GROUPS];
    int num_comet_groups;

    /* Raw actions for parity testing (written by c_step or test harness) */
    RawActionC raw_actions[OW_MAX_PLAYERS][OW_MAX_ACTIONS_PER_PLAYER];
    int num_raw_actions[OW_MAX_PLAYERS];

    /* Tracking */
    double angular_velocity;
    int next_fleet_id;
    int next_planet_id;
    int current_step;

    /* Planet rotation state */
    double planet_angle[OW_MAX_PLANETS];
    double planet_orbital_radius[OW_MAX_PLANETS];
    int planet_orbits[OW_MAX_PLANETS];   /* 1 = orbiting, 0 = static */

    /* Combat accumulator — zeroed each step, filled during movement/rotation */
    int arriving_ships[OW_MAX_PLANETS][OW_MAX_PLAYERS];

    int prevent_reset;
#ifdef PARITY_TESTING
    float raw_observations[OW_MAX_PLAYERS][OW_OBS_SIZE];
#endif
} OrbitWars;

typedef struct {
    double x[OW_MAX_PLANETS][165];
    double y[OW_MAX_PLANETS][165];
    int step[OW_MAX_PLANETS][165];
    char result[OW_MAX_PLANETS][165];

    int fleet_id[OW_MAX_FLEETS];
    double fleet_dx[OW_MAX_FLEETS];
    double fleet_dy[OW_MAX_FLEETS];
} EnvCache;

static inline EnvCache* ow_get_cache(OrbitWars* env) {
    if (env->client == NULL) {
        EnvCache* cache = (EnvCache*)calloc(1, sizeof(EnvCache));
        for (int f = 0; f < OW_MAX_FLEETS; f++) {
            cache->fleet_id[f] = -1;
        }
        env->client = (Client*)cache;
    }
    return (EnvCache*)env->client;
}
/* ========================================================================
 * RNG helpers
 * ======================================================================== */

static inline int ow_rand(unsigned int* rng) {
    return rand_r(rng);
}

static inline float ow_randf(unsigned int* rng) {
    return (float)rand_r(rng) / (float)RAND_MAX;
}

/* Random int in [lo, hi] inclusive */
static inline int ow_rand_range(unsigned int* rng, int lo, int hi) {
    return lo + (rand_r(rng) % (hi - lo + 1));
}

/* ========================================================================
 * Math helpers
 * ======================================================================== */

static inline float ow_dist(float x1, float y1, float x2, float y2) {
    double dx = (double)x2 - (double)x1, dy = (double)y2 - (double)y1;
    return (float)sqrt(dx * dx + dy * dy);
}

static inline float ow_clampf(float v, float lo, float hi) {
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

static inline float ow_norm_angle(float a) {
    while (a < 0.0f) a += 2.0f * (float)M_PI;
    while (a >= 2.0f * (float)M_PI) a -= 2.0f * (float)M_PI;
    return a;
}

static int ow_player_for_slot(OrbitWars* env, int slot) {
    for (int p = 0; p < env->num_agents; p++) {
        if (env->slot_for_color[p] == slot) return p;
    }
    return slot;
}

static void ow_planet_slots_by_id(OrbitWars* env, int slots[OW_MAX_PLANETS]) {
    for (int i = 0; i < OW_MAX_PLANETS; i++) slots[i] = -1;
    for (int out = 0; out < OW_MAX_PLANETS; out++) {
        int best = -1;
        for (int i = 0; i < OW_MAX_PLANETS; i++) {
            if (!env->planets[i].active) continue;
            int used = 0;
            for (int k = 0; k < out; k++) {
                if (slots[k] == i) { used = 1; break; }
            }
            if (used) continue;
            if (best < 0 || env->planets[i].id < env->planets[best].id) best = i;
        }
        if (best < 0) break;
        slots[out] = best;
    }
}

static float ow_interval_pair_strength(float xs, float rs, float xt, float rt) {
    float ars = fabsf(rs);
    float art = fabsf(rt);
    float overlap = ars + art - fabsf(xs - xt);
    if (overlap <= 0.0f) return 0.0f;
    float denom = ars + art;
    if (denom < 1e-6f) return 0.0f;
    float broadness = ow_clampf((ars + art) * 0.5f, 0.0f, 1.0f);
    float precision_bonus = 1.0f / (0.25f + broadness);
    return ow_clampf((overlap / denom) * precision_bonus, 0.0f, 1.0f);
}

/*
 * Segment–circle intersection.
 * Returns the smallest t ∈ [0,1] where the segment (x1,y1)→(x2,y2) enters
 * the circle centered at (cx,cy) with radius r.  Returns -1 if no hit.
 */
static float ow_segment_circle_t(float x1, float y1, float x2, float y2,
                                  float cx, float cy, float r) {
    double dx = (double)x2 - (double)x1, dy = (double)y2 - (double)y1;
    double fx = (double)x1 - (double)cx, fy = (double)y1 - (double)cy;
    double a = dx * dx + dy * dy;
    if (a < 1e-15) {
        /* Zero-length segment: check if point is inside circle */
        return ((fx * fx + fy * fy) <= (double)r * (double)r) ? 0.0f : -1.0f;
    }
    double b = 2.0 * (fx * dx + fy * dy);
    double c = fx * fx + fy * fy - (double)r * (double)r;
    double disc = b * b - 4.0 * a * c;
    if (disc < 0.0) return -1.0f;
    double sqd = sqrt(disc);
    double t1 = (-b - sqd) / (2.0 * a);
    double t2 = (-b + sqd) / (2.0 * a);
    /* Return the earliest entry point in [0,1] */
    if (t1 >= 0.0 && t1 <= 1.0) return (float)t1;
    if (t2 >= 0.0 && t2 <= 1.0) return (float)t2;
    /* Segment starts inside circle */
    if (c <= 0.0) return 0.0f;
    return -1.0f;
}

/*
 * Swept-pair collision detection for two moving circles (or moving circle and moving segment).
 * Returns 1 if they hit during t ∈ [0,1], 0 otherwise.
 */
static int ow_swept_pair_hit(float ax, float ay, float bx, float by,
                             float px0, float py0, float px1, float py1,
                             float r) {
    double d0x = (double)ax - (double)px0;
    double d0y = (double)ay - (double)py0;
    double dvx = ((double)bx - (double)ax) - ((double)px1 - (double)px0);
    double dvy = ((double)by - (double)ay) - ((double)py1 - (double)py0);
    double a = dvx * dvx + dvy * dvy;
    double b = 2.0 * (d0x * dvx + d0y * dvy);
    double c = d0x * d0x + d0y * d0y - (double)r * (double)r;
    if (a < 1e-15) {
        return c <= 0.0;
    }
    double disc = b * b - 4.0 * a * c;
    if (disc < 0.0) return 0;
    double sq = sqrt(disc);
    double t1 = (-b - sq) / (2.0 * a);
    double t2 = (-b + sq) / (2.0 * a);
    return (t2 >= 0.0 && t1 <= 1.0);
}

static inline int ow_aabb_overlap(double amin_x, double amin_y, double amax_x, double amax_y,
                                  double bmin_x, double bmin_y, double bmax_x, double bmax_y) {
    return amin_x <= bmax_x && amax_x >= bmin_x &&
           amin_y <= bmax_y && amax_y >= bmin_y;
}

/* ========================================================================
 * Fleet speed
 * ======================================================================== */

static inline float ow_fleet_speed(int ships) {
    if (ships <= 1) return 1.0f;
    double ratio = log((double)ships) / log(1000.0);
    if (ratio > 1.0) ratio = 1.0;
    return (float)(1.0 + ((double)OW_MAX_SPEED - 1.0) * pow(ratio, 1.5));
}

/* ========================================================================
 * Planet radius from production
 * ======================================================================== */

static inline float ow_planet_radius(int production) {
    return (float)(1.0 + log((double)production));
}

/* ========================================================================
 * Find first inactive fleet slot
 * ======================================================================== */

static int ow_alloc_fleet(OrbitWars* env) {
    for (int i = 0; i < OW_MAX_FLEETS; i++) {
        if (!env->fleets[i].active) return i;
    }
    return -1; /* no free slot */
}

/* ========================================================================
 * Map generation with 4-fold symmetry
 * ======================================================================== */

static void ow_generate_map(OrbitWars* env) {
    int num_groups = ow_rand_range(&env->rng, OW_MIN_PLANET_GROUPS, OW_MAX_PLANET_GROUPS);

    /* Ensure at least 1 orbiting and at least 3 static groups */
    int num_orbiting = ow_rand_range(&env->rng, 1, (num_groups - 3 > 1) ? num_groups - 3 : 1);
    int num_static   = num_groups - num_orbiting;
    if (num_static < 3) { num_static = 3; num_orbiting = num_groups - 3; }
    if (num_orbiting < 1) { num_orbiting = 1; num_static = num_groups - 1; }

    env->num_planets = 0;
    env->next_planet_id = 0;

    /* Angular velocity for this game */
    env->angular_velocity = 0.025f + ow_randf(&env->rng) * 0.025f;

    /* Track group starts for home planet selection */
    int group_starts[OW_MAX_PLANET_GROUPS];
    int total_groups = 0;

    /* --- Generate orbiting groups --- */
    for (int g = 0; g < num_orbiting && env->num_planets + 4 <= OW_MAX_PLANETS; g++) {
        int production = ow_rand_range(&env->rng, 1, 5);
        float radius = ow_planet_radius(production);
        /* Orbiting: orbital_radius + radius < ROTATION_RADIUS_LIMIT */
        float max_orb = OW_ROTATION_RADIUS_LIMIT - radius - 1.0f;
        if (max_orb < 15.0f) max_orb = 15.0f;
        float orbital_r = 15.0f + ow_randf(&env->rng) * (max_orb - 15.0f);
        float angle = ow_randf(&env->rng) * (M_PI / 2.0f); /* Q1 angle */

        /* Base position in top-left quadrant (x < 50, y < 50) */
        float bx = OW_SUN_X - orbital_r * cosf(angle);
        float by = OW_SUN_Y - orbital_r * sinf(angle);

        /* Skewed-low starting ships: min of 3 random values */
        int ships = 99;
        for (int k = 0; k < 3; k++) {
            int v = ow_rand_range(&env->rng, 5, 99);
            if (v < ships) ships = v;
        }

        group_starts[total_groups] = env->num_planets;
        total_groups++;

        /* Create 4 symmetric planets */
        float mirror_x[4] = {bx, OW_BOARD_SIZE - bx, bx, OW_BOARD_SIZE - bx};
        float mirror_y[4] = {by, by, OW_BOARD_SIZE - by, OW_BOARD_SIZE - by};
        for (int m = 0; m < 4; m++) {
            int idx = env->num_planets;
            env->planets[idx] = (PlanetC){
                .id = env->next_planet_id++,
                .owner = -1,
                .x = mirror_x[m],
                .y = mirror_y[m],
                .radius = radius,
                .ships = ships,
                .production = production,
                .is_comet = 0,
                .active = 1
            };
            /* Compute rotation state */
            float dx = mirror_x[m] - OW_SUN_X;
            float dy = mirror_y[m] - OW_SUN_Y;
            env->planet_orbital_radius[idx] = sqrtf(dx * dx + dy * dy);
            env->planet_angle[idx] = atan2f(dy, dx);
            env->planet_orbits[idx] = 1;
            env->num_planets++;
        }
    }

    /* --- Generate static groups --- */
    for (int g = 0; g < num_static && env->num_planets + 4 <= OW_MAX_PLANETS; g++) {
        int production = ow_rand_range(&env->rng, 1, 5);
        float radius = ow_planet_radius(production);
        /* Static: place in corners / edges, orbital_radius + radius >= 50 */
        float min_orb = OW_ROTATION_RADIUS_LIMIT - radius + 1.0f;
        float max_orb = 45.0f; /* keep within board bounds */
        if (min_orb > max_orb) min_orb = max_orb - 1.0f;
        float orbital_r = min_orb + ow_randf(&env->rng) * (max_orb - min_orb);
        float angle = ow_randf(&env->rng) * (M_PI / 2.0f);

        float bx = OW_SUN_X - orbital_r * cosf(angle);
        float by = OW_SUN_Y - orbital_r * sinf(angle);

        /* Clamp to board with margin */
        bx = ow_clampf(bx, radius + 1.0f, OW_BOARD_SIZE - radius - 1.0f);
        by = ow_clampf(by, radius + 1.0f, OW_BOARD_SIZE - radius - 1.0f);

        int ships = 99;
        for (int k = 0; k < 3; k++) {
            int v = ow_rand_range(&env->rng, 5, 99);
            if (v < ships) ships = v;
        }

        group_starts[total_groups] = env->num_planets;
        total_groups++;

        float mirror_x[4] = {bx, OW_BOARD_SIZE - bx, bx, OW_BOARD_SIZE - bx};
        float mirror_y[4] = {by, by, OW_BOARD_SIZE - by, OW_BOARD_SIZE - by};
        for (int m = 0; m < 4; m++) {
            int idx = env->num_planets;
            env->planets[idx] = (PlanetC){
                .id = env->next_planet_id++,
                .owner = -1,
                .x = mirror_x[m],
                .y = mirror_y[m],
                .radius = radius,
                .ships = ships,
                .production = production,
                .is_comet = 0,
                .active = 1
            };
            float dx = mirror_x[m] - OW_SUN_X;
            float dy = mirror_y[m] - OW_SUN_Y;
            env->planet_orbital_radius[idx] = sqrtf(dx * dx + dy * dy);
            env->planet_angle[idx] = atan2f(dy, dx);
            env->planet_orbits[idx] = 0; /* static */
            env->num_planets++;
        }
    }

    /* --- Assign home planets --- */
    int home_group = ow_rand_range(&env->rng, 0, total_groups - 1);
    int home_base = group_starts[home_group];

    if (env->num_agents == 2) {
        /* Player 0 = planet 0 (top-left), Player 1 = planet 3 (bottom-right) */
        env->planets[home_base + 0].owner = 0;
        env->planets[home_base + 0].ships = 10;
        env->planets[home_base + 3].owner = 1;
        env->planets[home_base + 3].ships = 10;
    } else {
        /* 4-player: each player gets one planet from the group */
        for (int p = 0; p < 4 && p < env->num_agents; p++) {
            env->planets[home_base + p].owner = p;
            env->planets[home_base + p].ships = 10;
        }
    }
}

/* ========================================================================
 * Comet path generation
 *
 * Generates a curved trajectory through the board using gravity simulation.
 * The comet enters from outside the board, is deflected by the sun's
 * gravity, and exits. Paths are symmetric across quadrants.
 * ======================================================================== */

static void ow_generate_comet_path(OrbitWars* env, int group_idx) {
    CometGroupC* cg = &env->comet_groups[group_idx];

    /* Generate path for Q1 comet, then mirror */
    /* Pick a random entry edge (top or left of Q1 area) */
    float entry_x, entry_y, vx, vy;
    if (ow_randf(&env->rng) < 0.5f) {
        /* Enter from top */
        entry_x = 55.0f + ow_randf(&env->rng) * 40.0f;
        entry_y = -5.0f;
        vx = -1.0f + ow_randf(&env->rng) * 0.5f;
        vy = 1.5f + ow_randf(&env->rng);
    } else {
        /* Enter from right */
        entry_x = 105.0f;
        entry_y = 5.0f + ow_randf(&env->rng) * 40.0f;
        vx = -(1.5f + ow_randf(&env->rng));
        vy = 0.5f + ow_randf(&env->rng) * 0.5f;
    }

    /* Normalize velocity to COMET_SPEED */
    float mag = sqrtf(vx * vx + vy * vy);
    vx = vx / mag * OW_COMET_SPEED;
    vy = vy / mag * OW_COMET_SPEED;

    /* Simulate with gravity */
    float px = entry_x, py = entry_y;
    int count = 0;
    for (int i = 0; i < OW_COMET_PATH_LEN; i++) {
        cg->paths_x[0][count] = px;
        cg->paths_y[0][count] = py;
        count++;

        /* Gravitational pull toward sun */
        float dx = OW_SUN_X - px;
        float dy = OW_SUN_Y - py;
        float dist = sqrtf(dx * dx + dy * dy);
        if (dist < 2.0f) dist = 2.0f;
        float g = 30.0f / (dist * dist);
        vx += g * dx / dist;
        vy += g * dy / dist;

        /* Normalize to constant speed */
        mag = sqrtf(vx * vx + vy * vy);
        vx = vx / mag * OW_COMET_SPEED;
        vy = vy / mag * OW_COMET_SPEED;

        px += vx;
        py += vy;

        /* Stop if far out of bounds */
        if (px < -20.0f || px > 120.0f || py < -20.0f || py > 120.0f) break;
    }
    cg->num_steps = count;

    /* Mirror to other 3 quadrants */
    for (int i = 0; i < count; i++) {
        float x0 = cg->paths_x[0][i];
        float y0 = cg->paths_y[0][i];
        cg->paths_x[1][i] = OW_BOARD_SIZE - x0;  cg->paths_y[1][i] = y0;
        cg->paths_x[2][i] = x0;                    cg->paths_y[2][i] = OW_BOARD_SIZE - y0;
        cg->paths_x[3][i] = OW_BOARD_SIZE - x0;  cg->paths_y[3][i] = OW_BOARD_SIZE - y0;
    }
}

/* ========================================================================
 * Comet spawning — creates 4 comet-planets and a comet group
 * ======================================================================== */

static void ow_spawn_comet_group(OrbitWars* env) {
    if (env->num_comet_groups >= OW_MAX_COMET_GROUPS) return;
    if (env->num_planets + 4 > OW_MAX_PLANETS) return;

    int gi = env->num_comet_groups;
    CometGroupC* cg = &env->comet_groups[gi];
    memset(cg, 0, sizeof(CometGroupC));

    /* Generate comet path */
    ow_generate_comet_path(env, gi);

    /* Starting ships: min of 4 random rolls in [1, 99] */
    int ships = 99;
    for (int k = 0; k < 4; k++) {
        int v = ow_rand_range(&env->rng, 1, 99);
        if (v < ships) ships = v;
    }

    /* Create 4 comet-planets at path start positions */
    cg->path_index = -1;
    cg->active = 1;
    for (int m = 0; m < 4; m++) {
        int idx = env->num_planets;
        if (idx >= OW_MAX_PLANETS) break;

        env->planets[idx] = (PlanetC){
            .id = idx,
            .owner = -1,
            .x = -99.0f,
            .y = -99.0f,
            .radius = OW_COMET_RADIUS,
            .ships = ships,
            .production = OW_COMET_PRODUCTION,
            .is_comet = 1,
            .active = 1
        };
        env->planet_orbital_radius[idx] = 0;
        env->planet_angle[idx] = 0;
        env->planet_orbits[idx] = 0;

        cg->planet_ids[m] = env->planets[idx].id;
        env->num_planets++;
    }

    env->num_comet_groups++;
}

/* ========================================================================
 * Observation computation — perspective-symmetric
 * ======================================================================== */

#ifdef PARITY_TESTING
static void ow_compute_raw_observations(OrbitWars* env, int a, float* obs, const int* total_ships, int sum_all_ships) {
    int na = env->num_agents;
    /* Get the actual player ID for slot a */
    int player_id = -1;
    for (int p = 0; p < na; p++) {
        if (env->slot_for_color[p] == a) { player_id = p; break; }
    }
    if (player_id < 0) player_id = a; /* fallback */

    /* Zero the observation buffer first to avoid writing zeros in loops */
    memset(obs, 0, sizeof(float) * OW_OBS_SIZE);

    int idx = 0;

    /* Per-planet features (48 × 7) */
    for (int p = 0; p < OW_MAX_PLANETS; p++) {
        PlanetC* pl = &env->planets[p];
        if (pl->active) {
            /* Owner relative to observer */
            if (pl->owner == -1) {
                obs[idx] = -1.0f;
            } else if (pl->owner == player_id) {
                obs[idx] = 0.0f;
            } else {
                int rel = (pl->owner - player_id + na) % na;
                obs[idx] = (float)rel;
            }
            obs[idx+1] = (float)pl->x;
            obs[idx+2] = (float)pl->y;
            obs[idx+3] = (float)pl->radius;
            obs[idx+4] = (float)pl->ships;
            obs[idx+5] = (float)pl->production;
            obs[idx+6] = 1.0f;
        }
        idx += OW_PLANET_OBS_FEAT;
    }

    /* Per-fleet features (1024 × 6) */
    for (int f = 0; f < OW_MAX_FLEETS; f++) {
        FleetC* fl = &env->fleets[f];
        if (fl->active) {
            if (fl->owner == player_id) {
                obs[idx] = 0.0f;
            } else {
                int rel = (fl->owner - player_id + na) % na;
                obs[idx] = (float)rel;
            }
            obs[idx+1] = (float)fl->x;
            obs[idx+2] = (float)fl->y;
            obs[idx+3] = (float)fl->angle;
            obs[idx+4] = (float)fl->ships;
            obs[idx+5] = 1.0f;
        }
        idx += OW_FLEET_OBS_FEAT;
    }

    /* Global features (4) */
    obs[idx] = (float)env->angular_velocity;
    obs[idx+1] = (float)env->current_step;

    int my_ships = total_ships[player_id];
    int enemy_ships = sum_all_ships - my_ships;

    obs[idx+2] = (float)my_ships;
    obs[idx+3] = (float)enemy_ships;
}

static void ow_process_observations(OrbitWars* env, int a, const float* raw_obs, float* out_obs) {
    int na = env->num_agents;
    memset(out_obs, 0, sizeof(float) * OW_OBS_SIZE);
    int idx = 0;

    /* Process per-planet features (48 × 7) */
    for (int p = 0; p < OW_MAX_PLANETS; p++) {
        PlanetC* pl = &env->planets[p];
        if (pl->active) {
            /* owner relative */
            if (raw_obs[idx] == -1.0f) {
                out_obs[idx] = -1.0f / (float)na;
            } else if (raw_obs[idx] == 0.0f) {
                out_obs[idx] = 0.0f;
            } else {
                out_obs[idx] = raw_obs[idx] / (float)(na - 1);
            }
            out_obs[idx+1] = raw_obs[idx+1] / OW_BOARD_SIZE;
            out_obs[idx+2] = raw_obs[idx+2] / OW_BOARD_SIZE;
            out_obs[idx+3] = raw_obs[idx+3] / 5.0f;
            out_obs[idx+4] = raw_obs[idx+4] / 1000.0f;
            out_obs[idx+5] = raw_obs[idx+5] / 5.0f;
            out_obs[idx+6] = 1.0f;
        }
        idx += OW_PLANET_OBS_FEAT;
    }

    /* Process per-fleet features (1024 × 6) */
    for (int f = 0; f < OW_MAX_FLEETS; f++) {
        FleetC* fl = &env->fleets[f];
        if (fl->active) {
            /* owner relative */
            if (raw_obs[idx] == 0.0f) {
                out_obs[idx] = 0.0f;
            } else {
                out_obs[idx] = raw_obs[idx] / (float)(na - 1);
            }
            out_obs[idx+1] = raw_obs[idx+1] / OW_BOARD_SIZE;
            out_obs[idx+2] = raw_obs[idx+2] / OW_BOARD_SIZE;
            out_obs[idx+3] = raw_obs[idx+3] / (2.0f * M_PI);
            out_obs[idx+4] = raw_obs[idx+4] / 1000.0f;
            out_obs[idx+5] = 1.0f;
        }
        idx += OW_FLEET_OBS_FEAT;
    }

    /* Process global features (4) */
    out_obs[idx]   = raw_obs[idx] / 0.05f;
    out_obs[idx+1] = raw_obs[idx+1] / (float)OW_MAX_STEPS;
    out_obs[idx+2] = raw_obs[idx+2] / 1000.0f;
    out_obs[idx+3] = raw_obs[idx+3] / 1000.0f;
}
#else
static void ow_compute_and_scale_observations_impl(OrbitWars* env, int a, float* out_obs,
                                                   const int* total_ships, int sum_all_ships,
                                                   const int* active_fleet_indices, int num_active_fleets,
                                                   const float* fleet_cos, const float* fleet_sin,
                                                   int own_prod, int enemy_prod) {
    int na = env->num_agents;
    int player_id = ow_player_for_slot(env, a);
    int slots[OW_MAX_PLANETS];
    float fleet_grid[OW_LITE_GRID_OBS_SIZE] = {0};
    int clean_fleets[OW_LITE_TOP_FLEETS];

    for (int i = 0; i < OW_LITE_TOP_FLEETS; i++) {
        clean_fleets[i] = -1;
    }
    ow_planet_slots_by_id(env, slots);
    memset(out_obs, 0, sizeof(float) * OW_OBS_SIZE);

    for (int i = 0; i < num_active_fleets; i++) {
        int f = active_fleet_indices[i];
        FleetC* fl = &env->fleets[f];

        int gx = (int)(fl->x * 0.1);
        int gy = (int)(fl->y * 0.1);
        if (gx < 0) gx = 0;
        if (gx >= OW_LITE_GRID_SIZE) gx = OW_LITE_GRID_SIZE - 1;
        if (gy < 0) gy = 0;
        if (gy >= OW_LITE_GRID_SIZE) gy = OW_LITE_GRID_SIZE - 1;

        int base = (gy * OW_LITE_GRID_SIZE + gx) * OW_LITE_GRID_FEAT;
        float mass = ow_clampf((float)fl->ships / 100.0f, 0.0f, 5.0f);
        float dir_x = fleet_cos[f] * mass;
        float dir_y = fleet_sin[f] * mass;
        if (fl->owner == player_id) {
            fleet_grid[base + 0] += mass;
            fleet_grid[base + 2] += dir_x;
            fleet_grid[base + 3] += dir_y;
        } else {
            fleet_grid[base + 1] += mass;
            fleet_grid[base + 2] -= dir_x;
            fleet_grid[base + 3] -= dir_y;
        }
    }

    if (num_active_fleets > 0) {
        int start = (env->current_step + player_id * OW_LITE_TOP_FLEETS) % num_active_fleets;
        int count = num_active_fleets < OW_LITE_TOP_FLEETS ? num_active_fleets : OW_LITE_TOP_FLEETS;
        for (int k = 0; k < count; k++) {
            clean_fleets[k] = active_fleet_indices[(start + k) % num_active_fleets];
        }
    }

    int idx = 0;
    for (int s = 0; s < OW_MAX_PLANETS; s++) {
        int pi = slots[s];
        if (pi >= 0) {
            PlanetC* pl = &env->planets[pi];
            float owner_rel = 0.0f;
            if (pl->owner == player_id) owner_rel = 1.0f;
            else if (pl->owner >= 0) owner_rel = -1.0f;

            float dx = (float)(pl->x - OW_SUN_X);
            float dy = (float)(pl->y - OW_SUN_Y);

            out_obs[idx + 0] = 1.0f;
            out_obs[idx + 1] = owner_rel;
            out_obs[idx + 2] = ow_clampf(dx / OW_SUN_X, -1.0f, 1.0f);
            out_obs[idx + 3] = ow_clampf(dy / OW_SUN_Y, -1.0f, 1.0f);
            out_obs[idx + 4] = ow_clampf((float)pl->ships / 200.0f, 0.0f, 5.0f);
            out_obs[idx + 5] = ow_clampf((float)pl->production / 5.0f, 0.0f, 1.0f);
            out_obs[idx + 6] = pl->is_comet ? 1.0f : 0.0f;
            out_obs[idx + 7] = env->planet_orbits[pi] ? 1.0f : 0.0f;
        }
        idx += OW_LITE_PLANET_OBS_FEAT;
    }

    for (int i = 0; i < OW_LITE_GRID_OBS_SIZE; i++) {
        out_obs[idx++] = ow_clampf(fleet_grid[i], -5.0f, 5.0f);
    }

    for (int k = 0; k < OW_LITE_TOP_FLEETS; k++) {
        int fi = clean_fleets[k];
        if (fi >= 0) {
            FleetC* fl = &env->fleets[fi];
            float owner_rel = fl->owner == player_id ? 1.0f : -1.0f;
            out_obs[idx + 0] = 1.0f;
            out_obs[idx + 1] = owner_rel;
            out_obs[idx + 2] = ow_clampf((float)(fl->x - OW_SUN_X) / OW_SUN_X, -1.0f, 1.0f);
            out_obs[idx + 3] = ow_clampf((float)(fl->y - OW_SUN_Y) / OW_SUN_Y, -1.0f, 1.0f);
            out_obs[idx + 4] = fleet_cos[fi];
            out_obs[idx + 5] = fleet_sin[fi];
            out_obs[idx + 6] = ow_clampf((float)fl->ships / 200.0f, 0.0f, 5.0f);
        }
        idx += OW_LITE_TOP_FLEET_OBS_FEAT;
    }

    int my_ships = total_ships[player_id];
    int enemy_ships = sum_all_ships - my_ships;
    out_obs[idx + 0] = ow_clampf((float)env->angular_velocity / 0.05f, 0.0f, 1.0f);
    out_obs[idx + 1] = ow_clampf((float)env->current_step / (float)OW_MAX_STEPS, 0.0f, 1.0f);
    out_obs[idx + 2] = ow_clampf((float)(OW_MAX_STEPS - env->current_step) / (float)OW_MAX_STEPS, 0.0f, 1.0f);
    out_obs[idx + 3] = ow_clampf((float)my_ships / 1000.0f, 0.0f, 1.0f);
    out_obs[idx + 4] = ow_clampf((float)enemy_ships / 1000.0f, 0.0f, 1.0f);
    out_obs[idx + 5] = ow_clampf((float)own_prod / 50.0f, 0.0f, 1.0f);
    out_obs[idx + 6] = ow_clampf((float)enemy_prod / 50.0f, 0.0f, 1.0f);
    out_obs[idx + 7] = (na == 2) ? 1.0f : 0.0f;
}

static inline void ow_compute_and_scale_observations(OrbitWars* env, int a, float* out_obs, const int* total_ships, int sum_all_ships) {
    int player_id = ow_player_for_slot(env, a);
    int active_fleet_indices[OW_MAX_FLEETS];
    int num_active_fleets = 0;
    float fleet_cos[OW_MAX_FLEETS];
    float fleet_sin[OW_MAX_FLEETS];
    for (int f = 0; f < OW_MAX_FLEETS; f++) {
        FleetC* fl = &env->fleets[f];
        if (fl->active) {
            active_fleet_indices[num_active_fleets++] = f;
            float angle = (float)fl->angle;
            fleet_cos[f] = cosf(angle);
            fleet_sin[f] = sinf(angle);
        }
    }
    int own_prod = 0;
    int enemy_prod = 0;
    for (int p = 0; p < OW_MAX_PLANETS; p++) {
        PlanetC* pl = &env->planets[p];
        if (!pl->active) continue;
        if (pl->owner == player_id) own_prod += pl->production;
        else if (pl->owner >= 0) enemy_prod += pl->production;
    }
    ow_compute_and_scale_observations_impl(env, a, out_obs, total_ships, sum_all_ships,
                                           active_fleet_indices, num_active_fleets, fleet_cos, fleet_sin,
                                           own_prod, enemy_prod);
}
#endif

static void ow_compute_observations(OrbitWars* env) {
    int na = env->num_agents;

    /* Precompute total ships per player once for all agents */
    int total_ships[OW_MAX_PLAYERS] = {0};
    int sum_all_ships = 0;
    for (int p = 0; p < OW_MAX_PLANETS; p++) {
        PlanetC* pl = &env->planets[p];
        if (pl->active && pl->owner >= 0 && pl->owner < na) {
            total_ships[pl->owner] += pl->ships;
        }
    }

    int active_fleet_indices[OW_MAX_FLEETS];
    int num_active_fleets = 0;
    float fleet_cos[OW_MAX_FLEETS];
    float fleet_sin[OW_MAX_FLEETS];

    for (int f = 0; f < OW_MAX_FLEETS; f++) {
        FleetC* fl = &env->fleets[f];
        if (fl->active) {
            active_fleet_indices[num_active_fleets++] = f;
            if (fl->owner >= 0 && fl->owner < na) {
                total_ships[fl->owner] += fl->ships;
            }
            float angle = (float)fl->angle;
            fleet_cos[f] = cosf(angle);
            fleet_sin[f] = sinf(angle);
        }
    }

    for (int p = 0; p < na; p++) {
        sum_all_ships += total_ships[p];
    }

    int prod_by_player[OW_MAX_PLAYERS] = {0};
    int sum_all_prod = 0;
    for (int p = 0; p < OW_MAX_PLANETS; p++) {
        PlanetC* pl = &env->planets[p];
        if (pl->active && pl->owner >= 0 && pl->owner < na) {
            prod_by_player[pl->owner] += pl->production;
            sum_all_prod += pl->production;
        }
    }

    for (int a = 0; a < na; a++) {
#ifdef PARITY_TESTING
        float raw_obs[OW_OBS_SIZE];
        ow_compute_raw_observations(env, a, raw_obs, total_ships, sum_all_ships);
        memcpy(env->raw_observations[a], raw_obs, sizeof(float) * OW_OBS_SIZE);
        ow_process_observations(env, a, raw_obs, env->obs_ptr[a]);
#else
        int player_id = ow_player_for_slot(env, a);
        int own_prod = prod_by_player[player_id];
        int enemy_prod = sum_all_prod - own_prod;
        ow_compute_and_scale_observations_impl(env, a, env->obs_ptr[a], total_ships, sum_all_ships,
                                               active_fleet_indices, num_active_fleets, fleet_cos, fleet_sin,
                                               own_prod, enemy_prod);
#endif
    }
}

/* ========================================================================
 * init — called once per env by binding.c
 * ======================================================================== */

void init(OrbitWars* env) {
    env->client = NULL;
    env->max_steps = OW_MAX_STEPS;
    /* Everything else is zeroed by calloc in vecenv.h */
}

/* ========================================================================
 * c_reset — generate a new game and compute initial observations
 * ======================================================================== */

void c_reset(OrbitWars* env) {
    EnvCache* cache = ow_get_cache(env);
    memset(cache->step, 0, sizeof(cache->step));
    for (int f = 0; f < OW_MAX_FLEETS; f++) {
        cache->fleet_id[f] = -1;
    }
    /* Clear game state */
    memset(env->planets, 0, sizeof(env->planets));
    memset(env->fleets, 0, sizeof(env->fleets));
    memset(env->comet_groups, 0, sizeof(env->comet_groups));
    memset(env->arriving_ships, 0, sizeof(env->arriving_ships));
    for (int i = 0; i < OW_MAX_PLANETS; i++) {
        env->planet_orbits[i] = 0;
        env->planet_angle[i] = 0;
        env->planet_orbital_radius[i] = 0;
    }
    env->num_planets = 0;
    env->num_comet_groups = 0;
    env->next_fleet_id = 0;
    env->next_planet_id = 0;
    env->current_step = 0;
    for (int p = 0; p < OW_MAX_PLAYERS; p++) env->num_raw_actions[p] = 0;

    /* Generate map */
    ow_generate_map(env);

    /* Compute initial observations */
    ow_compute_observations(env);
}

/* ========================================================================
 * Phase 1: Comet expiration
 * Remove comets whose planet has left the board.
 * ======================================================================== */

static void ow_phase_comet_expiration(OrbitWars* env) {
    for (int gi = 0; gi < env->num_comet_groups; gi++) {
        CometGroupC* cg = &env->comet_groups[gi];
        if (!cg->active) continue;

        /* Check if path_index exceeded path length */
        if (cg->path_index >= cg->num_steps) {
            /* Remove all comets in this group */
            for (int m = 0; m < 4; m++) {
                for (int p = 0; p < OW_MAX_PLANETS; p++) {
                    if (env->planets[p].active && env->planets[p].id == cg->planet_ids[m]) {
                        env->planets[p].active = 0;
                        break;
                    }
                }
            }
            cg->active = 0;
            env->num_planets -= 4;
            continue;
        }

        /* Also check if any comet planet is out of bounds */
        for (int m = 0; m < 4; m++) {
            for (int p = 0; p < OW_MAX_PLANETS; p++) {
                if (!env->planets[p].active) continue;
                if (env->planets[p].id != cg->planet_ids[m]) continue;
                float x = env->planets[p].x;
                float y = env->planets[p].y;
                if (x < -5.0f || x > OW_BOARD_SIZE + 5.0f ||
                    y < -5.0f || y > OW_BOARD_SIZE + 5.0f) {
                    env->planets[p].active = 0;
                }
            }
        }
    }
}

/* ========================================================================
 * Phase 2: Comet spawning
 * ======================================================================== */

static void ow_phase_comet_spawning(OrbitWars* env) {
    for (int i = 0; i < OW_NUM_COMET_SPAWNS; i++) {
        if (env->current_step == OW_COMET_SPAWN_STEPS[i]) {
            ow_spawn_comet_group(env);
            break;
        }
    }
}

/* ========================================================================
 * Phase 3: Fleet launch — process raw_actions
 * ======================================================================== */

static void ow_phase_fleet_launch(OrbitWars* env) {
    for (int p = 0; p < env->num_agents; p++) {
        for (int ai = 0; ai < env->num_raw_actions[p]; ai++) {
            RawActionC* act = &env->raw_actions[p][ai];
            if (act->ships <= 0) continue;

            /* Find the source planet */
            int src_idx = -1;
            for (int pi = 0; pi < OW_MAX_PLANETS; pi++) {
                if (env->planets[pi].active && env->planets[pi].id == act->from_planet_id) {
                    src_idx = pi;
                    break;
                }
            }
            if (src_idx < 0) continue;

            PlanetC* src = &env->planets[src_idx];
            /* Must own the planet and have enough ships */
            if (src->owner != p) continue;
            int ships_to_send = act->ships;
            if (ships_to_send > src->ships) ships_to_send = src->ships;
            if (ships_to_send <= 0) continue;

            /* Allocate fleet slot */
            int fi = ow_alloc_fleet(env);
            if (fi < 0) continue;

            /* Spawn just outside planet radius */
            double spawn_x = src->x + (src->radius + (double)OW_FLEET_SPAWN_OFFSET) * cos(act->angle);
            double spawn_y = src->y + (src->radius + (double)OW_FLEET_SPAWN_OFFSET) * sin(act->angle);

            env->fleets[fi] = (FleetC){
                .id = env->next_fleet_id++,
                .owner = p,
                .x = spawn_x,
                .y = spawn_y,
                .angle = act->angle,
                .from_planet_id = act->from_planet_id,
                .ships = ships_to_send,
                .speed = ow_fleet_speed(ships_to_send),
                .active = 1
            };

            src->ships -= ships_to_send;
        }
    }
}

/* ========================================================================
 * Phase 4: Production
 * ======================================================================== */

static void ow_phase_production(OrbitWars* env) {
    for (int i = 0; i < OW_MAX_PLANETS; i++) {
        PlanetC* p = &env->planets[i];
        if (p->active && p->owner >= 0) {
            p->ships += p->production;
        }
    }
}

/* ========================================================================
 * Phase 5: Fleet movement
 * Move fleets along their heading. Check OOB, sun, planet collisions.
 * Uses continuous (segment–circle) collision detection.
 * ======================================================================== */

static void ow_phase_fleet_movement(OrbitWars* env) {
    if (env->next_fleet_id == 0) return;

    double next_px[OW_MAX_PLANETS];
    double next_py[OW_MAX_PLANETS];
    double planet_min_x[OW_MAX_PLANETS];
    double planet_min_y[OW_MAX_PLANETS];
    double planet_max_x[OW_MAX_PLANETS];
    double planet_max_y[OW_MAX_PLANETS];
    int active_planets[OW_MAX_PLANETS];
    int num_active_planets = 0;
    int active_fleets[OW_MAX_FLEETS];
    int num_active_fleets = 0;

    for (int fi = 0; fi < OW_MAX_FLEETS; fi++) {
        if (env->fleets[fi].active) {
            active_fleets[num_active_fleets++] = fi;
        }
    }
    if (num_active_fleets == 0) return;

    /* Precompute projected next positions and broadphase boxes for collidable planets. */
    for (int pi = 0; pi < OW_MAX_PLANETS; pi++) {
        PlanetC* pl = &env->planets[pi];
        next_px[pi] = pl->x;
        next_py[pi] = pl->y;
        if (!pl->active) continue;
        if (pl->x < 0.0f) continue;

        if (env->planet_orbits[pi]) {
            next_px[pi] = OW_SUN_X + env->planet_orbital_radius[pi] * cos(env->planet_angle[pi]);
            next_py[pi] = OW_SUN_Y + env->planet_orbital_radius[pi] * sin(env->planet_angle[pi]);
        } else if (pl->is_comet) {
            // Find comet group path
            for (int gi = 0; gi < env->num_comet_groups; gi++) {
                CometGroupC* cg = &env->comet_groups[gi];
                if (!cg->active) continue;
                int found = 0;
                for (int m = 0; m < 4; m++) {
                    if (cg->planet_ids[m] == pl->id) {
                        int next_idx = cg->path_index + 1;
                        if (next_idx < cg->num_steps) {
                            next_px[pi] = cg->paths_x[m][next_idx];
                            next_py[pi] = cg->paths_y[m][next_idx];
                        }
                        found = 1;
                        break;
                    }
                }
                if (found) break;
            }
        }

        double min_x = pl->x < next_px[pi] ? pl->x : next_px[pi];
        double min_y = pl->y < next_py[pi] ? pl->y : next_py[pi];
        double max_x = pl->x > next_px[pi] ? pl->x : next_px[pi];
        double max_y = pl->y > next_py[pi] ? pl->y : next_py[pi];
        double r = pl->radius;
        planet_min_x[pi] = min_x - r;
        planet_min_y[pi] = min_y - r;
        planet_max_x[pi] = max_x + r;
        planet_max_y[pi] = max_y + r;
        active_planets[num_active_planets++] = pi;
    }

    EnvCache* cache = ow_get_cache(env);

    for (int afi = 0; afi < num_active_fleets; afi++) {
        int fi = active_fleets[afi];
        FleetC* fl = &env->fleets[fi];

        double old_x = fl->x, old_y = fl->y;
        double dx, dy;
        if (cache->fleet_id[fi] == fl->id) {
            dx = cache->fleet_dx[fi];
            dy = cache->fleet_dy[fi];
        } else {
            dx = fl->speed * cos(fl->angle);
            dy = fl->speed * sin(fl->angle);
            cache->fleet_id[fi] = fl->id;
            cache->fleet_dx[fi] = dx;
            cache->fleet_dy[fi] = dy;
        }
        double new_x = old_x + dx;
        double new_y = old_y + dy;
        double fleet_min_x = old_x < new_x ? old_x : new_x;
        double fleet_min_y = old_y < new_y ? old_y : new_y;
        double fleet_max_x = old_x > new_x ? old_x : new_x;
        double fleet_max_y = old_y > new_y ? old_y : new_y;

        /* Check planet collisions first using swept-pair continuous check */
        int hit_planet = 0;
        for (int api = 0; api < num_active_planets; api++) {
            int pi = active_planets[api];
            PlanetC* pl = &env->planets[pi];
            if (!ow_aabb_overlap(fleet_min_x, fleet_min_y, fleet_max_x, fleet_max_y,
                                 planet_min_x[pi], planet_min_y[pi],
                                 planet_max_x[pi], planet_max_y[pi])) {
                continue;
            }

            if (ow_swept_pair_hit(old_x, old_y, new_x, new_y,
                                  pl->x, pl->y, next_px[pi], next_py[pi],
                                  pl->radius)) {
                env->arriving_ships[pi][fl->owner] += fl->ships;
                fl->active = 0;
                hit_planet = 1;
                break;
            }
        }

        if (hit_planet) continue;

        /* Check OOB */
        if (new_x < 0.0f || new_x > OW_BOARD_SIZE ||
            new_y < 0.0f || new_y > OW_BOARD_SIZE) {
            fl->active = 0;
            continue;
        }

        /* Check sun collision (segment vs sun circle) */
        float t_sun = ow_segment_circle_t(old_x, old_y, new_x, new_y,
                                           OW_SUN_X, OW_SUN_Y, OW_SUN_RADIUS);
        if (t_sun >= 0.0f) {
            fl->active = 0; /* Destroyed by sun */
            continue;
        }

        /* Move fleet to new position */
        fl->x = new_x;
        fl->y = new_y;
    }
}

/* ========================================================================
 * Phase 6: Planet rotation & comet movement
 * Rotate orbiting planets, advance comets. Check if any fleet
 * is now inside a planet (swept collision).
 * ======================================================================== */

static void ow_phase_rotation_and_comets(OrbitWars* env) {
    /* Rotate orbiting planets — update position with current angle, then increment angle */
    for (int i = 0; i < OW_MAX_PLANETS; i++) {
        if (!env->planets[i].active || !env->planet_orbits[i]) continue;
        if (env->planets[i].is_comet) continue; /* comets move via paths */

        double next_angle = env->planet_angle[i] + env->angular_velocity;
        env->planets[i].x = OW_SUN_X + env->planet_orbital_radius[i] * cos(env->planet_angle[i]);
        env->planets[i].y = OW_SUN_Y + env->planet_orbital_radius[i] * sin(env->planet_angle[i]);
        env->planet_angle[i] = next_angle;
    }

    /* Move comets along their paths */
    for (int gi = 0; gi < env->num_comet_groups; gi++) {
        CometGroupC* cg = &env->comet_groups[gi];
        if (!cg->active) continue;

        cg->path_index++;
        if (cg->path_index >= cg->num_steps) continue; /* will be expired next step */

        for (int m = 0; m < 4; m++) {
            /* Find the planet for this comet */
            for (int pi = 0; pi < OW_MAX_PLANETS; pi++) {
                if (!env->planets[pi].active) continue;
                if (env->planets[pi].id != cg->planet_ids[m]) continue;
                env->planets[pi].x = cg->paths_x[m][cg->path_index];
                env->planets[pi].y = cg->paths_y[m][cg->path_index];
                break;
            }
        }
    }
}

/* ========================================================================
 * Phase 7: Combat resolution
 * ======================================================================== */

static void ow_phase_combat_resolution(OrbitWars* env) {
    for (int pi = 0; pi < OW_MAX_PLANETS; pi++) {
        PlanetC* pl = &env->planets[pi];
        if (!pl->active) continue;

        /* Check if any forces arrived */
        int total_arrivals = 0;
        for (int p = 0; p < env->num_agents; p++) {
            total_arrivals += env->arriving_ships[pi][p];
        }
        if (total_arrivals == 0) continue;

        /* Find the two largest arriving forces */
        int largest = 0, largest_owner = -1;
        int second  = 0;
        for (int p = 0; p < env->num_agents; p++) {
            int s = env->arriving_ships[pi][p];
            if (s > largest) {
                second = largest;
                largest = s;
                largest_owner = p;
            } else if (s > second) {
                second = s;
            }
        }

        if (largest <= 0) continue;

        /* Resolve inter-fleet combat */
        int surviving;
        int surv_owner;
        if (largest > second) {
            surviving = largest - second;
            surv_owner = largest_owner;
        } else {
            /* Tie — all attacking ships destroyed */
            continue;
        }

        /* Surviving force interacts with garrison */
        if (surv_owner == pl->owner) {
            /* Reinforcement */
            pl->ships += surviving;
        } else {
            /* Attack garrison */
            if (surviving > pl->ships) {
                /* Attacker takes the planet */
                pl->ships = surviving - pl->ships;
                pl->owner = surv_owner;
            } else {
                /* Garrison holds */
                pl->ships -= surviving;
            }
        }
    }
}

/* ========================================================================
 * Game-over check
 * ======================================================================== */

static int ow_check_game_over(OrbitWars* env) {
    /* Step limit */
    if (env->current_step >= env->max_steps) return 1;

    /* Elimination: check how many players have assets */
    int players_alive = 0;
    for (int p = 0; p < env->num_agents; p++) {
        int has_assets = 0;
        for (int i = 0; i < OW_MAX_PLANETS; i++) {
            if (env->planets[i].active && env->planets[i].owner == p) {
                has_assets = 1; break;
            }
        }
        if (!has_assets) {
            for (int i = 0; i < OW_MAX_FLEETS; i++) {
                if (env->fleets[i].active && env->fleets[i].owner == p) {
                    has_assets = 1; break;
                }
            }
        }
        if (has_assets) players_alive++;
    }

    if (players_alive <= 1) return 1;
    return 0;
}

/* ========================================================================
 * End-of-game scoring and terminal handling
 * ======================================================================== */

static void ow_handle_game_over(OrbitWars* env) {
    /* Compute total ships per player */
    int total_ships[OW_MAX_PLAYERS] = {0};
    for (int i = 0; i < OW_MAX_PLANETS; i++) {
        PlanetC* p = &env->planets[i];
        if (p->active && p->owner >= 0 && p->owner < env->num_agents) {
            total_ships[p->owner] += p->ships;
        }
    }
    for (int i = 0; i < OW_MAX_FLEETS; i++) {
        FleetC* f = &env->fleets[i];
        if (f->active && f->owner >= 0 && f->owner < env->num_agents) {
            total_ships[f->owner] += f->ships;
        }
    }

    /* Find the maximum score */
    int max_ships = 0;
    for (int p = 0; p < env->num_agents; p++) {
        if (total_ships[p] > max_ships) max_ships = total_ships[p];
    }

    /* Set rewards and terminals for each agent slot */
    for (int slot = 0; slot < env->num_agents; slot++) {
        int player_id = -1;
        for (int p = 0; p < env->num_agents; p++) {
            if (env->slot_for_color[p] == slot) { player_id = p; break; }
        }
        if (player_id < 0) player_id = slot;

        float reward = -1.0f;
        if (max_ships > 0 && total_ships[player_id] == max_ships) {
            /* Check for tie */
            int num_winners = 0;
            for (int p = 0; p < env->num_agents; p++) {
                if (total_ships[p] == max_ships) num_winners++;
            }
            if (num_winners == 1) {
                reward = 1.0f;
            }
        }

        *env->reward_ptr[slot] = reward;
        *env->terminal_ptr[slot] = 1.0f;
    }

    /* Update log */
    int slot0_player = -1;
    for (int p = 0; p < env->num_agents; p++) {
        if (env->slot_for_color[p] == 0) { slot0_player = p; break; }
    }
    if (slot0_player < 0) slot0_player = 0;

    float primary_reward = *env->reward_ptr[0];
    float slot0_won = (primary_reward == 1.0f) ? 1.0f : 0.0f;
    env->log.perf = slot0_won;
    env->log.score = (float)total_ships[slot0_player];
    env->log.episode_return += primary_reward;
    env->log.episode_length = (float)env->current_step;
    env->log.n++;

    /* Historical self-play logging */
    if (env->tag > 0 && env->tag <= OW_MAX_BANKS) {
        int bank_idx = env->tag - 1;
        float primary_score = 0.0f;
        if (primary_reward == 1.0f) {
            primary_score = 1.0f; // Win
        } else {
            // Draw vs Loss check
            int num_winners = 0;
            for (int p = 0; p < env->num_agents; p++) {
                if (total_ships[p] == max_ships) num_winners++;
            }
            if (max_ships == 0 || num_winners > 1) {
                primary_score = 0.5f; // Draw
            } else {
                primary_score = 0.0f; // Loss
            }
        }
        env->log.hist_score_bank[bank_idx] += primary_score;
        env->log.hist_n_bank[bank_idx] += 1.0f;
        env->log.hist_score += primary_score;
        env->log.hist_n += 1.0f;
    }

    /* Self-play boundary */
    env->boundary_reached = 1;

    /* Reset for next episode */
    if (!env->prevent_reset) {
        c_reset(env);
    }
}

/* ========================================================================
 * c_step_core — runs game physics using raw_actions
 * This is the parity-testable entry point.
 * ======================================================================== */

void c_step_core(OrbitWars* env) {
    /* Clear combat accumulator */
    memset(env->arriving_ships, 0, sizeof(env->arriving_ships));


    /* Increment step */
    env->current_step++;

    /* Execute turn phases in order 
    this should be the right order as specified in original implementation:
    1. Comet expiration: Remove comets that have left the board.
    2. Comet spawning: Spawn new comet groups at designated steps.
    3. Fleet launch: Process all player actions, creating new fleets.
    4. Production: All owned planets (including comets) generate ships.
    5. Fleet movement: Move all fleets along their headings. Check for out-of-bounds, sun collision, and planet collision. Fleets that hit planets are queued for combat.
    6. Planet rotation & comet movement: Orbiting planets rotate, comets advance along their paths. Any fleet caught by a moving planet/comet is swept into combat with it.
    7. Combat resolution: Resolve all queued planet combats. */
    ow_phase_comet_expiration(env);
    ow_phase_comet_spawning(env);
    ow_phase_fleet_launch(env);
    ow_phase_production(env);
    ow_phase_fleet_movement(env);
    ow_phase_rotation_and_comets(env);
    ow_phase_comet_expiration(env);
    ow_phase_combat_resolution(env);

    /* Check game over */
    if (ow_check_game_over(env)) {
        ow_handle_game_over(env);
        return; /* c_reset was called inside handle_game_over */
    }

    /* Compute observations for next step */
    ow_compute_observations(env);
}

static int ow_find_comet_member(OrbitWars* env, int planet_id, CometGroupC** out_cg, int* out_member) {
    for (int gi = 0; gi < env->num_comet_groups; gi++) {
        CometGroupC* cg = &env->comet_groups[gi];
        if (!cg->active) continue;
        for (int m = 0; m < 4; m++) {
            if (cg->planet_ids[m] == planet_id) {
                if (out_cg) *out_cg = cg;
                if (out_member) *out_member = m;
                return 1;
            }
        }
    }
    return 0;
}


static int ow_planet_position_at_tick(OrbitWars* env, int pi, int tick, double* x, double* y) {
    PlanetC* pl = &env->planets[pi];
    if (!pl->active) return 0;

    EnvCache* cache = ow_get_cache(env);

    if (tick >= 0 && tick < 165) {
        if (cache->step[pi][tick] == env->current_step + 1) {
            char status = cache->result[pi][tick];
            if (status == 1) {
                *x = cache->x[pi][tick];
                *y = cache->y[pi][tick];
                return 1;
            } else if (status == 2) {
                return 0;
            }
        }
    }

    int res = 0;
    double rx = 0.0, ry = 0.0;

    if (pl->is_comet) {
        if (tick <= 0) {
            if (pl->x >= 0.0) {
                rx = pl->x;
                ry = pl->y;
                res = 1;
            }
        } else {
            CometGroupC* cg = NULL;
            int member = -1;
            if (ow_find_comet_member(env, pl->id, &cg, &member)) {
                int path_idx = cg->path_index + tick;
                if (path_idx >= 0 && path_idx < cg->num_steps) {
                    rx = cg->paths_x[member][path_idx];
                    ry = cg->paths_y[member][path_idx];
                    res = 1;
                }
            }
        }
    } else if (env->planet_orbits[pi]) {
        if (tick <= 0) {
            rx = pl->x;
            ry = pl->y;
            res = 1;
        } else {
            double angle = env->planet_angle[pi] + env->angular_velocity * (double)(tick - 1);
            rx = OW_SUN_X + env->planet_orbital_radius[pi] * cos(angle);
            ry = OW_SUN_Y + env->planet_orbital_radius[pi] * sin(angle);
            res = 1;
        }
    } else {
        rx = pl->x;
        ry = pl->y;
        res = pl->x >= 0.0;
    }

    if (tick >= 0 && tick < 165) {
        cache->x[pi][tick] = rx;
        cache->y[pi][tick] = ry;
        cache->result[pi][tick] = res ? 1 : 2;
        cache->step[pi][tick] = env->current_step + 1;
    }

    if (res) {
        *x = rx;
        *y = ry;
        return 1;
    }
    return 0;
}

static int ow_planet_position_at_time(OrbitWars* env, int pi, double t, double* x, double* y) {
    if (t < 0.0) return 0;
    int tick = (int)floor(t);
    double frac = t - (double)tick;
    double x0, y0, x1, y1;
    if (!ow_planet_position_at_tick(env, pi, tick, &x0, &y0)) return 0;
    if (frac <= 1e-9) {
        *x = x0;
        *y = y0;
        return 1;
    }
    if (!ow_planet_position_at_tick(env, pi, tick + 1, &x1, &y1)) {
        x1 = x0;
        y1 = y0;
    }
    *x = x0 + (x1 - x0) * frac;
    *y = y0 + (y1 - y0) * frac;
    return 1;
}

static int ow_planet_segment_for_turn(OrbitWars* env, int pi, int turn,
                                      double* x0, double* y0,
                                      double* x1, double* y1) {
    if (!ow_planet_position_at_tick(env, pi, turn, x0, y0)) return 0;
    if (*x0 < 0.0) return 0;
    if (!ow_planet_position_at_tick(env, pi, turn + 1, x1, y1)) {
        *x1 = *x0;
        *y1 = *y0;
    }
    return 1;
}

static float ow_swept_pair_t(double ax, double ay, double bx, double by,
                             double px0, double py0, double px1, double py1,
                             double r) {
    double d0x = ax - px0;
    double d0y = ay - py0;
    double dvx = (bx - ax) - (px1 - px0);
    double dvy = (by - ay) - (py1 - py0);
    double a = dvx * dvx + dvy * dvy;
    double b = 2.0 * (d0x * dvx + d0y * dvy);
    double c = d0x * d0x + d0y * d0y - r * r;
    if (c <= 0.0) return 0.0f;
    if (a < 1e-15) return -1.0f;
    double disc = b * b - 4.0 * a * c;
    if (disc < 0.0) return -1.0f;
    double sq = sqrt(disc);
    double t1 = (-b - sq) / (2.0 * a);
    double t2 = (-b + sq) / (2.0 * a);
    if (t1 >= 0.0 && t1 <= 1.0) return (float)t1;
    if (t2 >= 0.0 && t2 <= 1.0) return (float)t2;
    return -1.0f;
}

static float ow_segment_oob_t(double x0, double y0, double x1, double y1) {
    if (x0 < 0.0 || x0 > OW_BOARD_SIZE || y0 < 0.0 || y0 > OW_BOARD_SIZE) return 0.0f;
    if (x1 >= 0.0 && x1 <= OW_BOARD_SIZE && y1 >= 0.0 && y1 <= OW_BOARD_SIZE) return -1.0f;

    double best = 2.0;
    double dx = x1 - x0;
    double dy = y1 - y0;
    if (dx < 0.0) {
        double t = (0.0 - x0) / dx;
        if (t >= 0.0 && t <= 1.0 && t < best) best = t;
    } else if (dx > 0.0) {
        double t = (OW_BOARD_SIZE - x0) / dx;
        if (t >= 0.0 && t <= 1.0 && t < best) best = t;
    }
    if (dy < 0.0) {
        double t = (0.0 - y0) / dy;
        if (t >= 0.0 && t <= 1.0 && t < best) best = t;
    } else if (dy > 0.0) {
        double t = (OW_BOARD_SIZE - y0) / dy;
        if (t >= 0.0 && t <= 1.0 && t < best) best = t;
    }
    return best <= 1.0 ? (float)best : 0.0f;
}

static int ow_aim_horizon_turns(OrbitWars* env, double speed) {
    int horizon = OW_MAX_STEPS - env->current_step;
    if (horizon <= 0) return 0;
    if (horizon > OW_MAX_STEPS) horizon = OW_MAX_STEPS;
    if (speed < 1e-6) return horizon;

    int board_horizon = (int)ceil(160.0 / speed) + 2;
    if (board_horizon < 1) board_horizon = 1;
    if (horizon > board_horizon) horizon = board_horizon;
    return horizon;
}

static double ow_ray_circle_distance(double x, double y, double dx, double dy,
                                     double cx, double cy, double r) {
    double fx = x - cx;
    double fy = y - cy;
    double b = 2.0 * (fx * dx + fy * dy);
    double c = fx * fx + fy * fy - r * r;
    if (c <= 0.0) return 0.0;
    double disc = b * b - 4.0 * c;
    if (disc < 0.0) return -1.0;
    double sq = sqrt(disc);
    double d1 = (-b - sq) * 0.5;
    double d2 = (-b + sq) * 0.5;
    if (d1 >= 0.0) return d1;
    if (d2 >= 0.0) return d2;
    return -1.0;
}

static double ow_ray_oob_distance(double x, double y, double dx, double dy) {
    if (x < 0.0 || x > OW_BOARD_SIZE || y < 0.0 || y > OW_BOARD_SIZE) return 0.0;
    double best = 1e30;
    if (dx > 1e-12) {
        double d = (OW_BOARD_SIZE - x) / dx;
        if (d >= 0.0 && d < best) best = d;
    } else if (dx < -1e-12) {
        double d = (0.0 - x) / dx;
        if (d >= 0.0 && d < best) best = d;
    }
    if (dy > 1e-12) {
        double d = (OW_BOARD_SIZE - y) / dy;
        if (d >= 0.0 && d < best) best = d;
    } else if (dy < -1e-12) {
        double d = (0.0 - y) / dy;
        if (d >= 0.0 && d < best) best = d;
    }
    return best < 1e29 ? best : -1.0;
}

static int ow_validate_static_target_angle(OrbitWars* env, int src_idx, int tgt_idx,
                                           int ships, float angle) {
    PlanetC* src = &env->planets[src_idx];
    PlanetC* tgt = &env->planets[tgt_idx];
    if (!src->active || !tgt->active || ships <= 0 || tgt->x < 0.0) return 0;

    double dx = cos((double)angle);
    double dy = sin((double)angle);
    double x = src->x + (src->radius + (double)OW_FLEET_SPAWN_OFFSET) * dx;
    double y = src->y + (src->radius + (double)OW_FLEET_SPAWN_OFFSET) * dy;
    double speed = ow_fleet_speed(ships);
    int horizon = ow_aim_horizon_turns(env, speed);
    if (horizon <= 0) return 0;

    double target_dist = ow_ray_circle_distance(x, y, dx, dy, tgt->x, tgt->y, tgt->radius);
    if (target_dist < 0.0) return 0;
    double target_time = target_dist / speed;
    if (target_time > (double)horizon + 1e-6) return 0;

    double oob_dist = ow_ray_oob_distance(x, y, dx, dy);
    if (oob_dist >= 0.0 && oob_dist <= target_dist + 1e-5) return 0;

    double sun_dist = ow_ray_circle_distance(x, y, dx, dy, OW_SUN_X, OW_SUN_Y, OW_SUN_RADIUS);
    if (sun_dist >= 0.0 && sun_dist <= target_dist + 1e-5) return 0;

    for (int pi = 0; pi < OW_MAX_PLANETS; pi++) {
        if (pi == tgt_idx) continue;
        PlanetC* pl = &env->planets[pi];
        if (!pl->active || pl->x < 0.0) continue;
        if (env->planet_orbits[pi] || pl->is_comet) continue;
        double blocker_dist = ow_ray_circle_distance(x, y, dx, dy, pl->x, pl->y, pl->radius);
        if (blocker_dist >= 0.0 && blocker_dist <= target_dist + 1e-5) return 0;
    }

    int max_turn = (int)ceil(target_time);
    if (max_turn > horizon) max_turn = horizon;
    double fx = x;
    double fy = y;
    for (int turn = 0; turn <= max_turn; turn++) {
        double nx = fx + speed * dx;
        double ny = fy + speed * dy;
        for (int pi = 0; pi < OW_MAX_PLANETS; pi++) {
            if (pi == tgt_idx) continue;
            PlanetC* pl = &env->planets[pi];
            if (!pl->active || (!env->planet_orbits[pi] && !pl->is_comet)) continue;

            double px0, py0, px1, py1;
            if (!ow_planet_segment_for_turn(env, pi, turn, &px0, &py0, &px1, &py1)) continue;
            float hit_t = ow_swept_pair_t(fx, fy, nx, ny, px0, py0, px1, py1, pl->radius);
            if (hit_t >= 0.0f && (double)turn + (double)hit_t <= target_time + 1e-5) return 0;
        }
        fx = nx;
        fy = ny;
    }

    return 1;
}

static int ow_validate_launch_angle(OrbitWars* env, int src_idx, int tgt_idx, int ships,
                                    float angle, float* out_hit_turns) {
    PlanetC* src = &env->planets[src_idx];
    PlanetC* tgt = &env->planets[tgt_idx];
    if (!src->active || !tgt->active || ships <= 0 || tgt->x < 0.0) return 0;

    double dx = cos((double)angle);
    double dy = sin((double)angle);
    double x = src->x + (src->radius + (double)OW_FLEET_SPAWN_OFFSET) * dx;
    double y = src->y + (src->radius + (double)OW_FLEET_SPAWN_OFFSET) * dy;
    double speed = ow_fleet_speed(ships);
    int horizon = ow_aim_horizon_turns(env, speed);
    if (horizon <= 0) return 0;

    for (int turn = 0; turn < horizon; turn++) {
        double nx = x + speed * dx;
        double ny = y + speed * dy;
        float target_t = -1.0f;
        float blocker_t = -1.0f;
        int blocker_idx = -1;

        for (int pi = 0; pi < OW_MAX_PLANETS; pi++) {
            PlanetC* pl = &env->planets[pi];
            if (!pl->active) continue;

            double px0, py0, px1, py1;
            if (!ow_planet_segment_for_turn(env, pi, turn, &px0, &py0, &px1, &py1)) continue;
            float hit_t = ow_swept_pair_t(x, y, nx, ny, px0, py0, px1, py1, pl->radius);
            if (hit_t < 0.0f) continue;

            if (pi == tgt_idx) {
                if (target_t < 0.0f || hit_t < target_t) target_t = hit_t;
            } else if (blocker_t < 0.0f || hit_t < blocker_t) {
                blocker_t = hit_t;
                blocker_idx = pi;
            }
        }

        float oob_t = ow_segment_oob_t(x, y, nx, ny);
        float sun_t = ow_segment_circle_t((float)x, (float)y, (float)nx, (float)ny,
                                          OW_SUN_X, OW_SUN_Y, OW_SUN_RADIUS);
        const float eps = 1e-5f;
        if (target_t >= 0.0f) {
            if (blocker_t >= 0.0f && (blocker_t <= target_t + eps || blocker_idx < tgt_idx)) return 0;
            if (oob_t >= 0.0f && oob_t <= target_t + eps) return 0;
            if (sun_t >= 0.0f && sun_t <= target_t + eps) return 0;
            if (out_hit_turns) *out_hit_turns = (float)turn + target_t;
            return 1;
        }

        if (blocker_t >= 0.0f || oob_t >= 0.0f || sun_t >= 0.0f) return 0;
        x = nx;
        y = ny;
    }

    return 0;
}

static int ow_launch_time_error(OrbitWars* env, int src_idx, int tgt_idx, double speed,
                                double t, double* err) {
    PlanetC* src = &env->planets[src_idx];
    double tx, ty;
    if (!ow_planet_position_at_time(env, tgt_idx, t, &tx, &ty)) return 0;
    double angle = atan2(ty - src->y, tx - src->x);
    double spawn_x = src->x + (src->radius + (double)OW_FLEET_SPAWN_OFFSET) * cos(angle);
    double spawn_y = src->y + (src->radius + (double)OW_FLEET_SPAWN_OFFSET) * sin(angle);
    *err = hypot(tx - spawn_x, ty - spawn_y) / speed - t;
    return 1;
}

static double ow_refine_intercept_time(OrbitWars* env, int src_idx, int tgt_idx,
                                       double speed, double lo, double hi) {
    double flo = 0.0, hi_err = 0.0;
    if (!ow_launch_time_error(env, src_idx, tgt_idx, speed, lo, &flo)) return lo;
    if (!ow_launch_time_error(env, src_idx, tgt_idx, speed, hi, &hi_err)) return hi;

    for (int iter = 0; iter < 12; iter++) {
        double mid = 0.5 * (lo + hi);
        double fmid = 0.0;
        if (!ow_launch_time_error(env, src_idx, tgt_idx, speed, mid, &fmid)) break;

        double t = mid;
        double deriv = 0.0;
        double left = mid - 1e-3;
        double right = mid + 1e-3;
        if (left > lo && right < hi) {
            double fl = 0.0, fr = 0.0;
            if (ow_launch_time_error(env, src_idx, tgt_idx, speed, left, &fl) &&
                ow_launch_time_error(env, src_idx, tgt_idx, speed, right, &fr)) {
                deriv = (fr - fl) / (right - left);
            }
        }
        if (fabs(deriv) > 1e-6) {
            double nt = mid - fmid / deriv;
            if (nt > lo && nt < hi) t = nt;
        }
        double ft = 0.0;
        if (!ow_launch_time_error(env, src_idx, tgt_idx, speed, t, &ft)) break;

        if ((flo <= 0.0 && ft <= 0.0) || (flo >= 0.0 && ft >= 0.0)) {
            lo = t;
            flo = ft;
        } else {
            hi = t;
        }
    }

    return 0.5 * (lo + hi);
}

static int ow_try_aim_at_time(OrbitWars* env, int src_idx, int tgt_idx, int ships,
                              double t, float* out_angle) {
    PlanetC* src = &env->planets[src_idx];
    double tx, ty;
    if (!ow_planet_position_at_time(env, tgt_idx, t, &tx, &ty)) return 0;
    float angle = ow_norm_angle((float)atan2(ty - src->y, tx - src->x));
    if (!ow_validate_launch_angle(env, src_idx, tgt_idx, ships, angle, NULL)) return 0;
    *out_angle = angle;
    return 1;
}

static int ow_find_validated_moving_aim(OrbitWars* env, int src_idx, int tgt_idx,
                                        int ships, float* out_angle) {
    double speed = ow_fleet_speed(ships);
    int horizon = ow_aim_horizon_turns(env, speed);
    if (horizon <= 0) return 0;

    double best_t[4] = {-1.0, -1.0, -1.0, -1.0};
    double best_abs[4] = {1e30, 1e30, 1e30, 1e30};
    double prev_t = 0.0;
    double prev_err = 0.0;
    int prev_ok = ow_launch_time_error(env, src_idx, tgt_idx, speed, prev_t, &prev_err);

    for (int ti = 1; ti <= horizon; ti++) {
        double t = (double)ti;
        double err = 0.0;
        int ok = ow_launch_time_error(env, src_idx, tgt_idx, speed, t, &err);
        if (ok) {
            double aerr = fabs(err);
            for (int k = 0; k < 4; k++) {
                if (aerr < best_abs[k]) {
                    for (int j = 3; j > k; j--) {
                        best_abs[j] = best_abs[j - 1];
                        best_t[j] = best_t[j - 1];
                    }
                    best_abs[k] = aerr;
                    best_t[k] = t;
                    break;
                }
            }

            if (prev_ok && ((prev_err >= 0.0 && err <= 0.0) ||
                            (prev_err <= 0.0 && err >= 0.0))) {
                double root = ow_refine_intercept_time(env, src_idx, tgt_idx, speed, prev_t, t);
                if (ow_try_aim_at_time(env, src_idx, tgt_idx, ships, root, out_angle)) return 1;
            }
            prev_t = t;
            prev_err = err;
            prev_ok = 1;
        } else {
            prev_t = t;
            prev_ok = 0;
        }
    }

    for (int k = 0; k < 4; k++) {
        if (best_t[k] >= 0.0 && best_abs[k] <= 2.0 &&
            ow_try_aim_at_time(env, src_idx, tgt_idx, ships, best_t[k], out_angle)) {
            return 1;
        }
    }
    return 0;
}

static int ow_aim_angle_to_planet(OrbitWars* env, int src_idx, int tgt_idx, int ships, float* out_angle) {
    PlanetC* src = &env->planets[src_idx];
    PlanetC* tgt = &env->planets[tgt_idx];
    if (!src->active || !tgt->active || ships <= 0 || tgt->x < 0.0) return 0;

    if (env->planet_orbits[tgt_idx] || tgt->is_comet) {
        return ow_find_validated_moving_aim(env, src_idx, tgt_idx, ships, out_angle);
    }

    float direct_angle = ow_norm_angle((float)atan2(tgt->y - src->y, tgt->x - src->x));
    if (ow_validate_static_target_angle(env, src_idx, tgt_idx, ships, direct_angle)) {
        *out_angle = direct_angle;
        return 1;
    }

    return 0;
}

static double ow_lite_action_to_board(float v) {
    return 0.5 * OW_BOARD_SIZE * ((double)ow_clampf(v, -1.0f, 1.0f) + 1.0);
}

static int ow_lite_amount_to_ships(float amount, int available) {
    if (available <= 0 || amount <= OW_LITE_AMOUNT_EPS) return 0;

    float u = ow_clampf(amount, 0.0f, 1.0f);
    int ships = (int)roundf(u * 200.0f);
    if (ships > available) ships = available;
    return ships;
}

static int ow_lite_nearest_source(OrbitWars* env, int player_id, double x, double y,
                                  const int used[OW_MAX_PLANETS]) {
    int best = -1;
    double best_d2 = 1e30;
    for (int pi = 0; pi < OW_MAX_PLANETS; pi++) {
        PlanetC* pl = &env->planets[pi];
        if (!pl->active || pl->owner != player_id || pl->ships <= 1 || used[pi]) continue;
        if (pl->x < 0.0) continue;
        double dx = pl->x - x;
        double dy = pl->y - y;
        double d2 = dx * dx + dy * dy;
        if (d2 < best_d2) {
            best_d2 = d2;
            best = pi;
        }
    }
    return best;
}

static int ow_decode_lite_actions_for_slot(OrbitWars* env, int slot, const float* act) {
    int player_id = ow_player_for_slot(env, slot);
    int source_used[OW_MAX_PLANETS] = {0};
    int active_slots[OW_LITE_MAX_ACTIVE_SLOTS];
    float active_amounts[OW_LITE_MAX_ACTIVE_SLOTS];
    int launches = 0;

    for (int i = 0; i < OW_LITE_MAX_ACTIVE_SLOTS; i++) {
        active_slots[i] = -1;
        active_amounts[i] = OW_LITE_AMOUNT_EPS;
    }

    for (int s = 0; s < OW_LITE_LAUNCH_SLOTS; s++) {
        int base = s * OW_LITE_ATN_FEAT;
        float amount = ow_clampf(act[base + 0], -1.0f, 1.0f);
        if (amount <= OW_LITE_AMOUNT_EPS) continue;
        for (int pos = 0; pos < OW_LITE_MAX_ACTIVE_SLOTS; pos++) {
            if (amount > active_amounts[pos]) {
                for (int move = OW_LITE_MAX_ACTIVE_SLOTS - 1; move > pos; move--) {
                    active_slots[move] = active_slots[move - 1];
                    active_amounts[move] = active_amounts[move - 1];
                }
                active_slots[pos] = s;
                active_amounts[pos] = amount;
                break;
            }
        }
    }

    for (int pos = 0; pos < OW_LITE_MAX_ACTIVE_SLOTS && launches < OW_MAX_ACTIONS_PER_PLAYER; pos++) {
        int s = active_slots[pos];
        if (s < 0) continue;
        int base = s * OW_LITE_ATN_FEAT;
        float amount = active_amounts[pos];

        float dir_x = ow_clampf(act[base + 1], -1.0f, 1.0f);
        float dir_y = ow_clampf(act[base + 2], -1.0f, 1.0f);
        float dir_len2 = dir_x * dir_x + dir_y * dir_y;
        if (dir_len2 < 1e-6f) continue;

        double sx = ow_lite_action_to_board(act[base + 3]);
        double sy = ow_lite_action_to_board(act[base + 4]);
        int src_idx = ow_lite_nearest_source(env, player_id, sx, sy, source_used);
        if (src_idx < 0) continue;

        int available = env->planets[src_idx].ships - 1;
        int ships = ow_lite_amount_to_ships(amount, available);
        if (ships <= 0) continue;

        int ai = env->num_raw_actions[player_id];
        if (ai >= OW_MAX_ACTIONS_PER_PLAYER) break;

        float angle = ow_norm_angle((float)atan2f(dir_y, dir_x));

        env->raw_actions[player_id][ai] = (RawActionC){
            .from_planet_id = env->planets[src_idx].id,
            .angle = angle,
            .ships = ships
        };
        env->num_raw_actions[player_id]++;
        source_used[src_idx] = 1;
        launches++;
    }

    return launches;
}

typedef struct {
    int slot;
    int planet_idx;
    float x;
    float r;
    float strength;
} OWIntervalNode;

static int ow_decode_interval_actions_for_slot(OrbitWars* env, int slot, const float* act) {
    int player_id = ow_player_for_slot(env, slot);
    int slots[OW_MAX_PLANETS];
    int budgets[OW_MAX_PLANETS] = {0};
    OWIntervalNode sources[OW_MAX_PLANETS];
    OWIntervalNode sinks[OW_MAX_PLANETS];
    int num_sources = 0;
    int num_sinks = 0;
    int launches = 0;

    ow_planet_slots_by_id(env, slots);

    for (int s = 0; s < OW_MAX_PLANETS; s++) {
        int pi = slots[s];
        if (pi < 0) continue;
        PlanetC* pl = &env->planets[pi];
        float x = ow_clampf(act[2 * s + 0], -1.0f, 1.0f);
        float r = ow_clampf(act[2 * s + 1], -1.0f, 1.0f);
        if (r > OW_INTERVAL_EPS && pl->owner == player_id && pl->ships > 1) {
            budgets[pi] = pl->ships - 1;
            sources[num_sources++] = (OWIntervalNode){s, pi, x, r, 0.0f};
        } else if (r < -OW_INTERVAL_EPS) {
            sinks[num_sinks++] = (OWIntervalNode){s, pi, x, r, 0.0f};
        }
    }

    for (int ti = 0; ti < num_sinks; ti++) {
        float total = 0.0f;
        for (int si = 0; si < num_sources; si++) {
            if (sources[si].planet_idx == sinks[ti].planet_idx) continue;
            total += ow_interval_pair_strength(sources[si].x, sources[si].r, sinks[ti].x, sinks[ti].r);
        }
        sinks[ti].strength = total;
    }

    for (int pass = 0; pass < OW_MAX_TARGETS && launches < OW_MAX_ACTIONS_PER_PLAYER; pass++) {
        int best_ti = -1;
        for (int ti = 0; ti < num_sinks; ti++) {
            if (sinks[ti].strength <= 0.0f) continue;
            if (best_ti < 0 || sinks[ti].strength > sinks[best_ti].strength) best_ti = ti;
        }
        if (best_ti < 0) break;

        PlanetC* tgt = &env->planets[sinks[best_ti].planet_idx];
        int selected[OW_MAX_SOURCES_PER_TARGET];
        float selected_strength[OW_MAX_SOURCES_PER_TARGET];
        int selected_n = 0;
        float selected_total = 0.0f;
        for (int k = 0; k < OW_MAX_SOURCES_PER_TARGET; k++) {
            selected[k] = -1;
            selected_strength[k] = 0.0f;
        }

        for (int si = 0; si < num_sources; si++) {
            int src_idx = sources[si].planet_idx;
            if (src_idx == sinks[best_ti].planet_idx || budgets[src_idx] <= 0) continue;
            float strength = ow_interval_pair_strength(sources[si].x, sources[si].r, sinks[best_ti].x, sinks[best_ti].r);
            if (strength <= 0.0f) continue;
            for (int pos = 0; pos < OW_MAX_SOURCES_PER_TARGET; pos++) {
                if (selected[pos] < 0 || strength > selected_strength[pos]) {
                    for (int move = OW_MAX_SOURCES_PER_TARGET - 1; move > pos; move--) {
                        selected[move] = selected[move - 1];
                        selected_strength[move] = selected_strength[move - 1];
                    }
                    selected[pos] = si;
                    selected_strength[pos] = strength;
                    break;
                }
            }
        }

        for (int k = 0; k < OW_MAX_SOURCES_PER_TARGET; k++) {
            if (selected[k] >= 0) {
                selected_n++;
                selected_total += selected_strength[k];
            }
        }

        if (selected_n > 0 && selected_total > 0.0f) {
            int target_need;
            if (tgt->owner == player_id) {
                target_need = tgt->production * 4 + 1;
                if (target_need < 2) target_need = 2;
            } else {
                target_need = tgt->ships + 1;
                if (tgt->owner >= 0) target_need += tgt->production * 3;
            }

            int planned[OW_MAX_SOURCES_PER_TARGET] = {0};
            int planned_total = 0;
            for (int k = 0; k < OW_MAX_SOURCES_PER_TARGET && launches < OW_MAX_ACTIONS_PER_PLAYER; k++) {
                int si = selected[k];
                if (si < 0) continue;
                int src_idx = sources[si].planet_idx;
                int share = (int)ceilf((float)target_need * (selected_strength[k] / selected_total));
                if (share > budgets[src_idx]) share = budgets[src_idx];
                if (share < 0) share = 0;
                planned[k] = share;
                planned_total += share;
            }

            int remaining = target_need - planned_total;
            while (remaining > 0) {
                int best_k = -1;
                for (int k = 0; k < OW_MAX_SOURCES_PER_TARGET; k++) {
                    int si = selected[k];
                    if (si < 0) continue;
                    int src_idx = sources[si].planet_idx;
                    if (planned[k] >= budgets[src_idx]) continue;
                    if (best_k < 0 || selected_strength[k] > selected_strength[best_k]) best_k = k;
                }
                if (best_k < 0) break;
                int src_idx = sources[selected[best_k]].planet_idx;
                int add = budgets[src_idx] - planned[best_k];
                if (add > remaining) add = remaining;
                planned[best_k] += add;
                remaining -= add;
            }

            for (int k = 0; k < OW_MAX_SOURCES_PER_TARGET && launches < OW_MAX_ACTIONS_PER_PLAYER; k++) {
                int si = selected[k];
                if (si < 0) continue;
                int src_idx = sources[si].planet_idx;
                int share = planned[k];
                if (share <= 0) continue;

                int ai = env->num_raw_actions[player_id];
                if (ai >= OW_MAX_ACTIONS_PER_PLAYER) break;
                float angle = 0.0f;
                if (!ow_aim_angle_to_planet(env, src_idx, sinks[best_ti].planet_idx, share, &angle)) {
                    continue;
                }
                env->raw_actions[player_id][ai] = (RawActionC){
                    .from_planet_id = env->planets[src_idx].id,
                    .angle = angle,
                    .ships = share
                };
                env->num_raw_actions[player_id]++;
                budgets[src_idx] -= share;
                launches++;
            }
        }

        sinks[best_ti].strength = -1.0f;
    }

    return launches;
}

/* ========================================================================
 * c_step — decode lite coordinate actions, then call c_step_core
 * ======================================================================== */

void c_step(OrbitWars* env) {
    /* Clear raw actions */
    for (int p = 0; p < env->num_agents; p++) {
        env->num_raw_actions[p] = 0;
    }

    for (int slot = 0; slot < env->num_agents; slot++) {
        ow_decode_lite_actions_for_slot(env, slot, env->action_ptr[slot]);
    }

    /* Run physics */
    c_step_core(env);
}

/* ========================================================================
 * c_render — empty stub (no rendering for now)
 * ======================================================================== */

void c_render(OrbitWars* env) {
    (void)env;
}

/* ========================================================================
 * c_close — free allocated resources
 * ======================================================================== */

void c_close(OrbitWars* env) {
    if (env->client != NULL) {
        free(env->client);
        env->client = NULL;
    }
}
