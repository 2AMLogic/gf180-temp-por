#!/usr/bin/env bash
# run_devchar.sh -- thin entrypoint for issue #4's device-characterization
# sweep. See run_devchar.py for the actual corner x temperature x device
# orchestration logic (kept in Python for the CSV/regex/linear-fit work).
#
# Usage:
#   ./run_devchar.sh              # full 7-point temperature grid
#   ./run_devchar.sh --quick      # -40/27/125 C only, for a fast re-run check
#
# Env overrides:
#   PDK_ROOT   volare install root (default: ~/.volare)
#   NGSPICE    ngspice binary (default: ngspice on PATH)

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

exec python3 run_devchar.py \
  ${PDK_ROOT:+--pdk-root "$PDK_ROOT"} \
  ${NGSPICE:+--ngspice "$NGSPICE"} \
  "$@"
