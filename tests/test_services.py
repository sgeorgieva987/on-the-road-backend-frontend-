from app.models import Destination, SourcePage, BookSource
from app.services.ocr import normalize_text, create_passages
from app.services.recommender import haversine_km, rank_destination, passes_hard_filters


def test_haversine_distance_is_symmetric_and_positive():
    a = haversine_km(42.6977, 23.3219, 42.1480, 24.7515)
    b = haversine_km(42.1480, 24.7515, 42.6977, 23.3219)
    assert 130 < a < 150
    assert abs(a - b) < 1e-9


def test_rank_destination_and_unknown_budget_is_hard_filtered():
    d = Destination(
        id=1, slug='place', name='Place', region='Test', municipality='Test', description='Test',
        historical_context=None, categories=['история'], tags=['наследство'], latitude=42.7, longitude=23.3,
        estimated_visit_minutes=60, estimated_cost_eur=None, opening_hours=None, website=None, phone=None,
        seasonal_months=None, verification_status='verified', source_url=None,
    )
    score, reasons = rank_destination(d, interests=['история'], interest_weights={'история':1})
    assert score == 1
    assert reasons
    assert not passes_hard_filters(d, latitude=None, longitude=None, radius_km=None, budget_eur=20, travel_date=None, include_unverified=False)
    assert passes_hard_filters(d, latitude=None, longitude=None, radius_km=None, budget_eur=None, travel_date=None, include_unverified=False)


def test_normalize_text_preserves_words_and_paragraphs():
    text = normalize_text('  Исторически\t текст  \r\n\r\n\r\nВтора   линия ')
    assert text == 'Исторически текст\n\nВтора линия'


def test_create_passages_keeps_source_page_provenance(client):
    _, sessions = client
    with sessions() as db:
        source = BookSource(title='Test book', language='bg', copyright_status='unknown', original_filename='test.pdf', storage_path='/tmp/test.pdf')
        db.add(source)
        db.flush()
        page = SourcePage(source_id=source.id, page_number=1, processing_status='completed', review_status='reviewed')
        db.add(page)
        db.flush()
        count = create_passages(db, page, 'Първи абзац.\n\nВтори абзац.')
        db.commit()
        assert count == 1  # short paragraphs are retained together as one bounded chunk
        refreshed = db.query(SourcePage).filter_by(id=page.id).one()
        assert len(refreshed.passages) == 1
        assert 'Първи абзац.' in refreshed.passages[0].text and 'Втори абзац.' in refreshed.passages[0].text
        assert all(p.source_id == source.id and p.source_page_id == page.id for p in refreshed.passages)
