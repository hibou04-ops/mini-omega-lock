# SPDX-License-Identifier: Apache-2.0
"""Optional integration fails explicitly without hiding broken parent installations."""

import importlib

import pytest

from mini_omega_lock.bridge import adapt_omegaprompt_provider, to_omegaprompt_report


@pytest.mark.parametrize("convert", [to_omegaprompt_report, adapt_omegaprompt_provider])
def test_optional_bridge_explains_missing_parent_without_requiring_it(monkeypatch, convert):
    original = importlib.import_module

    def missing_parent(name, *args, **kwargs):
        if name.startswith("omegaprompt"):
            raise ModuleNotFoundError("No module named 'omegaprompt'", name="omegaprompt")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", missing_parent)
    with pytest.raises(RuntimeError, match=r"mini-omega-lock\[bridge\]"):
        convert({})


def test_bridge_preserves_a_broken_parent_dependency_error(monkeypatch):
    original = importlib.import_module
    inner_error = ModuleNotFoundError("Missing parent runtime dependency", name="missing_dependency")

    def broken_parent(name, *args, **kwargs):
        if name.startswith("omegaprompt"):
            raise inner_error
        return original(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", broken_parent)
    with pytest.raises(ModuleNotFoundError) as caught:
        to_omegaprompt_report({})
    assert caught.value is inner_error
