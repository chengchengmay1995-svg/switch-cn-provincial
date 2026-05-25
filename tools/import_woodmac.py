#!/usr/bin/env python3
"""
Build scenarios/shanghai/inputs/ for the 6-zone Shanghai scenario.

Pulls data from:
- Wood Mackenzie APAC H2 2025 Excel (inputs/raw/...): historical ≤2025 anchor
  + 2026 typical-day hourly shape; extrapolated to 2030-2060 using the
  growth assumptions in the CONSTANTS block below (user reviews).
- Upstream switch-china inputs/ (filtered to the 6 zones): zone-free /
  network / generation-fleet metadata that Wood Mac doesn't provide.

Zones (plan Path B):
  Shanghai + Jiangsu + Zhejiang + Anhui + Fujian + Sichuan

Output:
  Wood-Mac sourced (period-aggregated):
    zone_coincident_peak_demand.csv, fuel_cost.csv, carbon_policies.csv
  Wood-Mac sourced (timepoint-aggregated):
    loads.csv (annual demand × 2026 24h shape, replicated to all 12 rep days)
    variable_capacity_factors.csv (2026 hourly CF / installed cap)
  Upstream filter + period-remap:
    gen_build_costs (old 2023-2048 → new 2025-2050; 2020/2055/2060 copy nearest)
    fuel_supply_curves (same period remap)
    capacity_plans (same period remap)
    hydro_timeseries (filter project + ts year remap, month preserved)
  Upstream filter (period-free):
    load_zones, transmission_lines, gen_info, gen_build_predetermined,
    gen_part_load_heat_rates, planning_reserve_requirement_zones,
    planning_reserve_requirements, zone_to_regional_fuel_market,
    regional_fuel_markets
  Upstream copy:
    fuels, non_fuel_energy_sources, trans_params,
    financials (base_financial_year updated to 2020),
    periods.csv, timeseries.csv, timepoints.csv,
    modules.txt, switch_inputs_version.txt
  Empty (header only):
    total_capacity_limits (no national cap in 6-zone scenario)

Documented limitations:
- All 12 representative days in every period use the SAME diurnal shape
  (Wood Mac 2026 typical-day; no seasonal variation).
- VRE CF profile uses Wood Mac 2026 typical-day per zone × fuel; applied
  uniformly to every period (no inter-period VRE shape evolution).
- 2026-2060 demand projections compound from 2025 historical (see
  DEMAND_GROWTH_PER_PERIOD); user replaces with own forecast later.
- Fuel-cost real-USD growth post-2025 is a hard-coded annual rate per
  fuel (see FUEL_COST_GROWTH).
- Carbon trajectory post-2025 follows CARBON_TRAJECTORY_MULT (peak 2030,
  decline to 15% of 2025 by 2060).

Usage:
  python tools/import_woodmac.py --dry-run   # preview row counts; no writes
  python tools/import_woodmac.py             # write scenarios/shanghai/inputs/
"""

import argparse
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ============================================================================
#  Configuration — user reviews these before approving the first real run
# ============================================================================

WOODMAC_XLSX = Path("inputs/raw/apac-p-r-strategic-planning-outlook-h2-2025_data (2).xlsx")
UPSTREAM_INPUTS = Path("inputs")
TARGET_DIR = Path("scenarios/shanghai/inputs")

ZONES = ["Shanghai", "Jiangsu", "Zhejiang", "Anhui", "Fujian", "Sichuan"]
PERIOD_STARTS = [2020, 2025, 2030, 2035, 2040, 2045, 2050, 2055, 2060]

BASE_FINANCIAL_YEAR = 2020   # plan D-7

DEMAND_GROWTH_PER_PERIOD = {
    2030: 0.030, 2035: 0.025, 2040: 0.015, 2045: 0.005,
    2050: 0.002, 2055: 0.001, 2060: 0.000,
}
FUEL_COST_GROWTH = {"Coal": 0.005, "Gas": 0.010, "Diesel": 0.015, "FuelOil": 0.015}
CPI_2025_TO_2020_DEFLATOR = 0.824
CARBON_TRAJECTORY_MULT = {
    2020: None, 2025: 1.000, 2030: 1.030, 2035: 0.875, 2040: 0.715,
    2045: 0.550, 2050: 0.385, 2055: 0.220, 2060: 0.150,
}
CARBON_PRICE_PER_TCO2 = 0.0

# Map upstream's old periods (2023-2048) to our new periods (2025-2050)
OLD_TO_NEW_PERIOD = {2023: 2025, 2028: 2030, 2033: 2035,
                     2038: 2040, 2043: 2045, 2048: 2050}
# For our new periods not in the map (2020, 2055, 2060), nearest-neighbor:
NEAREST_FALLBACK_NEW_PERIOD = {2020: 2025, 2055: 2050, 2060: 2050}

# SWITCH gen_tech → Wood Mac VRE fuel category
GENTECH_TO_WM_FUEL = {
    "Wind":             "Wind_Onshore",
    "Wind_EP":          "Wind_Onshore",
    "Offshore_Wind":    "Wind_Offshore",
    "Central_PV":       "Solar_Grid",
    "Central_PV_EP":    "Solar_Grid",
    "Residential_PV":   "Solar_Distributed",
    "Commercial_PV":    "Solar_Distributed",
}

# Timepoint-of-day → which 4-hour bin of the 24-hour Wood Mac typical day
# (our timepoints are at hours 00, 04, 08, 12, 16, 20)
TP_HOURS_BINS = [(1, 5), (5, 9), (9, 13), (13, 17), (17, 21), (21, 25)]  # 1-indexed
TP_HOURS_LIST = [0, 4, 8, 12, 16, 20]


# ============================================================================
#  Wood Mac helpers
# ============================================================================

def load_woodmac():
    print(f"Loading {WOODMAC_XLSX.name} ({WOODMAC_XLSX.stat().st_size / 1024 / 1024:.1f} MB)...")
    return {
        "Demand":      pd.read_excel(WOODMAC_XLSX, sheet_name="Demand",      header=5),
        "Fuel prices": pd.read_excel(WOODMAC_XLSX, sheet_name="Fuel prices", header=5),
        "Emissions":   pd.read_excel(WOODMAC_XLSX, sheet_name="Emissions",   header=5),
        "Capacity":    pd.read_excel(WOODMAC_XLSX, sheet_name="Capacity",    header=5),
        # Hourly sheet: header row 5 has hour labels (1..24 repeated 5 times for years 2026,2030,2040,2050,2060)
        "Hourly":      pd.read_excel(WOODMAC_XLSX, sheet_name="Hourly",      header=5),
    }


def _wm_row(df, zone, **kw):
    mask = (df["Country"] == "China") & (df["Zone"] == zone)
    for k, v in kw.items():
        mask = mask & (df[k] == v)
    return df[mask]


def _project_from_2025(value_2025, period_starts_after_2025, growth_map=None):
    """Compound from 2025 forward using DEMAND_GROWTH_PER_PERIOD by default."""
    out = {}
    prev_val = value_2025
    prev_year = 2025
    growth_map = growth_map or DEMAND_GROWTH_PER_PERIOD
    for ps in period_starts_after_2025:
        g = growth_map[ps]
        years = ps - prev_year
        new_val = prev_val * (1 + g) ** years
        out[ps] = new_val
        prev_val = new_val
        prev_year = ps
    return out


def _hourly_2026_cols(hourly_df):
    """Wood Mac Hourly sheet: cols 5-28 are hours 1-24 for year 2026.
       Pandas reads them as columns named '1.0', '2.0', ..., '24.0' (strings).
       Returns the column labels for the 2026 24h block."""
    # The columns after metadata are float labels '1.0'..'24.0' (the first 24).
    # Use the dataframe's actual columns; first 24 numeric cols after Fuel.
    cols = list(hourly_df.columns)
    # cols[0..4] are Region/Country/Market/Zone/Fuel
    # cols[5..28] are 2026 hours 1..24
    return cols[5:29]


def _hourly_2026_block(hourly_df, zone, fuel):
    """Return the 24 MW values for (zone, fuel) typical day in 2026, or None."""
    row = _wm_row(hourly_df, zone, Fuel=fuel)
    if row.empty:
        return None
    cols_2026 = _hourly_2026_cols(hourly_df)
    return row[cols_2026].values[0].astype(float)


def _aggregate_24h_to_6tp(values_24):
    """Aggregate 24 hourly values into 6 4-hour timepoint averages."""
    return np.array([np.mean(values_24[lo - 1:hi - 1]) for lo, hi in TP_HOURS_BINS])


# ============================================================================
#  Section 3 — Wood Mac → period-aggregated CSVs
# ============================================================================

def build_zone_peak_demand(sheets):
    df_d = sheets["Demand"]
    rows = []
    for z in ZONES:
        row = _wm_row(df_d, z, Description="Peak Generation")
        if row.empty:
            sys.exit(f"FATAL: no Peak Generation for {z}")
        v_2020 = float(row[2020].values[0])
        v_2025 = float(row[2025].values[0])
        peaks = {2020: v_2020, 2025: v_2025}
        peaks.update(_project_from_2025(v_2025, [2030, 2035, 2040, 2045, 2050, 2055, 2060]))
        for ps in PERIOD_STARTS:
            rows.append((z, ps, peaks[ps]))
    return pd.DataFrame(rows, columns=["LOAD_ZONE", "PERIOD", "zone_expected_coincident_peak_demand"])


def build_fuel_cost(sheets):
    """fuel_cost.csv = simple-cost mode for Coal + Uranium only.
       Gas uses the regional_fuel_markets + fuel_supply_curves structure
       (matches upstream's split). Diesel/FuelOil are not in fuels.csv so
       they have no consumers and are excluded.
       Coal prices come from Wood Mac; Uranium copied from upstream + period remap.
    """
    df_fp = sheets["Fuel prices"]
    rows = []

    # --- Coal: Wood Mac historical + projected ---
    for z in ZONES:
        row = _wm_row(df_fp, z, Fuel="Coal")
        if row.empty:
            continue
        v_2020 = float(row[2020].values[0])
        v_2025 = float(row[2025].values[0]) * CPI_2025_TO_2020_DEFLATOR
        costs = {2020: v_2020, 2025: v_2025}
        prev = v_2025
        g = FUEL_COST_GROWTH["Coal"]
        for ps in [2030, 2035, 2040, 2045, 2050, 2055, 2060]:
            prev = prev * (1 + g) ** 5
            costs[ps] = prev
        for ps in PERIOD_STARTS:
            rows.append((z, "Coal", ps, costs[ps]))

    # --- Uranium: from upstream (Wood Mac doesn't price uranium per zone) ---
    upstream = pd.read_csv(UPSTREAM_INPUTS / "fuel_cost.csv")
    uranium = upstream[(upstream["fuel"] == "Uranium") &
                       (upstream["load_zone"].isin(ZONES))].copy()
    if len(uranium):
        uranium = _remap_period_column(uranium, "period")
        rows.extend(uranium[["load_zone", "fuel", "period", "fuel_cost"]].values.tolist())

    return pd.DataFrame(rows, columns=["load_zone", "fuel", "period", "fuel_cost"])


def build_carbon_policies(sheets):
    df_e = sheets["Emissions"]
    sum_2020_mt = 0.0
    sum_2025_mt = 0.0
    for z in ZONES:
        for _, r in _wm_row(df_e, z).iterrows():
            v20 = r.get(2020); v25 = r.get(2025)
            if pd.notna(v20): sum_2020_mt += v20
            if pd.notna(v25): sum_2025_mt += v25
    rows = []
    for ps in PERIOD_STARTS:
        cap_mt = (sum_2020_mt if ps == 2020 else
                  sum_2025_mt if ps == 2025 else
                  sum_2025_mt * CARBON_TRAJECTORY_MULT[ps])
        rows.append((ps, cap_mt * 1e6, CARBON_PRICE_PER_TCO2))
    return pd.DataFrame(rows, columns=["PERIOD", "carbon_cap_tco2_per_yr", "carbon_cost_dollar_per_tco2"])


# ============================================================================
#  Section 4 — Wood Mac → timepoint-aggregated CSVs (loads + VRE CF)
# ============================================================================

def _zone_hourly_demand_shape(hourly_df, zone):
    """Sum 2026 typical-day hourly across all fuels (incl. Import, excl. Export)
       to estimate zone hourly demand profile. Returns 24-value array normalized to mean=1."""
    cols_2026 = _hourly_2026_cols(hourly_df)
    df_z = hourly_df[(hourly_df["Country"] == "China") & (hourly_df["Zone"] == zone)]
    profile = np.zeros(24, dtype=float)
    for _, r in df_z.iterrows():
        fuel = r["Fuel"]
        if fuel in ("Export", "Price"):
            continue  # exports leave the zone; Price is not a flow
        vals = r[cols_2026].values
        if pd.isna(vals).any():
            continue
        profile += vals.astype(float)
    if profile.sum() == 0:
        sys.exit(f"FATAL: zero hourly profile for {zone}")
    return profile / profile.mean()  # mean-normalized so sum = 24


def build_loads(sheets, periods_df, timepoints_df):
    """loads.csv: LOAD_ZONE, TIMEPOINT, zone_demand_mw.
       Wood Mac annual demand × 2026 24h-shape (aggregated to 6 tps), replicated
       to all 12 representative days in each of 9 periods (no seasonal var)."""
    df_d = sheets["Demand"]
    hourly = sheets["Hourly"]
    rows = []
    for z in ZONES:
        gen_row = _wm_row(df_d, z, Description="Generation - Gross (w/ net imports)")
        if gen_row.empty:
            sys.exit(f"FATAL: no Generation row for {z}")
        annual_2020_gwh = float(gen_row[2020].values[0])
        annual_2025_gwh = float(gen_row[2025].values[0])
        annual_gwh = {2020: annual_2020_gwh, 2025: annual_2025_gwh}
        annual_gwh.update(_project_from_2025(annual_2025_gwh,
                                             [2030, 2035, 2040, 2045, 2050, 2055, 2060]))

        # Diurnal shape: 24 mean-normalized values → 6 timepoints
        shape24 = _zone_hourly_demand_shape(hourly, z)
        shape6  = _aggregate_24h_to_6tp(shape24)  # also mean ≈ 1

        # For each period: average hourly demand (MWh/h = MW) = annual_MWh / 8766
        # Each timepoint MW = shape6[tp_idx] * avg_demand_mw
        for _, prow in periods_df.iterrows():
            ps = int(prow["INVESTMENT_PERIOD"])
            avg_mw = annual_gwh[ps] * 1000.0 / 8766.0  # GWh→MWh /yr → MW
            # Find timepoints in this period
            tps_in_period = timepoints_df[timepoints_df["timeseries"].str.startswith(
                str(ps + (5 - 1) // 2))]  # mid-year prefix
            # For each timepoint, get hour from timepoint_id suffix (e.g., '.00','.04','.08','.12','.16','.20')
            for _, trow in tps_in_period.iterrows():
                tp_id = trow["timepoint_id"]
                hour = int(tp_id.split(".")[-1])
                tp_idx = TP_HOURS_LIST.index(hour)
                rows.append((z, tp_id, shape6[tp_idx] * avg_mw))
    return pd.DataFrame(rows, columns=["LOAD_ZONE", "TIMEPOINT", "zone_demand_mw"])


def build_variable_capacity_factors(sheets, periods_df, timepoints_df, gen_info_df):
    """variable_capacity_factors.csv: GENERATION_PROJECT, timepoint, gen_max_capacity_factor.

    For each (zone, wm_vre_fuel): CF = (2026 hourly MW) / (2026 installed MW).
    Aggregate 24h → 6tp. Apply same profile to every period × every rep day."""
    cap_df = sheets["Capacity"]
    hourly_df = sheets["Hourly"]

    # Build (zone, wm_fuel) → 6-value CF profile
    cf_profiles = {}
    wm_vre_fuels = ["Wind_Onshore", "Wind_Offshore", "Solar_Grid", "Solar_Distributed"]
    for z in ZONES:
        for wm_fuel in wm_vre_fuels:
            hourly_24 = _hourly_2026_block(hourly_df, z, wm_fuel)
            cap_row = _wm_row(cap_df, z, Fuel=wm_fuel)
            cap_2026 = float(cap_row[2026].values[0]) if not cap_row.empty else 0.0
            if hourly_24 is None or cap_2026 <= 0:
                cf_profiles[(z, wm_fuel)] = None
                continue
            cf24 = np.clip(hourly_24 / cap_2026, 0.0, 1.0)
            cf_profiles[(z, wm_fuel)] = _aggregate_24h_to_6tp(cf24)

    # Default fallback CF: if a zone has no 2026 capacity for a fuel, fall back to
    # the mean across zones that DO have it.
    fallback = {}
    for wm_fuel in wm_vre_fuels:
        valid = [v for (z, f), v in cf_profiles.items() if f == wm_fuel and v is not None]
        fallback[wm_fuel] = np.mean(valid, axis=0) if valid else np.full(6, 0.20)

    # For each VRE project, write 648 rows
    rows = []
    vre_projects = gen_info_df[gen_info_df["gen_is_variable"] == True]
    for _, gp in vre_projects.iterrows():
        gen_tech = gp["gen_tech"]
        zone = gp["gen_load_zone"]
        wm_fuel = GENTECH_TO_WM_FUEL.get(gen_tech)
        if wm_fuel is None:
            continue  # unmapped tech — skip (rare)
        cf6 = cf_profiles.get((zone, wm_fuel))
        if cf6 is None:
            cf6 = fallback[wm_fuel]
        for _, trow in timepoints_df.iterrows():
            tp_id = trow["timepoint_id"]
            hour = int(tp_id.split(".")[-1])
            tp_idx = TP_HOURS_LIST.index(hour)
            rows.append((gp["GENERATION_PROJECT"], tp_id, float(cf6[tp_idx])))
    return pd.DataFrame(rows, columns=["GENERATION_PROJECT", "timepoint", "gen_max_capacity_factor"])


# ============================================================================
#  Section 5 — Upstream → filter + period-remap
# ============================================================================

def _remap_period_column(df, col_name):
    """Map old period values (2023-2048) to new (2025-2050); duplicate to fill
    2020/2055/2060 from nearest. Returns new df with `period` cells rewritten."""
    out_rows = []
    for old, new in OLD_TO_NEW_PERIOD.items():
        sub = df[df[col_name] == old].copy()
        sub[col_name] = new
        out_rows.append(sub)
    # Fallback: 2020 ← 2025 (which came from 2023); 2055 ← 2050 (from 2048); 2060 ← 2050
    base = pd.concat(out_rows, ignore_index=True) if out_rows else df.iloc[0:0]
    for new, src in NEAREST_FALLBACK_NEW_PERIOD.items():
        sub = base[base[col_name] == src].copy()
        sub[col_name] = new
        base = pd.concat([base, sub], ignore_index=True)
    return base


def build_gen_build_costs(gen_info_df):
    df = pd.read_csv(UPSTREAM_INPUTS / "gen_build_costs.csv")
    df = df[df["GENERATION_PROJECT"].isin(gen_info_df["GENERATION_PROJECT"])].copy()
    historical = df[df["build_year"] < 2023].copy()             # sunk costs, keep as-is
    future_old = df[df["build_year"].isin(OLD_TO_NEW_PERIOD)].copy()
    future_new = _remap_period_column(future_old, "build_year")
    return pd.concat([historical, future_new], ignore_index=True)


def build_fuel_supply_curves(z2rfm_df):
    df = pd.read_csv(UPSTREAM_INPUTS / "fuel_supply_curves.csv")
    df = df[df["regional_fuel_market"].isin(z2rfm_df["regional_fuel_market"])].copy()
    # Note: upstream values are in 2010 USD nominal — for first pass we keep them.
    # Plan D-7 says costs in 2020 USD; user reviews + we may apply 2010→2020 deflator later.
    return _remap_period_column(df, "period")


def build_capacity_plans():
    df = pd.read_csv(UPSTREAM_INPUTS / "capacity_plans.csv")
    df = df[df["load_zones"].isin(ZONES)].copy()
    if df.empty:
        return df
    return _remap_period_column(df, "period")


# Hydro timeseries: filter by project + remap ts year (month preserved)
def build_hydro_timeseries(gen_info_df):
    df = pd.read_csv(UPSTREAM_INPUTS / "hydro_timeseries.csv")
    hydro_projects = gen_info_df[gen_info_df["gen_energy_source"] == "Water"]["GENERATION_PROJECT"]
    df = df[df["hydro_project"].isin(hydro_projects)].copy()
    if df.empty:
        return df

    # Map upstream ts year (mid-year of old period) → new ts year
    # OLD period_start → mid_year: 2023→2025, 2028→2030, 2033→2035, 2038→2040, 2043→2045, 2048→2050
    # NEW period_start → mid_year: 2020→2022, 2025→2027, 2030→2032, ..., 2060→2062
    # So: 2025 (old period 2023) → 2027 (new period 2025); 2030→2032; 2035→2037; ...
    OLD_MID_TO_NEW_MID = {
        2025: 2027,  # old period 2023 → new period 2025
        2030: 2032,  # old period 2028 → new period 2030
        2035: 2037,
        2040: 2042,
        2045: 2047,
        2050: 2052,
    }

    # Our canonical MM.DD per month (matches CANONICAL_REPDAYS in
    # tools/rebuild_periods.py); used to remap upstream's per-period
    # cluster days to our canonical days, by month.
    CANONICAL_MONTH_DAY = {
        1: "01.22", 2: "02.08", 3: "03.21", 4: "04.11", 5: "05.22", 6: "06.16",
        7: "07.22", 8: "08.19", 9: "09.20", 10: "10.26", 11: "11.19", 12: "12.16",
    }

    def remap_ts(old_ts):
        parts = old_ts.split(".")
        if len(parts) != 3:
            return None
        try:
            old_year = int(parts[0])
            month = int(parts[1])
            new_year = OLD_MID_TO_NEW_MID.get(old_year)
            if new_year is None or month not in CANONICAL_MONTH_DAY:
                return None
            return f"{new_year}.{CANONICAL_MONTH_DAY[month]}"
        except ValueError:
            return None

    df["timeseries"] = df["timeseries"].map(remap_ts)
    df = df.dropna(subset=["timeseries"])
    # Aggregate any collisions (shouldn't happen within a period, but guard)
    df = df.groupby(["hydro_project", "timeseries"], as_index=False).agg({
        "hydro_min_flow_mw": "mean",
        "hydro_avg_flow_mw": "mean",
    })

    # Fallback: copy new periods 2020/2055/2060 from nearest
    NEAREST_FALLBACK_NEW_MID = {2022: 2027, 2057: 2052, 2062: 2052}
    extras = []
    for fallback_mid, src_mid in NEAREST_FALLBACK_NEW_MID.items():
        src_rows = df[df["timeseries"].str.startswith(f"{src_mid}.")].copy()
        src_rows["timeseries"] = src_rows["timeseries"].str.replace(
            f"{src_mid}.", f"{fallback_mid}.", regex=False)
        extras.append(src_rows)
    return pd.concat([df] + extras, ignore_index=True)


# ============================================================================
#  Section 6 — Upstream → filter (period-free)
# ============================================================================

def filter_load_zones():
    df = pd.read_csv(UPSTREAM_INPUTS / "load_zones.csv")
    return df[df["LOAD_ZONE"].isin(ZONES)].copy()


def filter_transmission_lines():
    df = pd.read_csv(UPSTREAM_INPUTS / "transmission_lines.csv")
    return df[df["trans_lz1"].isin(ZONES) & df["trans_lz2"].isin(ZONES)].copy()


def filter_gen_info():
    df = pd.read_csv(UPSTREAM_INPUTS / "gen_info.csv")
    return df[df["gen_load_zone"].isin(ZONES)].copy()


def filter_gen_build_predetermined(gen_info_df):
    """Filter to our projects, then collapse predetermined builds inside
    period 2020 (2020-2024) to build_year=2020 (the period_start convention).
    Upstream has some rows at build_year=2023 (upstream's old first
    period_start) that aren't valid in our 2020-anchored periods.
    """
    df = pd.read_csv(UPSTREAM_INPUTS / "gen_build_predetermined.csv")
    df = df[df["GENERATION_PROJECT"].isin(gen_info_df["GENERATION_PROJECT"])].copy()
    # Collapse any build_year ∈ (2020, 2024] to 2020
    inside = (df["build_year"] > 2020) & (df["build_year"] <= 2024)
    df.loc[inside, "build_year"] = 2020
    # Aggregate duplicates (sum capacity; max can_retire_early flag)
    df = df.groupby(["GENERATION_PROJECT", "build_year"], as_index=False).agg({
        "build_gen_predetermined": "sum",
        "gen_can_retire_early":   "max",
    })
    return df


def filter_gen_part_load_heat_rates(gen_info_df):
    df = pd.read_csv(UPSTREAM_INPUTS / "gen_part_load_heat_rates.csv")
    return df[df["GENERATION_PROJECT"].isin(gen_info_df["GENERATION_PROJECT"])].copy()


def filter_planning_reserve_requirement_zones():
    df = pd.read_csv(UPSTREAM_INPUTS / "planning_reserve_requirement_zones.csv")
    return df[df["LOAD_ZONE"].isin(ZONES)].copy()


def filter_planning_reserve_requirements(prr_zones_df):
    df = pd.read_csv(UPSTREAM_INPUTS / "planning_reserve_requirements.csv")
    return df[df["PLANNING_RESERVE_REQUIREMENTS"].isin(
        prr_zones_df["PLANNING_RESERVE_REQUIREMENTS"])].copy()


def filter_zone_to_regional_fuel_market():
    df = pd.read_csv(UPSTREAM_INPUTS / "zone_to_regional_fuel_market.csv")
    return df[df["load_zone"].isin(ZONES)].copy()


def filter_regional_fuel_markets(z2rfm_df):
    df = pd.read_csv(UPSTREAM_INPUTS / "regional_fuel_markets.csv")
    return df[df["regional_fuel_market"].isin(z2rfm_df["regional_fuel_market"])].copy()


# ============================================================================
#  Section 7 — Upstream → copy (with light edits)
# ============================================================================

def copy_fuels(): return pd.read_csv(UPSTREAM_INPUTS / "fuels.csv")
def copy_non_fuel_energy_sources(): return pd.read_csv(UPSTREAM_INPUTS / "non_fuel_energy_sources.csv")
def copy_trans_params(): return pd.read_csv(UPSTREAM_INPUTS / "trans_params.csv")


def updated_financials():
    df = pd.read_csv(UPSTREAM_INPUTS / "financials.csv")
    df["base_financial_year"] = BASE_FINANCIAL_YEAR
    return df


def copy_time_axis(target_dir):
    for f in ["periods.csv", "timeseries.csv", "timepoints.csv"]:
        shutil.copy(UPSTREAM_INPUTS / f, target_dir / f)


def copy_modules_txt(target_dir):
    shutil.copy(UPSTREAM_INPUTS / "modules.txt", target_dir / "modules.txt")


def copy_switch_inputs_version(target_dir):
    shutil.copy(UPSTREAM_INPUTS / "switch_inputs_version.txt",
                target_dir / "switch_inputs_version.txt")


def write_empty_total_capacity_limits(target_dir):
    pd.DataFrame(columns=["energy_sources", "period", "total_capacity_limit_mw"]
                 ).to_csv(target_dir / "total_capacity_limits.csv", index=False)


# ============================================================================
#  Section 8 — Main
# ============================================================================

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="Preview row counts; write no files")
    args = ap.parse_args()

    print()
    sheets = load_woodmac()

    # Need the new time-axis to drive loads + VRE CF
    periods_df    = pd.read_csv(UPSTREAM_INPUTS / "periods.csv")
    timepoints_df = pd.read_csv(UPSTREAM_INPUTS / "timepoints.csv")

    # Upstream filters first (gen_info drives many downstream filters)
    df_lz      = filter_load_zones()
    df_tl      = filter_transmission_lines()
    df_gen     = filter_gen_info()
    df_gbp     = filter_gen_build_predetermined(df_gen)
    df_gphr    = filter_gen_part_load_heat_rates(df_gen)
    df_prrz    = filter_planning_reserve_requirement_zones()
    df_prr     = filter_planning_reserve_requirements(df_prrz)
    df_z2rfm   = filter_zone_to_regional_fuel_market()
    df_rfm     = filter_regional_fuel_markets(df_z2rfm)

    # Upstream copy / light edit
    df_fuels   = copy_fuels()
    df_nfes    = copy_non_fuel_energy_sources()
    df_tp      = copy_trans_params()
    df_fin     = updated_financials()

    # Upstream filter + period remap
    df_gbc     = build_gen_build_costs(df_gen)
    df_fsc     = build_fuel_supply_curves(df_z2rfm)
    df_cp_      = build_capacity_plans()
    df_ht      = build_hydro_timeseries(df_gen)

    # Wood-Mac sourced — period
    df_peak    = build_zone_peak_demand(sheets)
    df_fc      = build_fuel_cost(sheets)
    df_cp      = build_carbon_policies(sheets)

    # Wood-Mac sourced — timepoint
    print("Building loads (6 zones × 648 tps)...")
    df_loads   = build_loads(sheets, periods_df, timepoints_df)
    print("Building variable_capacity_factors (VRE projects × 648 tps)...")
    df_vcf     = build_variable_capacity_factors(sheets, periods_df, timepoints_df, df_gen)

    summary = [
        # Wood-Mac sourced — period
        ("zone_coincident_peak_demand.csv", df_peak, "Wood Mac Demand:Peak Generation"),
        ("fuel_cost.csv",                  df_fc,   "Wood Mac Fuel prices + CPI deflator"),
        ("carbon_policies.csv",            df_cp,   "Wood Mac Emissions sum + trajectory"),
        # Wood-Mac sourced — timepoint
        ("loads.csv",                      df_loads,"Wood Mac annual demand × 2026 24h shape"),
        ("variable_capacity_factors.csv",  df_vcf,  "Wood Mac 2026 hourly / installed capacity"),
        # Upstream filter + period remap
        ("gen_build_costs.csv",            df_gbc,  "upstream filter + period remap 2023-2048→2025-2050"),
        ("fuel_supply_curves.csv",         df_fsc,  "upstream filter + period remap"),
        ("capacity_plans.csv",             df_cp_,  "upstream filter zones + period remap"),
        ("hydro_timeseries.csv",           df_ht,   "upstream filter + ts year remap"),
        # Upstream filter (period-free)
        ("load_zones.csv",                 df_lz,   "upstream filter ZONES"),
        ("transmission_lines.csv",         df_tl,   "upstream filter both endpoints"),
        ("gen_info.csv",                   df_gen,  "upstream filter gen_load_zone"),
        ("gen_build_predetermined.csv",    df_gbp,  "upstream filter project"),
        ("gen_part_load_heat_rates.csv",   df_gphr, "upstream filter project"),
        ("planning_reserve_requirement_zones.csv", df_prrz, "upstream filter LOAD_ZONE"),
        ("planning_reserve_requirements.csv",      df_prr,  "upstream filter PRR"),
        ("zone_to_regional_fuel_market.csv",       df_z2rfm,"upstream filter load_zone"),
        ("regional_fuel_markets.csv",              df_rfm,  "upstream filter market"),
        # Upstream copy
        ("fuels.csv",                      df_fuels, "upstream copy"),
        ("non_fuel_energy_sources.csv",    df_nfes,  "upstream copy"),
        ("trans_params.csv",               df_tp,    "upstream copy"),
        ("financials.csv",                 df_fin,   f"upstream copy + base_year→{BASE_FINANCIAL_YEAR}"),
    ]

    print()
    print(f"{'CSV file':45s} {'rows':>7s}  source")
    print("-" * 105)
    for name, df, src in summary:
        print(f"{name:45s} {len(df):>7d}  {src}")
    print()
    print("Time-axis (copy from inputs/):   periods.csv (9), timeseries.csv (108), timepoints.csv (648)")
    print("Boilerplate:                     modules.txt, switch_inputs_version.txt")
    print("Empty (header only):             total_capacity_limits.csv")

    if args.dry_run:
        print()
        print("--dry-run set; no files written.")
        return

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    for fname, df, _ in summary:
        df.to_csv(TARGET_DIR / fname, index=False)
    write_empty_total_capacity_limits(TARGET_DIR)
    copy_time_axis(TARGET_DIR)
    copy_modules_txt(TARGET_DIR)
    copy_switch_inputs_version(TARGET_DIR)

    print()
    print(f"Wrote {len(summary) + 5} files to {TARGET_DIR}/")
    print()
    print("Next: tools/validate_scenario.py (Phase B) — or directly")
    print("  cd /Users/meichengcheng/switch-china && switch solve \\")
    print(f"     --inputs-dir {TARGET_DIR} --outputs-dir scenarios/shanghai/outputs \\")
    print('     --solver appsi_highs --solver-options-string "solver=ipm run_crossover=off"')


if __name__ == "__main__":
    main()
