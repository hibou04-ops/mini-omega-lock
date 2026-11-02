# SPDX-License-Identifier: Apache-2.0
"""Run the offline audit with a verified tag context or the pre-tag guard."""

from __future__ import annotations

import argparse
import ast
from collections.abc import Mapping
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib


REPO_ROOT = Path(__file__).resolve().parent.parent
RELEASE_ENV = "MINI_OMEGA_LOCK_RELEASE_WORKFLOW"


def _version(root: Path) -> str:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    version = project["version"]
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("Package version must be a stable X.Y.Z version")
    tree = ast.parse((root / "src/mini_omega_lock/__init__.py").read_text(encoding="utf-8"))
    versions = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if any(isinstance(target, ast.Name) and target.id == "__version__" for target in targets):
            try:
                versions.append(ast.literal_eval(node.value))
            except (TypeError, ValueError) as exc:
                raise ValueError("Runtime version must be a literal string") from exc
    if versions != [version]:
        raise ValueError("Runtime version does not match package metadata")
    return version


def _commit(root: Path, revision: str) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", revision],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        raise ValueError("Git is unavailable for release tag verification") from exc
    commit = result.stdout.strip()
    if result.returncode or not re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", commit):
        raise ValueError("Cannot resolve the checked-out commit and release tag")
    return commit.lower()


def prepare_audit_environment(root: Path, environ: Mapping[str, str]) -> dict[str, str]:
    """Scope the existing release-mode flag to a metadata/tag/HEAD match.

    Branch and pull-request runs always retain the pre-tag marker check, even
    when the caller inherited a release-mode flag. Tag runs resolve the actual
    local Git tag (including annotated tags) rather than trusting its name.
    """
    child_env = dict(environ)
    child_env.pop(RELEASE_ENV, None)
    ref = child_env.get("GITHUB_REF", "")
    ref_type = child_env.get("GITHUB_REF_TYPE", "")
    is_tag_ref = ref.startswith("refs/tags/")
    if ref_type == "tag" and not is_tag_ref:
        raise ValueError("Tag context requires a full refs/tags/ reference")
    if is_tag_ref and ref_type not in ("", "tag"):
        raise ValueError("GitHub reference type contradicts the tag reference")
    if not is_tag_ref:
        return child_env

    version = _version(root)
    tag = f"v{version}"
    if ref != f"refs/tags/{tag}":
        raise ValueError("Release tag does not match package metadata")
    if child_env.get("GITHUB_REF_NAME", tag) != tag:
        raise ValueError("GitHub reference name contradicts the release tag")
    head = _commit(root, "HEAD^{commit}")
    tag_commit = _commit(root, f"refs/tags/{tag}^{{commit}}")
    if head != tag_commit:
        raise ValueError("Release tag does not resolve to the checked-out HEAD")
    child_env[RELEASE_ENV] = "1"
    return child_env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-network", action="store_true", required=True)
    parser.parse_args(argv)
    try:
        child_env = prepare_audit_environment(REPO_ROOT, os.environ)
    except (OSError, ValueError, SyntaxError, KeyError) as exc:
        message = str(exc).encode("ascii", errors="backslashreplace").decode("ascii")
        print(f"CI audit context rejected: {message}", file=sys.stderr)
        return 2
    mode = "verified-tag" if child_env.get(RELEASE_ENV) == "1" else "pre-tag"
    print(f"CI audit context: {mode}", flush=True)
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/release_audit.py"), "--no-network"],
        cwd=REPO_ROOT,
        env=child_env,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
