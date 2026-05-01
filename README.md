# mini-omega-lock

> **Empirical preflight probes for [omegaprompt](https://pypi.org/project/omegaprompt/) calibration.** Measures judge consistency, endpoint schema reliability, context-budget margin, latency, and noise floor — emits `PreflightReport` records that omegaprompt's `derive_adaptation_plan` consumes.

[![CI](https://github.com/hibou04-ops/mini-omega-lock/actions/workflows/ci.yml/badge.svg)](https://github.com/hibou04-ops/mini-omega-lock/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/badge/pypi-0.3.0-blue.svg)](https://pypi.org/project/mini-omega-lock/)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org)
[![Tests](https://img.shields.io/badge/tests-40%20passing-brightgreen.svg)](tests/)
[![Parent](https://img.shields.io/badge/parent-omegaprompt%E2%89%A51.4.0-blueviolet.svg)](https://pypi.org/project/omegaprompt/)

> **Part of the omegaprompt toolkit** — [omegaprompt](https://github.com/hibou04-ops/omegaprompt) (calibration engine) · [omega-lock](https://github.com/hibou04-ops/omega-lock) (audit framework) · [antemortem-cli](https://github.com/hibou04-ops/antemortem-cli) (pre-implementation recon CLI) · [mini-omega-lock](https://github.com/hibou04-ops/mini-omega-lock) (empirical preflight, this repo) · [mini-antemortem-cli](https://github.com/hibou04-ops/mini-antemortem-cli) (analytical preflight) · [Antemortem](https://github.com/hibou04-ops/Antemortem) (methodology). Cross-toolkit cookbook: [AGENT_TRIGGERS.md](https://github.com/hibou04-ops/omegaprompt/blob/main/AGENT_TRIGGERS.md).

```bash
pip install omegaprompt mini-omega-lock
```

**MCP server.** This package also exposes its five probes (`empirical_preflight`, `measure_judge_consistency`, `compute_context_margin`, `noise_floor_estimate`, `project_performance`) as agent-callable MCP tools. Run `pip install "mini-omega-lock[mcp]"` then `python -m mini_omega_lock.mcp` (stdio, default for Claude Code). See [AGENT_TRIGGERS.md scenario 2](https://github.com/hibou04-ops/omegaprompt/blob/main/AGENT_TRIGGERS.md#scenario-2--pre-calibration-sanity-check).

---

## TL;DR

`omegaprompt` ships a **plugin interface** for preflight probes (`omegaprompt.preflight.contracts` + `omegaprompt.preflight.adaptation`) but no probe implementation. This package fills that gap with five empirical measurements, then hands the result to omegaprompt's adaptation layer:

- **Judge consistency** — same (response, rubric) scored N times → `1 - CV`. Low = noisy judge, need `rescore_count > 1`.
- **Schema reliability** — STRICT_SCHEMA probe success rate. < 0.9 triggers `JSON_OBJECT` fallback automatically.
- **Context budget margin** — `1 - (longest_call_tokens / context_window)`. Negative = guaranteed overflow.
- **Performance projection** — probe latency × calibration scale → wall-time estimate before launching.
- **Noise floor** — fitness stdev under identical params → adaptive `min_kc4` threshold.

One call (`empirical_preflight()`) returns the three records `omegaprompt`'s `derive_adaptation_plan()` consumes.

> **Looking for the analytical (no-API, deterministic) preflight?** See sibling tool [`mini-antemortem-cli`](https://pypi.org/project/mini-antemortem-cli/) — same plugin interface, deterministic rule-based classifier instead of LLM probes.

---

## Quick start (3-minute)

```python
from omegaprompt import make_provider, PreflightReport, derive_adaptation_plan
from omegaprompt.domain.dataset import DatasetItem
from omegaprompt.domain.judge import Dimension, JudgeRubric
from omegaprompt.judges.llm_judge import LLMJudge
from mini_omega_lock import empirical_preflight

judge_provider = make_provider("anthropic")
judge = LLMJudge(provider=judge_provider)
rubric = JudgeRubric(dimensions=[Dimension(name="accuracy", description="x", weight=1.0)])
probe_item = DatasetItem(id="probe", input="2+2", reference="4")

# One call → five measurements → adaptation plan
judge_quality, endpoint, performance = empirical_preflight(
    judge=judge, rubric=rubric, probe_item=probe_item, n_consistency_runs=3,
)

report = PreflightReport(judge_quality=judge_quality, endpoint=endpoint, performance=performance)
plan = derive_adaptation_plan(report)
print(plan.recommendations)
```

> 👋 Simpler intro: [EASY_README.md](EASY_README.md) (English) · [EASY_README_KR.md](EASY_README_KR.md)

---

## Why this is separate from omegaprompt

`omegaprompt` ships a **plugin interface** (`omegaprompt.preflight.contracts` + `omegaprompt.preflight.adaptation`) but no probe code. Standalone users do not need preflight probes — they run calibration with declared defaults. Users who want adaptive thresholds tuned to their actual infrastructure install this package alongside:

```bash
pip install omegaprompt mini-omega-lock
```

## What it measures

| Measurement | Function | What it tells you |
|---|---|---|
| Judge consistency | `measure_judge_consistency` | Same (response, rubric) scored `N` times; `1 - CV`. Low = noisy judge, need `rescore_count > 1`. |
| Endpoint schema reliability | `probe_strict_schema` | `STRICT_SCHEMA` probe success fraction. `< 0.9` triggers `JSON_OBJECT` fallback. |
| Context budget margin | `compute_context_margin` | `1 - (longest_call_tokens / context_window)`. Negative = overflow. |
| Performance projection | `project_performance` | Mean probe latency → projected calibration wall time. |
| Noise floor | `noise_floor_estimate` | Stdev of fitness under identical parameters. Sets adaptive `min_kc4`. |

The composite entry point is `empirical_preflight()`, which runs all five in one call and returns the three measurement records omegaprompt's adaptation layer consumes.

## Usage

```python
from omegaprompt import make_provider, PreflightReport, derive_adaptation_plan
from omegaprompt.domain.dataset import DatasetItem
from omegaprompt.domain.judge import Dimension, JudgeRubric
from omegaprompt.judges.llm_judge import LLMJudge
from mini_omega_lock import empirical_preflight

judge_provider = make_provider("anthropic")
judge = LLMJudge(provider=judge_provider)
rubric = JudgeRubric(dimensions=[Dimension(name="accuracy", description="x", weight=1.0)])
probe_item = DatasetItem(id="probe", input="2+2", reference="4")

judge_quality, endpoint, performance = empirical_preflight(
    judge=judge,
    rubric=rubric,
    probe_item=probe_item,
    probe_response="4",
    consistency_repeats=3,
    dataset_size_hint=10,
    candidates_expected=20,
)

report = PreflightReport(
    judge_quality=judge_quality,
    endpoint=endpoint,
    performance=performance,
)
plan = derive_adaptation_plan(report=report)
# plan.min_kc4_override, plan.rescore_count, etc.
```

## Design principles

- **No fabricated numbers.** Every measurement is computed from a real provider response. No heuristic estimation.
- **Minimal probe budget.** Default 3 consistency repeats + 3 schema probes + 1 context-margin compute = 7-10 API calls per preflight. Worth < $0.01 on frontier tiers.
- **Protocol-conformant output.** Emits `omegaprompt.preflight.contracts.JudgeQualityMeasurement` / `EndpointMeasurement` / `PerformanceMeasurement` exactly. No shape drift.
- **Composable.** Can run alongside `mini-antemortem-cli` (analytical preflight) into the same `PreflightReport`.

## Validation

All adapter tests mock the provider SDK; no network, no API credits, fully offline. Run with `pytest -q`.

## Relation to the family

- **[omega-lock](https://github.com/hibou04-ops/omega-lock)** — parameter-calibration framework. The naming "mini-omega-lock" echoes this family; the *sensitivity + walk-forward + KC-4* discipline comes from there.
- **[omegaprompt](https://pypi.org/project/omegaprompt/)** — prompt calibration engine. This package feeds its preflight plugin interface.
- **[mini-antemortem-cli](https://pypi.org/project/mini-antemortem-cli/)** — analytical sibling. Runs deterministic trap classification over config before calibration.

## License

Apache 2.0. See [LICENSE](LICENSE).

**License history.** PyPI distributions of version 0.1.0 were shipped with an MIT `LICENSE` file. The repository was relicensed to Apache 2.0 on 2026-04-22 (commit `ff489a9`); 0.2.0 (2026-04-28) and all later versions ship under Apache 2.0. Anyone who installed 0.1.0 holds an MIT license to that copy — license changes do not apply retroactively.
