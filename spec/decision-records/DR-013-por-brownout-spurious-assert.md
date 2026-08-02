# DR-013: An intermediate falling-slew band asserts `POR_RAW` above `VPOR-uparrow,max` — confirmed, mechanism not fully resolved

- **Status**: proposed
- **Date**: 2026-08-02
- **Decided by**: Loom Builder agent, issue #61

## Context

[DR-011](DR-011-brownout-falling-slew-limit.md)'s Consequences section
recorded, but deliberately left open, a finding from
`sim/por-brownout/control/results.md` § B: at one PVT point
(`tt`/27 °C/3.30 V), two falling-edge rates *slower* than DR-011's own
"`RESETn` never leaves the dip rail" boundary (measured 7.67–11.50 mV/µs)
asserted `POR_RAW` at a rail **above** `VPOR-uparrow,max` = 2.73 V — a reset
firing while the supply is still comfortably inside the ratified operating
range:

| falling slew | rail at `POR_RAW` assert (control, one point) |
|---|---|
| 7.67 mV/µs (0.3 ms edge) | 2.9941 V — spurious |
| 2.30 mV/µs (1.0 ms edge) | 3.1385 V — spurious |
| 0.77 mV/µs (3.0 ms edge) | 2.3828 V — correct, inside the ratified `VPOR-downarrow` band |

Per `sim/README.md`, a control is a diagnosis, not evidence: it substantiates
nothing about the 81-point corner grid on its own. This issue's job was to
confirm or refute the effect across the full grid, determine whether the
assert rail is bounded or tracks `VDD`, and check whether
`design/bias_core.md`'s documented ≈2.4 µs × ramp-rate `VREF` feedthrough term
is quantitatively sufficient to explain it.

All three falling rates above sit **inside** the ratified
[`por-ramp-rate`](../target-spec.md#por-ramp-rate) envelope (1 V/s … 1 V/µs =
1…1e6 V/s; 0.77–7.67 mV/µs = 770–7670 V/s), and are *faster* than the
~243–408 V/s falling ramp `sim/por-vth/`'s own `por-vth-fall` evidence was
taken at (`sim/por-vth/testbench/stimulus.spice`). This is therefore a
falling-rate regime inside the already-ratified envelope that no existing
record had characterized on a dip/recovery profile.

## Confirm/refute grid

[`sim/por-brownout-spurious/records/20260802-122414-3c3e728.md`](../../sim/por-brownout-spurious/records/20260802-122414-3c3e728.md),
minted by `sim/run_corners.py`, reproduces the control's own three Part-B
points (0.3/1.0/3.0 ms edge, 1.0 V dip depth, 50 µs dwell) as three parallel
branches sharing one transient — the same multi-branch idiom
`sim/por-ramp-rate/testbench/stimulus.spice` already uses — across the full
81-point PVT grid, per `sim/README.md`'s directory/record convention.

**Confirmed, and far from a one-corner curiosity.** Both of the control's
spurious rates fail at most of the grid; the control's own "correct" third
point fails at a substantial minority of it too:

| branch | slew (tt/27C/3.30V) | assert rail: min / max across the grid | FAIL / ERROR / PASS |
|---|---|---|---|
| xb1 (0.3 ms edge) | 7.67 mV/µs | 1.8752 V (`fs_27c_3.63v`) … 3.44728 V (`ff_125c_3.63v`) | **45/81 FAIL**, 5/81 **ERROR** (never asserts inside the dip window — those 5 corners, `ss_-40c` at all 3 supplies plus `res_ss_-40c` at 3.30/3.63 V, have already crossed into #55/#60's own "`RESETn` never leaves the dip rail" regime at this slew, exactly as the tb.json's own check description anticipated), 31/81 PASS |
| xb3 (1.0 ms edge) | 2.30 mV/µs | 2.34782 V (`ff_125c_2.97v`) … 3.48184 V (`res_ff_-40c_3.63v`) | **74/81 FAIL (91 %)**, 7/81 PASS |
| xb6 (3.0 ms edge) | 0.77 mV/µs | 2.34908 V (`res_ss_125c_3.63v`) … 3.43977 V (`fs_-40c_3.63v`) | **15/81 FAIL (19 %)**, 66/81 PASS |

`xb6` is the control's own "correct, inside the ratified band" reference
point — at `tt`/27 °C/3.30 V it is (2.3827 V, in band). Across the full grid
it is **not** universally correct: 15 corners, overwhelmingly `−40 °C`
combined with the two higher supplies (3.30 V / 3.63 V) — `tt`, `ss`, `fs`,
`sf`, `res_ff`, `res_ss`, `bjt_ff`, `bjt_ss` at `−40c_3.30v`/`−40c_3.63v`, plus
one `27c_3.63v` and one `res_ss_-40c_2.97v` outlier — also assert above
`VPOR-uparrow,max`. The control's single point was not wrong; it was simply
one of the 66 corners where 0.77 mV/µs still behaves.

**The assert rail tracks `VDD`; it is not bounded to a fixed absolute
threshold.** Holding process and temperature fixed at `tt`/27 °C and sweeping
only supply, branch `xb3`'s assert rail is:

| supply | assert rail (`xb3`) | offset below that supply's own `VDD` |
|---|---|---|
| 2.97 V | 2.81248 V | −158 mV |
| 3.30 V | 3.13861 V | −161 mV |
| 3.63 V | 3.46351 V | −167 mV |

An offset that stays within 9 mV of −160 mV while the supply itself moves by
660 mV is a **ratiometric** trip (tracking `VDD`), not a threshold pinned to
an absolute device voltage. The same pattern holds across every process
corner at `27c`/`3.30v` (`xb3` spans only 3.09–3.15 V there, a 60 mV band, at
nine different process skews) — process corner barely moves the number;
supply moves it almost 1:1.

## The feedthrough-magnitude arithmetic check

`design/bias_core.md`'s "Ramp-rate feedthrough" note gives the coefficient as
**≈2.4 µs × ramp rate**, input-referred on `VREF`, sign always toward more
loop current (`VREF` high). At the two confirmed-spurious rates the implied
offset is:

- 7.67 mV/µs → 2.4 µs × 7.67 mV/µs ≈ **18.4 mV**
- 2.30 mV/µs → 2.4 µs × 2.30 mV/µs ≈ **5.5 mV**

**This does not close.** The record's own `vref_at_praw_bN_v` measurements at
`tt`/27 °C/3.30 V show `VREF` at the assert instant sitting at **0.7326 V**
(branch xb1) and **1.1187 V** (branch xb3) against a **1.1993 V** settled
value (`sim/por-brownout/control/results.md`'s own pre-dip figure) — offsets
of **−467 mV** and **−81 mV**, one to two orders of magnitude larger than the
5.5–18.4 mV the feedthrough coefficient predicts, and in the case of branch
xb1 large enough that "feedthrough" (a small linear perturbation) is not the
right word for it at all — `VREF` has not settled, it is still recovering
from the dip's own collapse.

**The sign does not close either.** `design/por_comparator.md`'s own
algebra is `VPOR-downarrow = VREF · (RTOP+RBOT+RHYS)/(RBOT+RHYS)` — a
**lower** `VREF` predicts a **lower** assert threshold (reset should fire
*later*, at a lower rail, not earlier at a higher one). Both branches measure
`VREF` **below** settled at the assert instant, yet the assert rail is
**above** `VPOR-uparrow,max` — the opposite direction the static divider
algebra predicts for a depressed `VREF`.

**Conclusion, stated plainly**: neither the ≈2.4 µs feedthrough coefficient
(wrong order of magnitude) nor the static `VREF`-scales-`VPOR-downarrow`
relationship (wrong sign) is quantitatively sufficient to explain the
observed effect. Something in the *dynamic* response of the comparator's
sense divider, its bias current, or `bias_core`'s own settling path — not
captured by either of those two models — is the actual driver. This record
does not identify that mechanism; it rules out the two candidate
explanations the Curator's own arithmetic check invited, honestly, rather
than accepting "plausibly the same family" as confirmation (the exact framing
DR-011's Consequences section flagged as unresolved).

## Decision

1. **The effect is confirmed on the full 81-point grid** — not just refuted
   nor limited to the control's one point. It is pervasive at both of the
   control's spurious rates (55 % and 91 % of the grid) and present at a
   sizeable minority of the grid (19 %) even at the control's own "correct"
   reference rate. `spec/target-spec.md#por-brownout`'s existing amendment
   (added by DR-011) already names this defect and points at #61; this
   record supplies the confirming evidence, the boundedness finding (tracks
   `VDD`, not a fixed threshold), and the arithmetic check the amendment's
   own text anticipated.

2. **`por-vth-fall` and `por-hysteresis` are not retroactively invalidated**,
   but their evidence is now known to be scoped: `sim/por-vth/`'s
   continuous-ramp characterization (**~243–408 V/s** falling) does not cover
   the **770–7670 V/s** dip/recovery regime this record measures, even though
   both sit inside the same ratified `por-ramp-rate` envelope. The two rows'
   `ratifiable` status stands on the evidence that supports it (a monotonic
   ramp); this record adds a **separate, dip-shaped** falling-rate condition
   under which the assert threshold is violated, and that condition is not
   silently absorbed into either row's existing verdict — see the
   `target-spec.md` edit below.

3. **No design change is made.** This record measures and diagnoses; it does
   not propose a fix. A structural fix (if one exists short of the `por-iq`
   budget re-cost `design/bias_core.md`'s starved-loop section already
   discusses) is a separate, future decision.

4. **The falling-edge counterpart of the ramp-rate feedthrough note in
   `design/bias_core.md` is updated** to record that the existing rising-edge
   coefficient does not explain this falling-edge effect, rather than being
   silently extended to cover it.

## Alternatives considered

- **Accept the feedthrough-coefficient hypothesis without the arithmetic
  check** — not chosen; the Curator's own review of #61 flagged that the
  coefficient likely would not close quantitatively, and accepting a
  qualitative "same family" resemblance without checking the numbers is
  exactly the anti-pattern CLAUDE.md's evidence-before-claim rule exists to
  prevent.
- **Fold this into DR-011** as an addendum rather than a new record — not
  chosen; DR-011 already root-caused a *different* mechanism (the fast-edge
  latch-out) with its own boundary and its own falsifiable claims. This
  record's confirm/refute grid and arithmetic check stand on their own
  evidence and deserve their own citable record rather than diluting DR-011's
  already-ratified reasoning.
- **Run the full original six-branch sweep (0.3/0.5/1.0/1.5/2.0/3.0 ms
  edges)** — not chosen for this record. The shared build machine was running
  under heavy multi-tenant contention during this issue's work session (many
  concurrent `ngspice` jobs from unrelated repos/issues); a single 81-point
  grid point on the six-branch deck did not reliably complete inside a
  300–1800 s per-point timeout. The deck was trimmed to the three branches
  that reproduce the control's own three Part-B points exactly (still a full
  81-point grid, still `sim/run_corners.py`-minted), which is sufficient for
  this issue's own acceptance criteria (confirm/refute, boundedness, the
  arithmetic check). The finer transition boundary between 0.77 and
  2.30 mV/µs (the original 0.5/1.5/2.0 ms branches) is explicitly left
  uncharacterized — a follow-up, not a silent scope cut.

## Consequences

- `spec/target-spec.md#por-brownout`'s existing DR-011 amendment gets its #61
  forward-reference filled in with this record's actual finding instead of
  standing as an open question.
- `design/bias_core.md`'s "Ramp-rate feedthrough" section gains a falling-edge
  note stating the coefficient does not explain this effect, so the gap is
  visible rather than silently inherited by the next reader.
- The true dynamic mechanism behind the spurious assert remains
  **unidentified** — this is a genuine open item, not a resolved one. A
  follow-up issue is warranted to root-cause it (candidate directions: the
  sense divider's own RC lag on a fast-falling rail vs. `VREF`'s recovery
  path, or a bias-current-dependent shift in the comparator's own offset as
  `IBIAS` droops with the starved loop) before any design change is
  considered.
- The transition boundary between the confirmed-spurious band and the
  control's correct 0.77 mV/µs point is not characterized by this record
  (see Alternatives) and is available as follow-up scope, potentially
  coordinated with #60's own falling-slew grid on the same dip topology.
