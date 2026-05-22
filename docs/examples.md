# Examples and deterministic replay

`mini-omega-lock` ships two pieces of verification machinery on top of the unit tests:

1. **Deterministic demo replay** — one Python file with one expected output file. Diff = fail.
2. **Offline golden cases** — small JSON fixtures that cover the documented probe matrix end-to-end, replayed by a runner that diffs structured output (with timing fields masked) against a baseline.

Neither requires API keys. Both are part of the release-audit gate.

## Deterministic demo (`examples/demo_replay.py`)

```bash
python examples/demo_replay.py
```

The demo:

- Builds a scripted fake judge and a minimal `JudgeRubric` / `DatasetItem`.
- Calls `empirical_preflight` with a representative set of inputs (a happy-path consistency probe, the schema probe stubbed, the noise floor stubbed missing).
- Prints a stable text rendering of:
  - the four return values (`judge_quality`, `endpoint`, `performance`, `warnings`),
  - the `omegaprompt.preflight.PreflightReport` round-trip,
  - the resulting `AdaptationPlan` summary.

`examples/_demo_output.txt` is the committed expected output. `tests/test_demo_replay.py` runs `demo_replay.py` and diffs against this file. Any drift in warning text, default value, or contract shape is caught immediately.

### Why timing fields are masked

`empirical_preflight` reuses the consistency-probe wall time as its latency sample. Because `time.perf_counter()` is non-deterministic, the demo replaces `mean_call_latency_ms` and `projected_wall_time_seconds` with the literal string `<masked: timing>` before printing. Monkeypatching `perf_counter` would be fragile across Python versions and worse — it would let real timing regressions slip through. Masking the displayed value is the explicit choice.

### When to update the expected output

Update `examples/_demo_output.txt` when *and only when*:

- A documented contract changed (e.g., a new field on `PreflightReport`).
- A warning text changed intentionally (commit message must explain).
- The fake-judge script changed.

Regenerating it because "the diff doesn't matter" is a release blocker — the test exists to catch that exact pattern. If the diff looks irrelevant, it isn't: every byte of `_demo_output.txt` is part of the warning-surface contract.

## Offline golden cases (`benchmarks/golden_cases/*.json`)

```bash
python scripts/run_golden_cases.py --check
```

Each case is a single JSON file. Layout:

```jsonc
{
  "name": "missing_strict_schema",
  "description": "When strict_schema inputs are absent, schema_reliability defaults to 0.0 with a warning.",
  "inputs": {
    "scripted_scores": [4, 4, 4],
    "consistency_repeats": 3,
    "include_schema_probe": false,
    "fitness_samples": null,
    "monotonic_examples": false,
    "token_counter": null
  },
  "expected": {
    "judge_quality": { "consistency": 1.0, "anchoring_usage": 0.0, "scale_monotonic": false, "samples": 3 },
    "endpoint":      { "schema_reliability": 0.0, "context_budget_margin_sign": "positive", "caching_active": false, "silent_degradation_detected": false },
    "performance":   { "noise_floor": 0.0 },
    "warnings_contains_all_of": ["schema_reliability not measured", "noise_floor not measured", "chars_per_token"]
  }
}
```

The runner builds the matching inputs, calls `empirical_preflight`, compares deterministic fields with the case's `expected`, and asserts every substring in `warnings_contains_all_of` is present in the returned warnings list. Timing-dependent fields (`mean_call_latency_ms`, `projected_wall_time_seconds`) are *not* compared. The sign-only comparison for `context_budget_margin_sign` (`"positive"` / `"negative"` / `"zero"`) lets cases assert the qualitative shape without pinning the chars-per-token heuristic.

### Cases shipped

| File | Probe matrix slice it covers |
|---|---|
| `all_probes_supplied.json` | Happy path: every input supplied, no warnings besides the heuristic note. |
| `missing_strict_schema.json` | `schema_reliability` fail-closes to 0.0 with warning. |
| `monotonicity_not_supplied.json` | `scale_monotonic` defaults to False with warning. |
| `token_counter_exact.json` | Tokenizer-exact context margin path is taken (no chars-per-token warning). |
| `token_counter_heuristic.json` | Chars heuristic path is taken (warning present). |
| `strict_schema_failure.json` | Provider raises; success rate computed only over actual successes. |
| `noise_floor_supplied.json` | `noise_floor` populated from `fitness_samples`. |
| `noise_floor_missing.json` | `noise_floor` defaults to 0.0 with warning. |

## Fixture integrity

`benchmarks/golden_cases/manifest.json` records a SHA-256 of each case file's canonical JSON form (`json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n"`, UTF-8).

```bash
python scripts/verify_fixture_integrity.py
```

The script recomputes every digest and fails on mismatch. To intentionally update a case:

1. Edit the case.
2. Re-run `python scripts/run_golden_cases.py --update-manifest` (which delegates the rehash).
3. Commit both the case file and the updated manifest in the same commit; the diff in `manifest.json` is the audit trail for the fixture change.

### What this is and is not

- It **is** fixture integrity — a tampered fixture can't pass `verify_fixture_integrity.py` without an explicit manifest update.
- It is **not** an append-only audit trail. There is no hash chain across commits; we don't claim there is one. Git history is the only chronological record.

## Running everything together

```bash
python -m pytest -q
python examples/demo_replay.py
python scripts/run_golden_cases.py --check
python scripts/verify_fixture_integrity.py
```

The trust-loop block in `README.md` lists these alongside the README-consistency commands. `scripts/release_audit.py --no-network` runs the same sequence and fails on the first non-zero exit.
