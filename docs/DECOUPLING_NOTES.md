# Decoupling notes (omegaprompt) — analysis only, NOT implemented

> **Status: deliberately not implemented.** Making `omegaprompt` optional
> is out of scope for 0.7.0 and carries real risk. This file records what
> a thin standalone path *would* look like so the decision is explicit and
> reversible, not so it ships now.

## Why the coupling is deep

`mini-omega-lock` does not merely emit omegaprompt-shaped records; it
imports omegaprompt symbols across nearly every module:

- `src/mini_omega_lock/probes.py` imports `DatasetItem`, the
  `OutputBudgetBucket` / `ReasoningProfile` / `ResponseSchemaMode` enums,
  `JudgeResult` / `JudgeRubric`, `LLMJudge`, the three
  `preflight.contracts` records, and `LLMProvider` / `ProviderError` /
  `ProviderRequest`.
- `src/mini_omega_lock/cli.py` resolves rubrics/items via
  `JudgeRubric` / `DatasetItem`, builds a judge via `make_provider` +
  `LLMJudge`, and round-trips through `PreflightReport` +
  `derive_adaptation_plan`.
- `src/mini_omega_lock/mcp/server.py` imports the same surface plus
  `make_provider`.

The genuinely standalone-capable surface is small and already present:

- `mini_omega_lock.summary` (`judge_noise_floor`, `build_summary`,
  `render_scorecard`) is **pure** — it reads dicts / Pydantic dumps and
  has zero omegaprompt imports. It already runs without omegaprompt.
- `compute_context_margin` / `compute_context_margin_from_texts` are pure
  arithmetic over char/token counts.
- `noise_floor_estimate` is `statistics.pstdev` over caller-supplied
  floats.

Everything else (`measure_judge_consistency`, `measure_gate_flip_rate`,
`probe_strict_schema`, `empirical_preflight`, the CLI, the MCP server)
needs a real `LLMJudge` / `LLMProvider`, which are omegaprompt types.

## What a thin standalone path would look like (if ever wanted)

1. **Move the omegaprompt imports in `probes.py` to module-edge,
   import-time-optional shims.** Wrap the contract-record imports in a
   `try/except ImportError` that falls back to local, structurally
   identical Pydantic models with the *same field names and defaults*.
   The records `empirical_preflight` returns are the frozen surface; a
   standalone fallback must construct byte-identical `model_dump()`
   output or downstream `derive_adaptation_plan` consumers break.
2. **Define a minimal `Judge`/`Provider` Protocol** (`score(...)`,
   `call(...)`, `capabilities()`) and type the probe functions against
   the Protocol instead of the concrete omegaprompt classes. The tests
   already use duck-typed scripted fakes, so the Protocol is essentially
   "whatever the fakes implement".
3. **Split the dependency into an extra:** make `omegaprompt` an optional
   `[full]` extra and keep only `pydantic` as a hard dep. `pip install
   mini-omega-lock` would then give the pure summary/context/noise-floor
   surface; `pip install "mini-omega-lock[full]"` would add the probe +
   CLI + MCP + `derive_adaptation_plan` path.
4. **CI matrix would need a "no-omegaprompt" leg** to prove the pure
   surface imports and the fail-loud message fires when a probe needing
   omegaprompt is called without it installed.

## Why NOT to do it now

- **Frozen-surface risk.** The whole point of `empirical_preflight` is to
  hand records to omegaprompt's `derive_adaptation_plan`. A fallback
  record class that drifts by one field/default silently corrupts that
  contract — exactly the false-safe this package exists to prevent.
- **Negative user value.** The realistic user installs both packages
  anyway (the probes only make sense feeding the calibration engine). The
  standalone-pure subset (summary + context + noise-floor math) is
  already usable today *with* omegaprompt installed; carving it out adds
  packaging surface for little gain.
- **The pin is already permissive.** `omegaprompt>=1.1.0` has no upper
  bound; omegaprompt 2.x resolves fine. There is no version-conflict pain
  to solve.

Revisit only if a concrete user needs the noise-floor/scorecard surface
in an environment where omegaprompt genuinely cannot be installed.
