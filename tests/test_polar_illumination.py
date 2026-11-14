import math
import csv
import tempfile
import unittest
from pathlib import Path

import numpy as np

from scripts.polar_illumination import (
    equivalent_circle_edge_distance,
    continuity_window_samples,
    load_ephemeris,
    sampled_run_duration_days,
    science_value_proxy,
    thermal_stability_proxy,
    topocentric_direction_components,
)


class PolarIlluminationUtilityTests(unittest.TestCase):
    def test_six_and_half_day_window_includes_both_endpoints(self):
        self.assertEqual(continuity_window_samples(6.5, step_hours=6.0), 27)

    def test_science_proxy_is_neutral_until_independent_geology_is_ingested(self):
        actual = science_value_proxy(np.asarray([0.0, 7.5, 30.0]))
        np.testing.assert_allclose(actual, [0.5, 0.5, 0.5])

    def test_topocentric_earth_direction_includes_surface_parallax(self):
        upward, eastward, northward = topocentric_direction_components(
            np.asarray([0.0]),
            np.asarray([1.0]),
            np.asarray([0.0]),
            range_km=404_000.0,
            observer_radius_km=np.asarray([1737.4]),
        )

        self.assertAlmostEqual(
            math.degrees(math.asin(upward[0])), -0.2464, delta=0.001
        )
        self.assertGreater(eastward[0], 0.999)
        self.assertEqual(northward[0], 0.0)

    def test_dark_run_duration_never_exceeds_the_sampled_window(self):
        self.assertEqual(
            sampled_run_duration_days(
                np.asarray([5, 2]), sample_count=5, step_hours=6.0
            ).tolist(),
            [1.0, 0.5],
        )

    def test_ephemeris_requires_identical_sun_and_earth_timestamps(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ephemeris.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle, fieldnames=["utc", "body", "lon_deg", "lat_deg", "range_km"]
                )
                writer.writeheader()
                writer.writerows(
                    [
                        {"utc": "2024-01-01T00:00:00Z", "body": "sun", "lon_deg": 0, "lat_deg": 0, "range_km": 150_000_000},
                        {"utc": "2024-01-01T06:00:00Z", "body": "sun", "lon_deg": 90, "lat_deg": 0, "range_km": 150_000_000},
                        {"utc": "2024-01-01T00:00:00Z", "body": "earth", "lon_deg": 0, "lat_deg": 0, "range_km": 404_000},
                        {"utc": "2024-01-01T12:00:00Z", "body": "earth", "lon_deg": 90, "lat_deg": 0, "range_km": 404_000},
                    ]
                )

            with self.assertRaisesRegex(ValueError, "timestamps"):
                load_ephemeris(path)

    def test_ephemeris_exposes_aligned_timestamps_and_body_fixed_vectors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ephemeris.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle, fieldnames=["utc", "body", "lon_deg", "lat_deg", "range_km"]
                )
                writer.writeheader()
                writer.writerows(
                    [
                        {"utc": "2024-01-01T00:00:00Z", "body": "sun", "lon_deg": 0, "lat_deg": 0, "range_km": 150_000_000},
                        {"utc": "2024-01-01T00:00:00Z", "body": "earth", "lon_deg": 90, "lat_deg": 0, "range_km": 404_000},
                    ]
                )

            ephemeris = load_ephemeris(path)

            self.assertEqual(ephemeris["utc"].tolist(), ["2024-01-01T00:00:00Z"])
            np.testing.assert_allclose(ephemeris["sun"], [[1.0, 0.0, 0.0]], atol=1e-12)
            np.testing.assert_allclose(ephemeris["earth"], [[0.0, 1.0, 0.0]], atol=1e-12)
            np.testing.assert_allclose(ephemeris["earth_range_km"], [404_000.0])

    def test_thermal_stability_proxy_increases_toward_the_south_pole(self):
        actual = thermal_stability_proxy(np.asarray([-80.0, -85.0, -90.0]))
        np.testing.assert_allclose(actual, [0.0, 0.5, 1.0])

    def test_psr_distance_is_to_equivalent_area_edge_not_centroid(self):
        cells = np.asarray([[0.0, 0.0], [5.0, 0.0]])
        centers = np.asarray([[0.0, 0.0]])
        areas = np.asarray([math.pi * 4.0])  # equivalent radius = 2 km

        actual = equivalent_circle_edge_distance(cells, centers, areas)

        np.testing.assert_allclose(actual, [0.0, 3.0])


if __name__ == "__main__":
    unittest.main()
