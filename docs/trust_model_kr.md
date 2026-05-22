# Trust model (한국어)

본 문서는 `mini-omega-lock`이 **무엇을 보증하고 무엇을 보증하지 않는지** 명시합니다. 호출자는 CI gate 크기를 결정할 때, 리뷰어는 회의의 깊이를 결정할 때 이 문서를 기준선으로 씁니다. `README.md` 상단 "boundary claim"의 정식 근거 문서.

## 검증하는 것

- **Judge consistency** — `measure_judge_consistency`가 동일 `(rubric, item, response)`에 대해 judge를 `N`회 호출하고 `1 - CV(weighted_score)`를 `[0, 1]`로 clamp해 반환. 성공한 호출만 반영하며, 실패 호출은 `warnings`로 surface되고 latency 집계에서 제외됨.
- **Hard-gate flip rate** — `measure_gate_flip_rate`가 judge-mode hard gate 별로 인접 호출 쌍에서 boolean이 뒤집힌 비율, majority, pass count를 보고. Judge-mode hard gate가 없으면 빈 dict.
- **Scale monotonicity** — `measure_scale_monotonicity`는 `ordered_examples` 시퀀스의 점수가 비감소(non-decreasing)인지 검증. 호출자가 ordering을 제공해야 함; 단일 item consistency probe로 추론 불가하므로 ordering 미제공 시 `empirical_preflight`는 `scale_monotonic=False` 기본값 + warning.
- **Endpoint strict-schema reliability** — `probe_strict_schema`가 명시적 `ProviderRequest` probe들의 parse 성공률을 카운트. Probe 없으면 1.0 fabricate 거부하고 raise; `empirical_preflight`는 missing-probe 케이스를 `schema_reliability=0.0` + explicit warning으로 변환.
- **Context-budget margin (chars heuristic)** — `compute_context_margin`가 `chars_per_token=3.8` (기본값)으로 `1 − tokens/window`를 projection. 길이 기반 projection, **tokenizer-exact 측정값 아님**.
- **Context-budget margin (tokenizer-exact)** — `compute_context_margin_from_texts`는 실제 `token_counter`와 실제 텍스트를 요구. Tokenizer-exact margin을 얻는 유일한 경로.
- **Performance projection** — `project_performance`가 `mean(probe_latencies) × dataset × candidates × calls_per_candidate_per_item`을 wall time으로 extrapolate. `empirical_preflight`는 consistency probe latency를 재사용 (별도 probe call 추가 없음).
- **Noise floor** — `noise_floor_estimate`는 `fitness_samples`의 population standard deviation. 샘플 ≥ 2 필요; 부족하면 `empirical_preflight`가 0.0 + warning.

## 검증하지 **않는** 것

- **모델 품질** — 어떤 probe도 모델 답변의 정답성을 절대 척도로 측정하지 않습니다. Judge consistency 높음 = judge가 안정적이라는 의미일 뿐, 정답이라는 의미가 아닙니다.
- **부하 상태 provider 신뢰도** — Probe는 작음 (≈4–10 calls). 지속 QPS, retry storm, context-window edge case 실패 모드를 simulate하지 않습니다.
- **프로덕션 도입 사례** — 어떤 deployment / 조직 / 스케일 사용 주장도 본 패키지에 의해 뒷받침되지 않습니다. README/EASY_READMEs는 의도적으로 그런 claim을 배제합니다.
- **외부 검증** — 어떤 제3자 benchmark / audit도 참조되거나 암시되지 않습니다.
- **비용** — 문서의 probe budget(`~4 API calls`)은 예시 default. 실제 비용은 tier, region, retry, caller config에 따라 다름.
- **Provider-specific schema 정합성** — `probe_strict_schema`는 provider의 strict-schema mode가 parse되는지 측정. 반환 객체의 *semantics*는 검증하지 않음.

## Boundary 의미

### Live-provider boundary

- Production에서 `empirical_preflight`는 `omegaprompt.providers.LLMProvider`를 통해 실제 provider 호출. 비용과 latency는 호출자 부담.
- 기본 테스트(`pytest -q`)와 기본 CI는 mock/scripted provider 사용 — API key 불필요.
- MCP tools는 `provider` arg를 받아 `omegaprompt.providers.make_provider`를 거침. 실제 provider는 실제 네트워크 호출 발생; agent는 MCP tool surface를 live로 간주해야 함 (fake provider를 wire하지 않은 한).

### Offline-test boundary

- Unit test는 deterministic scripted provider로 mock (`tests/test_probes.py::_ScriptedJudgeProvider` 참조).
- 결정론적 demo(`examples/demo_replay.py`)와 golden case(`benchmarks/golden_cases/`)는 네트워크 없이 실행. Scripted fake 사용, timing 필드는 마스킹된 byte-for-byte 출력 검증.
- CI workflow는 `dev`와 `mcp` extra만 설치, provider 인증 없음, `make_provider("anthropic")` 같은 live probe 호출 없음.

### Warning 의미

- `empirical_preflight`는 4-tuple `(judge_quality, endpoint, performance, warnings)` 반환. 이전 버전은 3-tuple; warnings 리스트가 load-bearing 추가물.
- 측정되지 않은 필드마다 fail-closed default로 떨어졌음을 명시하는 warning이 append됨. 호출자는 숫자 값을 "좋음"으로 다루기 전에 반드시 warning을 surface하거나 집계해야 함.
- 테스트(`tests/test_fail_closed_defaults.py`)가 기본값과 warning 텍스트를 모두 pin.

### Fail-closed 의미

| 필드 | 미측정 시 default | Warning |
|---|---|---|
| `JudgeQualityMeasurement.consistency` | `0.0` (probe 실패) | "consistency probe failed: …" |
| `JudgeQualityMeasurement.scale_monotonic` | `False` | "scale_monotonic not measured — pass monotonic_examples=…" |
| `EndpointMeasurement.schema_reliability` | `0.0` | "schema_reliability not measured — strict_schema_provider, output, probes were not supplied" |
| `EndpointMeasurement.context_budget_margin` (chars heuristic) | 계산은 되지만 flag | "context_budget_margin uses the chars_per_token=3.8 heuristic" |
| `PerformanceMeasurement.mean_call_latency_ms` | consistency probe 실패 시 `0.0` | "mean_call_latency_ms not measured — consistency probe failed" |
| `PerformanceMeasurement.noise_floor` | `0.0` | "noise_floor not measured — pass fitness_samples=[…]" |

Fail-closed 계약: *측정되지 않음 ≠ 좋음*. 이 측정값 위에 세워진 CI gate는 미측정 측정을 성공으로 다루면 안 됩니다.

### Schema reliability 주의사항

`probe_strict_schema`는 빈 probe 리스트에 대해 `1.0` 반환 대신 raise합니다. 의도적 — 미측정에 대해 완벽 점수를 silent하게 반환하던 0.4.0 이전 fail-open default를 제거하기 위함. 옛 fail-open 동작이 필요하면 호출자가 직접 wire해야 하며 silence 비용을 감수해야 함.

### Context-margin: heuristic vs tokenizer-exact

`compute_context_margin`은 전달된 `token_counter`를 무시합니다. 이 argument는 backward compatibility를 위해 받지만 source(`probes.py` 309–318 라인)에 명시되어 있음. Tokenizer-exact margin이 필요하면 `compute_context_margin_from_texts`를 실제 텍스트와 실제 tokenizer로 직접 호출하세요. MCP wrapper의 `compute_context_margin` 도구는 `token_counter` parameter를 노출하지 않습니다 — MCP 호출자는 heuristic-only.

### Gate-flip 한계

`measure_gate_flip_rate`는 `evaluator == "judge"`인 hard gate만 검사. Rule-evaluator gate는 본질상 안정이므로 skip. 인접 호출 쌍 사이의 *transition*을 측정 — `N`회 호출 → `N − 1` transition. `repeats < 2`는 내부적으로 2로 clamp.

### Noise-floor 한계

Noise floor는 호출자가 제공한 `fitness_samples`로부터 계산됩니다. `empirical_preflight` probe 자체는 fitness 수집을 위해 다수 calibration을 실행하지 않음 — 의도적 (단일 probe pass로는 calibration 간 variance 측정 불가). 호출자가 calibration을 직접 실행해 run당 aggregate fitness를 모아서 `empirical_preflight(fitness_samples=…)`에 전달하거나 `noise_floor_estimate`를 직접 호출 후 plan에 patch.

## 본 문서에 이의 제기

위 claim 중 source code나 테스트가 뒷받침하지 않는 항목을 발견하면 release-blocker 버그로 간주합니다. `.github/ISSUE_TEMPLATE/claim_drift.md`를 사용해 위반 라인과 source-of-truth 위치를 명시하여 보고하세요.
