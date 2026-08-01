v {xschem version=3.4.7 file_version=1.2}
G {}
K {}
V {}
S {}
E {}
T {por_output_chain -- deglitch, reset-pulse one-shot, push-pull output (issue #12)} -1400 -1500 0 0 0.6 0.6 {}
T {Topology per DR-004 / DR-005. POR_RAW (raw, hysteretic threshold decision from\npor_comparator, #10) -> deglitch dwell -> >=1 ms one-shot -> push-pull RESETn.\n\nPOLARITY CONVENTION (this cell defines it; #10 must match): POR_RAW is ACTIVE\nHIGH = \"rail is above VPOR and the comparator decision is authoritative\". Low, or\nundriven-low below the comparator floor, means \"not good\" -- the fail-safe sense,\nbecause RESETn must degrade to ASSERTED near 0 V (DR-004).\n\nSizing rationale, Iq budget and the corner numbers: design/por_output_chain.md.\nEvidence: sim/por-output-chain-pulse/, sim/por-output-chain-deglitch/,\nsim/por-output-chain-floor/.\n\nInterface contract (unchanged from the #29 stub):\n  VDD/VSS  3.3 V core-flavour supply pair (DR-001)\n  IBIAS    bias-mirror node from bias_core (#11). Convention as in temp_core:\n           bias_core SOURCES 0.5 uA into this pin; XMBD is the local mirror\n           diode. Every internal current is a ratio of it, so the pulse width\n           and the deglitch dwell scale as 1/IBIAS -- see the tolerance study\n           in design/por_output_chain.md.\n  POR_RAW  input, active high (see above).\n  RESETn   output, active low, push-pull (DR-004). Held low from 0 V up through\n           the comparator floor by the startup-assist path, which is NOT gated\n           by POR_RAW.} -1400 -1440 0 0 0.3 0.3 {}
N -1400 -1000 -1340 -1000 {}
C {devices/iopin.sym} -1400 -1000 0 0 {name=p_vdd lab=VDD}
N -1400 -940 -1340 -940 {}
C {devices/iopin.sym} -1400 -940 0 0 {name=p_vss lab=VSS}
N -1400 -880 -1340 -880 {}
C {devices/ipin.sym} -1400 -880 0 0 {name=p_ibias lab=IBIAS}
N -1400 -820 -1340 -820 {}
C {devices/ipin.sym} -1400 -820 0 0 {name=p_por_raw lab=POR_RAW}
N -1400 -760 -1340 -760 {}
C {devices/opin.sym} -1400 -760 0 0 {name=p_resetn lab=RESETn}
T {BIAS  --  local mirror off IBIAS, then a 10 nA PMOS leg (PDN) and a 10 nA NMOS leg (NDL).} -1400 -120 0 0 0.4 0.4 {}
T {Two cascaded 1:50 / 1:1 stages instead of one 1:200 mirror: every ratio pair below shares\nL = 10 um, so the nA references track over corners far better than a single long-L mirror\nagainst the 4u/4u IBIAS diode would. Standing draw from VDD is the two 10 nA legs; every\nother branch in this cell is a switched tail that conducts only while a node is slewing.} -1400 -90 0 0 0.3 0.3 {}
N -980 -30 -980 -70 {}
C {devices/lab_pin.sym} -980 -70 0 0 {name=l1 lab=IBIAS}
N -1020 0 -1080 0 {}
C {devices/lab_pin.sym} -1080 0 0 0 {name=l2 lab=IBIAS}
N -980 30 -980 70 {}
C {devices/lab_pin.sym} -980 70 0 0 {name=l3 lab=VSS}
N -980 0 -930 0 {}
C {devices/lab_pin.sym} -930 0 0 0 {name=l4 lab=VSS}
C {symbols/nfet_03v3.sym} -1000 0 0 0 {name=MBD
L=4u
W=4u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -740 -30 -740 -70 {}
C {devices/lab_pin.sym} -740 -70 0 0 {name=l5 lab=PDN}
N -780 0 -840 0 {}
C {devices/lab_pin.sym} -840 0 0 0 {name=l6 lab=IBIAS}
N -740 30 -740 70 {}
C {devices/lab_pin.sym} -740 70 0 0 {name=l7 lab=VSS}
N -740 0 -690 0 {}
C {devices/lab_pin.sym} -690 0 0 0 {name=l8 lab=VSS}
C {symbols/nfet_03v3.sym} -760 0 0 0 {name=MN1
L=25u
W=0.5u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -500 -30 -500 -70 {}
C {devices/lab_pin.sym} -500 -70 0 0 {name=l9 lab=VDD}
N -540 0 -600 0 {}
C {devices/lab_pin.sym} -600 0 0 0 {name=l10 lab=PDN}
N -500 30 -500 70 {}
C {devices/lab_pin.sym} -500 70 0 0 {name=l11 lab=PDN}
N -500 0 -450 0 {}
C {devices/lab_pin.sym} -450 0 0 0 {name=l12 lab=VDD}
C {symbols/pfet_03v3.sym} -520 0 0 0 {name=MPD
L=10u
W=2u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -260 -30 -260 -70 {}
C {devices/lab_pin.sym} -260 -70 0 0 {name=l13 lab=VDD}
N -300 0 -360 0 {}
C {devices/lab_pin.sym} -360 0 0 0 {name=l14 lab=PDN}
N -260 30 -260 70 {}
C {devices/lab_pin.sym} -260 70 0 0 {name=l15 lab=NDL}
N -260 0 -210 0 {}
C {devices/lab_pin.sym} -210 0 0 0 {name=l16 lab=VDD}
C {symbols/pfet_03v3.sym} -280 0 0 0 {name=MP2
L=10u
W=2u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -20 -30 -20 -70 {}
C {devices/lab_pin.sym} -20 -70 0 0 {name=l17 lab=NDL}
N -60 0 -120 0 {}
C {devices/lab_pin.sym} -120 0 0 0 {name=l18 lab=NDL}
N -20 30 -20 70 {}
C {devices/lab_pin.sym} -20 70 0 0 {name=l19 lab=VSS}
N -20 0 30 0 {}
C {devices/lab_pin.sym} 30 0 0 0 {name=l20 lab=VSS}
C {symbols/nfet_03v3.sym} -40 0 0 0 {name=MND
L=10u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
T {DEGLITCH  --  current-starved inverter (50 nA tails) into CDG, then two restoring inverters.} -1400 140 0 0 0.4 0.4 {}
T {This is DR-005's time-domain glitch rejection, entirely separate from the comparator's static\nhysteresis (#10): NDG has to traverse CDG at I/C before XMG1P/XMG1N flip, so a POR_RAW excursion\nshorter than the dwell never reaches PGDG. The dwell that matters for por-brownout is the\nPOR_RAW-falling one (NDG rising, XMDGPT charging CDG) -- it must stay <= 10 us at SS/-40 C so a\nqualifying >=10 us dip still re-asserts reset.\n\nXMG1P/XMG1N and XMG2P/XMG2N are deliberately ratio-skewed (weak PMOS + strong NMOS, then the\nmirror image). That skew is not about speed: it is what fixes each node's LEAKAGE default while\nthe bias core is dead below the comparator floor. POR_RAW low -> NDG high -> PGDG low -> PGDGB\nhigh, which grounds the timer node and leaves the NAND's PMOS pull-ups on. See the OUTPUT note.\n\nCDG SIZING IS TWO-SIDED, WHICH IS WHY IT IS 11u x 11u AND NOT SMALLER. Upper bound: the\nfalling dwell must stay under T_dip,min = 10 us at the SLOWEST point of the IBIAS envelope,\nand it scales as 1/IBIAS -- measured 4.58 us at ss/-40 C/3.63 V at nominal 0.5 uA, 8.88 us at\nhalf that current. Lower bound: a dwell only marginally longer than the glitch it is meant to\nreject does not reject it. The first cut of this cell used 7u x 7u (98 fF), giving a 1.07 us\ndwell at ff/+125 C -- against which a 1 us POR_RAW glitch propagated straight through to PGDG\n(75 mV) and restarted the timer at 30 of the 81 PVT points. 11u x 11u (242 fF) puts the\nSHORTEST dwell anywhere on the grid at 1.86 us, and the same 1 us glitch then moves PGDG by\n<40 mV everywhere. The two bounds are only ~3x apart (the dwell's own PVT x IBIAS spread), so\nthis capacitor is not free to grow: see design/por_output_chain.md, "Deglitch dwell".} -1400 170 0 0 0.3 0.3 {}
N -980 230 -980 190 {}
C {devices/lab_pin.sym} -980 190 0 0 {name=l21 lab=VDD}
N -1020 260 -1080 260 {}
C {devices/lab_pin.sym} -1080 260 0 0 {name=l22 lab=PDN}
N -980 290 -980 330 {}
C {devices/lab_pin.sym} -980 330 0 0 {name=l23 lab=NDGP}
N -980 260 -930 260 {}
C {devices/lab_pin.sym} -930 260 0 0 {name=l24 lab=VDD}
C {symbols/pfet_03v3.sym} -1000 260 0 0 {name=MDGPT
L=10u
W=10u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -740 230 -740 190 {}
C {devices/lab_pin.sym} -740 190 0 0 {name=l25 lab=NDGP}
N -780 260 -840 260 {}
C {devices/lab_pin.sym} -840 260 0 0 {name=l26 lab=POR_RAW}
N -740 290 -740 330 {}
C {devices/lab_pin.sym} -740 330 0 0 {name=l27 lab=NDG}
N -740 260 -690 260 {}
C {devices/lab_pin.sym} -690 260 0 0 {name=l28 lab=VDD}
C {symbols/pfet_03v3.sym} -760 260 0 0 {name=MDGPI
L=0.5u
W=1u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -500 230 -500 190 {}
C {devices/lab_pin.sym} -500 190 0 0 {name=l29 lab=NDG}
N -540 260 -600 260 {}
C {devices/lab_pin.sym} -600 260 0 0 {name=l30 lab=POR_RAW}
N -500 290 -500 330 {}
C {devices/lab_pin.sym} -500 330 0 0 {name=l31 lab=NDGN}
N -500 260 -450 260 {}
C {devices/lab_pin.sym} -450 260 0 0 {name=l32 lab=VSS}
C {symbols/nfet_03v3.sym} -520 260 0 0 {name=MDGNI
L=0.5u
W=1u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -260 230 -260 190 {}
C {devices/lab_pin.sym} -260 190 0 0 {name=l33 lab=NDGN}
N -300 260 -360 260 {}
C {devices/lab_pin.sym} -360 260 0 0 {name=l34 lab=NDL}
N -260 290 -260 330 {}
C {devices/lab_pin.sym} -260 330 0 0 {name=l35 lab=VSS}
N -260 260 -210 260 {}
C {devices/lab_pin.sym} -210 260 0 0 {name=l36 lab=VSS}
C {symbols/nfet_03v3.sym} -280 260 0 0 {name=MDGNT
L=10u
W=10u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -40 230 -40 190 {}
C {devices/lab_pin.sym} -40 190 0 0 {name=l37 lab=NDG}
N -40 290 -40 330 {}
C {devices/lab_pin.sym} -40 330 0 0 {name=l38 lab=VSS}
C {symbols/cap_mim_analog.sym} -40 260 0 0 {name=CDG
W=11u
L=11u
model=cap_mim_2f0_m3m4_noshield
spiceprefix=X
m=1}
N 220 230 220 190 {}
C {devices/lab_pin.sym} 220 190 0 0 {name=l39 lab=VDD}
N 180 260 120 260 {}
C {devices/lab_pin.sym} 120 260 0 0 {name=l40 lab=NDG}
N 220 290 220 330 {}
C {devices/lab_pin.sym} 220 330 0 0 {name=l41 lab=PGDG}
N 220 260 270 260 {}
C {devices/lab_pin.sym} 270 260 0 0 {name=l42 lab=VDD}
C {symbols/pfet_03v3.sym} 200 260 0 0 {name=MG1P
L=2u
W=0.5u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N 460 230 460 190 {}
C {devices/lab_pin.sym} 460 190 0 0 {name=l43 lab=PGDG}
N 420 260 360 260 {}
C {devices/lab_pin.sym} 360 260 0 0 {name=l44 lab=NDG}
N 460 290 460 330 {}
C {devices/lab_pin.sym} 460 330 0 0 {name=l45 lab=VSS}
N 460 260 510 260 {}
C {devices/lab_pin.sym} 510 260 0 0 {name=l46 lab=VSS}
C {symbols/nfet_03v3.sym} 440 260 0 0 {name=MG1N
L=0.5u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N 700 230 700 190 {}
C {devices/lab_pin.sym} 700 190 0 0 {name=l47 lab=VDD}
N 660 260 600 260 {}
C {devices/lab_pin.sym} 600 260 0 0 {name=l48 lab=PGDG}
N 700 290 700 330 {}
C {devices/lab_pin.sym} 700 330 0 0 {name=l49 lab=PGDGB}
N 700 260 750 260 {}
C {devices/lab_pin.sym} 750 260 0 0 {name=l50 lab=VDD}
C {symbols/pfet_03v3.sym} 680 260 0 0 {name=MG2P
L=0.5u
W=2u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N 940 230 940 190 {}
C {devices/lab_pin.sym} 940 190 0 0 {name=l51 lab=PGDGB}
N 900 260 840 260 {}
C {devices/lab_pin.sym} 840 260 0 0 {name=l52 lab=PGDG}
N 940 290 940 330 {}
C {devices/lab_pin.sym} 940 330 0 0 {name=l53 lab=VSS}
N 940 260 990 260 {}
C {devices/lab_pin.sym} 990 260 0 0 {name=l54 lab=VSS}
C {symbols/nfet_03v3.sym} 920 260 0 0 {name=MG2N
L=2u
W=0.5u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
T {ONE-SHOT TIMER  --  2.5 nA into 6.3 pF, gated by the deglitched power-good.} -1400 400 0 0 0.4 0.4 {}
T {A fixed >=1 ms pulse inside a sub-uA budget rules out an RC (1 ms into a 6 pF cap needs a\n~160 Mohm resistor -- unbuildable here), so the pulse is a current-starved ramp: XMPT sources\n~2.5 nA, XMTSW admits it only while PGDG is high, and XMDIS slams TIM back to VSS the moment\nPGDG falls -- which is what regenerates the FULL pulse after a brownout (por-brownout).\nXMDIS is 1u/1u, not wide: at FF/+125 C a wide device's own Ioff would be a sizeable fraction\nof the 2.5 nA charging current and the timer would never finish.} -1400 430 0 0 0.3 0.3 {}
N -980 490 -980 450 {}
C {devices/lab_pin.sym} -980 450 0 0 {name=l55 lab=VDD}
N -1020 520 -1080 520 {}
C {devices/lab_pin.sym} -1080 520 0 0 {name=l56 lab=PDN}
N -980 550 -980 590 {}
C {devices/lab_pin.sym} -980 590 0 0 {name=l57 lab=NTS}
N -980 520 -930 520 {}
C {devices/lab_pin.sym} -930 520 0 0 {name=l58 lab=VDD}
C {symbols/pfet_03v3.sym} -1000 520 0 0 {name=MPT
L=10u
W=0.5u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -740 490 -740 450 {}
C {devices/lab_pin.sym} -740 450 0 0 {name=l59 lab=NTS}
N -780 520 -840 520 {}
C {devices/lab_pin.sym} -840 520 0 0 {name=l60 lab=PGDGB}
N -740 550 -740 590 {}
C {devices/lab_pin.sym} -740 590 0 0 {name=l61 lab=TIM}
N -740 520 -690 520 {}
C {devices/lab_pin.sym} -690 520 0 0 {name=l62 lab=VDD}
C {symbols/pfet_03v3.sym} -760 520 0 0 {name=MTSW
L=1u
W=2u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -500 490 -500 450 {}
C {devices/lab_pin.sym} -500 450 0 0 {name=l63 lab=TIM}
N -540 520 -600 520 {}
C {devices/lab_pin.sym} -600 520 0 0 {name=l64 lab=PGDGB}
N -500 550 -500 590 {}
C {devices/lab_pin.sym} -500 590 0 0 {name=l65 lab=VSS}
N -500 520 -450 520 {}
C {devices/lab_pin.sym} -450 520 0 0 {name=l66 lab=VSS}
C {symbols/nfet_03v3.sym} -520 520 0 0 {name=MDIS
L=1u
W=1u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -280 490 -280 450 {}
C {devices/lab_pin.sym} -280 450 0 0 {name=l67 lab=TIM}
N -280 550 -280 590 {}
C {devices/lab_pin.sym} -280 590 0 0 {name=l68 lab=VSS}
C {symbols/cap_mim_analog.sym} -280 520 0 0 {name=CTIM
W=28u
L=28u
model=cap_mim_2f0_m3m4_noshield
spiceprefix=X
m=4}
T {CTIM: 4 x 28u x 28u MIM = 6.27 pF (2 fF/um2)} -340 620 0 0 0.3 0.3 {}
T {CDG: 11u x 11u MIM = 242 fF (2 fF/um2)} -100 360 0 0 0.3 0.3 {}
T {TRIP DETECTOR  --  two nA-limited current comparators, NOT starved inverters.} -1400 660 0 0 0.4 0.4 {}
T {TIM ramps at ~0.5 V/ms, so anything with a CMOS inverter's crowbar here would sit in its own\nhigh-gain region for hundreds of microseconds and burn far more than the whole por-iq budget.\nEach stage is therefore a single transistor against a nA current source: the through-current is\nhard-bounded at the source value (~2.5 nA) no matter how slow the input is, and the stage's own\nvoltage gain compresses the transition so the ordinary logic downstream sees a clean edge.\n\nWHY STAGE A IS A PMOS AND NOT A STARVED INVERTER (this is the load-bearing sizing decision).\nA starved inverter -- two matched tails around a CMOS pair -- has no defined trip point when\nthe input is a slow ramp: the pull-up stops winning when the input PMOS falls below the tail\ncurrent (TIM ~ VDD-|Vt|) and the pull-down starts winning when the input NMOS rises above it\n(TIM ~ Vtn), and between those two the node is indeterminate. Those are two DIFFERENT\nmechanisms with opposite tempcos, so the measured trip on the first cut of this cell ran from\n2.55 V at -40 C to 0.28 V at ff/+125 C -- a 9x pulse-width swing, and 0.57 ms at ff/125 C\nagainst a 1 ms floor. XMDAPI alone against the XMDANT sink has ONE mechanism: ND1 falls when\nthe PMOS can no longer supply 2.5 nA, i.e. at TIM = VDD - Vsg(2.5 nA). That trip is\nVDD-referenced with only a Vsg(T) correction, so the pulse width varies ~1.3x over the grid\ninstead of 9x, and it uses nearly the whole rail of ramp rather than the bottom half volt.\n\nConsequence worth stating plainly: because the trip is (VDD - Vsg) and not a fixed voltage,\nthe FASTEST-timer corner is the cold, low-rail one, not FF/+125 C/3.63 V as the spec row's\nparenthetical assumes for a generic current-starved one-shot. The >=1 ms check is applied at\nall 81 points regardless, so the claim does not depend on guessing the corner correctly.\n\nBelow-floor default: with the bias dead, XMDAPI has Vsg = VDD (on) against a sink whose gate\nis at NDL ~ 0 (off) and which is 40x smaller in W/L, so ND1 pins high; XMDBNI then has\nVgs = VDD against an off PMOS source 20x smaller, so TRIP pins low. TRIP low is what holds\nthe release NAND's output at VDD -- see the OUTPUT note. No static current in either state.} -1400 690 0 0 0.3 0.3 {}
N -980 750 -980 710 {}
C {devices/lab_pin.sym} -980 710 0 0 {name=l69 lab=VDD}
N -1020 780 -1080 780 {}
C {devices/lab_pin.sym} -1080 780 0 0 {name=l70 lab=TIM}
N -980 810 -980 850 {}
C {devices/lab_pin.sym} -980 850 0 0 {name=l71 lab=ND1}
N -980 780 -930 780 {}
C {devices/lab_pin.sym} -930 780 0 0 {name=l72 lab=VDD}
C {symbols/pfet_03v3.sym} -1000 780 0 0 {name=MDAPI
L=1u
W=2u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -740 750 -740 710 {}
C {devices/lab_pin.sym} -740 710 0 0 {name=l73 lab=ND1}
N -780 780 -840 780 {}
C {devices/lab_pin.sym} -840 780 0 0 {name=l74 lab=NDL}
N -740 810 -740 850 {}
C {devices/lab_pin.sym} -740 850 0 0 {name=l75 lab=VSS}
N -740 780 -690 780 {}
C {devices/lab_pin.sym} -690 780 0 0 {name=l76 lab=VSS}
C {symbols/nfet_03v3.sym} -760 780 0 0 {name=MDANT
L=10u
W=0.5u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -500 750 -500 710 {}
C {devices/lab_pin.sym} -500 710 0 0 {name=l77 lab=TRIP}
N -540 780 -600 780 {}
C {devices/lab_pin.sym} -600 780 0 0 {name=l78 lab=ND1}
N -500 810 -500 850 {}
C {devices/lab_pin.sym} -500 850 0 0 {name=l79 lab=VSS}
N -500 780 -450 780 {}
C {devices/lab_pin.sym} -450 780 0 0 {name=l80 lab=VSS}
C {symbols/nfet_03v3.sym} -520 780 0 0 {name=MDBNI
L=1u
W=1u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -260 750 -260 710 {}
C {devices/lab_pin.sym} -260 710 0 0 {name=l81 lab=VDD}
N -300 780 -360 780 {}
C {devices/lab_pin.sym} -360 780 0 0 {name=l82 lab=PDN}
N -260 810 -260 850 {}
C {devices/lab_pin.sym} -260 850 0 0 {name=l83 lab=TRIP}
N -260 780 -210 780 {}
C {devices/lab_pin.sym} -210 780 0 0 {name=l84 lab=VDD}
C {symbols/pfet_03v3.sym} -280 780 0 0 {name=MDBPT
L=10u
W=0.5u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
T {OUTPUT  --  release NAND + startup-assist keeper + push-pull driver.} -1400 920 0 0 0.4 0.4 {}
T {RESETn releases only when the timer has expired (TRIP) AND the deglitched rail is good (PGDG),\nso this cell -- not por_comparator -- owns the final gate (DR-005). A NAND, not a NOR, because\nthe below-floor assist depends on which way its leakage divider falls: a NAND's pull-up is two\nPARALLEL PMOS against a SERIES NMOS stack, so with both inputs at their dead-circuit default\n(low) RSTB is pinned to VDD by a divider that is ~30-80x in the PMOS's favour once the stack's\nown Ioff reduction is counted. RSTB = VDD turns XMON fully on and holds XMOP fully off, which\nIS the startup-assist pull-down of DR-004/DR-005 -- and it is not gated by POR_RAW.\n\nXMAST closes the loop: with RESETn low it latches RSTB high independently of TRIP/PGDG, so the\nassist survives even if the comparator drives POR_RAW high below its own floor. It is 0.5u/10u\nagainst a 2u/0.5u NAND stack (~40x), so the release still wins, and it draws nothing in either\nsettled state (RESETn high -> Vgs = 0).\n\nXMON/XMOP are 20:1 in W/L, not 1:1. The pull-up only has to move the 5 pF measurement load, but\nthe valid-low floor is a LEAKAGE-DIVIDER limit as VDD -> 0 (por-reset-valid-floor asks for\nV(RESETn) <= 0.1*VDD at every VDD, and the on/off ratio of a MOSFET vanishes as VDD -> 0), so\ngeometry has to supply the >=10x that biasing no longer can.} -1400 950 0 0 0.3 0.3 {}
N -980 1010 -980 970 {}
C {devices/lab_pin.sym} -980 970 0 0 {name=l85 lab=VDD}
N -1020 1040 -1080 1040 {}
C {devices/lab_pin.sym} -1080 1040 0 0 {name=l86 lab=TRIP}
N -980 1070 -980 1110 {}
C {devices/lab_pin.sym} -980 1110 0 0 {name=l87 lab=RSTB}
N -980 1040 -930 1040 {}
C {devices/lab_pin.sym} -930 1040 0 0 {name=l88 lab=VDD}
C {symbols/pfet_03v3.sym} -1000 1040 0 0 {name=MNAP1
L=0.5u
W=4u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -740 1010 -740 970 {}
C {devices/lab_pin.sym} -740 970 0 0 {name=l89 lab=VDD}
N -780 1040 -840 1040 {}
C {devices/lab_pin.sym} -840 1040 0 0 {name=l90 lab=PGDG}
N -740 1070 -740 1110 {}
C {devices/lab_pin.sym} -740 1110 0 0 {name=l91 lab=RSTB}
N -740 1040 -690 1040 {}
C {devices/lab_pin.sym} -690 1040 0 0 {name=l92 lab=VDD}
C {symbols/pfet_03v3.sym} -760 1040 0 0 {name=MNAP2
L=0.5u
W=4u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N -500 1010 -500 970 {}
C {devices/lab_pin.sym} -500 970 0 0 {name=l93 lab=RSTB}
N -540 1040 -600 1040 {}
C {devices/lab_pin.sym} -600 1040 0 0 {name=l94 lab=TRIP}
N -500 1070 -500 1110 {}
C {devices/lab_pin.sym} -500 1110 0 0 {name=l95 lab=NNAND}
N -500 1040 -450 1040 {}
C {devices/lab_pin.sym} -450 1040 0 0 {name=l96 lab=VSS}
C {symbols/nfet_03v3.sym} -520 1040 0 0 {name=MNAN1
L=0.5u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -260 1010 -260 970 {}
C {devices/lab_pin.sym} -260 970 0 0 {name=l97 lab=NNAND}
N -300 1040 -360 1040 {}
C {devices/lab_pin.sym} -360 1040 0 0 {name=l98 lab=PGDG}
N -260 1070 -260 1110 {}
C {devices/lab_pin.sym} -260 1110 0 0 {name=l99 lab=VSS}
N -260 1040 -210 1040 {}
C {devices/lab_pin.sym} -210 1040 0 0 {name=l100 lab=VSS}
C {symbols/nfet_03v3.sym} -280 1040 0 0 {name=MNAN2
L=0.5u
W=2u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
N -20 1010 -20 970 {}
C {devices/lab_pin.sym} -20 970 0 0 {name=l101 lab=VDD}
N -60 1040 -120 1040 {}
C {devices/lab_pin.sym} -120 1040 0 0 {name=l102 lab=RESETn}
N -20 1070 -20 1110 {}
C {devices/lab_pin.sym} -20 1110 0 0 {name=l103 lab=RSTB}
N -20 1040 30 1040 {}
C {devices/lab_pin.sym} 30 1040 0 0 {name=l104 lab=VDD}
C {symbols/pfet_03v3.sym} -40 1040 0 0 {name=MAST
L=10u
W=0.5u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N 220 1010 220 970 {}
C {devices/lab_pin.sym} 220 970 0 0 {name=l105 lab=VDD}
N 180 1040 120 1040 {}
C {devices/lab_pin.sym} 120 1040 0 0 {name=l106 lab=RSTB}
N 220 1070 220 1110 {}
C {devices/lab_pin.sym} 220 1110 0 0 {name=l107 lab=RESETn}
N 220 1040 270 1040 {}
C {devices/lab_pin.sym} 270 1040 0 0 {name=l108 lab=VDD}
C {symbols/pfet_03v3.sym} 200 1040 0 0 {name=MOP
L=1u
W=1u
nf=1
m=1
model=pfet_03v3
spiceprefix=X}
N 460 1010 460 970 {}
C {devices/lab_pin.sym} 460 970 0 0 {name=l109 lab=RESETn}
N 420 1040 360 1040 {}
C {devices/lab_pin.sym} 360 1040 0 0 {name=l110 lab=RSTB}
N 460 1070 460 1110 {}
C {devices/lab_pin.sym} 460 1110 0 0 {name=l111 lab=VSS}
N 460 1040 510 1040 {}
C {devices/lab_pin.sym} 510 1040 0 0 {name=l112 lab=VSS}
C {symbols/nfet_03v3.sym} 440 1040 0 0 {name=MON
L=0.5u
W=10u
nf=1
m=1
model=nfet_03v3
spiceprefix=X}
T {XMNAP1/2 + XMNAN1/2: release NAND      XMAST: startup-assist keeper      XMOP/XMON: push-pull driver} -1400 1140 0 0 0.3 0.3 {}
