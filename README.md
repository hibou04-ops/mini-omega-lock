# mini-omega-lock

> **Your prompt-eval improvement might be smaller than your judge's own noise. mini-omega-lock measures that noise floor before you trust any A/B result.**

```bash
pip install mini-omega-lock
```

[![CI](https://github.com/hibou04-ops/mini-omega-lock/actions/workflows/ci.yml/badge.svg)](https://github.com/hibou04-ops/mini-omega-lock/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/mini-omega-lock.svg?cacheSeconds=3600)](https://pypi.org/project/mini-omega-lock/)
[![Python](https://img.shields.io/pypi/pyversions/mini-omega-lock.svg?cacheSeconds=3600)](https://pypi.org/project/mini-omega-lock/)
[![License](https://img.shields.io/pypi/l/mini-omega-lock.svg?cacheSeconds=3600)](LICENSE)
[![Parent](https://img.shields.io/badge/parent-omegaprompt%E2%89%A51.1.0-blueviolet.svg?cacheSeconds=3600)](https://pypi.org/project/omegaprompt/)

## What is the "noise floor"?

An LLM judge does not give the *same* response the *same* score every time. Ask it to grade one fixed `(response, rubric)` pair five times and you'll often get five slightly different scores. That spread is the **judge's noise floor**.

It matters because of one rule:

> **An optimization delta smaller than your judge's own noise is not real.**

If prompt B scores 0.4% better than prompt A, but your judge swings 1.2% when re-grading the *identical* answer, your "win" is inside the noise. You'd ship B, but you measured a coin flip. mini-omega-lock fires a few cheap probe calls and tells you that floor number *before* you trust the A/B delta.

```bash
# One number, no Python, CI-friendly exit codes:
preflight --provider anthropic --rubric rubric.json \
          --probe-item item.json --probe-response "4" --summary
# -> {"judge_noise_floor": 0.07, "schema_reliability": 0.0, ...}
```

It also measures three more pre-flight surfaces in the same pass: endpoint **schema reliability**, **context-budget margin**, and a **wall-time projection** for the full run.

## Quick start (Python)

```python
from omegaprompt import make_provider
from omegaprompt.domain.dataset import DatasetItem
from omegaprompt.domain.judge import Dimension, JudgeRubric
from omegaprompt.judges.llm_judge import LLMJudge
from mini_omega_lock import empirical_preflight, judge_noise_floor

judge  = LLMJudge(provider=make_provider("anthropic"))
rubric = JudgeRubric(dimensions=[Dimension(name="accuracy", description="is it correct", weight=1.0)])
probe  = DatasetItem(id="probe", input="2+2", reference="4")

judge_quality, endpoint, performance, warnings = empirical_preflight(
    judge=judge, rubric=rubric, probe_item=probe,
    probe_response="4", consistency_repeats=5,
)

print("judge noise floor:", judge_noise_floor(judge_quality))
for w in warnings:                 # fail-closed warnings are load-bearing
    print("[mini-omega-lock]", w)
```

That's ~5 cheap API calls (under $0.01 on frontier tiers). `judge_noise_floor` is `1 - consistency`: `0.0` = the judge never disagreed with itself; the bigger the number, the larger the A/B delta you need before a "win" is believable.

## Works with omegaprompt — and standalone

- **Standalone:** the noise-floor probe is useful on its own. Run `preflight` against any LLM-judge / prompt-calibration setup, get the floor + schema-reliability numbers, gate your CI on them. No omegaprompt pipeline required to read the value.
- **In the ecosystem:** `empirical_preflight` emits `omegaprompt.preflight.PreflightReport` records (`JudgeQualityMeasurement` / `EndpointMeasurement` / `PerformanceMeasurement`). Feed them to omegaprompt's `derive_adaptation_plan` and the calibration engine adapts its thresholds to what your infrastructure can actually deliver. mini-omega-lock is the empirical probe layer; omegaprompt is the engine it feeds.

It depends on `omegaprompt` (`>=1.1.0`) to build those records, so `pip install mini-omega-lock` pulls omegaprompt in.

## vs. "just trust the eval delta"

| | Trust the A/B delta | mini-omega-lock |
|---|---|---|
| Tells you the judge's self-disagreement | no | **yes** (`judge_noise_floor`) |
| Catches deltas smaller than judge noise | no — you ship coin flips | **yes** — flagged before you trust them |
| Flags silent strict-schema degradation | no | **yes** (`silent_degradation_detected`) |
| Estimates wall time before a long run | no | **yes** |
| Cost | free, but misleading | ~5 cheap API calls (< $0.01) |

## What it measures

| Surface | Function | What it tells you |
|---|---|---|
| **Judge noise floor** | `judge_noise_floor`, `measure_judge_consistency` | `1 - CV` over repeated scores of one fixed pair. Below this floor, A/B deltas are noise. |
| Hard-gate flip rate | `measure_gate_flip_rate` | How often a pass/fail gate flips on the *same* input — a flipping gate randomises the ship verdict even when the score looks stable. |
| Endpoint schema reliability | `probe_strict_schema` | STRICT_SCHEMA parse-success fraction. `< 0.9` → omegaprompt falls back to `JSON_OBJECT`. Also flags *silent* degradation (200-shaped but unparseable). |
| Context budget margin | `compute_context_margin` (chars) / `compute_context_margin_from_texts` (tokenizer-exact) | `1 - (longest_call_tokens / context_window)`. Negative = guaranteed overflow. |
| Performance projection | `project_performance` | Probe latency × calibration scale → wall-time estimate before launching. |

One call — `empirical_preflight()` — runs them in one pass and returns `(judge_quality, endpoint, performance, warnings)`. **Any unmeasured field fails closed** (e.g. `schema_reliability=0.0`, not `1.0`) and is named in `warnings`, so an agent can always tell "measured zero" from "we never ran that probe". Treat the warnings list as load-bearing in CI, not cosmetic.

## CLI: machine summary, scorecard, threshold gates

```bash
# Flat, CI-consumable JSON (headline number + schema_version, byte-stable):
preflight ... --summary

# Single-file scorecard (stdlib only) for a PR artifact:
preflight ... --scorecard html --scorecard-out preflight.html

# Fail the build when the judge is too noisy or the endpoint too unreliable:
preflight ... --fail-over-noise-floor 0.10 --fail-under-schema-reliability 0.90
```

Exit codes: `0` all measured & in-bound · `2` a field fell back to a fail-closed default (unmeasured) · `3` a measured value breached a `--fail-*` threshold (takes precedence over `2`) · `1` usage/runtime error. A measured-but-bad value alone (noisy judge, gate flip) is still `0` — it *was* measured.

## Read more

| Topic | English | 한국어 |
|---|---|---|
| Simpler intro | [EASY_README.md](EASY_README.md) | [EASY_README_KR.md](EASY_README_KR.md) |
| Full Korean | — | [README_KR.md](README_KR.md) |
| Generated source-of-truth claims | [docs/generated/claims.md](docs/generated/claims.md) | [docs/generated/claims_kr.md](docs/generated/claims_kr.md) |
| Trust model | [docs/trust_model.md](docs/trust_model.md) | [docs/trust_model_kr.md](docs/trust_model_kr.md) |
| Toolkit positioning | [docs/toolkit_positioning.md](docs/toolkit_positioning.md) | [docs/toolkit_positioning_kr.md](docs/toolkit_positioning_kr.md) |
| Claim ledger | [docs/claim_ledger.md](docs/claim_ledger.md) | [docs/claim_ledger_kr.md](docs/claim_ledger_kr.md) |
| Examples / deterministic demo | [docs/examples.md](docs/examples.md) | [docs/examples_kr.md](docs/examples_kr.md) |
| Release checklist | [docs/release_checklist.md](docs/release_checklist.md) | — |
| Post-release verification | [docs/post_release_verification.md](docs/post_release_verification.md) | — |

Sibling projects: [omegaprompt](https://github.com/hibou04-ops/omegaprompt) (calibration engine) · [omega-lock](https://github.com/hibou04-ops/omega-lock) (broader audit framework) · [mini-antemortem-cli](https://github.com/hibou04-ops/mini-antemortem-cli) (analytical, no-API preflight) · [antemortem-cli](https://github.com/hibou04-ops/antemortem-cli) (pre-implementation recon).

## What's new in 0.7.0

- **Judge noise-floor metrics, front and centre.** New `judge_noise_floor()` helper + a `build_summary()` that produces a flat, `schema_version`-tagged, byte-stable CI dict, and a stdlib-only `render_scorecard()` (Markdown / self-contained HTML).
- **CLI `--summary`** (machine summary), **`--scorecard md|html`** (+ `--scorecard-out`), and **`--fail-over-noise-floor` / `--fail-under-schema-reliability` / `--fail-under-context-margin`** threshold gates (new exit code `3`).
- **Version-agnostic publish workflow** + dynamic PyPI shields that track releases automatically.
- Frozen surface unchanged: `empirical_preflight`, the three contract records, console scripts, and the `omegaprompt>=1.1.0` pin are all the same — additive only.

See [CHANGELOG.md](CHANGELOG.md) for the full history.

## Trust loop (no network)

These run entirely offline (no API keys) and are exactly what `scripts/release_audit.py` enforces, so local CI and the release gate stay in lockstep:

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

`python examples/demo_replay.py` replays `empirical_preflight` against a scripted fake judge; its output is byte-for-byte equal to `examples/_demo_output.txt` (verified by `tests/test_demo_replay.py`) — the "did I break the warning surface?" smoke test.

## MCP server

This package also exposes ten agent-callable MCP tools (`empirical_preflight`, `measure_judge_consistency`, `measure_gate_flip_rate`, `measure_scale_monotonicity`, `probe_strict_schema`, `compute_context_margin`, `compute_context_margin_from_texts`, `noise_floor_estimate`, `project_performance`, `derive_adaptation_plan`) — regenerated list in [docs/generated/claims.md](docs/generated/claims.md).

```bash
pip install "mini-omega-lock[mcp]"
python -m mini_omega_lock.mcp           # stdio (Claude Code default)
python -m mini_omega_lock.mcp --http    # streamable-http
```

> **Want the analytical (no-API, deterministic) preflight instead?** See sibling tool [`mini-antemortem-cli`](https://pypi.org/project/mini-antemortem-cli/) — same plugin interface, a deterministic rule-based classifier instead of LLM probes.

## What this does *not* prove

Not a benchmark of model quality, judge quality, or provider reliability under load. Not a production-readiness proof. It measures a narrow pre-flight surface (judge noise / endpoint / context / latency) so you stop trusting eval deltas that are smaller than your judge's own noise. See [docs/trust_model.md](docs/trust_model.md) and [docs/claim_ledger.md](docs/claim_ledger.md) for the per-claim boundary.

## License

Apache 2.0. See [LICENSE](LICENSE).

**License history.** PyPI distributions of 0.1.0 shipped with an MIT `LICENSE`. The repository was relicensed to Apache 2.0 on 2026-04-22 (commit `ff489a9`); 0.2.0 and all later versions ship under Apache 2.0. Anyone who installed 0.1.0 holds an MIT license to that copy — license changes do not apply retroactively.
