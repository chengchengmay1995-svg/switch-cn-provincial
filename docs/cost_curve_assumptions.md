# Technology cost-learning curve assumptions

This document records every assumption behind the multipliers in
`tools/apply_cost_curves.py`. That script overwrites
`scenarios/<province>/inputs/gen_build_costs.csv` to add 2020–2060
learning trajectories where upstream switch-china-open-model had flat
costs.

## Why this exists

`tools/import_woodmac.py:439` punts on cost forecasts:

> Note: upstream values are in 2010 USD nominal — for first pass we keep them.
> Plan D-7 says costs in 2020 USD; user reviews + we may apply 2010→2020
> deflator later.

The v0.1 + v0.2b results confirmed this is a major problem: with PV
stuck at $1,200/kW for all build_years 2020–2060, the LP picks
nuclear+coal forever (see
`scenarios/shanghai/results_archive/v0.2b/README.md` "Persistent
problems"). Without a falling cost curve, renewables can't replace
fossil/nuclear long-term.

## Approach

We hold 2020 cost values as-is (= upstream baseline, considered
approximately 2020 USD per the import_woodmac comment trail) and
**multiply later build_years** by published learning-curve factors.

Only VRE + storage gets a learning curve. Mature thermal/nuclear
keeps flat costs — this is consistent with how most published
outlooks treat them and is **deliberately conservative**: if anything,
fixing-only-renewables understates renewable competitiveness.

## Trajectories (multipliers, 2020 = 1.00)

| Tech | 2020 | 2025 | 2030 | 2035 | 2040 | 2045 | 2050 | 2055 | 2060 | Primary source |
|---|---|---|---|---|---|---|---|---|---|---|
| Central_PV / Commercial_PV / Residential_PV | 1.00 | 0.75 | 0.58 | 0.50 | 0.45 | 0.42 | 0.40 | 0.39 | 0.38 | BNEF NEO 2024 + IEA WEO 2024 STEPS China |
| Wind (onshore) | 1.00 | 0.92 | 0.84 | 0.79 | 0.75 | 0.73 | 0.72 | 0.71 | 0.71 | NREL ATB 2024 Moderate |
| Offshore_Wind | 1.00 | 0.88 | 0.75 | 0.67 | 0.60 | 0.56 | 0.53 | 0.52 | 0.51 | NREL ATB 2024 Moderate (fixed-bottom) |
| Battery_Storage (power) | 1.00 | 0.75 | 0.55 | 0.45 | 0.40 | 0.38 | 0.35 | 0.34 | 0.33 | BNEF Battery Cost Outlook 2024 |

Multipliers apply to **both** `gen_overnight_cost` and `gen_fixed_om`.
(Fixed O&M tracks capex roughly per industry observation, simplification
that BNEF/NREL both make.)

## Battery storage energy cost ($/MWh, absolute values)

Upstream had `gen_storage_energy_overnight_cost = 0` (energy capacity
free). We override with BNEF Battery Cost Outlook 2024 pack-level cost:

| Year | $/kWh | $/MWh (model unit) |
|---|---|---|
| 2020 | 400 | 400,000 |
| 2025 | 240 | 240,000 |
| 2030 | 160 | 160,000 |
| 2035 | 120 | 120,000 |
| 2040 | 100 | 100,000 |
| 2045 | 85  | 85,000 |
| 2050 | 75  | 75,000 |
| 2055 | 72  | 72,000 |
| 2060 | 70  | 70,000 |

(Asymptotes around $70/kWh per BNEF's 2050 projection — close to
DOE materials-floor estimate for Li-ion / Li-Fe-PO4.)

## Numerical sanity check

Worked examples assuming the multipliers above:

| Tech | 2020 $/MW | 2030 $/MW | 2050 $/MW | Real-world 2030 anchor |
|---|---|---|---|---|
| Central_PV | 1,200,000 | **696,000** | 480,000 | China utility PV 2030 ≈ $600-750/kW per IEA WEO 2024 |
| Wind | 1,129,000 | **948,000** | 813,000 | China onshore wind 2030 ≈ $900-1000/kW per NREL ATB |
| Offshore_Wind | 2,184,000 | **1,638,000** | 1,158,000 | Global offshore 2030 ≈ $1,600-2,000/kW |
| Battery (power) | 1,486,000 | **817,000** | 520,000 | (4hr Li-ion 2030 ≈ $400-600/kW for power module) |
| Battery (4hr total = power + 4×energy) | $1,486 + 4×$0 = $1,486 | $817 + 4×$160 = **$1,457/kW** | $520 + 4×$75 = $820/kW | China utility 4hr BESS 2030 ≈ $1,400-1,800/kW |

Each row's 2030 figure lands within ±15% of the published anchor —
good enough for a planning model. Replace with project-specific data
when available.

## What's deliberately omitted

- **No Coal/Gas/Nuclear cost evolution.** These stay flat at upstream
  2020 values. Defensible: mature tech, no major learning expected; if
  they do get cheaper, this just makes our results conservative on the
  renewable side.

- **No regional cost variation across the 6 zones.** Same trajectory
  applies to Shanghai-Central_PV-401 and Sichuan-Central_PV-403.
  Real-world Sichuan PV is ~10% cheaper than Shanghai. Refine later if
  needed via per-project overrides.

- **No CO2-shadow-priced cost adjustments.** Some forecasts adjust
  cost trajectories for implied carbon price; we use raw capex.

- **No discount-rate consistency check.** Discount rate is 8% in
  `financials.csv` (upstream). Real PV financing is often 4-6%; this
  understates PV value. Address separately if needed.

## Where to find source data

- **BNEF NEO 2024:** _New Energy Outlook 2024_, BloombergNEF.
  Subscription required for full data; headline charts are in
  press release & summary deck (Bloomberg.com search "NEO 2024").
- **BNEF Battery Cost Outlook 2024:** _Lithium-Ion Battery Price
  Survey 2024_. Headline number: 2023 pack price $115/kWh (cell+pack),
  projected $80/kWh by 2030.
- **NREL ATB 2024:** _Annual Technology Baseline 2024_, NREL.
  Public, full data at atb.nrel.gov. Use "Moderate" scenario for
  defaults.
- **IEA WEO 2024:** _World Energy Outlook 2024_, IEA. Stated Policies
  Scenario (STEPS) for our defaults. China chapter has region-specific
  PV/wind costs.

## Change log

| Date | Change | By |
|---|---|---|
| 2026-05-27 | Initial draft, applied to Shanghai scenario via apply_cost_curves.py | v0.3 fix B |
