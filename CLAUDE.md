# gf180-temp-por — agent instructions

Canary block: a temperature sensor + power-on-reset pair on gf180mcu.
Apache-2.0.

- **PDK**: gf180mcu (open PDK). Open-source flow: xschem + ngspice for
  design/sim, klayout-tools (`klt`) for layout work.
- **Friction protocol (the canary's job)**: every time klayout-tools is
  awkward, missing a capability, or wrong for what you need, file an issue
  at `2AMLogic/klayout-tools` describing the need generically — describe
  the tool gap, not the design. A tool issue that only makes sense to
  someone who has read this repo's spec is a bad tool issue.
- **Verification is the product**: no claim without a testbench. PVT
  corners on every recorded result. `sim/` results are append-only
  evidence.
- **Publication**: this repo is prepared to be public (#25) — the
  visibility flip itself is an operator action, not an agent one. Write
  every commit message, issue, and document here as if a stranger will
  read it, because one will. Nothing about business positioning,
  commercial terms, or the contents of other 2AM Logic repositories
  belongs in this one.
- Spec changes go through `spec/` with a decision record; agents do not
  relax the ratified spec to make results pass.
- Harness bootstrap: copy the sim-harness pattern from
  `2AMLogic/gf180-bandgap` once it lands there rather than reinventing.

<!-- BEGIN LOOM ORCHESTRATION -->
This repository uses [Loom](https://github.com/rjwalters/loom) for AI-powered development orchestration — see the Loom repository for the full guide (roles, labels, worktrees, configuration). When installed, Loom also writes a locally-substituted copy of that guide to `.loom/CLAUDE.md`.
<!-- END LOOM ORCHESTRATION -->
<!-- BEGIN REPO-SKILLS -->
This repository has [Repo Skills](https://github.com/rjwalters/repo) v0.8.1 installed —
general repository hygiene and environment commands invoked as `/repo:<command>`. Run
`/repo:help` for the command list, or see `.claude/skills/repo/SKILL.md` for the full
guide. Hygiene commands apply safe, reversible fixes by default and report each
change; run with `--ask` to review first, and `--prune` to allow irreversible
removals. Managed by `install.sh` — edit outside the markers only.
<!-- END REPO-SKILLS -->
