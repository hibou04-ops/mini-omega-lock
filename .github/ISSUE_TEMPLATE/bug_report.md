---
name: Bug report
about: A reproducible defect in `mini_omega_lock` (probes, MCP server, or scripts).
title: "[bug] "
labels: bug
---

## Summary

One sentence describing the defect.

## Reproduction

```bash
# Exact commands. Include version output:
python -c "import mini_omega_lock; print(mini_omega_lock.__version__)"
```

Inputs (rubric, dataset item, response, provider config). If provider involvement is suspected, please prefer a synthetic / scripted provider — see `tests/test_probes.py::_ScriptedJudgeProvider` for a minimal pattern.

## Expected vs actual

- Expected: …
- Actual: …
- Diff: …

## Environment

- OS / Python:
- `mini-omega-lock` version:
- `omegaprompt` version:
- Did you install with `[mcp]` extra?

## Did you run the offline checks before filing?

- [ ] `python -m pytest -q`
- [ ] `python scripts/check_repo_consistency.py`
- [ ] `python examples/demo_replay.py`
- [ ] `python scripts/run_golden_cases.py --check`

If any of these reproduce the bug, paste the output above. If none of them do, the bug is likely outside the package's deterministic surface — please describe where it appears.
