"""Install a built wheel into a temporary venv and verify the public API.

Used by ``scripts/publish_readiness.py`` to make sure the artifact that
would be uploaded actually imports cleanly with only its declared
runtime dependencies — no editable-install accidents, no missing data
files, no PEP-517 surprises.

Run::

    python scripts/wheel_smoke_install.py dist/mini_omega_lock-0.5.0-py3-none-any.whl

The fresh venv lives in the system temporary directory, outside the checkout,
and is removed on exit regardless of pass/fail. Imports run from that directory.

Cross-platform: detects Windows (``Scripts/python.exe``) vs POSIX
(``bin/python``). Only declared runtime dependencies are installed; this step
may download them. No optional extras or parent engine are installed.
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
        "import sys, importlib, importlib.util; from pathlib import Path;"
        f"m = importlib.import_module({name!r});"
        "assert Path(m.__file__).resolve().is_relative_to(Path(sys.prefix).resolve());"
        "assert all(importlib.util.find_spec(n) is None for n in "
        "('omegaprompt', 'omega_lock', 'numpy', 'openai', 'anthropic'));"
        "missing = [n for n in m.__all__ if not hasattr(m, n)];"
        "print('version:', getattr(m, '__version__', 'n/a'));"
        "print('all:', sorted(m.__all__));"
        "sys.exit(1 if missing else 0)"
    )
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONUTF8"] = "1"
    result = subprocess.run(
        [str(python), "-c", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=python.parent.parent,
        env=environment,
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

        print(f"[step] installing wheel: {wheel_path.name}")
        install = subprocess.run(
            [str(python), "-m", "pip", "install", "--disable-pip-version-check", str(wheel_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=venv_dir,
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
        if args.module == "mini_omega_lock":
            cli = python.parent / ("preflight.exe" if os.name == "nt" else "preflight")
            cp949_environment = os.environ.copy()
            cp949_environment.pop("PYTHONPATH", None)
            cp949_environment.update(PYTHONUTF8="0", PYTHONIOENCODING="cp949")
            help_result = subprocess.run(
                [str(cli), "--help"], cwd=venv_dir, capture_output=True,
                env=cp949_environment,
            )
            if help_result.returncode != 0:
                print("installed console help failed under cp949", file=sys.stderr)
                return 1
            help_result.stdout.decode("ascii")
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
