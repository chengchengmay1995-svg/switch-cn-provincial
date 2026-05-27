# v0.3 run archive — Shanghai 6-zone, caps + cost curves

Third end-to-end solve. Builds on v0.2b by applying 2020-2060 cost
learning curves to PV/Wind/Battery via `tools/apply_cost_curves.py`
(commit `eaadc00`). This is "fix B" from the v0.2b post-mortem.

## Run metadata

- **Date:** 2026-05-27
- **Inputs commit:** `eaadc00`
- **Solver:** HiGHS `appsi_highs`, `solver=ipm run_crossover=off`
- **Wall time:** **19,900 s (~5 h 32 min)** — 14x slowdown vs v0.2b's 38 min
- **Termination:** **optimal**
- **Total NPV cost:** $2.532 trillion (-7% vs v0.2b's $2.712 T)

## Three-way comparison (capacity by tech, MW)

|  | v0.1 (no caps, flat) | v0.2b (caps, flat) | **v0.3 (caps + curves)** |
|---|---|---|---|
| NPV ($B) | 2,256 | 2,712 | **2,532** |
| LCOE 2035 peak | $58.9 | $95.1 | **$82.5** |
| Carbon shadow $/tCO2 2035 | 8 | 436 | **286** |
| Central_PV 2030 | 0 | 218 | 218 |
| Central_PV 2035 peak | 0 | 506 | **563** |
| **Central_PV 2060** | **0** | **0** | **155** |
| Nuclear_SEA 2030 (cap binds at 50) | 136 | 11 | 11 |
| Nuclear_SEA 2060 (uncapped) | 485 | 487 | **402** |
| New Coal_1000_OT+RC 2060 | 138 | 138 | **125** |
| **Offshore_Wind 2060** | **0** | **0** | **214** |
| Wind 2060 | 55 | 55 | 34 |
| Battery_Storage 2060 | 11.7 | 9.3 | **2.9** |

## What fix B accomplished

**Positive (this is the value of cost-curve modeling):**

1. **Long-term PV survives.** Central_PV holds 155 GW by 2060 vs 0 in
   v0.1/v0.2b. Cheaper PV at later periods means the model still
   wants to rebuild as old vintages retire.

2. **Offshore_Wind long-term: 214 GW by 2060.** Both prior runs let it
   go to 0 (CapEx too expensive to refresh). With 2060 cost dropped
   to ~$1,030/MW the model maintains it.

3. **Nuclear_SEA 2060 reduced 85 GW (487 → 402).** Cheaper VRE
   competition partially displaces nuclear in the uncapped post-2035
   period.

4. **New coal 2060 reduced 13 GW (138 → 125).** Modest improvement
   from cheaper alternatives, but coal still dominates late-period new
   capacity (carbon cap relaxes once VRE meets early-period demand).

5. **System cost drops $180 B NPV vs v0.2b.** Cheaper VRE is just
   cheaper.

**Still not enough (gaps):**

1. **Nuclear_SEA 402 GW by 2060 still physically impossible.** Coastal
   site inventory caps reality at ~150-200 GW even in aggressive
   scenarios.

2. **125 GW new coal builds 2055-2060.** Concentrated post-2050 when
   carbon cap relaxes (annual emissions drop from 1.06 Gt in 2035 to
   182 Mt in 2060 — the cap is "easy" by 2060 because most generation
   is already zero-carbon). Model fills incremental demand with cheap
   new coal during this slack window.

3. **Battery_Storage = 2.9 GW.** Storage went DOWN vs v0.2b. With
   cheap Offshore_Wind + nuclear baseload providing firm power, the
   LP sees no value in storage. (Storage benefits get unlocked only
   when VRE share is high AND firm zero-carbon is scarce.)

4. **Central_PV non-monotonic:** 563 GW (2040 peak) → 88 GW (2055) →
   155 GW (2060). The 2030/2035 vintage retires around 2055 (~25 yr
   life). The 2050-2055 dip happens because uncapped Nuclear_SEA
   offers cheaper zero-carbon during that interval. PV rebuilds only
   when carbon cap tightens again at 2055/2060 (cap 267 / 182 Mt).

5. **Offshore_Wind 2025 = 148 GW unchanged.** Same build-rate problem
   as v0.2b — model assumes 110 GW of offshore wind can be deployed
   in 5 years across 6 zones (China 2024 national offshore total = 38
   GW). No constraint on annual build-out pace.

## Performance regression

Solve time exploded **14x** from 38 min to 5.5 h. Likely cause:
upstream costs were perfectly flat per tech (single column value); the
LP only needed coarse build-year decisions. With curves, each
(gen_tech × build_year) cell has a unique price, so the LP must do
fine-grained marginal comparisons between near-equivalent options.
HiGHS IPM degenerates on this kind of problem.

Mitigations to investigate before v0.4:
- `solver=simplex` (dual simplex; may be slower per iter but converges)
- `run_crossover=on` (counter-intuitive but sometimes faster overall)
- Loosen IPM tolerance: `primal_tol=1e-6 dual_tol=1e-6`
- Gurobi academic license (CLAUDE.md mentions this as future option)

## What to fix next (toward v0.4)

Now that fix A (caps) and fix B (cost curves) are validated, options
in rough priority order:

| Fix | Effort | Target outcome |
|---|---|---|
| **C — Coal cap 2035-2060** | small (5 CSV rows + assumptions update) | Push new coal 2060 from 125 → ~30-50 GW |
| **Performance** | medium (try alt solver settings; measure) | Get back under 1h per solve |
| **D — Build-rate caps via cn_modules/extensions** | large (new SWITCH module + per-tech data) | Fix Offshore_Wind 148 GW in 2025 + similar artifacts |
| **E — Improve PV CF data** | medium (find better Shanghai solar resource) | Marginal — CF only ~20% low |
| **F — Lower discount rate or use VRE-specific WACC** | small if just CSV; medium if module change | Could shift several percentage points more capacity to renewables |

Phase E (2025 calibration vs actuals) requires fix C minimum to be
meaningful — the v0.3 result still has unrealistically high nuclear
and late-period coal.
