# IP Defense Checklist — Future Actions

> **For**: Kyunghoon Gwak (곽경훈) — Primary Author, [@hibou04-ops](https://github.com/hibou04-ops)
> **Purpose**: Action items the IP-defense package depends on but cannot self-execute. Read this when (a) you receive an employment offer, (b) you set up a GPG key, or (c) you need to verify the snapshot.
> **Created**: 2026-04-29 (consolidated cross-repo list across all six packages)

---

## ⚡ 입사 / 계약 시점 (가장 중요)

고용계약 또는 컨설팅 계약을 받으면 *서명 전에* 반드시 아래 3단계를 진행하세요. 자동화 안 됨, 본인이 직접 챙겨야 함.

### Step 1. 한국 직무발명법 노무사·변리사 30분 상담 (필수)

**왜**: 한국은 「발명진흥법」 + 「직무발명 보상지침」이 적용되며, 직무발명 vs 비직무발명 경계가 *통계적으로 정의*됨. 본 PRE_EXISTING_IP.md는 *국제 표준 (Schedule A)* 베이스라, 한국 회사 입사 시엔 보조 자료로 사용. 한국 법체계에 맞는 첨부 형식과 표현이 필요할 수 있음.

**무엇을 물어볼지**:
- 본 repo들이 "직무 외 발명"으로 인정받기 위한 한국 표준 표현
- 입사 후 *개인 시간*에 본 repo 발전 작업 시 어떤 조건이면 비직무발명으로 유지되는지
- 회사 IP 양도 조항(보통 표준 약관)에 대한 본인 권리 보호 표현
- 계약서에 "Pre-existing IP 별첨" 조항이 *없을 경우* 추가를 요구할지 여부

**어디서 / 비용**:
- 노무사: 일반 노무 상담 — 보통 첫 상담 무료 또는 5~10만원
- 변리사: IP 전문 — 30분 상담 5~15만원 (특허·트레이드마크 더 자세히 다룰 때)
- 노동부 무료 상담: 1350 (제한적, 직무발명 전문성은 약함)

**언제**: 입사 결정 후 계약서 받은 시점 ~ 서명 전. 보통 1~3일 안에 가능.

### Step 2. Schedule A 첨부

계약서에 다음 중 하나라도 있을 때 본 repo들을 명시적으로 첨부:
- "Pre-existing Intellectual Property"
- "Schedule A" 또는 "별표 1: 직무 외 발명"
- "본 계약에 따른 발명에 포함되지 않는 기존 발명"
- 어떤 형태로든 *과거 작업*을 분리하는 조항

**첨부할 내용** (PDF 출력 권장):

1. 각 repo의 PRE_EXISTING_IP.md PDF print:
   - omegaprompt: https://github.com/hibou04-ops/omegaprompt/blob/main/PRE_EXISTING_IP.md
   - omega-lock: https://github.com/hibou04-ops/omega-lock/blob/main/PRE_EXISTING_IP.md
   - Antemortem: https://github.com/hibou04-ops/Antemortem/blob/main/PRE_EXISTING_IP.md
   - antemortem-cli: https://github.com/hibou04-ops/antemortem-cli/blob/main/PRE_EXISTING_IP.md
   - mini-omega-lock: https://github.com/hibou04-ops/mini-omega-lock/blob/main/PRE_EXISTING_IP.md
   - mini-antemortem-cli: https://github.com/hibou04-ops/mini-antemortem-cli/blob/main/PRE_EXISTING_IP.md

2. 각 repo의 pre-employment 스냅샷 tag URL (immutable witness):
   - https://github.com/hibou04-ops/omegaprompt/releases/tag/pre-employment-ip-snapshot-2026-04-29
   - https://github.com/hibou04-ops/omega-lock/releases/tag/pre-employment-ip-snapshot-2026-04-28
   - https://github.com/hibou04-ops/Antemortem/releases/tag/pre-employment-ip-snapshot-2026-04-28
   - https://github.com/hibou04-ops/antemortem-cli/releases/tag/pre-employment-ip-snapshot-2026-04-28
   - https://github.com/hibou04-ops/mini-omega-lock/releases/tag/pre-employment-ip-snapshot-2026-04-29
   - https://github.com/hibou04-ops/mini-antemortem-cli/releases/tag/pre-employment-ip-snapshot-2026-04-29

3. 계약서에 추가 요청할 표현 (한국어 샘플):
   > 「본 계약 체결일 이전에 작성된 별첨 1의 발명·저작물(omegaprompt, omega-lock, Antemortem, antemortem-cli, mini-omega-lock, mini-antemortem-cli — 각 GitHub URL 및 pre-employment-ip-snapshot tag 참조)은 피용자의 기존 지식재산권으로 인정되며, 본 계약의 직무발명·업무상 저작물 양도 조항의 적용 대상에서 제외된다.」

### Step 3. 계약 후 작업 분리 원칙 유지

입사 후에도 본 repo들이 개인 IP로 유지되려면:

- **개인 시간 + 개인 장비**: 회사 시간/장비/계정으로 본 repo 작업 금지
- **회사 도메인 지식 분리**: 회사 코드·문서·confidential 정보를 본 repo 예제·문서에 *반영 금지*
- **회사가 본 도구 사용 시**: Apache 2.0 NOTICE 준수 + 회사 fork와 personal repo 명확히 분리
- **공개 contribution**: GitHub 활동을 *개인 GitHub 핸들* (@hibou04-ops)에서, 회사 핸들과 분리

---

## 🔐 GPG signing (선택, 더 강한 tamper-evidence)

**왜 선택**: 현재 annotated tag + GitHub timestamp witness만으로도 Schedule A 표준 사용엔 *충분*. GPG는 추가 강도이지 필수 아님.

**언제 할지**: GPG 키 설정 후, 시간 여유 있을 때.

**방법**:
```bash
# 0. GPG 키가 있다고 가정 (없으면 gpg --gen-key로 생성)
gpg --list-secret-keys --keyid-format LONG

# 1. git config에 키 등록
git config --local user.signingkey <YOUR_KEY_ID>
git config --local commit.gpgsign true

# 2. 각 repo에서 tag 재서명 (예: omegaprompt)
cd C:/Users/hibou/omegaprompt
git tag -d pre-employment-ip-snapshot-2026-04-29
git tag -s pre-employment-ip-snapshot-2026-04-29 \
  -m "Pre-existing IP snapshot for Schedule A. Author: Kyunghoon Gwak (곽경훈) <hibouaile04@gmail.com>."
git push origin pre-employment-ip-snapshot-2026-04-29 --force

# 다른 repo도 동일하게 (각 repo의 snapshot tag 날짜에 맞춰):
# C:/Users/hibou/omega-lock              → pre-employment-ip-snapshot-2026-04-28
# C:/Users/hibou/Antemortem              → pre-employment-ip-snapshot-2026-04-28
# C:/Users/hibou/antemortem-cli          → pre-employment-ip-snapshot-2026-04-28
# C:/Users/hibou/mini-omega-lock         → pre-employment-ip-snapshot-2026-04-29
# C:/Users/hibou/mini-antemortem-cli     → pre-employment-ip-snapshot-2026-04-29
```

**검증**: `git tag -v pre-employment-ip-snapshot-2026-04-29`

---

## ✅ 스냅샷 검증 (의심스러울 때)

```bash
# 각 repo에서 (snapshot 날짜는 repo별로 다름):
git -C C:/Users/hibou/omegaprompt             show pre-employment-ip-snapshot-2026-04-29 | head -20
git -C C:/Users/hibou/omega-lock              show pre-employment-ip-snapshot-2026-04-28 | head -20
git -C C:/Users/hibou/Antemortem              show pre-employment-ip-snapshot-2026-04-28 | head -20
git -C C:/Users/hibou/antemortem-cli          show pre-employment-ip-snapshot-2026-04-28 | head -20
git -C C:/Users/hibou/mini-omega-lock         show pre-employment-ip-snapshot-2026-04-29 | head -20
git -C C:/Users/hibou/mini-antemortem-cli     show pre-employment-ip-snapshot-2026-04-29 | head -20

# GitHub remote tag 검증 (gh CLI 필요):
gh api repos/hibou04-ops/omegaprompt/git/refs/tags/pre-employment-ip-snapshot-2026-04-29
gh api repos/hibou04-ops/omega-lock/git/refs/tags/pre-employment-ip-snapshot-2026-04-28
gh api repos/hibou04-ops/Antemortem/git/refs/tags/pre-employment-ip-snapshot-2026-04-28
gh api repos/hibou04-ops/antemortem-cli/git/refs/tags/pre-employment-ip-snapshot-2026-04-28
gh api repos/hibou04-ops/mini-omega-lock/git/refs/tags/pre-employment-ip-snapshot-2026-04-29
gh api repos/hibou04-ops/mini-antemortem-cli/git/refs/tags/pre-employment-ip-snapshot-2026-04-29
```

각 commit의 author email이 `hibouaile04@gmail.com`인지, 본명이 NOTICE/AUTHORS/PRE_EXISTING_IP.md에 박혀있는지 확인.

---

## 📝 이 체크리스트 자체의 갱신

- 새로운 repo 추가 시 → 위 6개 repo URL 목록 갱신
- 본명·이메일·핸들 변경 시 → AUTHORS.md, PRE_EXISTING_IP.md, NOTICE 모두 갱신
- 입사 또는 큰 계약 체결 시 → 본 체크리스트의 Step 1~3 완료 여부 기록
- 다른 repo로 IP 자산 확장 시 → 동일 패턴 (AUTHORS + PRE_EXISTING_IP + NOTICE + IP_DEFENSE_CHECKLIST) 복사

---

**This file is part of the IP-defense package alongside [AUTHORS.md](AUTHORS.md), [PRE_EXISTING_IP.md](PRE_EXISTING_IP.md), [NOTICE](NOTICE), and [LICENSE](LICENSE). Read all four together when reviewing the IP claim.**
