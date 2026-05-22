"""Install a built wheel into a temporary venv and verify the public API.

Used by ``scripts/publish_readiness.py`` to make sure the artifact that
would be uploaded actually imports cleanly with only its declared
runtime dependencies — no editable-install accidents, no missing data
files, no PEP-517 surprises.

Run::

    python scripts/wheel_smoke_install.py dist/mini_omega_lock-0.5.0-py3-none-any.whl

The venv lives under ``tmp/wheel_smoke/`` and is removed on exit
regardless of pass/fail.

Cross-platform: detects Windows (``Scripts/python.exe``) vs POSIX
(``bin/python``). Does NOT install optional extras — those would
require either a private PyPI index or live network access.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _venv_python(venv_dir: Path) -> Path:
    """Return the platform-correct python interpreter inside ``venv_dir``."""
    if platform.system() == "Windows":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _smoke_test(python: Path, wheel_path: Path, name: str) -> int:
    """Verify the wheel imports cleanly and every name in ``__all__`` resolves."""
    script = (
        "import sys, importlib;"
        f"m = importlib.import_module({name!r});"
        "missing = [n for n in m.__all__ if not hasattr(m, n)];"
        "print('version:', getattr(m, '__version__', 'n/a'));"
        "print('all:', sorted(m.__all__));"
        "sys.exit(1 if missing else 0)"
    )
    result = subprocess.run(
        [str(python), "-c", script],
        capture_output=True,
        text=True,
    )
    sys.stdout.write(result.stdout)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("wheel", help="Path to the .whl file to smoke-install.")
    parser.add_argument(
        "--keep-venv",
        action="store_true",
        help="Don't remove the temporary venv on exit (debugging only).",
    )
    parser.add_argument(
        "--module",
        default="mini_omega_lock",
        help="Python import name to smoke-test (default: mini_omega_lock).",
    )
    args = parser.parse_args(argv)

    wheel_path = Path(args.wheel).resolve()
    if not wheel_path.exists():
        print(f"wheel not found: {wheel_path}", file=sys.stderr)
        return 1

    venv_dir = Path(tempfile.mkdtemp(prefix="mini_omega_lock_wheel_smoke_"))
    try:
        print(f"[step] creating venv at {venv_dir}")
        venv.EnvBuilder(with_pip=True).create(venv_dir)
        python = _venv_python(venv_dir)
        if not python.exists():
            print(f"venv python not found: {python}", file=sys.stderr)
            return 1

        # Upgrade pip silently to avoid surprises from old wheels.
        print("[step] upgrading pip")
        subprocess.run(
            [str(python), "-m", "pip", "install", "--upgrade", "pip"],
            check=False,
            capture_output=True,
        )

        print(f"[step] installing wheel: {wheel_path.name}")
        install = subprocess.run(
            [str(python), "-m", "pip", "install", str(wheel_path)],
            capture_output=True,
            text=True,
        )
        if install.returncode != 0:
            sys.stdout.write(install.stdout)
            sys.stderr.write(install.stderr)
            return install.returncode

        print(f"[step] smoke-importing {args.module!r}")
        rc = _smoke_test(python, wheel_path, args.module)
        if rc != 0:
            print("wheel smoke FAILED", file=sys.stderr)
            return rc
        print("wheel smoke OK")
        return 0
    finally:
        if not args.keep_venv:
            try:
                shutil.rmtree(venv_dir)
            except OSError as exc:
                print(f"warning: could not remove temp venv {venv_dir}: {exc}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
