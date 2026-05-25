#!/usr/bin/env python3
"""
Build scenarios/shanghai/inputs/ for the 6-zone Shanghai scenario.

Pulls data from:
- Wood Mackenzie APAC H2 2025 Excel (inputs/raw/...): historical ≤2025, then
  extrapolated to 2030-2060 with growth assumptions in the CONSTANTS block.
- Upstream switch-china inputs/ (filtered to the 6 zones): for zone-free /
  network / generation-fleet metadata that Wood Mac doesn't provide.

Zones (plan Path B):
  Shanghai + Jiangsu + Zhejiang + Anhui + Fujian + Sichuan

Per-CSV handling:
  Wood-Mac sourced (done in this version, v0.2):
    zone_coincident_peak_demand.csv, fuel_cost.csv, carbon_policies.csv
  Upstream-filter (done in v0.2):
    load_zones, transmission_lines, gen_info, gen_build_predetermined,
    gen_part_load_heat_rates, planning_reserve_requirement_zones,
    planning_reserve_requirements, zone_to_regional_fuel_market,
    regional_fuel_markets
  Upstream-copy (done in v0.2):
    fuels, non_fuel_energy_sources, trans_params,
    financials (with base_financial_year updated to 2020 per plan D-7),
    periods, timeseries, timepoints, modules.txt, switch_inputs_version.txt
  Header-only / empty (placeholder until C.2.b round 2):
    capacity_plans, total_capacity_limits, gen_build_costs, fuel_supply_curves,
    loads, variable_capacity_factors, hydro_timeseries

Usage:
  python tools/import_woodmac.py --dry-run   # print summary, write nothing
  python tools/import_woodmac.py             # write scenarios/shanghai/inputs/
"""

import argparse
import shutil
import sys
from pathlib import Path

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

# --- Demand annual growth past 2025 (user said "min 2-3%/yr")
DEMAND_GROWTH_PER_PERIOD = {
    2030: 0.030, 2035: 0.025, 2040: 0.015, 2045: 0.005,
    2050: 0.002, 2055: 0.001, 2060: 0.000,
}

# --- Fuel cost real-USD annual growth past 2025
FUEL_COST_GROWTH = {"Coal": 0.005, "Gas": 0.010, "Diesel": 0.015, "FuelOil": 0.015}

# --- US CPI deflator (BLS): Wood Mac 2025 nominal USD → real 2020 USD
CPI_2025_TO_2020_DEFLATOR = 0.824

# --- Carbon cap trajectory (multiplier vs 2025 actual)
CARBON_TRAJECTORY_MULT = {
    2020: None, 2025: 1.000, 2030: 1.030, 2035: 0.875, 2040: 0.715,
    2045: 0.550, 2050: 0.385, 2055: 0.220, 2060: 0.150,
}
CARBON_PRICE_PER_TCO2 = 0.0


# ============================================================================
#  Wood Mac helpers
# ============================================================================

def load_woodmac():
    print(f"Loading {WOODMAC_XLSX.name} ({WOODMAC_XLSX.stat().st_size / 1024 / 1024:.1f} MB)...")
    return {
        "Demand":      pd.read_excel(WOODMAC_XLSX, sheet_name="Demand",      header=5),
        "Fuel prices": pd.read_excel(WOODMAC_XLSX, sheet_name="Fuel prices", header=5),
        "Emissions":   pd.read_excel(WOODMAC_XLSX, sheet_name="Emissions",   header=5),
    }


def _wm_row(df, zone, **kw):
    mask = (df["Country"] == "China") & (df["Zone"] == zone)
    for k, v in kw.items():
        mask = mask & (df[k] == v)
    return df[mask]


def _project_from(value_2025, period_starts_after_2025):
    out = {}
    prev_val = value_2025
    prev_year = 2025
    for ps in period_starts_after_2025:
        growth = DEMAND_GROWTH_PER_PERIOD[ps]
        years = ps - prev_year
        new_val = prev_val * (1 + growth) ** years
        out[ps] = new_val
        prev_val = new_val
        prev_year = ps
    return out


# ============================================================================
#  Wood Mac → period CSVs
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
        peaks.update(_project_from(v_2025, [2030, 2035, 2040, 2045, 2050, 2055, 2060]))
        for ps in PERIOD_STARTS:
            rows.append((z, ps, peaks[ps]))
    return pd.DataFrame(rows, columns=["LOAD_ZONE", "PERIOD", "zone_expected_coincident_peak_demand"])


def build_fuel_cost(sheets):
    df_fp = sheets["Fuel prices"]
    rows = []
    for z in ZONES:
        for wm_fuel in ["Coal", "Gas", "Diesel", "FuelOil"]:
            row = _wm_row(df_fp, z, Fuel=wm_fuel)
            if row.empty:
                continue
            v_2020 = float(row[2020].values[0])
            v_2025 = float(row[2025].values[0]) * CPI_2025_TO_2020_DEFLATOR
            costs = {2020: v_2020, 2025: v_2025}
            prev = v_2025
            growth = FUEL_COST_GROWTH.get(wm_fuel, 0.0)
            for ps in [2030, 2035, 2040, 2045, 2050, 2055, 2060]:
                prev = prev * (1 + growth) ** 5
                costs[ps] = prev
            for ps in PERIOD_STARTS:
                rows.append((z, wm_fuel, ps, costs[ps]))
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
        if ps == 2020:
            cap_mt = sum_2020_mt
        elif ps == 2025:
            cap_mt = sum_2025_mt
        else:
            cap_mt = sum_2025_mt * CARBON_TRAJECTORY_MULT[ps]
        rows.append((ps, cap_mt * 1e6, CARBON_PRICE_PER_TCO2))
    return pd.DataFrame(rows, columns=["PERIOD", "carbon_cap_tco2_per_yr", "carbon_cost_dollar_per_tco2"])


# ============================================================================
#  Upstream → filtered CSVs
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
    df = pd.read_csv(UPSTREAM_INPUTS / "gen_build_predetermined.csv")
    return df[df["GENERATION_PROJECT"].isin(gen_info_df["GENERATION_PROJECT"])].copy()


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
#  Upstream → copy (with light edits)
# ============================================================================

def copy_fuels():
    return pd.read_csv(UPSTREAM_INPUTS / "fuels.csv")


def copy_non_fuel_energy_sources():
    return pd.read_csv(UPSTREAM_INPUTS / "non_fuel_energy_sources.csv")


def copy_trans_params():
    return pd.read_csv(UPSTREAM_INPUTS / "trans_params.csv")


def updated_financials():
    df = pd.read_csv(UPSTREAM_INPUTS / "financials.csv")
    df["base_financial_year"] = BASE_FINANCIAL_YEAR
    return df


# ============================================================================
#  Empty / header-only CSVs (placeholders for round 2)
# ============================================================================

EMPTY_SCHEMAS = {
    "capacity_plans.csv":        ["energy_sources", "load_zones", "period", "planned_capacity_mw"],
    "total_capacity_limits.csv": ["energy_sources", "period", "total_capacity_limit_mw"],
    "gen_build_costs.csv":       ["GENERATION_PROJECT", "build_year", "gen_overnight_cost",
                                  "gen_fixed_om", "gen_storage_energy_overnight_cost"],
    "fuel_supply_curves.csv":    ["regional_fuel_market", "period", "tier",
                                  "unit_cost", "max_avail_at_cost"],
    "loads.csv":                 ["LOAD_ZONE", "TIMEPOINT", "zone_demand_mw"],
    "variable_capacity_factors.csv": ["GENERATION_PROJECT", "timepoint", "gen_max_capacity_factor"],
    "hydro_timeseries.csv":      ["hydro_project", "timeseries", "hydro_min_flow_mw", "hydro_avg_flow_mw"],
}


def write_empty(target_dir, fname, columns):
    pd.DataFrame(columns=columns).to_csv(target_dir / fname, index=False)


# ============================================================================
#  modules.txt + switch_inputs_version.txt + time-axis copy
# ============================================================================

def copy_time_axis(target_dir):
    for f in ["periods.csv", "timeseries.csv", "timepoints.csv"]:
        shutil.copy(UPSTREAM_INPUTS / f, target_dir / f)


def copy_modules_txt(target_dir):
    shutil.copy(UPSTREAM_INPUTS / "modules.txt", target_dir / "modules.txt")


def copy_switch_inputs_version(target_dir):
    shutil.copy(UPSTREAM_INPUTS / "switch_inputs_version.txt",
                target_dir / "switch_inputs_version.txt")


# ============================================================================
#  Main
# ============================================================================

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="Preview row counts; write no files")
    args = ap.parse_args()

    print()
    sheets = load_woodmac()

    # Wood-Mac sourced
    df_peak    = build_zone_peak_demand(sheets)
    df_fc      = build_fuel_cost(sheets)
    df_cp      = build_carbon_policies(sheets)

    # Upstream filter
    df_lz      = filter_load_zones()
    df_tl      = filter_transmission_lines()
    df_gen     = filter_gen_info()
    df_gbp     = filter_gen_build_predetermined(df_gen)
    df_gphr    = filter_gen_part_load_heat_rates(df_gen)
    df_prrz    = filter_planning_reserve_requirement_zones()
    df_prr     = filter_planning_reserve_requirements(df_prrz)
    df_z2rfm   = filter_zone_to_regional_fuel_market()
    df_rfm     = filter_regional_fuel_markets(df_z2rfm)

    # Upstream copy
    df_fuels   = copy_fuels()
    df_nfes    = copy_non_fuel_energy_sources()
    df_tp      = copy_trans_params()
    df_fin     = updated_financials()

    summary = [
        # Wood-Mac sourced
        ("zone_coincident_peak_demand.csv", df_peak, "Wood Mac Demand:Peak Generation"),
        ("fuel_cost.csv",                  df_fc,   "Wood Mac Fuel prices + CPI deflator"),
        ("carbon_policies.csv",            df_cp,   "Wood Mac Emissions sum + trajectory"),
        # Upstream filter
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
    print(f"{'CSV file':45s} {'rows':>6s}  source")
    print("-" * 100)
    for name, df, src in summary:
        print(f"{name:45s} {len(df):>6d}  {src}")
    print()
    print("Time-axis (copy from inputs/):  periods.csv (9), timeseries.csv (108), timepoints.csv (648)")
    print("Boilerplate:                    modules.txt, switch_inputs_version.txt")
    print()
    print("PLACEHOLDER (empty, header-only — round 2 will fill):")
    for fname in EMPTY_SCHEMAS:
        print(f"  {fname}")

    if args.dry_run:
        print()
        print("--dry-run set; no files written.")
        return

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    for fname, df, _ in summary:
        df.to_csv(TARGET_DIR / fname, index=False)
    for fname, columns in EMPTY_SCHEMAS.items():
        write_empty(TARGET_DIR, fname, columns)
    copy_time_axis(TARGET_DIR)
    copy_modules_txt(TARGET_DIR)
    copy_switch_inputs_version(TARGET_DIR)

    print()
    print(f"Wrote {len(summary) + len(EMPTY_SCHEMAS) + 5} files to {TARGET_DIR}/")
    print("Next: run tools/import_woodmac.py round 2 to fill the placeholder CSVs.")


if __name__ == "__main__":
    main()
