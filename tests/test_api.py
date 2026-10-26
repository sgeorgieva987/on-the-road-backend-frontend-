from app.models import User


def test_health_and_destination_seed(client):
    api, _ = client
    assert api.get('/api/health').json()['status'] == 'ok'
    response = api.get('/api/destinations')
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) >= 20
    assert any(row['slug'] == 'rila-monastery' for row in rows)
    assert all(row['verification_status'] == 'unverified' for row in rows)


def test_destination_search_and_category_filter(client):
    api, _ = client
    response = api.get('/api/destinations', params={'q': 'Пловдив'})
    assert response.status_code == 200
    assert response.json()
    assert all('Пловдив' in row['name'] or 'Пловдив' in row['description'] or row['region'] == 'Пловдив' for row in response.json())
    history = api.get('/api/destinations', params={'category': 'археология'}).json()
    assert history
    assert any('археология' in [x.lower() for x in row['categories']] for row in history)


def test_register_login_and_preferences(client):
    api, sessions = client
    response = api.post('/api/auth/register', json={'email':'traveller@example.com','password':'my-good-passphrase'})
    assert response.status_code == 201, response.text
    token = response.json()['access_token']
    assert api.get('/api/auth/me', headers={'Authorization':f'Bearer {token}'}).json()['email'] == 'traveller@example.com'
    update = api.put('/api/auth/me/preferences', headers={'Authorization':f'Bearer {token}'}, json={
        'interests':['история','природа'], 'interest_weights':{'история':0.7,'природа':0.3},
        'preferred_transport':'car','budget_eur':None,'trip_duration_minutes':180,'prefers_lesser_known':True
    })
    assert update.status_code == 200, update.text
    prefs = api.get('/api/auth/me/preferences', headers={'Authorization':f'Bearer {token}'}).json()
    assert prefs['interests'] == ['история','природа']
    login = api.post('/api/auth/login', json={'email':'traveller@example.com','password':'my-good-passphrase'})
    assert login.status_code == 200
    assert api.post('/api/auth/login', json={'email':'traveller@example.com','password':'wrong-password'}).status_code == 401


def test_planner_respects_available_time_and_train_limit(client):
    api, _ = client
    payload = {
      'start_latitude':42.6977,'start_longitude':23.3219,'available_time_minutes':180,
      'transport_mode':'car','interests':['история'],'include_unverified':True,'max_destinations':5
    }
    response = api.post('/api/itineraries/plan', json=payload)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['estimated_total_minutes'] <= data['available_time_minutes']
    assert all(stop['order'] == i + 1 for i, stop in enumerate(data['stops']))
    payload['transport_mode'] = 'train'
    train = api.post('/api/itineraries/plan', json=payload)
    assert train.status_code == 422
    assert 'BDZ' in train.json()['detail']


def test_admin_endpoints_require_admin(client):
    api, sessions = client
    register = api.post('/api/auth/register', json={'email':'ordinary@example.com','password':'another-good-pass'})
    token = register.json()['access_token']
    blocked = api.post('/api/admin/destinations', headers={'Authorization':f'Bearer {token}'}, json={
      'slug':'test-destination','name':'Тестова дестинация','latitude':42.7,'longitude':23.3
    })
    assert blocked.status_code == 403
    with sessions() as db:
        user = db.query(User).filter_by(email='ordinary@example.com').one()
        user.is_admin = True
        db.commit()
    # Log in again so the signed token includes the updated role claim (authorization also checks DB).
    admin_login = api.post('/api/auth/login', json={'email':'ordinary@example.com','password':'another-good-pass'})
    admin_token = admin_login.json()['access_token']
    created = api.post('/api/admin/destinations', headers={'Authorization':f'Bearer {admin_token}'}, json={
      'slug':'test-destination','name':'Тестова дестинация','latitude':42.7,'longitude':23.3,
      'categories':['култура'],'verification_status':'unverified'
    })
    assert created.status_code == 201, created.text


def test_reviewed_source_can_be_linked_and_publicly_retrieved(client):
    api, sessions = client
    registered = api.post('/api/auth/register', json={'email':'historian@example.com','password':'careful-source-pass'})
    with sessions() as db:
        user = db.query(User).filter_by(email='historian@example.com').one()
        user.is_admin = True
        from app.models import BookSource, SourcePage
        destination = db.query(__import__('app.models', fromlist=['Destination']).Destination).filter_by(slug='plovdiv-old-town').one()
        source = BookSource(title='Примерен исторически сборник', author='Редактор', publication_year=1901,
            language='bg', copyright_status='public_domain', original_filename='scan.png', storage_path='/tmp/scan.png')
        db.add(source); db.flush()
        page = SourcePage(source_id=source.id, page_number=17, raw_ocr_text='Примерен откъс за Пловдив.', normalized_text='Примерен откъс за Пловдив.',
            processing_status='completed', review_status='reviewed', verification_status='verified')
        db.add(page); db.commit(); db.refresh(page); destination_id = destination.id; page_id = page.id
    login = api.post('/api/auth/login', json={'email':'historian@example.com','password':'careful-source-pass'})
    token = login.json()['access_token']
    link = api.post(f'/api/admin/pages/{page_id}/link-destination', headers={'Authorization':f'Bearer {token}'}, json={
        'destination_id': destination_id, 'excerpt':'Примерен откъс за Пловдив.', 'review_status':'verified'
    })
    assert link.status_code == 201, link.text
    references = api.get(f'/api/destinations/{destination_id}/sources')
    assert references.status_code == 200
    assert len(references.json()) == 1
    assert references.json()[0]['page_number'] == 17


def test_public_historical_search_hides_unknown_rights_and_unreviewed_pages(client):
    api, sessions = client
    with sessions() as db:
        from app.models import BookSource, SourcePage, TextPassage
        source = BookSource(title='Private source', language='bg', copyright_status='unknown', original_filename='scan.png', storage_path='/tmp/scan.png')
        db.add(source); db.flush()
        page = SourcePage(source_id=source.id, page_number=1, raw_ocr_text='Тайна дума', normalized_text='Тайна дума', processing_status='completed', review_status='reviewed', verification_status='verified')
        db.add(page); db.flush()
        db.add(TextPassage(source_id=source.id, source_page_id=page.id, text='Тайна дума', language='bg', processing_status='reviewed', verification_status='verified'))
        db.commit()
    public = api.get('/api/sources/search', params={'q':'Тайна дума'})
    assert public.status_code == 200
    assert public.json() == []


def test_custom_route_keeps_selected_destinations_across_towns_and_builds_google_maps_link(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "google_routes_api_key", None)
    api, sessions = client
    with sessions() as db:
        from app.models import Destination
        plovdiv = db.query(Destination).filter_by(slug="plovdiv-old-town").one()
        rila = db.query(Destination).filter_by(slug="rila-monastery").one()
        selected_ids = [plovdiv.id, rila.id]
    response = api.post("/api/itineraries/plan", json={
        "start_latitude": 42.6977,
        "start_longitude": 23.3219,
        "available_time_minutes": 60,
        "transport_mode": "car",
        "interests": ["история"],
        "selected_destination_ids": selected_ids,
        "include_unverified": True,
    })
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["stops"]) == 2  # Manual selections are never silently dropped.
    assert {stop["destination"]["id"] for stop in data["stops"]} == set(selected_ids)
    assert data["route_is_estimate"] is True
    assert data["google_maps_url"].startswith("https://www.google.com/maps/dir/?api=1")
    assert "%7C" in data["google_maps_url"] or len(data["stops"]) == 2
    assert any("надвишава зададения лимит" in warning for warning in data["warnings"])


def test_public_config_never_exposes_server_routes_key(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "google_routes_api_key", "server-secret-test-key")
    monkeypatch.setattr(settings, "google_maps_js_api_key", "public-browser-key")
    api, _ = client
    response = api.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert data["google_maps_js_api_key"] == "public-browser-key"
    assert data["google_routes_enabled"] is True
    assert "server-secret-test-key" not in response.text
    assert "google_routes_api_key" not in data


def test_trip_interests_are_remembered_only_with_explicit_opt_in(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "google_routes_api_key", None)
    api, sessions = client
    registered = api.post('/api/auth/register', json={'email':'trip-preferences@example.com','password':'trip-preferences-pass'})
    assert registered.status_code == 201
    token = registered.json()['access_token']
    headers = {'Authorization': f"Bearer {token}"}
    with sessions() as db:
        from app.models import Destination
        destination_id = db.query(Destination).filter_by(slug='vitosha-zlatnite-mostove').one().id
    request = {
        'start_latitude': 42.6977, 'start_longitude': 23.3219,
        'available_time_minutes': 300, 'transport_mode': 'car',
        'interests': ['природа'], 'include_unverified': True,
        'selected_destination_ids': [destination_id], 'remember_interests': True,
    }
    response = api.post('/api/itineraries/plan', headers=headers, json=request)
    assert response.status_code == 200, response.text
    preferences = api.get('/api/auth/me/preferences', headers=headers).json()
    assert 'природа' in preferences['interests']
    assert preferences['interest_weights']['природа'] > 0
