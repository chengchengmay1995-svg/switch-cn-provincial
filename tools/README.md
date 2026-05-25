# tools/

Helper scripts for the scenario-based workflow. Built incrementally as the
plan progresses.

## Planned scripts

| Script | Phase | Purpose |
|---|---|---|
| `rebuild_periods.py` | C | Rebuild `inputs/periods.csv`, `timeseries.csv`, `timepoints.csv` for the 2020–2060 9-period horizon. Writes `docs/data_requirements.md` listing what other CSVs need re-filling. |
| `build_scenario.py` | B | Read `scenarios/<province>/scenario.yaml`, slice base `inputs/` to the focal+adjacent+UHV-partner zones, write `scenarios/<province>/inputs/`. |
| `validate_scenario.py` | B | Smoke-test a scenario's inputs: load Pyomo model, build instance, run `validate_time_weights`. Optional `--solve-quick` runs HiGHS for ≤60s. |
| `update_base.py` | C ongoing | Helper for the data-update workflow (CHANGES.md / `docs/` entries; re-runs build for all scenarios). |
| `compare_2025.py` | E | Compare model's 2025-period outputs vs user-provided 2025 actuals; write report to `docs/results_calibration.md`. |

Run all scripts from the repo root with the `switch` conda env activated.
