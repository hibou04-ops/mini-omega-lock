"""Tests for ``scripts/check_repo_consistency.py``.

These tests guard the checker's *detection* surface rather than the
current state of the repo — they create temp content with known drift,
re-run each individual check function against it, and assert the check
flags the right kind of issue. The committed-repo green path is covered
by the integration test at the bottom.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_repo_consistency.py"


def _load_module():
    # The module defines @dataclass classes. When loaded via
    # spec_from_file_location, the dataclass decorator inspects
    # sys.modules[cls.__module__] to resolve forward refs, so the
    # module MUST be registered in sys.modules before exec_module
    # or we hit ``AttributeError: 'NoneType' object has no attribute
    # '__dict__'`` deep inside dataclasses.py.
    spec = importlib.util.spec_from_file_location("check_repo", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["check_repo"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_module_loads_and_exposes_checks():
    mod = _load_module()
    assert callable(mod.main)
    assert isinstance(mod.CHECKS, list)
    assert len(mod.CHECKS) >= 5


def test_running_on_committed_repo_returns_zero():
    """The full checker against the committed tree must pass — this is
    the only end-to-end assertion we can make without polluting the repo."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, (
        "consistency check on committed tree failed:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_version_check_flags_drift():
    mod = _load_module()
    issues: list = []
    mod.check_version_consistency(
        facts={
            "version": "0.4.0",
            "init_version": "0.3.0",
        },
        issues=issues,
    )
    assert len(issues) == 1
    assert "version drift" in issues[0].message


def test_version_check_passes_when_in_sync():
    mod = _load_module()
    issues: list = []
    mod.check_version_consistency(
        facts={"version": "1.2.3", "init_version": "1.2.3"},
        issues=issues,
    )
    assert issues == []


def test_mcp_tool_count_claim_check_flags_wrong_number(tmp_path, monkeypatch):
    mod = _load_module()
    # Point the checker at a synthetic README so we don't touch the real one.
    bad_readme = tmp_path / "README.md"
    bad_readme.write_text("This package exposes five tools to agents.\n", encoding="utf-8")

    monkeypatch.setattr(mod, "README", bad_readme)
    monkeypatch.setattr(mod, "EASY_EN", tmp_path / "EASY_README.md")
    monkeypatch.setattr(mod, "EASY_KR", tmp_path / "EASY_README_KR.md")
    monkeypatch.setattr(mod, "README_KR", tmp_path / "README_KR.md")
    monkeypatch.setattr(mod, "INIT_PATH", tmp_path / "init.py")
    monkeypatch.setattr(mod, "MCP_INIT_PATH", tmp_path / "mcp_init.py")

    issues: list = []
    mod.check_mcp_tool_count_claims(
        facts={"mcp_tools": ["a", "b", "c", "d", "e", "f"], "public_api": []},
        issues=issues,
    )
    assert any("five tools" in i.message.lower() for i in issues)


def test_mcp_tool_count_claim_check_accepts_matching_number(tmp_path, monkeypatch):
    mod = _load_module()
    ok_readme = tmp_path / "README.md"
    ok_readme.write_text("Six tools are registered.\n", encoding="utf-8")

    monkeypatch.setattr(mod, "README", ok_readme)
    monkeypatch.setattr(mod, "EASY_EN", tmp_path / "EASY_README.md")
    monkeypatch.setattr(mod, "EASY_KR", tmp_path / "EASY_README_KR.md")
    monkeypatch.setattr(mod, "README_KR", tmp_path / "README_KR.md")
    monkeypatch.setattr(mod, "INIT_PATH", tmp_path / "init.py")
    monkeypatch.setattr(mod, "MCP_INIT_PATH", tmp_path / "mcp_init.py")

    issues: list = []
    mod.check_mcp_tool_count_claims(
        facts={"mcp_tools": ["a", "b", "c", "d", "e", "f"], "public_api": []},
        issues=issues,
    )
    assert issues == []


def test_korean_count_claim_is_detected(tmp_path, monkeypatch):
    mod = _load_module()
    bad = tmp_path / "EASY_README_KR.md"
    bad.write_text("이 패키지는 5개 probe를 노출합니다.\n", encoding="utf-8")

    monkeypatch.setattr(mod, "README", tmp_path / "README.md")
    monkeypatch.setattr(mod, "EASY_EN", tmp_path / "EASY_README.md")
    monkeypatch.setattr(mod, "EASY_KR", bad)
    monkeypatch.setattr(mod, "README_KR", tmp_path / "README_KR.md")
    monkeypatch.setattr(mod, "INIT_PATH", tmp_path / "init.py")
    monkeypatch.setattr(mod, "MCP_INIT_PATH", tmp_path / "mcp_init.py")

    issues: list = []
    mod.check_mcp_tool_count_claims(
        facts={"mcp_tools": ["a", "b", "c", "d", "e", "f"], "public_api": []},
        issues=issues,
    )
    assert any("5" in i.message and "개 probe" in i.message for i in issues)


def test_install_name_check_flags_underscore(tmp_path, monkeypatch):
    mod = _load_module()
    bad = tmp_path / "README.md"
    bad.write_text("Install: ``pip install mini_omega_lock``\n", encoding="utf-8")

    monkeypatch.setattr(mod, "README", bad)
    monkeypatch.setattr(mod, "EASY_EN", tmp_path / "EASY_README.md")
    monkeypatch.setattr(mod, "EASY_KR", tmp_path / "EASY_README_KR.md")
    monkeypatch.setattr(mod, "README_KR", tmp_path / "README_KR.md")

    issues: list = []
    mod.check_install_and_import_names({}, issues)
    assert any("underscore" in i.message for i in issues)


def test_mcp_run_command_check_flags_hyphenated(tmp_path, monkeypatch):
    mod = _load_module()
    bad = tmp_path / "README.md"
    bad.write_text("Run: ``python -m mini-omega-lock.mcp``\n", encoding="utf-8")

    monkeypatch.setattr(mod, "README", bad)
    monkeypatch.setattr(mod, "EASY_EN", tmp_path / "EASY_README.md")
    monkeypatch.setattr(mod, "EASY_KR", tmp_path / "EASY_README_KR.md")
    monkeypatch.setattr(mod, "README_KR", tmp_path / "README_KR.md")

    issues: list = []
    mod.check_mcp_run_command({}, issues)
    assert any("hyphen" in i.message for i in issues)


def test_public_api_name_check_flags_unknown_function(tmp_path, monkeypatch):
    mod = _load_module()
    bad = tmp_path / "README.md"
    bad.write_text(
        "Call ``measure_galaxy_alignment()`` for stellar judges.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "README", bad)
    monkeypatch.setattr(mod, "EASY_EN", tmp_path / "EASY_README.md")
    monkeypatch.setattr(mod, "EASY_KR", tmp_path / "EASY_README_KR.md")
    monkeypatch.setattr(mod, "README_KR", tmp_path / "README_KR.md")

    issues: list = []
    mod.check_public_api_names(
        facts={"public_api": ["measure_judge_consistency", "empirical_preflight"]},
        issues=issues,
    )
    assert any("measure_galaxy_alignment" in i.message for i in issues)


def test_test_count_badge_is_forbidden(tmp_path, monkeypatch):
    mod = _load_module()
    bad = tmp_path / "README.md"
    bad.write_text(
        "[![Tests](https://img.shields.io/badge/tests-99%20passing-brightgreen.svg)](tests/)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "README", bad)
    monkeypatch.setattr(mod, "EASY_EN", tmp_path / "EASY_README.md")
    monkeypatch.setattr(mod, "EASY_KR", tmp_path / "EASY_README_KR.md")

    issues: list = []
    mod.check_readme_badges(
        facts={"version": "0.4.0", "dependencies": []},
        issues=issues,
    )
    assert any("tests-N passing" in i.message for i in issues)
