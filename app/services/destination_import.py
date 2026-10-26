"""Load destination JSON files and upsert them into the database."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models import Destination
from app.schemas import DestinationCreate
from app.seed import grouped_information


def read_destination_file(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("destinations", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError("JSON must contain an array or a {\"destinations\": [...]} object")
    return [normalize_record(record) for record in records]


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError("Every destination must be a JSON object")
    item = dict(record)
    # Allow simple imports to use title instead of name and let the backend
    # generate the grouped information contract when it is omitted.
    item["name"] = item.get("name") or item.get("title")
    item["slug"] = item.get("slug") or make_slug(item.get("name", ""))
    item.setdefault("categories", [])
    item.setdefault("tags", [])
    item.setdefault("description", "")
    item.setdefault("estimated_visit_minutes", 60)
    item.setdefault("verification_status", "unverified")
    item.setdefault("source_url", None)
    item.setdefault("estimated_cost_eur", None)
    item.setdefault("information", grouped_information(item))
    return DestinationCreate.model_validate(item).model_dump()


def make_slug(name: str) -> str:
    # Slugs can also be supplied explicitly when transliteration is important.
    normalized = "-".join(str(name).casefold().split())
    return "".join(char for char in normalized if char.isalnum() or char == "-")


def upsert_destinations(db: Session, records: list[dict[str, Any]]) -> tuple[int, int]:
    created = updated = 0
    for record in records:
        existing = db.query(Destination).filter_by(slug=record["slug"]).first()
        if existing is None:
            db.add(Destination(**record))
            created += 1
            continue
        for key, value in record.items():
            setattr(existing, key, value)
        updated += 1
    db.commit()
    return created, updated
