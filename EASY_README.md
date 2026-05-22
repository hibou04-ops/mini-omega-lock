# mini-omega-lock — Easy Start

> The short version, for people who found the main README intimidating.
> Full doc: [README.md](README.md) · 한국어 Easy: [EASY_README_KR.md](EASY_README_KR.md)

## What is this?

An optional plug-in for [omegaprompt](https://pypi.org/project/omegaprompt/) that **measures your actual environment** before you calibrate, so omegaprompt can adapt its thresholds to what your setup can actually deliver.

If you're running omegaprompt with provider/endpoint/judge defaults and nothing feels weird, you don't need this. Install it only if any of these apply:
- Your judge gives different scores to the same response across runs.
- Your local/cloud endpoint sometimes rejects strict schema.
- You want to know how long a full calibration will take *before* running it.

## What it measures (5 measurement categories; 6 MCP tools)

> The five categories below are the **conceptual** probe surface — judge / endpoint / context / latency / noise floor. The MCP server exposes them as **6 tools** because hard-gate flip rate (`measure_gate_flip_rate`) is wired as its own tool under the judge category. The canonical tool list lives in [docs/generated/claims.md](docs/generated/claims.md).


| Probe | What it tells you | Default cost |
|---|---|---|
| **Judge consistency** | Same (response, rubric) scored N times → `1 − coefficient-of-variation`. Low = noisy judge, you should `rescore_count > 1`. | 3 judge API calls |
| **Endpoint schema reliability** | Fraction of STRICT_SCHEMA probes that parse. `< 0.9` triggers JSON_OBJECT fallback. | 0–3 API calls (caller-provided) |
| **Context budget margin** | `1 − (approx_tokens / context_window)`. Negative = overflow risk. | 0 (pure computation) |
| **Performance projection** | Mean latency × dataset size × candidates → projected wall time. | 1 judge call (latency probe) |
| **Noise floor** | Stdev of fitness under identical params. Sets adaptive `min_kc4`. | 0 API calls (caller supplies samples) |

Total `empirical_preflight()` default budget: **~4 API calls**. Under $0.01 on frontier tiers.

## Install

```bash
pip install mini-omega-lock
```

Requires `omegaprompt>=1.1.0` (it imports omegaprompt's preflight contracts to build the records it emits).

## The minimum working example

```python
from omegaprompt import make_provider, PreflightReport, derive_adaptation_plan
from omegaprompt.domain.dataset import DatasetItem
from omegaprompt.domain.judge import Dimension, JudgeRubric
from omegaprompt.judges.llm_judge import LLMJudge
from mini_omega_lock import empirical_preflight

judge_provider = make_provider("anthropic")
judge  = LLMJudge(provider=judge_provider)
rubric = JudgeRubric(dimensions=[Dimension(name="accuracy", description="correct?", weight=1.0)])
probe  = DatasetItem(id="probe", input="2+2", reference="4")

judge_quality, endpoint, performance, warnings = empirical_preflight(
    judge=judge,
    rubric=rubric,
    probe_item=probe,
    probe_response="4",
    consistency_repeats=3,   # default
)
for w in warnings:
    print(f"[mini-omega-lock] {w}")

# Feed into omegaprompt's adaptation layer:
report = PreflightReport(judge_quality=judge_quality, endpoint=endpoint, performance=performance)
plan   = derive_adaptation_plan(report=report)
# plan.min_kc4_override, plan.rescore_count, plan.schema_mode_override, etc.
```

That's it. 4 live API calls. `plan` tells omegaprompt what to adjust. The `warnings` list names every field that fell back to a fail-closed default — treat it as load-bearing in CI.

## Exported functions

The full public API lives in `mini_omega_lock.__all__`; the regenerated list is in [docs/generated/claims.md](docs/generated/claims.md). The five most common entry points:

```python
from mini_omega_lock import (
    empirical_preflight,            # composite: runs all probes, returns 4-tuple incl. warnings
    measure_judge_consistency,      # individual: returns (JudgeQualityMeasurement, raw scores)
    probe_strict_schema,            # individual: returns EndpointMeasurement
    compute_context_margin,         # pure compute: returns float (chars heuristic)
    noise_floor_estimate,           # pure compute: returns float stdev
)
```

Also exported and equally importable: `compute_context_margin_from_texts` (tokenizer-exact variant), `measure_gate_flip_rate`, `measure_scale_monotonicity`, `project_performance`. Use `empirical_preflight` for the default flow; call the individuals when you want finer control (e.g., compute noise floor from your own fitness samples across multiple calibration runs).

## When to use it

- Judge-consistency suspicion: you've seen the same response get different scores.
- Local or OpenAI-compatible endpoint: you can't trust its STRICT_SCHEMA support.
- Long-running calibrations: you want a wall-time estimate before committing.

## When to skip it

- Stock frontier providers + LLMJudge on known-stable tiers. Defaults are fine.
- You're in rapid iteration — preflight adds ~10s to every run.
- Tests / CI without API access (omegaprompt runs fine with declared defaults).

## One caveat: the noise floor

`empirical_preflight` **does not compute noise floor**. The `PerformanceMeasurement.noise_floor` it returns is a placeholder (0.0). True noise floor requires multiple complete calibration runs with identical params — you do those, collect the fitness samples, then call `noise_floor_estimate(samples)` separately and patch the plan.

This is by design, not a bug: a single preflight probe can't measure it.

## Go deeper

- Full contract definitions: `omegaprompt.preflight.contracts` (in the omegaprompt package)
- Adaptation rules: `omegaprompt.preflight.adaptation.derive_adaptation_plan`
- Sibling analytical preflight (zero API calls, deterministic rules): [mini-antemortem-cli](https://pypi.org/project/mini-antemortem-cli/)

License: Apache 2.0. Copyright (c) 2026 hibou.
