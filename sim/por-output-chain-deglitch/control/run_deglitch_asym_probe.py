#!/usr/bin/env python3
"""Deglitch-dwell asymmetry probe for sim/por-output-chain-deglitch/ (issue #182).

    python3 sim/por-output-chain-deglitch/control/run_deglitch_asym_probe.py

Diagnoses the schematic-vs-post-layout delta recorded in
`records/20260811-055634-d0ee17d.md` (post-layout) against
`records/20260802-205904-bdc077d.md` (schematic): the POR_RAW-**falling**
deglitch dwell -- the one `spec/target-spec.md#por-brownout` depends on --
**shrinks** 28-36 % at the fast corners, while the POR_RAW-**rising** dwell
through the same RC filter **grows** 12-14 %.

Composes decks from ``deglitch_asym_probe.spice`` + one DUT netlist per
variant, runs a ``.tran`` over one rising and one falling POR_RAW edge,
traces the deglitch filter's own nodes (``NDG``, the two tail nodes
``NDGP``/``NDGN``, and ``PGDG``), and decomposes each edge's dwell into

    dwell = (V_trip - V0) / slope

  * ``slope``  -- the I/C ramp rate of NDG across CDG (a capacitance effect),
  * ``V_trip`` -- the NDG voltage at which PGDG crosses the record's own 1.0 V
    measurement threshold (an XMG1 trip-point effect),
  * ``V0``     -- the level that ramp actually starts from, obtained by
    back-extrapolating the ramp to the POR_RAW edge. ``V0`` differs from the
    pre-edge rail exactly when charge is dumped onto (or pulled off) NDG at the
    instant the input pair switches.

Five variants isolate which of the three moved, by ablation:

    schematic     design/netlist/por_output_chain.spice, unmodified
    postlayout    layout/postlayout/por_output_chain.spice, unmodified
    sch+cndg      schematic + ONLY the extraction's NDG shunt capacitance
    sch+ctail     schematic + ONLY the extraction's NDGP/NDGN tail-node shunts
    sch+call      schematic + all three of those capacitances

Writes:

    decks/<variant>__<point>.spice   the exact deck as run
    decks/dut_<variant>.spice        the DUT netlist that deck includes
    logs/<variant>__<point>.log      raw ngspice output, verbatim
    traces/<variant>__<point>.csv    v(t) around the two POR_RAW edges
    results.md                       the decomposition table, from those traces

This is a **control experiment, not a record**: three PVT points tracing
internal nodes is a diagnosis, not corner-grid evidence, and it overwrites its
own outputs in place on every run. The PVT evidence for the por-brownout claim
stays in ``sim/por-output-chain-deglitch/records/`` (see ``sim/README.md``,
"Control experiments"). The traces are cropped to the two edge windows so this
directory stays a reviewable size; the ``decks/`` are complete and re-runnable.

Stdlib only, no virtualenv required.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

CONTROL_DIR = Path(__file__).resolve().parent
EXPERIMENT_DIR = CONTROL_DIR.parent
REPO_ROOT = CONTROL_DIR.parents[2]

sys.path.insert(0, str(REPO_ROOT / "sim"))

from harness import HARNESS_VERSION, corners as corners_mod, runner  # noqa: E402
from harness.pdk import PdkNotFound, find_pdk  # noqa: E402

FRAGMENT = CONTROL_DIR / "deglitch_asym_probe.spice"
SCHEMATIC_NETLIST = REPO_ROOT / "design" / "netlist" / "por_output_chain.spice"
POSTLAYOUT_NETLIST = REPO_ROOT / "layout" / "postlayout" / "por_output_chain.spice"
MANIFEST = EXPERIMENT_DIR / "testbench" / "tb.json"

STOP_S = 1.02e-3
TSTEP_S = 20e-9  # max timestep -- the dwells resolved here are 1-14 us wide

RISE_EDGE_S = 300.1e-6  # POR_RAW low -> high: NDG discharges, PGDG rises
FALL_EDGE_S = 1000.0e-6  # POR_RAW high -> low: NDG charges, PGDG falls
PGDG_THRESH = 1.0  # the records' own measurement threshold for the dwell

# Trace windows kept in traces/*.csv, one per edge: (start, stop).
TRACE_WINDOWS = ((RISE_EDGE_S - 1e-6, RISE_EDGE_S + 20e-6), (FALL_EDGE_S - 1e-6, FALL_EDGE_S + 8e-6))

# The three parasitic shunt capacitances layout/postlayout/por_output_chain.spice
# puts on the deglitch filter's own nodes (C_11 / C_16 / C_10 there). The
# ablation variants below splice these -- and nothing else -- onto the
# schematic netlist.
C_NDG_F = 3.8582127e-14
C_NDGP_F = 3.4117005e-14
C_NDGN_F = 3.4262384e-14

# node, csv column label, description -- traced in this order by wrdata
PROBES: list[tuple[str, str, str]] = [
    ("v(por_raw)", "POR_RAW", "the deglitch input"),
    ("v(xdut1.ndg)", "NDG", "the dwell node -- CDG plus whatever else sits on it"),
    ("v(xdut1.ndgp)", "NDGP", "PMOS tail node, XMDGPT drain / XMDGPI source"),
    ("v(xdut1.ndgn)", "NDGN", "NMOS tail node, XMDGNT drain / XMDGNI source"),
    ("v(xdut1.pgdg)", "PGDG", "the deglitched power-good node, XMG1's output"),
]

# Three points from the two records: the post-layout grid minimum (the corner
# whose falling dwell erodes most), the nominal corner, and the corner the
# 10 us ceiling check binds at.
POINTS: list[tuple[str, str, float, float]] = [
    ("ff_125c_3.63v", "ff", 125.0, 3.63),
    ("tt_27c_3.30v", "tt", 27.0, 3.30),
    ("ss_-40c_2.97v", "ss", -40.0, 2.97),
]

# The two records' dwell_pgdg_1x_us at those points, for the cross-check that
# this shorter deck reproduces the recorded numbers.
RECORDED_US: dict[str, dict[str, float]] = {
    "ff_125c_3.63v": {"schematic": 2.01, "postlayout": 1.28},
    "tt_27c_3.30v": {"schematic": 3.11, "postlayout": 2.60},
    "ss_-40c_2.97v": {"schematic": 4.41, "postlayout": 4.17},
}
RECORDED_RISE_US: dict[str, dict[str, float]] = {
    "ff_125c_3.63v": {"schematic": 10.7191, "postlayout": 12.4069},
    "tt_27c_3.30v": {"schematic": 10.2709, "postlayout": 11.5561},
    "ss_-40c_2.97v": {"schematic": 9.3447, "postlayout": 10.2313},
}


def _splice_caps(text: str, caps: list[tuple[str, str, float]], source: Path) -> str:
    """``text`` with extra capacitors inserted just before its ``.ends``."""
    lines = text.splitlines(keepends=True)
    idx = [i for i, ln in enumerate(lines) if ln.strip().lower().startswith(".ends")]
    if len(idx) != 1:
        raise SystemExit(f"expected exactly one '.ends' line in {source}, found {len(idx)}")
    added = [f"* spliced by run_deglitch_asym_probe.py -- ablation variant\n"]
    added += [f"{name} {node} VSS {value!r}\n" for name, node, value in caps]
    lines[idx[0] : idx[0]] = added
    return "".join(lines)


VARIANTS: list[tuple[str, str]] = [
    ("schematic", "`design/netlist/por_output_chain.spice`, unmodified"),
    ("postlayout", "`layout/postlayout/por_output_chain.spice`, unmodified"),
    ("sch+cndg", "schematic + the extraction's NDG shunt only (38.58 fF)"),
    ("sch+ctail", "schematic + the extraction's NDGP/NDGN tail shunts only (34.12 / 34.26 fF)"),
    ("sch+call", "schematic + all three of those shunts (38.58 / 34.12 / 34.26 fF)"),
]


def dut_netlist(variant: str) -> str:
    if variant == "postlayout":
        return POSTLAYOUT_NETLIST.read_text()
    text = SCHEMATIC_NETLIST.read_text()
    if variant == "schematic":
        return text
    caps: list[tuple[str, str, float]] = []
    if variant in ("sch+cndg", "sch+call"):
        caps.append(("Cabl_ndg", "NDG", C_NDG_F))
    if variant in ("sch+ctail", "sch+call"):
        caps.append(("Cabl_ndgp", "NDGP", C_NDGP_F))
        caps.append(("Cabl_ndgn", "NDGN", C_NDGN_F))
    if not caps:
        raise SystemExit(f"unknown variant {variant!r}")
    return _splice_caps(text, caps, SCHEMATIC_NETLIST)


def slug(variant: str) -> str:
    return variant.replace("+", "_")


def compose_deck(
    pdk, variant: str, corner_name: str, temp_c: float, vdd: float, options: list[str], deck_dir: Path
) -> str:
    corner = corners_mod.CORNERS[corner_name]
    fragment_rel = os.path.relpath(FRAGMENT, deck_dir)
    dut_rel = f"dut_{slug(variant)}.spice"
    lines = [
        f"* por-output-chain-deglitch asymmetry probe -- {variant} @ {corner_name} /"
        f" {temp_c:g} C / {vdd:g} V -- GENERATED by run_deglitch_asym_probe.py, do not edit",
        f"* pdk={pdk.variant}@{pdk.version}",
        "",
        f".param vdd_val={vdd!r}",
        f".param stop_s={STOP_S!r}",
        "",
    ]
    lines += runner.deck_preamble(pdk, corner, temp_c, options)
    lines += [
        "",
        f'.include "{fragment_rel}"',
        f'.include "{dut_rel}"',
        "",
        f".tran {TSTEP_S!r} {{stop_s}}",
        "",
        ".control",
        "set numdgt=10",
        "set noaskquit",
        "run",
        "wrdata trace.csv " + " ".join(expr for expr, _, _ in PROBES),
        ".endc",
        ".end",
        "",
    ]
    return "\n".join(lines)


def _refine_crossing(rows, col: int, thresh: float, t_row: float) -> float:
    """Linearly interpolated crossing time for the crossing ``runner.find_crossings``
    reported at sample time ``t_row`` (which is the sample *after* the crossing)."""
    prev = None
    for row in rows:
        if row[0] == t_row and prev is not None:
            a, b = prev[col], row[col]
            if b == a:
                return row[0]
            return prev[0] + (thresh - a) * (row[0] - prev[0]) / (b - a)
        prev = row
    return t_row


def _interp(rows, col: int, t: float) -> float:
    prev = None
    for row in rows:
        if row[0] >= t and prev is not None:
            span = row[0] - prev[0]
            if span <= 0:
                return row[col]
            return prev[col] + (row[col] - prev[col]) * (t - prev[0]) / span
        prev = row
    return rows[-1][col] if rows else float("nan")


def _fit(rows, col: int, t_lo: float, t_hi: float) -> tuple[float, float]:
    """Ordinary least squares of ``rows[:, col]`` vs time over ``[t_lo, t_hi]``.
    Returns ``(slope_V_per_s, value_at_t_lo_intercept_form)`` as ``(m, b)`` of
    ``v = m*t + b``."""
    pts = [(r[0], r[col]) for r in rows if t_lo <= r[0] <= t_hi]
    n = len(pts)
    if n < 3:
        raise SystemExit(f"fit window [{t_lo:g}, {t_hi:g}] holds only {n} samples")
    sx = sum(t for t, _ in pts)
    sy = sum(v for _, v in pts)
    sxx = sum(t * t for t, _ in pts)
    sxy = sum(t * v for t, v in pts)
    denom = n * sxx - sx * sx
    m = (n * sxy - sx * sy) / denom
    b = (sy - m * sx) / n
    return m, b


def analyze_edge(rows, t_edge: float, pgdg_direction: str) -> dict:
    """Decompose one edge's dwell into start level, ramp slope and trip point."""
    col = {label: i + 1 for i, (_, label, _) in enumerate(PROBES)}
    crossings = runner.find_crossings(rows, col["PGDG"], PGDG_THRESH, t_edge)
    hit = next((t for t, direction in crossings if direction == pgdg_direction), None)
    if hit is None:
        raise SystemExit(f"no PGDG {pgdg_direction} through {PGDG_THRESH} V after t={t_edge:g}")
    t_x = _refine_crossing(rows, col["PGDG"], PGDG_THRESH, hit)
    dwell_s = t_x - t_edge
    v_trip = _interp(rows, col["NDG"], t_x)
    # Fit the slow I/C ramp over its middle half, away from both the switching
    # transient at the edge and XMG1's own feedback near the trip.
    m, b = _fit(rows, col["NDG"], t_edge + 0.25 * dwell_s, t_edge + 0.75 * dwell_s)
    v0 = m * t_edge + b
    v_pre = _interp(rows, col["NDG"], t_edge - 0.5e-6)
    return {
        "dwell_us": dwell_s * 1e6,
        "v_pre": v_pre,
        "v0": v0,
        "step": v0 - v_pre,
        "slope_v_per_us": m * 1e-6,
        "v_trip": v_trip,
        "dwell_pred_us": (v_trip - v0) / m * 1e6,
        "ndgp_pre": _interp(rows, col["NDGP"], t_edge - 0.5e-6),
        "ndgn_pre": _interp(rows, col["NDGN"], t_edge - 0.5e-6),
        "ndgp_mid": _interp(rows, col["NDGP"], t_edge + 0.5 * dwell_s),
        "ndgn_mid": _interp(rows, col["NDGN"], t_edge + 0.5 * dwell_s),
    }


GENERATED = tuple(
    str((CONTROL_DIR / name).relative_to(REPO_ROOT)) for name in ("results.md", "decks", "logs", "traces")
)


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
    trace_dir = CONTROL_DIR / "traces"
    for d in (deck_dir, log_dir, trace_dir):
        d.mkdir(exist_ok=True)

    for variant, _ in VARIANTS:
        (deck_dir / f"dut_{slug(variant)}.spice").write_text(dut_netlist(variant))

    results: dict[tuple[str, str], dict] = {}

    for variant, _ in VARIANTS:
        for point_id, corner_name, temp_c, vdd in POINTS:
            run_id = f"{slug(variant)}__{point_id}"
            deck_path = deck_dir / f"{run_id}.spice"
            log_path = log_dir / f"{run_id}.log"
            trace_path = trace_dir / f"{run_id}.csv"
            deck_path.write_text(compose_deck(pdk, variant, corner_name, temp_c, vdd, options, deck_dir))
            proc = subprocess.run(
                ["ngspice", "-b", deck_path.name],
                capture_output=True,
                text=True,
                cwd=deck_dir,
                check=False,
                timeout=1800,
            )
            output = proc.stdout + "\n" + proc.stderr
            log_path.write_text(output)
            raw_trace = deck_dir / "trace.csv"
            if not raw_trace.exists():
                print(f"{run_id}: ngspice produced no trace.csv", file=sys.stderr)
                print(output[-4000:], file=sys.stderr)
                return 2
            rows = runner.parse_wrdata_trace(raw_trace.read_text(), len(PROBES))
            raw_trace.unlink()
            if not rows:
                print(f"{run_id}: could not parse any rows from trace.csv", file=sys.stderr)
                return 2

            kept = [r for r in rows if any(lo <= r[0] <= hi for lo, hi in TRACE_WINDOWS)]
            header = "* time " + " ".join(label for _, label, _ in PROBES)
            trace_path.write_text(
                header + "\n" + "\n".join(" ".join(f"{v:.10g}" for v in r) for r in kept) + "\n"
            )

            results[(variant, point_id)] = {
                "rise": analyze_edge(rows, RISE_EDGE_S, "rise"),
                "fall": analyze_edge(rows, FALL_EDGE_S, "fall"),
            }
            fall = results[(variant, point_id)]["fall"]
            print(
                f"{run_id}: fall dwell {fall['dwell_us']:.3f} us "
                f"(V0 {fall['v0']:.4f} V, slope {fall['slope_v_per_us']:.4f} V/us, "
                f"Vtrip {fall['v_trip']:.4f} V)"
            )

    write_results(results, pdk, ngspice_version)
    print(f"wrote {(CONTROL_DIR / 'results.md').relative_to(REPO_ROOT)}")
    return 0


def write_results(results: dict, pdk, ngspice_version: str) -> None:
    lines: list[str] = [
        "# por-output-chain-deglitch asymmetry probe -- generated, do not edit",
        "",
        "Generated by `sim/por-output-chain-deglitch/control/run_deglitch_asym_probe.py`"
        " (issue #182). Re-run it to regenerate this file, the decks under `decks/`,"
        " the raw ngspice logs under `logs/` and the cropped traces under `traces/`."
        " The numbers quoted in `design/por_output_chain.md` are transcribed from"
        " here, and from nowhere else.",
        "",
        "This is a **control experiment, not a record**: three PVT points tracing"
        " internal nodes is a diagnosis, and this directory is overwritten in place"
        " on every run. The corner-grid evidence for"
        " [`por-brownout`](../../../spec/target-spec.md#por-brownout) stays in"
        " `sim/por-output-chain-deglitch/records/` (`sim/README.md`, \"Control"
        " experiments\").",
        "",
        f"- ngspice: `{ngspice_version}`",
        f"- PDK: `{pdk.variant}@{pdk.version}` ({pdk.source})",
        f"- harness: `{HARNESS_VERSION}`",
        "",
        "## The decomposition",
        "",
        "Each POR_RAW edge starts a slow `I/C` ramp on `NDG` that ends when `XMG1`"
        " flips `PGDG` through the records' own 1.0 V measurement threshold, so",
        "",
        "```",
        "dwell = (V_trip - V0) / slope",
        "```",
        "",
        "where `V0` is the level the ramp actually starts from -- the ramp fitted over"
        " its middle half and extrapolated back to the edge -- **not** the pre-edge"
        " rail. `step = V0 - V(NDG) just before the edge` is therefore the charge"
        " dumped onto (or pulled off) `NDG` at the instant the input pair switches.",
        "",
    ]

    for edge, edge_name, recorded in (
        ("fall", "POR_RAW falling (`dwell_pgdg_1x_us`) -- the por-brownout direction", RECORDED_US),
        ("rise", "POR_RAW rising (`dwell_rise_1x_us`)", RECORDED_RISE_US),
    ):
        lines += [
            f"### {edge_name}",
            "",
            "| corner | variant | dwell | pre-edge `NDG` | step | `V0` | slope | `V_trip` | `(V_trip-V0)/slope` |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for point_id, _, _, _ in POINTS:
            for variant, _ in VARIANTS:
                r = results[(variant, point_id)][edge]
                lines.append(
                    f"| `{point_id}` | `{variant}` | {r['dwell_us']:.3f} us |"
                    f" {r['v_pre']:.4f} V | {r['step']:+.4f} V | {r['v0']:.4f} V |"
                    f" {r['slope_v_per_us']:+.5f} V/us | {r['v_trip']:.4f} V |"
                    f" {r['dwell_pred_us']:.3f} us |"
                )
        lines += ["", "Cross-check against the two records at the same corners:", ""]
        lines += [
            "| corner | this probe, `schematic` | record `20260802-205904-bdc077d` |"
            " this probe, `postlayout` | record `20260811-055634-d0ee17d` |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        for point_id, _, _, _ in POINTS:
            lines.append(
                f"| `{point_id}` | {results[('schematic', point_id)][edge]['dwell_us']:.3f} us |"
                f" {recorded[point_id]['schematic']} us |"
                f" {results[('postlayout', point_id)][edge]['dwell_us']:.3f} us |"
                f" {recorded[point_id]['postlayout']} us |"
            )
        lines.append("")

    lines += ["## Tail-node levels", "", "| corner | variant | edge | `NDGP` before | `NDGP` mid-ramp | `NDGN` before | `NDGN` mid-ramp |", "| --- | --- | --- | ---: | ---: | ---: | ---: |"]
    for point_id, _, _, _ in POINTS:
        for variant, _ in VARIANTS:
            for edge in ("fall", "rise"):
                r = results[(variant, point_id)][edge]
                lines.append(
                    f"| `{point_id}` | `{variant}` | {edge} | {r['ndgp_pre']:.4f} V |"
                    f" {r['ndgp_mid']:.4f} V | {r['ndgn_pre']:.4f} V | {r['ndgn_mid']:.4f} V |"
                )
    lines.append("")

    lines += ["## Variants", "", "| variant | DUT netlist |", "| --- | --- |"]
    for variant, description in VARIANTS:
        lines.append(f"| `{variant}` | {description} |")
    lines.append("")

    (CONTROL_DIR / "results.md").write_text("\n".join(lines))


if __name__ == "__main__":
    raise SystemExit(main())
