# mini-omega-lock — Easy Start

> The short version. Full doc: [README.md](README.md) · 한국어 Easy: [EASY_README_KR.md](EASY_README_KR.md)

```bash
pip install mini-omega-lock
```

## The one-sentence pitch

**Your prompt-eval improvement might be smaller than your judge's own noise — and then it isn't a real improvement.** mini-omega-lock measures that noise before you trust an A/B result.

## What's the "noise floor"?

An LLM judge doesn't score the *same* answer the *same* way every time. Grade one fixed answer five times → five slightly different scores. That wobble is the judge's **noise floor**.

The rule: **if prompt B beats prompt A by less than that wobble, your "win" is noise.** You'd ship B but you measured a coin flip. This tool gives you the floor number first, so you know whether your delta is real.

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
