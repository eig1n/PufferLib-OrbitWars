"""Kaggle-compatible agent running Puffer-trained checkpoints on CPU."""

import os
import sys
import math
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

# Ensure the root of the repo is in the path
import inspect
if "__file__" in globals() and __file__ is not None:
    current_dir = os.path.dirname(os.path.abspath(__file__))
else:
    inferred_path = None
    for frame_info in inspect.stack():
        f_locals = frame_info.frame.f_locals
        if "path" in f_locals:
            p = f_locals["path"]
            if isinstance(p, str) and (p.endswith(".py") or p.endswith(".tar.gz")):
                inferred_path = p
                break
    if inferred_path and os.path.exists(inferred_path):
        current_dir = os.path.dirname(os.path.abspath(inferred_path))
    else:
        current_dir = os.getcwd()

if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

possible_repo_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
if os.path.exists(os.path.join(possible_repo_root, "pufferlib")):
    repo_root = possible_repo_root
else:
    repo_root = current_dir

if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
    sys.path.insert(0, os.path.join(repo_root, "orbit-wars"))

try:
    from puffer_agent.policy_adapter import compact_features, policy_actions_to_moves
except ImportError:
    from policy_adapter import compact_features, policy_actions_to_moves

# Configuration constants
OBS_SIZE = 848
NUM_ATNS = 30
NUM_LAYERS = 1


class CustomEncoder(nn.Module):
    def __init__(self, obs_size, hidden_size):
        super().__init__()
        self.encoder = nn.Linear(obs_size, hidden_size, bias=False)

    def forward(self, observations):
        return self.encoder(observations.view(observations.shape[0], -1).float())


class CustomDecoder(nn.Module):
    def __init__(self, num_atns, hidden_size):
        super().__init__()
        self.decoder = nn.Linear(hidden_size, num_atns + 1, bias=False)
        self.decoder_logstd = nn.Parameter(torch.zeros(1, num_atns))

    def forward(self, hidden):
        out = self.decoder(hidden)
        mean = out[:, :NUM_ATNS]
        logstd = self.decoder_logstd.expand_as(mean)
        logits = torch.distributions.Normal(mean, torch.exp(logstd))
        values = out[:, -1:]
        return logits, values


class MinGRU(nn.Module):
    def __init__(self, hidden_size, num_layers=1):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.layers = nn.ModuleList([
            nn.Linear(hidden_size, 3 * hidden_size, bias=False) for _ in range(num_layers)
        ])

    def _g(self, x):
        return torch.where(x >= 0, x + 0.5, x.sigmoid())

    def _highway(self, x, out, proj):
        g = proj.sigmoid()
        return g * out + (1.0 - g) * x

    def initial_state(self, batch_size, device):
        return (torch.zeros(self.num_layers, batch_size, self.hidden_size, device=device),)

    def forward_eval(self, h, state):
        state = state[0]
        assert state.shape[1] == h.shape[0]
        h = h.unsqueeze(1)
        state_out = []
        for i in range(self.num_layers):
            hidden, gate, proj = self.layers[i](h).chunk(3, dim=-1)
            out = torch.lerp(state[i:i+1].transpose(0, 1), self._g(hidden), gate.sigmoid())
            h = self._highway(h, out, proj)
            state_out.append(out[:, -1:])
        return h.squeeze(1), (torch.stack(state_out, 0).squeeze(2),)


class CustomPolicy(nn.Module):
    def __init__(self, encoder, decoder, network):
        super().__init__()
        self.encoder = encoder
        self.decoder = decoder
        self.network = network

    def initial_state(self, batch_size, device):
        return self.network.initial_state(batch_size, device)

    def forward_eval(self, x, state):
        h = self.encoder(x)
        h, state = self.network.forward_eval(h, state)
        logits, values = self.decoder(h)
        return logits, values, state


class AgentState:
    def __init__(self):
        self.policy = None
        self.recurrent_state = None
        self.player_id = None
        self.device = "cpu"
        self.hidden_size = None


_state = AgentState()


def detect_hidden_size(num_params, obs_size=848, num_atns=30, num_layers=1):
    a = 3 * num_layers
    b = obs_size + num_atns + 1
    c = num_atns - num_params
    disc = b * b - 4 * a * c
    if disc < 0:
        return None
    H = (-b + math.sqrt(disc)) / (2 * a)
    return int(round(H))


def load_flat_weights(policy, flat_weights, hidden_size):
    ptr = 0

    # 1. Encoder weights: hidden_size * obs_size
    enc_size = hidden_size * OBS_SIZE
    enc_weight = flat_weights[ptr : ptr + enc_size].reshape(hidden_size, OBS_SIZE)
    policy.encoder.encoder.weight.data.copy_(torch.tensor(enc_weight))
    ptr += enc_size

    # 2. Decoder weights: (num_atns + 1) * hidden_size
    dec_size = (NUM_ATNS + 1) * hidden_size
    dec_weight = flat_weights[ptr : ptr + dec_size].reshape(NUM_ATNS + 1, hidden_size)
    policy.decoder.decoder.weight.data.copy_(torch.tensor(dec_weight))
    ptr += dec_size

    # 3. Decoder logstd: num_atns
    logstd_size = NUM_ATNS
    dec_logstd = flat_weights[ptr : ptr + logstd_size].reshape(1, NUM_ATNS)
    policy.decoder.decoder_logstd.data.copy_(torch.tensor(dec_logstd))
    ptr += logstd_size

    # 4. MinGRU weights: 3 * hidden_size * hidden_size per layer
    for i in range(NUM_LAYERS):
        gru_size = 3 * hidden_size * hidden_size
        gru_weight = flat_weights[ptr : ptr + gru_size].reshape(3 * hidden_size, hidden_size)
        policy.network.layers[i].weight.data.copy_(torch.tensor(gru_weight))
        ptr += gru_size

    assert ptr == len(flat_weights), f"Used {ptr} elements of weight file, but total length is {len(flat_weights)}"


def initialize_policy():
    if _state.policy is not None:
        return

    # Locate the checkpoint
    checkpoint_candidates = [
        os.path.join(repo_root, "checkpoints/orbit_wars_lite/colab_t4_smoke/0000000006291456.bin"),
        os.path.join(current_dir, "0000000006291456.bin"),
    ]

    checkpoint_path = None
    for path in checkpoint_candidates:
        if os.path.exists(path):
            checkpoint_path = path
            break

    if checkpoint_path is None:
        import glob
        # Search directly in current_dir first
        candidates = glob.glob(os.path.join(current_dir, "*.bin"))
        if not candidates:
            # Search in the workspace structure
            pattern = os.path.join(repo_root, "checkpoints", "orbit_wars_lite", "**", "*.bin")
            candidates = glob.glob(pattern, recursive=True)
        if candidates:
            checkpoint_path = sorted(candidates, key=os.path.getctime)[-1]

    if checkpoint_path is not None:
        print(f"Loading flat policy weights from {checkpoint_path}", file=sys.stderr)
        flat_weights = np.fromfile(checkpoint_path, dtype=np.float32)
        num_params = len(flat_weights)
        _state.hidden_size = detect_hidden_size(num_params, OBS_SIZE, NUM_ATNS, NUM_LAYERS)
        if _state.hidden_size is None:
            raise ValueError(f"Could not auto-detect hidden size for checkpoint size {num_params}")
        print(f"Auto-detected hidden_size: {_state.hidden_size}", file=sys.stderr)
    else:
        print("WARNING: No checkpoint found, using uninitialized policy weights!", file=sys.stderr)
        _state.hidden_size = 32  # fallback default

    # Build policy model matching C++ architecture
    encoder = CustomEncoder(obs_size=OBS_SIZE, hidden_size=_state.hidden_size)
    decoder = CustomDecoder(num_atns=NUM_ATNS, hidden_size=_state.hidden_size)
    network = MinGRU(hidden_size=_state.hidden_size, num_layers=NUM_LAYERS)
    
    _state.policy = CustomPolicy(encoder, decoder, network)
    _state.policy.eval()

    if checkpoint_path is not None:
        load_flat_weights(_state.policy, flat_weights, _state.hidden_size)


def agent(obs, configuration=None):
    initialize_policy()

    player_id = obs.get("player", 0) if isinstance(obs, dict) else obs.player
    step = obs.get("step", 0) if isinstance(obs, dict) else obs.step

    # Reset recurrent state at step 0 or if player_id changes
    if step == 0 or _state.player_id != player_id or _state.recurrent_state is None:
        _state.player_id = player_id
        _state.recurrent_state = _state.policy.initial_state(batch_size=1, device=_state.device)

    # Preprocess observation
    features = compact_features(obs, player_id)
    features_t = torch.tensor([features], dtype=torch.float32, device=_state.device)

    # Run policy
    with torch.no_grad():
        logits, values, _state.recurrent_state = _state.policy.forward_eval(features_t, _state.recurrent_state)
        actions = logits.mean.squeeze(0).cpu().numpy()

    # Decode actions to moves
    moves = policy_actions_to_moves(actions, obs, player_id)
    return moves
