# Changelog

All notable changes to `mini-omega-lock` are documented here. This
project adheres to [Semantic Versioning](https://semver.org/).

## [0.7.0] - 2026-06-12

This release puts the package's headline value — the **judge noise
floor** — front and centre, adds CI-consumable output + threshold gates,
and makes the publish workflow fully version-agnostic. Everything is
**additive**: the frozen surface (`empirical_preflight` signature, the
three `omegaprompt.preflight.contracts` records it produces, the console
script names, the import name, and the `omegaprompt>=1.1.0` pin) is
unchanged.

### Added

- **Headline summary layer (`mini_omega_lock.summary`).** Three new
  public helpers, all exported in `__all__`:
  - `judge_noise_floor(judge_quality)` — the single load-bearing number,
    defined as `1 - consistency` (`0.0` = the judge never disagreed with
    itself). An A/B fitness delta smaller than this is below the judge's
    own noise and is not a real improvement.
  - `build_summary(judge_quality, endpoint, performance, warnings)` — a
    flat, JSON-serialisable, **byte-stable** CI dict (timing fields
    excluded) carrying a `schema_version` string (`mini-omega-lock/summary/v1`)
    and an `unmeasured_fields` list extracted from the warnings.
  - `render_scorecard(summary, fmt="md"|"html")` — a single-file
    preflight scorecard, **stdlib only**, deterministic (no timestamp),
    self-contained HTML (inline CSS, no external assets).
- **CLI machine summary + scorecard + threshold gates.**
  - `--summary` emits the flat `build_summary` JSON (distinct from the
    full `--json`/`--jsonl` dumps, which now also carry a `summary` key).
  - `--scorecard md|html` (+ `--scorecard-out PATH`) renders the
    scorecard to stdout or a file.
  - `--fail-over-noise-floor X`, `--fail-under-schema-reliability X`,
    `--fail-under-context-margin X` add a new exit code **3** when a
    *measured* value breaches the bound. A threshold breach takes
    precedence over the fail-closed unmeasured-field exit (2).
- **Version-agnostic publish workflow.** `publish.yml` now also triggers
  on a published GitHub Release, reads the version from `pyproject.toml`
  via `tomllib`, and asserts `__init__.__version__` matches and the tag
  equals `v<version>`. No version is hard-coded in workflow logic.
- **Dynamic PyPI shields.** README badges switched to
  `img.shields.io/pypi/v|pyversions|l/...` with `?cacheSeconds=3600`, so
  the version/python/license badges track releases automatically instead
  of being pinned in prose. `check_repo_consistency.py` accepts the
  dynamic shield form (and still validates a static badge if present).

### Changed

- **README family overhaul** (README, README_KR, EASY_README,
  EASY_README_KR) leads with the noise-floor value proposition, explains
  "noise floor" in plain language, frames standalone vs. omegaprompt use,
  and adds a "vs. just trust the eval delta" comparison + a README
  cross-link row.

### Maintenance

- pyproject `authors` set to `Kyunghoon Gwak <hibouaile04@gmail.com>`.
- Development Status remains `3 - Alpha` (the CLI/MCP surface is still
  expanding; `4 - Beta` waits for it to freeze).

## [0.6.1] - 2026-06-08

### Changed

- **Release-workflow hardening (CI only — no package change).** The
  `MINI_OMEGA_LOCK_RELEASE_WORKFLOW` env that tells `release_audit.py` to skip its
  pre-tag "tag already exists" check was set at the publish job level, broader than
  needed. It is now scoped to the Publish readiness gate step alone, so the
  deterministic-verification pytest step runs the tag guard at full strength. The
  built wheel/sdist are byte-identical to 0.6.0 (only the version string differs).

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
