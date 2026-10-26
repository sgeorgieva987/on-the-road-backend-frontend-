from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON
from app.db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    preferences: Mapped["UserPreference | None"] = relationship(back_populates="user", cascade="all, delete-orphan", uselist=False)
    itineraries: Mapped[list["Itinerary"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserPreference(Base):
    __tablename__ = "user_preferences"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    interests: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    interest_weights: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    preferred_transport: Mapped[str] = mapped_column(String(20), default="car", nullable=False)
    budget_eur: Mapped[float | None] = mapped_column(Float, nullable=True)
    trip_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prefers_lesser_known: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    user: Mapped[User] = relationship(back_populates="preferences")


class Destination(Base):
    __tablename__ = "destinations"
    __table_args__ = (
        Index("ix_destinations_lat_lon", "latitude", "longitude"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(240), index=True)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    municipality: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    historical_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    categories: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    google_place_id: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    estimated_visit_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    estimated_cost_eur: Mapped[float | None] = mapped_column(Float, nullable=True)
    opening_hours: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(60), nullable=True)
    seasonal_months: Mapped[list | None] = mapped_column(JSON, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(24), default="unverified", nullable=False, index=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Structured, editorially grouped content for the destination detail box.
    # The legacy columns above remain available for existing clients/imports.
    information: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(240), index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    destination_id: Mapped[int | None] = mapped_column(ForeignKey("destinations.id", ondelete="SET NULL"), nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(24), default="unverified", nullable=False)
    destination: Mapped[Destination | None] = relationship()


class BookSource(Base):
    __tablename__ = "book_sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(320), index=True)
    author: Mapped[str | None] = mapped_column(String(320), nullable=True)
    publication_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    publisher: Mapped[str | None] = mapped_column(String(320), nullable=True)
    edition: Mapped[str | None] = mapped_column(String(240), nullable=True)
    language: Mapped[str] = mapped_column(String(12), default="bg", nullable=False)
    copyright_status: Mapped[str] = mapped_column(String(40), default="unknown", nullable=False, index=True)
    bibliographic_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(1000))
    processing_status: Mapped[str] = mapped_column(String(24), default="uploaded", nullable=False, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    pages: Mapped[list["SourcePage"]] = relationship(back_populates="source", cascade="all, delete-orphan", order_by="SourcePage.page_number")


class SourcePage(Base):
    __tablename__ = "source_pages"
    __table_args__ = (UniqueConstraint("source_id", "page_number", name="uq_source_page_number"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("book_sources.id", ondelete="CASCADE"), index=True)
    page_number: Mapped[int] = mapped_column(Integer)
    original_image_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    processed_image_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    raw_ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_engine: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ocr_engine_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ocr_language: Mapped[str] = mapped_column(String(40), default="bul+eng", nullable=False)
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    processing_status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False, index=True)
    review_status: Mapped[str] = mapped_column(String(24), default="needs_review", nullable=False, index=True)
    verification_status: Mapped[str] = mapped_column(String(24), default="unverified", nullable=False)
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[BookSource] = relationship(back_populates="pages")
    passages: Mapped[list["TextPassage"]] = relationship(back_populates="page", cascade="all, delete-orphan")


class TextPassage(Base):
    __tablename__ = "text_passages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("book_sources.id", ondelete="CASCADE"), index=True)
    source_page_id: Mapped[int] = mapped_column(ForeignKey("source_pages.id", ondelete="CASCADE"), index=True)
    section_title: Mapped[str | None] = mapped_column(String(320), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(12), default="bg", nullable=False)
    processing_status: Mapped[str] = mapped_column(String(24), default="extracted", nullable=False)
    verification_status: Mapped[str] = mapped_column(String(24), default="unverified", nullable=False)
    page: Mapped[SourcePage] = relationship(back_populates="passages")


class SourceReference(Base):
    __tablename__ = "source_references"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    destination_id: Mapped[int | None] = mapped_column(ForeignKey("destinations.id", ondelete="CASCADE"), nullable=True, index=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), nullable=True, index=True)
    passage_id: Mapped[int | None] = mapped_column(ForeignKey("text_passages.id", ondelete="CASCADE"), nullable=True, index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("book_sources.id", ondelete="CASCADE"), index=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str] = mapped_column(String(24), default="needs_review", nullable=False)
    reviewer_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class Itinerary(Base):
    __tablename__ = "itineraries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(240), default="My Bulgaria trip", nullable=False)
    request_parameters: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    destination_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    proposed_order: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    estimated_total_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    user: Mapped[User] = relationship(back_populates="itineraries")


class SavedDestination(Base):
    __tablename__ = "saved_destinations"
    __table_args__ = (UniqueConstraint("user_id", "destination_id", name="uq_user_saved_destination"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    destination_id: Mapped[int] = mapped_column(ForeignKey("destinations.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
