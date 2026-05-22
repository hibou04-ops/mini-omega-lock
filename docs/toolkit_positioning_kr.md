# Toolkit positioning (한국어)

`omegaprompt` toolkit은 인터페이스를 공유하지만 서로 다른 sub-problem을 푸는 관련 저장소들의 모음입니다. 본 문서는 "각 도구가 무엇을 하고 무엇을 *하지 않는지*"의 정식 reference. 아래 boundary 밖의 요청은 `mini-omega-lock` scope가 아니며 해당 sibling 저장소에 제기하세요.

본 문서의 claim은 **category-level** — sibling 저장소의 feature 목록을 재생산하지 않습니다. 그건 해당 저장소 owner만이 최신 상태로 유지할 수 있는 사실. 공식 PyPI/GitHub URL로 cross-reference하세요.

## 한눈에

| 패키지 | 역할 | Live API 호출? | 기본 모드 |
|---|---|---|---|
| [`omegaprompt`](https://pypi.org/project/omegaprompt/) | Calibration 엔진; preflight plugin contract 정의. | yes (calibration 시) | core library |
| [`mini-omega-lock`](https://pypi.org/project/mini-omega-lock/) (본 repo) | Empirical preflight probe, `derive_adaptation_plan`에 feed. | yes (production); no (기본 테스트/CI). | Python package + MCP server |
| [`mini-antemortem-cli`](https://pypi.org/project/mini-antemortem-cli/) | Analytical preflight: deterministic rule 기반 trap classifier. | no | CLI + library |
| [`omega-lock`](https://github.com/hibou04-ops/omega-lock) | 더 넓은 parameter calibration / audit 프레임워크 (sensitivity, walk-forward, KC-4). | varies | framework |
| [`antemortem-cli`](https://github.com/hibou04-ops/antemortem-cli) | Pre-implementation recon CLI (코드/스펙 작성 전 문서·prior art 읽기). | varies | CLI |
| [`Antemortem`](https://github.com/hibou04-ops/Antemortem) | 방법론 / trap-spectrum reference. | n/a | docs |

## `mini-omega-lock`의 자리

`omegaprompt`는 preflight probe용 plugin interface(`omegaprompt.preflight.contracts` + `omegaprompt.preflight.adaptation`)는 노출하지만 probe code는 ship하지 않습니다. 두 sibling이 그 자리를 메움:

- **`mini-omega-lock`** (본 repo)은 *empirical* probe를 제공 — 작은 LLM 호출(judge consistency, schema reliability) 발생 + 런타임 입력으로부터 deterministic metric 계산(context margin, noise floor).
- **`mini-antemortem-cli`**는 *analytical* probe를 제공 — LLM 호출이 발생하기 *전* 단계에서 config에 대해 deterministic rule classification.

둘 다 `omegaprompt.preflight.contracts.PreflightReport` 호환 레코드를 emit. 나란히 실행해 두 report를 모두 `derive_adaptation_plan`에 feed 가능. 둘 사이 선택은 배타적이지 않음 — "smoke test" vs "static analysis"의 같은 축.

## `mini-omega-lock`이 **아닌** 것

- **Calibration 엔진이 아님.** `omegaprompt`가 calibration loop, judge scaffolding, dataset 추상화, adaptation policy를 소유. 본 패키지는 그 preflight input만 feed.
- **Analytical preflight가 아님.** Config의 deterministic rule classification은 `mini-antemortem-cli`. `mini-omega-lock`은 *empirical* probe만 — config를 e.g. "trap: ambiguous rubric"으로 classify하지 않음.
- **General agent framework가 아님.** 여기서 노출하는 MCP server는 empirical preflight probe와 1:1로 매핑된 6개 도구. Chat, planning, RAG, non-preflight surface 일체 제공 안 함.
- **Benchmark가 아님.** 어떤 모델도 ranking되지 않고, leaderboard도 없고, provider 간 aggregate 점수도 주장 안 함.
- **Dashboard나 SaaS가 아님.** 패키지는 Python 객체와 (선택적) MCP 응답을 emit. Hosted UI 없음.
- **End-user용 CLI가 아님.** 유일한 console script는 MCP server(`mini-omega-lock-mcp`). `mini-omega-lock` user-facing CLI는 없음 — Python이나 MCP로 소비. `scripts/*.py`는 repo 유지보수용 script이지 user tool이 아님.

## 올바른 도구 선택

| 하고 싶은 것 | 쓸 것 |
|---|---|
| omegaprompt threshold를 내 실제 환경에 맞춤 | `mini-omega-lock` |
| Calibration 전에 config trap 잡기 | `mini-antemortem-cli` |
| Full calibration 실행 | `omegaprompt` |
| Calibration run 감사, sensitivity / walk-forward 분석 | `omega-lock` |
| 코드/스펙 작성 전 pre-implementation recon | `antemortem-cli` |
| 방법론 / trap-spectrum reference | `Antemortem` |
| Preflight probe를 agent에게 MCP로 노출 | `mini-omega-lock[mcp]` |

## 안정성과 호환성

- `mini-omega-lock`은 PyPI Development Status `3 - Alpha`. `mini_omega_lock/__init__.py`의 `__all__`만 안정 surface; `mini_omega_lock.probes`도 안정이지만 private helper는 변경 가능.
- 0.4.0에서 `empirical_preflight`는 3-tuple에서 4-tuple로 변경(`warnings` 추가). 0.4 이전 호출자는 unpacking 업데이트 필요 — `tests/test_fail_closed_defaults.py::test_empirical_preflight_returns_4_tuple_not_3_tuple` 참조.
- 최소 `omegaprompt` 핀은 `pyproject.toml`의 값 (regenerated into `docs/generated/claims_kr.md`). 더 낮은 `omegaprompt` 버전은 본 패키지가 import하는 contract를 갖지 않을 수 있음.

## Cross-toolkit cookbook

여러 toolkit 패키지를 가로지르는 end-to-end 시나리오 (예: preflight → calibration → audit)는 부모 `omegaprompt` repo의 [AGENT_TRIGGERS.md](https://github.com/hibou04-ops/omegaprompt/blob/main/AGENT_TRIGGERS.md) 참조.
