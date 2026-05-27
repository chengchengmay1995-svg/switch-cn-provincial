#!/usr/bin/env python3
"""
Apply technology cost-learning curves to gen_build_costs.csv.

Why: upstream switch-china-open-model has flat overnight costs across all
build_years (see tools/import_woodmac.py:439 "for first pass we keep them").
That makes renewables permanently uncompetitive vs coal/nuclear — see
scenarios/shanghai/results_archive/v0.1/README.md root cause B.

What this does:
  For each (gen_tech, build_year) row, multiply gen_overnight_cost and
  gen_fixed_om by a tech-specific factor (anchored to 2020 = 100%).
  For Battery_Storage, also set gen_storage_energy_overnight_cost using
  BNEF Battery Cost Outlook 2024 trajectory (was 0 in upstream).

  Mature technologies (Coal, Gas, Nuclear) keep flat costs.

Sources (see docs/cost_curve_assumptions.md for full citation trail):
  PV         : BNEF NEO 2024 + IEA WEO 2024 STEPS China
  Wind       : NREL ATB 2024 Moderate (US baseline, trajectory shape)
  Battery    : BNEF Battery Cost Outlook 2024

Usage:
  python tools/apply_cost_curves.py --inputs-dir scenarios/shanghai/inputs
  python tools/apply_cost_curves.py --inputs-dir scenarios/shanghai/inputs --dry-run
"""

import argparse
import csv
from pathlib import Path

# Cost trajectory multipliers (2020 baseline = 1.0)
# Periods: 2020, 2025, 2030, 2035, 2040, 2045, 2050, 2055, 2060
CURVES = {
    # Solar PV — BNEF NEO 2024 + IEA WEO 2024 STEPS China
    "Central_PV":     [1.00, 0.75, 0.58, 0.50, 0.45, 0.42, 0.40, 0.39, 0.38],
    "Commercial_PV":  [1.00, 0.75, 0.58, 0.50, 0.45, 0.42, 0.40, 0.39, 0.38],
    "Residential_PV": [1.00, 0.75, 0.58, 0.50, 0.45, 0.42, 0.40, 0.39, 0.38],
    # Wind onshore — NREL ATB 2024 Moderate
    "Wind":           [1.00, 0.92, 0.84, 0.79, 0.75, 0.73, 0.72, 0.71, 0.71],
    # Wind offshore — NREL ATB 2024 Moderate fixed-bottom
    "Offshore_Wind":  [1.00, 0.88, 0.75, 0.67, 0.60, 0.56, 0.53, 0.52, 0.51],
    # Battery storage power capacity — BNEF Battery Cost Outlook 2024
    "Battery_Storage":[1.00, 0.75, 0.55, 0.45, 0.40, 0.38, 0.35, 0.34, 0.33],
}

# Battery storage energy cost trajectory ($/MWh) — BNEF BCO 2024
# Pack-level; absolute values, not multipliers (upstream had 0).
BATTERY_ENERGY_COST = {
    2020: 400_000,
    2025: 240_000,
    2030: 160_000,
    2035: 120_000,
    2040: 100_000,
    2045:  85_000,
    2050:  75_000,
    2055:  72_000,
    2060:  70_000,
}

PERIODS = [2020, 2025, 2030, 2035, 2040, 2045, 2050, 2055, 2060]
PERIOD_INDEX = {p: i for i, p in enumerate(PERIODS)}


def load_gen_tech_map(gen_info_path):
    """Return dict GENERATION_PROJECT -> gen_tech."""
    m = {}
    with open(gen_info_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            m[row["GENERATION_PROJECT"]] = row["gen_tech"]
    return m


def apply_curves(rows, tech_map):
    """Mutate rows in place. Return summary stats."""
    touched = 0
    storage_energy_set = 0
    by_tech = {}

    for row in rows:
        proj = row["GENERATION_PROJECT"]
        tech = tech_map.get(proj)
        if tech is None:
            continue

        try:
            byr = int(row["build_year"])
        except ValueError:
            continue
        if byr not in PERIOD_INDEX:
            # Historical build year (1968-2019); leave alone
            continue

        idx = PERIOD_INDEX[byr]

        # Power capex + fixed O&M
        if tech in CURVES:
            mult = CURVES[tech][idx]
            for col in ("gen_overnight_cost", "gen_fixed_om"):
                if row[col] not in ("", ".", None):
                    row[col] = str(int(round(float(row[col]) * mult)))
            touched += 1
            by_tech[tech] = by_tech.get(tech, 0) + 1

        # Battery storage energy capex
        if tech == "Battery_Storage":
            row["gen_storage_energy_overnight_cost"] = str(BATTERY_ENERGY_COST[byr])
            storage_energy_set += 1

    return {
        "rows_touched": touched,
        "storage_energy_set": storage_energy_set,
        "by_tech": by_tech,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inputs-dir", required=True,
                    help="Scenario inputs directory (e.g., scenarios/shanghai/inputs)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print stats only; do not write")
    args = ap.parse_args()

    inputs = Path(args.inputs_dir)
    gbc_path = inputs / "gen_build_costs.csv"
    gi_path = inputs / "gen_info.csv"

    tech_map = load_gen_tech_map(gi_path)
    print(f"Loaded {len(tech_map)} project -> gen_tech mappings from {gi_path}")

    with open(gbc_path, newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    print(f"Loaded {len(rows)} rows from {gbc_path}")

    stats = apply_curves(rows, tech_map)
    print(f"Touched {stats['rows_touched']} rows; set storage energy cost on "
          f"{stats['storage_energy_set']} rows")
    print("By tech:")
    for t, n in sorted(stats["by_tech"].items()):
        print(f"  {t}: {n}")

    if args.dry_run:
        print("\n--dry-run set; not writing.")
        return

    with open(gbc_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nWrote {len(rows)} rows back to {gbc_path}")
    print("\nNext: re-solve and compare against v0.2b.")


if __name__ == "__main__":
    main()
