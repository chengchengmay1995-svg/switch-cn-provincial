#!/usr/bin/env python3
"""
Import historical data from Wood Mackenzie APAC Power Strategic Planning Outlook
H2 2025 (the Excel in inputs/raw/) into scenarios/shanghai/inputs/.

Strict rule (per user instruction): only Wood Mac values for **years ≤ 2025**
may flow into the model directly. For periods 2030-2060, this tool applies
**baked-in projection assumptions** (visible in the CONSTANTS block below);
user reviews + adjusts those numbers before re-running.

First pass (this version) handles 3 CSVs:
  - zone_coincident_peak_demand.csv  (peak demand MW per zone × period)
  - fuel_cost.csv                    (fuel price $/MMBTU per zone × fuel × period)
  - carbon_policies.csv              (aggregate fossil-CO2 cap for the 6 zones)

Scope: 6 zones (plan Path B):
  Shanghai + Jiangsu + Zhejiang + Anhui + Fujian + Sichuan

Usage:
  python tools/import_woodmac.py --dry-run         # preview, write nothing
  python tools/import_woodmac.py                   # write to scenarios/shanghai/inputs/
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

# ============================================================================
#  Configuration — user reviews these before approving the first real run
# ============================================================================

WOODMAC_XLSX = Path("inputs/raw/apac-p-r-strategic-planning-outlook-h2-2025_data (2).xlsx")
TARGET_DIR = Path("scenarios/shanghai/inputs")

ZONES = ["Shanghai", "Jiangsu", "Zhejiang", "Anhui", "Fujian", "Sichuan"]
PERIOD_STARTS = [2020, 2025, 2030, 2035, 2040, 2045, 2050, 2055, 2060]

# --- Demand growth (2026 → 2060) — user said "min 2-3%/yr"
#     applied compounding from prior period's last year (2025 onward)
DEMAND_GROWTH_PER_PERIOD = {
    # period_start: annual growth rate during the 5 years leading up to it
    2030: 0.030,   # 2026-2030: 3.0%/yr (continued growth + electrification)
    2035: 0.025,   # 2031-2035: 2.5%/yr
    2040: 0.015,   # 2036-2040: 1.5%/yr (peaking)
    2045: 0.005,   # 2041-2045: 0.5%/yr
    2050: 0.002,   # 2046-2050: 0.2%/yr
    2055: 0.001,   # 2051-2055: 0.1%/yr
    2060: 0.000,   # 2056-2060: flat
}

# --- Fuel cost real-terms growth (per year) past 2025
FUEL_COST_GROWTH = {
    "Coal":    0.005,   # +0.5%/yr real (transition + scarcity pressure)
    "Gas":     0.010,   # +1.0%/yr real
    "Diesel":  0.015,
    "FuelOil": 0.015,
}

# --- US CPI deflator: convert Wood Mac 2025 nominal USD → real 2020 USD
#     (plan decision D-7: all costs in real 2020 USD)
#     US BLS CPI-U: 2020=258.811, 2025e≈314.0 → deflator = 258.811/314.0
CPI_2025_TO_2020_DEFLATOR = 0.824

# --- Carbon cap trajectory (multiplier vs 2025 actual)
#     6-zone aggregate fossil-CO2. Default = peak ~2030, linear decline to ~15%
#     of 2025 by 2060 (consistent with China 30·60 framework + East China lead).
CARBON_TRAJECTORY_MULT = {
    2020: None,    # use Wood Mac 2020 actual
    2025: 1.000,   # use Wood Mac 2025 actual
    2030: 1.030,   # peak: +3% vs 2025
    2035: 0.875,
    2040: 0.715,
    2045: 0.550,
    2050: 0.385,
    2055: 0.220,
    2060: 0.150,
}

# Cap-only mode (no carbon shadow price added directly; cap drives behavior)
CARBON_PRICE_PER_TCO2 = 0.0


# ============================================================================
#  Wood Mac extraction helpers
# ============================================================================

def load_sheets():
    print(f"Loading {WOODMAC_XLSX.name} ({WOODMAC_XLSX.stat().st_size / 1024 / 1024:.1f} MB)...")
    return {
        "Demand":      pd.read_excel(WOODMAC_XLSX, sheet_name="Demand",      header=5),
        "Fuel prices": pd.read_excel(WOODMAC_XLSX, sheet_name="Fuel prices", header=5),
        "Emissions":   pd.read_excel(WOODMAC_XLSX, sheet_name="Emissions",   header=5),
    }


def _wm_row(df, zone, **kw):
    """Filter Wood Mac df to China + zone + arbitrary key/value pairs."""
    mask = (df["Country"] == "China") & (df["Zone"] == zone)
    for k, v in kw.items():
        mask = mask & (df[k] == v)
    return df[mask]


def _project_from(value_2025, period_starts_after_2025):
    """Apply DEMAND_GROWTH_PER_PERIOD compounding from 2025 forward.
       Returns dict {period_start: projected_value}."""
    out = {}
    prev_val = value_2025
    prev_year = 2025
    for ps in period_starts_after_2025:
        growth = DEMAND_GROWTH_PER_PERIOD[ps]
        years = ps - prev_year   # always 5 for our uniform schedule
        new_val = prev_val * (1 + growth) ** years
        out[ps] = new_val
        prev_val = new_val
        prev_year = ps
    return out


# ============================================================================
#  CSV builders
# ============================================================================

def build_zone_peak_demand(sheets):
    """zone_coincident_peak_demand.csv columns: LOAD_ZONE, PERIOD, zone_expected_coincident_peak_demand."""
    df_d = sheets["Demand"]
    rows = []
    for z in ZONES:
        row = _wm_row(df_d, z, Description="Peak Generation")
        if row.empty:
            sys.exit(f"FATAL: no 'Peak Generation' row for {z} in Wood Mac Demand sheet")
        v_2020 = float(row[2020].values[0])
        v_2025 = float(row[2025].values[0])
        peaks = {2020: v_2020, 2025: v_2025}
        peaks.update(_project_from(v_2025, [2030, 2035, 2040, 2045, 2050, 2055, 2060]))
        for ps in PERIOD_STARTS:
            rows.append((z, ps, peaks[ps]))
    return pd.DataFrame(rows, columns=["LOAD_ZONE", "PERIOD", "zone_expected_coincident_peak_demand"])


def build_fuel_cost(sheets):
    """fuel_cost.csv columns: load_zone, fuel, period, fuel_cost ($/MMBTU 2020 USD)."""
    df_fp = sheets["Fuel prices"]
    rows = []
    for z in ZONES:
        for wm_fuel in ["Coal", "Gas", "Diesel", "FuelOil"]:
            row = _wm_row(df_fp, z, Fuel=wm_fuel)
            if row.empty:
                continue  # not all zones have all fuels
            v_2020 = float(row[2020].values[0])               # nominal 2020 USD = real 2020 USD (by definition)
            v_2025 = float(row[2025].values[0]) * CPI_2025_TO_2020_DEFLATOR  # deflate nominal → real 2020
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
    """carbon_policies.csv columns: PERIOD, carbon_cap_tco2_per_yr, carbon_cost_dollar_per_tco2.

    6-zone aggregate fossil-CO2. Wood Mac Emissions sheet is in Mt CO2.
    """
    df_e = sheets["Emissions"]
    sum_2020_mt = 0.0
    sum_2025_mt = 0.0
    for z in ZONES:
        rows = _wm_row(df_e, z)  # all fuels for this zone
        for _, r in rows.iterrows():
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
        rows.append((ps, cap_mt * 1e6, CARBON_PRICE_PER_TCO2))  # Mt → t
    return pd.DataFrame(rows, columns=["PERIOD", "carbon_cap_tco2_per_yr", "carbon_cost_dollar_per_tco2"])


# ============================================================================
#  Main
# ============================================================================

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="Preview only; write no files")
    args = ap.parse_args()

    sheets = load_sheets()
    df_peak = build_zone_peak_demand(sheets)
    df_fc   = build_fuel_cost(sheets)
    df_cp   = build_carbon_policies(sheets)

    print()
    print("=" * 78)
    print("zone_coincident_peak_demand.csv  (all 54 rows: 6 zones × 9 periods)")
    print("=" * 78)
    print(df_peak.to_string(index=False, float_format=lambda x: f"{x:,.0f}"))

    print()
    print("=" * 78)
    print(f"fuel_cost.csv  ({len(df_fc)} rows, sample = Shanghai only)")
    print("=" * 78)
    print(df_fc[df_fc["load_zone"]=="Shanghai"].to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    print(f"  ({len(df_fc)} rows total — Shanghai shown; other zones follow same pattern)")

    print()
    print("=" * 78)
    print("carbon_policies.csv  (9 periods, 6-zone aggregate Mt CO2 → tCO2)")
    print("=" * 78)
    print(df_cp.assign(
        cap_Mt=lambda d: d["carbon_cap_tco2_per_yr"] / 1e6
    ).to_string(index=False, float_format=lambda x: f"{x:,.1f}"))

    if args.dry_run:
        print()
        print("--dry-run set; no files written.")
        return

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    df_peak.to_csv(TARGET_DIR / "zone_coincident_peak_demand.csv", index=False)
    df_fc.to_csv(TARGET_DIR / "fuel_cost.csv", index=False)
    df_cp.to_csv(TARGET_DIR / "carbon_policies.csv", index=False)

    print()
    print(f"Wrote 3 CSVs to {TARGET_DIR}/")
    print("  zone_coincident_peak_demand.csv")
    print("  fuel_cost.csv")
    print("  carbon_policies.csv")


if __name__ == "__main__":
    main()
