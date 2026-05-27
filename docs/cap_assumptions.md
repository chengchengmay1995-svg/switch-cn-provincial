# Capacity-cap assumptions (`total_capacity_limits.csv`)

This document records every assumption behind the values in
`scenarios/<province>/inputs/total_capacity_limits.csv`. The file caps
the **6-zone aggregate** installed capacity of a given `energy_source`
in a given period (sum across all `LOAD_ZONES` in the active model
instance — `tech_plans.py` enforces it via `Enforce_Total_Capacity_Limit`).

The cn_modules.tech_plans Set is **sparse**: rows that are absent
from the CSV mean "unconstrained in that (energy_source, period) cell".
We use this to leave late periods open where we deliberately want the
model to have freedom.

## Uranium (nuclear)

| Period | Cap (MW) | Source |
|---|---|---|
| 2025 | 37,000 | Matches v0.1 model's GEM-derived `Nuclear_EP_SEA` 2025 peak (existing + under-construction along ZJ/FJ/JS coast). No headroom for new builds in this period. |
| 2030 | 50,000 | 14/15 FYP path. Coastal new starts (Sanmen 3-4, Tianwan 7-8, Ningde 5-6, Fuqing 5-6, Zhangzhou 1-2). |
| 2035 | 65,000 | Mid-trajectory between 2030 anchor and CCETP 2060 estimate. |
| 2040+ | _unconstrained_ | **Deliberate** — per project owner guidance: "保持想象力，不要有太大的限制，除非有非常笃定的物理限制证据". No such evidence exists for sites > 2035 (coastal site inventory ~80-100 reactors potential; inland nuclear remains contested but not physically blocked). |

### Sources / reasoning trail

- 2024 actual operating: ZJ ~9 GW + FJ ~9 GW + JS ~5 GW = 23 GW (coast trio carries all operating capacity; AH/SC/SH have none)
- 2025 with under-construction: model's `Nuclear_EP_SEA` aggregates to 37 GW (= 14 GW under-construction coming online)
- CCETP 2060 carbon-neutral roadmap (Tsinghua iCET 2021): national 200-300 GW total nuclear by 2060
- 6-zone coastal share of national nuclear: historically ~100% (all national nuclear is in ZJ/FJ/JS/GD/HN/SD — our 6 zones = 80% of all coastal capacity)
- → 6-zone 2060 implied = 80% × 250 GW ≈ 200 GW, but **we don't cap 2060** (per owner guidance)

### Zone-level constraints

`total_capacity_limits.csv` is zone-blind. The model's geographic realism
comes from `gen_info.csv`: Shanghai has zero nuclear projects defined;
Sichuan and Anhui have only `Nuclear_SMR` options. Zhejiang/Fujian/Jiangsu
carry the bulk (29 of 31 projects). To tighten this further, set
per-project `gen_capacity_limit_mw` in `gen_info.csv` (currently all `.`).

## Coal

| Period | Cap (MW) | Source |
|---|---|---|
| 2025 | 320,000 | Existing 6-zone GEM fleet 286 GW + ~12% headroom for under-construction. Matches v0.1 model's `EP_Coal_1000_OT` 2025 = 285 GW. |
| 2030 | 400,000 | **Anchor — EF judgment.** 25% × national 1,550-1,600 GW peak (see below). |
| 2035+ | _unconstrained_ | Carbon cap (`carbon_policies.csv`) is binding from 2025 onward (shadow price reaches $65/tCO2 by 2060). Letting coal float past 2030 means the model can build coal in principle, but the emissions cap should force retirement automatically. If v0.2 results show new coal still being built in 2035+, escalate by adding declining trajectory rows. |

### Sources / reasoning trail

- **EF judgment (project owner, 2026-05-27):** national coal capacity peaks at **1,550-1,600 GW before end of 15th FYP (= 2030)**. Documented as a planning assumption, not a citation.
- 2024 national coal: ~1,170 GW (NEA / CEC)
- 6-zone share of national coal capacity: 286 / 1,170 ≈ **24.4%** as of 2024
- Applied to EF peak: 25% × 1,600 GW = **400 GW** at 6-zone level in 2030
- 2025 interpolated: 286 GW EP + ~34 GW headroom (smooth growth toward 2030 peak)
- Post-2030: carbon cap drives decline; we choose not to add a separate physical cap to avoid over-constraining the LP and to let cross-tech competition decide retirement timing.

## Convention reminder

`gen_overnight_cost` and `gen_fixed_om` in `gen_build_costs.csv` are in
**$/MW** (and $/MW-yr), per `switch_model/generators/core/build.py:193-216`.
This document's MW figures are SWITCH-native — no conversion required.

## Change log

| Date | Change | Why |
|---|---|---|
| 2026-05-27 | Initial Uranium 2025-2035 + Coal 2025-2030 caps | v0.1 root-cause fix A (see `scenarios/shanghai/results_archive/v0.1/README.md`) |
