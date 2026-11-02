"""Verify CI tag identity with real temporary Git objects and scoped child envs."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.8.6"
TAG = "v" + VERSION
FLAG = "MINI_OMEGA_LOCK_RELEASE_WORKFLOW"


def _load_script(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ci = _load_script("mini_omega_ci_release_audit_test", "ci_release_audit.py")
legacy = _load_script("mini_omega_pre_tag_audit_test", "release_audit.py")


def _git(root, *args, input=None):
    env = os.environ.copy()
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        env.pop(key, None)
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    return subprocess.run(
        ["git", "-c", "user.name=release-contract-test",
         "-c", "user.email=release-contract-test@example.invalid",
         "-c", "commit.gpgSign=false", "-c", "tag.gpgSign=false", *args],
        cwd=root, env=env, input=input, capture_output=True,
        text=True, encoding="utf-8", check=True,
    ).stdout.strip()


@pytest.fixture
def git_repo(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "mini-omega-lock"\nversion = "{VERSION}"\n', encoding="utf-8"
    )
    package = tmp_path / "src/mini_omega_lock"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(f'__version__ = "{VERSION}"\n', encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "pyproject.toml", "src")
    _git(tmp_path, "commit", "--no-gpg-sign", "-qm", "fixture")
    return tmp_path


def _tag_env(**extra):
    return {"GITHUB_REF": "refs/tags/" + TAG, "GITHUB_REF_TYPE": "tag",
            "GITHUB_REF_NAME": TAG, **extra}


@pytest.mark.parametrize("annotated", [False, True])
@pytest.mark.parametrize("include_type", [False, True])
def test_only_an_actual_current_version_tag_at_head_grants_child_flag(git_repo, annotated, include_type):
    _git(git_repo, "tag", *(["-a", "-m", "fixture release"] if annotated else []), TAG)
    environ = _tag_env(**{FLAG: "inherited-untrusted", "SENTINEL": "preserved"})
    if not include_type:
        environ.pop("GITHUB_REF_TYPE")
        environ.pop("GITHUB_REF_NAME")
    original = dict(environ)
    prepared = ci.prepare_audit_environment(git_repo, environ)
    assert prepared[FLAG] == "1" and prepared["SENTINEL"] == "preserved"
    assert prepared is not environ and environ == original
    assert _git(git_repo, "rev-parse", "--verify", f"refs/tags/{TAG}^{{commit}}") == _git(git_repo, "rev-parse", "HEAD^{commit}")


@pytest.mark.parametrize("context", [
    {},
    {"GITHUB_REF_TYPE": "branch", "GITHUB_REF": "refs/heads/main", "GITHUB_REF_NAME": "main"},
    {"GITHUB_EVENT_NAME": "pull_request", "GITHUB_REF": "refs/pull/42/merge", "GITHUB_REF_NAME": "42/merge"},
])
def test_main_pr_and_non_ci_contexts_remove_inherited_release_flag(git_repo, context):
    _git(git_repo, "tag", TAG)
    environ = {**context, FLAG: "1", "SENTINEL": "kept"}
    original = dict(environ)
    child = ci.prepare_audit_environment(git_repo, environ)
    assert FLAG not in child and child["SENTINEL"] == "kept"
    assert environ == original


@pytest.mark.parametrize("context", [
    {"GITHUB_REF_TYPE": "tag"},
    {"GITHUB_REF_TYPE": "tag", "GITHUB_REF": "refs/heads/main"},
    {"GITHUB_REF_TYPE": "branch", "GITHUB_REF": "refs/tags/" + TAG},
    _tag_env(GITHUB_REF_NAME="v0.8.4"),
    _tag_env(GITHUB_REF="refs/tags/v0.8.4", GITHUB_REF_NAME="v0.8.4"),
])
def test_inconsistent_reference_or_metadata_contexts_fail_closed(git_repo, context):
    _git(git_repo, "tag", TAG)
    with pytest.raises(ValueError):
        ci.prepare_audit_environment(git_repo, {**context, FLAG: "1"})


def test_tag_name_without_a_real_local_tag_is_insufficient(git_repo):
    with pytest.raises(ValueError):
        ci.prepare_audit_environment(git_repo, _tag_env(**{FLAG: "1"}))


def test_tag_at_another_commit_cannot_grant_release_mode(git_repo):
    _git(git_repo, "tag", TAG)
    (git_repo / "later.txt").write_text("later commit\n", encoding="utf-8")
    _git(git_repo, "add", "later.txt")
    _git(git_repo, "commit", "--no-gpg-sign", "-qm", "different HEAD")
    with pytest.raises(ValueError):
        ci.prepare_audit_environment(git_repo, _tag_env())


def test_a_tag_resolving_to_a_blob_cannot_grant_release_mode(git_repo):
    blob = _git(git_repo, "hash-object", "-w", "--stdin", input="not a commit\n")
    _git(git_repo, "update-ref", "refs/tags/" + TAG, blob)
    with pytest.raises(ValueError):
        ci.prepare_audit_environment(git_repo, _tag_env())


@pytest.mark.parametrize("runtime_source", [
    '__version__ = "0.8.4"\n',
    '__version__ = str("0.8.6")\n',
    '__version__ = "0.8.6"\n__version__ = "0.8.6"\n',
    'def ignored():\n    __version__ = "0.8.6"\n',
])
def test_runtime_version_must_be_one_matching_top_level_literal(git_repo, runtime_source):
    _git(git_repo, "tag", TAG)
    (git_repo / "src/mini_omega_lock/__init__.py").write_text(runtime_source, encoding="utf-8")
    with pytest.raises(ValueError):
        ci.prepare_audit_environment(git_repo, _tag_env())


def test_metadata_version_must_match_the_runtime_and_tag(git_repo):
    _git(git_repo, "tag", TAG)
    (git_repo / "pyproject.toml").write_text('[project]\nversion = "0.8.4"\n', encoding="utf-8")
    with pytest.raises(ValueError):
        ci.prepare_audit_environment(git_repo, _tag_env())


def test_missing_git_is_a_context_validation_failure(git_repo, monkeypatch):
    def unavailable(*args, **kwargs):
        raise FileNotFoundError("git unavailable")
    monkeypatch.setattr(ci.subprocess, "run", unavailable)
    with pytest.raises(ValueError):
        ci.prepare_audit_environment(git_repo, _tag_env())


def test_original_pre_tag_guard_and_other_release_markers_remain_active(git_repo, monkeypatch):
    _git(git_repo, "tag", TAG)
    monkeypatch.setattr(legacy, "REPO_ROOT", git_repo)
    monkeypatch.setattr(legacy, "PYPROJECT", git_repo / "pyproject.toml")
    monkeypatch.delenv(FLAG, raising=False)
    assert any("local git tag" in issue for issue in legacy._check_no_release_markers())
    prepared = ci.prepare_audit_environment(git_repo, _tag_env())
    assert FLAG not in os.environ
    with monkeypatch.context() as child:
        child.setenv(FLAG, prepared[FLAG])
        assert legacy._check_no_release_markers() == []
        (git_repo / "RELEASE_DRAFT.md").write_text("STATUS: PUBLISHED\n", encoding="utf-8")
        assert any("STATUS: PUBLISHED" in issue for issue in legacy._check_no_release_markers())
    assert FLAG not in os.environ


@pytest.mark.parametrize("tag_context,exit_code", [(False, 0), (True, 7)])
def test_main_scopes_flag_to_real_child_and_propagates_audit_exit(git_repo, monkeypatch, tag_context, exit_code):
    _git(git_repo, "tag", TAG)
    scripts = git_repo / "scripts"
    scripts.mkdir()
    (scripts / "release_audit.py").write_text(
        'import json, os, pathlib\n'
        'pathlib.Path("child.json").write_text(json.dumps({"flag": os.environ.get("MINI_OMEGA_LOCK_RELEASE_WORKFLOW"), '
        '"sentinel": os.environ.get("AUDIT_TEST_SENTINEL")}), encoding="utf-8")\n'
        'raise SystemExit(int(os.environ["AUDIT_TEST_EXIT"]))\n', encoding="utf-8"
    )
    monkeypatch.setattr(ci, "REPO_ROOT", git_repo)
    for name in ("GITHUB_REF", "GITHUB_REF_TYPE", "GITHUB_REF_NAME"):
        monkeypatch.delenv(name, raising=False)
    context = _tag_env() if tag_context else {"GITHUB_REF_TYPE": "branch", "GITHUB_REF": "refs/heads/main"}
    for name, value in context.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv(FLAG, "inherited-untrusted")
    monkeypatch.setenv("AUDIT_TEST_SENTINEL", "unicode preserved: 검증")
    monkeypatch.setenv("AUDIT_TEST_EXIT", str(exit_code))
    assert ci.main(["--no-network"]) == exit_code
    child = json.loads((git_repo / "child.json").read_text(encoding="utf-8"))
    assert child == {"flag": "1" if tag_context else None, "sentinel": "unicode preserved: 검증"}
    assert os.environ[FLAG] == "inherited-untrusted"


def test_main_rejects_invalid_context_before_launching_audit(git_repo, monkeypatch, capsys):
    monkeypatch.setattr(ci, "REPO_ROOT", git_repo)
    for name, value in _tag_env(GITHUB_REF_NAME="wrong").items():
        monkeypatch.setenv(name, value)
    assert ci.main(["--no-network"]) == 2
    assert "CI audit context rejected" in capsys.readouterr().err
    assert not (git_repo / "child.json").exists()


def test_main_diagnostics_are_ascii_safe_and_no_network_flag_is_required(monkeypatch, capsys):
    def invalid(*args, **kwargs):
        raise ValueError("invalid context: 검증 😀")
    monkeypatch.setattr(ci, "prepare_audit_environment", invalid)
    assert ci.main(["--no-network"]) == 2
    capsys.readouterr().err.encode("ascii", errors="strict")
    with pytest.raises(SystemExit) as caught:
        ci.main([])
    assert caught.value.code == 2
