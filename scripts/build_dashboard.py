#!/usr/bin/env python3
"""Build web/data.js for the static Lunaria dashboard.

The dashboard is plain HTML/CSS/JS so it opens from the filesystem without a
server or a build toolchain. This script is the only data bridge.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict

from common import (
    CONFIG_DIR,
    PROCESSED_DIR,
    WEB_DIR,
    log,
    read_csv,
    read_json,
    utc_now,
)

HERO_IMAGE = {
    "shackleton_rim": ("PIA13523", "The Lunar South Pole (LRO mosaic)"),
    "nobile_connecting_ridge": ("PIA12905", "Lunar South Pole — Out of the Shadows"),
    "von_karman": ("art002e012702", "Poynting and Keeler craters, lunar far side (context)"),
    "marius_hills": ("PIA12954", "Marius Hills pit — possible lava-tube skylight"),
    "vallis_schroteri": ("PIA00090", "Aristarchus crater and plateau, Clementine mosaic"),
    "apollo17": ("as17-140-21497", "Apollo 17 station 6 panoramic, Taurus-Littrow"),
}

CRITERION_ORDER = [
    "solar_illumination",
    "earth_link",
    "terrain_trafficability",
    "isru_water_ice",
    "science_value",
    "thermal_stability",
    "crew_safety",
    "data_maturity",
]


def num(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def intnum(value, default=0):
    parsed = num(value)
    return int(parsed) if parsed is not None else default


def pct(value, digits=1):
    parsed = num(value)
    return round(parsed * 100, digits) if parsed is not None else None


def load(path):
    return read_csv(path) if path.exists() else []


def main() -> None:
    sites_rows = load(PROCESSED_DIR / "sites.csv")
    terrain_rows = load(PROCESSED_DIR / "terrain_summary.csv")
    ephem_rows = load(PROCESSED_DIR / "ephemeris_summary.csv")
    psr_rows = load(PROCESSED_DIR / "psr_proximity.csv")
    score_rows = load(PROCESSED_DIR / "site_scores.csv")
    ranking_rows = load(PROCESSED_DIR / "site_ranking.csv")
    profile_rows = load(PROCESSED_DIR / "site_ranking_by_profile.csv")
    sensitivity_rows = load(PROCESSED_DIR / "sensitivity.csv")
    criteria_rows = load(PROCESSED_DIR / "criteria_scores.csv")
    gaps = load(PROCESSED_DIR / "data_gaps.csv")
    images = load(PROCESSED_DIR.parent / "raw" / "nasa" / "images.csv")
    sources = load(PROCESSED_DIR / "source_registry.csv")
    recommendation = read_json(PROCESSED_DIR / "recommendation.json")
    criteria = read_json(CONFIG_DIR / "criteria.json")["criteria"]
    profiles = read_json(CONFIG_DIR / "profiles.json")["profiles"]

    by_site = lambda rows, mode=None: {
        row["site_id"]: row
        for row in rows
        if mode is None or row.get("mode") == mode
    }

    terrain = by_site(terrain_rows)
    ephem = {
        row["site_id"]: row
        for row in ephem_rows
        if row.get("scenario") == "primary"
    }
    psr = by_site(psr_rows)
    score_site = by_site(score_rows, "site")
    score_pinpoint = by_site(score_rows, "pinpoint")
    ranking_site = {row["site_id"]: row for row in ranking_rows if row["mode"] == "site"}
    ranking_pinpoint = {
        row["site_id"]: row for row in ranking_rows if row["mode"] == "pinpoint"
    }
    sensitivity_site = {
        row["site_id"]: row for row in sensitivity_rows if row["mode"] == "site"
    }
    sensitivity_pinpoint = {
        row["site_id"]: row for row in sensitivity_rows if row["mode"] == "pinpoint"
    }
    criteria_lookup = {
        (row["mode"], row["site_id"], row["criterion_id"]): row
        for row in criteria_rows
    }

    image_by_key = {(row["site_id"], row["nasa_id"]): row for row in images}
    image_by_site = defaultdict(list)
    for row in images:
        image_by_site[row["site_id"]].append(row)

    site_payload = []
    for row in sites_rows:
        sid = row["site_id"]
        terr = terrain.get(sid, {})
        eph = ephem.get(sid, {})
        shadow = psr.get(sid, {})
        sc = score_site.get(sid, {})
        rank = ranking_site.get(sid, {})
        pin = score_pinpoint.get(sid, {})
        sens = sensitivity_site.get(sid, {})
        sub = {}
        for criterion in criteria:
            cid = criterion["id"]
            cell = criteria_lookup.get(("site", sid, cid), {})
            sub[cid] = {
                "score": num(cell.get("subscore"), 0.0),
                "tier": cell.get("tier", criterion.get("tier", "C")),
                "raw": cell.get("raw_value", ""),
                "unit": cell.get("raw_unit", ""),
                "rationale": cell.get("rationale", ""),
                "source_id": cell.get("source_id", ""),
                "contribution": num(cell.get("weighted_contribution"), 0.0),
            }
        nasa_id, photo_caption = HERO_IMAGE.get(
            sid, (image_by_site[sid][0]["nasa_id"] if image_by_site[sid] else "", "")
        )
        image_row = image_by_key.get((sid, nasa_id), {})
        site_payload.append(
            {
                "id": sid,
                "name": row["name"],
                "short_name": row["short_name"],
                "lat": num(row["lat_deg"]),
                "lon": num(row["lon_deg"]),
                "region": row["region"],
                "site_type": row["site_type"],
                "earth_side": row["earth_side"],
                "elevation_m": num(row["elevation_m"]),
                "dem_service": row["dem_service"],
                "dem_label": row["dem_label"],
                "dem_res_m": num(row["dem_res_m"]),
                "dem_source_id": row["dem_source_id"],
                "slope_median_deg": num(terr.get("slope_median_deg")),
                "slope_p90_deg": num(terr.get("slope_p90_deg")),
                "roughness_m": num(terr.get("roughness_m")),
                "relief_m": num(terr.get("relief_p95_p5_m")),
                "horizon_mean_deg": num(terr.get("horizon_mean_deg")),
                "horizon_max_deg": num(terr.get("horizon_max_deg")),
                "open_sky_frac_5deg": num(terr.get("open_sky_frac_5deg")),
                "solar_pct": pct(eph.get("sun_up_terrain_frac")),
                "solar_hours_lit": num(eph.get("sun_longest_lit_terrain_h")),
                "solar_hours_dark": num(eph.get("sun_longest_dark_terrain_h")),
                "earth_pct": pct(eph.get("earth_up5_terrain_frac")),
                "earth_outage_h": num(eph.get("earth_longest_outage_terrain5_h")),
                "earth_range_km": num(eph.get("earth_range_km_mean")),
                "light_time_s": num(eph.get("earth_light_time_s_mean")),
                "relay_required": eph.get("relay_required", ""),
                "psr_edge_km": num(shadow.get("psr_edge_km_approx")),
                "psr_feature": shadow.get("nearest_psr_feature", ""),
                "image_count": len(image_by_site.get(sid, [])),
                "science_focus": row.get("science_focus", ""),
                "heritage": row.get("heritage", ""),
                "notes": row.get("notes", ""),
                "photo": f"assets/nasa/{sid}.jpg",
                "photo_caption": photo_caption or image_row.get("title", ""),
                "photo_nasa_id": nasa_id,
                "photo_description": image_row.get("description", ""),
                "rank": intnum(rank.get("rank"), 99),
                "score": num(rank.get("score"), 0.0),
                "delta": num(rank.get("delta_to_best"), 0.0),
                "top1": num(sens.get("top1_prob"), 0.0),
                "top1_weights_only": num(sens.get("top1_prob_weight_only"), 0.0),
                "score_p10": num(sens.get("p10_score")),
                "score_p90": num(sens.get("p90_score")),
                "pinpoint_rank": intnum(ranking_pinpoint.get(sid, {}).get("rank"), 99),
                "pinpoint_score": num(pin.get("weighted_total")),
                "pinpoint": {
                    "lat": num(terr.get("pinpoint_lat_deg")),
                    "lon": num(terr.get("pinpoint_lon_deg")),
                    "offset_km": num(terr.get("pinpoint_offset_km")),
                    "elevation_m": num(terr.get("pinpoint_elev_m")),
                    "slope_deg": num(terr.get("pinpoint_slope_deg")),
                    "slope_p90_deg": num(terr.get("pinpoint_slope_p90_deg")),
                    "roughness_m": num(terr.get("pinpoint_roughness_m")),
                    "horizon_max_deg": num(terr.get("pinpoint_horizon_max_deg")),
                    "open_sky_frac_5deg": num(terr.get("pinpoint_open_sky_frac_5deg")),
                },
                "criteria": sub,
                "hillshade": f"assets/hillshade_{sid}.jpg",
            }
        )

    site_payload.sort(key=lambda item: item["rank"])

    profile_payload = {}
    for profile_id, profile in profiles.items():
        rows = [
            row
            for row in profile_rows
            if row["mode"] == "site" and row["profile_id"] == profile_id
        ]
        rows.sort(key=lambda row: intnum(row["rank"], 99))
        profile_payload[profile_id] = {
            "id": profile_id,
            "label": profile["label"],
            "description": profile["description"],
            "weights": profile["weights"],
            "ranking": [
                {
                    "site_id": row["site_id"],
                    "rank": intnum(row["rank"]),
                    "score": num(row["score"]),
                    "delta": num(row["delta_to_best"]),
                }
                for row in rows
            ],
        }

    gap_counts = Counter(row["dataset"] for row in gaps)
    priority_counts = Counter(row["priority"] for row in gaps)
    p0 = [row for row in gaps if row["priority"] == "P0"]
    gap_by_site = defaultdict(lambda: {"P0": 0, "P1": 0, "P2": 0, "P3": 0})
    for row in gaps:
        gap_by_site[row["site_id"]][row["priority"]] += 1

    ephemeris_count = sum(
        intnum(row.get("sun_samples")) + intnum(row.get("earth_samples"))
        for row in ephem.values()
    )
    window_start = next(iter(ephem.values()), {}).get("window_start", "")
    window_end = next(iter(ephem.values()), {}).get("window_end", "")

    source_payload = [
        {
            "id": row["source_id"],
            "name": row["name"],
            "type": row["type"],
            "url": row["url"],
            "status": row["status"],
            "credit": row["credit"],
            "notes": row["notes"],
        }
        for row in sources
    ]

    data = {
        "meta": {
            "generated_at": utc_now(),
            "window_start": window_start,
            "window_end": window_end,
            "site_count": len(site_payload),
            "ephemeris_rows": ephemeris_count,
            "dem_count": len({row["dem_service"] for row in sites_rows}),
            "monte_carlo_draws": recommendation.get("method", {})
            .get("monte_carlo_draws", 5000),
            "gap_count": len(gaps),
            "p0_count": len(p0),
            "source_count": len(source_payload),
            "image_count": len(images),
            "profile_count": len(profiles),
            "criteria_count": len(criteria),
        },
        "recommendation": recommendation,
        "sites": site_payload,
        "criteria": [
            {
                "id": c["id"],
                "label": c["label"],
                "short_label": c.get("short_label", c["label"]),
                "unit": c.get("unit", ""),
                "method": c.get("method", ""),
                "tier": c.get("tier", "C"),
                "source_id": c.get("source_id", ""),
                "description": c.get("description", ""),
                "caveat": c.get("caveat", ""),
            }
            for c in criteria
        ],
        "profiles": profile_payload,
        "baseline_profile": "baseline",
        "gaps": {
            "by_dataset": dict(gap_counts),
            "by_priority": dict(priority_counts),
            "by_site": {sid: counts for sid, counts in gap_by_site.items()},
            "p0": [
                {
                    "site_id": row["site_id"],
                    "dataset": row["dataset"],
                    "aoi": row["aoi"],
                    "request_spec": row["request_spec"],
                    "request_from": row["request_from"],
                    "why": row["why"],
                    "placeholder": row["placeholder_file"],
                }
                for row in p0
            ],
        },
        "images": [
            {
                "site_id": row["site_id"],
                "nasa_id": row["nasa_id"],
                "title": row["title"],
                "date": row["date_created"],
                "center": row["center"],
                "description": row["description"],
                "keywords": row["keywords"],
                "query": row["source_query"],
                "match_type": row["match_type"],
            }
            for row in images
        ],
        "sources": source_payload,
    }

    out = WEB_DIR / "data.js"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )
    out.write_text(
        "/* Generated by scripts/build_dashboard.py. Do not edit by hand. */\n"
        f"window.LUNARIA_DATA = {payload};\n",
        encoding="utf-8",
    )
    log(
        f"Wrote {out.relative_to(WEB_DIR.parent)}: {len(site_payload)} sites, "
        f"{len(criteria)} criteria, {len(gaps)} gaps, {len(images)} images"
    )


if __name__ == "__main__":
    main()
