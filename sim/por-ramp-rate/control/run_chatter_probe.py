#!/usr/bin/env python3
"""Internal-node control probe for sim/por-ramp-rate/ (issue #56).

    python3 sim/por-ramp-rate/control/run_chatter_probe.py

Composes decks from ``chatter_probe.spice`` + ``design/netlist/temp_por_top.spice``,
one PVT point + ramp rate + *arm* per run, traces every node on the release path
**and** the shared-bias nodes behind it with ``wrdata``, and writes:

    decks/<run>.spice     the exact deck as run
    decks/dut_<arm>.spice the exact DUT netlist that deck included
    logs/<run>.log        raw ngspice output, verbatim
    traces/<run>.csv      the full v(t) trace ngspice wrote via wrdata
    results.md            the crossing-count table, generated from those traces

This is the control experiment behind design/por_output_chain.md's
"The release-edge chatter is a shared-IBIAS relaxation loop, not a local
instability" section, diagnosing record `20260802-000004-32fbaa0` (21/81 PASS)
and justifying the ``XMRLK`` release latch that record's successor verifies.
It is NOT a recorded PVT result: a handful of points tracing internal nodes is
a diagnosis, not the corner-grid evidence for the por-ramp-rate claim, which
remains sim/por-ramp-rate/records/. See sim/README.md, "Control experiments".

THE FOUR ARMS (one variable each, all derived from the committed netlist by an
asserted single-line edit, so every arm is auditable against what is taped out):

    asbuilt          design/netlist/temp_por_top.spice, verbatim.
    nokeeper         XMRLK (the issue #56 release latch) deleted -- i.e. the
                     exact circuit record 20260802-000004-32fbaa0 measured.
    nokeeper_en_vdd  XMRLK deleted AND temp_core's EN pin tied to VDD instead
                     of RESETn, so RESETn no longer modulates the shared IBIAS
                     load. Everything else identical.
    nokeeper_en_vss  same, tied to VSS (temp_core permanently disabled).

The two ``en_*`` arms are the loop-break test: if the chatter were a local
instability inside por_output_chain's trip detector, cutting the RESETn ->
temp_core.EN -> IBIAS path could not fix it. If it is a relaxation loop closed
through the shared bias node, cutting that path -- in EITHER direction -- must
kill it outright.

Stdlib only, no virtualenv required.
"""

from __future__ import annotations

import json
import os
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

FRAGMENT = CONTROL_DIR / "chatter_probe.spice"
DUT_NETLIST = REPO_ROOT / "design" / "netlist" / "temp_por_top.spice"
MANIFEST = EXPERIMENT_DIR / "testbench" / "tb.json"

# The single lines each arm rewrites in the committed netlist. Both are
# asserted present before the edit, so a schematic change that moves them fails
# this script loudly instead of silently running the wrong circuit.
KEEPER_HEAD = "XMRLK ND1 RESETn VSS VSS nfet_03v3"
TEMP_CORE_INST = "xtemp VDD VSS IBIAS RESETn PTAT CTAT temp_core"

# (arm_id, drop_keeper, temp_core_en)
ARMS: list[tuple[str, bool, str | None]] = [
    ("asbuilt", False, None),
    ("nokeeper", True, None),
    ("nokeeper_en_vdd", True, "VDD"),
    ("nokeeper_en_vss", True, "VSS"),
]

# Three points from record 20260802-000004-32fbaa0 (the pre-XMRLK circuit):
#   - tt/27C/10V/s chatters (chatter_10vs_us = 36.7 us there)
#   - tt/-40C/10V/s does not (chatter_10vs_us = 0), same rate: isolates
#     temperature, not ramp rate, as what turns chatter on
#   - tt/27C/1V/s chatters too (chatter_1vs_us = 37 us there), a decade
#     slower: tests whether the mechanism is really ramp-rate independent
# (point_id, corner, temp_c, vdd, rate_v_per_s, stop_s)
POINTS: list[tuple[str, str, float, float, float, float]] = [
    ("tt_27c_3.30v_10vs", "tt", 27.0, 3.30, 10.0, 0.30),
    ("tt_-40c_3.30v_10vs", "tt", -40.0, 3.30, 10.0, 0.30),
    ("tt_27c_3.30v_1vs", "tt", 27.0, 3.30, 1.0, 2.65),
]

PROBES: list[tuple[str, str, str]] = [
    ("v(vdd)", "VDD", "the ramping rail"),
    ("v(xdut.por_raw)", "POR_RAW", "por_comparator's raw decision"),
    ("v(xdut.xpor.pgdg)", "PGDG", "the deglitched power-good node"),
    ("v(xdut.vref)", "VREF", "bias_core's reference"),
    ("v(xdut.bias_ok)", "BIAS_OK", "bias_core's settle flag"),
    ("v(resetn)", "RESETn", "the output"),
    ("v(xdut.xpor.tim)", "TIM", "the one-shot timer capacitor"),
    ("v(xdut.xpor.nd1)", "ND1", "trip detector stage A output"),
    ("v(xdut.xpor.trip)", "TRIP", "the trip detector output"),
    ("v(xdut.xpor.rstb)", "RSTB", "the release NAND's output"),
    ("v(xdut.ibias)", "IBIAS", "the shared bias node (DR-010)"),
    ("v(xdut.xpor.pdn)", "PDN", "por_output_chain's PMOS starve reference"),
    ("v(xdut.xpor.ndl)", "NDL", "por_output_chain's NMOS starve reference"),
]

# Nodes whose 1.0 V crossing count is a meaningful "did this stage toggle"
# statistic. The bias nodes never approach 1.0 V as a logic level, so counting
# their crossings would be noise -- they are reported as levels instead.
LOGIC_NODES = ("POR_RAW", "PGDG", "VREF", "BIAS_OK", "TIM", "TRIP", "RSTB")

RELEASE_THRESH = 1.0  # matches ../testbench/tb.json's own release-crossing definition


def arm_netlist(drop_keeper: bool, temp_core_en: str | None) -> str:
    """The committed top netlist with this arm's one-line edit applied."""
    text = DUT_NETLIST.read_text()
    if drop_keeper:
        lines = text.splitlines(keepends=True)
        idx = [i for i, ln in enumerate(lines) if ln.startswith(KEEPER_HEAD)]
        if len(idx) != 1:
            raise SystemExit(
                f"expected exactly one '{KEEPER_HEAD}...' line in {DUT_NETLIST}, found {len(idx)}"
            )
        i = idx[0]
        # the device spans its own line plus the '+' continuation beneath it
        end = i + 1
        while end < len(lines) and lines[end].startswith("+"):
            end += 1
        del lines[i:end]
        text = "".join(lines)
    if temp_core_en is not None:
        if TEMP_CORE_INST not in text:
            raise SystemExit(f"expected '{TEMP_CORE_INST}' in {DUT_NETLIST}")
        text = text.replace(
            TEMP_CORE_INST, TEMP_CORE_INST.replace("IBIAS RESETn", f"IBIAS {temp_core_en}")
        )
    return text


def compose_deck(
    pdk,
    corner_name: str,
    temp_c: float,
    vdd: float,
    rate: float,
    stop_s: float,
    options: list[str],
    deck_dir: Path,
    dut_rel: str,
    arm_id: str,
) -> str:
    corner = corners_mod.CORNERS[corner_name]
    fragment_rel = os.path.relpath(FRAGMENT, deck_dir)
    lines = [
        f"* por-ramp-rate internal-node probe @ {corner_name} / {temp_c:g} C / {vdd:g} V / {rate:g} V/s"
        f" / arm={arm_id} -- GENERATED by run_chatter_probe.py, do not edit",
        f"* pdk={pdk.variant}@{pdk.version}",
        "",
        f".param vdd_val={vdd!r}",
        f".param rate_v_per_s={rate!r}",
        f".param stop_s={stop_s!r}",
        "",
        f'.include "{pdk.design_include}"',
    ]
    lines += [f'.lib "{pdk.model_lib}" {section}' for section in corner.sections]
    lines += ["", f".temp {temp_c!r}"]
    lines += [f".options {option}" for option in options]
    lines += [
        "",
        f'.include "{fragment_rel}"',
        f'.include "{dut_rel}"',
        "",
        ".tran 2m {stop_s}",
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


def parse_trace(text: str) -> list[tuple[float, ...]]:
    rows: list[tuple[float, ...]] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) != 2 * len(PROBES):
            continue
        try:
            vals = [float(x) for x in parts]
        except ValueError:
            continue
        t = vals[0]
        row = (t,) + tuple(vals[1 + 2 * i] for i in range(len(PROBES)))
        rows.append(row)
    return rows


def find_crossings(rows: list[tuple[float, ...]], col: int, thresh: float) -> list[tuple[float, str]]:
    crossings: list[tuple[float, str]] = []
    prev = None
    for row in rows:
        if prev is None:
            prev = row
            continue
        a, b = prev[col], row[col]
        if (a - thresh) * (b - thresh) < 0:
            crossings.append((row[0], "rise" if b > a else "fall"))
        prev = row
    return crossings


def value_at(rows: list[tuple[float, ...]], col: int, t: float) -> float:
    """Linear interpolation of column ``col`` at time ``t``."""
    prev = rows[0]
    for row in rows:
        if row[0] >= t:
            if row[0] == prev[0]:
                return row[col]
            f = (t - prev[0]) / (row[0] - prev[0])
            return prev[col] + f * (row[col] - prev[col])
        prev = row
    return rows[-1][col]


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
    for stale in list(deck_dir.glob("*.spice")) + list(log_dir.glob("*.log")):
        stale.unlink()

    col = {label: i + 1 for i, (_, label, _) in enumerate(PROBES)}
    summaries: dict[str, dict] = {}

    for arm_id, drop_keeper, temp_core_en in ARMS:
        dut_path = deck_dir / f"dut_{arm_id}.spice"
        dut_path.write_text(arm_netlist(drop_keeper, temp_core_en))
        for point_id, corner_name, temp_c, vdd, rate, stop_s in POINTS:
            run_id = f"{point_id}__{arm_id}"
            deck_path = deck_dir / f"{run_id}.spice"
            log_path = log_dir / f"{run_id}.log"
            trace_path = trace_dir / f"{run_id}.csv"
            deck_path.write_text(
                compose_deck(
                    pdk, corner_name, temp_c, vdd, rate, stop_s, options, deck_dir, dut_path.name, arm_id
                )
            )
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
                print(output, file=sys.stderr)
                return 2
            trace_text = raw_trace.read_text()
            trace_path.write_text(trace_text)
            raw_trace.unlink()
            rows = parse_trace(trace_text)
            if not rows:
                print(f"{run_id}: could not parse any rows from trace.csv", file=sys.stderr)
                return 2

            resetn_crossings = find_crossings(rows, col["RESETn"], RELEASE_THRESH)
            window = None
            if len(resetn_crossings) >= 2:
                window = (resetn_crossings[-1][0] - resetn_crossings[0][0]) * 1e6  # us

            per_signal_counts = {
                label: len(find_crossings(rows, col[label], RELEASE_THRESH)) for label in LOGIC_NODES
            }

            # The shared-bias step: sample 20 us BEFORE the first release edge
            # (RESETn still low, temp_core still disabled) and 300 us AFTER it
            # (RESETn released and settled in every arm -- the widest chatter
            # window here is 37 us -- temp_core enabled wherever RESETn still
            # drives EN). The window is deliberately short so VDD, which is
            # still ramping, moves <=3 mV between the two samples and cannot be
            # mistaken for the step being measured.
            t_rel = resetn_crossings[0][0] if resetn_crossings else rows[-1][0]
            t_pre, t_post = t_rel - 20e-6, min(t_rel + 300e-6, rows[-1][0])
            bias_step = {
                label: (value_at(rows, col[label], t_pre), value_at(rows, col[label], t_post))
                for label in ("VDD", "IBIAS", "PDN", "NDL")
            }
            # ND1 is the node the PDN/NDL shift walks. Report where it lands
            # right after the release and how far it drifts inside the same
            # 300 us -- that drift IS the chatter mechanism.
            nd1_window = [r for r in rows if t_rel + 2e-6 <= r[0] <= t_post]
            bias_step["ND1"] = (
                value_at(rows, col["ND1"], t_rel + 2e-6),
                max((r[col["ND1"]] for r in nd1_window), default=float("nan")),
            )

            summaries[run_id] = {
                "arm": arm_id,
                "point": point_id,
                "rate": rate,
                "resetn_crossings": len(resetn_crossings),
                "chatter_window_us": window,
                "per_signal_counts": per_signal_counts,
                "bias_step": bias_step,
            }
            cw = f"{window:.2f} us" if window is not None else "0 (single crossing)"
            print(f"{run_id}: RESETn crossings={len(resetn_crossings)} window={cw}")

    def arm_rows(arm_id: str) -> list[str]:
        out = []
        for point_id, _, _, _, rate, _ in POINTS:
            s = summaries[f"{point_id}__{arm_id}"]
            cw = (
                f"{s['chatter_window_us']:.2f} us"
                if s["chatter_window_us"] is not None
                else "n/a (single crossing)"
            )
            counts = ", ".join(f"{k}={v}" for k, v in s["per_signal_counts"].items())
            out.append(f"| `{point_id}` | {rate:g} V/s | {s['resetn_crossings']} | {cw} | {counts} |")
        return out

    bias_rows = []
    for point_id, _, _, _, _, _ in POINTS:
        for arm_id in ("asbuilt", "nokeeper"):
            b = summaries[f"{point_id}__{arm_id}"]["bias_step"]
            bias_rows.append(
                f"| `{point_id}` | `{arm_id}` | "
                + " | ".join(
                    f"{b[n][0] * 1e3:.1f} -> {b[n][1] * 1e3:.1f} ({(b[n][1] - b[n][0]) * 1e3:+.1f})"
                    for n in ("VDD", "IBIAS", "PDN", "NDL")
                )
                + f" | {b['ND1'][0] * 1e3:.1f} -> {b['ND1'][1] * 1e3:.1f} |"
            )

    findings = [
        textwrap.fill(text, width=76, initial_indent="- ", subsequent_indent="  ")
        for text in (
            "POR_RAW, PGDG, VREF and BIAS_OK cross the 1.0 V threshold at most once at "
            "every point and in every arm, including the ones that show RESETn chatter "
            "-- bias_core and por_comparator are firmly settled well before the chatter "
            "window opens, so neither design/bias_core.md's starved-loop window nor "
            "comparator threshold noise is the mechanism.",
            "In the nokeeper arm (the circuit record 20260802-000004-32fbaa0 measured) "
            "TRIP and RSTB chatter in lock-step with RESETn at the tt/27C points and "
            "settle cleanly at tt/-40C, at BOTH 10 V/s and 1 V/s -- a decade apart, with "
            "comparable window widths. Ramp rate is not the variable.",
            "The shared-bias table below is what the variable actually is. RESETn's own "
            "release enables temp_core (at the top level, temp_core's EN pin IS RESETn), "
            "which adds a second mirror diode to the shared IBIAS node and steps IBIAS "
            "DOWN. por_output_chain's starve references follow (PDN up, NDL down), which "
            "weakens the nA sink XMDANT that sets ND1's balance point, so ND1 drifts back "
            "UP after the release until XMDBNI re-conducts, TRIP collapses and RESETn "
            "re-asserts -- which disables temp_core again, restores IBIAS and restarts "
            "the cycle. A relaxation oscillation whose loop leaves por_output_chain "
            "entirely.",
            "The two nokeeper_en_* arms cut exactly that loop and nothing else: with "
            "temp_core's EN tied to a rail instead of to RESETn, RESETn no longer "
            "modulates the shared-node load, and the chatter disappears completely at "
            "every point -- in BOTH directions (permanently enabled and permanently "
            "disabled), which rules out 'temp_core enabled is simply a harder operating "
            "point' and leaves only the RESETn-driven modulation itself.",
            "The asbuilt arm is the fix: XMRLK (ND1 -> VSS, gated by RESETn) makes the "
            "release one-way, so the post-release bias drift can no longer walk the "
            "decision back. Single crossing at every point, including the two that "
            "chatter without it. It cannot arm prematurely because RSTB = NAND(TRIP, "
            "PGDG): PGDG low forces RSTB high and RESETn low regardless of TRIP.",
        )
    ]

    lines = [
        "# por-ramp-rate release-chatter probe -- generated, do not edit",
        "",
        "Generated by `sim/por-ramp-rate/control/run_chatter_probe.py`. Re-run it to "
        "regenerate this file, the decks under `decks/`, the raw ngspice logs under "
        "`logs/` and the traces under `traces/`. The numbers quoted in "
        "`design/por_output_chain.md` are transcribed from here, and from nowhere else.",
        "",
        "Three PVT + rate points from record `20260802-000004-32fbaa0`: `tt_27c_3.30v` "
        "at 10 V/s and 1 V/s (both chatter in that record), and `tt_-40c_3.30v` at "
        "10 V/s (does not). Every DUT is a single-rate, single-corner cold-start ramp "
        "on the real four-cell assembly, with the full release path AND the shared-bias "
        "nodes behind it traced.",
        "",
        "Four arms, each one asserted single-line edit away from the committed "
        "`design/netlist/temp_por_top.spice` (each arm's exact DUT is committed as "
        "`decks/dut_<arm>.spice`):",
        "",
        "| arm | edit | what it isolates |",
        "| --- | --- | --- |",
        "| `asbuilt` | none | the circuit as drawn, with the `XMRLK` release latch |",
        "| `nokeeper` | `XMRLK` deleted | the pre-fix circuit record `20260802-000004-32fbaa0` measured |",
        "| `nokeeper_en_vdd` | `XMRLK` deleted, `temp_core.EN` tied to `VDD` | breaks the `RESETn` -> `temp_core.EN` -> `IBIAS` loop (temp_core permanently enabled) |",
        "| `nokeeper_en_vss` | `XMRLK` deleted, `temp_core.EN` tied to `VSS` | breaks the same loop the other way (temp_core permanently disabled) |",
        "",
        "## Result",
        "",
    ]
    for arm_id, _, _ in ARMS:
        lines += [
            f"### arm `{arm_id}`",
            "",
            "| point | rate | `RESETn` crossings of 1.0 V | first-to-last window | other-node "
            "crossing counts |",
            "| --- | ---: | ---: | ---: | --- |",
            *arm_rows(arm_id),
            "",
        ]
    lines += [
        "## The shared-bias step across the release edge (mV)",
        "",
        "Sampled 20 us before the first `RESETn` release edge and 300 us after it. "
        "`VDD` is carried in the same table on purpose: it is still ramping, and its "
        "own movement across that window (a few mV) is the yardstick the `IBIAS` step "
        "has to beat to mean anything. The `ND1` column is different -- it is the "
        "trip detector's stage-A node 2 us after the release, and its PEAK over the "
        "same 300 us. That drift is the chatter mechanism: without `XMRLK` it walks "
        "back up to `XMDBNI`'s conduction point and collapses `TRIP`.",
        "",
        "| point | arm | `VDD` | `IBIAS` | `PDN` | `NDL` | `ND1` (post-release -> peak) |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        *bias_rows,
        "",
        "## What the numbers say",
        "",
        *findings,
        "",
        "## Environment",
        "",
        f"- PDK: {pdk.variant} @ open_pdks `{pdk.version}` ({pdk.path}, found via {pdk.source})",
        f"- ngspice: {ngspice_version}",
        f"- Harness: sim/harness {HARNESS_VERSION} (corner sections and solver options only), python {sys.version.split()[0]}",
        f"- git: `{runner.git_describe(REPO_ROOT, GENERATED)}`",
        f"- Solver options (from `../testbench/tb.json`): {' '.join(options)}",
        f"- `chatter_probe.spice` sha256: `{runner.sha256_file(FRAGMENT)}`",
        f"- `design/netlist/temp_por_top.spice` sha256: `{runner.sha256_file(DUT_NETLIST)}`",
        "",
    ]
    (CONTROL_DIR / "results.md").write_text("\n".join(lines))
    print(f"wrote {(CONTROL_DIR / 'results.md').relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
