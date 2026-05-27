# v0.1 run archive — Shanghai 6-zone, 2020–2060

Snapshot of the first end-to-end solve following Phase E.4 (GEM unit-level +
3 Sichuan UHV + imported_power activation, commit `0147162`).

## Run metadata

- **Date:** 2026-05-27
- **Inputs commit at solve time:** `fd6b081` (validate_scenario.py Windows fix)
- **Solver:** HiGHS via `appsi_highs`, `solver=ipm run_crossover=off`, no time limit
- **Wall time:** 2339 s (~39 min); model construct 37 s; LP solve 2258 s; post-solve 41 s
- **Termination:** **optimal**
- **Total NPV cost:** $2.256 trillion (2020 USD discounting)
- **LCOE range:** $58–66/MWh (2020 → 2060)
- **Construction warnings:** 124 VRE projects with capacity-factor data outside operating windows; 14 GEM hydro plants similarly. Both benign per upstream `switch_model` semantics.

## Files in this archive

| File | What it captures |
|---|---|
| `total_cost.txt` | Single scalar NPV |
| `electricity_cost.csv` | Per-period system cost + LCOE |
| `emissions.csv` | Per-period tCO2, carbon cap, shadow price |
| `cost_components.csv` | NPV decomposition (capex / fuel / O&M / etc.) |
| `gen_cap.csv` | Per-project installed capacity each period |
| `gen_build.csv` | Per-project new-build decisions each period |
| `dispatch_zonal_annual_summary.csv` | Generation by tech × zone × period |
| `transmission.csv` | UHV / inter-provincial line flows |
| `model_config.json` | Module list + solver options used |
| `solve.log` | Stream-solver log |

Full dispatch / commit / storage outputs (~150 MB) live in
`scenarios/shanghai/outputs/` (gitignored) — re-solve to regenerate.

## Headline finding: v0.0 over-build-coal **NOT fixed** by E.4

Capacity by technology, 6-zone aggregate (MW):

| Tech | 2020 | 2025 | 2030 | 2045 | 2060 |
|---|---|---|---|---|---|
| EP_Coal_1000_OT (GEM existing) | 241,368 | **285,152** | 283,322 | 232,920 | 43,784 |
| **Coal_1000_OT** (model new) | 927 | 6,122 | 13,238 | 54,051 | **101,294** |
| **Coal_1000_RC** (model new) | 0 | 2,354 | 10,801 | 31,634 | **36,323** |
| Nuclear_SEA (new) | 15,391 | 80,199 | 136,089 | 368,874 | **485,320** |
| Nuclear_EP_SEA | 26,717 | 36,991 | 36,991 | 33,905 | 10,274 |
| Hydro_NonPumped | 88,130 | 98,114 | 100,514 | 100,514 | 100,351 |
| Hydro_Pumped | 23,510 | 40,085 | 51,085 | 51,085 | 51,005 |
| Wind (new) | 0 | 0 | 0 | 11,932 | 55,250 |
| **Central_PV** (new) | **0** | **0** | **0** | **0** | **0** |
| Central_PV_EP | 44,042 | 56,346 | 56,333 | 0 | 0 |
| Battery_Storage | 0 | 0 | 0 | 0 | 11,676 |
| Offshore_Wind | 21,288 | 22,298 | 22,298 | 21,840 | 0 |

By 2060 the model adds **137.6 GW new coal** (101 OT + 36 RC) and **485 GW nuclear**, with zero new utility PV — completely opposite of the real-world decarbonization path.

## Root cause analysis (post-mortem)

| # | Cause | Evidence | Fix path |
|---|---|---|---|
| **A** | `total_capacity_limits.csv` empty | Header-only file; no Uranium / Coal cap | Populate per `docs/cap_assumptions.md` |
| **B** | Cost trajectories flat 2020→2060 | Central_PV stuck at $1.2M/MW for all build_years; same for Coal, Nuclear | Apply BNEF/WoodMac learning curves to `gen_build_costs.csv` |
| C | PV CF mildly low | Shanghai/Jiangsu PV CF 0.10–0.12 vs real-world ~0.14 | Refresh `variable_capacity_factors.csv` from solar resource data |

**Note:** initial hypothesis that costs were "1000× too high" was wrong —
SWITCH's `gen_overnight_cost` is in `$/MW` not `$/kW` (see
`switch_model/generators/core/build.py` lines 193–216). The numbers in
`gen_build_costs.csv` are correct in level; their flatness over time is
the actual problem. `docs/data_requirements.md` had the wrong unit label.

## Next step (v0.2 target)

Apply fix **A** (cap Uranium + Coal per EF judgment, see
`docs/cap_assumptions.md`) and re-solve. If post-cap result still
under-builds VRE, escalate to fix **B** (cost learning curves).
