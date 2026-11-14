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
* :func:`stage_requests` -- group units and write one ``klt sim`` request
  per group, submitting nothing (``--emit-request``, #496). The grouping and
  staging rules live here only; :func:`run_units` uses the same two.
* :func:`run_units` -- stage, submit via ``klt sim --backend batch``, validate
  the report and copy each corner's raw log byte-for-byte to the unit's
  destination. Returns one :class:`UnitOutcome` per unit, in input order.
* :func:`measurement_specs` -- a testbench manifest's ``checks`` -> the
  per-measurement ``limits`` / ``spec_row`` klt grades each corner against.

Invariants (all covered by ``sim/tests/test_klt_batch.py``):

* Once batch is selected nothing in this module ever runs ``ngspice``. A
  missing ``klt``, a refused submission, a malformed report, a timeout, a
  missing / duplicate corner, a non-``pass`` corner, a missing log or a
  missing measurement is an error outcome (or an exception), never an ``ok``.
  So is a corner whose analysis aborted or that produced no measurement value
  at all, even where an absent measurement is otherwise tolerated.
* A corner must agree with itself to be ``ok``: an error-level diagnostic
  under a ``pass`` label, a requested measurement value that is not a finite
  number (string, boolean, NaN, infinity), or a malformed ``measurements`` /
  ``diagnostics`` / ``artifacts`` / ``runtime_s`` field is an error outcome,
  decided before the raw log is copied.
* A report from a fleet runner whose ``klt`` is not the client's build
  (``environment.remote.runner_compatibility`` other than ``match``) is
  rejected, and the rest of that run is refused without being submitted.
* So is a report whose fleet runner read a different PDK model library than
  the one this host resolved (``environment.remote.runner_models_lib_sha256``
  against the SHA-256 of ``cfg.pdk.model_lib``, or klt's own
  ``models_lib_comparison: mismatch``): on batch the models come from the
  runner's image, so an accepted result must have been simulated against the
  build the record is about to name. A report that carries no usable runner
  hash is accepted and recorded as *not comparable* -- never as a match.
  What the runner did read is carried out on :attr:`BatchConfig.provenance`
  for the evidence record (:func:`batch_provenance`).
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

import argparse
import atexit
import hashlib
import json
import math
import os
import random
import re
import shutil
import subprocess
import tempfile
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

#: The value a lifted ``.param`` is declared with in the staged body. klt's
#: parameter axis rewrites it per corner (``alterparam`` + ``reset``), so this
#: default is never simulated -- but the declaration must exist, because klt
#: refuses a ``corners.params`` name no top-level ``.param`` declares. Zero
#: rather than the nominal on purpose: if the rewrite ever failed to land, a
#: corner would simulate a 0 V supply and fail loudly, instead of silently
#: returning the nominal point three times (#464).
_LIFTED_DEFAULT = "0"

_CAP_REFUSAL = "exceeds BATCH_MAX_CONCURRENT_INSTANCES"
#: Corner error diagnostics that, for callers whose local contract is "an
#: absent measurement is simply absent from the log" (the control scripts'
#: ``parse_bare_measurements`` consumers), do not by themselves make a corner
#: a failure. Every other error diagnostic (timeout, netlist, unknown,
#: batch_*, ...) always does.
ABSENT_MEASUREMENT_CODES = frozenset({"measurement", "no_such_vector"})
#: ngspice's own marker for an analysis that stopped before completing.
_ABORTED = "simulation(s) aborted"
#: A SHA-256 digest as klt reports it (lowercase hex).
_SHA256_RE = re.compile(r"\A[0-9a-f]{64}\Z")
#: The ratified spec row a ``tb.json`` ``checks`` entry substantiates, read
#: from the *leading* reference of its free-text ``description`` (there is no
#: structured field for it). Deliberately narrower than "mentions a row
#: anywhere": across this repo's manifests a check that merely cites a row in
#: prose ("at the fast end of spec/target-spec.md#por-ramp-rate", "(spec/
#: target-spec.md#supply-voltage)") is *not* evidence for it, and tagging it
#: as such would claim a bound it does not measure. A check that is evidence
#: names its row first -- which is what every one of the rows this repo
#: actually cites does.
_SPEC_ROW_RE = re.compile(r"\A`?spec/target-spec\.md#([a-z0-9-]+)")
#: A ratified row id as ``spec/target-spec.md`` anchors it. Same anchors
#: ``signoff/inventories.py:spec_row_ids`` audits, read here from text rather
#: than a path: the sim harness is importable on its own and must not depend
#: on the signoff package.
_SPEC_ANCHOR_RE = re.compile(r'<a id="([a-z0-9-]+)"></a>`')


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


class BatchRunFatal(BatchResultError):
    """A rejection that condemns the whole run, not just one report: every
    later request would reach the same fleet runner, so it is refused without
    being submitted (:attr:`BatchConfig.halted`)."""


class BatchRunnerMismatch(BatchRunFatal):
    """The fleet runner's ``klt`` is not the submitting client's build, so the
    request may have been run with options ignored (or not run at all). Fatal
    for the whole run: later submissions would hit the same runner."""


class BatchPdkMismatch(BatchRunFatal):
    """The fleet runner read a different PDK model library than the one this
    host resolved, so a record naming the local install would name a build the
    simulation never used. Fatal for the whole run: the runner's image does
    not change between requests."""


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
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--klt",
        default=KLT,
        metavar="EXE",
        help="klt executable used for batch submission (default: %(default)s on PATH). "
        "The fleet refuses a request whose runner klt differs from the client's, "
        "so point this at a client matching the runner when they differ",
    )
    group.add_argument(
        "--klt-pin",
        action=_PinAction,
        default=None,
        metavar="VERSION",
        help="submit with klayout-tools==VERSION from a throwaway `uvx` environment "
        "(for when the fleet runner's klt differs from the host's); the host's klt "
        "is not touched. Mutually exclusive with --klt",
    )


_PIN_RE = re.compile(r"^[0-9]+(\.[0-9]+)*([.+-]?[0-9A-Za-z.]+)?$")


def pinned_klt(version: str, directory: Path | None = None) -> str:
    """Path of a wrapper that runs ``klt`` at exactly ``version``.

    The wrapper is ``uvx --from klayout-tools==<version> klt``: a throwaway
    environment resolved by uv's cache, so the host's installed ``klt`` is
    neither read nor modified. The path is usable anywhere a ``--klt`` value is.
    """
    if not _PIN_RE.match(version):
        raise BatchError(f"--klt-pin {version!r} is not a plain klayout-tools version (e.g. 0.5.0)")
    base = Path(directory) if directory else Path(tempfile.mkdtemp(prefix="klt-pin-"))
    if directory is None:
        atexit.register(shutil.rmtree, base, ignore_errors=True)
    wrapper = base / "klt"
    wrapper.write_text(
        f'#!/bin/sh\nexec uvx --from "klayout-tools=={version}" klt "$@"\n'
    )
    wrapper.chmod(0o755)
    return str(wrapper)


class _PinAction(argparse.Action):
    """``--klt-pin VER``: set ``klt`` to a pinned-version wrapper (see
    :func:`pinned_klt`). Exclusion with ``--klt`` is enforced by the argparse
    group in :func:`add_backend_argument`, so it holds in either order."""

    def __call__(self, parser, namespace, values, option_string=None):
        try:
            namespace.klt = pinned_klt(values)
        except BatchError as exc:
            parser.error(str(exc))
        namespace.klt_pin = values


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
class MeasurementSpec:
    """One measurement's ratified pass/fail envelope, as ``klt sim`` grades it.

    ``klt`` reads these as ``measurements[].limits`` (``min`` and ``max``
    each independently optional -- a measurement with no ``limits`` is
    reported but can never fail) and grades every corner against them,
    returning a per-corner ``status`` plus a signed ``margin`` and, in the
    rollup, the binding corner (``worst_case.corner_id``) and the true
    ``min``/``max`` extremes. ``spec_row`` is the ratified
    ``spec/target-spec.md`` row id this measurement is evidence for, carried
    as ``measurements[].spec_row`` for klt's own row-coverage derivation;
    empty for a measurement that is not a spec row of its own (a guard or
    integrity check), which klt accepts and ignores.

    Frozen and hashable so a unit's specs can be part of
    :func:`_unit_group_key` -- two units graded against different bounds must
    not share a request, because the request carries one ``measurements[]``
    block for the whole group.
    """

    #: The name the *request's* measurement carries, not necessarily the
    #: manifest's own check key -- see :func:`measurement_specs`.
    name: str
    minimum: float | None = None
    maximum: float | None = None
    spec_row: str = ""

    def limits(self) -> dict:
        """``measurements[].limits``, with an undeclared bound simply absent
        (never a ``null``, which klt would have to interpret)."""
        out: dict = {}
        if self.minimum is not None:
            out["min"] = self.minimum
        if self.maximum is not None:
            out["max"] = self.maximum
        return out


def spec_row_ids(spec_text: str) -> frozenset[str]:
    """Every row id ``spec/target-spec.md``'s text ratifies (its ``<a id=>``
    anchors), for cross-checking what a testbench check claims to be evidence
    for."""
    return frozenset(_SPEC_ANCHOR_RE.findall(spec_text))


def spec_row_of(description: str) -> str:
    """The ratified row id a ``checks`` entry's ``description`` declares, or
    ``""``. See :data:`_SPEC_ROW_RE` for why only a leading reference counts.
    """
    m = _SPEC_ROW_RE.match(description.strip())
    return m.group(1) if m else ""


def measurement_specs(
    checks: dict[str, dict],
    *,
    request_names: dict[str, str],
    known_rows: frozenset[str] | None = None,
) -> tuple[MeasurementSpec, ...]:
    """A testbench manifest's ``checks`` -> the specs klt should grade against.

    One :class:`MeasurementSpec` per entry that declares a ``min`` and/or a
    ``max``, sorted by request-side name. An entry declaring neither (a
    grid-level ``max_spread_pct``/``min_spread_pct`` check) contributes
    nothing: there is no bound for klt to grade a single corner against, and
    an empty ``limits`` would say "never fails" in a way the manifest does
    not.

    ``request_names`` maps a check's name to the name the request's own
    measurement carries, and *selects*: a check with no entry there is not a
    request measurement at all -- a Python-derived quantity such as the Monte
    Carlo benches' ``terr_trim_c``, computed from other measurements after
    the run -- so klt has nothing to attach a bound to and it is skipped.

    ``known_rows`` (from :func:`spec_row_ids`) turns a row id no longer in
    the ratified spec into an error rather than a ``spec_row`` naming a row
    that does not exist. ``None`` skips that cross-check.
    """
    specs: list[MeasurementSpec] = []
    for name, spec in checks.items():
        request_name = request_names.get(name)
        if request_name is None:
            continue
        low, high = spec.get("min"), spec.get("max")
        if low is None and high is None:
            continue
        row = spec_row_of(spec.get("description", ""))
        if row and known_rows is not None and row not in known_rows:
            raise BatchIncompatible(
                f"check {name!r} names spec row {row!r}, which spec/target-spec.md "
                "does not ratify; a request must not claim a row that does not exist"
            )
        specs.append(MeasurementSpec(
            name=request_name,
            minimum=None if low is None else float(low),
            maximum=None if high is None else float(high),
            spec_row=row,
        ))
    return tuple(sorted(specs, key=lambda s: s.name))


@dataclass(frozen=True)
class BatchUnit:
    """One requested simulation: one deck at one corner/temperature/supply."""

    key: str                       # result key (deck name / corner id)
    log_path: Path                 # where the raw log must land
    body: str                      # circuit body (no control block / lib / temp)
    process: tuple[str, ...] | None  # ordered .lib sections (None: no process axis)
    temp_c: float
    #: Lifted per-corner ``.param`` values, sorted by name. These ride klt's
    #: ``corners.params`` axis (``alterparam`` + ``reset``), NOT ``corners.supply_v``:
    #: ``supply_v`` is an ``alter`` on a voltage *source*, so a ``.param`` name on
    #: it addresses nothing and klt refuses the request (#464).
    lifted: tuple[tuple[str, float], ...]
    analysis: tuple[str, str]      # (kind, args)
    measurements: tuple[tuple[str, str, str], ...]  # (name, "spice"|"expr", text)
    init: tuple[str, ...]          # .spiceinit lines
    timeout_s: int = DEFAULT_TIMEOUT_S
    #: Several solves of one corner (route (a), #440): ordered
    #: ``(step name, (kind, args), step measurements)`` rows sent as klt's
    #: ``analysis_steps[]``. Empty for the ordinary single-analysis unit. In a
    #: stepped unit ``measurements`` are the *derived* top-level entries
    #: (``expr`` over ``<step>.<measurement>``), named as the deck's own
    #: ``print``ed vectors, so callers read the same names either way.
    steps: tuple[tuple[str, tuple[str, str], tuple[tuple[str, str, str], ...]], ...] = ()
    #: Ratified pass/fail envelopes for this unit's measurements, sorted by
    #: name (#496): what ``measurements[].limits`` / ``.spec_row`` carry, so
    #: the fleet grades each corner against the spec instead of returning
    #: ungraded numbers. Empty by default -- a caller that attaches none gets
    #: byte-for-byte the request it got before.
    specs: tuple[MeasurementSpec, ...] = ()

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


_BRACE_RE = re.compile(r"\{([^{}]*)\}")


def _resolve_analysis_args(
    args: str, params: dict[str, str], lift_params: tuple[str, ...], key: str
) -> str:
    """Substitute ``{name}`` tokens in an analysis line with the deck's own
    plain-number ``.param`` value.

    ``klt sim`` runs the analysis as a ``.control`` command, and ngspice does
    not expand ``.param`` braces in control-mode commands: ``tran 2e-06
    {stop_s}`` there is a TSTOP of zero and the analysis aborts (observed on
    the fleet, #331). A local ``ngspice -b`` run of the same deck evaluates the
    file-scope ``.tran`` card with the parameter, so substituting the deck's
    own literal (text, unrounded) keeps the analysis identical. Anything that
    is not a bare reference to such a parameter -- an expression, an unknown
    name, a lifted per-corner parameter -- is refused before submission.
    """
    def sub(m: re.Match) -> str:
        name = m.group(1).strip()
        if name in lift_params:
            raise BatchIncompatible(
                f"{key}: analysis uses lifted per-corner parameter {{{name}}}; "
                "a klt request has one analysis line for every corner"
            )
        if name not in params:
            raise BatchIncompatible(
                f"{key}: analysis argument {{{m.group(1)}}} is not a plain-number .param "
                "of this deck; klt runs the analysis as a control command, where "
                ".param braces are not expanded"
            )
        return params[name]

    out = _BRACE_RE.sub(sub, args)
    if "{" in out or "}" in out:
        raise BatchIncompatible(f"{key}: unbalanced or nested braces in analysis: {args}")
    return out


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
    specs: tuple[MeasurementSpec, ...] = (),
) -> BatchUnit:
    """Take a harness-composed deck apart into a :class:`BatchUnit`.

    ``deck_dir`` is where relative ``.include`` targets resolve (the local
    run's working directory). ``lift_params`` names ``.param`` cards whose
    value is swept through klt's ``corners.params`` axis instead of being
    fixed in the body (lets PVT points that differ only in those values share
    one request). The card itself stays, rewritten to the
    :data:`_LIFTED_DEFAULT` sentinel: klt's parameter axis is an
    ``alterparam``, which refuses a name no top-level ``.param`` declares.

    ``specs`` attaches ratified bounds to the unit's measurements (#496).
    Each :class:`MeasurementSpec` must name a measurement this deck actually
    produces -- a bound on something the deck never measures is a mismatch
    between manifest and deck, not a bound to drop silently.
    """
    body: list[str] = ["* gf180-temp-por batch body -- GENERATED by sim/harness/klt_batch.py"]
    sections: list[str] = []
    temp_c: float | None = None
    analysis: tuple[str, str] | None = None
    extra_analyses: list[tuple[str, str]] = []   # 2nd.. control-block analyses
    init: list[str] = []
    lets: dict[str, str] = {}          # name -> fully expanded expression
    printed: list[tuple[str, int]] = []   # (let name, index of the solve it follows)
    meas: list[tuple[str, str, str]] = []
    lifted: dict[str, float] = {}
    params: dict[str, str] = {}        # plain-number .param cards kept in the body
    in_control = False

    def add_meas(name: str, form: str, text_: str) -> None:
        if any(m[0] == name for m in meas):
            raise BatchIncompatible(f"{key}: duplicate measurement name {name!r}")
        meas.append((name, form, text_))

    def set_analysis(kind: str, args: str, *, control: bool = False) -> None:
        nonlocal analysis
        if analysis is not None:
            if not control:
                raise BatchIncompatible(
                    f"{key}: more than one analysis ({analysis[0]!r} and {kind!r}); "
                    "klt sim runs exactly one per corner"
                )
            # Control-block solves run in order, each followed by its own
            # lets/prints: that is klt's analysis_steps[] (route (a), #440).
            extra_analyses.append((kind.lower(), args.strip()))
            return
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
                set_analysis(m.group(1), m.group(2), control=True)
            elif _LET_RE.match(stripped):
                m = _LET_RE.match(stripped)
                lets[m.group(1)] = _inline(m.group(2).strip(), lets, lambda e: f"({e})")
            elif low.startswith("print "):
                for name in stripped.split()[1:]:
                    if name not in lets:
                        raise BatchIncompatible(
                            f"{key}: `print {name}` of something that is not a `let` vector"
                        )
                    printed.append((name, len(extra_analyses)))
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
                # Keep a top-level declaration in place of the deck's own card.
                # klt's parameter axis is `alterparam <name>=<value>` + `reset`,
                # which refuses a name no top-level `.param` declares; the value
                # here is a sentinel every corner overwrites (see _LIFTED_DEFAULT).
                # It is constant across units so points differing only in the
                # lifted value still share one body, and so one request.
                body.append(f".param {name}={_LIFTED_DEFAULT}")
                continue
            if pm:
                try:
                    float(pm.group(2))
                except ValueError:
                    pass
                else:
                    params[pm.group(1)] = pm.group(2)
            body.append(stripped)

    if in_control:
        raise BatchIncompatible(f"{key}: .control block never closed")
    if analysis is None:
        raise BatchIncompatible(f"{key}: no analysis found (need exactly one)")
    analysis = (analysis[0], _resolve_analysis_args(analysis[1], params, lift_params, key))
    if temp_c is None:
        raise BatchIncompatible(f"{key}: no .temp card; the temperature axis would be undefined")
    steps: list = []
    if extra_analyses:
        if meas:
            raise BatchIncompatible(
                f"{key}: `.meas` cards in a deck with more than one solve are not "
                "expressible as analysis_steps (use `let`/`print` vectors)"
            )
        every = [analysis, *((k, _resolve_analysis_args(a, params, lift_params, key))
                             for k, a in extra_analyses)]
        for i, (kind, args) in enumerate(every):
            step_meas = tuple((f"raw_{n}", "expr", lets[n]) for n, at in printed if at == i)
            steps.append((f"s{i + 1}", (kind, args), step_meas))
        for name, at in printed:
            add_meas(name, "expr", f"s{at + 1}.raw_{name}")
    else:
        for name, _ in printed:
            add_meas(name, "expr", lets[name])
    if not meas:
        raise BatchIncompatible(f"{key}: no measurements; nothing to return from the fleet")
    for name in lift_params:
        lifted.setdefault(name, math.nan)
    missing_lift = [n for n, v in lifted.items() if math.isnan(v)]
    if missing_lift:
        raise BatchIncompatible(f"{key}: lifted .param {', '.join(missing_lift)} not found")
    measured = {n for n, _, _ in meas}
    unmeasured = sorted(s.name for s in specs if s.name not in measured)
    if unmeasured:
        raise BatchIncompatible(
            f"{key}: spec limits name measurement(s) {', '.join(unmeasured[:5])} "
            f"that this deck does not measure (it measures "
            f"{', '.join(sorted(measured)[:8])})"
        )

    return BatchUnit(
        key=key,
        log_path=Path(log_path),
        body="\n".join(body) + "\n",
        process=tuple(sections) if sections else None,
        temp_c=temp_c,
        lifted=tuple(sorted(lifted.items())),
        analysis=analysis,
        measurements=tuple(meas),
        init=tuple(dict.fromkeys([*extra_init, *init])),
        timeout_s=timeout_s,
        steps=tuple(steps),
        specs=tuple(sorted(specs, key=lambda s: s.name)),
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
    #: Submit every request of a run through ONE ``klt sim --batch-set`` call
    #: (#440) instead of one blocking ``klt sim`` per request. ``max_in_flight``
    #: and ``capacity_retries`` are forwarded as ``--max-in-flight`` /
    #: ``--capacity-retries`` on that path only (klt documents both as
    #: ``--batch-set``-specific).
    batch_set: bool = False
    max_in_flight: int = 4
    #: Forwarded as ``--wait-for-capacity`` on BOTH paths (#467): how long klt
    #: waits out a ``batch_no_capacity`` / ``batch_concurrency_cap`` launch
    #: refusal before giving up. 0 means one attempt. Also added to the
    #: client-side subprocess bound, since klt does not charge this wait to
    #: the poll timeout.
    wait_for_capacity_s: int = 600
    capacity_retries: int = 3
    #: Set once a run-wide fatal condition (runner/client ``klt`` mismatch, a
    #: runner PDK that is not the local one) is seen; every later request in
    #: the same run is then refused without being submitted, so a grid does
    #: not burn one fleet job per deck on a runner that cannot run it.
    halted: str | None = field(default=None, init=False)
    #: One row per accepted report, naming what the fleet actually simulated:
    #: ``{job_id, runner_models_lib_sha256, models_lib_sha256, comparison}``.
    #: :func:`batch_provenance` turns it into the evidence record's
    #: ``environment.batch`` block.
    provenance: list[dict] = field(default_factory=list, init=False)
    #: Memo for :meth:`local_model_lib_sha256`; ``""`` means "tried, could
    #: not read it" (distinct from "not computed yet").
    _model_lib_sha256: str | None = field(default=None, init=False, repr=False)

    def local_model_lib_sha256(self) -> str | None:
        """SHA-256 of ``pdk.model_lib``, hashed once per run, or ``None`` if
        it cannot be read. This is the digest the fleet runner's own hash is
        compared against -- not klt's `models_lib_comparison`, which compares
        the runner against the install *klt* resolved, which need not be the
        one ``harness.pdk.find_pdk()`` resolved (#468)."""
        if self._model_lib_sha256 is None:
            # A benign race between group threads recomputes the same digest.
            self._model_lib_sha256 = _sha256_file(self.pdk.model_lib) or ""
        return self._model_lib_sha256 or None


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
    # `specs` belongs here for the same reason `measurements` does (#496):
    # `_build_request` emits one `measurements[]` block for the whole group,
    # read from its first member, so two units graded against different
    # bounds that grouped together would silently inherit the first unit's.
    # Limits are constant per experiment today, so this cannot currently
    # bite -- which is exactly why leaving it out would go unnoticed.
    return (u.body, u.temp_c, u.analysis, u.measurements, u.init, u.timeout_s,
            tuple(n for n, _ in u.lifted), u.process is None, u.steps, u.specs)


def _same(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)


def _request_measurements(
    measurements: tuple[tuple[str, str, str], ...],
    specs: tuple[MeasurementSpec, ...],
) -> list[dict]:
    """``measurements[]`` for a request: each measurement plus the ratified
    bounds (and spec row) klt should grade it against, where there are any."""
    by_name = {s.name: s for s in specs}
    out = []
    for name, form, text in measurements:
        entry = {"name": name, form: text}
        spec = by_name.get(name)
        if spec is not None:
            limits = spec.limits()
            if limits:
                entry["limits"] = limits
            if spec.spec_row:
                entry["spec_row"] = spec.spec_row
        out.append(entry)
    return out


def _build_request(units: list[BatchUnit], pdk: Pdk, cfg: BatchConfig) -> dict:
    first = units[0]
    process_names: list[str] = []
    bundles: dict[str, tuple[str, ...]] = {}
    param_rows: list[tuple[float, ...]] = []
    for u in units:
        if u.process is not None and u.process_name not in bundles:
            bundles[u.process_name] = u.process
            process_names.append(u.process_name)
        row = tuple(v for _, v in u.lifted)
        if not any(len(row) == len(r) and all(_same(a, b) for a, b in zip(row, r)) for r in param_rows):
            param_rows.append(row)

    corners: dict = {"temperature_c": [first.temp_c]}
    if process_names:
        corners["process"] = [{"name": n, "sections": list(bundles[n])} for n in process_names]
    # The lifted values ride klt's parameter axis, not its supply axis: a
    # `.param` name on `corners.supply_v` is an `alter` of a voltage source
    # that does not exist, which klt refuses outright (#464).
    param_keys = [k for k, _ in first.lifted]
    if param_keys:
        corners["params"] = {k: [r[i] for r in param_rows] for i, k in enumerate(param_keys)}

    # Sparse grids: exclude every (process, params) combination not requested.
    wanted = {(u.process_name, tuple(v for _, v in u.lifted)) for u in units}
    exclude = []
    for n in process_names or [None]:
        for row in param_rows:
            if not any(n == wn and len(row) == len(wr) and all(_same(a, b) for a, b in zip(row, wr))
                       for wn, wr in wanted):
                spec: dict = {}
                if n is not None:
                    spec["process"] = n
                if param_keys:
                    spec["params"] = dict(zip(param_keys, row))
                exclude.append(spec)

    request: dict = {
        "netlist": "body.spice",
        "engine": "ngspice",
        "backend": BACKEND_BATCH,
        "netlist_source": "schematic",
        "corners": corners,
        "measurements": _request_measurements(first.measurements, first.specs),
        "options": {
            "timeout_s": first.timeout_s,
            "keep_artifacts": True,
            "ngspice_init": list(first.init),
        },
    }
    if first.steps:
        request["analysis_steps"] = [
            {"name": sname, "analysis": {"kind": kind, "args": args},
             "measurements": [{"name": n, form: txt} for n, form, txt in smeas]}
            for sname, (kind, args), smeas in first.steps
        ]
    else:
        request["analysis"] = {"kind": first.analysis[0], "args": first.analysis[1]}
    if process_names:
        # No `models.pdk_root` here, deliberately (#464). Pinning the root the
        # harness resolved is what klt's own multiple-installs warning asks
        # for, but on this backend klt refuses it: the field is forwarded to
        # the fleet runner verbatim, where a submitter-local path does not
        # exist, so `_validate_batch_pdk_root` rejects any `pdk_root` that is
        # a real directory here (`models_pdk_root_host_path`, klt #4097). It
        # is refused at submit time, which `--dry-run` never reaches -- so a
        # dry run would validate and every real submit would die.
        #
        # It would not record the right thing either: on batch the models come
        # from the runner's own PDK image, not this host's install, so the
        # submitter's root is not the provenance of the simulation. klt
        # reports the honest comparison itself, in
        # `environment.remote.models_lib_comparison` (klt #5321: the runner's
        # executed model-card hash against the client's).
        request["models"] = {
            "pdk": pdk.variant,
            "lib": str(pdk.model_lib.relative_to(pdk.path)),
        }
    if exclude:
        request["exclude"] = exclude
    if cfg.poll_timeout_s is not None:
        request["batch"] = {"poll_timeout_s": cfg.poll_timeout_s}
    return request


def _stage(units: list[BatchUnit], pdk: Pdk, cfg: BatchConfig, name: str,
           request_name: str = "request.json") -> tuple[Path, dict]:
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
    req_path = stage / request_name
    req_path.write_text(json.dumps(request, indent=2) + "\n")
    return req_path, request


@dataclass(frozen=True)
class StagedRequest:
    """One ``klt sim`` request written to disk, and the units it covers."""

    #: Group name: the stage subdirectory, and the ``klt-<name>.request.json``
    #: evidence filename when the request is submitted.
    name: str
    #: The written request JSON. Its ``netlist`` is relative to this path's
    #: own directory, so ``klt sim <path> --dry-run`` resolves from anywhere.
    path: Path
    request: dict
    units: tuple[BatchUnit, ...]
    #: Positions of :attr:`units` in the list they were grouped from.
    indices: tuple[int, ...] = ()

    @property
    def unit_count(self) -> int:
        """Requested corners this request expands to -- its own units, not
        counting the sparse-grid cells ``exclude`` carves back out."""
        return len(self.units)

    @property
    def temperature_c(self) -> float:
        return self.units[0].temp_c


def _group_name(members: list[BatchUnit]) -> str:
    return _safe(members[0].key) + (f"+{len(members) - 1}" if len(members) > 1 else "")


def group_units(units: list[BatchUnit]) -> list[list[int]]:
    """Indices of ``units``, grouped into one ``klt sim`` request each.

    Units that share body/analysis/measurements/specs/temperature become one
    request (a process x parameter matrix, sparse cells excluded); every
    other unit is its own. The one home for that rule: both
    :func:`stage_requests` and :func:`run_units` group through here, so a
    staged request set and a submitted one can never be packaged differently.
    Duplicate keys are refused -- a result keyed by a name two units share
    could not be attributed back.
    """
    keys = [u.key for u in units]
    if len(set(keys)) != len(keys):
        dup = sorted({k for k in keys if keys.count(k) > 1})
        raise BatchIncompatible(f"duplicate unit keys in one submission: {', '.join(dup[:5])}")
    groups: dict[tuple, list[int]] = {}
    for i, u in enumerate(units):
        groups.setdefault(_unit_group_key(u), []).append(i)
    return list(groups.values())


def _stage_group(units: list[BatchUnit], cfg: BatchConfig, indices: list[int],
                 *, named: bool = False) -> StagedRequest:
    members = [units[i] for i in indices]
    name = _group_name(members)
    req_path, request = _stage(members, cfg.pdk, cfg, name,
                               request_name=f"{name}.json" if named else "request.json")
    return StagedRequest(name=name, path=req_path, request=request,
                         units=tuple(members), indices=tuple(indices))


def stage_requests(units: list[BatchUnit], cfg: BatchConfig,
                   *, named: bool = True) -> list[StagedRequest]:
    """Group ``units`` and write one ``klt sim`` request per group, submitting
    nothing (#496).

    The request-building half of :func:`run_units`: same grouping
    (:func:`group_units`), same staging (:func:`_stage_group`), same request
    shape -- it simply stops before ``klt`` is invoked, so it needs neither
    ``klt`` on PATH nor a reachable fleet. ``named`` writes each request as
    ``<group>.json`` rather than ``request.json``, so a whole set is
    distinguishable in one listing and can be passed to ``klt sim
    --batch-set`` or validated one-by-one with ``klt sim <request>
    --dry-run``.
    """
    return [_stage_group(units, cfg, indices, named=named)
            for indices in group_units(units)]


# --------------------------------------------------------------------------
# invocation
# --------------------------------------------------------------------------


def invoke_klt(req: Path, outdir: Path, cfg: BatchConfig, timeout_s: float) -> dict:
    """Run ``klt sim`` on ``req`` with the batch backend forced; return the
    parsed report.

    ``--wait-for-capacity cfg.wait_for_capacity_s`` is always passed (#467):
    the fleet is vCPU-budgeted, so a burst is refused routinely, and klt waits
    the refusal out with backoff instead of failing the submit. Without it a
    single-request run got one launch attempt. ``--capacity-retries`` is NOT
    passed -- ``klt sim --help`` documents it as applying with ``--batch-set``
    only.

    ``timeout_s`` must therefore already include the capacity wait; see
    :func:`run_units`. klt measures that wait on its own clock and does not
    charge it to the request's ``batch.poll_timeout_s``, whose clock starts
    once a launch succeeds.

    Re-submits only on the fleet concurrency-cap refusal, within
    ``cfg.max_cap_wait_s``; every other failure raises."""
    exe = shutil.which(cfg.klt)
    if not exe:
        raise KltMissing(
            f"'{cfg.klt}' not found on PATH; batch mode never falls back to a local ngspice run"
        )
    cmd = [exe, "sim", str(req), "-o", str(outdir), "--format", "json",
           "--wait-for-capacity", str(cfg.wait_for_capacity_s),
           "--backend", BACKEND_BATCH]
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


def invoke_klt_set(reqs: list[Path], outdir: Path, cfg: BatchConfig, timeout_s: float) -> dict:
    """Run ONE ``klt sim --batch-set`` over ``reqs``; return the aggregate
    envelope. Exit codes 0/3/4 carry an envelope on stdout (4 = some member
    errored or was refused: reported per member, not raised); anything else,
    or output that is not an envelope, raises :class:`BatchSubmitError`."""
    exe = shutil.which(cfg.klt)
    if not exe:
        raise KltMissing(
            f"'{cfg.klt}' not found on PATH; batch mode never falls back to a local ngspice run"
        )
    cmd = [exe, "sim", "--batch-set", *map(str, reqs),
           "--max-in-flight", str(cfg.max_in_flight),
           "--wait-for-capacity", str(cfg.wait_for_capacity_s),
           "--capacity-retries", str(cfg.capacity_retries),
           "-o", str(outdir), "--format", "json", "--backend", BACKEND_BATCH]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        raise BatchSubmitError(
            f"klt sim --batch-set ({len(reqs)} requests) did not finish within {timeout_s:.0f}s "
            "(the fleet jobs may still be running)"
        ) from exc
    except OSError as exc:
        raise BatchSubmitError(f"could not execute klt: {exc}") from exc
    try:
        env = json.loads(proc.stdout) if proc.stdout.strip() else None
    except json.JSONDecodeError:
        env = None
    if proc.returncode in (0, 3, 4) and isinstance(env, dict) and isinstance(env.get("requests"), list):
        return env
    message = ""
    if isinstance(env, dict) and isinstance(env.get("error"), dict):
        message = str(env["error"].get("message", ""))
    message = (message + " " + proc.stderr).strip()
    raise BatchSubmitError(
        f"klt sim --batch-set failed (exit {proc.returncode}): "
        f"{message[:800] or proc.stdout[:400] or 'no output'}"
    )


def _sha256_file(path: Path) -> str | None:
    """``path``'s SHA-256 as lowercase hex, or ``None`` if it cannot be read.

    Unreadable is not an error here: it makes the runner comparison *not
    comparable*, which is recorded as such rather than passed off as a match.
    """
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _hex64(value) -> str | None:
    """``value`` as a lowercase 64-hex digest, else ``None``.

    Absent, JSON ``null``, a non-string or anything that is not a SHA-256
    digest all mean "no usable hash" -- never guessed at, and never allowed to
    compare equal to a real digest.
    """
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    return text if _SHA256_RE.match(text) else None


def _remote_jobs(remote: dict) -> list[dict]:
    """The per-fleet-job records in ``environment.remote``.

    A single-job report carries ``job_id`` / ``runner_models_lib_sha256`` /
    ``models_lib_comparison`` on ``remote`` itself; a submission that fanned
    out to several jobs carries one entry per member under ``remote.fleet``
    (klt 0.9.2). Both shapes are gated and recorded the same way.
    """
    fleet = remote.get("fleet")
    members = [m for m in fleet if isinstance(m, dict)] if isinstance(fleet, list) else []
    return members or [remote]


def _klt_comparison(value) -> tuple[str | None, str]:
    """klt's own ``models_lib_comparison`` -> ``(status, reason)``.

    ``status`` is ``None`` for a field that is absent or not an object, so a
    malformed comparison is never read as a verdict either way.
    """
    if not isinstance(value, dict):
        return None, ""
    status = value.get("status")
    reason = value.get("reason") or value.get("warning") or ""
    return (status if isinstance(status, str) else None), str(reason)[:300]


def _models_lib_rows(remote: dict, job_id: str, cfg: BatchConfig) -> list[dict]:
    """Gate a report's fleet jobs on the PDK the runner actually read, and
    return one provenance row per job.

    Fail closed, exactly as ``runner_compatibility`` already does: a runner
    digest that differs from this host's ``pdk.model_lib``, or klt's own
    client-vs-runner ``mismatch`` verdict, raises :class:`BatchPdkMismatch`
    (so no unit of the report is ``ok`` and the run halts). A job with no
    usable runner digest -- an older runner, staged models, a model library
    this host cannot read -- is accepted and recorded as not comparable.
    """
    local = cfg.local_model_lib_sha256()
    why = "a record of it would name a PDK build the simulation never read"
    fix = (
        "point PDK_ROOT (or sim/pdk.local.json) at the install the fleet runner uses, "
        f"instead of {cfg.pdk.path} (found via {cfg.pdk.source})"
    )
    rows: list[dict] = []
    for job_rec in _remote_jobs(remote):
        job = str(job_rec.get("job_id") or job_id)
        runner_hash = _hex64(job_rec.get("runner_models_lib_sha256"))
        klt_status, klt_reason = _klt_comparison(job_rec.get("models_lib_comparison"))
        if klt_status == "mismatch":
            raise BatchPdkMismatch(
                f"fleet job {job}: klt reports models_lib_comparison='mismatch' -- the "
                "runner did not read the model library the client resolved"
                + (f": {klt_reason}" if klt_reason else "")
                + f"; its result is not accepted, because {why} -- {fix}"
            )
        if runner_hash is not None and local is not None and runner_hash != local:
            raise BatchPdkMismatch(
                f"fleet job {job}: the runner read model library sha256 {runner_hash}, "
                f"but this host resolved {local} ({cfg.pdk.model_lib}); its result is "
                f"not accepted, because {why} -- {fix}"
            )
        if runner_hash is None:
            comparison = {"status": "not_comparable", "reason": "runner_hash_unavailable"}
        elif local is None:
            comparison = {"status": "not_comparable", "reason": "client_hash_unavailable"}
        else:
            comparison = {"status": "match"}
        rows.append({
            "job_id": job,
            "runner_models_lib_sha256": runner_hash,
            "models_lib_sha256": local,
            "comparison": comparison,
            "klt_models_lib_comparison": klt_status,
        })
    return rows


def batch_provenance(cfg: BatchConfig) -> dict:
    """What the fleet actually simulated, for the evidence record (#468).

    One entry per accepted report in ``cfg.provenance`` plus an aggregate
    verdict: ``match`` only when every job's runner digest was compared and
    equal, otherwise ``not_comparable`` (``mismatch`` cannot appear -- such a
    report is rejected before it is recorded). ``no_accepted_report`` when the
    run accepted none, so an all-failed batch run does not render as a local
    one. Callers pass the result to ``report.build_record`` /
    ``mc_report.build_mc_record`` as ``batch=``.
    """
    jobs = list(cfg.provenance)
    statuses = {str(j.get("comparison", {}).get("status")) for j in jobs}
    if not jobs:
        overall = "no_accepted_report"
    elif statuses == {"match"}:
        overall = "match"
    else:
        overall = "not_comparable"
    return {
        "backend": BACKEND_BATCH,
        "models_lib_sha256": cfg.local_model_lib_sha256(),
        "models_lib_comparison": overall,
        "jobs": jobs,
    }


def _finite(value) -> float | None:
    """``value`` as a float if it is a finite JSON number, else ``None``.
    Booleans (a JSON ``true`` is a Python ``int``) and strings are refused."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _match(report_corners: list[dict], unit: BatchUnit) -> list[dict]:
    hits = []
    for c in report_corners:
        if unit.process_name is not None and c.get("process") != unit.process_name:
            continue
        t = _finite(c.get("temperature_c"))
        if t is None or not _same(t, unit.temp_c):
            continue
        if unit.lifted:
            # klt reports a parameter-axis point under `params` (present only
            # when the request had such an axis), not under `supply_v`.
            pv = c.get("params")
            if not isinstance(pv, dict):
                continue
            if any(_finite(pv.get(k)) is None or not _same(_finite(pv[k]), v)
                   for k, v in unit.lifted):
                continue
        hits.append(c)
    return hits


def _collect_group(
    units: list[BatchUnit], report: dict, tolerate_absent: bool, cfg: BatchConfig
) -> list[UnitOutcome]:
    remote = (report.get("environment") or {}).get("remote")
    if not isinstance(remote, dict) or not remote.get("job_id"):
        raise BatchResultError(
            "report has no environment.remote.job_id: this run was not executed on the "
            "batch fleet, so it is rejected (no local result is accepted in batch mode)"
        )
    job_id = str(remote["job_id"])
    compat = remote.get("runner_compatibility")
    if compat is not None and compat != "match":
        raise BatchRunnerMismatch(
            f"fleet job {job_id}: runner_compatibility={compat!r} "
            f"(runner klt {remote.get('runner_klt_version')!r}, client klt "
            f"{remote.get('client_klt_version')!r}); its result is not accepted -- "
            "submit with a klt client that matches the fleet runner (--klt), or "
            "update the runner image"
        )
    # What the runner's PDK image actually provided, before any corner is
    # judged: an accepted result must have been simulated against the model
    # library the record is about to name (#468).
    provenance = _models_lib_rows(remote, job_id, cfg)
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
                                        f"params={dict(u.lifted)})", job_id=job_id))
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
    # Accepted: record what the fleet read. `list.append` from the group
    # threads needs no lock; the rows are only read once the run is over.
    cfg.provenance.extend(provenance)
    return outcomes


def _corner_fields(c: dict) -> tuple[float, str | None, list[dict], list[dict]]:
    """The nested fields ``_judge`` consumes, type-checked. Raises
    :class:`BatchResultError` (with the offending field named) for a corner
    whose containers are not the shape of a klt report, so a malformed report
    is an error outcome rather than a ``TypeError``/``ValueError`` escaping
    from deep inside the judgement -- or, worse, being silently skipped."""
    runtime = c.get("runtime_s")
    seconds = 0.0 if runtime is None else _finite(runtime)
    if seconds is None:
        raise BatchResultError(f"corner field runtime_s is not a finite number: {runtime!r}")

    artifacts = c.get("artifacts")
    if artifacts is None:
        artifacts = {}
    if not isinstance(artifacts, dict):
        raise BatchResultError(f"corner field artifacts is not an object: {type(artifacts).__name__}")
    log = artifacts.get("log")
    if log is not None and not isinstance(log, str):
        raise BatchResultError(f"corner field artifacts.log is not a path string: {log!r}")

    diags = c.get("diagnostics")
    if diags is None:
        diags = []
    if not isinstance(diags, list) or not all(isinstance(d, dict) for d in diags):
        raise BatchResultError("corner field diagnostics is not a list of objects")

    meas = c.get("measurements")
    if meas is None:
        meas = []
    if not isinstance(meas, list) or not all(isinstance(m, dict) for m in meas):
        raise BatchResultError("corner field measurements is not a list of objects")
    if not all(isinstance(m.get("name"), str) and m["name"] for m in meas):
        raise BatchResultError("corner field measurements has an entry without a string name")
    names = [m["name"] for m in meas]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        raise BatchResultError(
            f"corner field measurements names {', '.join(dup)} more than once")
    return seconds, log or None, diags, meas


def _judge(u: BatchUnit, c: dict, tolerate_absent: bool, job_id: str) -> UnitOutcome:
    """One matched corner -> ``ok`` only if every field agrees it succeeded.

    Checked before the raw log is copied: the containers are well formed;
    every requested measurement is either absent (``null``) or a finite
    number (not a string, boolean, NaN or infinity); an error-level
    diagnostic is never accepted under a ``pass`` label; and the
    absent-measurement exception (``tolerate_absent``) applies only to a corner
    klt itself labelled ``error`` whose error diagnostics are all absence
    codes *and* that actually has an absent requested measurement.
    """
    try:
        seconds, log, diags, meas = _corner_fields(c)
    except BatchResultError as exc:
        return UnitOutcome(u, "error", f"malformed klt result for this unit: {exc}", job_id=job_id)
    errors = [d for d in diags if d.get("severity") == "error"]
    codes = sorted({str(d.get("code", "?")) for d in errors})
    detail = "; ".join(f"{d.get('code')}: {d.get('message', '')}".strip() for d in errors)[:600]
    raw_values = {m["name"]: m.get("value") for m in meas}
    wanted = [n for n, _, _ in u.measurements]
    malformed = [f"{n}={raw_values[n]!r}" for n in wanted
                 if raw_values.get(n) is not None and _finite(raw_values[n]) is None]
    values: dict[str, float | None] = {
        n: (None if v is None else _finite(v)) for n, v in raw_values.items()
    }
    absent = [n for n in wanted if values.get(n) is None]
    status = c.get("status")

    def fail(msg: str) -> UnitOutcome:
        return UnitOutcome(u, "error", msg, values=values, absent=absent, seconds=seconds, job_id=job_id)

    if malformed:
        return fail("requested measurement value(s) not a finite number: "
                    + ", ".join(malformed)[:600])
    if status == "pass" and errors:
        return fail(f"klt corner status 'pass' contradicts its error diagnostic(s) "
                    f"[{', '.join(codes)}]: {detail}")
    absence_only = bool(errors) and all(d.get("code") in ABSENT_MEASUREMENT_CODES for d in errors)
    if status == "error" and absence_only and not absent:
        return fail(f"klt corner status 'error' with only absent-measurement diagnostic(s) "
                    f"[{', '.join(codes)}], but no requested measurement is absent: {detail}")

    if not log or not Path(log).is_file():
        return fail(f"klt returned no raw log for this unit (status={status!r}"
                    f"{', ' + detail if detail else ''})")

    try:
        log_text = Path(log).read_text(errors="replace")
    except OSError as exc:
        return fail(f"klt raw log is unreadable: {exc}")
    if _ABORTED in log_text:
        return fail(f"the analysis aborted on the fleet (ngspice: '{_ABORTED}'); "
                    f"see {log}" + (f" [{', '.join(codes)}]" if codes else ""))
    if wanted and len(absent) == len(wanted):
        # An absent measurement means "never happened" only when the run
        # produced *some* result; a corner with no value at all did not run.
        return fail(f"no requested measurement produced a value (status={status!r}"
                    + (f" [{', '.join(codes)}]" if codes else "")
                    + f"); the analysis most likely did not run -- see {log}")

    tolerated = tolerate_absent and status == "error" and absence_only and bool(absent)
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

    Units are grouped and staged by the same :func:`group_units` /
    :func:`_stage_group` pair :func:`stage_requests` uses, so a submitted
    request is packaged exactly as ``--emit-request`` would have written it.

    ``tolerate_absent`` keeps a corner whose only error diagnostics are an
    absent ``.meas`` (see :data:`ABSENT_MEASUREMENT_CODES`) as ``ok`` with
    the gap listed in ``absent`` -- the contract of the control scripts,
    where an absent measurement means "never happened". Request-level
    failures become error outcomes for that request's units; a missing
    ``klt`` raises :class:`KltMissing`.
    """
    batches = group_units(units)
    if not shutil.which(cfg.klt):
        raise KltMissing(
            f"'{cfg.klt}' not found on PATH; batch mode never falls back to a local ngspice run"
        )

    results: list[UnitOutcome | None] = [None] * len(units)

    def record(members: list[BatchUnit], name: str, req_path: Path, report: dict) -> list[UnitOutcome]:
        (req_path.parent / "report.json").write_text(
            json.dumps(report, indent=1, sort_keys=True) + "\n")
        if cfg.evidence_dir is not None:
            cfg.evidence_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(req_path, cfg.evidence_dir / f"klt-{name}.request.json")
            shutil.copyfile(req_path.parent / "report.json",
                            cfg.evidence_dir / f"klt-{name}.report.json")
        return _collect_group(members, report, tolerate_absent, cfg)

    def deliver(indices: list[int], outs: list[UnitOutcome]) -> None:
        for i, out in zip(indices, outs):
            results[i] = out
            if on_outcome is not None:
                on_outcome(out)

    def do_group(indices: list[int]) -> None:
        members = [units[i] for i in indices]
        name = _group_name(members)
        try:
            if cfg.halted:
                raise BatchRunFatal(f"not submitted: {cfg.halted}")
            staged = _stage_group(units, cfg, indices)
            req_path, request = staged.path, staged.request
            n_corners = len(members) + len(request.get("exclude", []))
            poll = cfg.poll_timeout_s or (members[0].timeout_s * n_corners + 1800 + 120)
            # The capacity wait is additive, not part of ``poll`` (#467): klt
            # runs it on its own clock before the poll clock starts, so a
            # submit that waits out a full refusal window and then runs must
            # not be killed by our own subprocess bound. Mirrors the
            # ``cfg.wait_for_capacity_s * waves`` term in ``do_set``.
            report = invoke_klt(req_path, req_path.parent / "klt", cfg,
                                poll + cfg.wait_for_capacity_s + cfg.client_slack_s)
            outs = record(members, name, req_path, report)
        except KltMissing:
            raise
        except BatchRunFatal as exc:
            if not cfg.halted:
                cfg.halted = f"an earlier request in this run was rejected: {exc}"
            outs = [UnitOutcome(u, "error", str(exc)) for u in members]
        except BatchError as exc:
            outs = [UnitOutcome(u, "error", str(exc)) for u in members]
        deliver(indices, outs)

    def do_set(batches: list[list[int]]) -> None:
        """Every request of the run through one ``klt sim --batch-set`` (#440).
        A member klt refused, or whose report is missing/malformed, is an error
        outcome for that member's units only -- never dropped, never ok."""
        staged: list[tuple[list[int], list[BatchUnit], str, Path, dict]] = []
        for b in batches:
            s = _stage_group(units, cfg, b, named=True)
            staged.append((b, list(s.units), s.name, s.path, s.request))
        longest = max(m[0].timeout_s * (len(m) + len(r.get("exclude", []))) + 1800 + 120
                      for _, m, _, _, r in staged)
        waves = -(-len(staged) // max(1, cfg.max_in_flight))
        total = (cfg.poll_timeout_s or longest) * waves + cfg.wait_for_capacity_s * waves
        outdir = cfg.stage_root / "klt-set"
        try:
            env = invoke_klt_set([s_[3] for s_ in staged], outdir, cfg, total + cfg.client_slack_s)
        except KltMissing:
            raise
        except BatchError as exc:
            for b, members, *_ in staged:
                deliver(b, [UnitOutcome(u, "error", str(exc)) for u in members])
            return
        by_request = {}
        for entry in env["requests"]:
            if isinstance(entry, dict) and isinstance(entry.get("request"), str):
                by_request[Path(entry["request"]).resolve()] = entry
        for b, members, name, req_path, _ in staged:
            entry = by_request.get(req_path.resolve())
            try:
                if entry is None:
                    raise BatchResultError("klt returned no entry for this request")
                rpt = entry.get("report")
                if not rpt or not Path(rpt).is_file():
                    err = entry.get("error") if isinstance(entry.get("error"), dict) else {}
                    raise BatchSubmitError(
                        f"klt sim --batch-set: request {req_path.name} {entry.get('status')!r} with no "
                        f"report ({err.get('code', '?')}: {str(err.get('message', ''))[:600]})")
                report = json.loads(Path(rpt).read_text())
                if not isinstance(report, dict) or "corners" not in report or "error" in report:
                    raise BatchResultError(f"request {req_path.name}: report is not a corner report")
                outs = record(members, name, req_path, report)
            except (BatchError, OSError, json.JSONDecodeError) as exc:
                # The whole set was already submitted in one klt call, so
                # halting cannot un-submit a member -- but it still refuses a
                # later `run_units` on this config, as `do_group` does.
                if isinstance(exc, BatchRunFatal) and not cfg.halted:
                    cfg.halted = f"an earlier request in this run was rejected: {exc}"
                outs = [UnitOutcome(u, "error", str(exc)) for u in members]
            deliver(b, outs)

    if cfg.batch_set:
        if cfg.halted:
            for b in batches:
                deliver(b, [UnitOutcome(units[i], "error", f"not submitted: {cfg.halted}") for i in b])
        else:
            do_set(batches)
    elif jobs <= 1 or len(batches) == 1:
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
