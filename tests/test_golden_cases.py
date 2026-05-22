"""Pytest entrypoint for the golden-case replay machinery.

The runner script (``scripts/run_golden_cases.py``) is also the
canonical CLI; this file wraps it so the golden cases participate in
the default ``pytest -q`` run without needing extra shell commands.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUN_SCRIPT = REPO_ROOT / "scripts" / "run_golden_cases.py"
CASES_DIR = REPO_ROOT / "benchmarks" / "golden_cases"


def test_runner_script_exists():
    assert RUN_SCRIPT.exists()


def test_cases_directory_has_required_coverage():
    """The documented probe matrix must be reflected on disk."""
    assert CASES_DIR.exists()
    names = {p.stem for p in CASES_DIR.glob("*.json") if p.name != "manifest.json"}
    required = {
        "all_probes_supplied",
        "missing_strict_schema",
        "monotonicity_not_supplied",
        "token_counter_exact",
        "token_counter_heuristic",
        "strict_schema_failure",
        "noise_floor_supplied",
        "noise_floor_missing",
    }
    missing = required - names
    assert not missing, f"required golden cases missing: {sorted(missing)}"


def test_run_all_golden_cases_pass():
    result = subprocess.run(
        [sys.executable, str(RUN_SCRIPT), "--check"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, (
        f"golden cases failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
