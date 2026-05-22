---
name: Provider probe issue
about: A real-provider probe (strict-schema, judge consistency, latency) misbehaves with a specific provider/model.
title: "[provider] "
labels: provider-probe
---

## Provider + model

- Provider name:
- Model:
- Tier (cloud / local / OpenAI-compatible / other):
- Anything non-default (custom base URL, region, retry settings)?

## Which probe

Tick the one(s) involved:

- [ ] `measure_judge_consistency`
- [ ] `measure_gate_flip_rate`
- [ ] `measure_scale_monotonicity`
- [ ] `probe_strict_schema`
- [ ] `compute_context_margin_from_texts`
- [ ] `project_performance`
- [ ] `empirical_preflight` (composite)
- [ ] MCP tool wrapping one of the above

## What happened

- Inputs (rubric, item, response — use a synthetic example if your real one is sensitive).
- `warnings` returned by `empirical_preflight`.
- Any traceback.

## Reminder: this repo is offline by default

We do **not** add live-provider API tests to default CI. If your report can be reproduced with a synthetic provider (see `tests/test_probes.py::_ScriptedJudgeProvider`), please attach that reproduction. If it cannot, the issue may still be valid but cannot be fixed via CI gates alone.

## Related toolkit

For provider/calibration issues unrelated to preflight probes:

- Calibration loop: [`omegaprompt`](https://github.com/hibou04-ops/omegaprompt)
- Analytical preflight: [`mini-antemortem-cli`](https://github.com/hibou04-ops/mini-antemortem-cli)
