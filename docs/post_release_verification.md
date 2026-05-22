# Post-release verification

After a `mini-omega-lock` release lands on PyPI, the following checks confirm that what was published matches what was audited. None of them are run automatically by the package; they are the human-operated complement to `scripts/publish_readiness.py --no-network`.

## When to run

Run the no-network section immediately after publish. The network section is optional and only useful when you want to verify the PyPI artifact matches the local one.

## No-network checks (default)

```bash
python scripts/post_release_verify.py --no-network
```

What it does:

1. Re-runs `pytest -q`, `generate_readme_claims.py --check`, `check_repo_consistency.py`, the demo replay, the golden cases, and the fixture integrity check. (Identical to the audit; included so post-release runs catch drift introduced between the audit and a manual publish.)
2. Confirms `dist/` still contains exactly the wheel + sdist that publish_readiness validated. Any change since the audit is reported.
3. Confirms the version in `pyproject.toml` and `__init__.py` is unchanged since the audit (the publish should not have bumped versions).

The script always exits non-zero when any of these checks fail; it never asserts "publish succeeded" — that is a fact about PyPI / GitHub state and is not part of the no-network path.

## Network checks (opt-in)

The network path is documented but **not** the default and **not** run in CI. Invoke it manually when you want to confirm the PyPI artifact:

```bash
python scripts/post_release_verify.py --network --version <version>
```

What it does (when `--network` is supplied):

1. Downloads the wheel from PyPI (`pip download --no-deps --dest tmp/post_release/`).
2. Compares the SHA-256 of the downloaded wheel to the local `dist/` wheel.
3. Hits `pypi.org/pypi/mini-omega-lock/json` and asserts the `info.version` field equals `<version>`.

Failure modes the network path can detect:

- Wrong artifact uploaded (hash mismatch).
- Cancelled upload (PyPI does not have the version yet).
- Wrong artifact published from a different machine with stale changes.

Successful network path output:

```text
[ok] PyPI version matches: 0.5.0
[ok] wheel SHA-256 matches local dist/mini_omega_lock-0.5.0-py3-none-any.whl
```

Failure mode output:

```text
[fail] PyPI version is 0.4.0 but local pyproject.toml is 0.5.0 — did the publish actually run?
```

## Smoke install from PyPI

After a release, in a fresh shell:

```bash
python -m venv tmp/post_release_smoke
tmp/post_release_smoke/bin/python -m pip install --upgrade pip
tmp/post_release_smoke/bin/python -m pip install "mini-omega-lock==<version>"
tmp/post_release_smoke/bin/python -c "
import mini_omega_lock
print('version:', mini_omega_lock.__version__)
for name in mini_omega_lock.__all__:
    assert hasattr(mini_omega_lock, name), name
print('public API:', sorted(mini_omega_lock.__all__))
"
```

On Windows use `tmp\post_release_smoke\Scripts\python.exe` instead of `tmp/post_release_smoke/bin/python`. The `scripts/wheel_smoke_install.py` script already handles this platform split for the local wheel; the post-release smoke from PyPI is intentionally a manual / readable command rather than a hidden script step.

## When the post-release check fails

The release is not in a known-good state. Open a `claim_drift.md` issue describing the mismatch (artifact hash, version, behavior). Do not patch the published release; cut a new patch version. There is no "yank without replacement" path documented here because every yank breaks downstream consumers without a fix.

## What this document does **not** claim

- Not a claim that the PyPI release was generated from this exact commit — see git tags for that, and verify with the human reviewer who pushed them.
- Not a substitute for the audit. The audit is what blocks a bad publish; this document only confirms a publish happened cleanly.
- Not a claim that the package works against a particular provider. The smoke install only checks the public Python API is importable; live-provider validation is out of scope.
