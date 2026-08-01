v {xschem version=3.4.7 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {por_comparator -- POR threshold comparator with hysteresis (issue #10)} -300 -330 0 0 0.5 0.5 {}
T {Topology per DR-005: bandgap-referenced comparator against a resistor-divided
VDD tap, hysteresis from resistor-network positive feedback -- a static,
non-time-domain mechanism (deglitch is a separate, additional block owned by
por_output_chain, #12; #10 does not attempt to satisfy it here).

A three-segment ppolyf_u_3k string RTOP/RBOT/RHYS divides VDD; the SNS tap
(between RTOP and RBOT) is compared against VREF by an NMOS-input 5T OTA
(divider flavour per sim/devchar/SUMMARY.md's POR-divider recommendation,
input-pair polarity per the same document's comparator-input-pair
recommendation). POR_RAW feeds back into the DIVIDER RATIO: MHSW shorts RHYS
out while POR_RAW is low, so

  VPOR^ = VREF * (RTOP+RBOT)/RBOT            (reset asserted, RHYS shorted)
  VPORv = VREF * (RTOP+RBOT+RHYS)/(RBOT+RHYS) (released, RHYS in circuit)
  V_hys = VREF * RTOP*RHYS / (RBOT*(RBOT+RHYS))

Every one of those is VREF times a ratio of same-flavour, same-width
resistors, so sheet-rho corners and TC cancel in BOTH edges and in their
difference. Full sizing rationale, error budget and Iq budget:
design/por_comparator.md; PVT evidence: sim/por-comparator-designer-check/.

Interface contract (unchanged from the #10 stub, PR #29):
  VDD/VSS  3.3 V core-flavor supply pair (DR-001)
  IBIAS    bias-mirror node from bias_core (shared, DR-005). Convention
           matches temp_core: bias_core SOURCES 0.5 uA into this pin.
  VREF     reference voltage from bias_core (assumed ~1.2 V bandgap-scale,
           per SUMMARY.md; bias_core itself is still #11's placeholder, so
           this cell's threshold sizing is against that assumed value and
           will need a one-line reconciliation once #11 lands with a real
           number). SNS is compared against this, which is what makes the
           threshold an absolute voltage rather than a rail fraction.
  BIAS_OK  shared-core-valid flag. Gates NBG (kills the tail + hysteresis
           mirrors) and clamps CMPO to VSS when low, so POR_RAW reads a
           safe "not released" before the shared core is valid -- this
           cell's own authoritative-decision gate (DR-005 step 4), not
           the full startup-ordering AND with the pulse timer (#12's job).
  POR_RAW  raw threshold decision handed to por_output_chain. Active HIGH:
           1 means SNS >= VREF, i.e. VDD is above the (hysteretic) release
           threshold. Not the reset pin: hysteresis lives here, deglitch +
           pulse + output drive live in por_output_chain (DR-005 split).

Below the comparator's own operating floor POR_RAW is undefined by
construction -- see design/por_comparator.md, "Below the operating floor"
for what this schematic actually does there (measured, not just asserted).
Holding RESETn low in that regime is por_output_chain's job (DR-004).} -300 -300 0 0 0.3 0.3 {}
N -300 -200 -240 -200 {lab=VDD}
N -300 -140 -240 -140 {lab=VSS}
N -300 -80 -240 -80 {lab=IBIAS}
N -300 -20 -240 -20 {lab=VREF}
N -300 40 -240 40 {lab=BIAS_OK}
N 240 -200 300 -200 {lab=POR_RAW}
C {devices/iopin.sym} -300 -200 0 1 {name=p_vdd lab=VDD}
C {devices/iopin.sym} -300 -140 0 1 {name=p_vss lab=VSS}
C {devices/ipin.sym} -300 -80 0 0 {name=p_ibias lab=IBIAS}
C {devices/ipin.sym} -300 -20 0 0 {name=p_vref lab=VREF}
C {devices/ipin.sym} -300 40 0 0 {name=p_bias_ok lab=BIAS_OK}
C {devices/opin.sym} 300 -200 0 0 {name=p_por_raw lab=POR_RAW}
T {ENABLE + NBG BIAS GENERATION -- BIAS_OK/BIAS_OKB local inverter, and the
same MPASS/MBD/MDNB pattern design/temp_core.sch uses to derive a local NMOS
bias-mirror gate (NBG) off IBIAS, clamped to VSS whenever BIAS_OK is low.
MDIB additionally clamps the IBIAS PIN itself to VSS when disabled -- same
role as temp_core's own XMDIB: without it, a testbench (or a real system
moment where every IBIAS consumer disables at once) forcing current into a
pin with no live sink here has nowhere defined to go. Measured cost of
omitting it: sim/por-comparator-designer-check found tens of uA at ff/125 C
before this clamp was added -- see design/por_comparator.md.} -1100 -120 0 0 0.4 0.4 {}
N -980 -30 -980 -70 {}
C {devices/lab_pin.sym} -980 -70 0 0 {name=l1 lab=VDD}
N -1020 0 -1080 0 {}
C {devices/lab_pin.sym} -1080 0 0 0 {name=l2 lab=BIAS_OK}
N -980 30 -980 70 {}
C {devices/lab_pin.sym} -980 70 0 0 {name=l3 lab=BIAS_OKB}
N -980 0 -930 0 {}
C {devices/lab_pin.sym} -930 0 0 0 {name=l4 lab=VDD}
C {symbols/pfet_03v3.sym} -1000 0 0 0 {name=MENP
L=0.5u
W=2u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -740 -30 -740 -70 {}
C {devices/lab_pin.sym} -740 -70 0 0 {name=l5 lab=BIAS_OKB}
N -780 0 -840 0 {}
C {devices/lab_pin.sym} -840 0 0 0 {name=l6 lab=BIAS_OK}
N -740 30 -740 70 {}
C {devices/lab_pin.sym} -740 70 0 0 {name=l7 lab=VSS}
N -740 0 -690 0 {}
C {devices/lab_pin.sym} -690 0 0 0 {name=l8 lab=VSS}
C {symbols/nfet_03v3.sym} -760 0 0 0 {name=MENN
L=0.5u
W=1u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -500 -30 -500 -70 {}
C {devices/lab_pin.sym} -500 -70 0 0 {name=l9 lab=IBIAS}
N -540 0 -600 0 {}
C {devices/lab_pin.sym} -600 0 0 0 {name=l10 lab=NBG}
N -500 30 -500 70 {}
C {devices/lab_pin.sym} -500 70 0 0 {name=l11 lab=VSS}
N -500 0 -450 0 {}
C {devices/lab_pin.sym} -450 0 0 0 {name=l12 lab=VSS}
C {symbols/nfet_03v3.sym} -520 0 0 0 {name=MBD
L=2u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -260 -30 -260 -70 {}
C {devices/lab_pin.sym} -260 -70 0 0 {name=l13 lab=IBIAS}
N -300 0 -360 0 {}
C {devices/lab_pin.sym} -360 0 0 0 {name=l14 lab=BIAS_OK}
N -260 30 -260 70 {}
C {devices/lab_pin.sym} -260 70 0 0 {name=l15 lab=NBG}
N -260 0 -210 0 {}
C {devices/lab_pin.sym} -210 0 0 0 {name=l16 lab=VSS}
C {symbols/nfet_03v3.sym} -280 0 0 0 {name=MPASS
L=0.5u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -20 -30 -20 -70 {}
C {devices/lab_pin.sym} -20 -70 0 0 {name=l17 lab=NBG}
N -60 0 -120 0 {}
C {devices/lab_pin.sym} -120 0 0 0 {name=l18 lab=BIAS_OKB}
N -20 30 -20 70 {}
C {devices/lab_pin.sym} -20 70 0 0 {name=l19 lab=VSS}
N -20 0 30 0 {}
C {devices/lab_pin.sym} 30 0 0 0 {name=l20 lab=VSS}
C {symbols/nfet_03v3.sym} -40 0 0 0 {name=MDNB
L=0.5u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N 220 -30 220 -70 {}
C {devices/lab_pin.sym} 220 -70 0 0 {name=l83 lab=IBIAS}
N 180 0 120 0 {}
C {devices/lab_pin.sym} 120 0 0 0 {name=l84 lab=BIAS_OKB}
N 220 30 220 70 {}
C {devices/lab_pin.sym} 220 70 0 0 {name=l85 lab=VSS}
N 220 0 270 0 {}
C {devices/lab_pin.sym} 270 0 0 0 {name=l86 lab=VSS}
C {symbols/nfet_03v3.sym} 200 0 0 0 {name=MDIB
L=1u
W=1u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
T {SENSE DIVIDER + HYSTERESIS -- a three-segment ppolyf_u_3k string off VDD
(RTOP / RBOT / RHYS, all one flavour and one drawn width, so sheet-rho and TC
cancel in every ratio -- SUMMARY.md's POR-divider recommendation). MHSW shorts
RHYS out whenever POR_RAW is LOW (its gate is N1 = POR_RAW-bar), which is the
whole hysteresis mechanism:

  reset asserted (POR_RAW low, MHSW on):   SNS = VDD * RBOT/(RTOP+RBOT)
     -> VPOR^ = VREF * (RTOP+RBOT)/RBOT
  released      (POR_RAW high, MHSW off):  SNS = VDD * (RBOT+RHYS)/(RTOP+RBOT+RHYS)
     -> VPORv = VREF * (RTOP+RBOT+RHYS)/(RBOT+RHYS)

  V_hys = VREF * RTOP * RHYS / (RBOT * (RBOT+RHYS))

V_hys is therefore a pure ratio of same-flavour resistors times VREF: the
+/-25 % sheet-rho corner spread and the -1545 ppm/C TC of ppolyf_u_3k cancel
instead of multiplying through, which is what a current-injection ("I_HYS *
RTOP") hysteresis leg cannot do. See design/por_comparator.md, "Why the
hysteresis is a resistor ratio", for the measured before/after.

MHSW sits at the VSS end of the string on purpose: when it is on its source is
at VSS and its gate is at VDD, so it has full overdrive and no body effect, and
its Ron (~1 k) appears in series with RBOT as a ~0.03 % term. A switch placed
higher in the string would be gated at only Vgs = VDD - V(tap) and would go
soft exactly at the low-rail/SS/cold corner the release threshold binds at.} -1100 140 0 0 0.4 0.4 {}
N -1000 290 -1000 330 {}
C {devices/lab_pin.sym} -1000 330 0 0 {name=l21 lab=SNS}
N -1000 230 -1000 190 {}
C {devices/lab_pin.sym} -1000 190 0 0 {name=l22 lab=VDD}
N -1020 260 -1080 260 {}
C {devices/lab_pin.sym} -1080 260 0 0 {name=l23 lab=VSS}
C {symbols/ppolyf_u_3k.sym} -1000 260 0 0 {name=RTOP
W=2u
L=7897.44u
model=ppolyf_u_3k
spiceprefix=X
m=1}
N -760 290 -760 330 {}
C {devices/lab_pin.sym} -760 330 0 0 {name=l24 lab=SNSB}
N -760 230 -760 190 {}
C {devices/lab_pin.sym} -760 190 0 0 {name=l25 lab=SNS}
N -780 260 -840 260 {}
C {devices/lab_pin.sym} -840 260 0 0 {name=l26 lab=VSS}
C {symbols/ppolyf_u_3k.sym} -760 260 0 0 {name=RBOT
W=2u
L=6769.23u
model=ppolyf_u_3k
spiceprefix=X
m=1}
N -520 290 -520 330 {}
C {devices/lab_pin.sym} -520 330 0 0 {name=l91 lab=VSS}
N -520 230 -520 190 {}
C {devices/lab_pin.sym} -520 190 0 0 {name=l92 lab=SNSB}
N -540 260 -600 260 {}
C {devices/lab_pin.sym} -600 260 0 0 {name=l93 lab=VSS}
C {symbols/ppolyf_u_3k.sym} -520 260 0 0 {name=RHYS
W=2u
L=775.0u
model=ppolyf_u_3k
spiceprefix=X
m=1}
N -260 230 -260 190 {}
C {devices/lab_pin.sym} -260 190 0 0 {name=l94 lab=SNSB}
N -300 260 -360 260 {}
C {devices/lab_pin.sym} -360 260 0 0 {name=l95 lab=N1}
N -260 290 -260 330 {}
C {devices/lab_pin.sym} -260 330 0 0 {name=l96 lab=VSS}
N -260 260 -210 260 {}
C {devices/lab_pin.sym} -210 260 0 0 {name=l97 lab=VSS}
C {symbols/nfet_03v3.sym} -280 260 0 0 {name=MHSW
L=0.5u
W=10u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
T {COMPARATOR CORE -- NMOS diff pair (SNS, VREF), PMOS mirror load diode-
referenced on the SNS branch (NA) so CMPO tracks SNS positively (see
design/por_comparator.md for the derivation). MTAIL mirrors NBG at a 1:10
ratio for a ~50 nA tail. MENSRC gates the mirror's OWN VDD connection
(VDDA) with BIAS_OKB -- cutting the tail (MTAIL) alone is not enough to
silence this block when disabled: with CMPO clamped low by MDCMPO and VREF
still a live, always-present ~1.2 V input, MINB's *effective* source becomes
whichever of {TN, CMPO} is lower -- CMPO, once clamped -- so its Vgs is
measured against that clamp, not against TN, and it conducts hard regardless
of the (correctly off) tail. Measured before this fix: tens of uA at
ff/125 C with BIAS_OK low; see design/por_comparator.md, "Below the operating
floor" for the full story.} -1100 400 0 0 0.4 0.4 {}
N -980 490 -980 450 {}
C {devices/lab_pin.sym} -980 450 0 0 {name=l27 lab=TN}
N -1020 520 -1080 520 {}
C {devices/lab_pin.sym} -1080 520 0 0 {name=l28 lab=NBG}
N -980 550 -980 590 {}
C {devices/lab_pin.sym} -980 590 0 0 {name=l29 lab=VSS}
N -980 520 -930 520 {}
C {devices/lab_pin.sym} -930 520 0 0 {name=l30 lab=VSS}
C {symbols/nfet_03v3.sym} -1000 520 0 0 {name=MTAIL
L=10u
W=1u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -740 490 -740 450 {}
C {devices/lab_pin.sym} -740 450 0 0 {name=l31 lab=NA}
N -780 520 -840 520 {}
C {devices/lab_pin.sym} -840 520 0 0 {name=l32 lab=SNS}
N -740 550 -740 590 {}
C {devices/lab_pin.sym} -740 590 0 0 {name=l33 lab=TN}
N -740 520 -690 520 {}
C {devices/lab_pin.sym} -690 520 0 0 {name=l34 lab=VSS}
C {symbols/nfet_03v3.sym} -760 520 0 0 {name=MINA
L=1u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -500 490 -500 450 {}
C {devices/lab_pin.sym} -500 450 0 0 {name=l35 lab=CMPO}
N -540 520 -600 520 {}
C {devices/lab_pin.sym} -600 520 0 0 {name=l36 lab=VREF}
N -500 550 -500 590 {}
C {devices/lab_pin.sym} -500 590 0 0 {name=l37 lab=TN}
N -500 520 -450 520 {}
C {devices/lab_pin.sym} -450 520 0 0 {name=l38 lab=VSS}
C {symbols/nfet_03v3.sym} -520 520 0 0 {name=MINB
L=1u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -260 490 -260 450 {}
C {devices/lab_pin.sym} -260 450 0 0 {name=l39 lab=VDDA}
N -300 520 -360 520 {}
C {devices/lab_pin.sym} -360 520 0 0 {name=l40 lab=NA}
N -260 550 -260 590 {}
C {devices/lab_pin.sym} -260 590 0 0 {name=l41 lab=NA}
N -260 520 -210 520 {}
C {devices/lab_pin.sym} -210 520 0 0 {name=l42 lab=VDD}
C {symbols/pfet_03v3.sym} -280 520 0 0 {name=MLA
L=1u
W=4u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -20 490 -20 450 {}
C {devices/lab_pin.sym} -20 450 0 0 {name=l43 lab=VDDA}
N -60 520 -120 520 {}
C {devices/lab_pin.sym} -120 520 0 0 {name=l44 lab=NA}
N -20 550 -20 590 {}
C {devices/lab_pin.sym} -20 590 0 0 {name=l45 lab=CMPO}
N -20 520 30 520 {}
C {devices/lab_pin.sym} 30 520 0 0 {name=l46 lab=VDD}
C {symbols/pfet_03v3.sym} -40 520 0 0 {name=MLB
L=1u
W=4u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N 220 490 220 450 {}
C {devices/lab_pin.sym} 220 450 0 0 {name=l87 lab=VDD}
N 180 520 120 520 {}
C {devices/lab_pin.sym} 120 520 0 0 {name=l88 lab=BIAS_OKB}
N 220 550 220 590 {}
C {devices/lab_pin.sym} 220 590 0 0 {name=l89 lab=VDDA}
N 220 520 270 520 {}
C {devices/lab_pin.sym} 270 520 0 0 {name=l90 lab=VDD}
C {symbols/pfet_03v3.sym} 200 520 0 0 {name=MENSRC
L=0.5u
W=4u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
T {OUTPUT BUFFER + DISABLE CLAMP -- two inverting stages square CMPO up to a
rail-to-rail POR_RAW (even inversion count preserves polarity: CMPO high ==
POR_RAW high == release condition true). MDCMPO holds CMPO at VSS whenever
BIAS_OK is low, so POR_RAW reads a safe "not released" with no floating node
(the failure mode design/temp_core.md documents for its own disabled state).} -1100 660 0 0 0.4 0.4 {}
N -980 750 -980 710 {}
C {devices/lab_pin.sym} -980 710 0 0 {name=l47 lab=CMPO}
N -1020 780 -1080 780 {}
C {devices/lab_pin.sym} -1080 780 0 0 {name=l48 lab=BIAS_OKB}
N -980 810 -980 850 {}
C {devices/lab_pin.sym} -980 850 0 0 {name=l49 lab=VSS}
N -980 780 -930 780 {}
C {devices/lab_pin.sym} -930 780 0 0 {name=l50 lab=VSS}
C {symbols/nfet_03v3.sym} -1000 780 0 0 {name=MDCMPO
L=1u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -740 750 -740 710 {}
C {devices/lab_pin.sym} -740 710 0 0 {name=l51 lab=VDD}
N -780 780 -840 780 {}
C {devices/lab_pin.sym} -840 780 0 0 {name=l52 lab=CMPO}
N -740 810 -740 850 {}
C {devices/lab_pin.sym} -740 850 0 0 {name=l53 lab=N1}
N -740 780 -690 780 {}
C {devices/lab_pin.sym} -690 780 0 0 {name=l54 lab=VDD}
C {symbols/pfet_03v3.sym} -760 780 0 0 {name=MI1P
L=0.5u
W=2u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -500 750 -500 710 {}
C {devices/lab_pin.sym} -500 710 0 0 {name=l55 lab=N1}
N -540 780 -600 780 {}
C {devices/lab_pin.sym} -600 780 0 0 {name=l56 lab=CMPO}
N -500 810 -500 850 {}
C {devices/lab_pin.sym} -500 850 0 0 {name=l57 lab=VSS}
N -500 780 -450 780 {}
C {devices/lab_pin.sym} -450 780 0 0 {name=l58 lab=VSS}
C {symbols/nfet_03v3.sym} -520 780 0 0 {name=MI1N
L=0.5u
W=1u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -260 750 -260 710 {}
C {devices/lab_pin.sym} -260 710 0 0 {name=l59 lab=VDD}
N -300 780 -360 780 {}
C {devices/lab_pin.sym} -360 780 0 0 {name=l60 lab=N1}
N -260 810 -260 850 {}
C {devices/lab_pin.sym} -260 850 0 0 {name=l61 lab=POR_RAW}
N -260 780 -210 780 {}
C {devices/lab_pin.sym} -210 780 0 0 {name=l62 lab=VDD}
C {symbols/pfet_03v3.sym} -280 780 0 0 {name=MI2P
L=0.5u
W=2u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -20 750 -20 710 {}
C {devices/lab_pin.sym} -20 710 0 0 {name=l63 lab=POR_RAW}
N -60 780 -120 780 {}
C {devices/lab_pin.sym} -120 780 0 0 {name=l64 lab=N1}
N -20 810 -20 850 {}
C {devices/lab_pin.sym} -20 850 0 0 {name=l65 lab=VSS}
N -20 780 30 780 {}
C {devices/lab_pin.sym} 30 780 0 0 {name=l66 lab=VSS}
C {symbols/nfet_03v3.sym} -40 780 0 0 {name=MI2N
L=0.5u
W=1u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
T {No separate hysteresis-generation band: hysteresis is the RHYS/MHSW leg of the
sense divider above. That is DR-005's "resistor-network positive feedback" taken
literally -- POR_RAW feeds back into the divider ratio, not into a summing node --
and it is why V_hys has no I*R term to drag it across the resistor corners.} -1100 920 0 0 0.4 0.4 {}
