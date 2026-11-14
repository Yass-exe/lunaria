#!/usr/bin/env python3
"""Score the six lunar sites with a transparent multi-criteria model.

Two geometry modes are produced:
  * site     - the user-supplied site coordinate, with its local horizon
  * pinpoint - a DEM-screened pad within 1 km of the site

The primary ranking is site-level. The pinpoint mode is a robustness check and
a candidate landing pad, not a certified pad.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict

from common import (
    PROCESSED_DIR,
    ROOT,
    clamp,
    ensure_dirs,
    linear_score,
    load_criteria,
    load_curated,
    load_profiles,
    load_sites_enriched,
    log,
    read_csv,
    seeded_rng,
    utc_now,
    write_csv,
    write_json,
)

SOURCE_BY_DEM = {
    "LRO_LOLA_DEM_SPole875_5mp_v04": "SRC-DEM-01",
    "LRO_LOLA_DEM_SPole75_30mp_v04": "SRC-DEM-02",
    "LRO_LOLA_DEM_Global_256ppd_v06": "SRC-DEM-03",
    "LRO_NAC_DEM_14N304E_2mp": "SRC-DEM-04",
    "NAC_DTM_APOLLO17": "SRC-DEM-05",
}

MODE_LABEL = {"site": "site coordinate", "pinpoint": "DEM-screened pad"}


def f(row: dict, key: str, default=None):
    value = row.get(key)
    if value in (None, "", "None", "nan"):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_table(path):
    if not path.exists():
        return []
    return read_csv(path)


def criterion_value(
    criterion: dict,
    site: dict,
    ephem: dict,
    terrain: dict,
    psr: dict,
    curated: dict,
    mode: str,
) -> dict:
    cid = criterion["id"]
    if cid == "solar_illumination":
        field = "pinpoint_sun_up_terrain_frac" if mode == "pinpoint" else "sun_up_terrain_frac"
        raw = f(ephem, field)
        if raw is None:
            raw = f(ephem, "sun_up_terrain_frac", 0.0)
        low, high = criterion["scale"]
        return {
            "raw_value": round(raw * 100, 2),
            "raw_unit": "% of year above local terrain",
            "subscore": round(linear_score(raw, low, high), 2),
            "tier": criterion["tier"],
            "source_id": criterion["source_id"],
            "rationale": (
                f"Horizons topocentric Sun geometry combined with the {MODE_LABEL[mode]} "
                f"LOLA/NAC 5 km horizon model."
            ),
        }
    if cid == "earth_link":
        field = "pinpoint_earth_up5_terrain_frac" if mode == "pinpoint" else "earth_up5_terrain_frac"
        raw = f(ephem, field)
        if raw is None:
            raw = f(ephem, "earth_up5_terrain_frac", 0.0)
        low, high = criterion["scale"]
        return {
            "raw_value": round(raw * 100, 2),
            "raw_unit": "% of year with Earth >5 deg above local terrain",
            "subscore": round(linear_score(raw, low, high), 2),
            "tier": criterion["tier"],
            "source_id": criterion["source_id"],
            "rationale": (
                "Direct-to-Earth screening metric from Horizons Earth az/el and the "
                f"{MODE_LABEL[mode]} terrain horizon. A relay is still required for continuous coverage."
            ),
        }
    if cid == "terrain_trafficability":
        if mode == "pinpoint":
            slope = f(terrain, "pinpoint_slope_p90_deg")
            rough = f(terrain, "pinpoint_roughness_m")
            res = f(terrain, "pinpoint_dem_res_m")
        else:
            slope = f(terrain, "slope_p90_deg")
            rough = f(terrain, "roughness_m")
            res = f(terrain, "dem_res_effective_m")
        if slope is None:
            slope = f(terrain, "slope_p90_deg", 30.0)
        if rough is None:
            rough = f(terrain, "roughness_m", 25.0)
        slope_score = linear_score(slope, *criterion["slope_scale"])
        rough_score = linear_score(rough, *criterion["roughness_scale"])
        blend = criterion.get("blend", [0.85, 0.15])
        subscore = blend[0] * slope_score + blend[1] * rough_score
        return {
            "raw_value": f"{slope:.2f} deg / {rough:.2f} m",
            "raw_unit": f"slope p90 / roughness; DEM ~{res:.0f} m" if res else "slope p90 / roughness",
            "subscore": round(clamp(subscore), 2),
            "tier": criterion["tier"],
            "source_id": terrain.get("source_id") or SOURCE_BY_DEM.get(site.get("dem_service"), "SRC-DEM-03"),
            "rationale": (
                f"DEM-derived slope and residual roughness for the {MODE_LABEL[mode]}. "
                "This is a screening product, not a boulder-scale hazard map."
            ),
        }
    if cid == "isru_water_ice":
        polar = site["lat_deg"] <= -60.0
        edge = f(psr, "psr_edge_km_approx")
        if polar and edge is not None:
            low, high = criterion["scale"]
            score = linear_score(edge, low, high)
            return {
                "raw_value": round(edge, 3),
                "raw_unit": "km to nearest mapped PSR edge (approx.)",
                "subscore": round(score, 2),
                "tier": criterion["tier"],
                "source_id": criterion["source_id"],
                "rationale": (
                    f"Nearest PSR: {psr.get('nearest_psr_feature', 'unknown')} "
                    f"(centroid {psr.get('centroid_distance_km', '?')} km; equivalent-radius edge "
                    f"{edge} km). PSR proximity is a proxy, not an ice detection."
                ),
            }
        item = curated.get(cid, {})
        score = float(item.get("score", 0.0))
        return {
            "raw_value": score,
            "raw_unit": "analyst rubric (0-100)",
            "subscore": round(score, 2),
            "tier": item.get("tier", "C"),
            "source_id": item.get("source_id", "SRC-PUB-01"),
            "rationale": item.get("rationale", "No polar PSR access."),
        }
    # Curated criteria.
    item = curated.get(cid, {})
    score = float(item.get("score", 0.0))
    return {
        "raw_value": score,
        "raw_unit": "analyst rubric (0-100)",
        "subscore": round(clamp(score), 2),
        "tier": item.get("tier", criterion.get("tier", "C")),
        "source_id": item.get("source_id", criterion.get("source_id", "SRC-PUB-01")),
        "rationale": item.get("rationale", criterion.get("description", "")),
    }


def build_mode_scores(sites, criteria, ephem_by_site, terrain_by_site, psr_by_site, curated, mode):
    rows = []
    scores_by_site = {}
    for site in sites:
        sid = site["site_id"]
        ephem = ephem_by_site.get(sid, {})
        terrain = terrain_by_site.get(sid, {})
        psr = psr_by_site.get(sid, {})
        subs = {}
        for criterion in criteria:
            cid = criterion["id"]
            item = criterion_value(
                criterion, site, ephem, terrain, psr, curated.get(sid, {}), mode
            )
            subs[cid] = item
            rows.append(
                {
                    "mode": mode,
                    "site_id": sid,
                    "criterion_id": cid,
                    "criterion_label": criterion["label"],
                    "raw_value": item["raw_value"],
                    "raw_unit": item["raw_unit"],
                    "subscore": item["subscore"],
                    "tier": item["tier"],
                    "source_id": item["source_id"],
                    "rationale": item["rationale"],
                }
            )
        scores_by_site[sid] = subs
    return rows, scores_by_site


def weighted_total(subs: dict, weights: dict) -> float:
    return sum(weights[cid] * subs[cid]["subscore"] for cid in weights)


def rank_sites(sites, scores_by_site, weights):
    scored = []
    for site in sites:
        sid = site["site_id"]
        subs = scores_by_site[sid]
        total = weighted_total(subs, weights)
        strength = max(
            weights[cid] * subs[cid]["subscore"] for cid in weights
        )
        strength_id = max(weights, key=lambda cid: weights[cid] * subs[cid]["subscore"])
        weakness = max(
            weights[cid] * (100.0 - subs[cid]["subscore"]) for cid in weights
        )
        weakness_id = max(
            weights, key=lambda cid: weights[cid] * (100.0 - subs[cid]["subscore"])
        )
        scored.append(
            {
                "site_id": sid,
                "name": site["name"],
                "total": round(total, 3),
                "strength": f"{strength_id} ({subs[strength_id]['subscore']:.0f})",
                "weakness": f"{weakness_id} ({subs[weakness_id]['subscore']:.0f})",
                "strength_weighted": round(strength, 3),
                "weakness_weighted": round(weakness, 3),
            }
        )
    scored.sort(key=lambda item: (-item["total"], item["site_id"]))
    best = scored[0]["total"] if scored else 0.0
    for rank, item in enumerate(scored, start=1):
        item["rank"] = rank
        item["delta_to_best"] = round(best - item["total"], 3)
    return scored


def perturb_subscores(scores_by_site, rng):
    """Sample judgment and measurement error around each criterion score.

    Tier A/B evidence is treated as +/-3 points (1 sigma); Tier C analyst
    judgments use +/-10 points. Scores are clipped to 0-100.
    """
    out = {}
    for sid, subs in scores_by_site.items():
        out[sid] = {}
        for cid, item in subs.items():
            sd = 3.0 if str(item.get("tier", "C")).upper() in {"A", "B"} else 10.0
            out[sid][cid] = {
                **item,
                "subscore": round(clamp(item["subscore"] + rng.gauss(0.0, sd)), 3),
            }
    return out


def monte_carlo(sites, scores_by_site, weights, *, draws=5000, seed=42):
    """Joint weight + score uncertainty, plus a weight-only comparison."""
    rng = seeded_rng(seed)
    criteria_ids = list(weights)
    per_site = {
        site["site_id"]: {
            "scores": [],
            "ranks": [],
            "top1_joint": 0,
            "top1_weight_only": 0,
        }
        for site in sites
    }
    for _ in range(draws):
        perturbed = {cid: weights[cid] * rng.uniform(0.5, 1.5) for cid in criteria_ids}
        total_weight = sum(perturbed.values())
        perturbed = {cid: value / total_weight for cid, value in perturbed.items()}

        weight_only = rank_sites(sites, scores_by_site, perturbed)
        for item in weight_only:
            if item["rank"] == 1:
                per_site[item["site_id"]]["top1_weight_only"] += 1

        sampled = perturb_subscores(scores_by_site, rng)
        ranked = rank_sites(sites, sampled, perturbed)
        for item in ranked:
            entry = per_site[item["site_id"]]
            entry["scores"].append(item["total"])
            entry["ranks"].append(item["rank"])
            if item["rank"] == 1:
                entry["top1_joint"] += 1
    rows = []
    for site in sites:
        sid = site["site_id"]
        entry = per_site[sid]
        scores = sorted(entry["scores"])
        ranks = entry["ranks"]
        rows.append(
            {
                "site_id": sid,
                "mean_score": round(sum(scores) / len(scores), 3),
                "p10_score": round(scores[int(0.10 * (len(scores) - 1))], 3),
                "p90_score": round(scores[int(0.90 * (len(scores) - 1))], 3),
                "top1_prob": round(entry["top1_joint"] / draws, 4),
                "top1_prob_weight_only": round(entry["top1_weight_only"] / draws, 4),
                "mean_rank": round(sum(ranks) / len(ranks), 3),
                "modal_rank": max(set(ranks), key=ranks.count),
            }
        )
    return rows


def one_at_a_time(sites, scores_by_site, weights):
    baseline = rank_sites(sites, scores_by_site, weights)[0]["site_id"]
    rows = []
    for cid in weights:
        zero = dict(weights)
        zero[cid] = 0.0
        zero_total = sum(zero.values())
        zero = {k: v / zero_total for k, v in zero.items()}
        zero_winner = rank_sites(sites, scores_by_site, zero)[0]["site_id"]

        double = dict(weights)
        double[cid] = double[cid] * 2.0
        double_total = sum(double.values())
        double = {k: v / double_total for k, v in double.items()}
        double_winner = rank_sites(sites, scores_by_site, double)[0]["site_id"]
        rows.append(
            {
                "criterion_id": cid,
                "baseline_winner": baseline,
                "winner_if_weight_zero": zero_winner,
                "winner_if_weight_doubled": double_winner,
                "result_changes": "yes"
                if zero_winner != baseline or double_winner != baseline
                else "no",
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    args = parser.parse_args()
    ensure_dirs()

    sites = load_sites_enriched()
    criteria = load_criteria()
    profiles = load_profiles()
    curated = load_curated()
    baseline_weights = profiles["baseline"]["weights"]

    ephem_rows = {
        row["site_id"]: row
        for row in load_table(PROCESSED_DIR / "ephemeris_summary.csv")
        if row["scenario"] == "primary"
    }
    terrain = {row["site_id"]: row for row in load_table(PROCESSED_DIR / "terrain_summary.csv")}
    psr = {row["site_id"]: row for row in load_table(PROCESSED_DIR / "psr_proximity.csv")}

    all_criteria_rows = []
    scores_by_mode = {}
    for mode in ("site", "pinpoint"):
        rows, scores_by_site = build_mode_scores(
            sites, criteria, ephem_rows, terrain, psr, curated, mode
        )
        all_criteria_rows.extend(rows)
        scores_by_mode[mode] = scores_by_site

    # Add baseline weight and contribution to the long table.
    for row in all_criteria_rows:
        weight = baseline_weights[row["criterion_id"]]
        row["weight_baseline"] = weight
        row["weighted_contribution"] = round(weight * row["subscore"], 4)
    write_csv(
        PROCESSED_DIR / "criteria_scores.csv",
        all_criteria_rows,
        [
            "mode", "site_id", "criterion_id", "criterion_label", "raw_value",
            "raw_unit", "subscore", "weight_baseline", "weighted_contribution",
            "tier", "source_id", "rationale",
        ],
    )

    # Per-profile rankings and baseline sensitivity.
    profile_rows = []
    ranking_rows = []
    sensitivity_rows = []
    recommendations = []
    for mode in ("site", "pinpoint"):
        scores_by_site = scores_by_mode[mode]
        for profile_id, profile in profiles.items():
            ranked = rank_sites(sites, scores_by_site, profile["weights"])
            for item in ranked:
                profile_rows.append(
                    {
                        "mode": mode,
                        "profile_id": profile_id,
                        "profile_label": profile["label"],
                        "rank": item["rank"],
                        "site_id": item["site_id"],
                        "name": item["name"],
                        "score": item["total"],
                        "delta_to_best": item["delta_to_best"],
                    }
                )

        baseline_ranked = rank_sites(sites, scores_by_site, baseline_weights)
        sens = monte_carlo(sites, scores_by_site, baseline_weights)
        sens_by_site = {row["site_id"]: row for row in sens}
        for row in sens:
            row["mode"] = mode
            row["baseline_score"] = next(
                item["total"] for item in baseline_ranked if item["site_id"] == row["site_id"]
            )
            row["baseline_rank"] = next(
                item["rank"] for item in baseline_ranked if item["site_id"] == row["site_id"]
            )
            sensitivity_rows.append(row)
        for item in baseline_ranked:
            row = {
                "mode": mode,
                "rank": item["rank"],
                "site_id": item["site_id"],
                "name": item["name"],
                "score": item["total"],
                "delta_to_best": item["delta_to_best"],
                "top1_prob": sens_by_site[item["site_id"]]["top1_prob"],
                "key_strength": item["strength"],
                "key_weakness": item["weakness"],
            }
            ranking_rows.append(row)
        recommendations.append((mode, baseline_ranked, sens_by_site))

    write_csv(
        PROCESSED_DIR / "site_ranking_by_profile.csv",
        profile_rows,
        [
            "mode", "profile_id", "profile_label", "rank", "site_id", "name",
            "score", "delta_to_best",
        ],
    )
    write_csv(
        PROCESSED_DIR / "sensitivity.csv",
        sensitivity_rows,
        [
            "mode", "site_id", "mean_score", "p10_score", "p90_score", "top1_prob",
            "top1_prob_weight_only", "mean_rank", "modal_rank", "baseline_score",
            "baseline_rank",
        ],
    )
    write_csv(
        PROCESSED_DIR / "site_ranking.csv",
        ranking_rows,
        [
            "mode", "rank", "site_id", "name", "score", "delta_to_best", "top1_prob",
            "key_strength", "key_weakness",
        ],
    )

    # Wide score table.
    wide_rows = []
    for mode in ("site", "pinpoint"):
        scores_by_site = scores_by_mode[mode]
        ranked = rank_sites(sites, scores_by_site, baseline_weights)
        rank_by_site = {item["site_id"]: item for item in ranked}
        sens_by_site = {
            row["site_id"]: row for row in sensitivity_rows if row["mode"] == mode
        }
        for site in sites:
            sid = site["site_id"]
            subs = scores_by_site[sid]
            measured = sum(1 for c in criteria if c["method"] != "curated")
            judgment = len(criteria) - measured
            row = {
                "mode": mode,
                "site_id": sid,
                "name": site["name"],
                "weighted_total": rank_by_site[sid]["total"],
                "rank": rank_by_site[sid]["rank"],
                "top1_prob": sens_by_site.get(sid, {}).get("top1_prob", ""),
                "evidence_grade": "B" if measured >= 3 else ("C" if measured < 2 else "B/C"),
                "measured_criteria": measured,
                "judgment_criteria": judgment,
            }
            for criterion in criteria:
                row[f"{criterion['id']}_score"] = subs[criterion["id"]]["subscore"]
            wide_rows.append(row)
    criterion_cols = [f"{c['id']}_score" for c in criteria]
    write_csv(
        PROCESSED_DIR / "site_scores.csv",
        wide_rows,
        [
            "mode", "site_id", "name", "weighted_total", "rank", "top1_prob",
            "evidence_grade", "measured_criteria", "judgment_criteria",
        ]
        + criterion_cols,
    )

    oat_rows = []
    for mode in ("site", "pinpoint"):
        rows = one_at_a_time(sites, scores_by_mode[mode], baseline_weights)
        for row in rows:
            row["mode"] = mode
            oat_rows.append(row)
    write_csv(
        PROCESSED_DIR / "criterion_swing.csv",
        oat_rows,
        [
            "mode", "criterion_id", "baseline_winner", "winner_if_weight_zero",
            "winner_if_weight_doubled", "result_changes",
        ],
    )

    # Profile winners for the recommendation summary.
    profile_winners = {}
    for mode in ("site", "pinpoint"):
        for profile_id in profiles:
            rows = [
                r
                for r in profile_rows
                if r["mode"] == mode and r["profile_id"] == profile_id and r["rank"] == 1
            ]
            if rows:
                profile_winners[f"{mode}:{profile_id}"] = rows[0]["site_id"]

    # Recommendation JSON, primary = site mode.
    primary_mode = "site"
    primary_ranked = next(r for m, r, _ in recommendations if m == primary_mode)
    pinpoint_ranked = next(r for m, r, _ in recommendations if m == "pinpoint")
    primary_sens = next(s for m, _, s in recommendations if m == primary_mode)
    winner = primary_ranked[0]
    runner_up = primary_ranked[1]
    winner_site = next(site for site in sites if site["site_id"] == winner["site_id"])
    winner_terrain = terrain.get(winner["site_id"], {})
    winner_ephem = ephem_rows.get(winner["site_id"], {})
    winner_psr = psr.get(winner["site_id"], {})
    winner_subs = scores_by_mode[primary_mode][winner["site_id"]]
    runner_subs = scores_by_mode[primary_mode][runner_up["site_id"]]

    strengths = sorted(
        winner_subs, key=lambda cid: winner_subs[cid]["subscore"], reverse=True
    )[:3]
    weaknesses = sorted(winner_subs, key=lambda cid: winner_subs[cid]["subscore"])[:2]
    rationale = [
        f"{winner['name']} ranks first at {winner['total']:.1f}/100 under the balanced profile.",
        "Leading baseline strengths: "
        + "; ".join(
            f"{cid} {winner_subs[cid]['subscore']:.0f}/100 ({winner_subs[cid]['tier']})"
            for cid in strengths
        )
        + ".",
        f"Runner-up {runner_up['name']} scores {runner_up['total']:.1f}; it leads on "
        + ", ".join(
            cid
            for cid in runner_subs
            if runner_subs[cid]["subscore"] > winner_subs[cid]["subscore"]
        )
        + ".",
        f"Top-1 probability under joint weight and score perturbation: "
        f"{primary_sens[winner['site_id']]['top1_prob'] * 100:.1f}% "
        f"(weights only: {primary_sens[winner['site_id']]['top1_prob_weight_only'] * 100:.1f}%).",
    ]
    caveats = [
        "The illumination and Earth-link fractions use a 5 km terrain horizon and a 1-year Horizons window; terrain beyond 5 km and the 18.6-year libration cycle are not fully modelled.",
        "Terrain scores come from 5-118 m/px DEMs sampled on a 32x32 grid; they are screening products, not landing-hazard certification.",
        "Science, thermal, safety and data-maturity scores are analyst judgments (Tier C), not measurements.",
        "PSR edge distance is approximated from a centroid-and-area catalogue, not PSR polygons.",
        "A direct-to-Earth fraction below 99% means a relay is required for continuous communications. No relay link budget was ingested.",
    ]
    data_requests = []
    for row in load_table(PROCESSED_DIR / "data_gaps.csv"):
        if row["priority"] == "P0":
            data_requests.append(
                {
                    "site_id": row["site_id"],
                    "dataset": row["dataset"],
                    "aoi": row["aoi"],
                    "request_spec": row["request_spec"],
                    "request_from": row["request_from"],
                }
            )
    recommendation = {
        "generated_at": utc_now(),
        "primary_mode": primary_mode,
        "winner": {
            "site_id": winner["site_id"],
            "name": winner["name"],
            "lat_deg": winner_site["lat_deg"],
            "lon_deg": winner_site["lon_deg"],
            "score": winner["total"],
            "top1_prob": primary_sens[winner["site_id"]]["top1_prob"],
            "pinpoint_lat_deg": winner_terrain.get("pinpoint_lat_deg", ""),
            "pinpoint_lon_deg": winner_terrain.get("pinpoint_lon_deg", ""),
            "pinpoint_offset_km": winner_terrain.get("pinpoint_offset_km", ""),
            "pinpoint_slope_p90_deg": winner_terrain.get("pinpoint_slope_p90_deg", ""),
            "elevation_m": winner_site.get("elevation_m", ""),
            "solar_illumination_pct": winner_ephem.get("sun_up_terrain_frac", ""),
            "earth_link_gt5_pct": winner_ephem.get("earth_up5_terrain_frac", ""),
            "psr_edge_km_approx": winner_psr.get("psr_edge_km_approx", ""),
        },
        "runner_up": {
            "site_id": runner_up["site_id"],
            "name": runner_up["name"],
            "score": runner_up["total"],
            "margin": round(winner["total"] - runner_up["total"], 3),
        },
        "pinpoint_mode_winner": {
            "site_id": pinpoint_ranked[0]["site_id"],
            "name": pinpoint_ranked[0]["name"],
            "score": pinpoint_ranked[0]["total"],
        },
        "profile_winners": profile_winners,
        "rationale": rationale,
        "caveats": caveats,
        "data_requests": data_requests,
        "method": {
            "criteria": [c["id"] for c in criteria],
            "baseline_weights": baseline_weights,
            "monte_carlo_draws": 5000,
            "monte_carlo_seed": 42,
            "uncertainty_model": {
                "weights": "+/-50% multiplicative, renormalised",
                "tier_A_B_scores_sd_points": 3.0,
                "tier_C_scores_sd_points": 10.0,
                "scores_clipped": [0, 100],
            },
        },
    }
    write_json(PROCESSED_DIR / "recommendation.json", recommendation)

    # GeoJSON: site points and pinpoint pads.
    site_features = []
    pinpoint_features = []
    baseline_by_site = {
        row["site_id"]: row for row in ranking_rows if row["mode"] == "site"
    }
    scores = scores_by_mode["site"]
    for site in sites:
        sid = site["site_id"]
        rank_row = baseline_by_site[sid]
        properties = {
            "site_id": sid,
            "name": site["name"],
            "rank": rank_row["rank"],
            "score": rank_row["score"],
            "top1_prob": rank_row["top1_prob"],
            "key_strength": rank_row["key_strength"],
            "key_weakness": rank_row["key_weakness"],
            "solar_score": scores[sid]["solar_illumination"]["subscore"],
            "earth_score": scores[sid]["earth_link"]["subscore"],
            "terrain_score": scores[sid]["terrain_trafficability"]["subscore"],
            "science_score": scores[sid]["science_value"]["subscore"],
            "isru_score": scores[sid]["isru_water_ice"]["subscore"],
            "pinpoint_lat_deg": terrain.get(sid, {}).get("pinpoint_lat_deg", ""),
            "pinpoint_lon_deg": terrain.get(sid, {}).get("pinpoint_lon_deg", ""),
        }
        site_features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [site["lon_deg"], site["lat_deg"]]},
                "properties": properties,
            }
        )
        if terrain.get(sid, {}).get("pinpoint_lat_deg"):
            pinpoint_features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [
                            float(terrain[sid]["pinpoint_lon_deg"]),
                            float(terrain[sid]["pinpoint_lat_deg"]),
                        ],
                    },
                    "properties": {
                        "site_id": sid,
                        "name": site["name"],
                        "offset_km": terrain[sid].get("pinpoint_offset_km", ""),
                        "slope_p90_deg": terrain[sid].get("pinpoint_slope_p90_deg", ""),
                        "horizon_mean_deg": terrain[sid].get("pinpoint_horizon_mean_deg", ""),
                    },
                }
            )
    write_json(
        PROCESSED_DIR / "sites.geojson",
        {"type": "FeatureCollection", "features": site_features},
    )
    write_json(
        PROCESSED_DIR / "pinpoints.geojson",
        {"type": "FeatureCollection", "features": pinpoint_features},
    )

    log(
        f"Primary winner: {winner['name']} {winner['total']:.1f} "
        f"(top1 {primary_sens[winner['site_id']]['top1_prob'] * 100:.1f}%); "
        f"runner-up {runner_up['name']} {runner_up['total']:.1f}"
    )
    log(f"Wrote scores, rankings, sensitivity and recommendation.json")


if __name__ == "__main__":
    main()
