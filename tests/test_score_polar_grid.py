import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts.score_polar_grid import run


class PolarGridScoringTests(unittest.TestCase):
    def test_scoring_writes_cell_region_and_sensitivity_products(self):
        fields = [
            "candidate_id",
            "row",
            "col",
            "lat_deg",
            "lon_deg",
            "solar_illumination_fraction",
            "longest_dark_days",
            "sunlight_continuity_fraction",
            "earth_visibility_fraction",
            "regional_slope_p90_deg",
            "pinpoint_slope_p90_deg",
            "psr_edge_km",
            "science_proxy",
            "thermal_proxy",
            "data_coverage_fraction",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "cells.csv"
            with input_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                for col in range(3):
                    writer.writerow(
                        {
                            "candidate_id": f"cell-{col}",
                            "row": 0,
                            "col": col,
                            "lat_deg": -88.0,
                            "lon_deg": col * 0.01,
                            "solar_illumination_fraction": 0.7,
                            "longest_dark_days": 1.0,
                            "sunlight_continuity_fraction": 0.8,
                            "earth_visibility_fraction": 0.8,
                            "regional_slope_p90_deg": 4.0,
                            "pinpoint_slope_p90_deg": 4.0,
                            "psr_edge_km": 3.0,
                            "science_proxy": 0.8,
                            "thermal_proxy": 0.7,
                            "data_coverage_fraction": 0.9,
                        }
                    )

            result = run(input_path, root / "processed", draws=10)

            self.assertEqual(result["status"], "ranked")
            self.assertEqual(result["region_count"], 1)
            self.assertEqual(result["rank_agreement"]["top_rank_match"], 1)
            self.assertEqual(result["winner"], "polar-region-r000-c000")
            with (root / "processed/polar_region_ranking.csv").open(
                newline="", encoding="utf-8"
            ) as handle:
                regions = list(csv.DictReader(handle))
            self.assertEqual(regions[0]["cell_count"], "3")
            self.assertEqual(regions[0]["best_cell_lat_deg"], "-88.0")
            self.assertEqual(regions[0]["best_cell_lon_deg"], "0.02")
            with (root / "processed/polar_recommendation.json").open(
                encoding="utf-8"
            ) as handle:
                recommendation = json.load(handle)
            self.assertEqual(recommendation["candidate_cell_id"], "cell-2")
            with (root / "processed/polar_candidate_regions.geojson").open(
                encoding="utf-8"
            ) as handle:
                regions_geojson = json.load(handle)
            self.assertEqual(regions_geojson["type"], "FeatureCollection")
            self.assertEqual(
                regions_geojson["features"][0]["geometry"]["type"], "MultiPolygon"
            )

    def test_header_only_placeholder_does_not_produce_a_fake_ranking(self):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "empty.csv"
            input_path.write_text("candidate_id,row,col\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "no measured rows"):
                run(input_path, Path(tmp) / "processed", draws=10)


if __name__ == "__main__":
    unittest.main()
