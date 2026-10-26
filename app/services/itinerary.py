from datetime import datetime
from app.models import Destination
from app.schemas import PlannerRequest, PlannerOut, PlannedStop
from app.services.recommender import haversine_km, passes_hard_filters, rank_destination


def estimated_leg(distance_geo_km: float, transport_mode: str) -> tuple[float, int]:
    """Fallback estimates only; replace with a routing provider before production."""
    if transport_mode == "car":
        estimated_road_km = distance_geo_km * 1.25
        minutes = round(estimated_road_km / 45 * 60 + (4 if estimated_road_km > 0 else 0))
        return estimated_road_km, max(1, minutes)
    # Pedestrian paths are not straight lines; this is a coarse distance proxy.
    walking_km = distance_geo_km * 1.2
    minutes = round(walking_km / 4.2 * 60)
    return walking_km, max(1, minutes)


def generate_itinerary(destinations: list[Destination], request: PlannerRequest) -> PlannerOut:
    if request.transport_mode == "train":
        raise ValueError("Train itineraries are not calculated yet because verified BDZ timetables and transfers are not integrated. Select car/walking, then verify train options directly with BDZ.")
    start_lat, start_lon = request.start_latitude, request.start_longitude
    candidates = [d for d in destinations if passes_hard_filters(
        d,
        latitude=start_lat,
        longitude=start_lon,
        radius_km=request.radius_km,
        budget_eur=request.budget_eur,
        travel_date=request.travel_date,
        include_unverified=request.include_unverified,
    )]
    current_lat, current_lon = start_lat, start_lon
    elapsed = 0
    total_cost = 0.0
    cost_known = True
    total_distance = 0.0
    stops: list[PlannedStop] = []
    remaining = request.available_time_minutes

    while candidates and len(stops) < request.max_destinations:
        viable: list[tuple[float, Destination, float, int, float]] = []
        for destination in candidates:
            geo_km = haversine_km(current_lat, current_lon, destination.latitude, destination.longitude)
            route_km, travel_minutes = estimated_leg(geo_km, request.transport_mode)
            cost = destination.estimated_cost_eur
            if request.budget_eur is not None and cost is None:
                continue
            if cost is not None and request.budget_eur is not None and total_cost + cost > request.budget_eur:
                continue
            return_leg_km = return_leg_minutes = 0
            if request.return_to_start:
                ret_geo = haversine_km(destination.latitude, destination.longitude, start_lat, start_lon)
                return_leg_km, return_leg_minutes = estimated_leg(ret_geo, request.transport_mode)
            visit = destination.estimated_visit_minutes
            if elapsed + travel_minutes + visit + return_leg_minutes > request.available_time_minutes:
                continue
            score, _ = rank_destination(
                destination,
                interests=request.interests,
                interest_weights=request.interest_weights,
                latitude=start_lat,
                longitude=start_lon,
                budget_eur=request.budget_eur,
            )
            # A stable deterministic tie-breaker mildly favors closer options.
            utility = score / (1 + travel_minutes / 240)
            viable.append((utility, destination, route_km, travel_minutes, score))
        if not viable:
            break
        viable.sort(key=lambda item: (-item[0], item[3], item[1].name.casefold()))
        _, chosen, leg_km, leg_minutes, score = viable[0]
        visit_minutes = chosen.estimated_visit_minutes
        stops.append(PlannedStop(
            order=len(stops) + 1,
            destination=chosen,
            distance_from_previous_km=round(leg_km, 1),
            travel_minutes_from_previous=leg_minutes,
            visit_minutes=visit_minutes,
            estimated_cost_eur=chosen.estimated_cost_eur,
            recommendation_score=score,
        ))
        elapsed += leg_minutes + visit_minutes
        total_distance += leg_km
        if chosen.estimated_cost_eur is None:
            cost_known = False
        else:
            total_cost += chosen.estimated_cost_eur
        current_lat, current_lon = chosen.latitude, chosen.longitude
        candidates = [d for d in candidates if d.id != chosen.id]

    if request.return_to_start and stops:
        last = stops[-1].destination
        geo_km = haversine_km(last.latitude, last.longitude, start_lat, start_lon)
        return_km, return_minutes = estimated_leg(geo_km, request.transport_mode)
        if elapsed + return_minutes <= request.available_time_minutes:
            elapsed += return_minutes
            total_distance += return_km
        else:
            # Drop stops from the end until the return journey also fits.
            while stops and elapsed + return_minutes > request.available_time_minutes:
                removed = stops.pop()
                elapsed -= removed.travel_minutes_from_previous + removed.visit_minutes
                total_distance -= removed.distance_from_previous_km
                if removed.estimated_cost_eur is not None:
                    total_cost -= removed.estimated_cost_eur
                if stops:
                    last = stops[-1].destination
                    geo_km = haversine_km(last.latitude, last.longitude, start_lat, start_lon)
                    return_km, return_minutes = estimated_leg(geo_km, request.transport_mode)
                else:
                    return_km = return_minutes = 0
            if stops:
                elapsed += return_minutes
                total_distance += return_km

    warnings = ["Travel times and distances are rough estimates from geographic coordinates, not verified road or walking routes."]
    warnings.append("Opening hours, events, accessibility, and live transport conditions are not checked by this MVP.")
    if any(stop.destination.verification_status != "verified" for stop in stops):
        warnings.append("One or more stops have not been editorially verified. Check official sources before travelling.")
    if not stops:
        warnings.append("No destinations met all hard constraints within the available time and budget.")
    return PlannerOut(
        transport_mode=request.transport_mode,
        available_time_minutes=request.available_time_minutes,
        estimated_total_minutes=elapsed,
        estimated_total_cost_eur=round(total_cost, 2) if cost_known else None,
        total_route_distance_km=round(total_distance, 1),
        returns_to_start=request.return_to_start,
        warnings=warnings,
        stops=stops,
    )

# Real routing and manually selected destination routes are implemented below;
# the original greedy planner above remains the candidate selector for the MVP.
from app.core.config import settings
from app.services.google_maps import GoogleRoutesError, build_google_maps_url, compute_google_route


def _nearest_neighbor_order(destinations: list[Destination], start_lat: float, start_lon: float) -> list[Destination]:
    """Reasonable no-key ordering for a manually selected multi-stop route."""
    remaining = list(destinations)
    ordered: list[Destination] = []
    lat, lon = start_lat, start_lon
    while remaining:
        nearest = min(remaining, key=lambda item: (haversine_km(lat, lon, item.latitude, item.longitude), item.name.casefold()))
        ordered.append(nearest)
        remaining.remove(nearest)
        lat, lon = nearest.latitude, nearest.longitude
    return ordered


def build_route_output(
    destinations: list[Destination],
    request: PlannerRequest,
    *,
    recommendation_scores: dict[int, float] | None = None,
    base_warnings: list[str] | None = None,
    nearest_neighbor_fallback: bool = False,
    preserve_all_stops: bool = True,
) -> PlannerOut:
    """Calculate route metrics, use Google Routes when configured, and create a Maps URL.

    With no server key (or if Google returns an error), all selected stops are
    retained and the service clearly labels the distances and times as estimates.
    The Google Maps URL is still available because Maps URLs need no API key.
    """
    if request.transport_mode == "train":
        raise ValueError("Train itineraries are not calculated yet because verified BDZ timetables and transfers are not integrated. Select car/walking, then verify train options directly with BDZ.")
    warnings = list(base_warnings or [])
    scores = recommendation_scores or {}
    for d in destinations:
        if d.verification_status != "verified":
            warnings.append("One or more stops have not been editorially verified. Check official sources before travelling.")
            break

    google_result = None
    routing_error: str | None = None
    if destinations and settings.google_routes_api_key:
        try:
            google_result = compute_google_route(
                request.start_latitude,
                request.start_longitude,
                destinations,
                transport_mode=request.transport_mode,
                return_to_start=request.return_to_start,
            )
        except GoogleRoutesError as exc:
            routing_error = str(exc)

    if google_result is not None:
        warnings = [w for w in warnings if "rough estimates from geographic coordinates" not in w]
        ordered = google_result.ordered_destinations
        leg_distances = google_result.leg_distance_km
        leg_minutes = google_result.leg_travel_minutes
        route_distance = google_result.total_distance_km
        drive_minutes = google_result.total_travel_minutes
        route_is_estimate = False
        route_provider = "google_routes_api"
        route_polyline = google_result.encoded_polyline
        warnings.append("Разстоянията и времената за придвижване са изчислени от Google Maps Routes API; посещенията на обектите са добавени отделно. Трафикът в реално време не е гарантиран.")
    else:
        if nearest_neighbor_fallback and destinations:
            ordered = _nearest_neighbor_order(destinations, request.start_latitude, request.start_longitude)
        else:
            ordered = list(destinations)
        leg_distances = []
        leg_minutes = []
        current_lat, current_lon = request.start_latitude, request.start_longitude
        route_distance = 0.0
        drive_minutes = 0
        for destination in ordered:
            geo_km = haversine_km(current_lat, current_lon, destination.latitude, destination.longitude)
            leg_km, minutes = estimated_leg(geo_km, request.transport_mode)
            leg_distances.append(round(leg_km, 1))
            leg_minutes.append(minutes)
            route_distance += leg_km
            drive_minutes += minutes
            current_lat, current_lon = destination.latitude, destination.longitude
        if request.return_to_start and ordered:
            geo_km = haversine_km(current_lat, current_lon, request.start_latitude, request.start_longitude)
            return_km, return_minutes = estimated_leg(geo_km, request.transport_mode)
            route_distance += return_km
            drive_minutes += return_minutes
        route_is_estimate = True
        route_provider = "estimated_fallback"
        route_polyline = None
        if not destinations:
            pass
        elif routing_error:
            warnings.append(f"Google Maps Routes API не беше достъпен; показан е ориентировъчен резервен маршрут. {routing_error}")
        elif not settings.google_routes_api_key:
            warnings.append("GOOGLE_ROUTES_API_KEY не е конфигуриран. Разстоянията и времената са приблизителни; линкът към Google Maps отваря всички спирки в зададения ред.")
        else:
            warnings.append("Не беше получен проверим маршрут от Google Maps; използвани са приблизителни оценки.")

    planned_stops: list[PlannedStop] = []
    visit_minutes = 0
    total_cost = 0.0
    costs_known = True
    for index, destination in enumerate(ordered):
        visit_minutes += destination.estimated_visit_minutes
        if destination.estimated_cost_eur is None:
            costs_known = False
        else:
            total_cost += destination.estimated_cost_eur
        planned_stops.append(PlannedStop(
            order=index + 1,
            destination=destination,
            distance_from_previous_km=leg_distances[index] if index < len(leg_distances) else 0.0,
            travel_minutes_from_previous=leg_minutes[index] if index < len(leg_minutes) else 0,
            visit_minutes=destination.estimated_visit_minutes,
            estimated_cost_eur=destination.estimated_cost_eur,
            recommendation_score=float(scores.get(destination.id, 0.5)),
        ))

    total_minutes = drive_minutes + visit_minutes
    if not ordered:
        warnings.append("Няма избрани или подходящи дестинации за този маршрут.")
    if preserve_all_stops and ordered and total_minutes > request.available_time_minutes:
        warnings.append(f"Избраните места остават в маршрута, но общото време ({total_minutes} мин) надвишава зададения лимит ({request.available_time_minutes} мин). Премахни спирки или увеличи времето.")
    if preserve_all_stops and ordered and request.budget_eur is not None:
        unknown_prices = any(destination.estimated_cost_eur is None for destination in ordered)
        known_cost = sum(destination.estimated_cost_eur or 0.0 for destination in ordered)
        if unknown_prices:
            warnings.append("Цените за част от избраните места липсват, затова общият бюджет не може да бъде потвърден.")
        if known_cost > request.budget_eur:
            warnings.append(f"Избраните места имат известни ориентировъчни разходи €{known_cost:.2f}, над зададения бюджет €{request.budget_eur:.2f}; спирките са запазени по твой избор.")
    if not ordered and not any("Няма избрани" in warning for warning in warnings):
        warnings.append("No destinations met all hard constraints within the available time and budget.")

    maps_url = build_google_maps_url(
        request.start_latitude,
        request.start_longitude,
        ordered,
        transport_mode=request.transport_mode,
        return_to_start=request.return_to_start,
    )
    maps_waypoint_count = len(ordered) if request.return_to_start else max(0, len(ordered) - 1)
    if maps_waypoint_count > 3:
        warnings.append("Забележка: Google Maps документацията посочва до 3 междинни спирки в мобилни браузъри (до 9 на други платформи). При проблем отвори линка в приложението Google Maps или раздели маршрута.")
    return PlannerOut(
        transport_mode=request.transport_mode,
        available_time_minutes=request.available_time_minutes,
        estimated_total_minutes=total_minutes,
        estimated_total_cost_eur=round(total_cost, 2) if costs_known and ordered else None,
        total_route_distance_km=round(route_distance, 1),
        returns_to_start=request.return_to_start,
        route_is_estimate=route_is_estimate,
        route_provider=route_provider,
        google_maps_url=maps_url,
        route_polyline=route_polyline,
        warnings=list(dict.fromkeys(warnings)),
        stops=planned_stops,
    )
