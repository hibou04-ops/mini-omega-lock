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
        project_performance,
        noise_floor_estimate,
        # headline summary + scorecard helpers
        judge_noise_floor,
        build_summary,
        render_scorecard,
    )

Separate package; not part of the main ``omegaprompt`` install. Install
alongside omegaprompt when you want to augment the preflight plugin
interface with real probe measurements::

    pip install omegaprompt mini-omega-lock

Runs entirely offline in tests (SDK clients mocked); production use
issues real provider calls through :class:`omegaprompt.providers.LLMProvider`.
"""

from mini_omega_lock.probes import (
    compute_context_margin,
    compute_context_margin_from_texts,
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

__version__ = "0.7.0"

__all__ = [
    "build_summary",
    "compute_context_margin",
    "compute_context_margin_from_texts",
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
