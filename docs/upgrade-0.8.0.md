# 0.8.0 검증과 이행

기준은 `a850d686cdd62c508d8bbeeb6eff6c8434c0ae1c`(공개 0.7.1과 같은 commit)입니다. Windows, Python 3.12, omegaprompt 2.1.2의 격리 환경에서 오프라인 scripted judge를 사용했습니다. 호출 수는 실제 `judge.score` 호출을 세었으며 캐시 응답을 쓰지 않았습니다. 시간 배속이나 live model 품질 주장은 하지 않습니다.

| consistency / gate 반복 | 이전 실제 호출 | 새 실제 호출 | consistency 표본 |
|---|---:|---:|---:|
| 3 / 5 | 8 | 5 | 3 |
| 7 / 3 | 10 | 7 | 7 |
| 3 / 0 | 3 | 3 | 3 |

각 지표는 공유 배치의 자기 요청 수만큼의 prefix를 사용합니다. 두 지표의 표본은 서로 독립하지 않습니다. 실패 시 배치를 중단하고 필요한 prefix가 확보되지 않은 지표는 `failed`입니다. 기존보다 호출 순서가 달라지므로 상태를 가진 judge의 결과가 같다고 보장하지 않습니다.

재현:

```bash
python benchmarks/observation_cost.py
python benchmarks/observation_cost.py --source-root /path/to/baseline
python -m pytest -q tests/test_observation_contracts.py
python examples/cli_demo_replay.py --check
```

이는 수정에 사용한 개발 사례이며 독립·블라인드 검증은 아닙니다. [이전](../benchmarks/upgrade-0.8.0/before.json), [수정 후](../benchmarks/upgrade-0.8.0/after.json)의 결정적 호출 기록을 제공합니다. 기존 golden corpus는 보존했습니다. CLI demo golden은 두 additive 필드와 경고 전달을 반영해 생성기로 다시 만들었으며 timing만 마스킹합니다.

`empirical_preflight`는 기존 `(judge_quality, endpoint, performance, warnings)`를 반환합니다. warnings는 list 호환 객체이며 `measurement_status`, `probe_accounting`을 추가로 보유합니다. 일반 list로 복사하거나 JSON list만 저장하면 추가 정보를 잃으므로 두 dict를 명시적으로 함께 저장하세요. CLI/MCP는 두 dict를 출력합니다. 새로운 omegaprompt의 `PreflightReport`에는 두 필드를 넣으며 구형 omegaprompt에서는 지원 필드만 넘깁니다. 빈 상태 dict는 과거 측정 상태가 알려지지 않았다는 의미입니다.

`attempted_calls`, `successful_calls`, `failed_calls`는 wrapper가 직접 관측한 judge/schema 요청 수입니다. `elapsed_ms`는 실패를 포함한 요청 시간의 합, `total_elapsed_ms`는 전체 preflight 시간입니다. 성공 응답의 usage만 합산합니다. provider 내부 재시도 수는 `null`, 실패 호출의 usage는 알 수 없다고 표시합니다. 전체 청구 비용이 모두 계측됐다고 주장하지 않습니다.

`judge_noise_floor` 호환 필드의 값은 `1-consistency`인 clipped CV입니다. 상대 변동이며 절대 fitness 단위가 아닙니다. `fitness_noise_floor`는 반복 aggregate fitness의 표준편차입니다. 평균이 0인 고정 점수는 CV를 정의할 수 없어 기존 호환값 0을 반환하지만 이것은 품질이나 A/B 유의성 보장이 아닙니다. 비유한 fitness는 입력 오류로 거절합니다.

CLI 종료: 0은 지정 측정 완료, 1은 입력 오류, 2는 미측정·추정·표본 부족·실패, 3은 측정한 값의 명시적 threshold 위반입니다. threshold가 없으면 0을 품질 승인으로 읽으면 안 됩니다. 과거 미측정 schema 기본값 0을 threshold 실패 3으로 보던 경로는 이제 불완전 측정 2로 구분합니다. 잘못된 threshold는 provider 호출 전 거절합니다.

CLI `--require-measurements judge_consistency,gate_flip_rate`로 이번 실행에서 필요한 관측을 명시할 수 있습니다. 생략하면 기존처럼 전체 측정을 요구합니다. 선택하지 않은 필드의 미측정 상태와 warnings는 출력에 남고 `all_fields_measured`도 거짓으로 유지합니다. threshold를 지정한 필드는 자동으로 필수에 포함되므로 미측정 기준을 생략해서 통과시킬 수 없습니다. JSON의 `required_measurements`, `quality_thresholds_configured`, `quality_assessment`로 관측 범위와 기준 평가를 구분합니다. 미지 측정명은 호출 전 입력 오류입니다. MCP도 명시적으로 `quality_assessment=not_requested`를 반환합니다.
