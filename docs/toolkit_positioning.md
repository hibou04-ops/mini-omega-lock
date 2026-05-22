# Toolkit positioning

The `omegaprompt` toolkit is a small set of related repositories that share interfaces but solve different sub-problems. This document is the canonical "what each tool does, and what it does *not* do" reference. Anything outside the boundaries below is not part of `mini-omega-lock`'s scope and should be requested in the relevant sibling repository instead.

Claims here are **category-level** and intentionally do not reproduce feature inventories from sibling repos — only their owners can keep those up to date. Cross-reference via the official PyPI/GitHub URLs below.

## At a glance

| Package | Role | Live API calls? | Default mode |
|---|---|---|---|
| [`omegaprompt`](https://pypi.org/project/omegaprompt/) | Calibration engine; defines the preflight plugin contracts. | yes (when calibrating) | core library |
| [`mini-omega-lock`](https://pypi.org/project/mini-omega-lock/) (this repo) | Empirical preflight probes feeding `derive_adaptation_plan`. | yes (production); no (default tests/CI). | Python package + MCP server |
| [`mini-antemortem-cli`](https://pypi.org/project/mini-antemortem-cli/) | Analytical preflight: deterministic rule-based trap classifier. | no | CLI + library |
| [`omega-lock`](https://github.com/hibou04-ops/omega-lock) | Broader parameter-calibration / audit framework (sensitivity, walk-forward, KC-4). | varies | framework |
| [`antemortem-cli`](https://github.com/hibou04-ops/antemortem-cli) | Pre-implementation recon CLI (reads docs/prior art before writing). | varies | CLI |
| [`Antemortem`](https://github.com/hibou04-ops/Antemortem) | Methodology / trap-spectrum reference. | n/a | docs |

## Where `mini-omega-lock` sits

`omegaprompt` exposes a plugin interface for preflight probes (`omegaprompt.preflight.contracts` + `omegaprompt.preflight.adaptation`) but ships no probe code. Two siblings fill that gap:

- **`mini-omega-lock`** (this repo) provides *empirical* probes — they make small LLM calls (judge consistency, schema reliability) and compute deterministic metrics (context margin, noise floor) from runtime inputs.
- **`mini-antemortem-cli`** provides *analytical* probes — deterministic rule-based classification over configuration *before* any LLM call is made.

Both emit `omegaprompt.preflight.contracts.PreflightReport`-compatible records. You can run them side by side and feed both reports into `derive_adaptation_plan`. The choice between them is not exclusive — it is the same axis as "smoke test" vs "static analysis".

## What `mini-omega-lock` is **not**

- **Not the calibration engine.** `omegaprompt` owns the calibration loop, judge scaffolding, dataset abstraction, and adaptation policy. This package only feeds its preflight inputs.
- **Not the analytical preflight.** Use `mini-antemortem-cli` for deterministic, no-API rule classification of configs. `mini-omega-lock` does *empirical* probes; it does not classify a configuration as e.g. "trap: ambiguous rubric".
- **Not a general agent framework.** The MCP server here exposes six tools backed 1:1 by the empirical-preflight probes. It does not provide chat, planning, RAG, or any non-preflight surface.
- **Not a benchmark.** No model is ranked, no leaderboard is published, no aggregate score across providers is claimed.
- **Not a dashboard or SaaS.** The package emits Python objects and (optionally) MCP responses. There is no hosted UI.
- **Not a CLI for end users.** The only console script is the MCP server (`mini-omega-lock-mcp`). There is no `mini-omega-lock` user-facing CLI; the package is consumed from Python or via MCP. The `scripts/*.py` files are repo-maintenance scripts, not user tools.

## Choosing the right tool

| You want to … | Use |
|---|---|
| Adapt omegaprompt's thresholds to your actual environment | `mini-omega-lock` |
| Catch configuration traps before running calibration | `mini-antemortem-cli` |
| Run a full calibration | `omegaprompt` |
| Audit a calibration run, sensitivity / walk-forward analysis | `omega-lock` |
| Pre-implementation recon before writing code or specs | `antemortem-cli` |
| Read the methodology / trap-spectrum reference | `Antemortem` |
| Expose preflight probes to an agent over MCP | `mini-omega-lock[mcp]` |

## Stability and compatibility

- `mini-omega-lock` is at PyPI Development Status `3 - Alpha`. The public API (`__all__` in `mini_omega_lock/__init__.py`) is the only stable surface; everything in `mini_omega_lock.probes` is also stable but private helpers may change.
- The 0.4.0 release changed `empirical_preflight` from a 3-tuple to a 4-tuple (adds `warnings`). Pre-0.4 callers must update their unpacking — see `tests/test_fail_closed_defaults.py::test_empirical_preflight_returns_4_tuple_not_3_tuple`.
- The minimum `omegaprompt` pin is the one in `pyproject.toml` (regenerated into `docs/generated/claims.md`). Older `omegaprompt` versions may lack the contracts this package imports.

## Cross-toolkit cookbook

For end-to-end scenarios that span multiple toolkit packages (e.g. preflight → calibration → audit), see [AGENT_TRIGGERS.md](https://github.com/hibou04-ops/omegaprompt/blob/main/AGENT_TRIGGERS.md) in the parent `omegaprompt` repository.
