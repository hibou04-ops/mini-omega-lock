# Release checklist

The release path for `mini-omega-lock` is deliberately small. This checklist is the same one `scripts/publish_readiness.py --no-network` enforces; if any step here fails, that script fails.

## What this checklist does and does not do

- It **gates** a release by verifying generated docs, README consistency, deterministic artifacts, and the local wheel-install smoke.
- It does **not** publish, tag, or release. Those steps are explicitly excluded — see the bottom of this file for what a human still has to do.

## Step 0 — start clean

```bash
git status --porcelain
```

Must be empty. Uncommitted changes mean the gate is being run against a state that isn't going out to PyPI.

## Step 1 — install in editable mode with all extras

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev,mcp]"
```

`mcp` is required so the full MCP test surface participates in `pytest -q`. Skipping it means MCP regressions slip past the gate.

## Step 2 — deterministic tests

```bash
python -m pytest -q
```

Must pass on the current branch. Skipped tests are allowed when their `importorskip` reasons are recorded in the test file; failed tests are not.

## Step 3 — generated claims drift

```bash
python scripts/generate_readme_claims.py --check
```

Exits non-zero if any file under `docs/generated/` is stale relative to `pyproject.toml`, `src/mini_omega_lock/__init__.py`, or `src/mini_omega_lock/mcp/server.py`. Regenerate with `python scripts/generate_readme_claims.py` and re-run.

## Step 4 — repository consistency

```bash
python scripts/check_repo_consistency.py
```

Checks version sync, README badges, top-link existence, install/import naming, MCP run command, public API names, MCP tool counts (English + Korean phrasing), forbidden hard-coded test-count badges, and that the generator agrees with disk.

## Step 5 — demo replay (no network)

```bash
python examples/demo_replay.py
python -m pytest -q tests/test_demo_replay.py
```

The demo's stdout must equal `examples/_demo_output.txt` byte-for-byte (after the documented timing mask). The pytest run is the canonical assertion.

## Step 6 — offline golden cases

```bash
python scripts/run_golden_cases.py --check
```

Replays every JSON case under `benchmarks/golden_cases/` against `empirical_preflight` and compares deterministic fields and warning substrings.

## Step 7 — fixture integrity

```bash
python scripts/verify_fixture_integrity.py
```

Recomputes the SHA-256 of every fixture file and compares to `benchmarks/golden_cases/manifest.json`. Any mismatch — accidental edit, encoding drift, charset change — fails the step.

## Step 8 — release audit (no network)

```bash
python scripts/release_audit.py --no-network
```

Runs steps 2–7 in order, plus:

- Verifies no in-tree `v<version>` git tag (the audit must fail if `git tag -l v<version>` already shows the tag locally).
- Verifies that `dist/` contains at most the previously-built wheel and sdist for the current version (no rogue uploads pending).
- Verifies `.github/workflows/ci.yml` contains the regenerated audit steps.

## Step 9 — build wheel + sdist

```bash
python -m build
```

Requires the `build` package. If missing, this is reported as `TOOLING_MISSING: build`. Output is written to `dist/`.

## Step 10 — wheel smoke install (temp venv)

```bash
python scripts/wheel_smoke_install.py dist/mini_omega_lock-<version>-py3-none-any.whl
```

Creates a fresh `venv` under `tmp/`, installs the wheel, imports `mini_omega_lock`, and verifies every name in `__all__` is importable. Cleans up on success or failure. Does NOT install with `[mcp]` extra (no network in CI by default); install of optional extras is a separate manual step.

## Step 11 — publish readiness

```bash
python scripts/publish_readiness.py --no-network
```

The publish gate. Re-runs steps 3, 4, 5, 6, 7, 8, 9, 10 in sequence and exits 0 only when all pass. This is the final mechanical answer to "is this ready to publish?".

## Step 12 — human-only steps (not automated)

The following steps are intentionally **not** in any script in this repository:

- `python -m twine upload dist/*` — the publish itself.
- `git tag v<version>` — version tagging.
- `git push origin v<version>` — pushing the tag.
- Drafting / publishing a GitHub release.
- Updating the version in `pyproject.toml` and `src/mini_omega_lock/__init__.py` for the next cycle.

These remain human decisions backed by judgement that cannot be encoded in `--no-network` gates. The point of step 11 is to verify everything that *can* be checked has been checked; the publish itself is still a deliberate manual action.

## What "release performed" means for the audit

For `scripts/release_audit.py --no-network`, "release performed" — which must be absent — is defined as ANY of:

- A local git tag matching `v<pyproject.version>`.
- A wheel or sdist file in `dist/` that does **not** match either:
  - the current `<name>-<version>` exactly, or
  - the previously-committed file fingerprints (`dist/` is allowed to contain the artifacts the previous release built).
- A file at `RELEASE_DRAFT.md` containing the literal string `STATUS: PUBLISHED`.

If any of these are present, the audit exits non-zero. The audit never *creates* these markers — it only checks for them.

## Post-release

See `docs/post_release_verification.md` for what to do after a release lands on PyPI.
