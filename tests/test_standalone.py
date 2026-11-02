# SPDX-License-Identifier: Apache-2.0
"""Core installation must work while parent, optimizer and SDK imports are blocked."""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_dependencies_exclude_parent_and_bridge_is_explicit():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["dependencies"] == ["pydantic>=2.6.0"]
    assert project["optional-dependencies"]["bridge"] == ["omegaprompt>=1.1.0"]


def test_core_cli_and_offline_demo_never_import_parent_or_provider_sdks():
    program = """
import importlib.abc
import runpy
import sys
class BlockHeavyImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'omegaprompt', 'omega_lock', 'numpy', 'openai', 'anthropic', 'google'}:
            raise AssertionError('unexpected heavy dependency import: ' + fullname)
sys.meta_path.insert(0, BlockHeavyImports())
from mini_omega_lock import compute_empirical_noise_ceiling
from mini_omega_lock.cli import main
assert compute_empirical_noise_ceiling([0.25]) == 0.25
try:
    main(['--help'])
except SystemExit as exc:
    assert exc.code == 0
else:
    raise AssertionError('--help did not exit')
runpy.run_path('examples/demo_replay.py', run_name='__main__')
"""
    result = subprocess.run([sys.executable, "-c", program], cwd=ROOT,
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr
