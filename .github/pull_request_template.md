<!--
Pull request template for hibou04-ops/mini-omega-lock.
Keep the checklist below; reviewers gate on it.
-->

## What this PR changes

A one-paragraph summary. Link to issues being closed.

## Why

What problem does this solve? Why now? If this changes a contract
(public API shape, warning text, fail-closed default), say so explicitly.

## Verification

Local commands run before submitting (paste outputs where relevant):

- [ ] `python -m pytest -q`
- [ ] `python scripts/generate_readme_claims.py --check`
- [ ] `python scripts/check_repo_consistency.py`
- [ ] `python examples/demo_replay.py`
- [ ] `python scripts/run_golden_cases.py --check`
- [ ] `python scripts/verify_fixture_integrity.py`
- [ ] `python scripts/release_audit.py --no-network`

If a check above is intentionally skipped, explain why on the same line.

## Trust boundary

- [ ] No live API calls added to default tests or default CI.
- [ ] No unbacked README claim added. Any new claim is registered in `docs/claim_ledger.md` (or marked `not-claimed`).
- [ ] No weakening of fail-closed semantics in `empirical_preflight` or `probe_strict_schema`.
- [ ] No change to `LICENSE` / `NOTICE` / `AUTHORS.md` / `PRE_EXISTING_IP.md` / `IP_DEFENSE_CHECKLIST.md`.

## Release impact

- [ ] No publish performed (no `twine upload`, no PyPI artifact pushed).
- [ ] No tag created or pushed.
- [ ] No GitHub release drafted or published.

If this PR is a release-prep PR, link to `docs/release_checklist.md` and confirm each step was followed.

## Reviewer pointers

What's the riskiest part of the change to read first? Anything that would benefit from a focused look (warning text, fail-closed default, MCP tool signature)?
