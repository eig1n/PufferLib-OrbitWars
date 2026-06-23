#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="$ROOT/logs/orbit_wars/$STAMP"
mkdir -p "$LOG_DIR"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON="$ROOT/.venv/bin/python"
    export PATH="$ROOT/.venv/bin:$PATH"
else
    PYTHON="${PYTHON:-python}"
fi

run_logged() {
    local name="$1"
    shift
    echo "==> $name"
    echo "Log: $LOG_DIR/$name.log"
    "$@" 2>&1 | tee "$LOG_DIR/$name.log"
}

run_logged build_cpu bash build.sh orbit_wars --cpu
run_logged decoder "$PYTHON" -c 'import tests.test_orbit_wars_decoder as t; [getattr(t, n)() for n in dir(t) if n.startswith("test_")]'
run_logged runtime "$PYTHON" tests/test_orbit_wars.py
run_logged parity "$PYTHON" tests/test_orbit_wars_parity.py

echo "All Orbit Wars local checks passed. Logs saved to: $LOG_DIR"
