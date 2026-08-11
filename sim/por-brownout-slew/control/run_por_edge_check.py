#!/usr/bin/env python3
"""Cheap gate-check: is the ideal-`por`-interconnect edge worth a re-route? (#232)

    python3 sim/por-brownout-slew/control/run_por_edge_check.py
    python3 sim/por-brownout-slew/control/run_por_edge_check.py --report-only

WHAT THIS ADDS

`run_net_attribution.py` (#214) found that making `por_output_chain`'s own
13 nets ideal (`netlists/na-por.spice`, 522.9 fF / 8.9 % of the cell's
interconnect removed) converts the extracted netlist's 2.50 mV/µs near-miss
at `ss`/-40 °C/2.97 V from a 45.0 µs FAIL to a 303.4 µs PASS, with **no**
change to the bias-collapse state variable at all (`recovered` = 0.00 at
every supply): at this rung the failure is `por_output_chain`'s own
deglitch dwell running long under its extracted loading, not `bias_core`
starving. That is a lever on where the extracted netlist's own transition
edge sits, and therefore on how much of DR-019's 2.30 mV/µs re-cost is
recoverable -- but two rungs (2.50 and 3.40 mV/µs) bracket a boundary, they
do not locate one.

This control answers the cheap, pre-layout question #232 asks: **how far
past 2.50 mV/µs does the `por`-ideal edge reach**, at the one point that is
binding (2.97 V is the only supply of the three where `ext` fails at
2.50 mV/µs; 3.30 V and 3.63 V already pass there). If the answer is "close
to 2.50", the 8.9 % of `por_output_chain`'s ΣC that `netlists/na-por.spice`
removes is not worth drawing. If it reaches meaningfully further, a
corner-grid re-ladder against a real re-route becomes worth scoping.

METHOD -- one variable: the falling slew rate, at the one binding point

Two arms, `ext` (the extracted netlist, untouched) and `por`
(`netlists/na-por.spice`, `run_net_attribution.py`'s pre-built `por`-ideal
netlist -- generate that control first if this one reports the file
missing), at `ss`/-40 °C/2.97 V only -- the failing corner, not the full
three-supply family `run_net_attribution.py` and `run_band_mechanism.py`
keep, because #232 is scoped to bounding the edge at the one point that is
binding, not to re-deriving the supply axis.

Four rungs:

  * 2.50 mV/µs, both arms -- reproduces `net_attribution_results.md` §3's
    already-published -45.0 µs FAIL (`ext`) and +303.4 µs PASS (`por`)
    baselines, so the new points below are checked against a live rerun
    rather than trusted cold.
  * 2.80 mV/µs, `por` only -- `ext` already fails below 2.50, so its own
    result there is not informative; only whether the ideal-interconnect
    edge itself has moved is.
  * 3.00 mV/µs, `por` only -- same reasoning.

Every deck is built by `run_band_mechanism.deck()`, unmodified, exactly as
`run_net_attribution.py` and `run_postlayout_margin.py` (#188) already do,
so this control cannot drift from the measurement list its two siblings
share.

WHAT IT CANNOT DECIDE

This is a control, not a record: a one-supply-point, two-arm sweep is not
corner-grid evidence, so -- like its two siblings -- it does NOT go through
sim/run_corners.py and does NOT mint anything under `../records/`, and it
does not touch `spec/target-spec.md` or DR-019. Locating where the
transition edge actually sits (rather than bounding it between two rungs)
is a corner-grid ladder's job. Whether the ΣC reduction `netlists/na-por.spice`
models is achievable in a real re-route is a layout question this control
does not answer either -- see #214's own note that no single dominant net
exists in the `por_output_chain` group to widen or shield.

Outputs, all regenerated on every run (a control is not a record):

    decks/edge-<arm>-<slew>mvus-2.97v.spice   the exact deck as run
    logs/edge-<arm>-<slew>mvus-2.97v.log      raw ngspice output, verbatim

...plus one dated section appended to `net_attribution_results.md` (not a
rewrite of the sections `run_net_attribution.py` owns -- see
`update_results_md()`), per `sim/`'s append-only-evidence convention.

The `edge-` prefix keeps these decks and logs out of `run_band_mechanism.py`'s
`a-`/`b-`, `run_postlayout_margin.py`'s `pl-` and `run_net_attribution.py`'s
`na-` namespaces, so none of the four scripts can overwrite another's.

Stdlib only, no virtualenv required.
"""

from __future__ import annotations

import datetime
import importlib.util
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CONTROL_DIR = Path(__file__).resolve().parent
REPO_ROOT = CONTROL_DIR.parents[2]

sys.path.insert(0, str(REPO_ROOT / "sim"))

from harness import HARNESS_VERSION, cliutil, runner  # noqa: E402
from harness.pdk import PdkNotFound, find_pdk  # noqa: E402

# run_band_mechanism.py lives beside this file rather than on sys.path as a
# package, so it is loaded by path -- the same way run_net_attribution.py and
# run_postlayout_margin.py load it. Reuse rather than copy: its deck() is the
# measurement list every arm in this family must share.
_spec = importlib.util.spec_from_file_location(
    "run_band_mechanism", CONTROL_DIR / "run_band_mechanism.py"
)
band = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(band)

EXTRACTED = REPO_ROOT / "layout" / "postlayout" / "temp_por_top.spice"
POR_IDEAL = CONTROL_DIR / "netlists" / "na-por.spice"

#: The one binding supply -- 2.97 V is the only one of the three `ss`/-40 °C
#: points where `ext` fails at 2.50 mV/µs (`net_attribution_results.md` §3);
#: 3.30 V and 3.63 V already pass there, so they are not part of the question
#: this control asks.
VDD_V = 2.97

#: `ext`'s own reproduction rung -- the extracted netlist's transition edge,
#: the lowest rung #188 recorded a failure at, and the rung that put DR-019's
#: bound at 2.30 mV/µs. Also `por`'s sanity-check rung: this arm's result
#: here should reproduce `net_attribution_results.md`'s already-published
#: +303.4 µs PASS before the two new rungs below are trusted.
BASELINE_SLEW_MVUS = 2.50

#: The two new rungs #232 asks for, `por` arm only -- `ext` already fails
#: below 2.50 mV/µs so re-running it faster is not informative.
NEW_SLEWS_MVUS = [2.80, 3.00]

#: arm label -> DUT netlist, and which rungs each arm runs.
ARMS: dict[str, Path] = {"ext": EXTRACTED, "por": POR_IDEAL}
SLEWS_BY_ARM: dict[str, list[float]] = {
    "ext": [BASELINE_SLEW_MVUS],
    "por": [BASELINE_SLEW_MVUS, *NEW_SLEWS_MVUS],
}

#: DR-019's ratified bound and the extracted netlist's own transition edge,
#: quoted for orientation only -- nothing here re-derives or changes either.
DR019_BOUND_MVUS = 2.30
EXT_EDGE_LO_MVUS, EXT_EDGE_HI_MVUS = 2.45, 2.50

RESETN_RATIO_KEY = "resetn_ratio_min_in_dip"

#: The issue's own order-of-magnitude "not worth it" threshold ("if the
#: ideal-interconnect edge only reaches ~2.6 mV/µs, the re-route is not
#: worth drawing"), read literally here rather than re-derived: the go/no-go
#: call is which side of THIS number the measured edge (or its bracket)
#: falls on, not an independently chosen bound.
GO_THRESHOLD_MVUS = 2.6

RESULTS_MD = CONTROL_DIR / "net_attribution_results.md"

#: Marks this control's appended section so a rerun replaces its own block
#: instead of accumulating duplicates, without touching the sections
#: run_net_attribution.py owns above it. sim/ results are append-only
#: evidence (see CLAUDE.md) -- a rerun on a later date grows the file with a
#: new dated section rather than erasing the previous one.
SECTION_MARKER = "<!-- run_por_edge_check.py:{date} -->"
SECTION_MARKER_RE = re.compile(
    r"\n## 7 — .*?\n<!-- run_por_edge_check\.py:\d{4}-\d{2}-\d{2} -->\n"
    r".*?(?=\n## |\Z)",
    re.DOTALL,
)


def variant_name(arm: str, slew_mvus: float) -> str:
    return f"edge-{arm}-{slew_mvus:g}mvus-{VDD_V:.2f}v"


def read_logs() -> dict[str, dict[str, float]]:
    """Re-derive this control's variants from the logs already on disk.

    Scoped to the ``edge-`` prefix so ``--report-only`` reads only this
    script's own runs and never its three siblings'.
    """
    log_dir = CONTROL_DIR / "logs"
    return {
        path.stem: runner.parse_bare_measurements(path.read_text())
        for path in sorted(log_dir.glob("edge-*.log"))
    }


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    report_only = "--report-only" in argv

    try:
        pdk = find_pdk()
    except PdkNotFound as exc:
        print(exc, file=sys.stderr)
        return 1

    if not POR_IDEAL.exists():
        print(
            f"{POR_IDEAL.relative_to(REPO_ROOT)} does not exist -- run "
            "run_net_attribution.py first to generate the por-ideal netlist "
            "this control runs against.",
            file=sys.stderr,
        )
        return 1

    options = cliutil.load_manifest(band.MANIFEST)["options"]

    if report_only:
        results = read_logs()
        if not results:
            print(
                "no edge-* logs to report from -- run without --report-only "
                "first",
                file=sys.stderr,
            )
            return 1
    else:
        jobs: list[tuple[str, str]] = []
        for arm, netlist in ARMS.items():
            for slew in SLEWS_BY_ARM[arm]:
                jobs.append(
                    (
                        variant_name(arm, slew),
                        band.deck(pdk, options, VDD_V, slew, None, netlist),
                    )
                )
        print(
            f"running {len(jobs)} deck(s) at {band.CORNER} / {band.TEMP_C:g} C"
            f" / {VDD_V:g} V ..."
        )
        with ThreadPoolExecutor(max_workers=min(4, len(jobs))) as pool:
            results = dict(
                zip(
                    [name for name, _ in jobs],
                    pool.map(lambda job: runner.run_deck(*job, CONTROL_DIR), jobs),
                )
            )

    update_results_md(pdk, options, results)
    print(f"appended to {RESULTS_MD}")
    return 0


def close_us(slew: float) -> float:
    return (band.edge_s(VDD_V, slew) + band.T_DWELL_S) * 1e6


def margin_us(res: dict[str, dict[str, float]], arm: str, slew: float) -> float | None:
    t = res.get(variant_name(arm, slew), {}).get("t_rst")
    if t is None:
        return None
    return close_us(slew) - (t - band.T_DIP_S) * 1e6


def passes(res: dict[str, dict[str, float]], arm: str, slew: float, bound: float) -> bool | None:
    v = res.get(variant_name(arm, slew), {}).get("rst_r_min")
    if v is None:
        return None
    return v <= bound


def update_results_md(pdk, options: list[str], res: dict[str, dict[str, float]]) -> None:
    if not RESULTS_MD.exists():
        print(
            f"{RESULTS_MD.relative_to(REPO_ROOT)} does not exist -- run "
            "run_net_attribution.py first so this control has a base "
            "document to append to.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    manifest = cliutil.load_manifest(band.MANIFEST)
    rst_bound = float(manifest["checks"][RESETN_RATIO_KEY]["max"])
    today = datetime.date.today().isoformat()

    base_slews = [BASELINE_SLEW_MVUS, *NEW_SLEWS_MVUS]

    lines: list[str] = []
    lines.append("")
    lines.append(
        f"## 7 — {band.CORNER}/{band.TEMP_C:g}°C/{VDD_V:g}V ideal-`por`-"
        "interconnect edge check"
    )
    lines.append(SECTION_MARKER.format(date=today))
    lines.append("")
    lines.append(
        f"**Generated by `run_por_edge_check.py` on {today}. Do not edit — "
        "re-run it.** Sections 1–6 above are `run_net_attribution.py`'s and "
        "are not touched by this script; this section is appended, and a "
        "rerun on the same date replaces only this section (see the marker "
        "comment above), per `sim/`'s append-only-evidence convention."
    )
    lines.append("")
    lines.append(
        "[#232](https://github.com/2AMLogic/gf180-temp-por/issues/232) asks "
        "how far past 2.50 mV/µs the `por`-ideal edge reaches, at the one "
        f"supply where `ext` fails at {BASELINE_SLEW_MVUS:g} mV/µs "
        f"({VDD_V:g} V — the other two, 3.30 V and 3.63 V, already pass "
        "there, see §3 above). This is a cheap gate-check ahead of any "
        "layout re-route, not a corner-grid ladder: it does not touch "
        "`spec/target-spec.md`, DR-019, or any `../records/` entry."
    )
    lines.append("")
    lines.append(
        f"- PVT point: `{band.CORNER}` / {band.TEMP_C:g} °C / {VDD_V:g} V "
        "only — the failing corner, not the three-supply family §2–§6 keep "
        "(one supply is not corner evidence either; see `sim/README.md`)"
    )
    lines.append(
        f"- Rungs: {BASELINE_SLEW_MVUS:g} mV/µs (reproduction) and "
        + ", ".join(f"{s:g}" for s in NEW_SLEWS_MVUS)
        + " mV/µs (new), `por` arm; "
        f"{BASELINE_SLEW_MVUS:g} mV/µs only, `ext` arm"
    )
    lines.append(f"- PDK: `{pdk.variant}` @ `{pdk.version}`")
    lines.append(f"- Harness version: `{HARNESS_VERSION}`")
    lines.append(
        "- Solver options (from `../testbench/tb.json`): "
        f"`{'`, `'.join(options)}`"
    )
    lines.append(
        f"- `PASS`/`FAIL` is `{RESETN_RATIO_KEY} ≤ {rst_bound:g}`, the "
        "grid's own checked discriminator, recomputed from this control's "
        "own trace over the same window `../testbench/tb.json` uses."
    )
    lines.append(
        "- `por` = `netlists/na-por.spice` (`run_net_attribution.py`'s "
        "13-net, 522.9 fF / 8.9 % ΣC ideal-`por_output_chain`-interconnect "
        "netlist); `ext` = `layout/postlayout/temp_por_top.spice`, untouched."
    )
    lines.append("")

    lines.append("### Reproduction check")
    lines.append("")
    lines.append(
        f"Before trusting the new {', '.join(f'{s:g}' for s in NEW_SLEWS_MVUS)} "
        f"mV/µs points, {BASELINE_SLEW_MVUS:g} mV/µs must reproduce "
        "`net_attribution_results.md` §3's already-published baselines at "
        f"{VDD_V:g} V: `ext` −45.0 µs **FAIL**, `por` +303.4 µs PASS."
    )
    lines.append("")
    lines.append(
        "| arm | margin at "
        f"{BASELINE_SLEW_MVUS:g} mV/µs (µs) | verdict | published margin (µs) "
        "| published verdict | reproduces? |"
    )
    lines.append("|---|---:|---|---:|---|---|")
    published = {"ext": (-45.0, "FAIL"), "por": (303.4, "PASS")}
    reproduced_ok = True
    for arm in ("ext", "por"):
        m = margin_us(res, arm, BASELINE_SLEW_MVUS)
        ok = passes(res, arm, BASELINE_SLEW_MVUS, rst_bound)
        verdict = "—" if ok is None else ("PASS" if ok else "**FAIL**")
        pub_m, pub_v = published[arm]
        # "reproduces" = same verdict and margin within 1.0 µs -- ngspice on
        # the same host/PDK/options is deterministic, so this is a tight
        # check, not a loose one; a miss here means one of the two arms'
        # netlists or decks has drifted since §3 was generated.
        matches = (
            m is not None
            and verdict.strip("*") == pub_v
            and abs(m - pub_m) <= 1.0
        )
        reproduced_ok = reproduced_ok and matches
        lines.append(
            f"| `{arm}` | " + ("—" if m is None else f"{m:+.1f}") + f" | "
            f"{verdict} | {pub_m:+.1f} | {pub_v} | "
            + ("yes" if matches else "**NO — see note below**") + " |"
        )
    lines.append("")
    if not reproduced_ok:
        lines.append(
            "**Reproduction check failed** — at least one of the two rows "
            "above did not match the published baseline within 1.0 µs / same "
            "verdict. Treat the new-rung results below as unverified until "
            "this is resolved: re-run `run_net_attribution.py` and diff "
            "`netlists/na-por.spice` and `layout/postlayout/temp_por_top.spice` "
            "against the shas this control's own decks were generated "
            "against before trusting anything past this point."
        )
        lines.append("")

    lines.append(f"### `por`-ideal edge: {BASELINE_SLEW_MVUS:g}–3.00 mV/µs")
    lines.append("")
    lines.append(
        "All times are µs after the dip starts, same convention as §3. A "
        "positive margin is a PASS within the window; `ext` is included at "
        f"{BASELINE_SLEW_MVUS:g} mV/µs only, for the Δ column."
    )
    lines.append("")
    lines.append(
        "| rung (mV/µs) | arm | window closes | `POR_RAW` asserts | "
        "`PGDG` falls | `RESETn` valid-low | margin | Δ vs `ext` @ "
        f"{BASELINE_SLEW_MVUS:g} | verdict |"
    )
    lines.append("|---:|---|---:|---:|---:|---:|---:|---:|---|")
    ext_base_margin = margin_us(res, "ext", BASELINE_SLEW_MVUS)

    def us_after_dip(name: str, key: str) -> float | None:
        t = res.get(name, {}).get(key)
        return None if t is None else (t - band.T_DIP_S) * 1e6

    def fmt_us(value: float | None) -> str:
        return "**never**" if value is None else f"{value:.1f}"

    for slew in base_slews:
        arms_here = ["ext", "por"] if slew == BASELINE_SLEW_MVUS else ["por"]
        for arm in arms_here:
            name = variant_name(arm, slew)
            m = margin_us(res, arm, slew)
            ok = passes(res, arm, slew, rst_bound)
            verdict = "—" if ok is None else ("PASS" if ok else "**FAIL**")
            delta = (
                "—"
                if (m is None or ext_base_margin is None)
                else f"{m - ext_base_margin:+.1f}"
            )
            lines.append(
                f"| {slew:g} | `{arm}` | {close_us(slew):.1f} | "
                f"{fmt_us(us_after_dip(name, 't_praw'))} | "
                f"{fmt_us(us_after_dip(name, 't_pgdg'))} | "
                f"{fmt_us(us_after_dip(name, 't_rst'))} | "
                + ("—" if m is None else f"{m:+.1f}")
                + f" | {delta} | {verdict} |"
            )
    lines.append("")

    lines.append("### Go / no-go")
    lines.append("")
    por_margins = {s: margin_us(res, "por", s) for s in base_slews}
    por_passes = {s: passes(res, "por", s, rst_bound) for s in base_slews}
    fastest = max(base_slews)

    if not reproduced_ok:
        verdict_text = (
            "**INCONCLUSIVE — reproduction check failed.** The new-rung "
            "results above cannot be trusted until the reproduction mismatch "
            "is resolved (see the note above); re-run this control after "
            "fixing it before acting on the go/no-go question."
        )
    elif any(v is None for v in por_passes.values()):
        verdict_text = (
            "**INCONCLUSIVE.** Not every rung tested returned a usable "
            "measurement (see the table above for `—`/`never` entries) — "
            "re-run this control and inspect `logs/edge-*.log` before "
            "drawing a go/no-go conclusion."
        )
    else:
        passing = sorted(s for s, ok in por_passes.items() if ok)
        failing = sorted(s for s, ok in por_passes.items() if not ok)
        if not failing:
            # `por` passes every rung tried -- the edge is not located, only
            # bounded from below at the fastest rung tested.
            fastest_margin = por_margins[fastest]
            verdict_text = (
                f"**GO on further characterization, NO-GO on drawing a "
                f"re-route from this control alone.** `por` passes every "
                f"rung tested up to {fastest:g} mV/µs with "
                f"{fastest_margin:+.1f} µs of margin still in hand at "
                f"{VDD_V:g} V — the ideal-`por`-interconnect edge has not "
                f"been located yet even at the fastest rung tried, so it "
                f"sits somewhere past {fastest:g} mV/µs, clear of both "
                f"{BASELINE_SLEW_MVUS:g} mV/µs and the ~2.6 mV/µs this "
                "issue's own order-of-magnitude estimate treated as the "
                "not-worth-it threshold. That is far enough past "
                f"{BASELINE_SLEW_MVUS:g} mV/µs to justify scoping a "
                "corner-grid re-ladder against a real re-route candidate — "
                "but this control only bounds the edge from below, it does "
                "not locate it, and it says nothing about whether "
                "522.9 fF / 8.9 % of `por_output_chain`'s ΣC is actually "
                "drawable (#214 found no single dominant net in this group "
                "to widen or shield). The next step, if pursued, is "
                "locating the actual edge with a proper ladder before any "
                "layout is touched, exactly as `net_attribution_results.md` "
                "§3's closing note anticipates."
            )
        else:
            # A failing rung was found: the edge is bracketed between the
            # last passing rung tried (lo, exclusive) and the first failing
            # one (hi, exclusive) -- read that bracket against the issue's
            # own ~2.6 mV/µs not-worth-it estimate, not against the fastest
            # rung tried in isolation (a failing fastest rung does not by
            # itself mean the edge is close to 2.50: it can equally mean the
            # edge moved a long way and this control simply ran past it).
            lo = max(passing) if passing else BASELINE_SLEW_MVUS
            hi = min(failing)
            if lo >= GO_THRESHOLD_MVUS:
                verdict_text = (
                    f"**GO on further characterization, NO-GO on drawing a "
                    f"re-route from this control alone.** `por` passes "
                    f"through {lo:g} mV/µs and fails by {hi:g} mV/µs, so the "
                    f"ideal-`por`-interconnect edge is bracketed between "
                    f"{lo:g} and {hi:g} mV/µs — already at or above the "
                    f"~{GO_THRESHOLD_MVUS:g} mV/µs this issue's own "
                    "order-of-magnitude estimate treated as the "
                    "not-worth-it threshold, and meaningfully past the "
                    f"extracted netlist's own {EXT_EDGE_LO_MVUS:g}–"
                    f"{EXT_EDGE_HI_MVUS:g} mV/µs edge (+"
                    f"{lo - EXT_EDGE_HI_MVUS:.2g} mV/µs at the lower bound "
                    "alone). That is far enough past "
                    f"{BASELINE_SLEW_MVUS:g} mV/µs to justify scoping a "
                    "corner-grid re-ladder against a real re-route "
                    "candidate before any layout is drawn — but this "
                    f"control only brackets the edge between {lo:g} and "
                    f"{hi:g} mV/µs, it does not locate it, and it says "
                    "nothing about whether 522.9 fF / 8.9 % of "
                    "`por_output_chain`'s ΣC is actually drawable (#214 "
                    "found no single dominant net in this group to widen "
                    "or shield)."
                )
            elif hi <= GO_THRESHOLD_MVUS:
                verdict_text = (
                    f"**NO-GO.** `por` passes through {lo:g} mV/µs and "
                    f"fails by {hi:g} mV/µs — the ideal-`por`-interconnect "
                    f"edge is bracketed between {lo:g} and {hi:g} mV/µs, "
                    f"below the ~{GO_THRESHOLD_MVUS:g} mV/µs this issue's "
                    "own order-of-magnitude estimate treated as the "
                    "not-worth-it threshold, and close to the extracted "
                    f"netlist's own {EXT_EDGE_LO_MVUS:g}–"
                    f"{EXT_EDGE_HI_MVUS:g} mV/µs edge rather than "
                    "meaningfully past it. The layout re-route "
                    "`netlists/na-por.spice` models (522.9 fF / 8.9 % of "
                    "the cell's ΣC, no single dominant net to target per "
                    "#214) is not worth drawing for this little headroom."
                )
            else:
                verdict_text = (
                    f"**MARGINAL.** `por` passes through {lo:g} mV/µs and "
                    f"fails by {hi:g} mV/µs — the ideal-`por`-interconnect "
                    f"edge is bracketed between {lo:g} and {hi:g} mV/µs, "
                    f"straddling the ~{GO_THRESHOLD_MVUS:g} mV/µs this "
                    "issue's own order-of-magnitude estimate treated as the "
                    "not-worth-it threshold. This control cannot make the "
                    "call either way from a two-rung bracket that straddles "
                    "the threshold; only a finer-grained sweep (or the "
                    "corner-grid ladder step 2 of #232's own \"Suggested "
                    "approach\" would eventually need anyway) can resolve "
                    "which side of the threshold the true edge sits on."
                )
    lines.append(verdict_text)
    lines.append("")

    lines.append(
        "*This section answers only the pre-layout gate-check step 1 of "
        "#232's own \"Suggested approach\" — it does not decide whether a "
        "re-route is drawable (step 2) or ratify any spec change (step 3, "
        "which needs its own decision record and its own corner-grid "
        "ladder). DR-019's 2.30 mV/µs bound is unchanged by this control.*"
    )
    lines.append("")

    new_section = "\n".join(lines)
    text = RESULTS_MD.read_text()
    if SECTION_MARKER_RE.search(text):
        text = SECTION_MARKER_RE.sub(new_section.rstrip("\n"), text, count=1)
        if not text.endswith("\n"):
            text += "\n"
    else:
        text = text.rstrip("\n") + "\n" + new_section
        if not text.endswith("\n"):
            text += "\n"
    RESULTS_MD.write_text(text)


if __name__ == "__main__":
    raise SystemExit(main())
