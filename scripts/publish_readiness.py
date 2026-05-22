"""No-network publish-readiness gate.

Composes ``release_audit.py --no-network``, ``python -m build``, and
``wheel_smoke_install.py`` into a single pass/fail signal.

Run::

    python scripts/publish_readiness.py --no-network

Exit codes:
    0 — every check passed; safe to publish via ``twine upload`` (manual).
    1 — at least one check failed.
    2 — a required tool is missing (``TOOLING_MISSING:`` prefix in output).

Important: this script never *runs* the publish. It only verifies the
artifact passes the gate. ``twine upload dist/*`` remains the user's
explicit, manual step.
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
DIST = REPO_ROOT / "dist"


def _read_pyproject() -> dict:
    return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _wheel_path() -> Path | None:
    """Return the most recently built wheel for the current version, or None."""
    project = _read_pyproject()["project"]
    name = project["name"].replace("-", "_")
    version = project["version"]
    expected = DIST / f"{name}-{version}-py3-none-any.whl"
    if expected.exists():
        return expected
    return None


def _tool_exists(args: list[str]) -> bool:
    """Return True if ``args[0] -m args[1]`` (or args verbatim) can run --version."""
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=15)
    except (subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0


def _run(name: str, cmd: list[str]) -> tuple[bool, str]:
    print(f"[step] {name}: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        encoding="utf-8",
        errors="replace",
    )
    out = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        print(out)
        return False, out
    return True, out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--no-network",
        action="store_true",
        required=True,
        help="Required: confirms the caller knows this script does not hit the network.",
    )
    args = parser.parse_args(argv)
    _ = args.no_network

    # Step 1: release audit (composes pytest, gen-claims, consistency,
    # demo, golden, fixture integrity).
    ok, _ = _run(
        "release-audit",
        [sys.executable, "scripts/release_audit.py", "--no-network"],
    )
    if not ok:
        print("publish-readiness FAILED at release audit.", file=sys.stderr)
        return 1

    # Step 2: build wheel + sdist.
    if not _tool_exists([sys.executable, "-m", "build", "--version"]):
        print(
            "TOOLING_MISSING: the `build` package is not installed in this "
            "environment. Install with: python -m pip install build\n"
            "publish-readiness cannot proceed without a built wheel.",
            file=sys.stderr,
        )
        return 2

    ok, _ = _run("build-wheel-and-sdist", [sys.executable, "-m", "build"])
    if not ok:
        print("publish-readiness FAILED at build step.", file=sys.stderr)
        return 1

    # Step 3: wheel smoke install.
    wheel = _wheel_path()
    if wheel is None:
        print(
            "publish-readiness FAILED: no wheel matching the current version "
            f"was produced under {DIST.relative_to(REPO_ROOT)}.",
            file=sys.stderr,
        )
        return 1
    ok, _ = _run("wheel-smoke", [sys.executable, "scripts/wheel_smoke_install.py", str(wheel)])
    if not ok:
        print("publish-readiness FAILED at wheel smoke install.", file=sys.stderr)
        return 1

    version = _read_pyproject()["project"]["version"]
    print(
        "\nPublish-readiness PASSED for version "
        f"{version}.\n"
        "All no-network checks succeeded; the wheel installs cleanly into "
        "a fresh venv and exposes the documented public API.\n\n"
        "Next manual step (the user runs this; the script does NOT):\n"
        f"  python -m twine upload dist/mini_omega_lock-{version}-py3-none-any.whl "
        f"dist/mini_omega_lock-{version}.tar.gz\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
