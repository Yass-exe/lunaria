"""Shared utilities for the Lunaria lunar-site pipeline.

Standard library only. The project deliberately avoids heavy geospatial
dependencies so that it can be re-run on a bare Python 3 installation.
"""

from __future__ import annotations

import csv
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
INTERIM_DIR = DATA_DIR / "interim"
PROCESSED_DIR = DATA_DIR / "processed"
PLACEHOLDER_DIR = ROOT / "placeholders"
WEB_DIR = ROOT / "web"
ASSET_DIR = WEB_DIR / "assets"

USER_AGENT = "Lunaria/0.2 (lunar landing-site decision support; stdlib Python)"
NASA_API_BASE = "https://api.nasa.gov"
IMAGES_API_BASE = "https://images-api.nasa.gov"
HORIZONS_API = "https://ssd.jpl.nasa.gov/api/horizons.api"
TREK_BASE = "https://trek.nasa.gov/moon/trekarcgis/rest/services"

AU_KM = 149_597_870.700
C_KM_S = 299_792.458


def ensure_dirs() -> None:
    for path in (
        CONFIG_DIR,
        RAW_DIR / "nasa" / "images",
        RAW_DIR / "trek",
        RAW_DIR / "horizons",
        INTERIM_DIR,
        PROCESSED_DIR,
        PLACEHOLDER_DIR,
        ASSET_DIR,
        ROOT / "tests",
    ):
        path.mkdir(parents=True, exist_ok=True)


def load_env() -> dict[str, str]:
    """Load .env without adding a dependency. Existing environment wins."""
    values: dict[str, str] = {}
    env_path = ROOT / ".env"
    if env_path.exists():
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("'\"")
    for key, value in os.environ.items():
        if key.startswith(("NASA_", "LUNARIA_")):
            values[key] = value
    return values


def nasa_api_key() -> str:
    key = load_env().get("NASA_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "NASA_API_KEY is missing. Copy .env.example to .env and add a key."
        )
    return key


def log(message: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{stamp}Z] {message}", flush=True)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def redact_url(url: str) -> str:
    """Hide credentials (notably api_key) before logging or raising errors."""
    parsed = urllib.parse.urlsplit(url)
    if not parsed.query:
        return url
    pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    safe = [
        (key, "***" if key.lower() in {"api_key", "token", "key"} else value)
        for key, value in pairs
    ]
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(safe), parsed.fragment)
    )


def http_get(
    url: str,
    params: dict | None = None,
    *,
    timeout: int = 90,
    retries: int = 4,
    accept: str | None = None,
) -> bytes:
    """GET with retry/backoff. Returns raw bytes; callers decode as needed."""
    if params:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{urllib.parse.urlencode(params, doseq=True)}"
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept
    delay = 2.0
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in (408, 425, 429, 500, 502, 503, 504):
                raise
            retry_after = exc.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else delay
            log(f"HTTP {exc.code}; retrying in {wait:.0f}s ({attempt}/{retries})")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_error = exc
            wait = delay
            log(f"Network error ({exc}); retrying in {wait:.0f}s ({attempt}/{retries})")
        if attempt < retries:
            time.sleep(wait)
            delay = min(delay * 2, 30.0)
    raise RuntimeError(
        f"GET failed after {retries} attempts: {redact_url(url)}"
    ) from last_error


def http_get_json(url: str, params: dict | None = None, **kwargs):
    raw = http_get(url, params, accept="application/json", **kwargs)
    return json.loads(raw.decode("utf-8"))


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_sites() -> list[dict]:
    return read_json(CONFIG_DIR / "sites.json")


def load_elevations() -> dict[str, dict]:
    path = INTERIM_DIR / "site_elevations.json"
    if not path.exists():
        return {}
    payload = read_json(path)
    return payload.get("sites", payload)


def load_sites_enriched() -> list[dict]:
    """Config sites merged with the DEM elevation measured by fetch_terrain."""
    elevations = load_elevations()
    sites = load_sites()
    for site in sites:
        extra = elevations.get(site["site_id"], {})
        for key in ("elevation_m", "dem_service", "dem_label", "dem_res_m", "projection"):
            if extra.get(key) is not None:
                site[key] = extra[key]
        if site.get("elevation_m") is None:
            site["elevation_m"] = 0.0
    return sites


def load_criteria() -> list[dict]:
    return read_json(CONFIG_DIR / "criteria.json")["criteria"]


def load_profiles() -> dict[str, dict]:
    return read_json(CONFIG_DIR / "profiles.json")["profiles"]


def load_curated() -> dict[str, dict]:
    return read_json(CONFIG_DIR / "curated_scores.json")["sites"]


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def linear_score(value: float, low: float, high: float) -> float:
    """Map low->0, high->100. Works with reversed endpoints."""
    if high == low:
        return 50.0
    return clamp((value - low) / (high - low) * 100.0)


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = clamp(fraction, 0.0, 1.0) * (len(ordered) - 1)
    lo = int(position)
    hi = min(lo + 1, len(ordered) - 1)
    weight = position - lo
    return ordered[lo] * (1.0 - weight) + ordered[hi] * weight


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else float("nan")


def stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = mean(values)
    return (sum((v - avg) ** 2 for v in values) / (len(values) - 1)) ** 0.5


def circular_interp(profile: list[float | None], index: float) -> float:
    """Linear interpolation on a 360-bin circular profile."""
    i0 = int(index) % 360
    i1 = (i0 + 1) % 360
    frac = index - int(index)
    a = profile[i0]
    b = profile[i1]
    if a is None and b is None:
        return 0.0
    if a is None:
        return float(b)
    if b is None:
        return float(a)
    return float(a) * (1.0 - frac) + float(b) * frac


def seeded_rng(seed: int = 42) -> random.Random:
    return random.Random(seed)


def die(message: str, code: int = 1) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(code)
