#include "orbit_wars.h"
#define OBS_SIZE OW_OBS_SIZE
#define NUM_ATNS OW_NUM_ATNS
#define ACT_SIZES { \
    1, 1, 1, 1, 1, \
    1, 1, 1, 1, 1, \
    1, 1, 1, 1, 1, \
    1, 1, 1, 1, 1, \
    1, 1, 1, 1, 1, \
    1, 1, 1, 1, 1  \
}
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
    dict_set(out, "hist_score", log->hist_score);
    dict_set(out, "hist_n", log->hist_n);
    dict_set(out, "hist_score_bank_0", log->hist_score_bank[0]);
    dict_set(out, "hist_score_bank_1", log->hist_score_bank[1]);
    dict_set(out, "hist_score_bank_2", log->hist_score_bank[2]);
    dict_set(out, "hist_score_bank_3", log->hist_score_bank[3]);
    dict_set(out, "hist_score_bank_4", log->hist_score_bank[4]);
    dict_set(out, "hist_score_bank_5", log->hist_score_bank[5]);
    dict_set(out, "hist_score_bank_6", log->hist_score_bank[6]);
    dict_set(out, "hist_score_bank_7", log->hist_score_bank[7]);
    dict_set(out, "hist_n_bank_0", log->hist_n_bank[0]);
    dict_set(out, "hist_n_bank_1", log->hist_n_bank[1]);
    dict_set(out, "hist_n_bank_2", log->hist_n_bank[2]);
    dict_set(out, "hist_n_bank_3", log->hist_n_bank[3]);
    dict_set(out, "hist_n_bank_4", log->hist_n_bank[4]);
    dict_set(out, "hist_n_bank_5", log->hist_n_bank[5]);
    dict_set(out, "hist_n_bank_6", log->hist_n_bank[6]);
    dict_set(out, "hist_n_bank_7", log->hist_n_bank[7]);
}
