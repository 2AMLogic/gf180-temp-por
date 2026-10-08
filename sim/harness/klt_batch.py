"""Fail-closed ``klt sim`` batch execution backend for the sim harness (#331).

Why this exists. ``runner`` runs every deck as a local ``ngspice -b``
subprocess. On a shared dispatch worker a multi-corner grid must not run
locally: it has to be expressed as a ``klt sim`` request, which the batch
backend (``--backend batch``) submits to the Spot fleet. This module is the
seam that does that for decks the harness already composes, without changing
those decks, their measurements or their limits.

Public surface (the follow-up work for the other ``run_deck*`` callers should
reuse it instead of re-implementing request staging):

* :func:`resolve_backend` -- ``--backend`` / ``KLT_SIM_BACKEND`` -> ``"local"``
  or ``"batch"``. Local is the default; anything unrecognised is an error.
* :func:`translate_deck` -- a harness-composed ngspice deck -> a
  :class:`BatchUnit` (circuit body + analysis + measurements + corner values).
  Raises :class:`BatchIncompatible` for any construct it cannot express.
* :func:`run_units` -- stage, submit via ``klt sim --backend batch``, validate
  the report and copy each corner's raw log byte-for-byte to the unit's
  destination. Returns one :class:`UnitOutcome` per unit, in input order.

Invariants (all covered by ``sim/tests/test_klt_batch.py``):

* Once batch is selected nothing in this module ever runs ``ngspice``. A
  missing ``klt``, a refused submission, a malformed report, a timeout, a
  missing / duplicate corner, a non-``pass`` corner, a missing log or a
  missing measurement is an error outcome (or an exception), never an ``ok``.
* ``--backend batch`` is always passed explicitly. ``klt`` otherwise steps
  back to ``local`` for a single-unit run when the backend came from
  ``$KLT_SIM_BACKEND``; the report must also carry ``environment.remote``
  (the fleet job record), otherwise the run is rejected as "not executed on
  the fleet".
* Raw logs are copied (``shutil.copyfile``), never synthesised, and the caller
  parses the copy with the existing parsers.

Deck compatibility. ``klt sim`` owns the single ``.control`` block, the
``.lib``/``.temp`` cards and the analysis, so a composed deck is *taken
apart* and re-expressed rather than passed through. The recognised shape is
exactly what ``runner.compose_deck()`` and the control scripts emit:
``.param``/``.options``/``.include`` cards, ``deck_preamble()`` (design
include, ``.lib`` bundle, ``.temp``), one analysis (file-scope ``.tran`` or a
``.control`` ``tran``), file-scope ``.meas`` cards, and a ``.control`` block of
``set``/``let``/``print``/``meas``. ``let`` vectors used by ``meas`` commands
are inlined as ``par('...')`` expressions (a ``.control`` ``let`` is invisible
to a file-scope ``.meas`` card); this is a text transform whose numerical
equivalence to the local run is verified out-of-band, not here. Any other
control command (``write``, ``wrdata``, ``alter`` ...) is rejected.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .pdk import Pdk

KLT = "klt"
BACKEND_LOCAL = "local"
BACKEND_BATCH = "batch"
ENV_BACKEND = "KLT_SIM_BACKEND"
DEFAULT_TIMEOUT_S = 1800
#: Slack added to the fleet poll timeout when bounding the local ``klt``
#: process (Spot acquisition + boot + artifact download).
_CLIENT_SLACK_S = 600

_CAP_REFUSAL = "exceeds BATCH_MAX_CONCURRENT_INSTANCES"
#: Corner error diagnostics that, for callers whose local contract is "an
#: absent measurement is simply absent from the log" (the control scripts'
#: ``parse_bare_measurements`` consumers), do not by themselves make a corner
#: a failure. Every other error diagnostic (timeout, netlist, unknown,
#: batch_*, ...) always does.
ABSENT_MEASUREMENT_CODES = frozenset({"measurement", "no_such_vector"})


class BatchError(RuntimeError):
    """Base class: batch execution could not produce a trustworthy result."""


class KltMissing(BatchError):
    """``klt`` is not on PATH (environment problem; no local fallback)."""


class BatchIncompatible(BatchError):
    """A deck uses a construct the klt request cannot express (pre-submit)."""


class BatchSubmitError(BatchError):
    """klt could not be run, refused the request, timed out, or returned
    something that is not a valid report."""


class BatchResultError(BatchError):
    """The report is valid JSON but does not account for the requested units."""


# --------------------------------------------------------------------------
# backend selection
# --------------------------------------------------------------------------


def resolve_backend(cli_value: str | None = None, environ=None) -> str:
    """``--backend`` value (or ``None``/``"auto"``) -> ``"local"``/``"batch"``.

    Precedence: explicit CLI value, then ``$KLT_SIM_BACKEND``, then local.
    Library entry points (``runner.run_deck*``, ``run_grid``) never read the
    environment themselves -- only the CLI entry points call this -- so
    importing the harness on a ``KLT_SIM_BACKEND=batch`` host does not change
    any existing caller. ``klt``'s other backend names are refused rather than
    guessed at.
    """
    environ = os.environ if environ is None else environ
    value = cli_value if cli_value not in (None, "", "auto") else environ.get(ENV_BACKEND, "")
    value = (value or BACKEND_LOCAL).strip().lower()
    if value in (BACKEND_LOCAL, BACKEND_BATCH):
        return value
    raise BatchError(
        f"unsupported sim backend {value!r}: this harness supports "
        f"'{BACKEND_LOCAL}' and '{BACKEND_BATCH}' only"
    )


def add_backend_argument(parser) -> None:
    parser.add_argument(
        "--backend",
        choices=("auto", BACKEND_LOCAL, BACKEND_BATCH),
        default="auto",
        help="execution backend: 'local' runs ngspice here; 'batch' submits "
        "through `klt sim --backend batch` and never falls back to local; "
        f"'auto' (default) uses ${ENV_BACKEND} if set to local/batch, else local",
    )


def klt_version(klt: str = KLT) -> str:
    exe = shutil.which(klt)
    if not exe:
        raise KltMissing(f"'{klt}' not found on PATH; the batch backend needs klayout-tools")
    try:
        proc = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BatchSubmitError(f"could not run '{klt} --version': {exc}") from exc
    return (proc.stdout.strip() or proc.stderr.strip() or "unknown").splitlines()[0]


# --------------------------------------------------------------------------
# deck -> unit translation
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class BatchUnit:
    """One requested simulation: one deck at one corner/temperature/supply."""

    key: str                       # result key (deck name / corner id)
    log_path: Path                 # where the raw log must land
    body: str                      # circuit body (no control block / lib / temp)
    process: tuple[str, ...] | None  # ordered .lib sections (None: no process axis)
    temp_c: float
    supply: tuple[tuple[str, float], ...]  # lifted .param values, sorted by name
    analysis: tuple[str, str]      # (kind, args)
    measurements: tuple[tuple[str, str, str], ...]  # (name, "spice"|"expr", text)
    init: tuple[str, ...]          # .spiceinit lines
    timeout_s: int = DEFAULT_TIMEOUT_S

    @property
    def process_name(self) -> str | None:
        return None if self.process is None else "+".join(self.process)


_INCLUDE_RE = re.compile(r'^\.(?:include|inc)\s+(?:"([^"]+)"|\'([^\']+)\'|(\S+))\s*$', re.IGNORECASE)
_LIB_RE = re.compile(r'^\.lib\s+(?:"([^"]+)"|(\S+))\s+(\S+)\s*$', re.IGNORECASE)
_PARAM_RE = re.compile(r"^\.param\s+(\w+)\s*=\s*(\S+)\s*$", re.IGNORECASE)
_LET_RE = re.compile(r"^let\s+(\w+)\s*=\s*(.+)$", re.IGNORECASE)
_ANALYSIS_RE = re.compile(r"^\.?(tran|op|dc|ac)\b(.*)$", re.IGNORECASE)
_MEAS_RE = re.compile(r"^\.?meas(?:ure)?\s+(tran|ac|dc|sp|op)\s+(\w+)\b", re.IGNORECASE)


def _logical_lines(text: str) -> list[str]:
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("+") and out:
            out[-1] = out[-1] + " " + line[1:].strip()
        else:
            out.append(line)
    return out


def _inline(expr: str, lets: dict[str, str], wrap: Callable[[str], str]) -> str:
    """Replace every ``let`` vector name in ``expr`` with its expansion."""
    for name, expansion in lets.items():
        expr = re.sub(
            rf"(?<![\w.]){re.escape(name)}(?![\w.(])",
            lambda _m, e=expansion: wrap(e),
            expr,
        )
    return expr


def translate_deck(
    text: str,
    *,
    key: str,
    log_path: Path,
    pdk: Pdk,
    deck_dir: Path,
    lift_params: tuple[str, ...] = (),
    extra_init: tuple[str, ...] = (),
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> BatchUnit:
    """Take a harness-composed deck apart into a :class:`BatchUnit`.

    ``deck_dir`` is where relative ``.include`` targets resolve (the local
    run's working directory). ``lift_params`` names ``.param`` cards removed
    from the body and swept through klt's ``supply_v`` axis instead (lets
    PVT points that differ only in those values share one request).
    """
    body: list[str] = ["* gf180-temp-por batch body -- GENERATED by sim/harness/klt_batch.py"]
    sections: list[str] = []
    temp_c: float | None = None
    analysis: tuple[str, str] | None = None
    init: list[str] = []
    lets: dict[str, str] = {}          # name -> fully expanded expression
    printed: list[str] = []
    meas: list[tuple[str, str, str]] = []
    lifted: dict[str, float] = {}
    in_control = False

    def add_meas(name: str, form: str, text_: str) -> None:
        if any(m[0] == name for m in meas):
            raise BatchIncompatible(f"{key}: duplicate measurement name {name!r}")
        meas.append((name, form, text_))

    def set_analysis(kind: str, args: str) -> None:
        nonlocal analysis
        if analysis is not None:
            raise BatchIncompatible(
                f"{key}: more than one analysis ({analysis[0]!r} and {kind!r}); "
                "klt sim runs exactly one per corner"
            )
        analysis = (kind.lower(), args.strip())

    for line in _logical_lines(text):
        stripped = line.strip()
        if not stripped or stripped.startswith("*"):
            continue
        low = stripped.lower()

        if in_control:
            if low == ".endc":
                in_control = False
            elif low.startswith("set "):
                init.append(stripped)
            elif _ANALYSIS_RE.match(stripped) and not low.startswith("."):
                m = _ANALYSIS_RE.match(stripped)
                set_analysis(m.group(1), m.group(2))
            elif _LET_RE.match(stripped):
                m = _LET_RE.match(stripped)
                lets[m.group(1)] = _inline(m.group(2).strip(), lets, lambda e: f"({e})")
            elif low.startswith("print "):
                for name in stripped.split()[1:]:
                    if name not in lets:
                        raise BatchIncompatible(
                            f"{key}: `print {name}` of something that is not a `let` vector"
                        )
                    printed.append(name)
            elif low.startswith("meas"):
                m = _MEAS_RE.match(stripped)
                if not m or m.group(1).lower() == "op":
                    raise BatchIncompatible(f"{key}: unsupported measurement command: {stripped}")
                head = stripped.split(None, 3)
                tail = head[3] if len(head) > 3 else ""
                tail = _inline(tail, lets, lambda e: f"par('{e}')")
                add_meas(m.group(2), "spice", f".meas {m.group(1).lower()} {m.group(2)} {tail}".rstrip())
            else:
                raise BatchIncompatible(
                    f"{key}: control command not expressible in a klt sim request: {stripped}"
                )
            continue

        if low == ".control":
            in_control = True
        elif low == ".end":
            continue
        elif low == ".endc":
            raise BatchIncompatible(f"{key}: .endc without .control")
        elif _MEAS_RE.match(stripped) and low.startswith(".meas"):
            m = _MEAS_RE.match(stripped)
            if m.group(1).lower() == "op":
                raise BatchIncompatible(f"{key}: `.meas op` is not supported by ngspice/klt")
            add_meas(m.group(2), "spice", stripped)
        elif low.startswith((".tran", ".op", ".dc", ".ac")) and _ANALYSIS_RE.match(stripped):
            m = _ANALYSIS_RE.match(stripped)
            set_analysis(m.group(1), m.group(2))
        elif low.startswith(".temp"):
            if temp_c is not None:
                raise BatchIncompatible(f"{key}: more than one .temp card")
            try:
                temp_c = float(stripped.split()[1])
            except (IndexError, ValueError) as exc:
                raise BatchIncompatible(f"{key}: unparseable .temp card: {stripped}") from exc
        elif low.startswith(".lib"):
            m = _LIB_RE.match(stripped)
            if not m:
                raise BatchIncompatible(f"{key}: unparseable .lib card: {stripped}")
            lib = Path(m.group(1) or m.group(2))
            if lib != pdk.model_lib:
                raise BatchIncompatible(
                    f"{key}: .lib names {lib}, which is not the PDK model library "
                    f"{pdk.model_lib}; only that library is resolvable on the fleet"
                )
            sections.append(m.group(3))
        elif low.startswith((".include", ".inc")):
            m = _INCLUDE_RE.match(stripped)
            if not m:
                raise BatchIncompatible(f"{key}: unparseable include: {stripped}")
            target = Path(m.group(1) or m.group(2) or m.group(3))
            if "$" in str(target):
                raise BatchIncompatible(f"{key}: environment-variable include not staged: {stripped}")
            resolved = target if target.is_absolute() else (deck_dir / target)
            if resolved == pdk.design_include:
                if not resolved.is_file():
                    raise BatchIncompatible(f"{key}: PDK design include missing: {resolved}")
                content = resolved.read_text()
                digest = hashlib.sha256(content.encode()).hexdigest()[:16]
                body.append(f"* ---- design.ngspice inlined from the PDK (sha256 {digest}...) ----")
                body.append(content.rstrip("\n"))
                body.append("* ---- end design.ngspice ----")
                continue
            if not resolved.is_file():
                raise BatchIncompatible(
                    f"{key}: include does not resolve to a file on this host: {stripped} "
                    f"(looked for {resolved})"
                )
            try:
                resolved.resolve().relative_to(pdk.path.resolve())
            except ValueError:
                pass
            else:
                raise BatchIncompatible(
                    f"{key}: include under the PDK tree other than design.ngspice "
                    f"is not staged: {resolved}"
                )
            body.append(f'.include "{resolved.resolve()}"')
        else:
            pm = _PARAM_RE.match(stripped)
            if pm and pm.group(1) in lift_params:
                name = pm.group(1)
                if name in lifted:
                    raise BatchIncompatible(f"{key}: .param {name} defined twice")
                try:
                    lifted[name] = float(pm.group(2))
                except ValueError as exc:
                    raise BatchIncompatible(
                        f"{key}: lifted .param {name} is not a plain number: {stripped}"
                    ) from exc
                continue
            body.append(stripped)

    if in_control:
        raise BatchIncompatible(f"{key}: .control block never closed")
    if analysis is None:
        raise BatchIncompatible(f"{key}: no analysis found (need exactly one)")
    if temp_c is None:
        raise BatchIncompatible(f"{key}: no .temp card; the temperature axis would be undefined")
    for name in printed:
        add_meas(name, "expr", lets[name])
    if not meas:
        raise BatchIncompatible(f"{key}: no measurements; nothing to return from the fleet")
    for name in lift_params:
        lifted.setdefault(name, math.nan)
    missing_lift = [n for n, v in lifted.items() if math.isnan(v)]
    if missing_lift:
        raise BatchIncompatible(f"{key}: lifted .param {', '.join(missing_lift)} not found")

    return BatchUnit(
        key=key,
        log_path=Path(log_path),
        body="\n".join(body) + "\n",
        process=tuple(sections) if sections else None,
        temp_c=temp_c,
        supply=tuple(sorted(lifted.items())),
        analysis=analysis,
        measurements=tuple(meas),
        init=tuple(dict.fromkeys([*extra_init, *init])),
        timeout_s=timeout_s,
    )


def compat_init_lines(home_spiceinit: Path | None = None) -> tuple[str, ...]:
    """The ``.spiceinit`` lines the local runner writes (``set num_threads=1``
    plus the host's own carried-forward settings, e.g. ``set wnflag=1``), as
    klt ``options.ngspice_init`` entries."""
    from .runner import spiceinit_text

    return tuple(
        ln.strip()
        for ln in spiceinit_text(home_spiceinit).splitlines()
        if ln.strip() and not ln.lstrip().startswith("*")
    )


# --------------------------------------------------------------------------
# request staging
# --------------------------------------------------------------------------


@dataclass
class BatchConfig:
    pdk: Pdk
    stage_root: Path
    klt: str = KLT
    #: Extra seconds-of-grace bounds; ``poll_timeout_s=None`` lets klt derive it.
    poll_timeout_s: int | None = None
    client_slack_s: float = _CLIENT_SLACK_S
    max_cap_wait_s: float = 4 * 3600
    sleep: Callable[[float], None] = time.sleep
    log: Callable[[str], None] = print
    #: Where to also copy request.json / report.json (evidence), if anywhere.
    evidence_dir: Path | None = None


@dataclass
class UnitOutcome:
    unit: BatchUnit
    status: str                       # "ok" | "error"
    message: str = ""
    log_path: Path | None = None      # the byte-exact copy, when one exists
    values: dict[str, float | None] = field(default_factory=dict)
    absent: list[str] = field(default_factory=list)
    seconds: float = 0.0
    job_id: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def text(self) -> str:
        return self.log_path.read_text(errors="replace") if self.log_path else ""


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._+-]", "_", name)


def _unit_group_key(u: BatchUnit) -> tuple:
    return (u.body, u.temp_c, u.analysis, u.measurements, u.init, u.timeout_s,
            tuple(n for n, _ in u.supply), u.process is None)


def _same(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)


def _build_request(units: list[BatchUnit], pdk: Pdk, cfg: BatchConfig) -> dict:
    first = units[0]
    process_names: list[str] = []
    bundles: dict[str, tuple[str, ...]] = {}
    supply_rows: list[tuple[float, ...]] = []
    for u in units:
        if u.process is not None and u.process_name not in bundles:
            bundles[u.process_name] = u.process
            process_names.append(u.process_name)
        row = tuple(v for _, v in u.supply)
        if not any(len(row) == len(r) and all(_same(a, b) for a, b in zip(row, r)) for r in supply_rows):
            supply_rows.append(row)

    corners: dict = {"temperature_c": [first.temp_c]}
    if process_names:
        corners["process"] = [{"name": n, "sections": list(bundles[n])} for n in process_names]
    supply_keys = [n for n, _ in first.supply]
    if supply_keys:
        corners["supply_v"] = {k: [r[i] for r in supply_rows] for i, k in enumerate(supply_keys)}

    # Sparse grids: exclude every (process, supply) combination not requested.
    wanted = {(u.process_name, tuple(v for _, v in u.supply)) for u in units}
    exclude = []
    for n in process_names or [None]:
        for row in supply_rows:
            if not any(n == wn and len(row) == len(wr) and all(_same(a, b) for a, b in zip(row, wr))
                       for wn, wr in wanted):
                spec: dict = {}
                if n is not None:
                    spec["process"] = n
                if supply_keys:
                    spec["supply_v"] = dict(zip(supply_keys, row))
                exclude.append(spec)

    request: dict = {
        "netlist": "body.spice",
        "engine": "ngspice",
        "backend": BACKEND_BATCH,
        "netlist_source": "schematic",
        "corners": corners,
        "analysis": {"kind": first.analysis[0], "args": first.analysis[1]},
        "measurements": [
            {"name": n, form: txt} for n, form, txt in first.measurements
        ],
        "options": {
            "timeout_s": first.timeout_s,
            "keep_artifacts": True,
            "ngspice_init": list(first.init),
        },
    }
    if process_names:
        request["models"] = {
            "pdk": pdk.variant,
            "lib": str(pdk.model_lib.relative_to(pdk.path)),
        }
    if exclude:
        request["exclude"] = exclude
    if cfg.poll_timeout_s is not None:
        request["batch"] = {"poll_timeout_s": cfg.poll_timeout_s}
    return request


def _stage(units: list[BatchUnit], pdk: Pdk, cfg: BatchConfig, name: str) -> tuple[Path, dict]:
    stage = cfg.stage_root / name
    stage.mkdir(parents=True, exist_ok=True)
    lines = []
    for line in units[0].body.splitlines():
        m = _INCLUDE_RE.match(line.strip())
        if m and m.group(1) and Path(m.group(1)).is_absolute():
            rel = os.path.relpath(m.group(1), stage.resolve())
            line = f'.include "{rel}"'
        lines.append(line)
    (stage / "body.spice").write_text("\n".join(lines) + "\n")
    request = _build_request(units, pdk, cfg)
    req_path = stage / "request.json"
    req_path.write_text(json.dumps(request, indent=2) + "\n")
    return req_path, request


# --------------------------------------------------------------------------
# invocation
# --------------------------------------------------------------------------


def invoke_klt(req: Path, outdir: Path, cfg: BatchConfig, timeout_s: float) -> dict:
    """Run ``klt sim`` on ``req`` with the batch backend forced; return the
    parsed report. Re-submits only on the fleet concurrency-cap refusal,
    within ``cfg.max_cap_wait_s``; every other failure raises."""
    exe = shutil.which(cfg.klt)
    if not exe:
        raise KltMissing(
            f"'{cfg.klt}' not found on PATH; batch mode never falls back to a local ngspice run"
        )
    cmd = [exe, "sim", str(req), "-o", str(outdir), "--format", "json", "--backend", BACKEND_BATCH]
    deadline = time.monotonic() + cfg.max_cap_wait_s
    delay = 60.0
    while True:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        except subprocess.TimeoutExpired as exc:
            raise BatchSubmitError(
                f"klt sim for {req.parent.name} did not finish within {timeout_s:.0f}s "
                "(the fleet job may still be running)"
            ) from exc
        except OSError as exc:
            raise BatchSubmitError(f"could not execute klt: {exc}") from exc
        try:
            report = json.loads(proc.stdout) if proc.stdout.strip() else None
        except json.JSONDecodeError:
            report = None
        if isinstance(report, dict) and "error" not in report and "corners" in report:
            return report
        message = ""
        if isinstance(report, dict) and isinstance(report.get("error"), dict):
            message = str(report["error"].get("message", ""))
        message = (message + " " + proc.stderr).strip()
        if _CAP_REFUSAL in message and time.monotonic() + delay < deadline:
            wait = delay * random.uniform(0.5, 1.0)
            cfg.log(f"  fleet at its concurrency cap; re-submitting {req.parent.name} in {wait:.0f}s")
            cfg.sleep(wait)
            delay = min(delay * 2, 600.0)
            continue
        what = "refused or failed"
        if report is None and proc.returncode == 0:
            what = ("returned no JSON report" if not proc.stdout.strip()
                    else "returned output that is not a JSON report")
        raise BatchSubmitError(
            f"klt sim {what} for {req.parent.name} (exit {proc.returncode}): "
            f"{message[:800] or proc.stdout[:400] or 'no output'}"
        )


def _match(report_corners: list[dict], unit: BatchUnit) -> list[dict]:
    hits = []
    for c in report_corners:
        if unit.process_name is not None and c.get("process") != unit.process_name:
            continue
        t = c.get("temperature_c")
        if not isinstance(t, (int, float)) or not _same(float(t), unit.temp_c):
            continue
        sv = c.get("supply_v") or {}
        if any(k not in sv or not _same(float(sv[k]), v) for k, v in unit.supply):
            continue
        hits.append(c)
    return hits


def _collect_group(
    units: list[BatchUnit], report: dict, tolerate_absent: bool, stage: Path
) -> list[UnitOutcome]:
    remote = (report.get("environment") or {}).get("remote")
    if not isinstance(remote, dict) or not remote.get("job_id"):
        raise BatchResultError(
            "report has no environment.remote.job_id: this run was not executed on the "
            "batch fleet, so it is rejected (no local result is accepted in batch mode)"
        )
    job_id = str(remote["job_id"])
    corners = report.get("corners")
    if not isinstance(corners, list):
        raise BatchResultError("report 'corners' is not a list")
    if not all(isinstance(c, dict) for c in corners):
        raise BatchResultError("report contains malformed corner entries")

    outcomes: list[UnitOutcome] = []
    for u in units:
        hits = _match(corners, u)
        if not hits:
            outcomes.append(UnitOutcome(u, "error", "no result returned for this unit "
                                        f"(process={u.process_name}, temp={u.temp_c:g}, "
                                        f"supply={dict(u.supply)})", job_id=job_id))
            continue
        if len(hits) > 1:
            outcomes.append(UnitOutcome(u, "error", f"{len(hits)} results returned for this unit "
                                        "(expected exactly one)", job_id=job_id))
            continue
        outcomes.append(_judge(u, hits[0], tolerate_absent, job_id))
    unmatched = [c for c in corners if not any(any(c is h for h in _match(corners, u)) for u in units)]
    if unmatched:
        # Extra corners nobody asked for: the report does not match the request.
        raise BatchResultError(
            f"report contains {len(unmatched)} corner(s) that match no requested unit "
            f"(e.g. {unmatched[0].get('corner_id')!r})"
        )
    return outcomes


def _judge(u: BatchUnit, c: dict, tolerate_absent: bool, job_id: str) -> UnitOutcome:
    seconds = float(c.get("runtime_s") or 0.0)
    log = (c.get("artifacts") or {}).get("log")
    diags = [d for d in (c.get("diagnostics") or []) if isinstance(d, dict)]
    errors = [d for d in diags if d.get("severity") == "error"]
    codes = sorted({str(d.get("code", "?")) for d in errors})
    detail = "; ".join(f"{d.get('code')}: {d.get('message', '')}".strip() for d in errors)[:600]
    values = {m.get("name"): m.get("value") for m in (c.get("measurements") or []) if isinstance(m, dict)}
    wanted = [n for n, _, _ in u.measurements]
    absent = [n for n in wanted if values.get(n) is None]
    status = c.get("status")

    def fail(msg: str) -> UnitOutcome:
        return UnitOutcome(u, "error", msg, values=values, absent=absent, seconds=seconds, job_id=job_id)

    if not log or not Path(log).is_file():
        return fail(f"klt returned no raw log for this unit (status={status!r}"
                    f"{', ' + detail if detail else ''})")

    tolerated = (
        tolerate_absent
        and status == "error"
        and errors
        and all(d.get("code") in ABSENT_MEASUREMENT_CODES for d in errors)
    )
    if status != "pass" and not tolerated:
        return fail(f"klt corner status {status!r}" + (f" [{', '.join(codes)}]" if codes else "")
                    + (f": {detail}" if detail else "")
                    + (f" (measurement(s) without a value: {', '.join(absent)})" if absent else ""))
    if absent and not tolerate_absent:
        return fail(f"requested measurement(s) missing from the result: {', '.join(absent)}")

    u.log_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(log, u.log_path)     # byte-for-byte; never rewritten
    return UnitOutcome(u, "ok", values=values, absent=absent, log_path=u.log_path,
                       seconds=seconds, job_id=job_id)


def run_units(
    units: list[BatchUnit],
    cfg: BatchConfig,
    *,
    tolerate_absent: bool = False,
    jobs: int = 1,
    on_outcome: Callable[[UnitOutcome], None] | None = None,
) -> list[UnitOutcome]:
    """Submit ``units`` through ``klt sim --backend batch``; one outcome each,
    in input order.

    Units that share body/analysis/measurements/temperature are submitted as
    one request (a process x supply matrix, sparse cells excluded); every
    other unit is its own request. ``tolerate_absent`` keeps a corner whose
    only error diagnostics are an absent ``.meas`` (see
    :data:`ABSENT_MEASUREMENT_CODES`) as ``ok`` with the gap listed in
    ``absent`` -- the contract of the control scripts, where an absent
    measurement means "never happened". Request-level failures become error
    outcomes for that request's units; a missing ``klt`` raises
    :class:`KltMissing`.
    """
    keys = [u.key for u in units]
    if len(set(keys)) != len(keys):
        dup = sorted({k for k in keys if keys.count(k) > 1})
        raise BatchIncompatible(f"duplicate unit keys in one submission: {', '.join(dup[:5])}")
    if not shutil.which(cfg.klt):
        raise KltMissing(
            f"'{cfg.klt}' not found on PATH; batch mode never falls back to a local ngspice run"
        )

    groups: dict[tuple, list[int]] = {}
    for i, u in enumerate(units):
        groups.setdefault(_unit_group_key(u), []).append(i)
    results: list[UnitOutcome | None] = [None] * len(units)

    def do_group(indices: list[int]) -> None:
        members = [units[i] for i in indices]
        name = _safe(members[0].key) + (f"+{len(members) - 1}" if len(members) > 1 else "")
        try:
            req_path, request = _stage(members, cfg.pdk, cfg, name)
            n_corners = len(members) + len(request.get("exclude", []))
            poll = cfg.poll_timeout_s or (members[0].timeout_s * n_corners + 1800 + 120)
            report = invoke_klt(req_path, req_path.parent / "klt", cfg, poll + cfg.client_slack_s)
            (req_path.parent / "report.json").write_text(
                json.dumps(report, indent=1, sort_keys=True) + "\n")
            if cfg.evidence_dir is not None:
                cfg.evidence_dir.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(req_path, cfg.evidence_dir / f"klt-{name}.request.json")
                shutil.copyfile(req_path.parent / "report.json",
                                cfg.evidence_dir / f"klt-{name}.report.json")
            outs = _collect_group(members, report, tolerate_absent, req_path.parent)
        except KltMissing:
            raise
        except BatchError as exc:
            outs = [UnitOutcome(u, "error", str(exc)) for u in members]
        for i, out in zip(indices, outs):
            results[i] = out
            if on_outcome is not None:
                on_outcome(out)

    batches = list(groups.values())
    if jobs <= 1 or len(batches) == 1:
        for b in batches:
            do_group(b)
    else:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            for fut in [pool.submit(do_group, b) for b in batches]:
                fut.result()
    return [r for r in results if r is not None]


def run_single(unit: BatchUnit, cfg: BatchConfig, *, tolerate_absent: bool) -> UnitOutcome:
    """One unit; raises :class:`BatchError` unless it came back ``ok``."""
    (out,) = run_units([unit], cfg, tolerate_absent=tolerate_absent)
    if not out.ok:
        raise BatchResultError(f"{unit.key}: {out.message}")
    return out
