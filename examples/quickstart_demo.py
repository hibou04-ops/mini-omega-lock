"""Compact offline noise-ceiling replay; no significance or deployment claim."""
from mini_omega_lock import compute_empirical_noise_ceiling


def main() -> None:
    for name, observations in [("empty_observations", []), ("nonfinite_observation", [float("nan")])]:
        try:
            compute_empirical_noise_ceiling(observations)
        except ValueError:
            print(f"- [BLOCKED] {name}: ValueError")
        else:
            raise AssertionError(f"{name} must be rejected")
    ceiling = compute_empirical_noise_ceiling([-0.1, 0.1])
    assert ceiling == 0.1
    print(f"+ [PASS] finite_observations: empirical_noise_ceiling={ceiling}")


if __name__ == "__main__":
    main()
