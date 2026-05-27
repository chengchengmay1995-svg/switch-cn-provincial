# v0.2b run archive — Shanghai 6-zone, cap fix applied

Second end-to-end solve. Adds Uranium+Coal `total_capacity_limits.csv`
caps (root-cause fix A from v0.1 post-mortem). The "b" suffix records
that an initial v0.2 attempt with Uranium 2025 = 37 GW was **infeasible**
— see "Cap calibration history" below.

## Run metadata

- **Date:** 2026-05-27
- **Inputs commit:** `eabeed8` (caps + assumptions) minus the dropped
  `Uranium,2025,37000` row (commit `<TBD>` removes it; see below)
- **Solver:** HiGHS `appsi_highs`, `solver=ipm run_crossover=off`
- **Wall time:** 2257 s (~38 min); LP solve 2178 s
- **Termination:** **optimal**
- **Total NPV cost:** $2.712 trillion (+20% vs v0.1)

## Headline finding: fix A worked — but only for 2025-2035 transition

| Metric | v0.1 | v0.2b | Delta |
|---|---|---|---|
| Central_PV new in 2030 | 0 GW | **218 GW** | +218 |
| Wind new in 2030 | 0 GW | **79 GW** | +79 |
| Offshore_Wind in 2030 | 22 GW | **236 GW** | +214 |
| Nuclear_SEA in 2030 (capped at 50 GW total Uranium) | 136 GW | **11 GW** | -125 |
| New Coal_1000_OT in 2030 | 13 GW | **6 GW** | -7 |
| New Coal_1000_RC in 2030 | 11 GW | **4 GW** | -7 |
| Carbon shadow price 2030 | $7/tCO2 | **$137** | 18.5x |
| Carbon shadow price 2035 | $8/tCO2 | **$436** | 56x |
| LCOE 2035 | $58.9 | **$95.1** | +61% (transition cost peak) |

The cap correctly redirected investment from nuclear to VRE in 2025-2035.
Carbon shadow price spike to $436/tCO2 in 2035 confirms the carbon cap
is now acutely binding (it wasn't in v0.1 because nuclear absorbed all
zero-carbon need).

## Persistent problems (post-cap)

These show that fix A alone is **not sufficient**:

1. **Nuclear surges back post-2040.** Nuclear_SEA reaches 487 GW by 2060
   (matches v0.1 essentially). User intent ("保持想象力" for 2040+) is
   met, but the LP just defers the unrealistic mega-deployment by 10
   years. By 2060 we're back to the same physically-impossible number.

2. **Central_PV → 0 by 2060.** Despite 506 GW PV at peak (2035-2045),
   it ages out and is not rebuilt because the cost trajectory is flat —
   $1,200/MW for all build_years, so 2050-vintage PV competes with
   2050-vintage nuclear (also flat) and loses to nuclear's higher CF.

3. **Late-period new coal: 138 GW by 2060.** Unchanged from v0.1.
   No `Coal` cap past 2030, and carbon cap relaxes once VRE is in
   place (shadow price returns to $8 by 2040).

4. **Offshore_Wind 2025 = 148 GW.** Reality check: national China
   offshore wind 2024 ≈ 38 GW. The model places 148 GW in 6 zones by
   2025 — equally implausible as v0.1's 80 GW nuclear in 2025. The
   model has no build-rate constraint, so capping one tech just shifts
   the over-build to another.

## Cap calibration history

| Attempt | Uranium caps | Coal caps | Result |
|---|---|---|---|
| v0.2 | 2025=37, 2030=50, 2035=65 | 2025=320k, 2030=400k | **infeasible** |
| v0.2b | _(2025 dropped)_, 2030=50, 2035=65 | 2025=320k, 2030=400k | optimal |

Why 37 GW for 2025 was infeasible: model needs ~50 GW total Uranium in
2025 to balance the system under the carbon cap with current cost
trajectories. Capping at 37 GW (EP fleet level) leaves no room for
even the 13 GW of new Nuclear_SEA + SMR that the optimal trade-off
requires, and there's no feasible substitution within one period given
the cost data.

The 2030 cap of 50 GW _implicitly_ caps 2025 builds anyway (any 2025
new nuclear would still exist in 2030 and count against that cap), so
dropping the explicit 2025 row has no practical loosening effect on
the long-term solution. Model settled at total Uranium 2025 = 50 GW
naturally (= 37 EP + 11 new SEA + 2 SMR).

## What to fix next (toward v0.3)

Pick one or both:

**Fix B — Cost learning curves** (`gen_build_costs.csv`):
- Reduces PV/storage cost over time per BNEF or IEA WEO 2024 trajectory
- Would let renewables stay competitive in 2040-2060
- Likely fixes the Nuclear_SEA-487-GW-by-2060 issue: when PV+storage
  combo is cheaper than nuclear in 2050, LP will pick it without needing
  a cap
- Estimated effort: moderate (need a defensible learning-curve source)

**Fix C — Coal cap 2035-2060** (`total_capacity_limits.csv`):
- Mirror the Uranium logic: add declining coal cap rows
- Forces VRE/storage to absorb late-period growth
- Estimated effort: small (5 more rows + assumption doc update)

**Fix D — Build-rate caps** (new `cn_modules/extensions/build_rate.py`):
- Add `max_new_build_mw_per_period[gen_tech, period]` constraint
- Reflects physical lead-time + supply chain limits
- Would fix the 148-GW-offshore-wind-by-2025 issue
- Estimated effort: large (need new module + per-tech max-build research)

Fix B is the most leveraged for late-period realism. Fix C is cheapest.
Fix D is the most physically faithful but heaviest.
