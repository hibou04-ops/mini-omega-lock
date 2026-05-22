"""Post-release verification.

Default mode: ``--no-network``. Re-runs the same mechanical checks the
audit performs, plus confirms the local wheel/sdist and version are
unchanged since publish-readiness signed off.

Optional ``--network`` mode (must be passed explicitly; not used in
CI): downloads the PyPI artifact and compares its SHA-256 to the local
wheel, and verifies ``info.version`` from PyPI matches the local
pyproject version.

Run::

    python scripts/post_release_verify.py --no-network
    python scripts/post_release_verify.py --network --version 0.5.0  # opt-in
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DIST = REPO_ROOT / "dist"


def _read_project() -> dict:
    return tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def _local_wheel(version: str) -> Path | None:
    name = _read_project()["name"].replace("-", "_")
    candidate = DIST / f"{name}-{version}-py3-none-any.whl"
    return candidate if candidate.exists() else None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _no_network_path() -> int:
    """Repeat the audit + verify dist/ matches pyproject's current version."""
    failures: list[str] = []
    version = _read_project()["version"]

    # 1. Re-run release audit (composes the full mechanical set).
    audit = subprocess.run(
        [sys.executable, "scripts/release_audit.py", "--no-network"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    sys.stdout.write(audit.stdout)
    sys.stderr.write(audit.stderr)
    if audit.returncode != 0:
        failures.append("release_audit.py --no-network exited non-zero")

    # 2. dist/ must have artifacts for the current version (publish should
    #    have produced them locally before upload).
    wheel = _local_wheel(version)
    if wheel is None:
        failures.append(
            f"no local wheel for current version {version} in dist/ — "
            "did publish-readiness run?"
        )

    if failures:
        print("\npost-release verification FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print(
        "\npost-release verification PASSED (no-network).\n"
        f"  version: {version}\n"
        f"  wheel:   {wheel.relative_to(REPO_ROOT) if wheel else 'n/a'}"
    )
    return 0


def _network_path(version: str) -> int:
    """Hit PyPI; compare metadata + wheel hash. Opt-in only."""
    name = _read_project()["name"]
    url = f"https://pypi.org/pypi/{name}/json"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 - audit
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        print(
            f"ENVIRONMENT_BLOCKED: could not reach {url}: {exc}",
            file=sys.stderr,
        )
        return 2

    remote_version = data.get("info", {}).get("version")
    if remote_version != version:
        print(
            f"[fail] PyPI version is {remote_version!r} but local pyproject.toml "
            f"is {version!r} — did the publish actually run?",
            file=sys.stderr,
        )
        return 1
    print(f"[ok] PyPI version matches: {version}")

    # Match the wheel by exact filename when present.
    wheel_name = f"{name.replace('-', '_')}-{version}-py3-none-any.whl"
    releases = data.get("releases", {}).get(version, [])
    remote_record = next((r for r in releases if r.get("filename") == wheel_name), None)
    if remote_record is None:
        print(
            f"[warn] no wheel named {wheel_name} on PyPI for {version}",
            file=sys.stderr,
        )
        return 1

    local_wheel = _local_wheel(version)
    if local_wheel is None:
        print(f"[warn] no local wheel under dist/ matches {wheel_name}", file=sys.stderr)
        return 1
    local_sha = _sha256(local_wheel)
    remote_sha = remote_record.get("digests", {}).get("sha256")
    if remote_sha and remote_sha != local_sha:
        print(
            f"[fail] wheel SHA-256 differs.\n"
            f"  local : {local_sha}\n"
            f"  remote: {remote_sha}",
            file=sys.stderr,
        )
        return 1
    print(f"[ok] wheel SHA-256 matches local {local_wheel.relative_to(REPO_ROOT)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--no-network",
        action="store_true",
        help="Default safe mode: re-run the audit and verify local artifacts.",
    )
    mode.add_argument(
        "--network",
        action="store_true",
        help="Opt-in: hit PyPI to confirm the published artifact matches local.",
    )
    parser.add_argument(
        "--version",
        help="Version to confirm on PyPI. Required when --network is set.",
    )
    args = parser.parse_args(argv)

    if args.no_network:
        return _no_network_path()

    if not args.version:
        print("--network mode requires --version <version>", file=sys.stderr)
        return 2
    return _network_path(args.version)


if __name__ == "__main__":
    sys.exit(main())
