# mini-omega-lock (한국어)

> **당신의 prompt-eval 개선폭이 judge 자신의 noise보다 작을 수 있습니다. mini-omega-lock은 A/B 결과를 믿기 전에 그 noise floor를 측정합니다.**

```bash
pip install mini-omega-lock
```

[![CI](https://github.com/hibou04-ops/mini-omega-lock/actions/workflows/ci.yml/badge.svg)](https://github.com/hibou04-ops/mini-omega-lock/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/mini-omega-lock.svg?cacheSeconds=3600)](https://pypi.org/project/mini-omega-lock/)
[![Python](https://img.shields.io/pypi/pyversions/mini-omega-lock.svg?cacheSeconds=3600)](https://pypi.org/project/mini-omega-lock/)
[![License](https://img.shields.io/pypi/l/mini-omega-lock.svg?cacheSeconds=3600)](LICENSE)
[![Parent](https://img.shields.io/badge/parent-omegaprompt%E2%89%A51.1.0-blueviolet.svg?cacheSeconds=3600)](https://pypi.org/project/omegaprompt/)

> 본 페이지는 [README.md](README.md)(영문)의 한국어 미러본입니다. 식별자 / 명령 / 함수명은 번역하지 않습니다. 짧은 도입은 [EASY_README_KR.md](EASY_README_KR.md).

## "noise floor"가 뭔가요?

LLM judge는 *같은* 응답에 *같은* 점수를 매번 주지 않습니다. 고정된 `(response, rubric)` 하나를 다섯 번 채점시키면 미묘하게 다른 다섯 개의 점수가 나오곤 합니다. 그 산포가 바로 **judge의 noise floor**입니다.

이게 중요한 이유는 규칙 하나 때문입니다:

> **judge 자신의 noise보다 작은 최적화 delta는 진짜가 아니다.**

프롬프트 B가 A보다 0.4% 좋게 나왔는데, judge가 *동일한* 답을 재채점할 때 1.2%씩 흔들린다면, 그 "승리"는 noise 안에 있습니다. B를 배포하겠지만 실제로 측정한 건 동전 던지기입니다. mini-omega-lock은 저렴한 probe call 몇 번으로 A/B delta를 믿기 *전에* 그 floor 수치를 알려줍니다.

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
for w in warnings:                 # fail-closed warnings는 load-bearing
    print("[mini-omega-lock]", w)
```

저렴한 API 호출 ~5번 (frontier tier에서 $0.01 미만). `judge_noise_floor`는 `1 - consistency`입니다: `0.0`이면 judge가 자기 자신과 한 번도 어긋나지 않은 것이고, 숫자가 클수록 "승리"를 믿으려면 더 큰 A/B delta가 필요합니다.

## omegaprompt와 함께 — 그리고 단독으로

- **단독:** noise-floor probe는 그 자체로 유용합니다. 어떤 LLM-judge / prompt-calibration 셋업에든 `preflight`를 돌려 floor + schema-reliability 수치를 얻고, CI를 거기에 gate하세요. 값을 읽는 데 omegaprompt 파이프라인이 필요 없습니다.
- **생태계 안에서:** `empirical_preflight`는 `omegaprompt.preflight.PreflightReport` 레코드(`JudgeQualityMeasurement` / `EndpointMeasurement` / `PerformanceMeasurement`)를 emit합니다. omegaprompt의 `derive_adaptation_plan`에 넘기면 calibration 엔진이 당신 인프라가 실제로 뽑을 수 있는 수치에 맞춰 threshold를 조정합니다. mini-omega-lock은 empirical probe 레이어, omegaprompt는 그것이 먹이는 엔진입니다.

레코드 생성을 위해 `omegaprompt`(`>=1.1.0`)에 의존하므로 `pip install mini-omega-lock`이 omegaprompt를 함께 끌어옵니다.

## "그냥 eval delta를 믿기" vs. mini-omega-lock

| | A/B delta를 믿음 | mini-omega-lock |
|---|---|---|
| judge 자기 불일치를 알려줌 | no | **yes** (`judge_noise_floor`) |
| judge noise보다 작은 delta를 잡음 | no — 동전 던지기를 배포 | **yes** — 믿기 전에 표시 |
| silent strict-schema 저하를 표시 | no | **yes** (`silent_degradation_detected`) |
| 긴 실행 전 wall time 추정 | no | **yes** |
| 비용 | 무료지만 오도함 | probe ~5회 (< $0.01) |

## 측정하는 것

| 표면 | 함수 | 뭘 알려주나 |
|---|---|---|
| **Judge noise floor** | `judge_noise_floor`, `measure_judge_consistency` | 고정된 쌍을 반복 채점한 점수의 `1 - CV`. 이 floor 아래의 A/B delta는 noise. |
| Hard-gate flip rate | `measure_gate_flip_rate` | *같은* 입력에서 pass/fail gate가 얼마나 자주 뒤집히나 — 점수가 안정적이어도 flip하는 gate는 ship 판정을 무작위로 만듦. |
| Endpoint schema reliability | `probe_strict_schema` | STRICT_SCHEMA parse 성공 비율. `< 0.9` → omegaprompt가 `JSON_OBJECT`로 fallback. silent 저하(200 형태인데 parse 불가)도 표시. |
| Context budget margin | `compute_context_margin` (chars) / `compute_context_margin_from_texts` (tokenizer-exact) | `1 - (longest_call_tokens / context_window)`. 음수 = overflow 확정. |
| Performance projection | `project_performance` | probe latency × calibration 규모 → 시작 전 wall-time 추정. |

한 번의 호출 — `empirical_preflight()` — 으로 이들을 한 패스에 실행하고 `(judge_quality, endpoint, performance, warnings)`를 리턴합니다. **측정 안 된 필드는 fail-closed** (예: `schema_reliability=1.0`이 아니라 `0.0`)되고 `warnings`에 명시되므로, agent는 항상 "측정된 0"과 "probe를 안 돌림"을 구분할 수 있습니다. CI에서 warnings 리스트는 cosmetic이 아니라 load-bearing으로 다루세요.

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

모델 품질, judge 품질, 부하 상태 provider 신뢰도 벤치마크가 아닙니다. 프로덕션 readiness 증명도 아닙니다. judge 자신의 noise보다 작은 eval delta를 그만 믿게 하려고 좁은 pre-flight 표면(judge noise / endpoint / context / latency)을 측정합니다. 항목별 경계는 [docs/trust_model_kr.md](docs/trust_model_kr.md), [docs/claim_ledger_kr.md](docs/claim_ledger_kr.md) 참조.

## License

Apache 2.0. 상세는 [LICENSE](LICENSE).
