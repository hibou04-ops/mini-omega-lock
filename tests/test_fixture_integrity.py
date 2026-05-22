"""Fixture-integrity guard.

The committed manifest must verify cleanly. Tampering with any case
file (or with the manifest itself) must trip the check. Both halves
are pinned here.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "verify_fixture_integrity.py"
CASES_DIR = REPO_ROOT / "benchmarks" / "golden_cases"
MANIFEST = CASES_DIR / "manifest.json"


def test_manifest_verifies_clean():
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, (
        f"committed manifest failed verification:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_manifest_format_marker_present():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest.get("format", "").startswith("mini-omega-lock fixture-integrity")
    assert "canonicalisation" in manifest
    assert "files" in manifest and len(manifest["files"]) >= 1


def test_tampering_with_a_case_is_detected(tmp_path):
    """Mutate a fixture in a sandbox copy of the repo and prove the
    check flags it. We do NOT mutate the real repo — the tamper is
    confined to a copy."""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    # Mirror just enough of the layout for the script to find files.
    (sandbox / "benchmarks" / "golden_cases").mkdir(parents=True)
    (sandbox / "scripts").mkdir()
    shutil.copy(SCRIPT, sandbox / "scripts" / SCRIPT.name)
    for src in CASES_DIR.iterdir():
        shutil.copy(src, sandbox / "benchmarks" / "golden_cases" / src.name)

    # Tamper one case file.
    victim = sandbox / "benchmarks" / "golden_cases" / "all_probes_supplied.json"
    parsed = json.loads(victim.read_text(encoding="utf-8"))
    parsed["description"] = "tampered description"
    victim.write_text(json.dumps(parsed, indent=2), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(sandbox / "scripts" / SCRIPT.name)],
        capture_output=True,
        text=True,
        cwd=sandbox,
    )
    assert result.returncode == 1
    assert "hash drift" in result.stderr or "FAILED" in result.stderr


def test_write_then_verify_roundtrip(tmp_path):
    sandbox = tmp_path / "sandbox"
    (sandbox / "benchmarks" / "golden_cases").mkdir(parents=True)
    (sandbox / "scripts").mkdir()
    shutil.copy(SCRIPT, sandbox / "scripts" / SCRIPT.name)
    for src in CASES_DIR.iterdir():
        if src.name == "manifest.json":
            continue
        shutil.copy(src, sandbox / "benchmarks" / "golden_cases" / src.name)

    # No manifest yet -> verify should fail.
    pre = subprocess.run(
        [sys.executable, str(sandbox / "scripts" / SCRIPT.name)],
        capture_output=True,
        text=True,
        cwd=sandbox,
    )
    assert pre.returncode == 1

    # --write builds one.
    write = subprocess.run(
        [sys.executable, str(sandbox / "scripts" / SCRIPT.name), "--write"],
        capture_output=True,
        text=True,
        cwd=sandbox,
    )
    assert write.returncode == 0

    # Subsequent verify passes.
    post = subprocess.run(
        [sys.executable, str(sandbox / "scripts" / SCRIPT.name)],
        capture_output=True,
        text=True,
        cwd=sandbox,
    )
    assert post.returncode == 0
