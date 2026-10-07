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
python -m pip install mini-omega-lock==0.7.1
preflight --help
python -c "from mini_omega_lock import compute_context_margin; print(compute_context_margin(system_prompt_chars=0, rubric_chars=0, longest_input_chars=380, longest_reference_chars=0, longest_response_chars=0, context_window_tokens=1000))"
```

The offline API example prints 0.9: a character-based context projection, not an exact tokenizer measurement or model-quality result. Full preflight CLI probes require the selected provider infrastructure. Unmeasured warnings give exit 2; threshold breaches give 3; usage/runtime errors give 1. Exit 0 means requested measurements ran, not that their values are acceptable.

omegaprompt>=1.1.0 is required and installed automatically; no calibration pipeline is needed to use the probes. The supported current combination is omegaprompt 2.1.2. Pack judge_quality, endpoint, performance and warnings into PreflightReport, then derive_adaptation_plan. The package is not the omega-lock search engine.

[Docking contracts and runnable data handoff](https://github.com/hibou04-ops/omega-lock/blob/main/DOCKING.md) · [Full guide](README.md).

MCP: install the distribution with `[mcp]` and use its existing server executable. FastMCP support is bounded to MCP SDK `>=1.0.0,<2.0.0`; the tool names and schemas are unchanged.


## The one-sentence pitch

**Your prompt-eval improvement might be smaller than your judge's own noise — and then it isn't a real improvement.** mini-omega-lock measures that noise before you trust an A/B result.

## What's the "noise floor"?

An LLM judge doesn't score the *same* answer the *same* way every time. Grade one fixed answer five times → five slightly different scores. That wobble is the judge's **noise floor**.

The rule: **if prompt B beats prompt A by less than that wobble, gather more evidence before accepting the win.** You'd ship B but you measured a coin flip. This tool gives you the floor number first, so you know whether your delta is real.

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

`judge_noise_floor` is `1 - consistency`. `0.0` = the judge never disagreed with itself. Bigger = you need a bigger A/B delta before a win is believable. Cost: ~5 cheap API calls.

## It also checks (same pass)

| Check | What it tells you |
|---|---|
| **Judge noise floor** | The headline: how much the judge disagrees with itself. |
| **Schema reliability** | Fraction of STRICT_SCHEMA calls that parse. `< 0.9` → fall back to JSON. Catches *silent* failures too. |
| **Context budget margin** | How close your biggest call is to the context limit. Negative = overflow. |
| **Wall-time projection** | How long a full run will take, before you start it. |

Any check it *couldn't* run **fails closed** (returns a safe-looking `0.0` but warns you). The `warnings` list tells "measured zero" apart from "never measured" — read it in CI.

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
