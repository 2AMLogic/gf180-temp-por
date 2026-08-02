#!/usr/bin/env bash
#
# layout/run_checks.sh -- the repeatable DRC/LVS invocation for this block.
#
#     bash layout/run_checks.sh              # every cell in layout/cells/
#     bash layout/run_checks.sh <cell>       # one cell
#     bash layout/run_checks.sh --check-env  # just report the toolchain
#
# For each cell it:
#   1. re-checks that the committed GDS and reference netlist are current,
#   2. runs `klt drc   --deck gf180mcu`  and requires a clean verdict,
#   3. runs `klt extract --deck gf180mcu` and records the layout netlist,
#   4. runs `klt lvs` against the schematic-derived reference and requires
#      a match,
#   5. re-runs LVS twice against deliberately-corrupted references (one
#      topology defect, one device-parameter defect) and requires BOTH to be
#      reported as mismatches.
#
# Step 5 is not decoration. A mis-wired LVS invocation that silently compares
# nothing also reports "match", so a clean run on its own is not evidence; the
# two controls fail independently (klayout-tools docs/cli/lvs.md, "Negative
# controls"), so passing all three is what makes the clean run mean something.
#
# Every JSON report is written under layout/reports/ and committed as evidence.
# The script is the single source of truth for the invocation -- prose in
# layout/README.md describes it, but this file is what gets run.

set -euo pipefail

LAYOUT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$LAYOUT_DIR")"
cd "$REPO_ROOT"

DECK="gf180mcu"
REPORTS="layout/reports"

red() { printf '\033[0;31m%s\033[0m\n' "$*"; }
green() { printf '\033[0;32m%s\033[0m\n' "$*"; }
info() { printf '\033[0;34m%s\033[0m\n' "$*"; }

# --- toolchain ---------------------------------------------------------------

if ! command -v klt >/dev/null 2>&1; then
  red "klt not found on PATH -- install klayout-tools (2AMLogic/klayout-tools)"
  exit 127
fi

# layout/build_cells.py needs the `klayout` python module (klt's own runtime
# dependency). Prefer a plain python3 that already has it; otherwise borrow
# klt's interpreter, or fall back to `uv run --with klayout`.
KLAYOUT_PY=""
if python3 -c "import klayout.db" >/dev/null 2>&1; then
  KLAYOUT_PY="python3"
else
  klt_bin="$(command -v klt)"
  klt_py="$(dirname "$(readlink "$klt_bin" 2>/dev/null || echo "$klt_bin")")/python"
  if [ -x "$klt_py" ] && "$klt_py" -c "import klayout.db" >/dev/null 2>&1; then
    KLAYOUT_PY="$klt_py"
  elif command -v uv >/dev/null 2>&1; then
    KLAYOUT_PY="uv run --quiet --with klayout python3"
  fi
fi

KLT_VERSION="$(klt --version 2>&1)"

if [ "${1:-}" = "--check-env" ]; then
  echo "klt:        $KLT_VERSION ($(command -v klt))"
  echo "deck:       $DECK"
  echo "klayout py: ${KLAYOUT_PY:-<not available -- cannot rebuild GDS>}"
  klt pdk find || true
  exit 0
fi

# --- cell selection ----------------------------------------------------------

if [ "$#" -gt 0 ]; then
  CELLS=("$@")
else
  CELLS=()
  for gds in layout/cells/*.gds; do
    CELLS+=("$(basename "$gds" .gds)")
  done
fi

mkdir -p "$REPORTS"
cat >"$REPORTS/environment.json" <<EOF
{
  "klt_version": "$KLT_VERSION",
  "deck": "$DECK",
  "note": "regenerate with: bash layout/run_checks.sh"
}
EOF

# --- staleness gates ---------------------------------------------------------

info "==> checking committed sources are current"
if [ -n "$KLAYOUT_PY" ]; then
  $KLAYOUT_PY layout/build_cells.py --check
else
  red "no interpreter with the klayout module -- skipping the GDS staleness check"
  red "(install it, or run: uv run --with klayout python3 layout/build_cells.py --check)"
fi
python3 layout/lvs_reference.py --check

# --- per-cell checks ---------------------------------------------------------

status=0
for cell in "${CELLS[@]}"; do
  gds="layout/cells/${cell}.gds"
  request="layout/cells/${cell}.lvs.json"
  out="$REPORTS/${cell}"
  mkdir -p "$out"

  info "==> $cell"

  # 1. DRC ---------------------------------------------------------------
  if klt drc "$gds" --deck "$DECK" --format json >"$out/drc.json"; then
    green "    DRC   clean   ($out/drc.json)"
  else
    red "    DRC   FAILED  ($out/drc.json)"
    status=1
    continue
  fi

  # 2. extraction --------------------------------------------------------
  # Extraction is flat, so by default every net named by a label anywhere in
  # the hierarchy becomes a top-level pin -- including the ones an instanced
  # sub-cell names, which are internal nodes once instanced (klayout-tools
  # #291). A cell that instances others therefore sets `layout.top_cell_pins`
  # in its own request; this mirrors it onto the recorded extraction so the
  # committed extract.json and the compare see the same pin set.
  extract_flags=()
  if python3 -c "
import json,sys
print(json.load(open(sys.argv[1]))['layout'].get('top_cell_pins', False))
" "$request" | grep -q True; then
    extract_flags+=(--top-cell-pins)
  fi
  if klt extract "$gds" --deck "$DECK" \
    -o "$out/extracted.spice" --top "$cell" \
    "${extract_flags[@]+"${extract_flags[@]}"}" \
    --format json >"$out/extract.json"; then
    green "    EXTR  ok      ($out/extracted.spice)"
  else
    red "    EXTR  FAILED  ($out/extract.json)"
    status=1
    continue
  fi

  # 3. LVS ---------------------------------------------------------------
  if klt lvs "$request" --format json >"$out/lvs.json"; then
    green "    LVS   match   ($out/lvs.json)"
  else
    red "    LVS   FAILED  ($out/lvs.json)"
    status=1
    continue
  fi

  # 4. negative controls -------------------------------------------------
  control_dir="$(mktemp -d)"
  trap 'rm -rf "$control_dir"' EXIT
  for corruption in topology device-param; do
    ref="$control_dir/${cell}.${corruption}.spice"
    req="$control_dir/${cell}.${corruption}.request.json"
    python3 layout/lvs_reference.py --cell "$cell" \
      --corrupt "$corruption" -o "$ref" >/dev/null
    # Derived from the cell's own committed request, with *only* the reference
    # netlist swapped: a control that quietly dropped an option the real run
    # uses (`top_cell_pins`, hints, ...) would still exit 3, so it would still
    # look like a passing control while no longer controlling the same compare.
    python3 - "$request" "$PWD/$gds" "$ref" >"$req" <<'PY'
import json, os, sys
committed, gds, ref = sys.argv[1:4]
request = json.load(open(committed))
request["layout"]["file"] = gds
request["reference"]["netlist"] = ref
json.dump(request, sys.stdout, indent=2)
PY
    code=0
    klt lvs "$req" --format json >"$control_dir/${corruption}.report.json" || code=$?
    echo "$code" >"$control_dir/${corruption}.exit"
    # 3 == "ran successfully, mismatches found" (klt lvs exit-code contract)
    if [ "$code" -eq 3 ]; then
      green "    CTRL  $corruption -> mismatch (expected)"
    else
      red "    CTRL  $corruption -> exit $code, expected 3 (mismatch)"
      status=1
    fi
  done
  python3 - "$cell" "$control_dir" topology device-param \
    >"$out/negative-controls.json" <<'PY'
import json, sys
from pathlib import Path

cell, control_dir, *corruptions = sys.argv[1:]
controls = []
for name in corruptions:
    code = int(Path(control_dir, f"{name}.exit").read_text().strip())
    try:
        report = json.loads(Path(control_dir, f"{name}.report.json").read_text())
    except Exception:
        report = {}
    controls.append({
        "corruption": name,
        "detected": code == 3,
        "exit_code": code,
        "status": report.get("status"),
        "category_counts": report.get("category_counts", {}),
    })
json.dump({
    "cell": cell,
    "all_controls_detected": all(c["detected"] for c in controls),
    "controls": controls,
}, sys.stdout, indent=2)
sys.stdout.write("\n")
PY
  rm -rf "$control_dir"
  trap - EXIT
done

echo
if [ "$status" -eq 0 ]; then
  green "all cells: DRC clean, LVS match, both negative controls detected"
else
  red "one or more checks failed -- see $REPORTS"
fi
exit "$status"
