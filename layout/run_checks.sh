#!/usr/bin/env bash
#
# layout/run_checks.sh -- the repeatable DRC/LVS invocation for this block.
#
#     bash layout/run_checks.sh              # every cell in layout/cells/
#     bash layout/run_checks.sh <cell>       # one cell
#     bash layout/run_checks.sh --check-env  # just report the toolchain
#     bash layout/run_checks.sh --regen-all  # re-stamp every non-frozen cell
#                                            # onto one deck (see "deck-hash
#                                            # consistency gate" below)
#
# For each cell it:
#   1. re-checks that the committed GDS and reference netlist are current,
#   2. runs `klt drc   --deck gf180mcu`  and requires a clean verdict,
#   3. runs `klt extract --deck gf180mcu` and records the layout netlist,
#   4. runs `klt lvs` against the schematic-derived reference and requires
#      a match,
#   5. re-runs LVS against deliberately-corrupted references (one topology
#      defect, one MOS device-parameter defect, and -- on a cell that has
#      passives -- one resistor/bipolar parameter defect) and requires every
#      applicable one to be reported as a mismatch.
#
# Step 5 is not decoration. A mis-wired LVS invocation that silently compares
# nothing also reports "match", so a clean run on its own is not evidence; the
# two controls fail independently (klayout-tools docs/cli/lvs.md, "Negative
# controls"), so passing all three is what makes the clean run mean something.
#
# Every JSON report is written under layout/reports/ and committed as evidence,
# with one exception: a whole-repo run does not overwrite a *frozen* cell's
# committed reports (see "frozen-cell reports" below and layout/README.md). The
# script is the single source of truth for the invocation -- prose in
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

# splice_gds_hash <gds> <report.json> -- inject sha256(<gds>) as
# provenance.gds_sha256 into a just-written drc.json/extract.json.
#
# `klt drc`/`klt extract` write neither report with anything tying it to the
# GDS stream it describes (unlike `klt lvs`, whose own `environment.
# layout_sha256` already does this) -- see #106. Splicing it in here, right
# after each report is written and before it is ever treated as committed
# evidence, means `lvs_reference.py --check-gds-hash` can catch a report that
# has drifted from its own GDS the same way `--check-deck-hash` catches
# reports that have drifted from each other (#102/#103).
splice_gds_hash() {
  local gds="$1" report="$2"
  python3 - "$gds" "$report" <<'PY'
import hashlib
import json
import sys

gds_path, report_path = sys.argv[1:3]
digest = hashlib.sha256(open(gds_path, "rb").read()).hexdigest()
with open(report_path) as f:
    data = json.load(f)
data.setdefault("provenance", {})["gds_sha256"] = digest
with open(report_path, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PY
}

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

# --- argument handling -------------------------------------------------------
#
# `--regen-all` is the deck-hash gate's *bootstrap* mode, not a bypass: see the
# gate's own section below for what it moves and why that does not weaken it.

REGEN_ALL=0
ARGS=()
for arg in "$@"; do
  case "$arg" in
  --regen-all) REGEN_ALL=1 ;;
  *) ARGS+=("$arg") ;;
  esac
done
set -- "${ARGS[@]+"${ARGS[@]}"}"

if [ "$REGEN_ALL" -eq 1 ] && [ "$#" -gt 0 ]; then
  red "--regen-all regenerates every non-frozen cell and takes no cell argument"
  red "(got: $*) -- a partial regeneration is what produces the drift it exists to fix"
  exit 2
fi

if [ "${1:-}" = "--check-env" ]; then
  echo "klt:        $KLT_VERSION ($(command -v klt))"
  echo "deck:       $DECK"
  echo "klayout py: ${KLAYOUT_PY:-<not available -- cannot rebuild GDS>}"
  klt pdk find || true
  exit 0
fi

# --- cell selection ----------------------------------------------------------
#
# `--regen-all` skips the cells the deck-hash gate itself excludes as frozen
# (lvs_reference.FROZEN_DECK_CELLS): the gate's remediation is "regenerate every
# *non-frozen* cell's reports against one deck", and re-stamping a frozen cell's
# evidence here would silently take over the tracking issue that owns it. The
# list is read from lvs_reference.py so it is declared exactly once.

frozen_deck_cells() {
  python3 layout/lvs_reference.py --list-frozen-deck-cells
}

if [ "$REGEN_ALL" -eq 1 ]; then
  frozen="$(frozen_deck_cells)"
  CELLS=()
  for gds in layout/cells/*.gds; do
    cell="$(basename "$gds" .gds)"
    if printf '%s\n' "$frozen" | grep -qx "$cell"; then
      info "    skip $cell (frozen: excluded from the deck-hash gate, regenerated by its own issue)"
      continue
    fi
    CELLS+=("$cell")
  done
elif [ "$#" -gt 0 ]; then
  CELLS=("$@")
else
  CELLS=()
  for gds in layout/cells/*.gds; do
    CELLS+=("$(basename "$gds" .gds)")
  done
fi

# --- frozen-cell reports -------------------------------------------------------
#
# A frozen cell (lvs_reference.FROZEN_CELLS) has its committed GDS and reference
# netlist pinned, and its committed *reports* are the evidence recorded against
# that pinned pair under the deck of the day it was checked. Rewriting them in a
# routine whole-repo run re-stamps them onto today's deck, so a careless
# `git add -A` ends the freeze silently -- the exact restamping the freeze
# exists to prevent (#111).
#
# So for a whole-repo run this script still runs every check on a frozen cell --
# a freeze is "do not compare against a fresh rebuild", never "stop running
# DRC" -- but writes this run's reports into a scratch directory and diffs them
# against the committed set instead of replacing it. The verdicts below are this
# run's own and fail exactly as loudly as any other cell's; only the destination
# of the bytes changes, which is why the guard cannot absorb a real failure.
#
# Naming the cell explicitly (`bash layout/run_checks.sh temp_por_top`) writes
# its reports as usual -- the same "--cell overrides the freeze" convention
# build_cells.py and lvs_reference.py already use for regeneration. With no
# frozen cells the list is empty and every branch below is a no-op.
PINNED_REPORT_CELLS="$(
  python3 layout/lvs_reference.py --pinned-report-cells "$@" | tr '\n' ' '
)"

reports_pinned() {
  case " $PINNED_REPORT_CELLS " in
  *" $1 "*) return 0 ;;
  *) return 1 ;;
  esac
}

# One scratch root for the whole run: the frozen cells' unwritten reports and
# every cell's negative-control workspace. Kept (not deleted) when a frozen
# cell fails, so the report the FAIL line points at is still there to read.
SCRATCH="$(mktemp -d)"
keep_scratch=0
cleanup_scratch() {
  if [ "$keep_scratch" -eq 1 ]; then
    red "kept this run's frozen-cell reports for inspection: $SCRATCH"
  else
    rm -rf "$SCRATCH"
  fi
}
trap cleanup_scratch EXIT

mkdir -p "$REPORTS"
cat >"$REPORTS/environment.json" <<EOF
{
  "klt_version": "$KLT_VERSION",
  "deck": "$DECK",
  "note": "regenerate with: bash layout/run_checks.sh"
}
EOF

# --- staleness gates ---------------------------------------------------------
#
# The gate is scoped to the cells actually being checked. A whole-repo run
# (no cell argument) still gates on every cell, so nothing is relaxed; but a
# single-cell run is no longer blocked by an unrelated cell's known staleness.
# That matters while #97 is open: `temp_por_top`'s committed assembly is
# deliberately frozen behind the sub-cell device work, so an unscoped gate
# makes it impossible to check any *other* cell with this script.

stale_gate() {
  local scope=("$@")
  if [ "${#scope[@]}" -gt 0 ]; then
    local cell
    for cell in "${scope[@]}"; do
      if [ -n "$KLAYOUT_PY" ]; then
        $KLAYOUT_PY layout/build_cells.py --check --cell "$cell"
      fi
      python3 layout/lvs_reference.py --check --cell "$cell"
    done
  else
    if [ -n "$KLAYOUT_PY" ]; then
      $KLAYOUT_PY layout/build_cells.py --check
    fi
    python3 layout/lvs_reference.py --check
  fi
}

info "==> checking committed sources are current"
if [ -z "$KLAYOUT_PY" ]; then
  red "no interpreter with the klayout module -- skipping the GDS staleness check"
  red "(install it, or run: uv run --with klayout python3 layout/build_cells.py --check)"
fi
if [ "$#" -gt 0 ]; then
  stale_gate "$@"
else
  stale_gate
fi

# --- deck-hash consistency gate -----------------------------------------------
#
# Unscoped by design, even for a single-cell run: this checks an invariant
# across the whole `layout/reports/` directory (every committed drc.json
# describes the same klt deck), not a property of any one cell, so scoping it
# to `$@` would let a single-cell run stay blind to drift a full run would
# catch. `temp_por_top` is tolerated while frozen behind #97 (see
# lvs_reference.py's FROZEN_DECK_CELLS) -- everything else must agree.
#
# `--regen-all` *defers* this gate to after the per-cell loop instead of
# skipping it (see the assertion at the end of this script). That exists because
# the gate's own remediation -- "regenerate every non-frozen cell's reports
# against one deck (bash layout/run_checks.sh)" -- was unreachable: the gate
# aborted the very run that was supposed to perform the regeneration, so a
# directory that had legitimately drifted onto two decks (two correct
# single-cell PRs landing under different klt builds) could not be repaired with
# the documented command (#108).
#
# Deferring is not weakening, on three counts:
#   * it is opt-in and never the default -- a plain run and a single-cell run
#     still gate before touching anything, exactly as before;
#   * `--regen-all` cannot be pointed at a subset (it rejects cell arguments),
#     so it can only ever *establish* one shared deck, never hide a split;
#   * the same check still has to pass on the result, and a failure there is a
#     non-zero exit like any other. Nothing in this script can waive it.

if [ "$REGEN_ALL" -eq 0 ]; then
  info "==> checking layout/reports/ agree on one deck (provenance.deck.content_hash)"
  python3 layout/lvs_reference.py --check-deck-hash
else
  info "==> --regen-all: deck-hash gate deferred until after regeneration"
  info "    (this run rewrites every non-frozen cell against the deck below, so"
  info "     the gate is asserted on the result instead of on the pre-run state)"
fi

# --- GDS-hash gate -------------------------------------------------------------
#
# Also unscoped, for the same reason as the deck-hash gate above, and for the
# same reason it runs *before* the per-cell loop overwrites this run's own
# reports: this checks the invariant #106 added -- every already-committed
# report's recorded digest still matches the already-committed GDS it claims
# to describe -- so a stale/false-clean report (#102) is caught before this
# run's fresh reports replace the evidence of it.

info "==> checking layout/reports/ agree with layout/cells/ (gds_sha256 / layout_sha256)"
python3 layout/lvs_reference.py --check-gds-hash

# --- per-cell checks ---------------------------------------------------------

status=0

# Record a failed check for the cell being processed. Identical to `status=1`
# except that a frozen cell's scratch reports survive the run, since the FAIL
# line above it names a path inside $SCRATCH.
cell_failed() {
  status=1
  if [ "$out" != "$committed" ]; then
    keep_scratch=1
  fi
}

for cell in "${CELLS[@]}"; do
  gds="layout/cells/${cell}.gds"
  request="layout/cells/${cell}.lvs.json"
  committed="$REPORTS/${cell}"
  if reports_pinned "$cell"; then
    out="$SCRATCH/reports/${cell}"
  else
    out="$committed"
  fi
  mkdir -p "$out"

  info "==> $cell"
  if [ "$out" != "$committed" ]; then
    info "    (frozen: every check below really runs, but its reports go to a"
    info "     scratch dir and are diffed -- $committed/ is left as committed."
    info "     To regenerate it: bash layout/run_checks.sh $cell)"
  fi

  # 1. DRC ---------------------------------------------------------------
  if klt drc "$gds" --deck "$DECK" --format json >"$out/drc.json"; then
    splice_gds_hash "$gds" "$out/drc.json"
    green "    DRC   clean   ($out/drc.json)"
  else
    red "    DRC   FAILED  ($out/drc.json)"
    cell_failed
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
    splice_gds_hash "$gds" "$out/extract.json"
    green "    EXTR  ok      ($out/extracted.spice)"
  else
    red "    EXTR  FAILED  ($out/extract.json)"
    cell_failed
    continue
  fi

  # 3. LVS ---------------------------------------------------------------
  if klt lvs "$request" --format json >"$out/lvs.json"; then
    green "    LVS   match   ($out/lvs.json)"
  else
    red "    LVS   FAILED  ($out/lvs.json)"
    cell_failed
    continue
  fi

  # 4. negative controls -------------------------------------------------
  # Under $SCRATCH rather than its own mktemp -d, so the run has exactly one
  # cleanup trap: a per-cell `trap ... EXIT` here would replace the frozen-cell
  # scratch cleanup installed above and `trap - EXIT` would disarm it entirely.
  control_dir="$SCRATCH/controls/${cell}"
  rm -rf "$control_dir"
  mkdir -p "$control_dir"
  for corruption in topology device-param passive-param; do
    ref="$control_dir/${cell}.${corruption}.spice"
    req="$control_dir/${cell}.${corruption}.request.json"
    # `passive-param` needs a resistor or a bipolar to perturb; on a cell that
    # has none the generator says so and the control is recorded as not
    # applicable rather than silently skipped.
    if ! python3 layout/lvs_reference.py --cell "$cell" \
      --corrupt "$corruption" -o "$ref" >/dev/null 2>"$control_dir/${corruption}.why"; then
      echo "-1" >"$control_dir/${corruption}.exit"
      info "    CTRL  $corruption -> n/a ($(cat "$control_dir/${corruption}.why"))"
      continue
    fi
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
      cell_failed
    fi
  done
  python3 - "$cell" "$control_dir" topology device-param passive-param \
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
    entry = {
        "corruption": name,
        # -1 is this script's own marker for "the reference generator has no
        # such defect to inject in this cell" (today: passive-param on a cell
        # with no resistor or bipolar), which is not a failed control.
        "applicable": code != -1,
        "detected": code == 3,
        "exit_code": code,
        "status": report.get("status"),
        "category_counts": report.get("category_counts", {}),
    }
    if not entry["applicable"]:
        entry["why"] = Path(control_dir, f"{name}.why").read_text().strip()
    controls.append(entry)
json.dump({
    "cell": cell,
    "all_controls_detected": all(
        c["detected"] for c in controls if c["applicable"]
    ),
    "controls": controls,
}, sys.stdout, indent=2)
sys.stdout.write("\n")
PY
  rm -rf "$control_dir"

  # 5. frozen cells: diff instead of overwrite ---------------------------
  # Every verdict above was this run's own; all that is left is to say how the
  # reports it produced compare with the committed evidence, which stays as
  # committed either way. A difference is expected while frozen (the committed
  # set was recorded under an older deck, which is why FROZEN_DECK_CELLS
  # tolerates it) -- it is reported, not failed, because the verdicts are what
  # carry pass/fail and they already have.
  if [ "$out" != "$committed" ]; then
    drift="$(python3 - "$out" "$committed" \
      drc.json extracted.spice extract.json lvs.json negative-controls.json <<'PY'
import sys
from pathlib import Path

scratch, committed, *reports = sys.argv[1:]
drift = []
for name in reports:
    kept = Path(committed, name)
    if not kept.exists():
        drift.append(f"{name}(not committed)")
        continue
    # `klt extract` records the -o path it was handed (`netlist_path`), so a
    # scratch-dir run differs from the committed report by that string alone.
    # Rewriting it back to where the report would have been written is what
    # makes this a diff of the evidence and not of the guard's own doing.
    fresh = Path(scratch, name).read_bytes()
    fresh = fresh.replace(scratch.encode(), committed.encode())
    if fresh != kept.read_bytes():
        drift.append(name)
print(" ".join(drift))
PY
    )"
    if [ -n "$drift" ]; then
      info "    FROZEN this run's reports differ from the committed ones: $drift"
      info "           (expected while frozen -- the committed set was recorded"
      info "            under an older deck; the verdicts above are this run's)"
    else
      green "    FROZEN this run reproduces the committed reports exactly"
    fi
  fi
done

# --- deferred deck-hash assertion (--regen-all only) --------------------------
#
# The other half of the deferral above. `--regen-all` moved the gate; this is
# where it lands. If regenerating every non-frozen cell did not leave them on
# one deck, that is a real finding (klt handing out different decks inside a
# single run, or a cell whose report was skipped) and it fails the run.

if [ "$REGEN_ALL" -eq 1 ]; then
  echo
  info "==> asserting layout/reports/ now agree on one deck (deferred gate)"
  if python3 layout/lvs_reference.py --check-deck-hash; then
    green "    deck hash consistent across every non-frozen cell"
  else
    red "    deck-hash gate still fails after regenerating every non-frozen cell"
    red "    (--regen-all defers this gate; it does not waive it)"
    status=1
  fi
fi

echo
if [ "$status" -eq 0 ]; then
  green "all cells: DRC clean, LVS match, every applicable negative control detected"
else
  red "one or more checks failed -- see $REPORTS"
fi
exit "$status"
