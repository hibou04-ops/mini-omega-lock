# mini-omega-lock — 쉬운 설명

> 압축 버전. 원본: [README_KR.md](README_KR.md) · English easy: [EASY_README.md](EASY_README.md)

```bash
pip install mini-omega-lock
```

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


## 한 문장 요약

**당신의 prompt-eval 개선폭이 judge 자신의 noise보다 작을 수 있고, 그러면 추가 검증이 필요합니다.** mini-omega-lock은 A/B 결과를 믿기 전에 그 noise를 측정합니다.

## "noise floor"가 뭔가요?

LLM judge는 *같은* 답에 *같은* 점수를 매번 주지 않습니다. 고정된 답 하나를 다섯 번 채점 → 미묘하게 다른 다섯 점수. 그 흔들림이 judge의 **noise floor**입니다.

동일 항목의 반복 CV와 fitness 표준편차는 A/B 유의성 검정이 아닙니다. 두 후보의 대응 표본, 불확실성, 사전 판정 기준을 별도로 확인하세요.

## 30초 사용법

```bash
# Python 불필요 — CI 친화적 숫자 하나:
preflight --provider anthropic --rubric rubric.json \
          --probe-item item.json --probe-response "4" --summary
# -> {"judge_noise_floor": 0.07, "schema_reliability": 0.0, ...}
```

```python
from mini_omega_lock import empirical_preflight, judge_noise_floor
# ... judge + rubric + probe item 구성 (README_KR.md quick start 참조) ...
judge_quality, endpoint, performance, warnings = empirical_preflight(
    judge=judge, rubric=rubric, probe_item=probe,
    probe_response="4", consistency_repeats=5,
)
print(judge_noise_floor(judge_quality))   # 예: 0.07
```

`judge_noise_floor`는 clipped 상대 CV (`1 - consistency`)이며 절대 A/B 효과 크기의 기준이 아닙니다. 기본 공유 judge/gate 배치는 실제 관측 5개를 사용하며 전체 비용은 추가 probe와 provider 가격에 따라 달라집니다.

## 같은 패스에서 함께 확인

| 항목 | 뭘 알려주나 |
|---|---|
| **Judge noise floor** | headline: judge가 자기와 얼마나 어긋나나. |
| **Schema reliability** | STRICT_SCHEMA parse 성공 비율과 silent 실패. JSON fallback은 advisory 권고이며 runtime 자동 적용이 아님. |
| **Context budget margin** | 가장 큰 호출이 context 한계에 얼마나 가까운가. 음수 = overflow. |
| **Wall-time projection** | 전체 실행이 시작 전에 얼마나 걸릴지. |

미측정 숫자는 fail-closed 기본값을 사용합니다. `warnings.measurement_status`를 우선 읽고 `probe_accounting`도 보존하세요. 경고 문자열 추론은 구형 결과의 호환 경로이며 과거 측정 완료를 입증하지 않습니다.

## omegaprompt와 함께 — 또는 단독으로

- **단독:** noise-floor + schema-reliability 수치는 그 자체로 유용. `preflight` 돌려 CI를 gate.
- **[omegaprompt](https://pypi.org/project/omegaprompt/)와 함께:** emit하는 레코드가 omegaprompt의 `derive_adaptation_plan`에 들어가 calibration threshold를 당신 인프라에 맞춰 자동 튜닝. mini-omega-lock은 probe, omegaprompt는 그것이 먹이는 엔진. (이걸 설치하면 omegaprompt가 함께 깔립니다 — hard dependency.)

## CI용 CLI 추가 기능

```bash
preflight ... --scorecard html --scorecard-out preflight.html   # PR artifact
preflight ... --fail-over-noise-floor 0.10                       # 너무 noisy하면 빌드 실패
preflight ... --fail-under-schema-reliability 0.90              # endpoint 불안정하면 실패
```

Exit code: `0` 정상 · `2` 측정 못 한 항목 있음 · `3` 값이 `--fail-*` 한계 위반 · `1` 사용 오류.

## 건너뛸 때

- Stock frontier provider, known-stable tier — 기본값으로 충분.
- 빠른 반복 (run당 ~10초 추가).
- API 접근 없는 test / CI (omegaprompt는 선언된 기본값으로도 잘 돎).

## 더 깊이

- 전체 README: [README_KR.md](README_KR.md)
- Contract 정의: `omegaprompt.preflight.contracts`
- Analytical, zero-API 자매: [mini-antemortem-cli](https://pypi.org/project/mini-antemortem-cli/)

License: Apache 2.0. Copyright (c) 2026 Kyunghoon Gwak.

## 0.8.0: 실제 관측 공유와 측정 상태

- 같은 `(rubric, item, response)`의 consistency와 gate flip은 실제 judge 관측 배치를 공유합니다. 기본 3+5회가 5회로 줄며 각 지표는 요청한 3개·5개 prefix만 사용합니다. 독립 표본 수를 합산하지 않습니다. 호출 순서가 바뀌므로 stateful judge의 수치가 달라질 수 있습니다.
- 기존 4-tuple과 warnings list 동작을 유지합니다. 반환 warnings의 `measurement_status`와 `probe_accounting`을 함께 저장하세요. CLI/MCP JSON도 두 필드를 제공합니다. 요약은 상태를 우선 읽고 구형 일반 list에는 경고 문자열 호환 읽기를 사용합니다.
- 상태는 `measured`, `unmeasured`, `insufficient_samples`, `failed`, `estimated`, `not_applicable`입니다. 1회 채점은 변동 측정에 부족합니다. 실패한 호출 시간도 accounting에 포함하고, 성공 호출 latency projection과 구분합니다. provider 내부 재시도·실패 토큰 비용은 관측할 수 없으면 `null`/unknown으로 남깁니다.
- `judge_noise_floor`는 호환 이름이며 값은 clipped CV입니다. 새 별칭 `judge_relative_variability`도 같은 값입니다. `fitness_noise_floor`는 aggregate fitness의 표준편차입니다. 둘 다 임의 A/B 개선의 유의성을 판정하지 않습니다.
- CLI: 정상 실행 0은 지정된 측정 완료를 뜻합니다. 미측정·실패·표본 부족·추정은 2, **측정한** 값의 사용자 threshold 위반은 3, 잘못된 입력은 1입니다. threshold 없는 성공을 judge 품질 통과로 해석하지 마세요.

[전후 근거·호환성·재현 명령](docs/upgrade-0.8.0.md). 유료 provider 검증은 수행하지 않았습니다.
