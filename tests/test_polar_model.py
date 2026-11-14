import unittest
from pathlib import Path

from scripts.polar_model import (
    DEFAULT_WEIGHTS,
    apply_hard_constraints,
    cluster_cells,
    combine_scores,
    dirichlet_sensitivity,
    load_scoring_policy,
    normalize_indicators,
    rank_agreement,
    score_candidate,
)


class PolarModelTests(unittest.TestCase):
    def test_config_policy_controls_dark_scale_and_keeps_continuity_report_only(self):
        policy = load_scoring_policy(Path("config/polar_scoring.json"))
        base = {
            "solar_illumination_fraction": 0.8,
            "longest_dark_days": 15.0,
            "earth_visibility_fraction": 0.9,
            "regional_slope_p90_deg": 4.0,
            "psr_edge_km": 2.0,
            "science_proxy": 0.7,
            "thermal_proxy": 0.8,
        }
        dark_continuity, _ = normalize_indicators(
            {**base, "sunlight_continuity_fraction": 0.0}, policy=policy
        )
        lit_continuity, _ = normalize_indicators(
            {**base, "sunlight_continuity_fraction": 1.0}, policy=policy
        )

        self.assertEqual(policy.dark_high_days, 30.0)
        self.assertAlmostEqual(dark_continuity["solar_power"], 0.5**0.5)
        self.assertEqual(
            dark_continuity["solar_power"], lit_continuity["solar_power"]
        )

    def test_utilities_are_bounded_and_group_correlated_sun_inputs(self):
        indicators, _ = normalize_indicators(
            {
                "solar_illumination_fraction": 0.8,
                "longest_dark_days": 0.0,
                "sunlight_continuity_fraction": 1.0,
                "earth_visibility_fraction": 0.9,
                "regional_slope_p90_deg": 6.0,
                "pinpoint_slope_p90_deg": 4.0,
                "psr_edge_km": 2.0,
                "science_proxy": 0.7,
                "thermal_proxy": 0.6,
                "data_coverage_fraction": 0.8,
            }
        )
        self.assertEqual(indicators["solar_power"], 1.0)
        self.assertEqual(indicators["crew_safety"], indicators["terrain_safety"])
        self.assertEqual(len(indicators), 8)
        self.assertTrue(all(v is None or 0.0 <= v <= 1.0 for v in indicators.values()))

    def test_hard_filters_prioritize_slope_and_do_not_filter_earth_visibility(self):
        failures = apply_hard_constraints(
            {"pinpoint_slope_p90_deg": 16.0, "solar_illumination_fraction": 0.0}
        )
        self.assertEqual(failures, ["pinpoint_slope_over_limit"])
        self.assertEqual(
            apply_hard_constraints(
                {"pinpoint_slope_p90_deg": 10.0, "solar_illumination_fraction": 0.03}
            ),
            ["solar_below_cutoff"],
        )
        self.assertEqual(
            apply_hard_constraints(
                {"pinpoint_slope_p90_deg": 10.0, "solar_illumination_fraction": 0.5, "earth_visibility_fraction": 0.0}
            ),
            [],
        )

    def test_weighted_sum_and_geometric_mean_use_identical_weights(self):
        scores = combine_scores(
            {
                "solar_power": 1.0,
                "earth_visibility": 0.0,
                "terrain_safety": 1.0,
                "isru_access": 1.0,
                "science_value": 1.0,
                "thermal_stability": 1.0,
            }
        )
        self.assertAlmostEqual(scores["weighted_sum"], 0.8)
        self.assertLess(scores["weighted_geometric_mean"], scores["weighted_sum"])
        self.assertAlmostEqual(sum(DEFAULT_WEIGHTS.values()), 1.0)

    def test_invalid_finite_inputs_and_geometric_floor_are_rejected(self):
        with self.assertRaises(ValueError):
            combine_scores(
                {
                    "solar_power": float("nan"),
                    "earth_visibility": 0.5,
                    "terrain_safety": 0.5,
                    "isru_access": 0.5,
                    "science_value": 0.5,
                    "thermal_stability": 0.5,
                }
            )
        with self.assertRaises(ValueError):
            combine_scores(
                {
                    "solar_power": 0.5,
                    "earth_visibility": 0.5,
                    "terrain_safety": 0.5,
                    "isru_access": 0.5,
                    "science_value": 0.5,
                    "thermal_stability": 0.5,
                },
                geometric_floor=0.0,
            )
        with self.assertRaises(ValueError):
            apply_hard_constraints({"pinpoint_slope_p90_deg": float("nan")})

    def test_disqualified_candidate_scores_zero(self):
        result = score_candidate(
            {
                "solar_illumination_fraction": 0.5,
                "longest_dark_days": 1.0,
                "sunlight_continuity_fraction": 0.8,
                "earth_visibility_fraction": 0.6,
                "regional_slope_p90_deg": 4.0,
                "pinpoint_slope_p90_deg": 16.0,
                "psr_edge_km": 3.0,
                "science_proxy": 0.5,
                "thermal_proxy": 0.5,
            }
        )
        self.assertTrue(result["disqualified"])
        self.assertEqual(result["weighted_sum"], 0.0)
        self.assertEqual(result["weighted_geometric_mean"], 0.0)

    def test_clustering_ranks_distinct_regions_not_neighbor_cells(self):
        clusters = cluster_cells(
            [
                {"row": 0, "col": 0, "score": 0.8},
                {"row": 0, "col": 1, "score": 0.9},
                {"row": 10, "col": 10, "score": 0.7},
            ]
        )
        self.assertEqual([len(c) for c in clusters], [2, 1])
        self.assertEqual(max(cell["score"] for cell in clusters[0]), 0.9)

    def test_rank_agreement_and_dirichlet_sensitivity_are_reproducible(self):
        self.assertEqual(
            rank_agreement(["a", "b", "c"], ["a", "c", "b"])["top_rank_match"],
            1,
        )
        candidates = [
            {
                "candidate_id": "high-power",
                "dimensions": {
                    "solar_power": 0.9,
                    "earth_visibility": 0.8,
                    "terrain_safety": 0.8,
                    "isru_access": 0.7,
                    "science_value": 0.6,
                    "thermal_stability": 0.7,
                },
            },
            {
                "candidate_id": "high-comms",
                "dimensions": {
                    "solar_power": 0.6,
                    "earth_visibility": 0.9,
                    "terrain_safety": 0.8,
                    "isru_access": 0.5,
                    "science_value": 0.7,
                    "thermal_stability": 0.7,
                },
            },
        ]
        first = dirichlet_sensitivity(candidates, draws=100, seed=7)
        second = dirichlet_sensitivity(candidates, draws=100, seed=7)
        self.assertEqual(first, second)
        self.assertAlmostEqual(sum(row["top1_probability"] for row in first), 1.0)

    def test_disqualified_regions_never_win_sensitivity_draws(self):
        dimensions = {
            "solar_power": 0.9,
            "earth_visibility": 0.9,
            "terrain_safety": 0.9,
            "isru_access": 0.9,
            "science_value": 0.9,
            "thermal_stability": 0.9,
        }
        results = dirichlet_sensitivity(
            [
                {"candidate_id": "failed", "dimensions": dimensions, "disqualified": True},
                {"candidate_id": "eligible", "dimensions": dimensions},
            ],
            draws=20,
        )
        self.assertEqual(
            {row["candidate_id"]: row["top1_probability"] for row in results},
            {"failed": 0.0, "eligible": 1.0},
        )


if __name__ == "__main__":
    unittest.main()
