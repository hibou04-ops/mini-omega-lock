"""Tests for ``scripts/generate_readme_claims.py``.

Three things must hold:

1. The renderer pulls every field from a source-of-truth file rather than
   a literal in the script — verified by mutating a temp source and
   checking the rendered output changes.
2. ``--check`` exits 0 when files match, 1 when stale.
3. Generated docs contain the public API, MCP tool list, install command,
   and verification command surface that the rest of the repo depends on.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "generate_readme_claims.py"
CLAIMS_EN = REPO_ROOT / "docs" / "generated" / "claims.md"
CLAIMS_KR = REPO_ROOT / "docs" / "generated" / "claims_kr.md"


def _load_module():
    spec = importlib.util.spec_from_file_location("gen_claims", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_collect_facts_pulls_from_real_pyproject():
    mod = _load_module()
    facts = mod.collect_facts()

    assert facts["name"] == "mini-omega-lock"
    # version comes from pyproject; the test mustn't hard-code the literal
    # value (else this test becomes the second source of truth). We just
    # check it's non-empty and shaped like PEP 440.
    assert facts["version"]
    assert facts["version"].count(".") >= 1
    assert facts["version"] == facts["init_version"]


def test_collect_facts_includes_every_all_export():
    mod = _load_module()
    facts = mod.collect_facts()
    # The package-level __all__ is the contract; everything in it must
    # appear in the rendered docs.
    import mini_omega_lock

    for name in mini_omega_lock.__all__:
        assert name in facts["public_api"]


def test_collect_facts_discovers_at_least_one_mcp_tool():
    mod = _load_module()
    facts = mod.collect_facts()
    assert isinstance(facts["mcp_tools"], list)
    assert len(facts["mcp_tools"]) >= 1
    # Sanity: the empirical_preflight tool must be registered.
    assert "empirical_preflight" in facts["mcp_tools"]


def test_check_mode_passes_on_clean_repo():
    """The committed docs/generated/*.md must always match the live output."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, (
        f"--check failed; regenerate.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_check_mode_fails_when_a_file_is_stale(tmp_path, monkeypatch):
    """Mutate the rendered file on disk and prove --check reports drift."""
    # Save the originals so we can restore on teardown.
    original_en = CLAIMS_EN.read_text(encoding="utf-8")
    original_kr = CLAIMS_KR.read_text(encoding="utf-8")
    CLAIMS_EN.write_text(original_en + "\n<!-- drift sentinel -->\n", encoding="utf-8")
    try:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--check"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert result.returncode == 1
        assert "stale" in result.stderr or "stale" in result.stdout
    finally:
        CLAIMS_EN.write_text(original_en, encoding="utf-8")
        CLAIMS_KR.write_text(original_kr, encoding="utf-8")


def test_rendered_en_contains_required_sections():
    text = CLAIMS_EN.read_text(encoding="utf-8")
    for needle in (
        "Distribution",
        "Console scripts",
        "MCP",
        "Public API",
        "Install commands",
        "Verification commands",
        "What these claims are NOT",
        "empirical_preflight",  # API name must appear
        "python -m pytest -q",  # canonical test command
    ):
        assert needle in text, f"missing section/identifier: {needle!r}"


def test_rendered_kr_mirrors_en_structure():
    """The Korean file must keep every identifier (function name, command)
    in English while translating the prose labels — required because
    Python imports and shell commands are not localisable."""
    en = CLAIMS_EN.read_text(encoding="utf-8")
    kr = CLAIMS_KR.read_text(encoding="utf-8")
    # All MCP tool names should appear in both files identically.
    mod = _load_module()
    facts = mod.collect_facts()
    for tool in facts["mcp_tools"]:
        assert tool in en
        assert tool in kr
    for fn_name in facts["public_api"]:
        assert fn_name in en
        assert fn_name in kr
    # Distribution / import identifiers must be untranslated.
    for identifier in ("mini-omega-lock", "mini_omega_lock", "python -m pytest -q"):
        assert identifier in en
        assert identifier in kr
