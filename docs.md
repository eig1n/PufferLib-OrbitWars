### Key Features
*   **PuffeRL**: 20,000,000 step/second training in only ~5k lines of CUDA. Torch version up to 5,000,000.
*   **Ocean**: 20+ environments from simple arcade games to massively multiagent sims.
*   **Constellation**: Performant experiment local + web visualization toolkit in C.
*   **Protein**: Our algorithm for automatic hyperparameter and reward tuning.

---

## Installation

### Docker
```bash
git clone https://github.com/pufferai/puffertank
cd puffertank
./docker.sh test
```
*PufferLib uses CUDA, cuBLAS, NCCL, and Nsight. Use ssh -X on setup for remote work or graphics won't work.*

### UV
```bash
curl https://raw.githubusercontent.com/PufferAI/PufferTank/refs/heads/4.0/install.sh | sh
```
*Requires CUDA. If you don't want to deal with CUDA deps, use the Dockerfile.*

### Installation Test
```bash
bash build.sh breakout
puffer train breakout
puffer eval breakout --load-model-path latest
```

---

## Cheat Sheet

### PufferLib CLI
```bash
puffer [train|eval|sweep] env_name [OPTIONS]
python -m pufferlib.pufferl [train|eval|sweep] env_name [OPTIONS]
```

### Building PufferLib
*   `bash build.sh ENV_NAME`: Build training for a specific environment
*   `bash build.sh ENV_NAME --float`: Use fp32 backend (default is bf16)
*   `bash build.sh ENV_NAME --profile`: Build our profiling tools
*   `bash build.sh ENV_NAME --[local|fast|web]`: Build debug/optimized/web env standalones (no training)
*   `bash build.sh constellation --[local|fast|web]`: Build Constellation experiment dashboard

### Examples
```bash
# Train with custom params
puffer train breakout --train.learning-rate 0.001
puffer train breakout --env.frameskip 3
puffer train breakout --vec.num-threads 4

# Track with Weights and Biases
puffer train breakout --wandb --tag tag_name

# Eval
puffer eval breakout # Render with random agent
puffer eval breakout --load-model-path path/model_file
puffer eval breakout --load-model-path latest

# Distributed training and Sweeps
puffer sweep breakout # Run hyperparameter sweep
puffer sweep breakout --sweep.gpus N # Sweep with 6 GPUs
puffer train nmmo3 --train.gpus N # Distributed training
```

### Torch
*   `bash build.sh ENV_NAME --float`: Torch is not stable in bf16
*   `bash build.sh ENV_NAME --cpu`: Mostly for Mac users (Expect < 200k sps)
*   **Torch Distributed**: 
    `torchrun --standalone --nnodes=1 --nproc-per-node=6 -m pufferlib.pufferl train nmmo3 --slowly`

---

## About PufferLib

*   **Implementation**: PufferLib 4.0 native backend is ~1500 lines of Python and ~5000 lines of CUDA C. A PyTorch backend is provided for quick prototyping.
*   **Memory Management**: Tensors are structs with a shape and data pointer. Allocators sum up sizes and perform a single allocation of continuous memory. No tensors are created or reallocated after initialization.
*   **Tracing**: Uses Cudagraphs to capture and replay GPU operations to reduce kernel launch overhead.
*   **Vectorization**: Environment instances are chunked into buffers, each associated with a rollout worker on a separate CUDA stream.
*   **Kernels**: Focuses on fusing small elementwise operations to reduce memory bandwidth.
*   **Algorithm**: PPO-variant using Muon, a custom advantage function (GAE + VTrace), and prioritized replay.
*   **PufferNet**: Default architecture combining MinGRU (parallelizable over time) with highway nets.
*   **Sweeps**: Uses *Protein*, a tuning algorithm combining Gaussian processes with a genetic algorithm over the Pareto-frontier.

---

## Tutorial: Writing Your Own Environment

Ocean environments are written in simple C. 
1.  Copy `Squared` (single-agent) or `Target` (multi-agent) as templates.
2.  The `.h` file contains core logic; the `.c` file contains the standalone demo.
3.  Create a `.ini` file in the `config/` directory.
4.  Build and train: 
    ```bash
    puffer build env_name
    puffer train env_name
    ```

### Troubleshooting Checklist
*   **Zero/Incorrect observations**: Ensure observation and action metadata (space/size/type) is correct in `binding.c`.
*   **NaN losses**: Usually data corruption or writing to memory outside defined sizes.
*   **Incorrect/Missing resets**: Ensure your environment handles its own resets internally.
*   **Data Scale**: Keep observations and rewards roughly in the range of -1 to 1.

---

