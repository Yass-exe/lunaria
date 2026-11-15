import math
import unittest

from scripts.build_polar_dashboard import build_payload
from scripts.common import PROCESSED_DIR, WEB_DIR


class PolarDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = build_payload(PROCESSED_DIR)

    def test_payload_exposes_fixed_regions_weights_and_date_status(self):
        payload = self.payload

        self.assertEqual(payload["recommendation"]["status"], "ranked")
        self.assertFalse(payload["recommendation"]["barker_validation"]["pass"])
        self.assertEqual(
            payload["recommendation"]["barker_validation"]["status"], "blocked"
        )
        self.assertEqual(len(payload["regions"]), 6)
        self.assertEqual(len(payload["weights"]), 6)
        self.assertEqual(payload["scoring"]["geometric_floor"], 0.01)
        self.assertEqual(len(payload["timestamps"]), 2925)
        self.assertEqual(
            set(payload["timeline"]), {r["region_id"] for r in payload["regions"]}
        )
        for region in payload["regions"]:
            self.assertEqual(len(region["dimensions"]), 6)
            self.assertEqual(len(region["indicators"]), 8)
            self.assertEqual(
                len(payload["timeline"][region["region_id"]]), 2925
            )

    def test_headline_score_reproduces_from_weights_and_dimensions(self):
        payload = self.payload
        floor = payload["scoring"]["geometric_floor"]
        for region in payload["regions"]:
            expected = math.exp(
                sum(
                    payload["weights"][key]
                    * math.log(max(region["dimensions"][key], floor))
                    for key in payload["dimensions"]
                )
            )
            self.assertAlmostEqual(
                expected, region["weighted_geometric_mean"], places=12
            )

    def test_cell_and_region_statistics_cover_every_screen_cell(self):
        payload = self.payload
        stats = payload["cell_stats"]

        self.assertEqual(stats["count"], payload["meta"]["cell_count"])
        for key in ("solar", "earth", "slope", "dark", "psr", "score"):
            distribution = stats[key]
            self.assertEqual(distribution["count"], stats["count"])
            self.assertEqual(len(distribution["bins"]), 24)
            self.assertEqual(len(distribution["edges"]), 25)
            self.assertLessEqual(distribution["low"], distribution["high"])
            self.assertGreaterEqual(distribution["clipped"], 0)
            self.assertLessEqual(distribution["min"], distribution["median"])
            self.assertLessEqual(distribution["median"], distribution["max"])

        self.assertEqual(
            set(payload["region_stats"]),
            {r["region_id"] for r in payload["regions"]},
        )
        for region in payload["regions"]:
            region_stats = payload["region_stats"][region["region_id"]]
            self.assertEqual(set(region_stats), {
                "solar", "earth", "slope", "dark", "psr", "score"
            })
            self.assertEqual(
                region_stats["solar"]["count"], region["cell_count"]
            )

    def test_refined_cloud_matches_processed_cells(self):
        payload = self.payload
        cloud = payload["refined_cells"]

        self.assertEqual(
            cloud["fields"],
            [
                "region_index",
                "solar",
                "earth",
                "slope",
                "score",
                "psr_edge_km",
                "lat_deg",
                "lon_deg",
            ],
        )
        self.assertEqual(len(cloud["rows"]), payload["meta"]["refined_cell_count"])
        for row in cloud["rows"]:
            self.assertEqual(len(row), 8)
            self.assertGreaterEqual(row[0], 0)
            self.assertLess(row[0], len(payload["regions"]))
            self.assertGreaterEqual(row[1], 0.0)
            self.assertLessEqual(row[1], 1.0)
            self.assertGreaterEqual(row[2], 0.0)
            self.assertLessEqual(row[2], 1.0)
            self.assertGreaterEqual(row[3], 0.0)
            self.assertGreaterEqual(row[4], 0.0)
            self.assertLessEqual(row[4], 1.0)

    def test_pipeline_artifacts_and_layers_are_complete(self):
        payload = self.payload

        self.assertEqual(len(payload["pipeline"]), 6)
        for step in payload["pipeline"]:
            self.assertTrue(step["label"])
            self.assertTrue(step["unit"])
            self.assertTrue(step["detail"])

        self.assertEqual(len(payload["artifacts"]), payload["meta"]["artifact_count"])
        self.assertGreaterEqual(len(payload["artifacts"]), 15)
        for artifact in payload["artifacts"]:
            self.assertEqual(len(artifact["sha256"]), 64)
            self.assertTrue(artifact["href"].startswith("../"))
            self.assertGreater(artifact["bytes"], 0)

        self.assertEqual(set(payload["layers"]), {"score", "solar", "earth", "slope"})
        for layer in payload["layers"].values():
            self.assertTrue(layer["src"].startswith("assets/"))
            self.assertTrue(layer["description"])

    def test_policy_and_gap_ledger_keep_validation_blocked(self):
        payload = self.payload
        policy = payload["policy"]

        self.assertEqual(payload["scoring"]["continuity_weighted"], False)
        for key in ("scope", "assumptions", "utilities", "scoring", "validation"):
            self.assertIn(key, policy)
        self.assertFalse(policy["assumptions"]["earth_visibility_hard_filter"])
        self.assertIn("linear", policy["utilities"]["solar_illumination"]["type"])
        self.assertIn("low", policy["utilities"]["solar_illumination"])
        self.assertIn("high", policy["utilities"]["solar_illumination"])
        self.assertTrue(
            policy["validation"]["reference"].startswith("Barker et al. 2021")
        )

        self.assertGreaterEqual(len(payload["data_gaps"]), 1)
        for gap in payload["data_gaps"]:
            self.assertTrue(gap["gap_id"])
            self.assertTrue(gap["dataset"])
            self.assertTrue(gap["why"])
            self.assertTrue(gap["acceptance"])
            self.assertIn(gap["priority"], {"P0", "P1"})

        self.assertEqual(
            payload["artemis_regions"]["geometry_status"], "unavailable"
        )

    def test_range_controls_publish_browser_metadata(self):
        index_html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
        app_js = (WEB_DIR / "app.js").read_text(encoding="utf-8")

        self.assertIn('name="timeline-sample"', index_html)
        self.assertIn('autocomplete="off"', index_html)
        self.assertIn('name="mission-priority-', app_js)
        self.assertIn('autocomplete="off"', app_js)


if __name__ == "__main__":
    unittest.main()
