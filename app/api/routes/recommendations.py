from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy.orm import Session
from app.db import get_db
from app.dependencies import get_optional_user, get_current_user, require_admin
from app.models import BookSource, Destination, Itinerary, SourcePage, SourceReference, TextPassage, User, UserPreference
from app.schemas import (
    DestinationOut, ItineraryOut, PlannerOut, PlannerRequest, RecommendationItem,
    RecommendationRequest,
)
from app.services.itinerary import build_route_output, generate_itinerary
from app.services.recommender import combine_profile_and_trip_interests, passes_hard_filters, rank_destination
from app.core.config import settings

router = APIRouter(prefix="/api", tags=["recommendations and itineraries"])


@router.post("/recommendations", response_model=list[RecommendationItem])
def recommendations(
    payload: RecommendationRequest,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    profile_interests = user.preferences.interests if user and user.preferences else []
    profile_weights = user.preferences.interest_weights if user and user.preferences else {}
    interests, weights = combine_profile_and_trip_interests(
        profile_interests,
        profile_weights,
        payload.interests,
        payload.interest_weights,
    )
    budget = payload.budget_eur
    prefers_hidden = payload.prefers_lesser_known
    if user and user.preferences:
        if budget is None:
            budget = user.preferences.budget_eur
        if not payload.prefers_lesser_known:
            prefers_hidden = user.preferences.prefers_lesser_known
    destinations = db.query(Destination).all()
    ranked: list[RecommendationItem] = []
    for destination in destinations:
        if not passes_hard_filters(
            destination,
            latitude=payload.latitude,
            longitude=payload.longitude,
            radius_km=payload.radius_km,
            budget_eur=budget,
            travel_date=payload.travel_date,
            include_unverified=payload.include_unverified,
        ):
            continue
        score, reasons = rank_destination(
            destination,
            interests=interests,
            interest_weights=weights,
            latitude=payload.latitude,
            longitude=payload.longitude,
            budget_eur=budget,
            prefers_lesser_known=prefers_hidden,
        )
        ranked.append(RecommendationItem(destination=DestinationOut.model_validate(destination), score=score, reasons=reasons))
    ranked.sort(key=lambda item: (-item.score, item.destination.name.casefold()))
    return ranked[:payload.limit]


@router.post("/itineraries/plan", response_model=PlannerOut)
def plan_itinerary(
    payload: PlannerRequest,
    save: bool = Query(default=False),
    title: str = Query(default="My Bulgaria trip", max_length=240),
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    if save and user is None:
        raise HTTPException(status_code=401, detail="Log in to save an itinerary")

    profile_interests = user.preferences.interests if user and user.preferences else []
    profile_weights = user.preferences.interest_weights if user and user.preferences else {}
    effective_interests, effective_weights = combine_profile_and_trip_interests(
        profile_interests,
        profile_weights,
        payload.interests,
        payload.interest_weights,
    )
    effective_budget = payload.budget_eur
    if effective_budget is None and user and user.preferences:
        effective_budget = user.preferences.budget_eur
    effective_payload = payload.model_copy(update={
        "interests": effective_interests,
        "interest_weights": effective_weights,
        "budget_eur": effective_budget,
    })

    try:
        if payload.selected_destination_ids:
            found = db.query(Destination).filter(Destination.id.in_(payload.selected_destination_ids)).all()
            by_id = {item.id: item for item in found}
            missing = [destination_id for destination_id in payload.selected_destination_ids if destination_id not in by_id]
            if missing:
                raise HTTPException(status_code=404, detail=f"Selected destination(s) not found: {missing}")
            # Preserve the client's selected order as input. Google optimizes
            # intermediate stopovers when available; with no key, nearest-neighbour
            # ordering makes cross-town routes more practical than selection order.
            selected = [by_id[destination_id] for destination_id in payload.selected_destination_ids]
            if not effective_payload.include_unverified:
                unverified_names = [item.name for item in selected if item.verification_status != "verified"]
                if unverified_names:
                    raise HTTPException(status_code=422, detail="Some selected places are not verified. Enable demonstration records or select verified destinations: " + ", ".join(unverified_names))
            scores = {
                item.id: rank_destination(
                    item,
                    interests=effective_interests,
                    interest_weights=effective_weights,
                    latitude=payload.start_latitude,
                    longitude=payload.start_longitude,
                    budget_eur=effective_budget,
                    prefers_lesser_known=bool(user and user.preferences and user.preferences.prefers_lesser_known),
                )[0]
                for item in selected
            }
            result = build_route_output(
                selected,
                effective_payload,
                recommendation_scores=scores,
                base_warnings=["Това е маршрут през всички места, избрани от теб; радиусът за автоматично търсене не премахва тези спирки."],
                nearest_neighbor_fallback=True,
                preserve_all_stops=True,
            )
        else:
            estimated = generate_itinerary(db.query(Destination).all(), effective_payload)
            selected = [stop.destination for stop in estimated.stops]
            scores = {stop.destination.id: stop.recommendation_score for stop in estimated.stops}
            # The estimate-based selector is a cheap first pass. If actual Google
            # route durations show that it exceeds the user's time budget, remove
            # the lowest-ranked stop and calculate again until the route fits.
            excluded_names: list[str] = []
            result = build_route_output(
                selected,
                effective_payload,
                recommendation_scores=scores,
                base_warnings=estimated.warnings,
                nearest_neighbor_fallback=False,
                preserve_all_stops=False,
            )
            if settings.google_routes_api_key:
                while result.route_provider == "google_routes_api" and result.stops and result.estimated_total_minutes > payload.available_time_minutes:
                    lowest = min(selected, key=lambda item: (scores.get(item.id, 0.0), item.name.casefold()))
                    selected = [item for item in selected if item.id != lowest.id]
                    excluded_names.append(lowest.name)
                    if not selected:
                        result = build_route_output(
                            [], effective_payload,
                            base_warnings=estimated.warnings + ["No destinations fit the available time after Google route times were checked."],
                            preserve_all_stops=False,
                        )
                        break
                    result = build_route_output(
                        selected,
                        effective_payload,
                        recommendation_scores=scores,
                        base_warnings=estimated.warnings,
                        nearest_neighbor_fallback=False,
                        preserve_all_stops=False,
                    )
            if excluded_names:
                result.warnings.append("Изключени са по-ниско класирани места, за да се спази времевият лимит според маршрута от Google Maps: " + ", ".join(excluded_names) + ".")

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Persist current-trip interests only when a signed-in user explicitly opts in.
    if user and payload.remember_interests and payload.interests:
        preference = user.preferences
        if preference is None:
            preference = UserPreference(
                user_id=user.id,
                interests=[],
                interest_weights={},
                preferred_transport=payload.transport_mode,
                budget_eur=effective_budget,
                trip_duration_minutes=payload.available_time_minutes,
                prefers_lesser_known=False,
            )
            db.add(preference)
            db.flush()
        persisted_interests, persisted_weights = combine_profile_and_trip_interests(
            preference.interests,
            preference.interest_weights,
            payload.interests,
            payload.interest_weights,
        )
        preference.interests = persisted_interests
        preference.interest_weights = persisted_weights
        db.add(preference)
        db.commit()

    if save and user:
        record = Itinerary(
            user_id=user.id,
            title=title,
            request_parameters={**effective_payload.model_dump(mode="json"), "google_maps_url": result.google_maps_url, "route_provider": result.route_provider},
            destination_ids=[stop.destination.id for stop in result.stops],
            proposed_order=[{
                "order": stop.order,
                "destination_id": stop.destination.id,
                "distance_from_previous_km": stop.distance_from_previous_km,
                "travel_minutes_from_previous": stop.travel_minutes_from_previous,
                "visit_minutes": stop.visit_minutes,
            } for stop in result.stops],
            estimated_total_minutes=result.estimated_total_minutes,
        )
        db.add(record)
        db.commit()
    return result


@router.get("/itineraries/saved", response_model=list[ItineraryOut])
def saved_itineraries(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(Itinerary).filter_by(user_id=user.id).order_by(Itinerary.created_at.desc()).all()


@router.get("/itineraries/{itinerary_id}", response_model=ItineraryOut)
def get_itinerary(itinerary_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    itinerary = db.query(Itinerary).filter_by(id=itinerary_id, user_id=user.id).first()
    if not itinerary:
        raise HTTPException(status_code=404, detail="Itinerary not found")
    return itinerary


@router.delete("/itineraries/{itinerary_id}", status_code=204)
def delete_itinerary(itinerary_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    itinerary = db.query(Itinerary).filter_by(id=itinerary_id, user_id=user.id).first()
    if not itinerary:
        raise HTTPException(status_code=404, detail="Itinerary not found")
    db.delete(itinerary)
    db.commit()
    return None
