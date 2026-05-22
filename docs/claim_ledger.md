# Claim ledger

Every non-trivial public claim about `mini-omega-lock` is listed here with its location, source-of-truth, verification command, and status marker. The ledger exists so that **a reader can mechanically check any line** in `README.md`, `EASY_README.md`, or `EASY_README_KR.md`.

If you add a claim to any public doc and do not add a row here, `scripts/check_repo_consistency.py` should fail on it (extend the checker, or remove the claim).

## Status markers

| Marker | Meaning |
|---|---|
| `generated` | The value is rendered by `scripts/generate_readme_claims.py` from a source file. Drift is detected by `--check`. |
| `source-backed` | The claim points at a specific file/line in `src/` or `tests/`. |
| `command-backed` | The claim is verifiable by running a specific shell command (printed alongside). |
| `artifact-backed` | The claim is verifiable by re-running a specific deterministic artifact (golden case, demo replay, fixture manifest). |
| `qualitative` | The claim is a category-level / boundary statement, intentionally not numerically pinned. |
| `not-claimed` | Listed explicitly so the absence is itself part of the contract. |

## Ledger

| # | Claim | Where | Source of truth | Verification command | Status |
|---|---|---|---|---|---|
| 1 | "PyPI distribution is `mini-omega-lock`" | README badges, install commands; EASY_READMEs | `pyproject.toml` `[project].name` | `python scripts/generate_readme_claims.py --check` | `generated` |
| 2 | Package version is `0.5.0` | README PyPI badge | `pyproject.toml` `[project].version` + `mini_omega_lock.__version__` | `python scripts/check_repo_consistency.py` | `generated` |
| 3 | Requires Python ≥ 3.11 | README badge | `pyproject.toml` `[project].requires-python` | `python scripts/generate_readme_claims.py --check` | `generated` |
| 4 | Depends on `omegaprompt>=1.1.0` | README parent badge | `pyproject.toml` `[project].dependencies` | `python scripts/check_repo_consistency.py` | `generated` |
| 5 | Public API names (`empirical_preflight`, `measure_judge_consistency`, …) | README/EASY_READMEs code blocks | `src/mini_omega_lock/__init__.py::__all__` | `python scripts/check_repo_consistency.py` | `source-backed` |
| 6 | MCP server exposes six tools | README, `mcp/__init__.py` docstring | `src/mini_omega_lock/mcp/server.py` `@mcp_app.tool()` decorators | `python scripts/generate_readme_claims.py --check` | `generated` |
| 7 | MCP optional extra is `mcp` | README, EASY_READMEs | `pyproject.toml` `[project.optional-dependencies]` | `python scripts/check_repo_consistency.py` | `generated` |
| 8 | MCP run command is `python -m mini_omega_lock.mcp` | README, EASY_READMEs | `src/mini_omega_lock/mcp/__main__.py` | `python scripts/check_repo_consistency.py` (forbids hyphenated variant) | `source-backed` |
| 9 | `empirical_preflight` returns a 4-tuple (warnings) | README "TL;DR", trust model | `tests/test_fail_closed_defaults.py::test_empirical_preflight_returns_4_tuple_not_3_tuple` | `python -m pytest -q tests/test_fail_closed_defaults.py -k 4_tuple` | `source-backed` |
| 10 | Unmeasured `schema_reliability` defaults to `0.0` with a warning | README, trust model | `src/mini_omega_lock/probes.py::empirical_preflight` + `tests/test_fail_closed_defaults.py::test_schema_reliability_*` | `python -m pytest -q tests/test_fail_closed_defaults.py` | `source-backed` |
| 11 | Failed probe latency excluded from `mean_call_latency_ms` | trust model | `tests/test_fail_closed_defaults.py::test_consistency_probe_failure_does_not_poison_latency_mean` | `python -m pytest -q -k consistency_probe_failure_does_not_poison` | `source-backed` |
| 12 | Default tests / default CI run entirely offline | README, trust model | `.github/workflows/ci.yml`; `tests/*` use `MagicMock` / scripted providers | `python -m pytest -q` (no `ANTHROPIC_API_KEY` set) | `source-backed` |
| 13 | Deterministic demo output is byte-for-byte stable | README, examples doc | `examples/_demo_output.txt`; `tests/test_demo_replay.py` | `python examples/demo_replay.py` then `python -m pytest -q tests/test_demo_replay.py` | `artifact-backed` |
| 14 | Golden cases cover the documented probe matrix | README, examples doc | `benchmarks/golden_cases/*.json`; `tests/test_golden_cases.py` | `python scripts/run_golden_cases.py --check` | `artifact-backed` |
| 15 | Golden-case fixtures haven't been tampered with | examples doc, trust model | `benchmarks/golden_cases/manifest.json` (SHA-256 per file) | `python scripts/verify_fixture_integrity.py` | `artifact-backed` |
| 16 | `compute_context_margin` is a heuristic, not tokenizer-exact | trust model | `src/mini_omega_lock/probes.py` lines 279–331 docstring | `grep -n "chars_per_token" src/mini_omega_lock/probes.py` | `source-backed` |
| 17 | `compute_context_margin` silently ignores any `token_counter` arg | trust model | `src/mini_omega_lock/probes.py` lines 309–318 inline comment | same as #16 | `source-backed` |
| 18 | MCP `compute_context_margin` tool does not accept `token_counter` | trust model | `src/mini_omega_lock/mcp/server.py` lines 359–395 (signature) | `grep -n "def compute_context_margin" src/mini_omega_lock/mcp/server.py` | `source-backed` |
| 19 | MCP rubric paths are workspace-bounded | trust model | `src/mini_omega_lock/mcp/server.py` `_workspace_root` + `tests/test_mcp_workspace_boundary.py` | `python -m pytest -q tests/test_mcp_workspace_boundary.py` (when `mcp` installed) | `source-backed` |
| 20 | Cross-platform support (Ubuntu + Windows) | README CI badge | `.github/workflows/ci.yml` matrix | view workflow run in Actions tab | `source-backed` |
| 21 | License is Apache 2.0; 0.1.0 was MIT | README "License history" | `LICENSE`, `NOTICE`, README license history block | `head LICENSE` | `source-backed` |
| 22 | No exact test count claimed in README prose | n/a (anti-claim) | `scripts/check_repo_consistency.py::check_readme_badges` forbids `tests-N` badge | `python scripts/check_repo_consistency.py` | `not-claimed` |
| 23 | No benchmark / leaderboard / model-quality score claimed | trust model "What it does NOT verify" | n/a | n/a | `not-claimed` |
| 24 | No production-adoption claim | toolkit positioning | n/a | n/a | `not-claimed` |
| 25 | No append-only audit trail / hash chain claim | examples doc (Fixture integrity section) | n/a | n/a | `not-claimed` |
| 26 | Empirical probes measure a narrow preflight surface only | README "How is this different?", trust model | trust model | qualitative | `qualitative` |
| 27 | This is not the analytical trap classifier | README, toolkit positioning | `mini-antemortem-cli` is the sibling for that | qualitative | `qualitative` |

## Adding a new claim

1. Add the claim to the relevant doc.
2. Add a row here with the right status marker.
3. If the status is `generated` or `command-backed`, extend `scripts/check_repo_consistency.py` (or `scripts/generate_readme_claims.py`) so the gate catches drift.
4. Run `python scripts/check_repo_consistency.py && python -m pytest -q`. Both must pass.

## Reverting a claim

If a claim cannot be backed by a deterministic artifact or command, **remove it** rather than leaving it un-ledgered. The release-audit script will treat any un-ledgered numeric/feature claim it finds in the README as a release blocker once the corresponding detection rule is added to `check_repo_consistency.py`.
