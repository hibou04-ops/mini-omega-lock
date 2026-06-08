# mini-omega-lock (한국어)

> **[omegaprompt](https://pypi.org/project/omegaprompt/) calibration을 위한 empirical preflight probes.** Judge consistency, endpoint schema reliability, context-budget margin, latency, noise floor를 측정해서 `PreflightReport` 레코드를 만들어 omegaprompt의 `derive_adaptation_plan`에 흘려줍니다.

[![CI](https://github.com/hibou04-ops/mini-omega-lock/actions/workflows/ci.yml/badge.svg)](https://github.com/hibou04-ops/mini-omega-lock/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/badge/pypi-0.6.1-blue.svg)](https://pypi.org/project/mini-omega-lock/)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org)
[![Parent](https://img.shields.io/badge/parent-omegaprompt%E2%89%A51.1.0-blueviolet.svg)](https://pypi.org/project/omegaprompt/)

```bash
pip install mini-omega-lock
```

> 본 페이지는 [README.md](README.md)(영문)의 한국어 미러본입니다. 식별자 / 명령 / 함수명은 번역하지 않습니다. 짧은 도입은 [EASY_README_KR.md](EASY_README_KR.md).

## Trust & verification (한국어 문서 묶음)

| 주제 | 한국어 | English |
|---|---|---|
| 자동 생성 사실 (claims) | [docs/generated/claims_kr.md](docs/generated/claims_kr.md) | [docs/generated/claims.md](docs/generated/claims.md) |
| Trust model | [docs/trust_model_kr.md](docs/trust_model_kr.md) | [docs/trust_model.md](docs/trust_model.md) |
| Toolkit positioning | [docs/toolkit_positioning_kr.md](docs/toolkit_positioning_kr.md) | [docs/toolkit_positioning.md](docs/toolkit_positioning.md) |
| Claim ledger | [docs/claim_ledger_kr.md](docs/claim_ledger_kr.md) | [docs/claim_ledger.md](docs/claim_ledger.md) |
| Examples / demo | [docs/examples_kr.md](docs/examples_kr.md) | [docs/examples.md](docs/examples.md) |
| 쉬운 시작 | [EASY_README_KR.md](EASY_README_KR.md) | [EASY_README.md](EASY_README.md) |

## 이럴 때 씁니다

- 같은 응답인데도 judge 점수가 run마다 다름.
- Endpoint가 STRICT_SCHEMA mode를 silent하게 거절.
- 긴 calibration 실행 전에 wall-time 추정이 필요.

Stock frontier-tier provider + 선언된 기본값으로 잘 돌아가는 경우 굳이 필요 없습니다.

## 0.6.1에서 새로워진 것

- **릴리스 워크플로 경화 (CI 전용).** publish 워크플로에서 `release_audit`의 tag-skip env(`MINI_OMEGA_LOCK_RELEASE_WORKFLOW`)를 job 전체가 아니라 publish-readiness 스텝으로만 좁혔습니다. 덕분에 deterministic-verification pytest 스텝은 pre-tag 가드를 full strength로 돌립니다. 패키지/동작 변경 없음 — wheel/sdist는 버전 문자열만 빼면 0.6.0과 동일합니다.

## 0.6.0에서 새로워진 것

- **Release 인프라 (`publish.yml`).** Trusted-publishing GitHub workflow (deterministic gauntlet + build + wheel smoke + readiness gate, 그다음 `pypi` environment + OIDC로 PyPI publish).
- **Silent-degradation 신호 (C2).** `probe_strict_schema`가 strict-schema probe에서 `ProviderError` 없이 `parsed=None`이 오면 `silent_degradation_detected=True`로 표시합니다 — 예전엔 평범한 parse miss로 보이던 silent degradation. 미측정/fail-closed 경로는 `False`를 유지하되 degradation을 측정하지 않았다고 warning합니다.
- **`preflight` CLI (H1).** `empirical_preflight()` + `derive_adaptation_plan()`을 감싸는 `preflight` console script (`--json` / `--jsonl` / `--text`). 어떤 필드든 fail-closed 기본값으로 떨어지면 non-zero로 종료 (CI용 fail-closed 의미 그대로). 사용 불가한 `--token-counter`는 heuristic으로 조용히 fallback하지 않고 raise합니다.
- **Doc-citation 수정 (M5).** 존재하지 않는 `omega_lock.preflight` API를 인용하던 docstring을 실제 존재하는 omega-lock (parameter-calibration framework) 레벨로 정정.
- **완전한 MCP 표면 (H2).** 새 MCP 도구 4개 (`measure_scale_monotonicity`, `probe_strict_schema`, `compute_context_margin_from_texts`, `derive_adaptation_plan`) + `empirical_preflight` MCP 파라미터 4개 (`monotonic_examples`, `token_counter`, `system_prompts`, `gate_flip_repeats`). Tokenizer dispatch는 fail-loud — 사용 불가한 tokenizer는 chars/token heuristic으로 조용히 fallback하지 않고 raise.

Development Status는 `3 - Alpha`로 유지합니다; CLI/MCP 표면이 freeze되는 다음 릴리스에서 `4 - Beta`로 올립니다.

## Trust loop (네트워크 없이)

아래 명령은 전부 오프라인 (provider API key 없이 실행). `scripts/release_audit.py`가 그대로 enforcing하는 순서입니다.

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

### 결정론적 demo (한 줄, API key 불필요)

```bash
python examples/demo_replay.py
```

Scripted fake judge로 `empirical_preflight`를 재현 — 출력은 `examples/_demo_output.txt`와 byte-for-byte 동일 (`tests/test_demo_replay.py`가 검증). "warning surface 깨졌는지" 빠른 smoke check로 활용.

## 어떻게 다른가?

| 능력 | `mini-omega-lock` (본 패키지) | `mini-antemortem-cli` | `omegaprompt` default preflight | 임시 provider smoke test |
|---|---|---|---|---|
| 실제 live judge probe (production) | yes — 테스트는 mock | no (analytical) | no (declared defaults) | varies |
| Judge consistency / gate-flip 측정 | `measure_judge_consistency`, `measure_gate_flip_rate` | scope 밖 | scope 밖 | ad-hoc |
| Strict-schema reliability 측정 | `probe_strict_schema`; 미측정 시 **fail-closed at 0.0** | scope 밖 | scope 밖 | 보통 pass/fail만 |
| Context margin | `compute_context_margin` (chars heuristic) + `compute_context_margin_from_texts` (tokenizer-exact) | analytical 추정 | partial | ad-hoc |
| Latency projection | yes (consistency probe wall-time 재사용) | no | no | ad-hoc |
| Noise floor | 호출자 제공 `fitness_samples`; 아니면 **fail-closed** | no | no | no |
| 오프라인 testability | 기본 `pytest -q` 완전 오프라인 | deterministic by construction | yes | 보통 아님 |
| `omegaprompt.preflight.PreflightReport` shape 호환 | yes | yes | source | partial |
| **증명하지 않는 것** | 모델 품질, 부하 상태 provider 신뢰도, 프로덕션 도입, 외부 검증 | 동일 | 동일 | 동일 |
| Analytical trap classification | scope 밖 — `mini-antemortem-cli` 사용 | yes | no | no |

한 줄 요약: 이 패키지의 empirical probe는 **좁은** preflight 표면(judge / endpoint / context / latency / noise floor)만 측정합니다. 모델 품질 벤치마크도, 프로덕션 readiness 증명도 아닙니다. 전체 경계는 [docs/trust_model_kr.md](docs/trust_model_kr.md), [docs/toolkit_positioning_kr.md](docs/toolkit_positioning_kr.md), [docs/claim_ledger_kr.md](docs/claim_ledger_kr.md) 참조.

## MCP server

이 패키지는 10개의 도구를 agent에서 호출 가능한 MCP 도구로 expose합니다 (regenerated 목록: [docs/generated/claims_kr.md](docs/generated/claims_kr.md)).

```bash
pip install "mini-omega-lock[mcp]"
python -m mini_omega_lock.mcp           # stdio (Claude Code default)
python -m mini_omega_lock.mcp --http    # streamable-http
```

자세한 시나리오: [AGENT_TRIGGERS.md scenario 2](https://github.com/hibou04-ops/omegaprompt/blob/main/AGENT_TRIGGERS.md#scenario-2--pre-calibration-sanity-check).

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
    judge=judge, rubric=rubric, probe_item=probe,
    probe_response="4", consistency_repeats=3,
)
for w in warnings:
    print(f"[mini-omega-lock] {w}")

report = PreflightReport(judge_quality=judge_quality, endpoint=endpoint, performance=performance)
plan = derive_adaptation_plan(report=report)
```

`warnings` 리스트는 항상 load-bearing — fail-closed 기본값에 떨어진 필드를 모두 명시합니다. CI gate에서는 cosmetic으로 다루지 마세요.

## License

Apache 2.0. 상세는 [LICENSE](LICENSE).
