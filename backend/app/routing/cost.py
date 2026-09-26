"""Transparent prototype environmental risk calculation.

The component normalisers and weights are explicitly labelled prototype-only.
They are applied only to recorded observations with a documented, compatible
value.  Missing, unavailable, or incompatible observations never become zero.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any


@dataclass(frozen=True)
class EnvironmentalInput:
    domain: str
    observation_id: str
    source_id: str
    status: str
    value: dict[str, Any]
    units: str
    retrieved_at: str
    valid_from: str | None
    valid_to: str | None
    distance_to_route_km: float


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and isfinite(float(value)):
        return float(value)
    return None


def _sea_ice(observation: EnvironmentalInput) -> tuple[float | None, str | None]:
    value = _number(observation.value.get("concentration"))
    if value is None:
        return None, "Recorded sea-ice observation has no numeric concentration"
    unit = observation.units.strip().lower()
    if unit in {"%", "percent", "percentage"} and 0.0 <= value <= 100.0:
        return value / 100.0, None
    if unit in {"1", "fraction", "unitless"} and 0.0 <= value <= 1.0:
        return value, None
    return None, "Sea-ice concentration units or range are incompatible with prototype normalisation"


def _speed(observation: EnvironmentalInput, keys: tuple[str, ...], maximum: float, label: str) -> tuple[float | None, str | None]:
    value = next((_number(observation.value.get(key)) for key in keys if _number(observation.value.get(key)) is not None), None)
    if value is None:
        return None, f"Recorded {label} observation has no numeric speed"
    if observation.units.strip().lower() not in {"m s-1", "m/s", "ms-1"} or value < 0.0:
        return None, f"{label.capitalize()} speed units or range are incompatible with prototype normalisation"
    return min(value / maximum, 1.0), None


def calculate_risk(observations: dict[str, EnvironmentalInput]) -> tuple[float | None, dict[str, Any], list[str]]:
    """Calculate a null-safe environmental risk score and provenance-rich details."""
    definitions = {
        "sea_ice": (0.50, lambda item: _sea_ice(item)),
        "weather": (0.30, lambda item: _speed(item, ("wind_speed", "speed"), 30.0, "wind")),
        "ocean": (0.20, lambda item: _speed(item, ("speed", "current_speed"), 2.0, "ocean current")),
    }
    components: dict[str, Any] = {"method": "prototype_normalised_environmental_risk_v1", "weights": {name: weight for name, (weight, _) in definitions.items()}, "domains": {}}
    weighted, active_weight, reasons = 0.0, 0.0, []
    for domain, (weight, normalise) in definitions.items():
        observation = observations.get(domain)
        if observation is None:
            components["domains"][domain] = {"availability": "UNAVAILABLE", "reason": "No relevant persisted observation"}
            reasons.append(f"{domain}: no relevant persisted observation")
            continue
        if observation.status not in {"LIVE", "STALE", "DEGRADED"}:
            components["domains"][domain] = {"availability": observation.status, "reason": "Observation status is not usable for scoring"}
            reasons.append(f"{domain}: observation status {observation.status}")
            continue
        score, reason = normalise(observation)
        if score is None:
            components["domains"][domain] = {"availability": "UNAVAILABLE", "reason": reason}
            reasons.append(f"{domain}: {reason}")
            continue
        components["domains"][domain] = {"availability": observation.status, "normalised_risk": score, "weight": weight}
        weighted += score * weight
        active_weight += weight
    if active_weight == 0.0:
        components["availability"] = "UNAVAILABLE"
        return None, components, reasons
    components["availability"] = "PARTIAL" if active_weight < 1.0 else "AVAILABLE"
    components["active_weight"] = active_weight
    # Renormalisation makes partial evidence explicit while avoiding a hidden
    # assumption that an unavailable domain has zero risk.
    return weighted / active_weight, components, reasons
