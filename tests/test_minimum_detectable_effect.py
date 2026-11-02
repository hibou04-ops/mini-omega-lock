# SPDX-License-Identifier: Apache-2.0
"""Paired absolute-noise MDE formula and invalid-input boundaries."""

from math import sqrt

import pytest

from mini_omega_lock.probes import (
    compute_empirical_noise_ceiling,
    compute_minimum_detectable_effect,
)


def test_legacy_name_is_the_same_callable_and_both_names_are_public():
    import mini_omega_lock
    from mini_omega_lock import probes

    assert compute_minimum_detectable_effect is compute_empirical_noise_ceiling
    assert compute_minimum_detectable_effect([-1.0, 2.0, -3.0]) == compute_empirical_noise_ceiling([-1.0, 2.0, -3.0])
    for module in (mini_omega_lock, probes):
        assert module.compute_empirical_noise_ceiling is compute_empirical_noise_ceiling
        assert module.compute_minimum_detectable_effect is compute_empirical_noise_ceiling
        assert "compute_empirical_noise_ceiling" in module.__all__
        assert "compute_minimum_detectable_effect" in module.__all__


@pytest.mark.parametrize("function", [compute_empirical_noise_ceiling, compute_minimum_detectable_effect])
def test_both_public_names_have_identical_formula_and_error_boundaries(function):
    expected = 2 + 1.96 * sqrt(2 / 3) / sqrt(3)
    assert function([-1.0, 2.0, -3.0]) == pytest.approx(expected)
    assert function([-0.25]) == 0.25
    assert function([0.0]) == 0.0
    assert function([1.0, 3.0], 0.0) == 2.0
    for values in ([], [float("nan")], [float("inf")], [-float("inf")]):
        with pytest.raises(ValueError):
            function(values)
    for z in (-1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            function([1.0], z)


def test_mde_uses_absolute_deltas_and_population_standard_deviation():
    # Absolute values (1, 2, 3) have mean 2 and population variance 2/3.
    expected = 2 + 1.96 * sqrt(2 / 3) / sqrt(3)
    assert compute_minimum_detectable_effect([-1.0, 2.0, -3.0]) == pytest.approx(expected)


def test_mde_is_invariant_to_sign_and_input_order():
    expected = compute_minimum_detectable_effect([1.0, 2.0, 3.0])
    assert compute_minimum_detectable_effect([-3.0, -1.0, 2.0]) == expected


def test_zero_confidence_multiplier_returns_absolute_mean():
    assert compute_minimum_detectable_effect([-1.0, 2.0, -3.0], 0.0) == 2.0


def test_custom_confidence_multiplier_changes_standard_error_term():
    assert compute_minimum_detectable_effect([1.0, 3.0], 2.0) == pytest.approx(2 + sqrt(2))


def test_repeating_distribution_reduces_standard_error():
    assert compute_minimum_detectable_effect([1.0, 3.0] * 2) < compute_minimum_detectable_effect([1.0, 3.0])


@pytest.mark.parametrize("deltas", [[0.0], [0.0, 0.0], [0.0, 0.0, 0.0]])
def test_zero_deltas_have_zero_mde(deltas):
    assert compute_minimum_detectable_effect(deltas) == 0.0


def test_singleton_has_zero_standard_error():
    assert compute_minimum_detectable_effect([-0.25]) == 0.25


def test_equal_magnitudes_do_not_cancel_or_add_variance():
    assert compute_minimum_detectable_effect([-0.25, 0.25, -0.25]) == 0.25


def test_empty_deltas_are_rejected():
    with pytest.raises(ValueError, match="at least one"):
        compute_minimum_detectable_effect([])


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_deltas_are_rejected(invalid):
    with pytest.raises(ValueError, match="finite"):
        compute_minimum_detectable_effect([0.1, invalid])


@pytest.mark.parametrize("invalid", [-1.0, float("nan"), float("inf"), -float("inf")])
def test_invalid_confidence_multiplier_is_rejected(invalid):
    with pytest.raises(ValueError, match="confidence_z"):
        compute_minimum_detectable_effect([0.1, 0.2], invalid)
