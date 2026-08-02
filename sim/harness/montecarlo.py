"""Monte Carlo mismatch sampling (issue #15).

``sim/harness/corners.py`` + ``runner.py`` sweep a *deterministic* PVT grid:
one ``.lib`` section bundle per named process corner, mismatch off
(``sw_stat_mismatch=0``, the default ``design.ngspice`` ships). That answers
"how far does the systematic/corner term move the answer" but not "how far
does device-to-device local mismatch move it" -- the question
``spec/target-spec.md`` section 2 ratifies as **[3σ]**: *process plus local
mismatch, Monte Carlo, N ≥ 500, evaluated at the row's binding corner*.

This module adds that second axis. It deliberately does **not** touch
``corners.py`` / ``runner.py`` / the deterministic PVT grid: an MC run is a
different *kind* of claim (a distribution at a handful of named binding
points, not a pass/fail at every point of an 81-point grid), so it gets its
own point type, its own deck composition, and its own record renderer,
sharing only what is genuinely generic (``report.py``'s git/environment
provenance, record-id allocation, and the append-only netlist-snapshot
writer).

How one MC "sample" works, mechanically (see ``sim/harness/README.md`` for
the deterministic-grid equivalent):

- **Process** is held at the row's own named binding corner -- the same
  deterministic ``.lib`` section bundle ``corners.py`` already defines (e.g.
  ``ss`` for ``por-vth-rise``'s max edge). This is not randomized; the
  deterministic corner-sweep records (#13, #14) already cover the
  process/temperature/rail axis.
- **Local mismatch** is turned on (``sw_stat_mismatch=1``, overriding
  ``design.ngspice``'s default 0) and made reproducible with a per-sample
  ``.option seed=<N>``: gf180mcu's mismatch parameters (``mis_vth``,
  ``mis_k``, ...) are ``.param``s declared *inside* each device's ``.subckt``
  body, so they are re-evaluated -- independently -- for every instantiated
  device every time the netlist is elaborated. One ngspice invocation with
  one seed therefore draws one internally-consistent "die": every mismatched
  device on it gets its own independent random offset, but running the same
  seed twice reproduces the identical die exactly (see the harness tests).
  ``sw_stat_global`` is left at its design.ngspice default of 0: global
  (die-to-die) process spread is exactly what the deterministic corner sweep
  already covers, so this axis adds only the local-mismatch term the
  ``[3σ]`` rows are still missing, rather than double-counting the same
  variation two different ways.
- **Ordering is load-bearing**: the ``.option seed=`` / ``.param
  sw_stat_mismatch=1`` overrides are emitted *after* the corner ``.lib``
  includes. ngspice keeps the *last* declaration of a duplicate ``.param``
  name (verified empirically -- see the harness tests), and
  ``design.ngspice``'s own ``sw_stat_mismatch=0`` default lives inside the
  ``.include`` a few lines above the override, so the override has to come
  after it to win.
- **N ≥ 500 independent samples per binding point**, each its own ngspice
  invocation (own seed, own log), summarized into mean / σ / empirical yield
  / the parametric mean ± 3σ bound spec/target-spec.md's own **[3σ]**
  definition asks be reported.
"""

from __future__ import annotations

import shutil
import statistics
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .corners import CORNERS, Corner
from .pdk import Pdk
from .runner import NGSPICE, DEFAULT_TIMEOUT_S, NgspiceMissing, PointResult, parse_measurements
from .testbench import Testbench

#: Floor ratified by spec/target-spec.md section 2: "[3σ] = process plus
#: local mismatch, Monte Carlo, N >= 500". A binding point configured below
#: this is a manifest error, not a silent under-run.
MIN_SAMPLES = 500


class ManifestError(ValueError):
    """The testbench's ``mc`` config is missing or malformed."""


@dataclass(frozen=True)
class BindingPoint:
    """One spec-ratified binding point: a named deterministic corner plus a
    (temperature, rail) pair, per the row's own "binds at" text in
    ``spec/target-spec.md``. Not a grid axis -- each row names its own.
    """

    label: str
    corner: Corner
    temp_c: float
    vdd: float


def load_binding_points(tb: Testbench) -> list[BindingPoint]:
    """Read ``tb.mc["binding_points"]``, resolving each ``corner`` name."""
    if not tb.mc:
        raise ManifestError(
            f"{tb.directory / 'tb.json'}: no 'mc' block -- this is not a "
            "Monte Carlo testbench (see sim/harness/montecarlo.py)"
        )
    raw_points = tb.mc.get("binding_points")
    if not raw_points:
        raise ManifestError("mc.binding_points must list at least one binding point")
    points: list[BindingPoint] = []
    seen_labels: set[str] = set()
    for entry in raw_points:
        label = entry["label"]
        if label in seen_labels:
            raise ManifestError(f"duplicate mc.binding_points label {label!r}")
        seen_labels.add(label)
        corner_name = entry["corner"]
        if corner_name not in CORNERS:
            raise ManifestError(
                f"mc.binding_points[{label!r}]: unknown corner {corner_name!r}; "
                f"known corners: {', '.join(sorted(CORNERS))}"
            )
        points.append(
            BindingPoint(
                label=label,
                corner=CORNERS[corner_name],
                temp_c=float(entry["temp_c"]),
                vdd=float(entry["vdd"]),
            )
        )
    return points


@dataclass(frozen=True)
class McPoint:
    """One Monte Carlo sample: a binding point plus a sample index/seed.

    Mirrors ``corners.PvtPoint`` closely enough to be a drop-in for
    ``report.write_netlist_snapshot`` and friends, but is intentionally a
    separate type: an MC record's grid is (binding point x sample), not
    (process x temperature x supply).
    """

    label: str
    corner: Corner
    temp_c: float
    vdd: float
    sample: int
    seed: int
    index: int = field(default=0, compare=False)

    @property
    def corner_id(self) -> str:
        """``<label>_<process>_<temp>c_<supply>v_s<sample>`` -- extends the
        ``sim/README.md`` ``<corner-id>`` convention with the binding-point
        label and sample index an MC record needs to stay unique and
        traceable across N >= 500 samples per binding point.
        """
        return (
            f"{self.label}_{self.corner.name}_{self.temp_c:g}c_{self.vdd:.2f}v"
            f"_s{self.sample:04d}"
        )

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "corner": self.corner.name,
            "corner_sections": list(self.corner.sections),
            "temp_c": self.temp_c,
            "vdd": self.vdd,
            "sample": self.sample,
            "seed": self.seed,
            "corner_id": self.corner_id,
        }


def build_mc_grid(
    binding_points: list[BindingPoint],
    n: int,
    seed_base: int,
    enforce_min: bool = True,
) -> list[McPoint]:
    """N samples per binding point, each with a unique, reproducible seed.

    Seeds are assigned ``seed_base + binding_index * 100_000 + sample`` so
    that (a) two different binding points in the same run never collide even
    at N in the tens of thousands, and (b) the seed for a given (binding
    point, sample) is a pure function of the manifest's ``seed_base`` --
    re-running the same manifest with the same ``--seed-base`` reproduces the
    identical sample set, which is what "reproducible per-sample via
    ``.option seed=``" in the record's Statistical convention field means.

    ``enforce_min`` mirrors ``sim/run_corners.py``'s ``--subset-reason`` /
    ``--no-write`` split: a *recorded* run must meet the N>=500 floor
    spec/target-spec.md section 2 sets for a ``[3σ]`` claim, but a
    ``--no-write`` debugging run (``sim/run_mc.py --n 5 --no-write``) is
    allowed to use a small N to iterate on a deck quickly.
    """
    if enforce_min and n < MIN_SAMPLES:
        raise ManifestError(
            f"N={n} is below the spec/target-spec.md section 2 floor of "
            f"N>={MIN_SAMPLES} for a [3sigma] Monte Carlo claim"
        )
    points: list[McPoint] = []
    index = 0
    for bp_index, bp in enumerate(binding_points):
        for sample in range(n):
            points.append(
                McPoint(
                    label=bp.label,
                    corner=bp.corner,
                    temp_c=bp.temp_c,
                    vdd=bp.vdd,
                    sample=sample,
                    seed=seed_base + bp_index * 100_000 + sample,
                    index=index,
                )
            )
            index += 1
    return points


def _format_analysis(line: str, point: McPoint, tb: Testbench) -> str:
    """MC-specific ``%(name)s`` templating for ``tb.analyses`` lines.

    ngspice's own ``{expr}`` netlist substitution (used for ``vdd_val`` etc.
    everywhere else in this harness) is a *netlist-elaboration-time*
    mechanism and does not reach into interactive ``.control`` commands like
    ``dc temp <lo> <hi> <step>`` (verified empirically -- seeĥarness tests):
    a bare ``{temp_c}`` inside an ``analyses`` line would be passed to
    ngspice's ``dc`` command as the literal string ``temp_c`` and fail. So an
    MC testbench that needs the per-binding-point temperature *inside* a
    control command (rather than just via the deck's own ``.temp``) uses
    Python ``%``-style placeholders instead, substituted here, before the
    line ever reaches ngspice.
    """
    subs = {"temp_c": point.temp_c, "vdd": point.vdd, "vdd_nom": tb.nominal_supply_v}
    if "%(" not in line:
        return line
    return line % subs


def compose_mc_deck(tb: Testbench, pdk: Pdk, point: McPoint) -> str:
    """Build the self-contained ngspice deck for one Monte Carlo sample."""
    lines: list[str] = [
        f"* {tb.name} MC @ {point.corner_id} -- GENERATED by sim/harness, do not edit",
        f"* binding point={point.label}  corner={point.corner.name} ({point.corner.description})",
        f"* temp={point.temp_c} C  vdd={point.vdd} V  sample={point.sample}  seed={point.seed}",
        f"* pdk={pdk.variant}@{pdk.version}",
        "",
        "* ---- PVT parameters -------------------------------------------------",
        f".param vdd_nom={tb.nominal_supply_v!r}",
        f".param vdd_val={point.vdd!r}",
        f".param temp_c={point.temp_c!r}",
    ]
    for key, value in tb.params.items():
        lines.append(f".param {key}={value}")

    lines += [
        "",
        "* ---- gf180mcu models ------------------------------------------------",
        f'.include "{pdk.design_include}"',
    ]
    for section in point.corner.sections:
        lines.append(f'.lib "{pdk.model_lib}" {section}')

    lines += [
        "",
        "* ---- Monte Carlo mismatch (issue #15) --------------------------------",
        "* Process is the deterministic corner above (this row's own named",
        "* binding corner) -- NOT randomized here. Only local (intra-die)",
        "* mismatch is turned on, reproducibly, via a per-sample seed;",
        "* sw_stat_global stays at design.ngspice's default 0 because global",
        "* process spread is already the deterministic corner sweep's job",
        "* (#13/#14). This override MUST come after the .lib includes above:",
        "* ngspice keeps the LAST declaration of a duplicate .param name, and",
        "* design.ngspice's own sw_stat_mismatch=0 default lives inside the",
        "* .include a few lines up.",
        f".option seed={point.seed}",
        ".param sw_stat_mismatch=1",
        "",
        f".temp {point.temp_c!r}",
    ]
    for option in tb.options:
        lines.append(f".options {option}")

    lines += [
        "",
        "* ---- testbench ------------------------------------------------------",
        f'.include "{tb.netlist}"',
        "",
        "* ---- measurement ----------------------------------------------------",
        ".control",
        "set numdgt=10",
        "set noaskquit",
    ]
    for analysis in tb.analyses:
        lines.append(f"  {_format_analysis(analysis, point, tb)}")
    for name, expr in tb.measure.items():
        lines.append(f"  let m_{name} = {expr}")
    for name in tb.measure:
        lines.append(f"  print m_{name}")
    lines += [".endc", ".end", ""]
    return "\n".join(lines)


def run_mc_point(
    tb: Testbench,
    pdk: Pdk,
    point: McPoint,
    workdir: Path,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    log_dir: Path | None = None,
) -> PointResult:
    """Simulate one MC sample. Never raises for simulation failure.

    Structurally identical to ``runner.run_point`` (same ngspice invocation,
    same measurement parsing, same log-writing convention) but composes the
    deck via :func:`compose_mc_deck`. Kept separate rather than
    parameterising ``runner.run_point`` so the deterministic-grid path is
    untouched by this issue.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    log_dir = workdir if log_dir is None else log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    deck_path = workdir / f"{point.corner_id}.spice"
    log_path = log_dir / f"{point.corner_id}.log"
    deck_path.write_text(compose_mc_deck(tb, pdk, point))

    if shutil.which(NGSPICE) is None:
        raise NgspiceMissing("ngspice not found on PATH")

    started = time.monotonic()
    try:
        proc = subprocess.run(
            [NGSPICE, "-b", str(deck_path)],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=workdir,
            check=False,
        )
        output = proc.stdout + "\n" + proc.stderr
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - started
        log_path.write_text(f"TIMEOUT after {timeout_s}s\n")
        return PointResult(
            point=point,
            status="error",
            seconds=elapsed,
            deck=deck_path.name,
            log=log_path.name,
            message=f"ngspice timed out after {timeout_s}s",
        )
    elapsed = time.monotonic() - started
    log_path.write_text(output)

    measurements = parse_measurements(output)
    missing = [name for name in tb.measure if name not in measurements]
    if missing:
        first_error = next(
            (line.strip() for line in output.splitlines() if line.strip().startswith(("Error", "ERROR", "Fatal"))),
            "",
        )
        return PointResult(
            point=point,
            status="failed",
            measurements=measurements,
            missing=missing,
            seconds=elapsed,
            deck=deck_path.name,
            log=log_path.name,
            message=first_error or f"no measurements parsed",
        )

    return PointResult(
        point=point,
        status="ok",
        measurements=measurements,
        seconds=elapsed,
        deck=deck_path.name,
        log=log_path.name,
    )


def run_mc_grid(
    tb: Testbench,
    pdk: Pdk,
    points: list[McPoint],
    workdir: Path,
    jobs: int = 1,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    on_result=None,
    log_dir: Path | None = None,
) -> list[PointResult]:
    """Run every MC sample; results come back in the order ``points`` was given."""
    results: list[PointResult | None] = [None] * len(points)

    def _one(index_point):
        index, point = index_point
        result = run_mc_point(tb, pdk, point, workdir, timeout_s=timeout_s, log_dir=log_dir)
        results[index] = result
        if on_result is not None:
            on_result(result)
        return result

    if jobs <= 1:
        for item in enumerate(points):
            _one(item)
    else:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            list(pool.map(_one, enumerate(points)))

    return [r for r in results if r is not None]


# ---------------------------------------------------------------------------
# derived (Python-side) per-sample quantities
# ---------------------------------------------------------------------------

#: design/temp_core.md "Trim: single 25 C gain trim" / analyze_derived.py:
#: one trim LSB as a fraction of R2, quoted at the wider (conservative) end
#: of the measured 0.2287-0.2423 % range.
_TRIM_LSB_FRAC = 0.002423
_TRIM_REFERENCE_K = 298.15  # 25 C


def derive_temp_trim(measurements: dict[str, float]) -> dict[str, float]:
    """Per-sample trimmed temperature error from a die's own 25 C anchor.

    Same renormalisation ``sim/temp-accuracy-vt/analyze_derived.py`` performs
    on the deterministic grid (see that script's module docstring for the
    full rationale), applied per MC sample instead of per corner-sweep point:
    each die's *own* 25 C reading stands in for the one-point calibration a
    real 25 C production trim would perform on that same die, so
    ``k25`` is per-sample, not the shared nominal constant
    ``terr_untrim_c`` uses.

    Requires ``vptat25_v``, ``vptattgt_v`` and ``vtktgt_k`` in ``measurements``
    (the pre-trim 25 C reading, the binding-temperature reading, and the
    binding temperature in Kelvin, respectively -- see
    ``sim/temp-accuracy-mc/testbench/tb.json``). Returns ``{}`` if any are
    absent so callers can treat this as optional.
    """
    if not {"vptat25_v", "vptattgt_v", "vtktgt_k"} <= measurements.keys():
        return {}
    k25 = measurements["vptat25_v"] / _TRIM_REFERENCE_K
    if k25 == 0:
        return {}
    t_k = measurements["vtktgt_k"]
    curvature_c = measurements["vptattgt_v"] / k25 - t_k
    quant_c = (_TRIM_LSB_FRAC / 2.0) * t_k
    total_c = curvature_c + (quant_c if curvature_c >= 0 else -quant_c)
    return {"terr_trim_c": total_c, "k25_derived_mvk": k25 * 1e3}


DERIVE_HOOKS = {
    "temp_trim": derive_temp_trim,
}


def apply_derive_hook(tb: Testbench, results: list[PointResult]) -> list[str]:
    """Apply ``tb.mc["derive"]`` (a hook name in :data:`DERIVE_HOOKS`) in place.

    Returns the list of derived measurement names added (empty if no hook is
    configured), so callers can include them in the summary/report tables
    alongside the directly-measured ones.
    """
    hook_name = tb.mc.get("derive")
    if not hook_name:
        return []
    hook = DERIVE_HOOKS.get(hook_name)
    if hook is None:
        raise ManifestError(f"unknown mc.derive hook {hook_name!r}; known: {', '.join(DERIVE_HOOKS)}")
    added: set[str] = set()
    for result in results:
        if result.status != "ok":
            continue
        extra = hook(result.measurements)
        result.measurements.update(extra)
        added.update(extra)
    return sorted(added)


# ---------------------------------------------------------------------------
# summarization: mean / sigma / empirical yield / parametric 3-sigma bound
# ---------------------------------------------------------------------------


def summarize_binding_point(
    results: list[PointResult],
    measure_names: list[str],
    checks: dict[str, dict],
) -> dict[str, dict]:
    """Per-measurement distribution stats for one binding point's N samples.

    Reports both the **empirical yield** (fraction of the actual N samples
    landing inside the row's ratified [min, max]) and the **parametric [3σ]
    bound** (``mean ± 3*stdev`` compared against the same limits) --
    spec/target-spec.md section 2's own definition of a ``[3σ]`` claim is the
    latter, but N=500-2500 only resolves empirical yield to per-mille
    granularity, so the parametric bound is what actually stands in for "the
    3-sigma point of the fitted distribution" and the empirical figure is a
    sanity cross-check, not the headline number.
    """
    summary: dict[str, dict] = {}
    ok = [r for r in results if r.status == "ok"]
    for name in measure_names:
        values = [r.measurements[name] for r in ok if name in r.measurements]
        n = len(values)
        if n < 2:
            summary[name] = {"n": n}
            continue
        mean = statistics.fmean(values)
        stdev = statistics.stdev(values)
        spec = checks.get(name, {})
        low, high = spec.get("min"), spec.get("max")
        sigma3_lo = mean - 3.0 * stdev
        sigma3_hi = mean + 3.0 * stdev
        in_bounds = [
            v for v in values
            if (low is None or v >= low) and (high is None or v <= high)
        ]
        parametric_pass = (low is None or sigma3_lo >= low) and (high is None or sigma3_hi <= high)
        summary[name] = {
            "n": n,
            "mean": mean,
            "stdev": stdev,
            "min": min(values),
            "max": max(values),
            "sigma3_lo": sigma3_lo,
            "sigma3_hi": sigma3_hi,
            "spec_min": low,
            "spec_max": high,
            "empirical_yield": len(in_bounds) / n,
            "parametric_3sigma_pass": parametric_pass,
        }
    return summary


def summarize_mc(
    results: list[PointResult],
    measure_names: list[str],
    checks: dict[str, dict],
) -> dict[str, dict[str, dict]]:
    """``summarize_binding_point`` grouped by binding-point label."""
    by_label: dict[str, list[PointResult]] = {}
    for r in results:
        by_label.setdefault(r.point.label, []).append(r)
    return {
        label: summarize_binding_point(label_results, measure_names, checks)
        for label, label_results in by_label.items()
    }
