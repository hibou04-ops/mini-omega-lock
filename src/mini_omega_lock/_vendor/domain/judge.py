# SPDX-License-Identifier: Apache-2.0
# Vendored from hibou04-ops/omegaprompt; see VENDORED.md.
"""Judge rubric + structured result.

v1.0 keeps the rubric shape identical to v0.2 for user continuity - the
``dimensions`` / ``hard_gates`` contract is well-understood and rewriting
it provides no leverage. The judge implementation layer (rule vs LLM vs
ensemble) is where v1.0 adds new capability.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Dimension(BaseModel):
    """One scoring axis in a judge rubric."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    description: str = Field(
        ...,
        min_length=1,
        description="What this dimension measures; fed verbatim to the judge prompt.",
    )
    weight: float = Field(..., ge=0.0)
    scale: tuple[int, int] = Field(
        default=(1, 5),
        description="(min, max) inclusive integer scale the judge must use.",
    )

    @field_validator("scale")
    @classmethod
    def _scale_valid(cls, v: tuple[int, int]) -> tuple[int, int]:
        lo, hi = v
        if hi <= lo:
            raise ValueError(f"scale upper bound ({hi}) must exceed lower ({lo}).")
        return v


class HardGate(BaseModel):
    """A binary pass/fail predicate.

    Fail on any gate collapses the item's final score to zero, preserving
    the ``hard_gate × soft_score`` fitness contract from v0.2.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    evaluator: Literal["judge", "rule", "post"] = Field(
        default="judge",
        description=(
            "Which layer evaluates this gate. 'judge' = LLM-as-judge returns "
            "a boolean. 'rule' = deterministic regex/schema check run by "
            "RuleJudge. 'post' = a Python callable attached at runtime."
        ),
    )


class JudgeRubric(BaseModel):
    """The complete judge specification: dimensions + gates."""

    model_config = ConfigDict(extra="forbid")

    dimensions: list[Dimension] = Field(..., min_length=1)
    hard_gates: list[HardGate] = Field(default_factory=list)

    @field_validator("dimensions")
    @classmethod
    def _unique_dimension_names(cls, v: list[Dimension]) -> list[Dimension]:
        names = [d.name for d in v]
        if len(set(names)) != len(names):
            dupes = sorted({n for n in names if names.count(n) > 1})
            raise ValueError(f"dimensions must have unique names; duplicates: {dupes}")
        if sum(d.weight for d in v) <= 0:
            raise ValueError("at least one dimension must have weight > 0.")
        return v

    @field_validator("hard_gates")
    @classmethod
    def _unique_gate_names(cls, v: list[HardGate]) -> list[HardGate]:
        names = [g.name for g in v]
        if len(set(names)) != len(names):
            dupes = sorted({n for n in names if names.count(n) > 1})
            raise ValueError(f"hard_gates must have unique names; duplicates: {dupes}")
        return v

    @classmethod
    def from_json(cls, path: str | Path) -> JudgeRubric:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Rubric file not found: {p}")
        payload = json.loads(p.read_text(encoding="utf-8"))
        return cls.model_validate(payload)

    def normalized_weights(self) -> dict[str, float]:
        total = sum(d.weight for d in self.dimensions)
        return {d.name: d.weight / total for d in self.dimensions}


class HardGateFlags(BaseModel):
    """Canonical per-gate flag bundle.

    Used in ``JudgeResult.gate_results`` when a rubric is not in scope,
    and by :class:`mini_omega_lock._vendor.judges.rule_judge.RuleJudge` when it
    returns a partial result without an LLM call.
    """

    model_config = ConfigDict(extra="forbid")

    no_refusal: bool = True
    format_valid: bool = True
    no_safety_violation: bool = True


class JudgeResult(BaseModel):
    """The judge's structured response for a single dataset item."""

    model_config = ConfigDict(extra="forbid")

    scores: dict[str, int] = Field(
        ...,
        description="Per-dimension scores; keys must match rubric dimension names.",
    )
    gate_results: dict[str, bool] = Field(
        default_factory=dict,
        description="Per-gate boolean outcomes; keys must match rubric hard_gate names.",
    )
    notes: str = Field(
        default="",
        description="Judge's free-form justification. Not used in scoring.",
    )

    def weighted_score(self, rubric: JudgeRubric) -> float:
        weights = rubric.normalized_weights()
        dim_by_name = {d.name: d for d in rubric.dimensions}
        total = 0.0
        for name, raw in self.scores.items():
            if name not in dim_by_name:
                continue
            dim = dim_by_name[name]
            lo, hi = dim.scale
            if raw < lo or raw > hi:
                raw = max(lo, min(hi, raw))
            normalized = (raw - lo) / (hi - lo)
            total += weights.get(name, 0.0) * normalized
        return total

    def any_gate_failed(self) -> bool:
        return any(result is False for result in self.gate_results.values())
