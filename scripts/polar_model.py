#!/usr/bin/env python3
"""Normalized scoring, constraints, clustering, and sensitivity for polar cells."""

from __future__ import annotations

import math
import random
import json
from collections import deque
from dataclasses import dataclass
from pathlib import Path

DEFAULT_WEIGHTS = {
    "solar_power": 0.24,
    "earth_visibility": 0.20,
    "terrain_safety": 0.20,
    "isru_access": 0.16,
    "science_value": 0.10,
    "thermal_stability": 0.10,
}

SCORE_DIMENSIONS = tuple(DEFAULT_WEIGHTS)

@dataclass(frozen=True)
class ScoringPolicy:
    """Complete scoring policy supplied at the scoring seam.

    Runners load this from ``config/polar_scoring.json`` so utility definitions
    cannot silently diverge from the documented configuration.
    """

    weights: dict[str, float]
    solar_low: float = 0.04
    solar_high: float = 0.80
    dark_low_days: float = 0.0
    dark_high_days: float = 30.0
    earth_low: float = 0.0
    earth_high: float = 0.99
    regional_terrain_full_below: float = 5.0
    regional_terrain_zero_above: float = 15.0
    pinpoint_terrain_full_below: float = 5.0
    pinpoint_terrain_zero_above: float = 15.0
    isru_scale_km: float = 10.0
    slope_limit: float = 15.0
    solar_cutoff: float = 0.04
    geometric_floor: float = 0.01


DEFAULT_POLICY = ScoringPolicy(weights=dict(DEFAULT_WEIGHTS))


def clamp01(value: float) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("scores and metrics must be finite")
    return max(0.0, min(1.0, value))


def ramp_high(value: float, low: float, high: float) -> float:
    if not all(math.isfinite(float(v)) for v in (value, low, high)):
        raise ValueError("utility inputs must be finite")
    if high <= low:
        raise ValueError("high must exceed low")
    return clamp01((float(value) - low) / (high - low))


def ramp_low(value: float, low: float, high: float) -> float:
    return 1.0 - ramp_high(value, low, high)


def threshold_utility(value: float, *, full_below: float, zero_above: float) -> float:
    if not all(math.isfinite(float(v)) for v in (value, full_below, zero_above)):
        raise ValueError("threshold inputs must be finite")
    if zero_above <= full_below:
        raise ValueError("zero_above must exceed full_below")
    if value <= full_below:
        return 1.0
    if value >= zero_above:
        return 0.0
    return (zero_above - value) / (zero_above - full_below)


def _geometric_mean(values: list[float], floor: float) -> float:
    if not values:
        raise ValueError("geometric mean requires at least one value")
    return math.exp(sum(math.log(max(floor, clamp01(v))) for v in values) / len(values))


def normalize_indicators(
    metrics: dict,
    *,
    policy: ScoringPolicy | None = None,
    solar_cutoff: float | None = None,
    slope_limit: float | None = None,
) -> tuple[dict[str, float | None], list[str]]:
    """Return eight comparable display indicators and independently checked failures.

    Power submetrics and terrain scales are combined into their parent suitability
    dimensions later; the duplicate crew-safety display indicator is not weighted.
    """
    policy = DEFAULT_POLICY if policy is None else policy
    solar_cutoff = policy.solar_cutoff if solar_cutoff is None else solar_cutoff
    slope_limit = policy.slope_limit if slope_limit is None else slope_limit

    illumination = metrics.get("solar_illumination_fraction")
    dark_days = metrics.get("longest_dark_days")
    continuous = metrics.get("sunlight_continuity_fraction")
    earth = metrics.get("earth_visibility_fraction")
    regional_slope = metrics.get("regional_slope_p90_deg")
    pinpoint_slope = metrics.get("pinpoint_slope_p90_deg")
    psr_distance = metrics.get("psr_edge_km")
    science = metrics.get("science_proxy")
    thermal = metrics.get("thermal_proxy")
    coverage = metrics.get("data_coverage_fraction")

    illumination_u = (
        None
        if illumination is None
        else ramp_high(illumination, policy.solar_low, policy.solar_high)
    )
    dark_u = (
        None
        if dark_days is None
        else ramp_low(dark_days, policy.dark_low_days, policy.dark_high_days)
    )
    # Continuity is reported in the cell table but not folded into solar_power:
    # at the pole it is almost always ~0 for the same physical reason as the
    # dark period, and geometric-meaning all three would triple-count one
    # monthly shadowing signal and compress every score toward zero.
    power_parts = [v for v in (illumination_u, dark_u) if v is not None]
    solar_power = _geometric_mean(power_parts, 0.01) if power_parts else None
    earth_u = (
        None
        if earth is None
        else ramp_high(earth, policy.earth_low, policy.earth_high)
    )

    regional_u = (
        None
        if regional_slope is None
        else threshold_utility(
            regional_slope,
            full_below=policy.regional_terrain_full_below,
            zero_above=policy.regional_terrain_zero_above,
        )
    )
    pinpoint_u = (
        None
        if pinpoint_slope is None
        else threshold_utility(
            pinpoint_slope,
            full_below=policy.pinpoint_terrain_full_below,
            zero_above=policy.pinpoint_terrain_zero_above,
        )
    )
    terrain_parts = [v for v in (regional_u, pinpoint_u) if v is not None]
    terrain_u = _geometric_mean(terrain_parts, 0.01) if terrain_parts else None
    isru_u = (
        None
        if psr_distance is None
        else math.exp(-max(0.0, float(psr_distance)) / policy.isru_scale_km)
    )
    science_u = None if science is None else clamp01(science)
    thermal_u = None if thermal is None else clamp01(thermal)
    maturity_u = None if coverage is None else clamp01(coverage)

    indicators: dict[str, float | None] = {
        "solar_power": solar_power,
        "earth_visibility": earth_u,
        "terrain_safety": terrain_u,
        "isru_access_proxy": isru_u,
        "science_proxy": science_u,
        "thermal_proxy": thermal_u,
        "crew_safety": terrain_u,
        "data_maturity": maturity_u,
    }

    failures = []
    if pinpoint_slope is not None and pinpoint_slope > slope_limit:
        failures.append("pinpoint_slope_over_limit")
    # Solar is applied after slope/other hard constraints in score_candidate.
    if illumination is not None and illumination < solar_cutoff:
        failures.append("solar_below_cutoff")
    return indicators, failures


def _weights(weights: dict[str, float]) -> dict[str, float]:
    if set(weights) != set(SCORE_DIMENSIONS):
        raise ValueError(f"weights must have exactly {SCORE_DIMENSIONS}")
    if any(not math.isfinite(float(value)) or float(value) < 0 for value in weights.values()):
        raise ValueError("weights must be finite and non-negative")
    total = sum(float(weights[key]) for key in SCORE_DIMENSIONS)
    if total <= 0:
        raise ValueError("at least one weight must be positive")
    return {key: float(weights[key]) / total for key in SCORE_DIMENSIONS}


def load_scoring_policy(path: Path) -> ScoringPolicy:
    """Load and validate the single documented scoring policy."""
    config = json.loads(path.read_text(encoding="utf-8"))
    utilities = config["utilities"]
    assumptions = config["assumptions"]
    scoring = config["scoring"]
    continuity = utilities["sunlight_continuity"]
    if not continuity.get("report_only") or continuity.get("weighted", True):
        raise ValueError("sunlight continuity must be explicitly report-only")
    policy = ScoringPolicy(
        weights=_weights(config["weights"] or DEFAULT_WEIGHTS),
        solar_low=float(utilities["solar_illumination"]["low"]),
        solar_high=float(utilities["solar_illumination"]["high"]),
        dark_low_days=float(utilities["longest_dark_period"]["low_days"]),
        dark_high_days=float(utilities["longest_dark_period"]["high_days"]),
        earth_low=float(utilities["earth_visibility"]["low"]),
        earth_high=float(utilities["earth_visibility"]["high"]),
        regional_terrain_full_below=float(
            utilities["regional_terrain_roughness"]["full_below"]
        ),
        regional_terrain_zero_above=float(
            utilities["regional_terrain_roughness"]["zero_above"]
        ),
        pinpoint_terrain_full_below=float(
            utilities["pinpoint_slope"]["full_below"]
        ),
        pinpoint_terrain_zero_above=float(
            utilities["pinpoint_slope"]["zero_above"]
        ),
        isru_scale_km=float(utilities["isru_access"]["scale_km"]),
        slope_limit=float(assumptions["slope_p90_limit_deg"]),
        solar_cutoff=float(assumptions["solar_illumination_min_fraction"]),
        geometric_floor=float(scoring["geometric_floor"]),
    )
    if policy.dark_high_days <= policy.dark_low_days:
        raise ValueError("dark-period utility high_days must exceed low_days")
    if policy.isru_scale_km <= 0:
        raise ValueError("ISRU distance scale must be positive")
    return policy


def combine_scores(
    dimensions: dict[str, float],
    weights: dict[str, float] | None = None,
    *,
    geometric_floor: float = 0.01,
) -> dict[str, float]:
    """Calculate weighted sum and weighted geometric mean on [0,1]."""
    if not math.isfinite(geometric_floor) or not 0 < geometric_floor <= 1:
        raise ValueError("geometric_floor must be finite and in (0, 1]")
    weights = _weights(DEFAULT_WEIGHTS if weights is None else weights)
    if any(key not in dimensions for key in SCORE_DIMENSIONS):
        raise ValueError("all independent score dimensions are required")
    values = {key: clamp01(dimensions[key]) for key in SCORE_DIMENSIONS}
    weighted_sum = sum(weights[key] * values[key] for key in SCORE_DIMENSIONS)
    weighted_geometric = math.exp(
        sum(
            weights[key] * math.log(max(geometric_floor, values[key]))
            for key in SCORE_DIMENSIONS
        )
    )
    return {
        "weighted_sum": weighted_sum,
        "weighted_geometric_mean": weighted_geometric,
    }


def apply_hard_constraints(
    metrics: dict,
    *,
    slope_limit: float = 15.0,
    solar_cutoff: float = 0.04,
) -> list[str]:
    """Slope is checked first; solar cutoff is evaluated only if it passes."""
    if not math.isfinite(slope_limit) or not math.isfinite(solar_cutoff):
        raise ValueError("hard-constraint thresholds must be finite")
    failures = []
    slope = metrics.get("pinpoint_slope_p90_deg")
    if slope is not None:
        slope = float(slope)
        if not math.isfinite(slope):
            raise ValueError("pinpoint slope must be finite")
        if slope > slope_limit:
            failures.append("pinpoint_slope_over_limit")
    if not failures:
        illumination = metrics.get("solar_illumination_fraction")
        if illumination is not None:
            illumination = float(illumination)
            if not math.isfinite(illumination):
                raise ValueError("solar illumination must be finite")
            if illumination < solar_cutoff:
                failures.append("solar_below_cutoff")
    return failures


def score_candidate(
    metrics: dict,
    weights: dict[str, float] | None = None,
    *,
    policy: ScoringPolicy | None = None,
    slope_limit: float | None = None,
    solar_cutoff: float | None = None,
    geometric_floor: float | None = None,
) -> dict:
    policy = DEFAULT_POLICY if policy is None else policy
    slope_limit = policy.slope_limit if slope_limit is None else slope_limit
    solar_cutoff = policy.solar_cutoff if solar_cutoff is None else solar_cutoff
    geometric_floor = (
        policy.geometric_floor if geometric_floor is None else geometric_floor
    )
    indicators, _ = normalize_indicators(
        metrics,
        policy=policy,
        solar_cutoff=solar_cutoff,
        slope_limit=slope_limit,
    )
    failures = apply_hard_constraints(
        metrics, slope_limit=slope_limit, solar_cutoff=solar_cutoff
    )
    required = {
        "solar_power": indicators["solar_power"],
        "earth_visibility": indicators["earth_visibility"],
        "terrain_safety": indicators["terrain_safety"],
        "isru_access": indicators["isru_access_proxy"],
        "science_value": indicators["science_proxy"],
        "thermal_stability": indicators["thermal_proxy"],
    }
    missing = [key for key, value in required.items() if value is None]
    if missing:
        raise ValueError(f"missing suitability inputs: {', '.join(missing)}")
    scores = combine_scores(
        {key: float(value) for key, value in required.items()},
        policy.weights if weights is None else weights,
        geometric_floor=geometric_floor,
    )
    if failures:
        scores = {key: 0.0 for key in scores}
    return {
        **scores,
        "indicators": indicators,
        "hard_failures": failures,
        "disqualified": bool(failures),
    }


def cluster_cells(cells: list[dict], *, connectivity: int = 8) -> list[list[dict]]:
    """Cluster adjacent raster-cell records by integer (row, col) coordinates."""
    if connectivity not in (4, 8):
        raise ValueError("connectivity must be 4 or 8")
    by_position = {(int(c["row"]), int(c["col"])): c for c in cells}
    unseen = set(by_position)
    offsets = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    if connectivity == 8:
        offsets += [(-1, -1), (-1, 1), (1, -1), (1, 1)]
    clusters = []
    while unseen:
        seed = unseen.pop()
        queue = deque([seed])
        cluster = [by_position[seed]]
        while queue:
            row, col = queue.popleft()
            for dr, dc in offsets:
                pos = (row + dr, col + dc)
                if pos in unseen:
                    unseen.remove(pos)
                    queue.append(pos)
                    cluster.append(by_position[pos])
        clusters.append(cluster)
    clusters.sort(
        key=lambda cluster: (
            -max(float(c["score"]) for c in cluster),
            min(int(c["row"]) for c in cluster),
            min(int(c["col"]) for c in cluster),
        )
    )
    return clusters


def rank_agreement(rank_a: list[str], rank_b: list[str]) -> dict[str, float | int]:
    """Return top-rank match, exact order match, and Spearman rank correlation."""
    if len(rank_a) != len(rank_b) or set(rank_a) != set(rank_b):
        raise ValueError("rankings must contain the same unique candidate IDs")
    n = len(rank_a)
    if n < 2:
        return {"top_rank_match": int(rank_a == rank_b), "exact_order_match": int(rank_a == rank_b), "spearman_rho": 1.0}
    pos_a = {key: i + 1 for i, key in enumerate(rank_a)}
    pos_b = {key: i + 1 for i, key in enumerate(rank_b)}
    d2 = sum((pos_a[key] - pos_b[key]) ** 2 for key in rank_a)
    rho = 1.0 - 6.0 * d2 / (n * (n * n - 1))
    return {
        "top_rank_match": int(rank_a[0] == rank_b[0]),
        "exact_order_match": int(rank_a == rank_b),
        "spearman_rho": rho,
    }


def dirichlet_sensitivity(
    candidates: list[dict],
    *,
    draws: int = 1000,
    alpha: float = 1.0,
    seed: int = 42,
) -> list[dict]:
    """Estimate each candidate's top-rank share under Dirichlet weight variation."""
    if draws <= 0 or alpha <= 0:
        raise ValueError("draws and alpha must be positive")
    if not candidates:
        return []
    rng = random.Random(seed)
    counts = {str(c["candidate_id"]): 0 for c in candidates}
    for _ in range(draws):
        raw = [rng.gammavariate(alpha, 1.0) for _ in SCORE_DIMENSIONS]
        total = sum(raw)
        sampled = {key: value / total for key, value in zip(SCORE_DIMENSIONS, raw)}
        ranked = sorted(
            candidates,
            key=lambda c: (
                -(
                    0.0
                    if c.get("disqualified", False)
                    else combine_scores(c["dimensions"], sampled)[
                        "weighted_geometric_mean"
                    ]
                ),
                str(c["candidate_id"]),
            ),
        )
        if not ranked[0].get("disqualified", False):
            counts[str(ranked[0]["candidate_id"])] += 1
    return [
        {
            "candidate_id": key,
            "top1_probability": counts[key] / draws,
            "draws": draws,
            "method": f"Dirichlet({alpha:g})",
            "seed": seed,
        }
        for key in counts
    ]
