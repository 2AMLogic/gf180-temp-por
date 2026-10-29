# por-brownout: why the schematic leg yields no re-assert at 8 corners (#405)

Diagnosis of the 48 `status: error` rows in `layout/reports/temp_por_top/pex.json`
(`por-brownout`, schematic leg `value: null`, extracted leg measured). Evidence
only: nothing in `spec/`, the bench or the committed PEX report was changed.

## Result

**Classification (a): the schematic does not re-assert RESETn at these
corners.** It is not a `.meas` window or threshold problem (b): RESETn never
leaves the supply band after 19.9 ms, its minimum is 0.99993 V against the
0.3 V threshold, and the final value is 2.97 V. The `.meas` cards are correct;
there is no crossing to find.

The 8 corners are the ones the older schematic-only records already list as
`ERROR` (`sim/por-brownout/records/20260811-112115-9807e3f.md` and
`20260811-210509-4cf7113.md`): `tt`, `ss`, `res_ff`, `res_ss`, `bjt_ff`,
`bjt_ss` at `V2.97 -40C`, plus `ss` at `V3.30 -40C` and `V2.97 27C`. They
predate the PEX run.

## Waveform (one corner, local `ngspice -b`)

Corner `ss+res_ss+bjt_ss+diode_ss+moscap_ss+mimcap_ss`, `V2.97`, `-40C`, the
staged `layout/reports/temp_por_top/pex-requests/por-brownout/req/T-40C_V2.97`
request cut to that one process corner, `klt sim --backend local`
(klayout-tools 0.8.0, ngspice-42). Times are relative to 20 ms.

| t | VDD | RESETn | POR_RAW | BIAS_OK | VREF | deglitch node `xpor.NDG` |
|---|---|---|---|---|---|---|
| 0 (pre-dip) | 2.970 | 2.970 | 2.970 | 2.970 | 1.200 | 0.000 |
| 4.6 us (in dip) | 1.000 | 1.015 | 1.000 | 1.000 | 0.811 | 0.000 |
| 25-51 us (in dip) | 1.000 | 1.000 | 1.000 | 1.000 | 0.638 -> 0.615 | 0.000 |
| 52.6 us (recovered) | 2.970 | 2.971 | 2.970 | 2.970 | 0.891 | 0.036 |
| 53.5-64.8 us | 2.970 | 2.970 | **0.000** | 2.970 | 1.44 -> 1.14 | 0.067 -> 0.340 |
| 69.7 us | 2.970 | 2.970 | 2.970 | 2.970 | 1.155 | 0.371 (peak) |
| 84.7 us onward | 2.970 | 2.970 | 2.970 | 2.970 | 1.19 -> 1.20 | 0.000 |

1. During the 50 us dip POR_RAW and BIAS_OK follow the rail high. With the
   1 us edge the comparator never asserts in the dip, which is the known
   clause-(c) behaviour recorded in the bench header and in
   `sim/por-brownout/control/results.md` part E.
2. After the rail recovers, VREF overshoots and POR_RAW asserts once, for about
   16 us (53.5 to 69.7 us), then releases.
3. That 16 us pulse is shorter than the deglitch dwell at this corner
   (6.14-23.11 us across the grid, per the bench header), so the deglitch node
   peaks at 0.371 V and discharges. RESETn never falls. `treassert`, `trel2`
   and `trel2_last` have nothing to cross, hence `out of interval`.

Where the schematic does re-assert (the other 73 corners) it is this same
post-recovery pulse, 52.0-66.2 us after the dip start, and it is long enough to pass
the deglitch. These eight corners are the ones where it is not. The extracted
leg re-asserts at all eight (`t_reassert_us` 51.9-52.0 us) because the drawn
interconnect shifts the recovery timing; that is a real schematic/extracted
disagreement on a race the ratified clause-(c) envelope does not cover.

## `set wnflag=1`

The committed `ngspice_init` no longer carries `set wnflag=1`. Running the same
corner with `set wnflag=1` added to `.control` gives a byte-identical `wrdata`
waveform (`cmp` equal, 4120 points) and the same three `out of interval`
errors. It does not change the result.

## Outcome

A documented finding, not a bench fix. The deck's 1 us dip edge violates
clause (c) by about 1000x on purpose, so a re-assertion on recovery is
incidental rather than something the deck claims. The assembly-level evidence
that a dip meeting all three clauses re-asserts is `sim/por-brownout-slew/`
(2.30 mV/us rung). The 48 rows therefore stay as reported and the item 7
grade is unchanged (`unmet`/`check_failed`): re-running would reproduce them.
Widening the `.meas` window cannot help, and relaxing a spec row is out of scope.

## Reproduce

```
source <(python3 sim/run_corners.py --print-env)
# cut layout/reports/temp_por_top/pex-requests/por-brownout/req/T-40C_V2.97 to
# its ss+res_ss+bjt_ss+diode_ss+moscap_ss+mimcap_ss process corner, then
uvx --from "klayout-tools==0.8.0" klt sim request.json -o out --backend local --format json
```

Add `wrdata f.dat v(vdd) v(resetn) v(xdut.por_raw) v(xdut.bias_ok) v(xdut.vref)
v(xdut.xpor.ndg)` before `quit` in the emitted `corner.cir` to get the waveform.

## Tool gap

`measure.py` can only hand `klt pex` `name`/`value`/`status`, so the errored
rows read `no diagnostic was recorded for this errored row` although the
`klt sim` report says `produced no value -- ngspice reported: out of interval`.
Filed as 2AMLogic/klayout-tools#4555.
