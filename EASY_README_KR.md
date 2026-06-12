# mini-omega-lock — 쉬운 설명

> 압축 버전. 원본: [README_KR.md](README_KR.md) · English easy: [EASY_README.md](EASY_README.md)

```bash
pip install mini-omega-lock
```

## 한 문장 요약

**당신의 prompt-eval 개선폭이 judge 자신의 noise보다 작을 수 있고, 그러면 진짜 개선이 아닙니다.** mini-omega-lock은 A/B 결과를 믿기 전에 그 noise를 측정합니다.

## "noise floor"가 뭔가요?

LLM judge는 *같은* 답에 *같은* 점수를 매번 주지 않습니다. 고정된 답 하나를 다섯 번 채점 → 미묘하게 다른 다섯 점수. 그 흔들림이 judge의 **noise floor**입니다.

규칙: **프롬프트 B가 A를 그 흔들림보다 작은 폭으로 이기면, 그 "승리"는 noise입니다.** B를 배포하겠지만 측정한 건 동전 던지기. 이 도구는 floor 수치를 먼저 줘서 당신 delta가 진짜인지 알려줍니다.

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

`judge_noise_floor`는 `1 - consistency`. `0.0`이면 judge가 자기와 한 번도 어긋나지 않은 것. 숫자가 클수록 승리를 믿으려면 더 큰 A/B delta가 필요. 비용: 저렴한 API 호출 ~5번.

## 같은 패스에서 함께 확인

| 항목 | 뭘 알려주나 |
|---|---|
| **Judge noise floor** | headline: judge가 자기와 얼마나 어긋나나. |
| **Schema reliability** | STRICT_SCHEMA 호출 중 parse되는 비율. `< 0.9` → JSON fallback. silent 실패도 잡음. |
| **Context budget margin** | 가장 큰 호출이 context 한계에 얼마나 가까운가. 음수 = overflow. |
| **Wall-time projection** | 전체 실행이 시작 전에 얼마나 걸릴지. |

실행 *못 한* 항목은 **fail-closed** (안전해 보이는 `0.0`을 주되 warning). `warnings` 리스트가 "측정된 0"과 "측정 안 함"을 구분해줍니다 — CI에서 읽으세요.

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
