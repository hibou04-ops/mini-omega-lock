# mini-omega-lock

[English](README.md) · [한국어](README.ko.md) · [English easy](EASY_README.md) · [한국어 easy](EASY_README_KR.md)

Empirical preflight for repeated judge variability and missing measurements before interpreting evaluation results. It does not replace independent hold-out evaluation or an A/B significance test.

[![CI](https://github.com/hibou04-ops/mini-omega-lock/actions/workflows/ci.yml/badge.svg)](https://github.com/hibou04-ops/mini-omega-lock/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/mini-omega-lock.svg)](https://pypi.org/project/mini-omega-lock/)

<!-- QUICKSTART_DEMO_START -->
## 10-second start: install and inspect an offline gate

```bash
pip install mini-omega-lock
uvx --from mini-omega-lock preflight --help
```

The executable is `preflight`. The replay validates input rejection and an empirical absolute-noise ceiling; it is not an A/B significance test.

After installation, run the demo from a clone of this repository. The diff block is the demo's actual stdout.

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

## 0.8.7 — Documentation and package metadata

This documentation and packaging patch aligns the package description with the reviewed, domain-neutral source documentation. Public APIs, probe behavior and frozen fixtures are unchanged. It adds no new performance or generalization evidence.

## 0.8.6 — Verified tag-context CI audit

The sole required dependency is `pydantic>=2.6.0`. Necessary contracts, provider boundaries and judge code are included under internal `_vendor`, allowing core imports, CLI and fake-provider demos without omegaprompt, omega-lock, NumPy or provider SDKs. SDKs load lazily when a live provider is selected. `omegaprompt>=1.1.0` is confined to optional extra `[bridge]`.

Requires Python 3.11+. This checkout has source version **0.8.7**. The commands below install the checkout. The previous [0.8.4 is published on PyPI](https://pypi.org/project/mini-omega-lock/0.8.4/). Check version-specific [0.8.7 PyPI files](https://pypi.org/project/mini-omega-lock/0.8.7/) and [Actions](https://github.com/hibou04-ops/mini-omega-lock/actions) separately; source metadata alone does not establish publication.

On tag CI, `scripts/ci_release_audit.py` requires matching package/runtime versions and resolves the actual Git tag to the checked-out HEAD before setting the release-mode flag for the audit child only. Main and pull-request CI retain the pre-tag guard. Every audit step and the other release-marker checks still run.

```bash
python -m pip install .
preflight --help
python examples/demo_replay.py
python examples/cli_demo_replay.py
```

The fixture demos above run without API keys, live SDKs or network access. Installation may download dependencies. Live probes separately require the selected SDK, provider configuration and credentials.

## compute_empirical_noise_ceiling

```python
from mini_omega_lock import (
    compute_empirical_noise_ceiling,
    compute_minimum_detectable_effect,
)

assert compute_minimum_detectable_effect is compute_empirical_noise_ceiling
assert compute_empirical_noise_ceiling([-0.1, 0.1]) == 0.1
```

The canonical API is `compute_empirical_noise_ceiling(paired_deltas, confidence_z=1.96)`, exposed from both the package root and `mini_omega_lock.probes`. The legacy `compute_minimum_detectable_effect` name is a backward-compatible alias to the same callable in both modules.

```text
magnitudes = abs(paired_deltas)
ceiling = mean(magnitudes) + 1.96 * pstdev(magnitudes) / sqrt(n)
```

Default `confidence_z` is 1.96 and may be changed to a finite nonnegative value. `pstdev` is population standard deviation with denominator n. Empty samples, NaN/Inf observations and negative/nonfinite z are rejected; a singleton returns its absolute delta. This statistic is an empirical absolute-noise ceiling for the supplied repeated observations. It does not establish a sampling design, power, a distribution-free confidence interval or an A/B minimum detectable effect.

## Measurement states and accounting

`empirical_preflight()` returns `(judge_quality, endpoint, performance, warnings)`. Use local contracts from `mini_omega_lock.contracts`, providers from `mini_omega_lock.providers` and the judge from `mini_omega_lock.judges`.

Read `warnings.measurement_status` first and persist `probe_accounting`. States are `measured`, `unmeasured`, `insufficient_samples`, `failed`, `estimated`, `not_applicable`. The existing 4-tuple and warnings-list behavior remain. Human warnings are diagnostics; legacy substring fallback without structured states does not verify historical measurement coverage.

`judge_noise_floor` is clipped CV (`1 - consistency`); `judge_relative_variability` aliases the same value. `fitness_noise_floor` is the standard deviation of aggregate fitness. Relative CV cannot be compared directly with an absolute A/B score delta. Consistency and gate-flip share observations for the same `(rubric,item,response)`, with each metric using its requested prefix. The default batch uses 5 actual observations; additional probes add calls.

Accounting includes failed-call time separately from successful-call latency projection. Unobservable provider-internal retries and failed-token costs remain unknown/null. Suggested schema fallback is advisory and does not prove runtime consumption.

## CLI and optional integration

CLI exit codes: 0 means requested measurements completed; 2 indicates unmeasured, failed, insufficient or estimated states; 3 indicates a user threshold breach on a measured value; 1 indicates input/runtime errors. Exit 0 without thresholds is not judge-quality acceptance or deployment authorization.

```bash
# Live example: requires the selected provider SDK and credentials.
preflight --provider anthropic --rubric rubric.json \
  --probe-item item.json --probe-response "4" --summary

python -m pip install ".[mcp]"
mini-omega-lock-mcp
```

Supported MCP SDK range is `>=1.0.0,<2.0.0`; 2.x runtime behavior is unverified. Install `[bridge]` for parent integration. Local `PreflightReport` and adaptation work without the parent. Convert reports with `mini_omega_lock.bridge.to_omegaprompt_report(report)`; wrap an existing parent provider with `adapt_omegaprompt_provider(provider)` before passing it to the local `LLMJudge`. Model classes are not assumed to share identity.

## Local verification and limits

```bash
python -m pytest
python scripts/generate_readme_claims.py --check
python scripts/check_repo_consistency.py
```

Local contracts and fake-provider reproducibility do not establish external OOS utility, live-judge quality, load stability or production readiness. External-provider validation is not claimed. An independent OOS comparison must separately declare sampling units, splits, repeated-measurement correlation, uncertainty and decision rules.

## Optional bridge contract checks

Tests compare field and validation schemas plus Enum values between vendored models and the actual installed `omegaprompt`, then roundtrip JSON in both directions. Invalid inputs must retain matching error types and locations. These checks make no live provider calls.

```bash
python -m pip install ".[dev,mcp,bridge]"
python -m pytest -m bridge tests/test_bridge_contracts.py
```

Only an absent parent skips this optional integration file. Broken imports or changed contracts in an installed parent fail. Standalone core tests still run without the parent; required dependencies are unchanged.

`ProviderRequest.output_schema` is a Python class, so JSON does not transmit its class identity. A concrete `ProviderResponse.parsed` type must be restored through an explicit schema. Tests exercise the actual provider bridge, user schemas, degradation fields and original exception causes. `ProviderError` and `JudgeError` are distinct `RuntimeError` subclasses, not JSON models.

## Evidence and documentation

- Generated claims: [English](docs/generated/claims.md) / [한국어](docs/generated/claims_kr.md)
- [Trust model](docs/trust_model.md) · [Claim ledger](docs/claim_ledger.md)
- [Vendored source and maintenance](VENDORED.md) · [Changelog](CHANGELOG.md)
- [0.8.0 measurement-contract migration](docs/upgrade-0.8.0.md)

[README.ko.md](README.ko.md) is the canonical Korean document; [README_KR.md](README_KR.md) is an identical compatibility copy.

Apache 2.0. [LICENSE](LICENSE) · [NOTICE](NOTICE).
