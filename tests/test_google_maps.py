from app.core.config import settings
from app.models import Destination
from app.services.google_maps import compute_google_route
from app.services.recommender import combine_profile_and_trip_interests


def _destination(destination_id, name, latitude, longitude):
    return Destination(
        id=destination_id,
        slug=f"place-{destination_id}",
        name=name,
        region="Тестов регион",
        municipality=name,
        description="Тест",
        historical_context=None,
        categories=["история"],
        tags=[],
        latitude=latitude,
        longitude=longitude,
        estimated_visit_minutes=30,
        estimated_cost_eur=0,
        opening_hours=None,
        website=None,
        phone=None,
        seasonal_months=None,
        verification_status="verified",
        source_url=None,
    )


def test_profile_and_checked_trip_interests_are_blended():
    interests, weights = combine_profile_and_trip_interests(
        ["история"], {"история": 1.0}, ["природа"], {}
    )
    assert interests == ["история", "природа"]
    assert abs(weights["история"] - 0.35) < 1e-9
    assert abs(weights["природа"] - 0.65) < 1e-9


def test_google_routes_response_reorders_intermediate_stops(monkeypatch):
    monkeypatch.setattr(settings, "google_routes_api_key", "test-key")

    class FakeResponse:
        def raise_for_status(self):
            return None
        def json(self):
            return {"routes": [{
                "distanceMeters": 180000,
                "duration": "7200s",
                "optimizedIntermediateWaypointIndex": [1, 0],
                "legs": [
                    {"distanceMeters": 70000, "duration": "2400s"},
                    {"distanceMeters": 60000, "duration": "2400s"},
                    {"distanceMeters": 50000, "duration": "2400s"},
                ],
                "polyline": {"encodedPolyline": "test-encoded-polyline"},
            }]}

    def fake_post(url, **kwargs):
        assert url.endswith("/directions/v2:computeRoutes")
        assert kwargs["headers"]["X-Goog-Api-Key"] == "test-key"
        assert kwargs["json"]["optimizeWaypointOrder"] is True
        assert "routes.optimizedIntermediateWaypointIndex" in kwargs["headers"]["X-Goog-FieldMask"]
        return FakeResponse()

    monkeypatch.setattr("app.services.google_maps.httpx.post", fake_post)
    first = _destination(1, "Първо", 42.1, 24.1)
    second = _destination(2, "Второ", 42.2, 24.2)
    endpoint = _destination(3, "Крайна спирка", 42.3, 24.3)
    result = compute_google_route(
        42.7, 23.3, [first, second, endpoint], transport_mode="car", return_to_start=False
    )
    assert result is not None
    assert [d.id for d in result.ordered_destinations] == [2, 1, 3]
    assert result.total_distance_km == 180.0
    assert result.total_travel_minutes == 120
    assert result.encoded_polyline == "test-encoded-polyline"
