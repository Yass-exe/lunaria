#!/usr/bin/env python3
"""Fetch NASA api.nasa.gov and NASA Image Library metadata for the six sites.

The API key is read from .env and is never written into logs or data files.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from common import (
    ASSET_DIR,
    IMAGES_API_BASE,
    NASA_API_BASE,
    RAW_DIR,
    ensure_dirs,
    http_get,
    http_get_json,
    load_sites,
    log,
    nasa_api_key,
    write_csv,
    write_json,
    utc_now,
)

# One representative NASA Image Library asset per site, used by the dashboard.
# These are presentation-only and do not feed any score.
HERO_IMAGE = {
    "shackleton_rim": "PIA13523",
    "nobile_connecting_ridge": "PIA12905",
    "von_karman": "art002e012702",
    "marius_hills": "PIA12954",
    "vallis_schroteri": "PIA00090",
    "apollo17": "as17-140-21497",
}

# The NASA Image Library uses AND-matching and has uneven site-name coverage.
# Queries were checked against the live catalogue; each site keeps a direct
# query plus regional/context fallbacks that are known to return results.
IMAGE_QUERIES = {
    "shackleton_rim": [
        ("lunar south pole", "direct"),
        ("Moon south pole", "regional"),
        ("Shackleton crater Moon", "context"),
    ],
    "nobile_connecting_ridge": [
        ("lunar south pole", "direct"),
        ("Artemis lunar south pole", "regional"),
        ("Moon south pole", "context"),
    ],
    "von_karman": [
        ("Von Karman Moon", "direct"),
        ("lunar far side", "regional"),
        ("far side Moon", "context"),
    ],
    "marius_hills": [
        ("Marius Hills Moon", "direct"),
        ("Marius Hills", "regional"),
        ("lunar lava tube", "context"),
    ],
    "vallis_schroteri": [
        ("Cobra Head Moon", "direct"),
        ("Aristarchus", "regional"),
        ("Schroter Valley Moon", "context"),
    ],
    "apollo17": [
        ("Apollo 17", "direct"),
        ("Taurus-Littrow", "regional"),
        ("Apollo 17 landing site", "context"),
    ],
}

# The Image Library is a fuzzy full-text catalogue: "Shackleton" returns
# Antarctic ships and "von Karman" returns terrestrial cloud vortices. Keep
# only records whose title/keywords/description clearly refer to the Moon.
MOON_TERMS = ("moon", "lunar", "lro", "apollo", "artemis", "selene", "crater")
EXCLUDE_TERMS = (
    "earth observation", "earth limb", "vortices", "antarctica", "research ship",
    "briefing", "crew portrait", "emblem", "anniversary", "training", "hawaii",
    "cloud", "ocean", "island", "volcanic plume", "dust storm", "cassini",
)


def clean_text(value: str | None, limit: int = 600) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def fetch_apod(force: bool = False) -> None:
    out = RAW_DIR / "nasa" / "apod.json"
    if out.exists() and not force:
        log("APOD already cached")
        return
    try:
        payload = http_get_json(
            f"{NASA_API_BASE}/planetary/apod",
            {"api_key": nasa_api_key(), "thumbs": "true"},
        )
    except Exception as exc:  # APOD is illustrative, not a scoring input.
        log(f"APOD unavailable ({exc}); continuing with image-library metadata")
        return
    write_json(out, payload)
    log(f"APOD saved: {payload.get('title', 'unknown')!r} ({payload.get('date', '')})")


def is_moon_relevant(data: dict, site_id: str) -> bool:
    text = " ".join(
        [
            data.get("title") or "",
            data.get("description") or "",
            " ".join(data.get("keywords") or []),
        ]
    ).lower()
    if any(term in text for term in EXCLUDE_TERMS):
        return False
    if not any(term in text for term in MOON_TERMS):
        return False
    if site_id == "von_karman":
        return "von karman" in text or "far side" in text or "farside" in text
    return True


def fetch_images(site: dict, force: bool = False) -> list[dict]:
    site_id = site["site_id"]
    out = RAW_DIR / "nasa" / "images" / f"{site_id}.json"
    rows: list[dict] = []
    searches: list[dict] = []
    seen: set[str] = set()
    title_counts: dict[str, int] = {}

    for query, match_type in IMAGE_QUERIES[site_id]:
        if len(rows) >= 8:
            break
        payload = http_get_json(
            f"{IMAGES_API_BASE}/search",
            {"q": query, "media_type": "image", "page_size": 40},
        )
        collection = payload.get("collection", {})
        items = collection.get("items", []) or []
        total = (collection.get("metadata") or {}).get("total_hits", 0)
        searches.append({"query": query, "match_type": match_type, "total_hits": total})
        for item in items:
            data = (item.get("data") or [{}])[0]
            nasa_id = data.get("nasa_id")
            if not nasa_id or nasa_id in seen:
                continue
            seen.add(nasa_id)
            if not is_moon_relevant(data, site_id):
                continue
            title = clean_text(data.get("title"), 300)
            if title_counts.get(title, 0) >= 2:
                continue
            title_counts[title] = title_counts.get(title, 0) + 1
            links = item.get("links") or []
            preview = links[0].get("href", "") if links else ""
            rows.append(
                {
                    "site_id": site_id,
                    "nasa_id": nasa_id,
                    "title": title,
                    "date_created": data.get("date_created", ""),
                    "center": data.get("center", ""),
                    "photographer": data.get("photographer", ""),
                    "description": clean_text(data.get("description"), 700),
                    "keywords": "; ".join(data.get("keywords") or []),
                    "preview_url": preview,
                    "source_query": query,
                    "match_type": match_type,
                    "source_id": "SRC-IMG-01",
                }
            )
            if len(rows) >= 8:
                break
        time.sleep(0.4)

    write_json(out, {"site_id": site_id, "searches": searches, "items": rows})
    log(f"{site_id}: {len(rows)} relevant images from {len(searches)} queries")
    return rows


def download_hero_images(rows: list[dict]) -> None:
    """Cache one preview per site locally so the dashboard works offline."""
    by_key = {(row["site_id"], row["nasa_id"]): row for row in rows}
    out_dir = ASSET_DIR / "nasa"
    out_dir.mkdir(parents=True, exist_ok=True)
    for site_id, nasa_id in HERO_IMAGE.items():
        row = by_key.get((site_id, nasa_id))
        if not row or not row.get("preview_url"):
            log(f"{site_id}: no cached preview for {nasa_id}")
            continue
        url = row["preview_url"]
        suffix = ".jpg" if ".jpg" in url.lower() else ".png"
        out = out_dir / f"{site_id}{suffix}"
        try:
            out.write_bytes(http_get(url, timeout=60, retries=2))
            log(f"{site_id}: cached {nasa_id} preview")
        except Exception as exc:
            log(f"{site_id}: preview download failed ({exc})")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    ensure_dirs()

    fetch_apod(force=args.force)

    all_rows: list[dict] = []
    for site in load_sites():
        all_rows.extend(fetch_images(site, force=args.force))

    fieldnames = [
        "site_id",
        "nasa_id",
        "title",
        "date_created",
        "center",
        "photographer",
        "description",
        "keywords",
        "preview_url",
        "source_query",
        "match_type",
        "source_id",
    ]
    # Keep one row per NASA asset, preferring the earliest (most direct) query.
    deduped: dict[tuple[str, str], dict] = {}
    for row in all_rows:
        deduped.setdefault((row["site_id"], row["nasa_id"]), row)
    write_csv(RAW_DIR / "nasa" / "images.csv", list(deduped.values()), fieldnames)
    log(f"Wrote {len(deduped)} unique image records")
    download_hero_images(list(deduped.values()))

    write_json(
        RAW_DIR / "nasa" / "fetch_manifest.json",
        {
            "fetched_at": utc_now(),
            "api": "api.nasa.gov / planetary/apod and images-api.nasa.gov",
            "api_key_source": ".env (not persisted)",
            "sites": [s["site_id"] for s in load_sites()],
        },
    )


if __name__ == "__main__":
    main()
