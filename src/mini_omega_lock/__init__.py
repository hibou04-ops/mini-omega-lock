# SPDX-License-Identifier: Apache-2.0
"""mini-omega-lock - empirical preflight probes for omegaprompt calibration.

Issues small probe calls to measure judge consistency, endpoint schema
reliability, context-budget margin, latency, and noise floor. Emits
:class:`omegaprompt.preflight.PreflightReport`-compatible records that
feed :func:`omegaprompt.preflight.derive_adaptation_plan`.

Public API (see ``__all__`` for the full list; ``docs/generated/claims.md``
keeps a regenerated copy in sync with this module)::

    from mini_omega_lock import (
        # composite entry point
        empirical_preflight,
        # judge-quality probes
        measure_judge_consistency,
        measure_gate_flip_rate,
        measure_scale_monotonicity,
        # endpoint reliability
        probe_strict_schema,
        # context-budget probes (chars heuristic + tokenizer-exact)
        compute_context_margin,
        compute_context_margin_from_texts,
        # performance / noise
        compute_empirical_noise_ceiling,
    compute_minimum_detectable_effect,
        project_performance,
        noise_floor_estimate,
        # headline summary + scorecard helpers
        judge_noise_floor,
        build_summary,
        render_scorecard,
    )

The base package requires Pydantic only. Local contracts and fake-provider
probes work without omegaprompt or provider SDKs. For explicit parent
integration install the optional bridge extra and convert records::

    pip install "mini-omega-lock[bridge]"

Runs entirely offline in tests (SDK clients mocked); production callers
install their selected SDK separately. See mini_omega_lock.bridge for
parent provider and record conversion boundaries.
"""

from mini_omega_lock.probes import (
    compute_context_margin,
    compute_context_margin_from_texts,
    compute_empirical_noise_ceiling,
    compute_minimum_detectable_effect,
    empirical_preflight,
    measure_gate_flip_rate,
    measure_judge_consistency,
    measure_scale_monotonicity,
    noise_floor_estimate,
    probe_strict_schema,
    project_performance,
)
from mini_omega_lock.summary import (
    build_summary,
    judge_noise_floor,
    render_scorecard,
)

__version__ = "0.8.7"

__all__ = [
    "build_summary",
    "compute_context_margin",
    "compute_context_margin_from_texts",
    "compute_empirical_noise_ceiling",
    "compute_minimum_detectable_effect",
    "empirical_preflight",
    "judge_noise_floor",
    "measure_gate_flip_rate",
    "measure_judge_consistency",
    "measure_scale_monotonicity",
    "noise_floor_estimate",
    "probe_strict_schema",
    "project_performance",
    "render_scorecard",
    "__version__",
]
