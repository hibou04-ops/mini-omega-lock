# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Kyunghoon Gwak <hibouaile04@gmail.com>
"""Reviewer item #7: MCP rubric paths must stay inside MINI_OMEGA_WORKSPACE_ROOT.

Pre-fix: ``rubric="/etc/passwd"`` (or any absolute path / ``..`` traversal)
would be passed straight to ``JudgeRubric.from_json(Path(...))``. The file
read failure or schema-validation error would echo the path / partial
contents back through the MCP error response. Now path inputs resolve to
the workspace root and out-of-tree paths raise a structured ValueError
before any disk read.

Inline dicts skip the path-validation branch entirely — agents that pass
the rubric inline are unaffected.
"""

from __future__ import annotations

import json
import pytest

mcp = pytest.importorskip("mcp")


@pytest.fixture
def workspace(monkeypatch, tmp_path):
    """Pin MINI_OMEGA_WORKSPACE_ROOT to a tmpdir so each test owns its boundary."""
    monkeypatch.setenv("MINI_OMEGA_WORKSPACE_ROOT", str(tmp_path))
    return tmp_path


def _write_rubric(path):
    """Write a minimal valid JudgeRubric JSON to ``path``."""
    rubric = {
        "dimensions": [
            {"name": "q", "description": "q", "weight": 1.0, "scale": [0, 1]},
        ],
        "hard_gates": [],
    }
    path.write_text(json.dumps(rubric), encoding="utf-8")


def test_rubric_path_inside_workspace_resolves_normally(workspace):
    """A rubric path inside the configured workspace loads as before."""
    from mini_omega_lock.mcp.server import _resolve_rubric

    rubric_path = workspace / "rubric.json"
    _write_rubric(rubric_path)
    result = _resolve_rubric(str(rubric_path))
    assert result.dimensions[0].name == "q"


def test_rubric_path_outside_workspace_raises(workspace, tmp_path_factory):
    """A path outside the workspace root must fail BEFORE any disk read."""
    from mini_omega_lock.mcp.server import _resolve_rubric

    # Build a rubric in a sibling tmpdir — outside the configured workspace.
    outside = tmp_path_factory.mktemp("outside")
    outside_path = outside / "rubric.json"
    _write_rubric(outside_path)

    with pytest.raises(ValueError, match="outside the configured workspace root"):
        _resolve_rubric(str(outside_path))


def test_rubric_path_with_traversal_raises(workspace):
    """``..`` traversal that escapes the workspace root must raise."""
    from mini_omega_lock.mcp.server import _resolve_rubric

    # The traversal target is outside the workspace by construction.
    traversal = workspace / ".." / ".." / "etc" / "passwd"
    with pytest.raises(ValueError, match="outside the configured workspace root"):
        _resolve_rubric(str(traversal))


def test_rubric_inline_dict_is_unaffected_by_workspace_boundary(workspace):
    """Inline dicts skip the path-validation branch — no filesystem access."""
    from mini_omega_lock.mcp.server import _resolve_rubric

    inline = {
        "dimensions": [
            {"name": "q", "description": "q", "weight": 1.0, "scale": [0, 1]},
        ],
        "hard_gates": [],
    }
    result = _resolve_rubric(inline)
    assert result.dimensions[0].name == "q"


def test_workspace_root_defaults_to_cwd_when_env_unset(monkeypatch, tmp_path):
    """When MINI_OMEGA_WORKSPACE_ROOT is unset, the default is cwd. A rubric
    written under cwd loads; one outside cwd raises. This preserves
    backward compatibility for single-project setups."""
    from mini_omega_lock.mcp.server import _resolve_rubric

    monkeypatch.delenv("MINI_OMEGA_WORKSPACE_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)

    rubric_inside = tmp_path / "rubric.json"
    _write_rubric(rubric_inside)
    # Inside cwd: succeeds.
    assert _resolve_rubric(str(rubric_inside)).dimensions[0].name == "q"


def test_workspace_root_env_var_override_widens_boundary(monkeypatch, tmp_path_factory):
    """Setting MINI_OMEGA_WORKSPACE_ROOT to an explicit dir lets the agent
    operate on that dir even when cwd is elsewhere."""
    from mini_omega_lock.mcp.server import _resolve_rubric

    project = tmp_path_factory.mktemp("project")
    rubric_path = project / "rubric.json"
    _write_rubric(rubric_path)

    elsewhere = tmp_path_factory.mktemp("elsewhere")
    monkeypatch.chdir(elsewhere)
    monkeypatch.setenv("MINI_OMEGA_WORKSPACE_ROOT", str(project))

    # The rubric is OUTSIDE cwd but INSIDE the configured workspace root.
    assert _resolve_rubric(str(rubric_path)).dimensions[0].name == "q"
