"""Audit repository for drift between sources of truth.

Runs a battery of mechanical checks; each check appends ``Issue`` records
to a shared list rather than short-circuiting, so the first run after
upgrading the repo surfaces every drift at once.

Exit code 0 when all checks pass; 1 otherwise (with a per-issue diagnostic
on stderr). Designed to be called from CI, ``release_audit.py``, and
``publish_readiness.py``.

Implementation note: stdlib-only, no third-party imports. Safe to run on
a fresh checkout before ``pip install -e``.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
INIT_PATH = REPO_ROOT / "src" / "mini_omega_lock" / "__init__.py"
MCP_INIT_PATH = REPO_ROOT / "src" / "mini_omega_lock" / "mcp" / "__init__.py"
MCP_SERVER_PATH = REPO_ROOT / "src" / "mini_omega_lock" / "mcp" / "server.py"
README = REPO_ROOT / "README.md"
EASY_EN = REPO_ROOT / "EASY_README.md"
EASY_KR = REPO_ROOT / "EASY_README_KR.md"
README_KR = REPO_ROOT / "README_KR.md"

# We re-use these from the generator so the two stay in sync without
# duplicating parse code.
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from generate_readme_claims import (  # noqa: E402
    collect_facts,
    discover_mcp_tool_names,
    read_module_constant,
)


@dataclass
class Issue:
    where: str
    message: str

    def render(self) -> str:
        return f"  [{self.where}] {self.message}"


# ---------------------------------------------------------------------------
# Individual checks (each appends to ``issues``)
# ---------------------------------------------------------------------------


def check_version_consistency(facts: dict, issues: list[Issue]) -> None:
    if facts["version"] != facts["init_version"]:
        issues.append(
            Issue(
                "pyproject vs __init__.py",
                f"version drift: pyproject={facts['version']!r}, "
                f"__init__.__version__={facts['init_version']!r}",
            )
        )


def check_readme_badges(facts: dict, issues: list[Issue]) -> None:
    if not README.exists():
        issues.append(Issue("README.md", "missing"))
        return
    text = README.read_text(encoding="utf-8")

    # PyPI version badge.
    m = re.search(r"img\.shields\.io/badge/pypi-([0-9][0-9A-Za-z._-]*)-", text)
    if m and m.group(1) != facts["version"]:
        issues.append(
            Issue(
                "README badge",
                f"PyPI badge version {m.group(1)!r} != pyproject "
                f"version {facts['version']!r}",
            )
        )

    # Parent-omegaprompt badge.
    op_pin = ""
    for dep in facts["dependencies"]:
        if dep.startswith("omegaprompt"):
            mver = re.search(r">=\s*([0-9][0-9A-Za-z._-]*)", dep)
            if mver:
                op_pin = mver.group(1)
            break
    if op_pin:
        # Badge uses URL-encoded ≥ (%E2%89%A5).
        bm = re.search(
            r"parent-omegaprompt(?:%E2%89%A5|≥)([0-9][0-9A-Za-z._-]*)-",
            text,
        )
        if bm and bm.group(1) != op_pin:
            issues.append(
                Issue(
                    "README badge",
                    f"parent-omegaprompt badge {bm.group(1)!r} != "
                    f"pyproject pin {op_pin!r}",
                )
            )

    # Forbidden: hard-coded test count.
    for fname, fpath in (("README.md", README), ("EASY_README.md", EASY_EN), ("EASY_README_KR.md", EASY_KR)):
        if fpath.exists():
            content = fpath.read_text(encoding="utf-8")
            if re.search(r"tests-\d+\s*(?:passing|%20passing)", content):
                issues.append(
                    Issue(
                        fname,
                        "hard-coded 'tests-N passing' badge — "
                        "test counts must be source-backed, not pinned in README prose",
                    )
                )


def check_top_links_exist(facts: dict, issues: list[Issue]) -> None:
    """README top should link to actual files; verify every referenced
    repo-local .md path exists.

    We only fail on links to .md files inside the repo (not external URLs)
    and only for links that look like documentation/example paths.
    """
    if not README.exists():
        return
    text = README.read_text(encoding="utf-8")
    # Pull markdown link targets ``[label](target)``.
    targets = re.findall(r"\[[^\]]+\]\(([^)]+)\)", text)
    for t in targets:
        target = t.split("#", 1)[0].strip()
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        # Skip anchors / relative dotfiles unrelated to docs.
        if target.startswith(("LICENSE", "NOTICE", "AUTHORS", "PRE_EXISTING_IP", "IP_DEFENSE")):
            continue
        # Only verify .md / .py / .txt / directories under the repo.
        if not target.endswith((".md", ".py", ".txt", "/")) and "/" not in target:
            continue
        full = (REPO_ROOT / target).resolve()
        if not full.exists():
            issues.append(
                Issue(
                    "README link",
                    f"link target does not exist: {target!r}",
                )
            )


def check_easy_readme_kr_link(_facts: dict, issues: list[Issue]) -> None:
    if not EASY_KR.exists():
        return
    text = EASY_KR.read_text(encoding="utf-8")
    if "README_KR.md" in text and not README_KR.exists():
        issues.append(
            Issue(
                "EASY_README_KR.md",
                "references README_KR.md but the file does not exist",
            )
        )


def check_install_and_import_names(_facts: dict, issues: list[Issue]) -> None:
    """All three READMEs must use ``mini-omega-lock`` in pip install and
    ``mini_omega_lock`` in Python imports (no underscore/hyphen swap)."""
    for fname, fpath in (
        ("README.md", README),
        ("EASY_README.md", EASY_EN),
        ("EASY_README_KR.md", EASY_KR),
        ("README_KR.md", README_KR),
    ):
        if not fpath.exists():
            continue
        text = fpath.read_text(encoding="utf-8")
        # `pip install mini_omega_lock` is wrong (only the hyphenated form is the
        # PyPI distribution name).
        if re.search(r"pip\s+install\s+(?:\"|')?mini_omega_lock", text):
            issues.append(
                Issue(fname, "pip install uses underscore form; PyPI name is 'mini-omega-lock'")
            )
        # `from mini-omega-lock import …` is wrong (hyphen is illegal in Python).
        if re.search(r"from\s+mini-omega-lock\s+import", text):
            issues.append(
                Issue(fname, "Python import uses hyphenated form; import is 'mini_omega_lock'")
            )


def check_mcp_run_command(_facts: dict, issues: list[Issue]) -> None:
    """Every doc that mentions running the MCP server must spell it
    ``python -m mini_omega_lock.mcp`` — not the underscore-broken or
    hyphenated variants."""
    for fname, fpath in (
        ("README.md", README),
        ("EASY_README.md", EASY_EN),
        ("EASY_README_KR.md", EASY_KR),
        ("README_KR.md", README_KR),
    ):
        if not fpath.exists():
            continue
        text = fpath.read_text(encoding="utf-8")
        if "mini-omega-lock.mcp" in text:
            issues.append(
                Issue(fname, "MCP command uses hyphen: must be 'python -m mini_omega_lock.mcp'")
            )


def check_public_api_names(facts: dict, issues: list[Issue]) -> None:
    """Function-like names mentioned in code blocks in README/EASY_READMEs
    must exist in ``__all__``.

    Heuristic: pull ``identifier(`` patterns from fenced code blocks and
    intersect with the names we already know live in ``__all__`` — if the
    pattern looks like an exported name (matches the known prefix set) but
    isn't in ``__all__``, flag it.
    """
    known = set(facts["public_api"])
    # Restrict our hunt to names that this package "owns" — anything
    # starting with these prefixes:
    owned_prefixes = ("measure_", "probe_", "compute_", "noise_floor", "project_", "empirical_")

    def _has_unknown(text: str) -> set[str]:
        # Pull tokens that look like exported functions (snake_case + paren).
        names = set(re.findall(r"\b([a-z][a-z0-9_]*)\s*\(", text))
        # Keep only the ones that "look ours" by prefix.
        ours = {n for n in names if n.startswith(owned_prefixes)}
        return ours - known

    for fname, fpath in (
        ("README.md", README),
        ("EASY_README.md", EASY_EN),
        ("EASY_README_KR.md", EASY_KR),
        ("README_KR.md", README_KR),
    ):
        if not fpath.exists():
            continue
        text = fpath.read_text(encoding="utf-8")
        unknown = _has_unknown(text)
        if unknown:
            for u in sorted(unknown):
                issues.append(
                    Issue(
                        fname,
                        f"references function {u!r} but it is not in mini_omega_lock.__all__",
                    )
                )


def check_mcp_tool_count_claims(facts: dict, issues: list[Issue]) -> None:
    """Phrases like "Five tools" / "five probes" / "6 MCP tools" must
    match ``len(mcp_tools)``.

    Soft check: only fail when the number is *numerically* asserted next
    to "tool"/"probe"/"function" and that number differs from the actual
    count of MCP tools (`len(mcp_tools)`) AND from `len(__all__) - 1`
    (which is the count of exported callables, excluding ``__version__``).
    """
    expected_mcp = len(facts["mcp_tools"])
    expected_api = len([n for n in facts["public_api"] if n != "__version__"])

    word_to_num = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    }

    # Patterns: ``NUMBER (tools|probes|functions)`` where NUMBER is digits
    # or an English number word. Korean variants (``N개 probe`` / ``N개
    # 함수``) are matched too so EASY_README_KR doesn't drift silently.
    digit_pat = re.compile(
        r"\b(\d{1,2})\s+(tools?|probes?|functions?|exported\s+functions?)\b",
        re.IGNORECASE,
    )
    word_pat = re.compile(
        r"\b(one|two|three|four|five|six|seven|eight|nine|ten)\s+"
        r"(tools?|probes?|functions?|exported\s+functions?)\b",
        re.IGNORECASE,
    )
    kr_pat = re.compile(
        r"(\d{1,2})\s*개\s+(probes?|tools?|functions?|함수|도구|툴|export\s+함수)",
        re.IGNORECASE,
    )

    for fname, fpath in (
        ("README.md", README),
        ("EASY_README.md", EASY_EN),
        ("EASY_README_KR.md", EASY_KR),
        ("README_KR.md", README_KR),
        ("src/mini_omega_lock/__init__.py", INIT_PATH),
        ("src/mini_omega_lock/mcp/__init__.py", MCP_INIT_PATH),
    ):
        if not fpath.exists():
            continue
        text = fpath.read_text(encoding="utf-8")
        candidates: list[tuple[int, str]] = []
        for m in digit_pat.finditer(text):
            candidates.append((int(m.group(1)), m.group(0)))
        for m in word_pat.finditer(text):
            candidates.append((word_to_num[m.group(1).lower()], m.group(0)))
        for m in kr_pat.finditer(text):
            candidates.append((int(m.group(1)), m.group(0)))
        for value, snippet in candidates:
            if value not in {expected_mcp, expected_api}:
                issues.append(
                    Issue(
                        fname,
                        f"count claim {snippet!r} doesn't match "
                        f"MCP tools ({expected_mcp}) or public API "
                        f"functions ({expected_api})",
                    )
                )


def check_mcp_extra_and_script(facts: dict, issues: list[Issue]) -> None:
    extras = facts["optional_dependencies"]
    if "mcp" not in extras:
        issues.append(
            Issue("pyproject.toml", "no 'mcp' optional extra — README/docs claim it exists")
        )
    if "mini-omega-lock-mcp" not in facts["scripts"]:
        issues.append(
            Issue(
                "pyproject.toml",
                "no 'mini-omega-lock-mcp' console script — "
                "remove the claim from README or restore the entry point",
            )
        )


def check_mcp_tools_registered_vs_init_doc(facts: dict, issues: list[Issue]) -> None:
    """`mcp/__init__.py` docstring lists registered tools by bullet —
    every name in `__all__` of MCP server must appear in the bullets, and
    no stale name remains."""
    if not MCP_INIT_PATH.exists():
        return
    init_text = MCP_INIT_PATH.read_text(encoding="utf-8")
    tools = set(facts["mcp_tools"])
    # Bullet line shape: ``* ``name`` — …``
    listed = set(re.findall(r"\*\s+``([a-z_][a-z0-9_]*)``", init_text))
    missing = tools - listed
    stale = listed - tools
    for m in sorted(missing):
        issues.append(
            Issue(
                "src/mini_omega_lock/mcp/__init__.py",
                f"docstring missing MCP tool bullet: {m!r}",
            )
        )
    for s in sorted(stale):
        issues.append(
            Issue(
                "src/mini_omega_lock/mcp/__init__.py",
                f"docstring lists tool {s!r} but it is not registered "
                f"on mcp_app (decorator not found in server.py)",
            )
        )


def check_no_stale_omega_lock_preflight_citation(_facts: dict, issues: list[Issue]) -> None:
    """M5 coupling-safety: ``omega_lock.preflight`` is a NON-EXISTENT API.

    A docstring once cited that path as the place this surface is exposed.
    omega-lock exports no ``.preflight`` public surface, so the citation
    was a broken coupling claim. Assert the string never reappears in
    ``src/`` (the only place it would matter for the published package).
    """
    src_dir = REPO_ROOT / "src"
    needle = "omega_lock.preflight"
    for path in sorted(src_dir.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if needle in text:
            issues.append(
                Issue(
                    str(path.relative_to(REPO_ROOT)),
                    f"cites non-existent API {needle!r}; omega-lock has no "
                    f"public .preflight surface. Reference 'omega-lock "
                    f"(parameter-calibration framework)' instead.",
                )
            )


def check_generated_claims_drift(_facts: dict, issues: list[Issue]) -> None:
    """Delegate to the generator's --check mode."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "generate_readme_claims.py"), "--check"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        issues.append(
            Issue(
                "docs/generated",
                "generated claims are stale: "
                + (result.stderr.strip() or "see generate_readme_claims.py --check"),
            )
        )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


CHECKS = [
    check_version_consistency,
    check_readme_badges,
    check_top_links_exist,
    check_easy_readme_kr_link,
    check_install_and_import_names,
    check_mcp_run_command,
    check_public_api_names,
    check_mcp_tool_count_claims,
    check_mcp_extra_and_script,
    check_mcp_tools_registered_vs_init_doc,
    check_no_stale_omega_lock_preflight_citation,
    check_generated_claims_drift,
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--list-checks",
        action="store_true",
        help="Print the registered check names and exit.",
    )
    args = parser.parse_args(argv)

    if args.list_checks:
        for fn in CHECKS:
            print(fn.__name__)
        return 0

    facts = collect_facts()
    issues: list[Issue] = []
    for fn in CHECKS:
        fn(facts, issues)

    if issues:
        print("Repository consistency check FAILED", file=sys.stderr)
        for issue in issues:
            print(issue.render(), file=sys.stderr)
        print(
            f"\nTotal issues: {len(issues)}. "
            "Fix or regenerate (`python scripts/generate_readme_claims.py`) and re-run.",
            file=sys.stderr,
        )
        return 1

    print(f"Repository consistency check passed ({len(CHECKS)} checks).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
