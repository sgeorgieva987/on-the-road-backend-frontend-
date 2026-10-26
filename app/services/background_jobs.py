import logging
from app.db import SessionLocal
from app.models import BookSource
from app.services.ocr import process_source_ocr

logger = logging.getLogger(__name__)


def run_ocr_job(source_id: int, retry_failed_only: bool = False) -> None:
    """Run OCR as an in-process background task and persist page-level progress."""
    with SessionLocal() as db:
        source = db.get(BookSource, source_id)
        if source is None:
            return
        try:
            process_source_ocr(db, source, retry_failed_only=retry_failed_only)
        except Exception as exc:  # background-task errors must leave a visible status
            logger.exception("OCR job failed for source %s", source_id)
            source.processing_status = "failed"
            db.commit()
