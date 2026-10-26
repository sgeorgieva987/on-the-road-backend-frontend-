from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from app.models import Destination

BASE_WEIGHTS = {"interest": 0.60, "proximity": 0.15, "budget": 0.15, "lesser_known": 0.10}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km; it is not a road distance."""
    earth_radius_km = 6371.0088
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    return 2 * earth_radius_km * asin(min(1.0, sqrt(a)))


def _interest_score(destination: Destination, interests: list[str], weights: dict[str, float]) -> float | None:
    if not interests and not weights:
        return None
    normalized_weights = {k.casefold(): max(0.0, v) for k, v in weights.items()}
    if not normalized_weights:
        normalized_weights = {item.casefold(): 1.0 for item in interests}
    total = sum(normalized_weights.values())
    if total <= 0:
        return None
    destination_terms = {str(x).casefold() for x in (destination.categories or []) + (destination.tags or [])}
    matched = sum(weight for term, weight in normalized_weights.items() if term in destination_terms or any(term in entry or entry in term for entry in destination_terms))
    return max(0.0, min(1.0, matched / total))



def combine_profile_and_trip_interests(
    profile_interests: list[str] | None,
    profile_weights: dict[str, float] | None,
    trip_interests: list[str] | None,
    trip_weights: dict[str, float] | None = None,
) -> tuple[list[str], dict[str, float]]:
    """Blend explicitly saved preferences with interests checked for this trip.

    The current-trip choices receive 65% of the interest weight and saved
    profile preferences 35%. If only one group is present, it receives all
    weight. This is transparent, deterministic personalization—not behavioral
    tracking or a trained ML model.
    """
    profile = [str(item).strip() for item in (profile_interests or []) if str(item).strip()]
    trip = [str(item).strip() for item in (trip_interests or []) if str(item).strip()]
    saved_weights = profile_weights or {}
    current_weights = trip_weights or {}

    def normalize(items: list[str], supplied: dict[str, float]) -> dict[str, float]:
        by_key = {str(k).casefold(): max(0.0, float(v)) for k, v in supplied.items()}
        weights = {item.casefold(): by_key.get(item.casefold(), 1.0) for item in items}
        total = sum(weights.values())
        if total <= 0 and items:
            return {item.casefold(): 1.0 / len(items) for item in items}
        return {key: value / total for key, value in weights.items()} if total else {}

    profile_normalized = normalize(profile, saved_weights)
    trip_normalized = normalize(trip, current_weights)
    if profile_normalized and trip_normalized:
        combined: dict[str, float] = {}
        for key, weight in profile_normalized.items():
            combined[key] = combined.get(key, 0.0) + 0.35 * weight
        for key, weight in trip_normalized.items():
            combined[key] = combined.get(key, 0.0) + 0.65 * weight
    elif trip_normalized:
        combined = trip_normalized
    else:
        combined = profile_normalized
    interests = list(dict.fromkeys(profile + trip))
    return interests, combined


def rank_destination(
    destination: Destination,
    *, interests: list[str] | None = None,
    interest_weights: dict[str, float] | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    budget_eur: float | None = None,
    prefers_lesser_known: bool = False,
) -> tuple[float, list[str]]:
    interests = interests or []
    interest_weights = interest_weights or {}
    components: list[tuple[float, float, str]] = []
    interest_score = _interest_score(destination, interests, interest_weights)
    if interest_score is not None:
        components.append((BASE_WEIGHTS["interest"], interest_score, "matches your interests" if interest_score > 0 else "limited interest match"))
    if latitude is not None and longitude is not None:
        distance = haversine_km(latitude, longitude, destination.latitude, destination.longitude)
        proximity_score = 1 / (1 + distance / 100)
        components.append((BASE_WEIGHTS["proximity"], proximity_score, f"about {distance:.0f} km away geographically"))
    if budget_eur is not None:
        if destination.estimated_cost_eur is None:
            budget_score = 0.5  # Neutral score for ranking only; itinerary hard constraints exclude unknown cost.
            reason = "estimated cost is not available"
        else:
            budget_score = 1.0 if destination.estimated_cost_eur <= budget_eur else 0.0
            reason = "fits the stated budget estimate" if budget_score else "may exceed the stated budget"
        components.append((BASE_WEIGHTS["budget"], budget_score, reason))
    if prefers_lesser_known:
        popular_tags = {"popular", "well-known", "famous", "масов туризъм"}
        lesser_known_score = 0.3 if popular_tags.intersection({t.casefold() for t in destination.tags or []}) else 1.0
        components.append((BASE_WEIGHTS["lesser_known"], lesser_known_score, "may suit a preference for lesser-known places" if lesser_known_score > .5 else "is a popular destination"))
    if not components:
        return 0.5, ["general destination suggestion; add interests to personalize results"]
    used_weight = sum(weight for weight, _, _ in components)
    score = sum(weight * value for weight, value, _ in components) / used_weight if used_weight else 0.5
    return round(max(0.0, min(1.0, score)), 4), [reason for _, value, reason in components if value > 0][:4]


def passes_hard_filters(
    destination: Destination,
    *, latitude: float | None,
    longitude: float | None,
    radius_km: float | None,
    budget_eur: float | None,
    travel_date: datetime | None,
    include_unverified: bool,
) -> bool:
    if not include_unverified and destination.verification_status != "verified":
        return False
    if radius_km is not None and latitude is not None and longitude is not None:
        if haversine_km(latitude, longitude, destination.latitude, destination.longitude) > radius_km:
            return False
    if budget_eur is not None:
        # Treat unknown prices as unavailable for a strict budget constraint.
        if destination.estimated_cost_eur is None or destination.estimated_cost_eur > budget_eur:
            return False
    if travel_date is not None and destination.seasonal_months:
        month = travel_date.month
        if month not in destination.seasonal_months:
            return False
    return True
