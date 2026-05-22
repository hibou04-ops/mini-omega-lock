# Trust model

This document spells out what `mini-omega-lock` will and will not vouch for, so callers can size their CI gates and reviewers can size their scepticism. It is the canonical reference behind the boundary claims in the top of `README.md`.

## What the package verifies

- **Judge consistency** — `measure_judge_consistency` calls a judge `N` times on the same `(rubric, item, response)` and reports `1 - CV(weighted_score)` clamped to `[0, 1]`. The number reflects only the runs that succeeded; failed calls are surfaced via `warnings` and excluded from latency aggregates.
- **Hard-gate flip rate** — `measure_gate_flip_rate` reports the fraction of consecutive call-pairs where each judge-mode hard gate's boolean outcome flipped, plus majority and pass counts. Empty dict when the rubric declares no judge-mode hard gates.
- **Scale monotonicity** — `measure_scale_monotonicity` checks whether the judge ranks an `ordered_examples` sequence non-decreasingly. The caller must supply the ordering; single-item consistency probes cannot infer it, so `empirical_preflight` defaults `scale_monotonic=False` and emits a warning when no ordering is given.
- **Endpoint strict-schema reliability** — `probe_strict_schema` counts successful parses across explicit `ProviderRequest` probes. Without probes the function refuses to fabricate a number and raises; `empirical_preflight` translates the missing-probe case into `schema_reliability=0.0` with an explicit warning.
- **Context-budget margin (chars heuristic)** — `compute_context_margin` projects `1 − tokens/window` using `chars_per_token=3.8` by default. This is a length-based projection, not a tokenizer-exact measurement.
- **Context-budget margin (tokenizer-exact)** — `compute_context_margin_from_texts` requires a real `token_counter` and the actual texts; it is the only path that produces a tokenizer-exact margin.
- **Performance projection** — `project_performance` extrapolates `mean(probe_latencies) × dataset × candidates × calls_per_candidate_per_item` into a projected wall time. `empirical_preflight` reuses the consistency-probe latency rather than issuing a fresh probe call.
- **Noise floor** — `noise_floor_estimate` is the population standard deviation of `fitness_samples`. Needs ≥ 2 samples; otherwise returns 0.0 with a warning from `empirical_preflight`.

## What the package does **not** verify

- **Model quality.** No probe scores how good the model's answers are in absolute terms. A high judge-consistency score means the judge is stable, not that it's right.
- **Provider reliability under load.** Probes are small (≈4–10 calls). They do not simulate sustained QPS, retry storms, or context-window-edge-case failure modes.
- **Production adoption.** No claim about deployments, organisations, or usage at scale is supported here. The README and EASY_READMEs deliberately omit such claims.
- **External validation.** No third-party benchmark or audit is referenced or implied.
- **Cost.** Probe budgets in the docs (`~4 API calls`) are illustrative defaults; actual cost depends on tier, region, retries, and caller configuration.
- **Provider-specific schema correctness.** `probe_strict_schema` measures whether the provider's strict-schema mode parses; it does not validate the *semantics* of the returned object.

## Boundary semantics

### Live-provider boundary

- Production use of `empirical_preflight` issues real provider calls through `omegaprompt.providers.LLMProvider`. Costs and latency are caller-borne.
- Default tests (`pytest -q`) and default CI use mocked / scripted providers — no API key required.
- The MCP tools accept a `provider` arg and route through `omegaprompt.providers.make_provider`. Real providers run real network calls; agents should treat the MCP tool surface as live unless they wire a fake provider.

### Offline-test boundary

- The unit test suite mocks providers with deterministic scripts (see `tests/test_probes.py::_ScriptedJudgeProvider`).
- The deterministic demo (`examples/demo_replay.py`) and the golden cases (`benchmarks/golden_cases/`) run without any network access. They use scripted fakes and verify byte-for-byte output (with timing fields masked).
- The CI workflow installs only `dev` and `mcp` extras, never authenticates to a provider, and never invokes a probe with a live `make_provider("anthropic")` etc.

### Warning semantics

- `empirical_preflight` returns a 4-tuple `(judge_quality, endpoint, performance, warnings)`. Earlier versions returned a 3-tuple; the warnings list is the load-bearing addition.
- Each unmeasured field appends a warning naming the field that fell back to a fail-closed default. Callers MUST surface or aggregate these warnings before treating the numeric values as "good".
- Tests (`tests/test_fail_closed_defaults.py`) pin both the default values and the warning text.

### Fail-closed semantics

| Field | Default when not measured | Warning |
|---|---|---|
| `JudgeQualityMeasurement.consistency` | `0.0` (probe failed) | "consistency probe failed: …" |
| `JudgeQualityMeasurement.scale_monotonic` | `False` | "scale_monotonic not measured — pass monotonic_examples=…" |
| `EndpointMeasurement.schema_reliability` | `0.0` | "schema_reliability not measured — strict_schema_provider, output, probes were not supplied" |
| `EndpointMeasurement.context_budget_margin` (chars heuristic) | computed but flagged | "context_budget_margin uses the chars_per_token=3.8 heuristic" |
| `PerformanceMeasurement.mean_call_latency_ms` | `0.0` if consistency probe failed | "mean_call_latency_ms not measured — consistency probe failed" |
| `PerformanceMeasurement.noise_floor` | `0.0` | "noise_floor not measured — pass fitness_samples=[…]" |

The fail-closed contract is: *unmeasured ≠ good*. A CI gate built on these measurements must not treat a missing measurement as a successful one.

### Schema reliability caveat

`probe_strict_schema` raises rather than returning `1.0` on an empty probe list. This is intentional — a library helper that silently returned a perfect score for "no measurement" would re-introduce the fail-open default that the 0.4.0 redesign removed. Callers that want the historical fail-open behaviour must wire it themselves and bear the silence cost.

### Context-margin heuristic vs tokenizer-exact

`compute_context_margin` ignores any `token_counter` passed to it. The argument is accepted for backward compatibility and is documented in the source (see `probes.py` lines 309–318). To get a tokenizer-exact margin, call `compute_context_margin_from_texts` directly with real texts and a real tokenizer. The MCP wrapper `compute_context_margin` tool does not expose a `token_counter` parameter at all — MCP callers are heuristic-only.

### Gate-flip limitation

`measure_gate_flip_rate` only inspects hard gates whose `evaluator == "judge"`. Rule-evaluator gates are stable by construction and skipped. The metric measures *transitions* between consecutive calls; for `N` calls there are `N − 1` transitions. A run with `repeats < 2` is clamped to 2 internally.

### Noise-floor limitation

The noise floor is computed from caller-supplied `fitness_samples`. The `empirical_preflight` probe itself does not run multiple complete calibrations to gather fitness — that is by design (a single probe pass cannot measure variance across full calibrations). Callers run the calibrations themselves, collect aggregate fitness per run, and either pass the samples to `empirical_preflight(fitness_samples=…)` or call `noise_floor_estimate` directly and patch the resulting plan.

## How to challenge this document

If you find a claim above that the source code or tests do not back up, that is a release-blocker bug. File it via `.github/ISSUE_TEMPLATE/claim_drift.md` with the offending line and the source-of-truth location that contradicts it.
