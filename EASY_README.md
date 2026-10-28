# mini-omega-lock — Easy Start

> The short version. Full doc: [README.md](README.md) · 한국어 Easy: [EASY_README_KR.md](EASY_README_KR.md)

```bash
pip install mini-omega-lock
```

## Start here · Standalone use · Integration/Docking

**Omega Aile** — Quiet precision. AI research guided by evidence.

Probe judge consistency, schema behavior, context margin and run projections before a calibration. This is a separately distributed measurement tool.

Requires Python 3.11+. Installation needs internet.

```bash
python -m pip install mini-omega-lock==0.8.0
preflight --help
python -c "from mini_omega_lock import compute_context_margin; print(compute_context_margin(system_prompt_chars=0, rubric_chars=0, longest_input_chars=380, longest_reference_chars=0, longest_response_chars=0, context_window_tokens=1000))"
```

The offline API example prints 0.9: a character-based context projection, not an exact tokenizer measurement or model-quality result. Full preflight CLI probes require the selected provider infrastructure. Unmeasured warnings give exit 2; threshold breaches give 3; usage/runtime errors give 1. Exit 0 means requested measurements ran, not that their values are acceptable.

omegaprompt>=1.1.0 is required and installed automatically; no calibration pipeline is needed to use the probes. The supported current combination is omegaprompt 2.1.2. Pack judge_quality, endpoint, performance and warnings into PreflightReport, then derive_adaptation_plan. The package is not the omega-lock search engine.

[Docking contracts and runnable data handoff](https://github.com/hibou04-ops/omega-lock/blob/main/DOCKING.md) · [Full guide](README.md).

MCP: install the distribution with `[mcp]` and use its existing server executable. FastMCP support is bounded to MCP SDK `>=1.0.0,<2.0.0`; the tool names and schemas are unchanged.


## The one-sentence pitch

**Measure how repeated judge scores vary before interpreting evaluation results.** mini-omega-lock reports variability and measurement coverage.

## What's the "noise floor"?

An LLM judge doesn't score the *same* answer the *same* way every time. Grade one fixed answer five times → five slightly different scores. That wobble is the judge's **noise floor**.

The repeated-item CV is relative variability. Aggregate-fitness standard deviation has fitness units. An A/B comparison needs paired observations, uncertainty, and a decision rule; this tool does not supply that test.

## 30-second use

```bash
# No Python needed — one CI-friendly number:
preflight --provider anthropic --rubric rubric.json \
          --probe-item item.json --probe-response "4" --summary
# -> {"judge_noise_floor": 0.07, "schema_reliability": 0.0, ...}
```

```python
from mini_omega_lock import empirical_preflight, judge_noise_floor
# ... build a judge + rubric + probe item (see README.md quick start) ...
judge_quality, endpoint, performance, warnings = empirical_preflight(
    judge=judge, rubric=rubric, probe_item=probe,
    probe_response="4", consistency_repeats=5,
)
print(judge_noise_floor(judge_quality))   # e.g. 0.07
```

`judge_noise_floor` is clipped relative CV (`1 - consistency`), not an absolute A/B effect threshold. Default shared judge/gate measurement uses 5 actual observations; configured extra probes and provider pricing determine total cost.

## It also checks (same pass)

| Check | What it tells you |
|---|---|
| **Judge noise floor** | The headline: how much the judge disagrees with itself. |
| **Schema reliability** | Fraction of STRICT_SCHEMA calls that parse. `< 0.9` → fall back to JSON. Catches *silent* failures too. |
| **Context budget margin** | How close your biggest call is to the context limit. Negative = overflow. |
| **Wall-time projection** | How long a full run will take, before you start it. |

Unmeasured numeric fields use fail-closed defaults. Read `warnings.measurement_status` first and preserve `probe_accounting`; warning-string inference is a legacy fallback, not proof of historical measurement coverage.

## Works with omegaprompt — or alone

- **Alone:** the noise-floor + schema-reliability numbers are useful on their own. Run `preflight`, gate your CI on the result.
- **With [omegaprompt](https://pypi.org/project/omegaprompt/):** the records it emits feed omegaprompt's `derive_adaptation_plan`, which auto-tunes calibration thresholds to your infra. mini-omega-lock is the probe; omegaprompt is the engine it feeds. (Installing this pulls omegaprompt in — it's a hard dependency.)

## CLI extras for CI

```bash
preflight ... --scorecard html --scorecard-out preflight.html   # a PR artifact
preflight ... --fail-over-noise-floor 0.10                       # fail the build if too noisy
preflight ... --fail-under-schema-reliability 0.90              # fail if endpoint flaky
```

Exit codes: `0` good · `2` something couldn't be measured · `3` a value breached a `--fail-*` bound · `1` usage error.

## When to skip it

- Stock frontier providers on known-stable tiers — defaults are fine.
- Rapid iteration (it adds ~10s per run).
- Tests / CI with no API access (omegaprompt runs fine on declared defaults).

## Go deeper

- Full README: [README.md](README.md)
- Contract definitions: `omegaprompt.preflight.contracts`
- Analytical, zero-API sibling: [mini-antemortem-cli](https://pypi.org/project/mini-antemortem-cli/)

License: Apache 2.0. Copyright (c) 2026 Kyunghoon Gwak.

## 0.8.0: 실제 관측 공유와 측정 상태

- 같은 `(rubric, item, response)`의 consistency와 gate flip은 실제 judge 관측 배치를 공유합니다. 기본 3+5회가 5회로 줄며 각 지표는 요청한 3개·5개 prefix만 사용합니다. 독립 표본 수를 합산하지 않습니다. 호출 순서가 바뀌므로 stateful judge의 수치가 달라질 수 있습니다.
- 기존 4-tuple과 warnings list 동작을 유지합니다. 반환 warnings의 `measurement_status`와 `probe_accounting`을 함께 저장하세요. CLI/MCP JSON도 두 필드를 제공합니다. 요약은 상태를 우선 읽고 구형 일반 list에는 경고 문자열 호환 읽기를 사용합니다.
- 상태는 `measured`, `unmeasured`, `insufficient_samples`, `failed`, `estimated`, `not_applicable`입니다. 1회 채점은 변동 측정에 부족합니다. 실패한 호출 시간도 accounting에 포함하고, 성공 호출 latency projection과 구분합니다. provider 내부 재시도·실패 토큰 비용은 관측할 수 없으면 `null`/unknown으로 남깁니다.
- `judge_noise_floor`는 호환 이름이며 값은 clipped CV입니다. 새 별칭 `judge_relative_variability`도 같은 값입니다. `fitness_noise_floor`는 aggregate fitness의 표준편차입니다. 둘 다 임의 A/B 개선의 유의성을 판정하지 않습니다.
- CLI: 정상 실행 0은 지정된 측정 완료를 뜻합니다. 미측정·실패·표본 부족·추정은 2, **측정한** 값의 사용자 threshold 위반은 3, 잘못된 입력은 1입니다. threshold 없는 성공을 judge 품질 통과로 해석하지 마세요.

[전후 근거·호환성·재현 명령](docs/upgrade-0.8.0.md). 유료 provider 검증은 수행하지 않았습니다.
