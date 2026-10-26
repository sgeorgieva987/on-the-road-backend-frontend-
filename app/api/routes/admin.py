from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from app.schemas import validate_http_url
from sqlalchemy.orm import Session
from app.db import get_db
from app.dependencies import require_admin
from app.models import Destination, Event, User

router = APIRouter(prefix="/api/admin", tags=["administration"])


class EventCreate(BaseModel):
    name: str = Field(min_length=2, max_length=240)
    description: str = Field(default="", max_length=10000)
    destination_id: int | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    source_url: str | None = Field(default=None, max_length=500)
    verification_status: str = Field(default="unverified", pattern="^(unverified|reviewed|verified|conflicting)$")

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str | None) -> str | None:
        return validate_http_url(value)


@router.post("/events", status_code=201)
def create_event(payload: EventCreate, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    if payload.destination_id is not None and not db.get(Destination, payload.destination_id):
        raise HTTPException(status_code=404, detail="Destination not found")
    if payload.start_date and payload.end_date and payload.end_date < payload.start_date:
        raise HTTPException(status_code=422, detail="end_date cannot be before start_date")
    event = Event(**payload.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)
    return {"id": event.id, **payload.model_dump()}
