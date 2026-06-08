# Changelog

All notable changes to `mini-omega-lock` are documented here. This
project adheres to [Semantic Versioning](https://semver.org/).

## [0.6.0] - 2026-06-08

This release adds the missing release infrastructure, surfaces a silent
endpoint-degradation signal, ships a shell/CI entry point, fixes a broken
doc citation, and completes the MCP tool surface. It deliberately stays
`Development Status :: 3 - Alpha` (see "Held at Alpha" below).

### Added

- **Release infrastructure (`publish.yml`, C1).** Trusted-publishing
  GitHub Actions workflow. A `verify-build` job (tag regex gate, checkout
  at tag with `persist-credentials: false`, install `.[dev,mcp]`,
  tag-vs-version verification against both `pyproject.toml` and
  `mini_omega_lock.__version__`, the full deterministic gauntlet,
  `python -m build`, wheel smoke install, no-network publish-readiness
  gate, artifact upload) feeds a `publish` job (`environment: pypi`,
  `id-token: write`, `pypa/gh-action-pypi-publish@release/v1`).
- **Silent-degradation signal (C2).** `probe_strict_schema` now counts
  strict-schema probes that return `parsed=None` *without* raising a
  `ProviderError` and sets `EndpointMeasurement.silent_degradation_detected
  = True` when any occur. `empirical_preflight` emits a warning on that
  signal; the fail-closed/unprobed path keeps the field `False` but warns
  that degradation was *not probed* (so `False` is never misread as
  "measured: clean"). The downstream consumer
  (`omegaprompt.preflight.adaptation`) already reads this field — no
  contract change.
- **`preflight` CLI (H1).** A `preflight` console script wraps
  `empirical_preflight()` + `derive_adaptation_plan()`. Flags:
  `--provider/--model/--base-url`, `--rubric` (path or inline JSON),
  `--probe-item`, `--probe-response`, `--consistency-repeats`,
  `--context-window`, `--token-counter`, `--fitness-samples`. Output modes
  `--json` / `--jsonl` / `--text`. Exit code is non-zero when any field
  fell back to a fail-closed default (unmeasured-field signals), mirroring
  the library's fail-closed CI semantics. An unavailable `--token-counter`
  raises rather than silently using the chars/token heuristic. The CLI
  never rewrites library warning strings (the byte-locked
  `examples/_demo_output.txt` baseline is unaffected); a CLI-specific
  golden lives at `examples/_cli_demo_output.json`.
- **Complete MCP surface (H2).** Four new MCP tools —
  `measure_scale_monotonicity`, `probe_strict_schema`,
  `compute_context_margin_from_texts`, and a `derive_adaptation_plan`
  wrapper — bringing the registered tool count from 6 to 10. The
  `empirical_preflight` MCP tool gains four params: `monotonic_examples`,
  `token_counter`, `system_prompts`, `gate_flip_repeats`. MCP tokenizer
  dispatch fails loud: an unavailable tokenizer raises, never silently
  falling back to the heuristic.

### Fixed

- **Doc-citation (M5).** `probes.py` cited a non-existent
  `omega_lock.preflight` API. Corrected to reference omega-lock (the
  parameter-calibration framework), a level that actually exists. A
  claim-ledger row and a `check_repo_consistency.py` grep now assert no
  `omega_lock.preflight` string remains.

### Held at Alpha (not Beta)

`Development Status` stays `3 - Alpha`. This release *expands* the surface
(4 new MCP tools, a new CLI, 4 new params) and changes the
`EXPECTED_TOOLS` count contract — declaring a frozen-API Beta in the same
release would be incoherent. `4 - Beta` is the explicit goal of the next
release, once the CLI/MCP surface freezes and ships cleanly through the new
`publish.yml`.
