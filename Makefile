# gf180-temp-por -- top-level entry points for independent verification.
#
# Written for the Chipalooza design-review bar (2AMLogic/2am#542): "It must
# be possible for me to independently run simulations to verify the
# performance of the circuit [...] in the form of a shell script or a
# Makefile target such that full characterization can be done from a single
# command-line command." See README.md's "Independent verification
# (Chipalooza)" section for prerequisites, expected wall-clock, and how
# these targets map onto the evidence sim/ produces.
#
# All three targets are thin wrappers over the existing sim/ harness
# (sim/README.md, sim/harness/README.md are the authoritative conventions;
# nothing here reinvents them) and exit non-zero on any failure -- standard
# `make` behavior: a recipe line's non-zero exit aborts the target.
#
#   make check         unit tests + environment/PDK check (headless, seconds)
#   make smoke         fast end-to-end proof the toolchain works (seconds)
#   make characterize  full PVT/Monte-Carlo campaign, writes sim/ evidence
#
# Run from the repository root.

.DEFAULT_GOAL := help
.PHONY: help check smoke characterize

help:
	@echo "gf180-temp-por -- make targets:"
	@echo ""
	@echo "  make check         unit tests + environment/PDK check (headless, seconds)"
	@echo "  make smoke         fast end-to-end proof the toolchain works (seconds)"
	@echo "  make characterize  full PVT/Monte-Carlo campaign -> sim/*/records/ (dozens of minutes, host-dependent)"
	@echo ""
	@echo "See README.md's 'Independent verification (Chipalooza)' section for"
	@echo "prerequisites and what each target actually runs."

# Unit tests + a staleness check + an explicit environment/PDK report.
# Nothing here needs ngspice or the PDK except the last step, which reports
# (and fails loudly on) their absence rather than letting `make smoke` or
# `make characterize` fail later with a less specific error.
check:
	@echo "== sim/build_tb.py --check (testbench fragments match design/netlist/ exports) =="
	python3 sim/build_tb.py --check
	@echo
	@echo "== sim/tests (harness unit tests, no PDK required) =="
	python3 -m unittest discover -s sim/tests -t sim/tests
	@echo
	@echo "== layout/tests (layout-tooling unit tests, no PDK/klt required) =="
	python3 -m unittest discover -s layout/tests -t layout/tests
	@echo
	@echo "== environment / PDK check =="
	python3 sim/run_corners.py --check-env

# The harness's own acceptance test: harness unit tests, an environment
# report, and a full-PVT-grid run of sim/smoke-bias (three small, real
# gf180mcu device families -- an ideal divider, a poly resistor + nfet, and
# the same vertical-PNP diode the sensing core's CTAT leg is built from).
# Not "one corner": the harness's own checks (sim/harness/README.md,
# "harness-integrity check") are grid-scoped by construction, so a literal
# single-PVT-point run of any real testbench here trips a false failure
# (not enough measurement spread to prove the corner/temperature axes
# actually took effect) rather than proving anything. sim/smoke-bias's full
# 81-point grid runs in about a second, which is "fast" by any reading of
# the acceptance bar without that false-failure trap.
smoke:
	bash sim/selftest.sh

# The full campaign behind docs/chipalooza/challenge-3-proposal.md's spec
# table: every schematic-level PVT-grid and Monte Carlo experiment
# discovered under sim/*/testbench/, each run with its manifest's own
# defaults (full 81-point grid, or full N>=500 Monte Carlo sweep). See
# sim/characterize.py's module docstring for exactly what does and does not
# run (schematic-level only; testbench-postlayout/ re-runs are a separate,
# already-recorded effort triggered by a layout change, not by this target).
characterize:
	python3 sim/characterize.py
