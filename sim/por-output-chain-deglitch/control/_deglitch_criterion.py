"""Shared glitch-rejection verdict for this directory's #182 controls.

``run_glitch_width_sweep.py`` (the glitch-WIDTH sweep) and
``run_cdg_tradeoff.py`` (the ``CDG``-resize tradeoff) both reduce a run to the
same three-way verdict, and ``width_results.md`` / ``cdg_results.md`` both
publish it under the same ``rejected`` / ``partial`` / ``**through**`` names.
Before issue #493 each script carried its own copy of the function and of the
two fraction literals, with ``run_cdg_tradeoff.py``'s docstring *asserting*
the two were the same criterion -- so moving the 0.5 boundary in one file
would have left the two results files disagreeing about what "rejected"
means while that assertion still claimed they agreed. This module is the
single place the criterion and its boundaries are defined, rather than two
independently-maintained copies (the same consolidation as
``sim/por-brownout-slew/_rung_record.py``, #123, and ``sim/harness/cliutil.py``,
#135).

Nothing here runs a simulation or makes a measurement of its own: it only
reduces the ``timbefore`` / ``timafter`` scalars already parsed out of a run's
ngspice log.

Stdlib only, no virtualenv required.
"""

from __future__ import annotations

#: Fraction of the one-shot's pre-glitch ``TIM`` charge that must be lost for
#: the glitch to count as having come **through** the filter -- i.e. ``XMDIS``
#: conducted hard enough to set the reset pulse back past half its charge.
THROUGH_FRACTION = 0.5

#: Fraction above which the loss is material at all rather than numerical
#: noise on the measurement. Between this and ``THROUGH_FRACTION`` the glitch
#: was *partially* rejected.
PARTIAL_FRACTION = 0.01


def verdict(meas: dict[str, float]) -> str:
    """Did the glitch get through the filter?

    Functional criterion, not a voltage one: a glitch that reaches PGDG drives
    PGDGB high, fires XMDIS, and discharges the one-shot's TIM -- which is
    exactly what restarted the timer at 30/81 points in the historical
    CDG = 98 fF failure. TIM only ever *rises* while the filter is rejecting
    (XMPT is still charging it), so any material fall is XMDIS having
    conducted, and the size of the fall says how far the pulse was set back.
    PGDG merely drooping is not the failure; losing timer charge is.
    """
    lost = (meas["timbefore"] - meas["timafter"]) / meas["timbefore"]
    if lost > THROUGH_FRACTION:
        return "**through**"
    if lost > PARTIAL_FRACTION:
        return "partial"
    return "rejected"
