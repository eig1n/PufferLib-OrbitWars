import sys
import os
import json
from kaggle_environments import make

# Resolve repository root
current_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.abspath(os.path.join(current_dir, ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
    sys.path.insert(0, os.path.join(repo_root, "orbit-wars"))

def run(agent_a, agent_b, seeds=range(20)):
    name_a = os.path.basename(agent_a).replace(".py", "")
    name_b = agent_b if agent_b == "random" else os.path.basename(agent_b).replace(".py", "")

    wins = {name_a: 0, name_b: 0}
    ties = 0

    log_dir = os.path.join(repo_root, "logs")
    os.makedirs(log_dir, exist_ok=True)
    replay_dir = os.path.join(log_dir, "replays")
    os.makedirs(replay_dir, exist_ok=True)

    log_file_path = os.path.join(log_dir, f"evaluation_{name_a}_vs_{name_b}.log")
    
    # Fully qualified agent paths for kaggle-environments
    agent_a_path = agent_a if agent_a == "random" else os.path.join(repo_root, agent_a)
    agent_b_path = agent_b if agent_b == "random" else os.path.join(repo_root, agent_b)

    print(f"Starting evaluation match: {name_a} vs {name_b}")
    print(f"Log path: {log_file_path}")
    print(f"Replays path: {replay_dir}/")
    print("=" * 60)

    with open(log_file_path, "w") as log_file:
        log_file.write(f"Evaluation Match: {name_a} vs {name_b}\n")
        log_file.write("=" * 60 + "\n\n")

        for seed in seeds:
            env = make("orbit_wars", configuration={"seed": seed}, debug=True)
            env.run([agent_a_path, agent_b_path])
            rewards = [s.reward for s in env.steps[-1]]
            
            # Save replay json
            replay_path = os.path.join(replay_dir, f"seed_{seed}.json")
            with open(replay_path, "w") as f:
                json.dump(env.toJSON(), f)

            if rewards[0] is None or rewards[1] is None:
                msg = f"Seed {seed}: One of the rewards is None (likely a crash / error)\n"
                print(msg, end="")
                log_file.write(msg)
                for i, step in enumerate(env.steps):
                    for player_step in step:
                        if player_step.status == "ERROR":
                            err_msg = f"  Error at step {i}: {player_step}\n"
                            print(err_msg, end="")
                            log_file.write(err_msg)
                continue
                
            if rewards[0] > rewards[1]:
                wins[name_a] += 1
                winner = name_a
            elif rewards[1] > rewards[0]:
                wins[name_b] += 1
                winner = name_b
            else:
                ties += 1
                winner = "Tie"
                
            msg = f"Seed {seed}: Winner={winner} | rewards: {name_a}={rewards[0]}, {name_b}={rewards[1]} | steps={len(env.steps)}\n"
            print(msg, end="")
            log_file.write(msg)
            
        summary = f"\nFinal Result:\n{name_a}_wins: {wins[name_a]}, {name_b}_wins: {wins[name_b]}, ties: {ties}\n"
        print(summary)
        log_file.write(summary)
        
    print(f"\nEvaluation finished. Logs saved to: {log_file_path}")

if __name__ == "__main__":
    run("orbit-wars/puffer_agent/main.py", "orbit-wars/main.py")
