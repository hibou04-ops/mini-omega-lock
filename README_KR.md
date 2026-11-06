# mini-omega-lock

[English](README.md) · [한국어](README.ko.md) · [English easy](EASY_README.md) · [한국어 easy](EASY_README_KR.md)

평가 결과를 해석하기 전에 반복 judge 변동과 미측정 상태를 확인하는 empirical preflight 도구입니다. 독립 hold-out이나 A/B 유의성 검정을 대신하지 않습니다.

[![CI](https://github.com/hibou04-ops/mini-omega-lock/actions/workflows/ci.yml/badge.svg)](https://github.com/hibou04-ops/mini-omega-lock/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/mini-omega-lock.svg)](https://pypi.org/project/mini-omega-lock/)

<!-- QUICKSTART_DEMO_START -->
## 10초 시작: 설치와 오프라인 게이트 결과

```bash
pip install mini-omega-lock
uvx --from mini-omega-lock preflight --help
```

실행 명령은 `preflight`입니다. 리플레이는 입력 거절과 경험적 절대 노이즈 상한 계산을 확인하며 A/B 유의성 검정이 아닙니다.

설치 후 이 저장소를 복제한 디렉터리에서 아래 데모를 실행합니다. diff 블록은 데모가 출력하는 실제 stdout입니다.

```bash
git clone https://github.com/hibou04-ops/mini-omega-lock.git
cd mini-omega-lock
python examples/quickstart_demo.py
```

```diff
- [BLOCKED] empty_observations: ValueError
- [BLOCKED] nonfinite_observation: ValueError
+ [PASS] finite_observations: empirical_noise_ceiling=0.1
```
<!-- QUICKSTART_DEMO_END -->


Repository: `hibou04-ops/mini-omega-lock` · PyPI: `mini-omega-lock` · import: `mini_omega_lock` · CLI: `preflight` · MCP: `mini-omega-lock-mcp` with `mini-omega-lock[mcp]`

## 0.8.7 — 문서·패키지 metadata 정리

이 문서·패키징 패치는 패키지 설명을 검토된 도메인 중립 소스 문서와 맞춥니다. 공개 API, probe 동작과 동결 fixture는 유지합니다. 새로운 성능·일반화 근거를 추가하지 않습니다.

## 0.8.6 — 태그 일치 검증을 거치는 CI 감사

기본 필수 의존성은 `pydantic>=2.6.0` 하나입니다. 필요한 계약·provider 경계·judge 코드를 내부 `_vendor` namespace에 포함해 `omegaprompt`, `omega-lock`, NumPy, provider SDK 없이 core import·CLI·fake-provider 데모가 동작합니다. SDK는 live provider를 선택할 때 지연 import합니다. `omegaprompt>=1.1.0`은 선택 extra `[bridge]`에만 있습니다.

Python 3.11+가 필요합니다. 이 checkout의 소스 버전은 **0.8.7**입니다. 아래 명령은 checkout을 설치합니다. 이전 [0.8.4는 PyPI에 게시되었습니다](https://pypi.org/project/mini-omega-lock/0.8.4/). 버전별 [0.8.7 PyPI 파일](https://pypi.org/project/mini-omega-lock/0.8.7/)과 [Actions](https://github.com/hibou04-ops/mini-omega-lock/actions)는 별도로 확인하세요. 소스 메타데이터만으로 게시 완료를 입증하지 않습니다.

태그 CI에서는 `scripts/ci_release_audit.py`가 패키지/런타임 버전 일치와 실제 Git 태그가 checkout된 HEAD를 가리키는지 확인한 뒤 audit 자식 프로세스에만 release-mode 플래그를 설정합니다. Main과 pull-request CI는 기존 pre-tag 방어를 유지하며 모든 감사 단계와 나머지 release-marker 검사도 그대로 실행합니다.

```bash
python -m pip install .
preflight --help
python examples/demo_replay.py
python examples/cli_demo_replay.py
```

위 fixture 데모는 API 키·live SDK·네트워크 없이 실행됩니다. 설치 시 의존성을 내려받을 수 있습니다. live probe에는 선택한 SDK, provider 설정, 인증이 별도로 필요합니다.

## compute_empirical_noise_ceiling

```python
from mini_omega_lock import (
    compute_empirical_noise_ceiling,
    compute_minimum_detectable_effect,
)

assert compute_minimum_detectable_effect is compute_empirical_noise_ceiling
assert compute_empirical_noise_ceiling([-0.1, 0.1]) == 0.1
```

정식 API는 package root와 `mini_omega_lock.probes` 양쪽에 노출된 `compute_empirical_noise_ceiling(paired_deltas, confidence_z=1.96)`입니다. 기존 `compute_minimum_detectable_effect`는 두 모듈에서 같은 callable을 가리키는 하위 호환 alias입니다.

```text
magnitudes = abs(paired_deltas)
ceiling = mean(magnitudes) + 1.96 * pstdev(magnitudes) / sqrt(n)
```

기본 `confidence_z`는 1.96이며 사용자가 유한한 0 이상의 값으로 바꿀 수 있습니다. `pstdev`는 분모가 n인 모집단 표준편차입니다. 빈 표본, NaN/Inf 관측값, 음수·비유한 z는 거부하고 단일 표본은 절댓값을 반환합니다. 이 수치는 제공된 반복 관측의 경험적 절대 노이즈 상한입니다. sampling design·검정력·분포 무관 신뢰구간·A/B 최소 검출효과를 확립하지 않습니다.

## 측정 상태와 원가

`empirical_preflight()`는 `(judge_quality, endpoint, performance, warnings)`를 반환합니다. 로컬 계약은 `mini_omega_lock.contracts`, provider는 `mini_omega_lock.providers`, judge는 `mini_omega_lock.judges`에서 사용합니다.

`warnings.measurement_status`를 우선 확인하고 `probe_accounting`도 저장하세요. 상태는 `measured`, `unmeasured`, `insufficient_samples`, `failed`, `estimated`, `not_applicable`입니다. 기존 4-tuple과 warnings list 동작은 유지합니다. 사람이 읽는 경고는 진단이며 구조화 상태가 없을 때의 구형 substring fallback은 과거 측정 범위를 검증하지 않습니다.

`judge_noise_floor`는 clipped CV(`1 - consistency`)이며 `judge_relative_variability`는 같은 값의 alias입니다. `fitness_noise_floor`는 aggregate fitness의 표준편차입니다. 상대 CV를 절대 A/B 점수 차이와 직접 비교하면 안 됩니다. consistency와 gate-flip의 동일 `(rubric,item,response)` 관측 배치는 공유하며 각 지표는 요청한 prefix만 사용합니다. 기본 배치는 실제 관측 5회이고 추가 probe는 호출을 더 사용합니다.

실패 호출 시간도 accounting에 포함하지만 성공 호출 latency projection과 구분합니다. 관측할 수 없는 provider 내부 재시도·실패 토큰 비용은 unknown/null입니다. schema fallback 제안은 advisory이며 실제 runtime 적용을 보증하지 않습니다.

## CLI와 선택 연동

CLI 종료 코드: 0은 요청 측정 실행 완료, 2는 미측정·실패·표본 부족·추정 상태, 3은 실제 측정값의 사용자 threshold 위반, 1은 입력·runtime 오류입니다. threshold 없는 종료 0은 judge 품질 통과나 배포 승인이 아닙니다.

```bash
# Live example: requires the selected provider SDK and credentials.
preflight --provider anthropic --rubric rubric.json \
  --probe-item item.json --probe-response "4" --summary

python -m pip install ".[mcp]"
mini-omega-lock-mcp
```

MCP SDK 지원 범위는 `>=1.0.0,<2.0.0`이며 2.x 동작은 검증하지 않았습니다. parent 연동에는 `[bridge]`를 설치합니다. 로컬 `PreflightReport`와 adaptation은 parent 없이 동작합니다. `mini_omega_lock.bridge.to_omegaprompt_report(report)`로 보고서를 변환하고, 기존 parent provider를 로컬 `LLMJudge`에 넣을 때는 `adapt_omegaprompt_provider(provider)`로 감쌉니다. 모델 클래스 identity를 공유한다고 가정하지 않습니다.

## 로컬 검증과 한계

```bash
python -m pytest
python scripts/generate_readme_claims.py --check
python scripts/check_repo_consistency.py
```

로컬 계약·fake-provider 재현성은 외부 OOS 유효성, live judge 품질, 부하 안정성 또는 production readiness의 증거가 아닙니다. 외부 provider 검증을 수행했다고 주장하지 않습니다. 독립 OOS 비교에는 표본 단위, split, 반복측정 상관, 불확실성 및 의사결정 규칙을 별도로 선언해야 합니다.

## 선택 bridge 계약 검증

실제 설치된 `omegaprompt` 모델과 vendored 모델의 필드·검증 schema·Enum 값을 비교하고 JSON을 양방향으로 왕복합니다. 검증 오류의 종류와 위치도 비교합니다. 아래 검사는 live provider를 호출하지 않습니다.

```bash
python -m pip install ".[dev,mcp,bridge]"
python -m pytest -m bridge tests/test_bridge_contracts.py
```

parent 패키지가 없을 때만 이 선택 통합 검사 파일을 건너뜁니다. 설치된 parent의 import나 계약이 깨졌으면 실패합니다. 독립 core 검사는 parent 없이 계속 실행하며 필수 의존성은 늘리지 않았습니다.

`ProviderRequest.output_schema`는 Python 클래스이므로 JSON으로 클래스 identity를 전송하지 않습니다. `ProviderResponse.parsed`의 구체적인 타입은 명시한 schema로 복원해야 합니다. 실제 provider bridge 검사에서 이 경계와 사용자 schema·degradation 필드·원래 예외 cause 보존을 확인합니다. `ProviderError`와 `JudgeError`는 JSON 모델이 아닌 서로 다른 `RuntimeError` 하위 타입입니다.

## 근거와 문서

- Generated claims: [English](docs/generated/claims.md) / [한국어](docs/generated/claims_kr.md)
- [Trust model](docs/trust_model.md) · [Claim ledger](docs/claim_ledger.md)
- [Vendored source and maintenance](VENDORED.md) · [Changelog](CHANGELOG.md)
- [0.8.0 measurement-contract migration](docs/upgrade-0.8.0.md)

한국어 canonical 문서는 [README.ko.md](README.ko.md)이며 [README_KR.md](README_KR.md)는 같은 본문의 호환 사본입니다.

Apache 2.0. [LICENSE](LICENSE) · [NOTICE](NOTICE).
