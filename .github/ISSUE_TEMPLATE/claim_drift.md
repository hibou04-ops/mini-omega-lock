---
name: Claim drift
about: A public claim in README / EASY_README / docs that source/tests don't back up.
title: "[claim drift] "
labels: claim-drift, documentation
---

## Claim location

Paste the exact line and its file:

```
file:    docs/.../foo.md (line N)
content: "<the exact sentence>"
```

## Why it does not match the source

Point at the source-of-truth that contradicts the claim:

- File: `src/...`
- Test: `tests/...`
- pyproject value:
- Other:

## What the claim ledger says

Open `docs/claim_ledger.md` — is the claim listed? If yes, paste its row. If no, that itself is a defect of the ledger (every public claim must be ledgered).

## Suggested fix

One of:

- [ ] Update the claim to match the source.
- [ ] Update the source to match the claim (specify which).
- [ ] Remove the claim entirely (no defensible source).

## Reproduction of the gate

Did either of these scripts catch the drift?

- [ ] `python scripts/check_repo_consistency.py`
- [ ] `python scripts/generate_readme_claims.py --check`

If neither did, the checker has a gap — please describe how to extend it.
