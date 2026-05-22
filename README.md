# mini-omega-lock

> **Empirical preflight probes for [omegaprompt](https://pypi.org/project/omegaprompt/) calibration.** Measures judge consistency, endpoint schema reliability, context-budget margin, latency, and noise floor — emits `PreflightReport` records that omegaprompt's `derive_adaptation_plan` consumes.

[![CI](https://github.com/hibou04-ops/mini-omega-lock/actions/workflows/ci.yml/badge.svg)](https://github.com/hibou04-ops/mini-omega-lock/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/badge/pypi-0.5.0-blue.svg)](https://pypi.org/project/mini-omega-lock/)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org)
[![Parent](https://img.shields.io/badge/parent-omegaprompt%E2%89%A51.1.0-blueviolet.svg)](https://pypi.org/project/omegaprompt/)

```bash
pip install mini-omega-lock
```

## Trust & verification

| Topic | English | 한국어 |
|---|---|---|
| Generated source-of-truth claims | [docs/generated/claims.md](docs/generated/claims.md) | [docs/generated/claims_kr.md](docs/generated/claims_kr.md) |
| Trust model | [docs/trust_model.md](docs/trust_model.md) | [docs/trust_model_kr.md](docs/trust_model_kr.md) |
| Toolkit positioning | [docs/toolkit_positioning.md](docs/toolkit_positioning.md) | [docs/toolkit_positioning_kr.md](docs/toolkit_positioning_kr.md) |
| Claim ledger | [docs/claim_ledger.md](docs/claim_ledger.md) | [docs/claim_ledger_kr.md](docs/claim_ledger_kr.md) |
| Examples / deterministic demo | [docs/examples.md](docs/examples.md) | [docs/examples_kr.md](docs/examples_kr.md) |
| Release checklist | [docs/release_checklist.md](docs/release_checklist.md) | — |
| Post-release verification | [docs/post_release_verification.md](docs/post_release_verification.md) | — |
| Simpler intro | [EASY_README.md](EASY_README.md) | [EASY_README_KR.md](EASY_README_KR.md) |
| Full Korean | — | [README_KR.md](README_KR.md) |
| Cross-toolkit cookbook | [AGENT_TRIGGERS.md](https://github.com/hibou04-ops/omegaprompt/blob/main/AGENT_TRIGGERS.md) | — |

Sibling projects: [omegaprompt](https://github.com/hibou04-ops/omegaprompt) (calibration engine) · [omega-lock](https://github.com/hibou04-ops/omega-lock) (broader audit framework) · [antemortem-cli](https://github.com/hibou04-ops/antemortem-cli) (pre-implementation recon CLI) · [mini-antemortem-cli](https://github.com/hibou04-ops/mini-antemortem-cli) (analytical preflight) · [Antemortem](https://github.com/hibou04-ops/Antemortem) (methodology).

## Use it when

- The same response keeps getting different judge scores across runs.
- Your endpoint sometimes rejects STRICT_SCHEMA mode silently.
- You want a wall-time estimate before launching a long calibration.

You don't need it when you're on stock frontier-tier providers with declared defaults — `omegaprompt` runs fine without probes there.

## Trust loop (no network)

These commands run entirely offline (no provider/API keys). They are also the commands that `scripts/release_audit.py` enforces — keeping local CI and release gate in lockstep.

```bash
python -m pip install -e ".[dev,mcp]"
python -m pytest -q
python scripts/generate_readme_claims.py --check
python scripts/check_repo_consistency.py
python examples/demo_replay.py
python scripts/run_golden_cases.py --check
python scripts/verify_fixture_integrity.py
python scripts/release_audit.py --no-network
```

### Deterministic demo (one command, no API keys)

```bash
python examples/demo_replay.py
```

Replays `empirical_preflight` against a scripted fake judge; the output is byte-for-byte equal to `examples/_demo_output.txt` (verified by `tests/test_demo_replay.py`). Use this as the "did I break the warning surface?" smoke test.

## How is this different?

| Capability | `mini-omega-lock` (this) | `mini-antemortem-cli` | `omegaprompt` default preflight | Ad-hoc provider smoke test |
|---|---|---|---|---|
| Live empirical judge probe (production) | yes — scripted/mocked in tests | no (analytical) | no (declared defaults) | varies |
| Judge consistency / gate-flip measurement | `measure_judge_consistency`, `measure_gate_flip_rate` | not in scope | not in scope | ad-hoc |
| Strict-schema reliability measurement | `probe_strict_schema`; **fail-closed at 0.0** when probe not supplied | not in scope | not in scope | typically pass/fail, no rate |
| Context margin | `compute_context_margin` (chars heuristic) + `compute_context_margin_from_texts` (tokenizer-exact) | analytical estimate | partial | ad-hoc |
| Latency projection | yes — reuses consistency-probe wall time | no | no | ad-hoc |
| Noise floor | caller-supplied `fitness_samples`; **fail-closed** otherwise | no | no | no |
| Offline testability | default `pytest -q` is fully offline | deterministic by construction | yes | typically not |
| Emits `omegaprompt.preflight.PreflightReport` shape | yes | yes | source of truth | partial |
| What it does **not** prove | model quality, provider reliability under load, production adoption, external validation | same | same | same |
| Analytical trap classification | not in scope — use `mini-antemortem-cli` | yes | no | no |

Boundary in one line: this package's empirical probes measure a narrow preflight surface (judge / endpoint / context / latency / noise floor); they are not benchmarks of model quality or proofs of production readiness. See [docs/trust_model.md](docs/trust_model.md) and [docs/toolkit_positioning.md](docs/toolkit_positioning.md) for the full boundary, and [docs/claim_ledger.md](docs/claim_ledger.md) for the per-claim source-of-truth mapping.

> **Looking for the analytical (no-API, deterministic) preflight?** See sibling tool [`mini-antemortem-cli`](https://pypi.org/project/mini-antemortem-cli/) — same plugin interface, deterministic rule-based classifier instead of LLM probes.

> **MCP server.** This package also exposes six probes (`empirical_preflight`, `measure_judge_consistency`, `measure_gate_flip_rate`, `compute_context_margin`, `noise_floor_estimate`, `project_performance`) as agent-callable MCP tools — see [docs/generated/claims.md](docs/generated/claims.md) for the regenerated tool list. Install with `pip install "mini-omega-lock[mcp]"` then run `python -m mini_omega_lock.mcp` (stdio, default for Claude Code). See [AGENT_TRIGGERS.md scenario 2](https://github.com/hibou04-ops/omegaprompt/blob/main/AGENT_TRIGGERS.md#scenario-2--pre-calibration-sanity-check).

---

## TL;DR

`omegaprompt` ships a **plugin interface** for preflight probes (`omegaprompt.preflight.contracts` + `omegaprompt.preflight.adaptation`) but no probe implementation. This package fills that gap with five empirical measurements, then hands the result to omegaprompt's adaptation layer:

- **Judge consistency** — same (response, rubric) scored N times → `1 - CV`. Low = noisy judge, need `rescore_count > 1`.
- **Schema reliability** — STRICT_SCHEMA probe success rate. < 0.9 triggers `JSON_OBJECT` fallback automatically.
- **Context budget margin** — `1 - (longest_call_tokens / context_window)`. Negative = guaranteed overflow.
- **Performance projection** — probe latency × calibration scale → wall-time estimate before launching.
- **Noise floor** — fitness stdev under identical params → adaptive `min_kc4` threshold.

One call (`empirical_preflight()`) returns the three measurement records `omegaprompt`'s `derive_adaptation_plan()` consumes, plus a `warnings` list naming every field that fell back to a fail-closed default (e.g. `schema_reliability=0.0` when the strict-schema probe was not supplied).

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
judge_quality, endpoint, performance, warnings = empirical_preflight(
    judge=judge, rubric=rubric, probe_item=probe_item,
    probe_response="4", consistency_repeats=3,
)
for w in warnings:
    print(f"[mini-omega-lock] {w}")

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

The composite entry point is `empirical_preflight()`, which runs all five in one call and returns a 4-tuple — three measurement records omegaprompt's adaptation layer consumes plus a `warnings` list. Any unmeasured field is fail-closed (e.g. `schema_reliability=0.0` rather than `1.0`) and named in the warnings; CI gates should treat the warnings list as load-bearing, not cosmetic.

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

judge_quality, endpoint, performance, warnings = empirical_preflight(
    judge=judge,
    rubric=rubric,
    probe_item=probe_item,
    probe_response="4",
    consistency_repeats=3,
    dataset_size_hint=10,
    candidates_expected=20,
)

# Surface fail-closed warnings before trusting the measurements.
for w in warnings:
    print(f"[mini-omega-lock] {w}")

report = PreflightReport(
    judge_quality=judge_quality,
    endpoint=endpoint,
    performance=performance,
)
plan = derive_adaptation_plan(report=report)
# plan.min_kc4_override, plan.rescore_count, etc.
```

## Design principles

- **No fabricated success.** Unmeasured fields fail closed (`schema_reliability=0.0`, `noise_floor=0.0`, `scale_monotonic=False`) and emit explicit warnings — agents can tell "measured zero" from "we never ran the probe". The context-margin probe runs as a length-based projection by default (`compute_context_margin`, `chars_per_token=3.8`); pass real texts and a `token_counter` to upgrade to a tokenizer-exact measurement (`compute_context_margin_from_texts`).
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
