#!/usr/bin/env python3
"""Offline regression tests for the Lunaria pipeline.

Run with:  python3 -m unittest discover -s tests -v
These tests do not call NASA services.
"""

from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from common import (  # noqa: E402
    PROCESSED_DIR,
    clamp,
    linear_score,
    load_criteria,
    load_profiles,
    load_sites,
    read_csv,
    redact_url,
    seeded_rng,
)
from lunar_geom import (  # noqa: E402
    horizon_at,
    horizon_profile,
    horizon_stats,
    parse_dem_samples,
    project_point,
    slope_grid,
    unproject_point,
)


class TestCommon(unittest.TestCase):
    def test_six_sites_and_expected_coordinates(self):
        sites = load_sites()
        self.assertEqual(len(sites), 6)
        by_id = {site["site_id"]: site for site in sites}
        self.assertAlmostEqual(by_id["shackleton_rim"]["lat_deg"], -89.9)
        self.assertAlmostEqual(by_id["apollo17"]["lon_deg"], 30.8)
        self.assertEqual(
            {site["site_id"] for site in sites},
            {
                "shackleton_rim",
                "nobile_connecting_ridge",
                "von_karman",
                "marius_hills",
                "vallis_schroteri",
                "apollo17",
            },
        )

    def test_eight_criteria_and_five_profiles_sum_to_one(self):
        criteria = load_criteria()
        profiles = load_profiles()
        self.assertEqual(len(criteria), 8)
        self.assertEqual(len(profiles), 5)
        self.assertEqual(
            {criterion["id"] for criterion in criteria},
            {profile_key for profile_key in profiles["baseline"]["weights"]},
        )
        for profile in profiles.values():
            self.assertAlmostEqual(sum(profile["weights"].values()), 1.0, places=9)

    def test_linear_score_direction_and_clamping(self):
        self.assertAlmostEqual(linear_score(0.0, 0.4, 0.85), 0.0)
        self.assertAlmostEqual(linear_score(0.4, 0.4, 0.85), 0.0)
        self.assertAlmostEqual(linear_score(0.85, 0.4, 0.85), 100.0)
        self.assertAlmostEqual(linear_score(1.0, 0.4, 0.85), 100.0)
        # Reversed scales (lower is better) are supported.
        self.assertAlmostEqual(linear_score(30.0, 30.0, 5.0), 0.0)
        self.assertAlmostEqual(linear_score(5.0, 30.0, 5.0), 100.0)

    def test_clamp(self):
        self.assertEqual(clamp(-5.0), 0.0)
        self.assertEqual(clamp(105.0), 100.0)
        self.assertEqual(clamp(42.0), 42.0)

    def test_credentials_are_redacted(self):
        safe = redact_url("https://api.nasa.gov/planetary/apod?api_key=secret&thumbs=true")
        self.assertNotIn("secret", safe)
        self.assertIn("api_key=%2A%2A%2A", safe)

    def test_seeded_rng_is_reproducible(self):
        a = [seeded_rng(42).uniform(0, 1) for _ in range(3)]
        b = [seeded_rng(42).uniform(0, 1) for _ in range(3)]
        self.assertEqual(a, b)


class TestGeometry(unittest.TestCase):
    def test_projection_round_trip(self):
        for projection, lat, lon in [
            ("polar_stereographic", -89.9, 0.0),
            ("polar_stereographic", -84.2, 60.7),
            ("geographic", 20.2, 30.8),
            ("equirect_cm180_sp20", -45.5, 177.6),
        ]:
            x, y = project_point(projection, lat, lon)
            lat2, lon2 = unproject_point(projection, x, y)
            self.assertAlmostEqual(lat, lat2, places=6)
            # Longitude is circular; compare the shorter angular distance.
            delta = abs((lon - lon2 + 180.0) % 360.0 - 180.0)
            self.assertLess(delta, 1e-6)

    def test_slope_grid_on_a_ten_percent_plane(self):
        xs = [0.0, 100.0, 200.0]
        ys = [0.0, 1.0, 2.0]
        # z rises 10 m per 100 m in x, so the expected slope is atan(0.10).
        grid = {(xi, yi): xs[xi] * 0.10 for xi in range(3) for yi in range(3)}
        slopes = slope_grid("polar_stereographic", -84.2, xs, ys, grid)
        expected = math.degrees(math.atan(0.10))
        for slope in slopes.values():
            self.assertAlmostEqual(slope, expected, places=6)

    def test_horizon_profile_sees_a_one_kilometre_ridge(self):
        points = [(1000.0, y, 1000.0) for y in range(-20, 21, 2)]
        profile = horizon_profile(
            "polar_stereographic", -84.2, points, 0.0, 0.0, 0.0, max_radius_m=5000
        )
        self.assertAlmostEqual(horizon_at(profile, 90.0), 44.9, delta=0.3)
        stats = horizon_stats(profile)
        self.assertGreater(stats["horizon_max_deg"], 40.0)
        self.assertLess(stats["open_sky_frac_5deg"], 0.05)

    def test_parse_dem_samples_drops_nodata(self):
        payload = {
            "samples": [
                {"value": "12.5", "location": {"x": 1, "y": 2}},
                {"value": "-3.4028235e+38", "location": {"x": 3, "y": 4}},
                {"value": None, "location": {"x": 5, "y": 6}},
                {"value": "-8.0", "location": {"x": 7, "y": 8}},
            ]
        }
        points = parse_dem_samples(payload)
        self.assertEqual(len(points), 2)
        self.assertEqual(points[0], (1.0, 2.0, 12.5))
        self.assertEqual(points[1], (7.0, 8.0, -8.0))


class TestProcessedOutputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ranking = read_csv(PROCESSED_DIR / "site_ranking.csv")
        cls.scores = read_csv(PROCESSED_DIR / "site_scores.csv")
        cls.criteria = read_csv(PROCESSED_DIR / "criteria_scores.csv")
        cls.sensitivity = read_csv(PROCESSED_DIR / "sensitivity.csv")
        cls.gaps = read_csv(PROCESSED_DIR / "data_gaps.csv")
        cls.recommendation = json.loads(
            (PROCESSED_DIR / "recommendation.json").read_text(encoding="utf-8")
        )

    def test_ranking_has_two_modes_and_six_sites(self):
        self.assertEqual(len(self.ranking), 12)
        for mode in ("site", "pinpoint"):
            rows = [row for row in self.ranking if row["mode"] == mode]
            self.assertEqual(len(rows), 6)
            self.assertEqual({int(row["rank"]) for row in rows}, set(range(1, 7)))
            self.assertEqual(rows[0]["site_id"], "nobile_connecting_ridge")
            for row in rows:
                self.assertGreaterEqual(float(row["score"]), 0.0)
                self.assertLessEqual(float(row["score"]), 100.0)

    def test_criteria_scores_are_bounded_and_complete(self):
        self.assertEqual(len(self.criteria), 2 * 6 * 8)
        for row in self.criteria:
            value = float(row["subscore"])
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 100.0)
            self.assertIn(row["tier"], {"A", "B", "C"})

    def test_recommendation_is_nobile_with_apollo_runner_up(self):
        self.assertEqual(
            self.recommendation["winner"]["site_id"], "nobile_connecting_ridge"
        )
        self.assertEqual(
            self.recommendation["runner_up"]["site_id"], "apollo17"
        )
        self.assertGreater(self.recommendation["runner_up"]["margin"], 10.0)

    def test_sensitivity_reports_joint_and_weight_only(self):
        for row in self.sensitivity:
            self.assertIn("top1_prob", row)
            self.assertIn("top1_prob_weight_only", row)
            self.assertGreaterEqual(float(row["top1_prob"]), 0.0)
            self.assertLessEqual(float(row["top1_prob"]), 1.0)

    def test_gap_placeholders_exist(self):
        self.assertEqual(len(self.gaps), 34)
        self.assertEqual(sum(1 for row in self.gaps if row["priority"] == "P0"), 8)
        for row in self.gaps:
            path = ROOT / row["placeholder_file"]
            self.assertTrue(path.exists(), f"missing placeholder {path}")
            header = path.read_text(encoding="utf-8").splitlines()[0]
            self.assertTrue(header.strip(), f"empty placeholder header {path}")

    def test_geojson_is_well_formed(self):
        for name, count in [("sites.geojson", 6), ("pinpoints.geojson", 6)]:
            payload = json.loads(
                (PROCESSED_DIR / name).read_text(encoding="utf-8")
            )
            self.assertEqual(payload["type"], "FeatureCollection")
            self.assertEqual(len(payload["features"]), count)
            for feature in payload["features"]:
                self.assertEqual(feature["geometry"]["type"], "Point")
                self.assertEqual(len(feature["geometry"]["coordinates"]), 2)


class TestDashboardPayload(unittest.TestCase):
    def test_archived_six_site_data_is_preserved(self):
        path = ROOT / "archive" / "six-site-analysis" / "web" / "data.js"
        self.assertTrue(path.exists(), "six-site dashboard archive is incomplete")
        text = path.read_text(encoding="utf-8")
        self.assertIn("window.LUNARIA_DATA = ", text)
        payload = text.split("window.LUNARIA_DATA = ", 1)[1].rstrip().rstrip(";")
        data = json.loads(payload)
        self.assertEqual(len(data["sites"]), 6)
        self.assertEqual(len(data["criteria"]), 8)
        self.assertEqual(data["recommendation"]["winner"]["site_id"], "nobile_connecting_ridge")
        for site in data["sites"]:
            self.assertIn("criteria", site)
            self.assertEqual(len(site["criteria"]), 8)
            self.assertIsNotNone(site["pinpoint"]["lat"])
            self.assertIsNotNone(site["pinpoint"]["lon"])


if __name__ == "__main__":
    unittest.main()
