# Claim ledger (한국어)

`mini-omega-lock`의 모든 non-trivial 공개 claim을 위치, source-of-truth, 검증 명령, status marker와 함께 정리한 표. 본 ledger의 존재 목적: **`README.md`, `EASY_README.md`, `EASY_README_KR.md`, `README_KR.md`의 임의 줄을 reader가 기계적으로 검증 가능하게** 함.

새 claim을 공개 문서에 추가하고 본 ledger에 row를 더하지 않으면 `scripts/check_repo_consistency.py`가 fail해야 합니다 (체커 확장하거나, claim 제거).

## Status marker

| Marker | 의미 |
|---|---|
| `generated` | 값이 `scripts/generate_readme_claims.py`로부터 source 파일에서 렌더링됨. Drift는 `--check`가 탐지. |
| `source-backed` | Claim이 `src/`나 `tests/`의 특정 파일/라인을 지목. |
| `command-backed` | Claim이 특정 shell command로 검증 가능 (커맨드 같이 표기). |
| `artifact-backed` | Claim이 특정 deterministic artifact (golden case, demo replay, fixture manifest) 재실행으로 검증 가능. |
| `qualitative` | Category-level / boundary 진술, 의도적으로 수치로 못 박지 않음. |
| `not-claimed` | 부재 자체가 contract의 일부임을 명시. |

## Ledger

| # | Claim | 위치 | Source of truth | 검증 명령 | Status |
|---|---|---|---|---|---|
| 1 | "PyPI distribution은 `mini-omega-lock`" | README 배지, install 명령; EASY_READMEs | `pyproject.toml` `[project].name` | `python scripts/generate_readme_claims.py --check` | `generated` |
| 2 | 패키지 버전 `0.5.0` | README PyPI 배지 | `pyproject.toml` `[project].version` + `mini_omega_lock.__version__` | `python scripts/check_repo_consistency.py` | `generated` |
| 3 | Python ≥ 3.11 | README 배지 | `pyproject.toml` `[project].requires-python` | `python scripts/generate_readme_claims.py --check` | `generated` |
| 4 | `omegaprompt>=1.1.0` 의존 | README parent 배지 | `pyproject.toml` `[project].dependencies` | `python scripts/check_repo_consistency.py` | `generated` |
| 5 | Public API 이름들 | README/EASY_READMEs code block | `src/mini_omega_lock/__init__.py::__all__` | `python scripts/check_repo_consistency.py` | `source-backed` |
| 6 | MCP server 6개 도구 노출 | README, `mcp/__init__.py` docstring | `src/mini_omega_lock/mcp/server.py` `@mcp_app.tool()` decorator | `python scripts/generate_readme_claims.py --check` | `generated` |
| 7 | MCP optional extra는 `mcp` | README, EASY_READMEs | `pyproject.toml` `[project.optional-dependencies]` | `python scripts/check_repo_consistency.py` | `generated` |
| 8 | MCP 실행 명령은 `python -m mini_omega_lock.mcp` | README, EASY_READMEs | `src/mini_omega_lock/mcp/__main__.py` | `python scripts/check_repo_consistency.py` (hyphenated 변형 거부) | `source-backed` |
| 9 | `empirical_preflight`는 4-tuple 반환 (warnings) | README "TL;DR", trust model | `tests/test_fail_closed_defaults.py::test_empirical_preflight_returns_4_tuple_not_3_tuple` | `python -m pytest -q tests/test_fail_closed_defaults.py -k 4_tuple` | `source-backed` |
| 10 | 미측정 `schema_reliability` = `0.0` + warning | README, trust model | `src/mini_omega_lock/probes.py::empirical_preflight` + `tests/test_fail_closed_defaults.py::test_schema_reliability_*` | `python -m pytest -q tests/test_fail_closed_defaults.py` | `source-backed` |
| 11 | 실패한 probe latency는 `mean_call_latency_ms`에서 제외 | trust model | `tests/test_fail_closed_defaults.py::test_consistency_probe_failure_does_not_poison_latency_mean` | `python -m pytest -q -k consistency_probe_failure_does_not_poison` | `source-backed` |
| 12 | 기본 테스트 / 기본 CI 완전 오프라인 | README, trust model | `.github/workflows/ci.yml`; `tests/*`는 `MagicMock`/scripted provider 사용 | `python -m pytest -q` (`ANTHROPIC_API_KEY` unset) | `source-backed` |
| 13 | 결정론적 demo 출력 byte-for-byte 안정 | README, examples doc | `examples/_demo_output.txt`; `tests/test_demo_replay.py` | `python examples/demo_replay.py` 후 `python -m pytest -q tests/test_demo_replay.py` | `artifact-backed` |
| 14 | Golden case가 문서화된 probe matrix 커버 | README, examples doc | `benchmarks/golden_cases/*.json`; `tests/test_golden_cases.py` | `python scripts/run_golden_cases.py --check` | `artifact-backed` |
| 15 | Golden-case fixture 변조 없음 | examples doc, trust model | `benchmarks/golden_cases/manifest.json` (per-file SHA-256) | `python scripts/verify_fixture_integrity.py` | `artifact-backed` |
| 16 | `compute_context_margin`은 heuristic, tokenizer-exact 아님 | trust model | `src/mini_omega_lock/probes.py` 279–331 docstring | `grep -n "chars_per_token" src/mini_omega_lock/probes.py` | `source-backed` |
| 17 | `compute_context_margin`이 `token_counter` arg를 silent ignore | trust model | `src/mini_omega_lock/probes.py` 309–318 inline comment | #16과 동일 | `source-backed` |
| 18 | MCP `compute_context_margin` 도구는 `token_counter` 미노출 | trust model | `src/mini_omega_lock/mcp/server.py` 359–395 (signature) | `grep -n "def compute_context_margin" src/mini_omega_lock/mcp/server.py` | `source-backed` |
| 19 | MCP rubric path는 workspace-bound | trust model | `src/mini_omega_lock/mcp/server.py` `_workspace_root` + `tests/test_mcp_workspace_boundary.py` | `python -m pytest -q tests/test_mcp_workspace_boundary.py` (`mcp` 설치 시) | `source-backed` |
| 20 | Cross-platform 지원 (Ubuntu + Windows) | README CI 배지 | `.github/workflows/ci.yml` matrix | Actions 탭에서 workflow run 확인 | `source-backed` |
| 21 | Apache 2.0 license; 0.1.0은 MIT | README "License history" | `LICENSE`, `NOTICE`, README license history 블록 | `head LICENSE` | `source-backed` |
| 22 | README prose에 정확한 테스트 카운트 미claim | n/a (anti-claim) | `scripts/check_repo_consistency.py::check_readme_badges`가 `tests-N` 배지 금지 | `python scripts/check_repo_consistency.py` | `not-claimed` |
| 23 | Benchmark / leaderboard / model-quality 점수 미claim | trust model "검증하지 않는 것" | n/a | n/a | `not-claimed` |
| 24 | 프로덕션 도입 사례 미claim | toolkit positioning | n/a | n/a | `not-claimed` |
| 25 | Append-only audit trail / hash chain 미claim | examples doc (Fixture integrity 섹션) | n/a | n/a | `not-claimed` |
| 26 | Empirical probe는 좁은 preflight surface만 측정 | README "How is this different?", trust model | trust model | qualitative | `qualitative` |
| 27 | Analytical trap classifier 아님 | README, toolkit positioning | `mini-antemortem-cli`가 sibling | qualitative | `qualitative` |

## 새 claim 추가 절차

1. 해당 doc에 claim 추가.
2. 본 ledger에 row 추가 + 올바른 status marker.
3. Status가 `generated`나 `command-backed`라면 `scripts/check_repo_consistency.py`(혹은 `scripts/generate_readme_claims.py`)를 확장해 drift를 잡게 함.
4. `python scripts/check_repo_consistency.py && python -m pytest -q` 실행. 둘 다 통과해야 함.

## Claim 철회

Deterministic artifact나 command로 뒷받침할 수 없는 claim은 ledger에 남겨두지 말고 **제거**하세요. README에서 발견된 ledger 없는 수치/feature claim은 `check_repo_consistency.py`에 탐지 룰이 추가되는 즉시 release-audit script가 release blocker로 처리합니다.
