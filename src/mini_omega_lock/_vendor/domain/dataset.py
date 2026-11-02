# SPDX-License-Identifier: Apache-2.0
# Vendored from hibou04-ops/omegaprompt; see VENDORED.md.
"""Dataset contract.

A dataset is a list of items, each with a stable ``id``, an ``input`` the
target model sees, an optional ``reference`` the judge may consult, and
free-form ``metadata``. The file format is JSON Lines: one item per line.

v1.0 change: ``input`` is still a string (most prompt calibrations are
text-in / text-out), but ``metadata`` gains a conventional ``modality`` key
that reporters and rule-judges may consult (``text`` / ``code`` / ``tool_call``).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class DatasetItem(BaseModel):
    """A single calibration example."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(..., min_length=1)
    input: str = Field(..., min_length=1, description="Input given to the target model.")
    reference: str | None = Field(
        default=None,
        description="Optional reference / expected output for the judge.",
    )
    metadata: dict = Field(default_factory=dict)


class Dataset(BaseModel):
    """A set of ``DatasetItem`` s loaded from a JSONL file."""

    items: list[DatasetItem]

    @classmethod
    def from_jsonl(cls, path: str | Path) -> Dataset:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Dataset not found: {p}")
        items: list[DatasetItem] = []
        with p.open("r", encoding="utf-8") as fh:
            for lineno, raw in enumerate(fh, start=1):
                line = raw.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{p}:{lineno} - not valid JSON: {exc.msg}") from exc
                try:
                    items.append(DatasetItem.model_validate(payload))
                except Exception as exc:
                    raise ValueError(f"{p}:{lineno} - schema invalid: {exc}") from exc
        if not items:
            raise ValueError(f"{p} contained zero items (empty or blank-only lines).")
        ids = [it.id for it in items]
        if len(set(ids)) != len(ids):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"{p} has duplicate ids: {dupes}")
        return cls(items=items)

    @classmethod
    def from_items(cls, items: Iterable[DatasetItem | dict]) -> Dataset:
        """Build a Dataset from in-memory items.

        Mirrors ``from_jsonl`` invariants: duplicate ids and empty input
        are rejected here, not silently accepted. Reviewer P1 #9 — the
        downstream walk-forward path keys per-item scores by id, so a
        duplicate would silently overwrite the earlier item's score and
        bias KC-4 / the gap calculation.
        """
        parsed: list[DatasetItem] = []
        for it in items:
            if isinstance(it, DatasetItem):
                parsed.append(it)
            else:
                parsed.append(DatasetItem.model_validate(it))
        if not parsed:
            raise ValueError("Dataset.from_items received zero items.")
        ids = [it.id for it in parsed]
        if len(set(ids)) != len(ids):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"Dataset has duplicate ids: {dupes}")
        return cls(items=parsed)

    def __len__(self) -> int:
        return len(self.items)

    def __iter__(self):
        return iter(self.items)
