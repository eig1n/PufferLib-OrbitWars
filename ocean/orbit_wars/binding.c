#include "orbit_wars.h"
#define OBS_SIZE 6484      /* 48*7 + 1024*6 + 4 */
#define NUM_ATNS 3         /* planet_idx, angle_bucket, ship_bucket */
#define ACT_SIZES {48, 64, 16}
#define OBS_TENSOR_T FloatTensor

#define MY_USES_PERM
#define MY_USES_TAGS
#define Env OrbitWars
#include "vecenv.h"

/*
 * my_setup_perm — populate per-slot pointer arrays on the env,
 * given the global slot base for slot 0 of this env.
 * Follows the chess binding pattern.
 */
void my_setup_perm(StaticVec* vec, Env* env, int slot_base) {
    size_t obs_elem_size = obs_element_size();
    for (int s = 0; s < env->num_agents; s++) {
        int phys = vec->agent_perm ? vec->agent_perm[slot_base + s] : (slot_base + s);
        env->obs_ptr[s]    = (float*)((char*)vec->observations + (size_t)phys * OBS_SIZE * obs_elem_size);
        env->action_ptr[s] = vec->actions + (size_t)phys * NUM_ATNS;
        env->reward_ptr[s] = vec->rewards + phys;
        env->terminal_ptr[s] = vec->terminals + phys;
    }
}

/*
 * my_init — called for each env during vec creation.
 * Reads num_agents from kwargs (default 2 for 1v1).
 */
void my_init(Env* env, Dict* kwargs) {
    DictItem* na_item = dict_get_unsafe(kwargs, "num_agents");
    env->num_agents = na_item ? (int)na_item->value : 2;
    if (env->num_agents < 2) env->num_agents = 2;
    if (env->num_agents > 4) env->num_agents = 4;

    /* Initialize slot_for_color: randomize to avoid positional bias */
    for (int i = 0; i < env->num_agents; i++) {
        env->slot_for_color[i] = i;
    }
    /* Fisher-Yates shuffle using env rng */
    for (int i = env->num_agents - 1; i > 0; i--) {
        int j = rand_r(&env->rng) % (i + 1);
        int tmp = env->slot_for_color[i];
        env->slot_for_color[i] = env->slot_for_color[j];
        env->slot_for_color[j] = tmp;
    }

    init(env);
}

/*
 * my_log — export metrics to Python.
 */
void my_log(Log* log, Dict* out) {
    dict_set(out, "perf", log->perf);
    dict_set(out, "score", log->score);
    dict_set(out, "episode_return", log->episode_return);
    dict_set(out, "episode_length", log->episode_length);
}
