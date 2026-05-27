#!/usr/bin/env python3
"""
Smoke-test a scenario by running `switch solve` with HiGHS time_limit=1.
Construction (load inputs + create Pyomo instance) runs in full and is the
real validation; the solver runs only ~1 second and we ignore its output.

If construction succeeds, the model is consistent and ready for a full solve.

Usage:
  python tools/validate_scenario.py --inputs-dir scenarios/shanghai/inputs
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inputs-dir", required=True)
    ap.add_argument("--switch-bin",
                    default=shutil.which("switch"),
                    help="Path to the switch CLI binary "
                         "(default: first `switch` on PATH — activate the conda env first)")
    args = ap.parse_args()

    if not args.switch_bin:
        sys.exit("FATAL: `switch` not found on PATH. Activate the conda env "
                 "(`conda activate switch`) or pass --switch-bin explicitly.")

    inputs_dir = Path(args.inputs_dir)
    if not inputs_dir.is_dir():
        sys.exit(f"FATAL: {inputs_dir} is not a directory")

    outputs_dir = Path(tempfile.mkdtemp(prefix="switch_validate_"))

    # Use --no-save-solution + time_limit=1 so the solver returns ~immediately
    # after construction completes. Construction is what we want to validate.
    cmd = [
        args.switch_bin, "solve",
        "--inputs-dir", str(inputs_dir),
        "--outputs-dir", str(outputs_dir),
        "--solver", "appsi_highs",
        "--solver-options-string", "solver=ipm run_crossover=off time_limit=1",
        "--no-save-solution",
        "--verbose",
    ]
    print("Running:", " ".join(cmd))
    print()
    # Stream output live so user sees construction progress
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print()
        print(f"[FAIL] exit code {result.returncode} -- construction or solver failed.")
        sys.exit(result.returncode)
    print()
    print("[OK] Construction succeeded (solver ran briefly under time_limit=1).")


if __name__ == "__main__":
    main()
