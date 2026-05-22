# 예제 및 결정론적 replay (한국어)

`mini-omega-lock`은 unit test 위에 두 종류의 검증 기계장치를 ship합니다:

1. **결정론적 demo replay** — Python 파일 1개 + 예상 출력 파일 1개. Diff = fail.
2. **오프라인 golden case** — 문서화된 probe matrix를 end-to-end 커버하는 작은 JSON fixture, runner가 timing 필드 마스킹한 structured 출력을 baseline과 diff.

둘 다 API key 불필요. 둘 다 release-audit gate의 일부.

## 결정론적 demo (`examples/demo_replay.py`)

```bash
python examples/demo_replay.py
```

Demo는:

- Scripted fake judge와 minimal `JudgeRubric` / `DatasetItem`을 만들고
- 대표 입력 set으로 `empirical_preflight` 호출 (happy-path consistency probe, schema probe stub, noise floor 누락)
- 안정된 텍스트 형식으로 출력:
  - 4개 반환값 (`judge_quality`, `endpoint`, `performance`, `warnings`),
  - `omegaprompt.preflight.PreflightReport` round-trip,
  - 결과 `AdaptationPlan` 요약.

`examples/_demo_output.txt`가 커밋된 예상 출력. `tests/test_demo_replay.py`는 `demo_replay.py`를 실행하고 이 파일과 diff. Warning 텍스트, default 값, contract shape의 drift는 즉시 잡힘.

### Timing 필드를 마스킹하는 이유

`empirical_preflight`는 consistency probe wall time을 latency sample로 재사용. `time.perf_counter()`가 non-deterministic이므로 demo는 `mean_call_latency_ms`와 `projected_wall_time_seconds`를 print 전에 리터럴 문자열 `<masked: timing>`으로 치환. `perf_counter`를 monkeypatch하는 건 Python 버전 간 fragile하고, 더 나쁜 건 실제 timing regression이 slip-through될 수 있음. 표시 값을 마스킹하는 게 explicit choice.

### 예상 출력 갱신 시점

`examples/_demo_output.txt`는 *오직* 다음 경우에만 갱신:

- 문서화된 contract 변경 (e.g. `PreflightReport`에 새 필드).
- Warning 텍스트의 의도적 변경 (commit message가 이유 설명).
- Fake-judge script 변경.

"diff가 무의미해 보임"을 이유로 regenerate하는 건 release blocker — 테스트가 바로 그 패턴을 잡으려고 존재. Diff가 irrelevant해 보여도 그렇지 않음: `_demo_output.txt`의 모든 바이트가 warning surface contract의 일부.

## 오프라인 golden case (`benchmarks/golden_cases/*.json`)

```bash
python scripts/run_golden_cases.py --check
```

각 case는 단일 JSON 파일. 레이아웃:

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

Runner는 입력을 빌드, `empirical_preflight` 호출, deterministic 필드를 case의 `expected`와 비교, `warnings_contains_all_of`의 모든 substring이 반환된 warnings 리스트에 존재하는지 assert. Timing-dependent 필드(`mean_call_latency_ms`, `projected_wall_time_seconds`)는 비교하지 *않음*. `context_budget_margin_sign`(`"positive"`/`"negative"`/`"zero"`)의 sign-only 비교는 chars-per-token heuristic을 못 박지 않으면서 qualitative shape를 assert 가능하게 함.

### Ship되는 case들

| 파일 | 커버하는 probe matrix slice |
|---|---|
| `all_probes_supplied.json` | Happy path: 모든 입력 제공, heuristic note 외 warning 없음. |
| `missing_strict_schema.json` | `schema_reliability` 0.0으로 fail-close + warning. |
| `monotonicity_not_supplied.json` | `scale_monotonic` False default + warning. |
| `token_counter_exact.json` | Tokenizer-exact context margin 경로 사용 (chars-per-token warning 없음). |
| `token_counter_heuristic.json` | Chars heuristic 경로 사용 (warning 있음). |
| `strict_schema_failure.json` | Provider raise; 성공률은 실제 성공만으로 계산. |
| `noise_floor_supplied.json` | `noise_floor`가 `fitness_samples`로부터 채워짐. |
| `noise_floor_missing.json` | `noise_floor` 0.0 default + warning. |

## Fixture 무결성

`benchmarks/golden_cases/manifest.json`은 각 case 파일의 canonical JSON 형태(`json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n"`, UTF-8)의 SHA-256을 기록.

```bash
python scripts/verify_fixture_integrity.py
```

스크립트가 모든 digest를 재계산하고 mismatch에 fail. 의도적으로 case를 갱신하려면:

1. Case를 편집.
2. `python scripts/run_golden_cases.py --update-manifest` (rehash 위임) 재실행.
3. Case 파일과 갱신된 manifest를 같은 commit에 commit; `manifest.json`의 diff가 해당 fixture 변경의 audit trail.

### 이것이 무엇이고, 무엇이 아닌가

- **Fixture 무결성**임 — 변조된 fixture는 명시적 manifest 업데이트 없이 `verify_fixture_integrity.py` 통과 불가.
- **Append-only audit trail이 아님.** Commit 간 hash chain 없음; 그런 주장도 안 함. Git 히스토리가 유일한 chronological 기록.

## 한꺼번에 실행

```bash
python -m pytest -q
python examples/demo_replay.py
python scripts/run_golden_cases.py --check
python scripts/verify_fixture_integrity.py
```

`README.md`의 trust-loop 블록이 README-consistency 명령과 함께 이들을 나열. `scripts/release_audit.py --no-network`는 동일 시퀀스를 실행하고 첫 non-zero exit에서 fail.
