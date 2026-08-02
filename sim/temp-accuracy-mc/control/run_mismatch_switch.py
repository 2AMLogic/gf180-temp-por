#!/usr/bin/env python3
"""One-variable mismatch-switch control for sim/temp-accuracy-mc/.

    python3 sim/temp-accuracy-mc/control/run_mismatch_switch.py

`sim/harness/montecarlo.py` rests on three mechanical claims about how
gf180mcu's statistical models behave under ngspice. All three are load-bearing
-- if any were false the Monte Carlo records would still *look* fine (a
distribution with a plausible sigma comes out either way) while measuring
something other than local device mismatch:

1. `.param sw_stat_mismatch=1` actually engages the PDK's `statistical`
   models. If it silently did nothing, every sample would be the same die.
2. `.option seed=<N>` selects *and reproduces* the draw. If the seed did not
   reach the mismatch RNG, "N=500 reproducible samples" would be N=500
   irreproducible ones -- or, worse, one die repeated 500 times.
3. The override's **position** matters: `design.ngspice` sets
   `sw_stat_mismatch=0` itself, so the override has to come *after* that
   `.include` to win, because ngspice keeps the last declaration of a
   duplicate `.param` name.

This control demonstrates all three by composing six otherwise-identical decks
from `mismatch_switch.spice` + the exported `design/netlist/temp_core.spice`,
running a plain `op` on each at tt / 27 C / VDD = 3.3 V, and writing:

    decks/<variant>.spice   the exact deck as run
    logs/<variant>.log      raw ngspice output, verbatim
    results.md              the comparison table, generated from those logs

It is a diagnosis, not a record: six points at one corner say nothing about
the corner grid, so it deliberately does NOT go through sim/run_mc.py and does
NOT mint a record under ../records/. The distribution evidence is the N>=500
records there; this exists so the *mechanism* those records rely on is
reproducible instead of asserted. See sim/README.md for the distinction.

Everything except the mismatch switch and the seed is held fixed by
construction: all six decks are composed from the same fragment, in the same
process, from the same PDK, with the corner sections and solver tolerances
read from the harness and from ../testbench/tb.json rather than restated here.

Stdlib only, no virtualenv required.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

CONTROL_DIR = Path(__file__).resolve().parent
EXPERIMENT_DIR = CONTROL_DIR.parent
REPO_ROOT = CONTROL_DIR.parents[2]

sys.path.insert(0, str(REPO_ROOT / "sim"))

from harness import HARNESS_VERSION, corners as corners_mod, runner  # noqa: E402
from harness.pdk import PdkNotFound, find_pdk  # noqa: E402

# The one PVT point the control is taken at. tt / 27 C / 3.3 V is nominal --
# the mismatch machinery is either engaged or it is not, and that does not
# depend on where in the PVT grid the question is asked.
CORNER = "tt"
TEMP_C = 27.0
VDD_V = 3.3

FRAGMENT = CONTROL_DIR / "mismatch_switch.spice"
DUT_NETLIST = REPO_ROOT / "design" / "netlist" / "temp_core.spice"
MANIFEST = EXPERIMENT_DIR / "testbench" / "tb.json"

# Two seeds, deliberately unrelated to the manifest's own seed_base so this
# control can never be confused with a sample of the recorded population.
SEED_A = 1001
SEED_B = 2002

# node probes, in the order the results table presents them
PROBES: list[tuple[str, str, str]] = [
    ("v(ptat)", "V(PTAT)", "the PTAT output"),
    ("v(ctat)", "V(CTAT)", "the CTAT output"),
    ("v(xdut.na)", "V(NA)", "amplifier input, PTAT side"),
    ("v(xdut.nb)", "V(NB)", "amplifier input, 1x PNP side"),
    ("v(xdut.nc)", "V(NC)", "8x PNP emitter"),
]

#: (name, mismatch override or None, override placement, seed, column label)
#: ``placement`` is "after" (the harness's own ordering) or "before" (ahead of
#: the ``.include design.ngspice`` that defaults the switch to 0).
VARIANTS: list[tuple[str, int | None, str, int, str]] = [
    ("off-seedA", None, "after", SEED_A, f"off, seed {SEED_A}"),
    ("off-seedB", None, "after", SEED_B, f"off, seed {SEED_B}"),
    ("on-seedA", 1, "after", SEED_A, f"**on**, seed {SEED_A}"),
    ("on-seedA-repeat", 1, "after", SEED_A, f"**on**, seed {SEED_A} (re-run)"),
    ("on-seedB", 1, "after", SEED_B, f"**on**, seed {SEED_B}"),
    ("on-before-includes-seedA", 1, "before", SEED_A, f"on *before* the .include, seed {SEED_A}"),
]

_PRINT_RE = re.compile(r"^\s*(\S+)\s*=\s*([-+]?[0-9.]+(?:[eE][-+]?[0-9]+)?)\s*$")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compose_deck(
    pdk,
    mismatch: int | None,
    placement: str,
    seed: int,
    options: list[str],
    deck_dir: Path,
) -> str:
    """Build one complete deck. The ONLY variables across calls are the
    ``sw_stat_mismatch`` override (value and position) and ``.option seed``.

    Repo-internal ``.include`` paths are written relative to ``deck_dir`` so a
    committed deck is not tied to the checkout it happened to be generated in;
    the PDK's own paths are absolute because the PDK lives outside the repo
    and the harness resolves it per machine.
    """
    corner = corners_mod.CORNERS[CORNER]
    fragment_rel = os.path.relpath(FRAGMENT, deck_dir)
    dut_rel = os.path.relpath(DUT_NETLIST, deck_dir)
    override = None if mismatch is None else f".param sw_stat_mismatch={mismatch}"
    lines = [
        f"* temp-accuracy-mc mismatch-switch control @ {CORNER} / {TEMP_C} C / {VDD_V} V"
        " -- GENERATED by run_mismatch_switch.py, do not edit",
        f"* sw_stat_mismatch override: {override or 'none (design.ngspice default)'}"
        f"   placement: {placement} the .include"
        f"   seed: {seed}",
        f"* pdk={pdk.variant}@{pdk.version}",
        "",
        f".option seed={seed}",
    ]
    if override is not None and placement == "before":
        lines.append(override)
    lines += ["", f'.include "{pdk.design_include}"']
    lines += [f'.lib "{pdk.model_lib}" {section}' for section in corner.sections]
    if override is not None and placement == "after":
        lines += ["", override]
    lines += ["", f".temp {TEMP_C!r}"]
    lines += [f".options {option}" for option in options]
    lines += [
        "",
        f'.include "{fragment_rel}"',
        f'.include "{dut_rel}"',
        "",
        ".control",
        "set numdgt=10",
        "set noaskquit",
        "op",
    ]
    lines += [f"print {expr}" for expr, _, _ in PROBES]
    lines += [".endc", ".end", ""]
    return "\n".join(lines)


def parse_prints(text: str) -> dict[str, float]:
    found: dict[str, float] = {}
    for line in text.splitlines():
        match = _PRINT_RE.match(line)
        if match:
            try:
                found[match.group(1)] = float(match.group(2))
            except ValueError:  # pragma: no cover - regex already constrains this
                continue
    return found


def fmt(value: float) -> str:
    return f"{value:.10g} V"


def identical(a: dict[str, float], b: dict[str, float]) -> bool:
    """Bit-for-bit equal on every probe. Not a tolerance: two runs of the same
    deterministic deck are the same numbers, and anything else is the finding.
    """
    return all(a[expr] == b[expr] for expr, _, _ in PROBES)


def git_describe() -> str:
    """HEAD, plus whether anything OTHER than this script's own outputs is dirty.

    Regenerating in place necessarily dirties `results.md`, `decks/` and
    `logs/`, so counting them would report every re-run as taken against a
    dirty tree -- the same trap `sim/harness/report.py` avoids by sampling git
    before the run. What matters for provenance is the state of the *inputs*.
    """

    def _git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False
        ).stdout.strip()

    generated = tuple(
        str((CONTROL_DIR / name).relative_to(REPO_ROOT)) for name in ("results.md", "decks", "logs")
    )
    other = [
        line
        for line in _git("status", "--porcelain").splitlines()
        if not line[3:].strip('"').startswith(generated)
    ]
    state = "dirty" if other else "clean apart from this experiment's own outputs"
    return f"{_git('rev-parse', 'HEAD')} ({state})"


def main() -> int:
    try:
        pdk = find_pdk()
        ngspice_version = runner.ngspice_version()
    except (PdkNotFound, runner.NgspiceMissing) as exc:
        print(exc, file=sys.stderr)
        return 3

    options = list(json.loads(MANIFEST.read_text()).get("options", []))
    deck_dir = CONTROL_DIR / "decks"
    log_dir = CONTROL_DIR / "logs"
    deck_dir.mkdir(exist_ok=True)
    log_dir.mkdir(exist_ok=True)

    results: dict[str, dict[str, float]] = {}
    for name, mismatch, placement, seed, _label in VARIANTS:
        deck_path = deck_dir / f"{name}.spice"
        log_path = log_dir / f"{name}.log"
        deck_path.write_text(compose_deck(pdk, mismatch, placement, seed, options, deck_dir))
        proc = subprocess.run(
            ["ngspice", "-b", deck_path.name],
            capture_output=True,
            text=True,
            cwd=deck_dir,
            check=False,
        )
        output = proc.stdout + "\n" + proc.stderr
        log_path.write_text(output)
        values = parse_prints(output)
        missing = [expr for expr, _, _ in PROBES if expr not in values]
        if missing:
            print(f"{name}: ngspice produced no value for {', '.join(missing)}", file=sys.stderr)
            print(output, file=sys.stderr)
            return 2
        results[name] = values
        print(f"{name}: ok -> {log_path.relative_to(REPO_ROOT)}")

    # The five comparisons the three claims reduce to. Each is a hard
    # expectation, checked here rather than left to the reader of the table.
    comparisons: list[tuple[str, str, str, bool, str]] = [
        (
            "off-seedA", "off-seedB", "identical", True,
            "with the switch off, the seed changes nothing -- so any spread seen "
            "below is the mismatch models, not run-to-run solver noise",
        ),
        (
            "off-seedA", "on-seedA", "differ", False,
            "**claim 1**: `.param sw_stat_mismatch=1` really does engage the PDK's "
            "`statistical` models",
        ),
        (
            "on-seedA", "on-seedA-repeat", "identical", True,
            "**claim 2a**: a seed reproduces its die exactly, so an N-sample "
            "population is re-derivable from the manifest",
        ),
        (
            "on-seedA", "on-seedB", "differ", False,
            "**claim 2b**: a different seed draws a different die, so N samples are "
            "N dice and not one die N times",
        ),
        (
            "off-seedA", "on-before-includes-seedA", "identical", True,
            "**claim 3**: an override placed *before* the `.include` is overwritten "
            "by `design.ngspice`'s own `sw_stat_mismatch=0` and has no effect -- "
            "the harness's after-the-includes ordering is load-bearing, not "
            "cosmetic",
        ),
    ]

    failures: list[str] = []
    comparison_rows: list[str] = []
    for left, right, expectation, expect_identical, why in comparisons:
        same = identical(results[left], results[right])
        ok = same == expect_identical
        if not ok:
            failures.append(
                f"{left} vs {right}: expected {expectation}, "
                f"observed {'identical' if same else 'differ'}"
            )
        observed = "identical" if same else "differ"
        comparison_rows.append(
            f"| `{left}` vs `{right}` | {expectation} | **{observed}** | "
            f"{'OK' if ok else '**UNEXPECTED**'} | {why} |"
        )

    ptat_off = results["off-seedA"]["v(ptat)"]
    ptat_on_a = results["on-seedA"]["v(ptat)"]
    ptat_on_b = results["on-seedB"]["v(ptat)"]
    offs_off = (results["off-seedA"]["v(xdut.na)"] - results["off-seedA"]["v(xdut.nb)"]) * 1e6
    offs_on_a = (results["on-seedA"]["v(xdut.na)"] - results["on-seedA"]["v(xdut.nb)"]) * 1e6
    offs_on_b = (results["on-seedB"]["v(xdut.na)"] - results["on-seedB"]["v(xdut.nb)"]) * 1e6

    table = [
        "| | " + " | ".join(label for _, _, _, _, label in VARIANTS) + " |",
        "| --- | " + " | ".join("---:" for _ in VARIANTS) + " |",
    ]
    for expr, label, note in PROBES:
        cells = " | ".join(fmt(results[name][expr]) for name, _, _, _, _ in VARIANTS)
        table.append(f"| `{label}` -- {note} | {cells} |")
    offs_cells = " | ".join(
        f"{(results[name]['v(xdut.na)'] - results[name]['v(xdut.nb)']) * 1e6:.2f} uV"
        for name, _, _, _, _ in VARIANTS
    )
    table.append(f"| `V(NA) - V(NB)` -- amplifier input-referred offset | {offs_cells} |")

    findings = [
        textwrap.fill(text, width=76, initial_indent="- ", subsequent_indent="  ")
        for text in (
            f"With mismatch **off** the amplifier's input-referred offset is the "
            f"systematic **{offs_off:.2f} uV** `design/temp_core.md` quotes, and it is "
            f"the same number at either seed. With mismatch **on** the same node pair "
            f"reads **{offs_on_a:.2f} uV** at seed {SEED_A} and **{offs_on_b:.2f} uV** "
            f"at seed {SEED_B} -- three orders of magnitude larger, and seed-dependent. "
            f"That size gap is the whole reason the [3sigma] rows cannot be closed on "
            f"deterministic corners.",
            f"`V(PTAT)` moves from **{ptat_off:.6f} V** (mismatch off) to "
            f"**{ptat_on_a:.6f} V** / **{ptat_on_b:.6f} V** on the two mismatched dice: "
            f"{(ptat_on_a - ptat_off) * 1e3:+.3f} mV and "
            f"{(ptat_on_b - ptat_off) * 1e3:+.3f} mV. At the cell's ~4.31 mV/K that is "
            f"{(ptat_on_a - ptat_off) * 1e3 / 4.308842:+.2f} C and "
            f"{(ptat_on_b - ptat_off) * 1e3 / 4.308842:+.2f} C of untrimmed temperature "
            f"error from two arbitrary dice -- consistent in magnitude with the sigma "
            f"the N>=500 records report, from two samples instead of two thousand.",
            "Every deck under `decks/` is byte-identical apart from the `.option seed=` "
            "line and the presence/position of one `.param sw_stat_mismatch=1` line; "
            "`diff` them to confirm the control really is one-variable.",
        )
    ]

    verdict = (
        "All five comparisons came out as expected."
        if not failures
        else "**One or more comparisons did NOT come out as expected** -- see the "
        "Status column above. The Monte Carlo records' mechanism assumptions do "
        "not hold on this ngspice/PDK combination and must be re-derived before "
        "those records are cited."
    )

    body = f"""# mismatch-switch control -- generated, do not edit

Generated by `sim/temp-accuracy-mc/control/run_mismatch_switch.py`. Re-run it
to regenerate this file, the six decks under `decks/` and the six raw ngspice
logs under `logs/`. The numbers quoted in `sim/harness/montecarlo.py`'s module
docstring and in `../testbench/stimulus.spice` are transcribed from here, and
from nowhere else.

Two variables, one at a time: the `.param sw_stat_mismatch` override (absent /
present-after-the-`.include` / present-before-it) and `.option seed`. All six
decks are composed from `mismatch_switch.spice` +
`design/netlist/temp_core.spice` in the same process, at {CORNER} / {TEMP_C:g} C /
VDD = {VDD_V:g} V, plain `op`.

## Result

{chr(10).join(table)}

## The three mechanism claims

| comparison | expected | observed | status | why it matters |
| --- | --- | --- | --- | --- |
{chr(10).join(comparison_rows)}

{verdict}

## What the numbers say

{chr(10).join(findings)}

## Environment

- PDK: {pdk.variant} @ open_pdks `{pdk.version}` ({pdk.path}, found via {pdk.source})
- ngspice: {ngspice_version}
- Harness: sim/harness {HARNESS_VERSION} (corner sections and solver options only), python {sys.version.split()[0]}
- git: `{git_describe()}`
- Corner sections: {' '.join(corners_mod.CORNERS[CORNER].sections)}
- Solver options (from `../testbench/tb.json`): {' '.join(options)}
- `mismatch_switch.spice` sha256: `{sha256(FRAGMENT)}`
- `design/netlist/temp_core.spice` sha256: `{sha256(DUT_NETLIST)}`
"""
    (CONTROL_DIR / "results.md").write_text(body)
    print(f"wrote {(CONTROL_DIR / 'results.md').relative_to(REPO_ROOT)}")
    for failure in failures:
        print(f"UNEXPECTED: {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
