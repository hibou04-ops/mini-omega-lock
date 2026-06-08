"""No-network release audit.

Runs every mechanical check that does not require either internet or a
build toolchain. Designed to fail closed: if a check cannot be executed
(missing tool, missing source file) the audit reports the blocker and
exits non-zero rather than skipping.

Run::

    python scripts/release_audit.py --no-network

The ``--no-network`` flag is currently the only supported mode (kept
explicit so callers cannot accidentally regress us into a path that
hits the network). Pass ``--quiet`` to suppress step-by-step output.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"


# ---------------------------------------------------------------------------
# Step descriptors
# ---------------------------------------------------------------------------


def _step(name: str, cmd: list[str]) -> tuple[str, list[str]]:
    return name, cmd


STEPS: list[tuple[str, list[str]]] = [
    _step(
        "generated-claims-drift",
        [sys.executable, "scripts/generate_readme_claims.py", "--check"],
    ),
    _step(
        "repo-consistency",
        [sys.executable, "scripts/check_repo_consistency.py"],
    ),
    _step(
        "pytest",
        [sys.executable, "-m", "pytest", "-q"],
    ),
    _step(
        "demo-replay",
        [sys.executable, "examples/demo_replay.py"],
    ),
    _step(
        "demo-replay-diff",
        [sys.executable, "-m", "pytest", "-q", "tests/test_demo_replay.py"],
    ),
    _step(
        "golden-cases",
        [sys.executable, "scripts/run_golden_cases.py", "--check"],
    ),
    _step(
        "fixture-integrity",
        [sys.executable, "scripts/verify_fixture_integrity.py"],
    ),
]


# ---------------------------------------------------------------------------
# Release-marker checks (verify absence)
# ---------------------------------------------------------------------------


def _read_version() -> str:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return data["project"]["version"]


def _check_no_release_markers() -> list[str]:
    """Return human-readable issues if any "release performed" marker is present.

    The audit must FAIL when a release has been performed — this is the
    pre-publish gate. See ``docs/release_checklist.md`` "What 'release
    performed' means for the audit".
    """
    issues: list[str] = []
    version = _read_version()
    tag = f"v{version}"

    # 1. Local git tag. This is a PRE-TAG safety: locally (and in ci.yml's
    #    push/PR checkout, which fetches no tags) the version's tag must not yet
    #    exist. The trusted-publishing publish workflow, however, checks out AT
    #    the tag (so the tag necessarily exists) and gates on this same audit via
    #    publish_readiness.py — there the check is inverted and must be skipped.
    #    MINI_OMEGA_LOCK_RELEASE_WORKFLOW is set only by that workflow.
    if not os.environ.get("MINI_OMEGA_LOCK_RELEASE_WORKFLOW"):
        result = subprocess.run(
            ["git", "tag", "-l", tag],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        if result.returncode == 0 and result.stdout.strip() == tag:
            issues.append(
                f"local git tag {tag!r} already exists — release appears to have "
                "been performed; audit refuses to greenlight publish"
            )

    # 2. dist/ contents must be a subset of {wheel, sdist} for the current
    #    version. Unknown artifacts (e.g. a different version, a draft, a
    #    twine upload checksum) are a blocker.
    dist = REPO_ROOT / "dist"
    if dist.exists():
        name = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["name"]
        wheel_name = f"{name.replace('-', '_')}-{version}-py3-none-any.whl"
        sdist_name = f"{name.replace('-', '_')}-{version}.tar.gz"
        allowed = {wheel_name, sdist_name}
        for artifact in sorted(dist.iterdir()):
            if artifact.is_file() and artifact.name not in allowed:
                # Allow other versions to coexist (caller may keep history);
                # but anything that looks like a published-marker file is a
                # blocker.
                if not re.match(rf"{re.escape(name).replace('-', '_')}-\d", artifact.name):
                    issues.append(
                        f"unexpected file in dist/: {artifact.name!r} — clean dist/ before audit"
                    )

    # 3. RELEASE_DRAFT.md with a PUBLISHED marker.
    draft = REPO_ROOT / "RELEASE_DRAFT.md"
    if draft.exists() and "STATUS: PUBLISHED" in draft.read_text(encoding="utf-8"):
        issues.append(
            "RELEASE_DRAFT.md contains 'STATUS: PUBLISHED' — release already done"
        )

    return issues


def _check_ci_workflow_has_audit_steps() -> list[str]:
    """Spot-check that the CI workflow references the same script set the
    audit runs locally. This isn't a guarantee that CI passes, but it
    catches obvious drift where audit grew a step the workflow never picked up."""
    ci = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    issues: list[str] = []
    if not ci.exists():
        issues.append("missing .github/workflows/ci.yml")
        return issues
    text = ci.read_text(encoding="utf-8")
    expected_substrings = [
        "pytest",
        "generate_readme_claims.py",
        "check_repo_consistency.py",
        "run_golden_cases.py",
        "verify_fixture_integrity.py",
        "release_audit.py",
    ]
    for substring in expected_substrings:
        if substring not in text:
            issues.append(
                f"ci.yml does not reference {substring!r} — "
                "the workflow is missing an audit step"
            )
    return issues


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def _run_step(name: str, cmd: list[str], quiet: bool) -> tuple[bool, str]:
    if not quiet:
        print(f"[step] {name}: {' '.join(cmd)}")
    # encoding="utf-8" is load-bearing: the probe warning strings (and the
    # demo replay output) contain em-dashes that Windows' default cp949
    # cannot decode. Without this the audit FAILED steps would be drowned
    # by UnicodeDecodeError noise instead of the real cause.
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        encoding="utf-8",
        errors="replace",
    )
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        return False, output
    return True, output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--no-network",
        action="store_true",
        required=True,
        help="Required: confirms the caller knows this script does not hit the network.",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    _ = args.no_network  # required arg already enforced

    failures: list[str] = []

    # Run mechanical steps.
    for name, cmd in STEPS:
        ok, output = _run_step(name, cmd, args.quiet)
        if not ok:
            failures.append(f"{name}: command failed\n{output.rstrip()}")

    # Absence-of-marker checks.
    marker_issues = _check_no_release_markers()
    for issue in marker_issues:
        failures.append(f"release-marker: {issue}")

    ci_issues = _check_ci_workflow_has_audit_steps()
    for issue in ci_issues:
        failures.append(f"ci-workflow: {issue}")

    if failures:
        print("\nRelease audit FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print(f"\nRelease audit PASSED ({len(STEPS)} steps + 2 marker scans).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
