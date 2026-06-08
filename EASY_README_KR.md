# mini-omega-lock — 쉬운 설명

> 본 README가 어렵게 느껴지는 분들을 위한 압축 버전.
> 원본: [README_KR.md](README_KR.md) · English easy: [EASY_README.md](EASY_README.md)

## 이게 뭔가요?

[omegaprompt](https://pypi.org/project/omegaprompt/)용 선택적 플러그인. Calibration 전에 **실제 환경을 측정**해서, omegaprompt가 당신 셋업이 실제로 뽑을 수 있는 수치에 맞춰 threshold를 조정하도록 함.

Omegaprompt 기본 provider/endpoint/judge 로 돌리는데 아무 문제 없으면 이거 필요 없음. 다음 중 하나라도 해당하면 설치:
- Judge가 동일 응답에 run마다 다른 점수를 줌.
- Local/cloud 엔드포인트가 strict schema 를 가끔 거부.
- 전체 calibration 이 얼마나 걸릴지 *실행 전*에 알고 싶음.

## 0.6.0에서 새로워진 것

- **`preflight` CLI** — 셸에서 바로 체크(`preflight --help`), Python 불필요; 측정 못 한 항목이 있으면 non-zero 종료(CI 친화적).
- **Silent-degradation 신호** — 엔드포인트가 조용히 파싱 불가 출력을 반환하면 이제 무시하지 않고 표시.
- **완성된 MCP 표면(10개 도구)** — 모든 probe + `derive_adaptation_plan` 도구가 agent 호출 가능.
- 여전히 **3 - Alpha**; CLI/MCP 표면이 freeze되는 다음 릴리스에서 4 - Beta.

## 측정하는 것 (5개 측정 카테고리; 10개 MCP 도구)

> 아래 5개 카테고리는 **개념상** probe 표면 — judge / endpoint / context / latency / noise floor. MCP 서버는 여러 카테고리가 둘 이상의 probe를 가지므로 (예: hard-gate flip rate, scale monotonicity, tokenizer-exact context margin이 각각 별도 도구) 측정값을 plan으로 바꿔주는 `derive_adaptation_plan`까지 더해 실제 등록된 **MCP 도구는 10개**입니다. 정식 도구 목록은 [docs/generated/claims_kr.md](docs/generated/claims_kr.md).


| Probe | 뭘 알려주나 | 기본 비용 |
|---|---|---|
| **Judge consistency** | 같은 (response, rubric) 을 N번 채점 → `1 − coefficient-of-variation`. 낮음 = noisy judge → `rescore_count > 1` 필요. | judge API 3회 |
| **Endpoint schema 신뢰도** | STRICT_SCHEMA probe가 parse된 비율. `< 0.9` → JSON_OBJECT fallback 트리거. | API 0–3회 (호출자 제공) |
| **Context budget margin** | `1 − (approx_tokens / context_window)`. 음수 = overflow 위험. | 0 (pure 계산) |
| **Performance projection** | 평균 latency × 데이터셋 크기 × candidate → projected wall time. | judge 1회 (latency probe) |
| **Noise floor** | 동일 파라미터 fitness 의 표준편차. Adaptive `min_kc4` 설정. | API 0회 (호출자가 샘플 제공) |

`empirical_preflight()` 기본 예산 총합: **~4 API 호출**. Frontier tier 에서 $0.01 미만.

## 설치

```bash
pip install mini-omega-lock
```

`omegaprompt>=1.1.0` 필요 (omegaprompt preflight contracts 를 import 해서 output record 생성).

## 최소 동작 예제

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
    consistency_repeats=3,   # 기본값
)
for w in warnings:
    print(f"[mini-omega-lock] {w}")

# omegaprompt adaptation layer 에 feed:
report = PreflightReport(judge_quality=judge_quality, endpoint=endpoint, performance=performance)
plan   = derive_adaptation_plan(report=report)
# plan.min_kc4_override, plan.rescore_count, plan.schema_mode_override 등
```

끝. Live API 호출 4번. `plan`이 omegaprompt에 뭘 조정할지 알려줌. `warnings` 리스트는 fail-closed 기본값으로 떨어진 필드를 모두 명시하므로 CI에서는 load-bearing 으로 다뤄야 함.

## Export 함수

전체 public API는 `mini_omega_lock.__all__`에 정의되어 있고, 재생성된 목록은 [docs/generated/claims_kr.md](docs/generated/claims_kr.md)에 있습니다. 가장 자주 쓰는 5개 진입점:

```python
from mini_omega_lock import (
    empirical_preflight,            # 복합: 모든 probe 실행, warnings 포함 4-tuple 리턴
    measure_judge_consistency,      # 개별: (JudgeQualityMeasurement, raw 점수)
    probe_strict_schema,            # 개별: EndpointMeasurement 리턴
    compute_context_margin,         # 순수 계산: float 리턴 (chars heuristic)
    noise_floor_estimate,           # 순수 계산: float stdev 리턴
)
```

`__all__`에 함께 export되는 항목: `compute_context_margin_from_texts` (tokenizer-exact 변형), `measure_gate_flip_rate`, `measure_scale_monotonicity`, `project_performance`. 기본 플로우는 `empirical_preflight`. 세밀한 제어가 필요하면 개별 호출 (예: 다수 calibration run 의 fitness sample 로 noise floor 계산).

## 쓸 때

- Judge-consistency 의심: 같은 응답에 다른 점수 본 적 있음.
- Local 또는 OpenAI-호환 엔드포인트: STRICT_SCHEMA 지원 신뢰 못 함.
- 장시간 calibration: 시작 전에 wall-time 예상치 원함.

## 건너뛸 때

- Stock frontier provider + LLMJudge on known-stable tier. 기본값으로 충분.
- 빠른 반복 중 — preflight 가 run 당 ~10초 추가.
- API 접근 없는 test / CI (omegaprompt 는 선언된 기본값으로도 잘 돎).

## 주의사항 하나: noise floor

`empirical_preflight`는 **noise floor를 계산하지 않음**. 리턴되는 `PerformanceMeasurement.noise_floor` 는 placeholder (0.0). 진짜 noise floor 는 동일 파라미터로 calibration 여러 번 돌려 fitness sample 모은 뒤, `noise_floor_estimate(samples)` 를 별도 호출해서 plan 에 patch.

버그 아닌 의도적 설계 — 단일 preflight probe 로 측정 불가능한 값.

## 더 깊이

- 전체 contract 정의: `omegaprompt.preflight.contracts` (omegaprompt 패키지 안)
- Adaptation 규칙: `omegaprompt.preflight.adaptation.derive_adaptation_plan`
- 자매 analytical preflight (API 호출 0, deterministic rules): [mini-antemortem-cli](https://pypi.org/project/mini-antemortem-cli/)

License: Apache 2.0. Copyright (c) 2026 hibou.
