# mini-omega-lock (한국어)

> **judge 반복 관측의 변동과 미측정 항목을 확인합니다. A/B 유의성 판정에는 별도의 비교 설계가 필요합니다.**

```bash
pip install mini-omega-lock
```

[![CI](https://github.com/hibou04-ops/mini-omega-lock/actions/workflows/ci.yml/badge.svg)](https://github.com/hibou04-ops/mini-omega-lock/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/mini-omega-lock.svg?cacheSeconds=3600)](https://pypi.org/project/mini-omega-lock/)
[![Python](https://img.shields.io/pypi/pyversions/mini-omega-lock.svg?cacheSeconds=3600)](https://pypi.org/project/mini-omega-lock/)
[![License](https://img.shields.io/pypi/l/mini-omega-lock.svg?cacheSeconds=3600)](LICENSE)
[![Parent](https://img.shields.io/badge/parent-omegaprompt%E2%89%A51.1.0-blueviolet.svg?cacheSeconds=3600)](https://pypi.org/project/omegaprompt/)

> 본 페이지는 [README.md](README.md)(영문)의 한국어 미러본입니다. 식별자 / 명령 / 함수명은 번역하지 않습니다. 짧은 도입은 [EASY_README_KR.md](EASY_README_KR.md).

## 시작 · 단독 사용 · 도킹

**Omega Aile** — Quiet precision. AI research guided by evidence.

보정 전에 judge 일관성·스키마 동작·컨텍스트 여유·실행량을 점검합니다. 단독 probe 사용도 omegaprompt 패키지를 설치합니다.

Python 3.11 이상에서 실행합니다. 설치에는 인터넷이 필요합니다.

```bash
python -m pip install mini-omega-lock==0.8.1
preflight --help
python -c "from mini_omega_lock import compute_context_margin; print(compute_context_margin(system_prompt_chars=0, rubric_chars=0, longest_input_chars=380, longest_reference_chars=0, longest_response_chars=0, context_window_tokens=1000))"
```

API 예제 결과 0.9는 문자 수 기반 컨텍스트 추정치입니다. 실제 tokenizer 측정이나 모델 성능 결과가 아닙니다. CLI probe에는 provider 환경이 필요합니다. 미측정 경고는 종료 2, 임계값 위반은 3, 오류는 1입니다. 종료 0만으로 측정값의 적합성을 판단하면 안 됩니다.

[실제 연결 방식과 입력·출력](https://github.com/hibou04-ops/omega-lock/blob/main/DOCKING.md) · [전체 안내](README.md). 두 mini 도구의 현재 검증 조합은 omegaprompt 2.1.2이며, 별도 배포 패키지입니다.

MCP는 해당 배포명의 `[mcp]` extras와 기존 서버 명령을 사용합니다. 기존 FastMCP 계약은 SDK `>=1.0.0,<2.0.0` 범위로 유지합니다.


## "noise floor"가 뭔가요?

LLM judge는 *같은* 응답에 *같은* 점수를 매번 주지 않습니다. 고정된 `(response, rubric)` 하나를 다섯 번 채점시키면 미묘하게 다른 다섯 개의 점수가 나오곤 합니다. 그 산포가 바로 **judge의 noise floor**입니다.

이게 중요한 이유는 규칙 하나 때문입니다:

> **단일 항목의 반복 변동만으로 A/B 개선의 유의성을 판정할 수 없습니다.**

반복 점수의 CV는 상대 변동이고 aggregate fitness의 표준편차는 절대 단위입니다. A/B 판단에는 표본의 대응 관계, 불확실성, 사전 판정 기준이 별도로 필요합니다.

```bash
# 한 숫자, Python 불필요, CI 친화적 exit code:
preflight --provider anthropic --rubric rubric.json \
          --probe-item item.json --probe-response "4" --summary
# -> {"judge_noise_floor": 0.07, "schema_reliability": 0.0, ...}
```

같은 패스에서 세 가지 pre-flight 표면도 함께 측정합니다: endpoint **schema reliability**, **context-budget margin**, 그리고 전체 실행의 **wall-time 예측**.

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
print("measurement_status:", warnings.measurement_status)
for w in warnings:                 # 사람이 읽는 진단도 보존
    print("[mini-omega-lock]", w)
```

`judge_noise_floor`는 clipped 상대 CV (`1 - consistency`)이며 한 사례의 반복 점수 변동입니다. 절대 A/B delta의 유의성 기준이 아닙니다. 기본 judge/gate 배치는 실제 관측 5개를 사용하며 추가 probe를 설정하면 호출이 늘어납니다. 비용은 provider와 사용량에 따라 달라집니다.

## omegaprompt와 함께 — 그리고 단독으로

- **단독:** noise-floor probe는 그 자체로 유용합니다. 어떤 LLM-judge / prompt-calibration 셋업에든 `preflight`를 돌려 floor + schema-reliability 수치를 얻고, CI를 거기에 gate하세요. 값을 읽는 데 omegaprompt 파이프라인이 필요 없습니다.
- **생태계 안에서:** `empirical_preflight`는 `omegaprompt.preflight.PreflightReport` 레코드(`JudgeQualityMeasurement` / `EndpointMeasurement` / `PerformanceMeasurement`)를 emit합니다. `PreflightReport`로 조립하고 `derive_adaptation_plan`에 넘기면 실행 정책과 권고를 받습니다. schema fallback을 포함한 일부 필드는 advisory이므로 artifact의 정책 소비 기록을 확인해야 실제 적용 여부를 알 수 있습니다. mini-omega-lock은 empirical probe 레이어, omegaprompt는 그것이 먹이는 엔진입니다.

레코드 생성을 위해 `omegaprompt`(`>=1.1.0`)에 의존하므로 `pip install mini-omega-lock`이 omegaprompt를 함께 끌어옵니다.

## "그냥 eval delta를 믿기" vs. mini-omega-lock

| | A/B delta를 믿음 | mini-omega-lock |
|---|---|---|
| judge 자기 불일치를 알려줌 | no | **yes** (`judge_noise_floor`) |
| 반복 변동과 측정 범위를 구분 | 직접 확인 | 구조적 상태와 관측 기록 제공 |
| silent strict-schema 저하를 표시 | no | **yes** (`silent_degradation_detected`) |
| 긴 실행 전 wall time 추정 | no | **yes** |
| 비용 | 무료지만 오도함 | probe ~5회 (provider-dependent) |

## 측정하는 것

| 표면 | 함수 | 뭘 알려주나 |
|---|---|---|
| **Judge noise floor** | `judge_noise_floor`, `measure_judge_consistency` | 고정된 쌍을 반복 채점한 점수의 clipped CV (`1 - consistency`). 상대 변동 설명이며 A/B 유의성 판정이 아님. |
| Hard-gate flip rate | `measure_gate_flip_rate` | *같은* 입력에서 pass/fail gate가 얼마나 자주 뒤집히나 — 점수가 안정적이어도 flip하는 gate는 ship 판정을 무작위로 만듦. |
| Endpoint schema reliability | `probe_strict_schema` | STRICT_SCHEMA parse 성공 비율과 silent parse 저하. `JSON_OBJECT` fallback 권고는 advisory이며 runtime이 자동 적용하지 않습니다. artifact의 정책 소비 기록을 확인하세요. |
| Context budget margin | `compute_context_margin` (chars) / `compute_context_margin_from_texts` (tokenizer-exact) | `1 - (longest_call_tokens / context_window)`. 음수 = 제공된 구성 요소 기준 overflow 추정. 실제 request framing 비용은 별도. |
| Performance projection | `project_performance` | probe latency × calibration 규모 → 시작 전 wall-time 추정. |

한 번의 `empirical_preflight()`는 `(judge_quality, endpoint, performance, warnings)`를 반환하고 fail-closed 숫자 기본값을 유지합니다. 측정 상태는 `warnings.measurement_status`를 우선 읽고 `probe_accounting`도 함께 저장하세요. warnings 문자열은 사람용 진단이며, 구조적 상태가 없는 구형 결과만 문자열 호환 추론을 사용합니다. 이 추론이 과거 측정 범위를 검증하는 것은 아닙니다.

## CLI: machine summary, scorecard, threshold gate

```bash
# 평평한 CI-consumable JSON (headline 수치 + schema_version, byte-stable):
preflight ... --summary

# 단일 파일 scorecard (stdlib only) — PR artifact용:
preflight ... --scorecard html --scorecard-out preflight.html

# judge가 너무 noisy하거나 endpoint가 너무 불안정하면 빌드 실패:
preflight ... --fail-over-noise-floor 0.10 --fail-under-schema-reliability 0.90
```

Exit code: `0` 전부 측정·범위 내 · `2` 한 필드가 fail-closed 기본값으로 떨어짐(미측정) · `3` 측정값이 `--fail-*` threshold 위반(`2`보다 우선) · `1` 사용/런타임 오류. 측정됐으나 나쁜 값(noisy judge, gate flip)만 있는 경우는 여전히 `0` — *측정은* 됐으니까.

## 더 읽기

| 주제 | 한국어 | English |
|---|---|---|
| 쉬운 시작 | [EASY_README_KR.md](EASY_README_KR.md) | [EASY_README.md](EASY_README.md) |
| 영문 원본 | — | [README.md](README.md) |
| 자동 생성 사실 (claims) | [docs/generated/claims_kr.md](docs/generated/claims_kr.md) | [docs/generated/claims.md](docs/generated/claims.md) |
| Trust model | [docs/trust_model_kr.md](docs/trust_model_kr.md) | [docs/trust_model.md](docs/trust_model.md) |
| Toolkit positioning | [docs/toolkit_positioning_kr.md](docs/toolkit_positioning_kr.md) | [docs/toolkit_positioning.md](docs/toolkit_positioning.md) |
| Claim ledger | [docs/claim_ledger_kr.md](docs/claim_ledger_kr.md) | [docs/claim_ledger.md](docs/claim_ledger.md) |
| Examples / demo | [docs/examples_kr.md](docs/examples_kr.md) | [docs/examples.md](docs/examples.md) |

자매 프로젝트: [omegaprompt](https://github.com/hibou04-ops/omegaprompt) (calibration 엔진) · [omega-lock](https://github.com/hibou04-ops/omega-lock) (광역 audit framework) · [mini-antemortem-cli](https://github.com/hibou04-ops/mini-antemortem-cli) (analytical, no-API preflight) · [antemortem-cli](https://github.com/hibou04-ops/antemortem-cli) (사전 구현 recon).

## 0.7.0에서 새로워진 것

- **Judge noise-floor 메트릭을 전면에.** 새 `judge_noise_floor()` 헬퍼 + 평평하고 `schema_version` 태그가 붙은 byte-stable CI dict를 만드는 `build_summary()`, 그리고 stdlib만 쓰는 `render_scorecard()` (Markdown / self-contained HTML).
- **CLI `--summary`** (machine summary), **`--scorecard md|html`** (+ `--scorecard-out`), 그리고 **`--fail-over-noise-floor` / `--fail-under-schema-reliability` / `--fail-under-context-margin`** threshold gate (새 exit code `3`).
- **버전 무관 publish 워크플로** + 릴리스를 자동 추종하는 dynamic PyPI shields.
- Frozen surface 무변경: `empirical_preflight`, 세 contract 레코드, console script, `omegaprompt>=1.1.0` pin 모두 동일 — additive only.

전체 이력은 [CHANGELOG.md](CHANGELOG.md) 참조.

## Trust loop (네트워크 없이)

아래는 전부 오프라인(API key 없이) 실행되며 `scripts/release_audit.py`가 그대로 enforcing하는 순서입니다 — 로컬 CI와 release gate가 lockstep을 유지합니다:

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

`python examples/demo_replay.py`는 scripted fake judge로 `empirical_preflight`를 재현 — 출력은 `examples/_demo_output.txt`와 byte-for-byte 동일(`tests/test_demo_replay.py`가 검증)한 "warning surface 깨졌나?" smoke check.

## MCP server

이 패키지는 10개의 agent 호출 가능한 MCP 도구도 expose합니다 (`empirical_preflight`, `measure_judge_consistency`, `measure_gate_flip_rate`, `measure_scale_monotonicity`, `probe_strict_schema`, `compute_context_margin`, `compute_context_margin_from_texts`, `noise_floor_estimate`, `project_performance`, `derive_adaptation_plan`) — regenerated 목록은 [docs/generated/claims_kr.md](docs/generated/claims_kr.md).

```bash
pip install "mini-omega-lock[mcp]"
python -m mini_omega_lock.mcp           # stdio (Claude Code default)
python -m mini_omega_lock.mcp --http    # streamable-http
```

> **analytical(no-API, deterministic) preflight를 원하면?** 자매 도구 [`mini-antemortem-cli`](https://pypi.org/project/mini-antemortem-cli/) — 같은 plugin interface, LLM probe 대신 deterministic rule-based classifier.

## 증명하지 않는 것

모델 품질, judge 품질, 부하 상태 provider 신뢰도 벤치마크가 아닙니다. 프로덕션 readiness 증명도 아닙니다. 반복 변동과 측정 상태를 확인하도록 좁은 pre-flight 표면(judge variability / endpoint / context / latency)을 측정합니다. A/B 유의성 판단은 별도 비교 설계가 필요합니다. 항목별 경계는 [docs/trust_model_kr.md](docs/trust_model_kr.md), [docs/claim_ledger_kr.md](docs/claim_ledger_kr.md) 참조.

## License

Apache 2.0. 상세는 [LICENSE](LICENSE).

## 0.8.0: 실제 관측 공유와 측정 상태

- 같은 `(rubric, item, response)`의 consistency와 gate flip은 실제 judge 관측 배치를 공유합니다. 기본 3+5회가 5회로 줄며 각 지표는 요청한 3개·5개 prefix만 사용합니다. 독립 표본 수를 합산하지 않습니다. 호출 순서가 바뀌므로 stateful judge의 수치가 달라질 수 있습니다.
- 기존 4-tuple과 warnings list 동작을 유지합니다. 반환 warnings의 `measurement_status`와 `probe_accounting`을 함께 저장하세요. CLI/MCP JSON도 두 필드를 제공합니다. 요약은 상태를 우선 읽고 구형 일반 list에는 경고 문자열 호환 읽기를 사용합니다.
- 상태는 `measured`, `unmeasured`, `insufficient_samples`, `failed`, `estimated`, `not_applicable`입니다. 1회 채점은 변동 측정에 부족합니다. 실패한 호출 시간도 accounting에 포함하고, 성공 호출 latency projection과 구분합니다. provider 내부 재시도·실패 토큰 비용은 관측할 수 없으면 `null`/unknown으로 남깁니다.
- `judge_noise_floor`는 호환 이름이며 값은 clipped CV입니다. 새 별칭 `judge_relative_variability`도 같은 값입니다. `fitness_noise_floor`는 aggregate fitness의 표준편차입니다. 둘 다 임의 A/B 개선의 유의성을 판정하지 않습니다.
- CLI: 정상 실행 0은 지정된 측정 완료를 뜻합니다. 미측정·실패·표본 부족·추정은 2, **측정한** 값의 사용자 threshold 위반은 3, 잘못된 입력은 1입니다. threshold 없는 성공을 judge 품질 통과로 해석하지 마세요.

[전후 근거·호환성·재현 명령](docs/upgrade-0.8.0.md). 유료 provider 검증은 수행하지 않았습니다.
