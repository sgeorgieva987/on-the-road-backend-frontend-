from __future__ import annotations
import io
import re
import statistics
from pathlib import Path
import fitz
import pytesseract
from PIL import Image, ImageOps, ImageEnhance, UnidentifiedImageError
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models import BookSource, SourcePage, TextPassage

OCR_LANGUAGE = "bul+eng"


def normalize_text(raw: str) -> str:
    """Conservative normalization; raw OCR is retained unchanged."""
    lines = [re.sub(r"[\t\u00a0 ]+", " ", line).strip() for line in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    cleaned: list[str] = []
    blank_last = False
    for line in lines:
        blank = not line
        if blank and blank_last:
            continue
        cleaned.append(line)
        blank_last = blank
    return "\n".join(cleaned).strip()


def _preprocess_image(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image).convert("L")
    image = ImageOps.autocontrast(image)
    image = ImageEnhance.Contrast(image).enhance(1.15)
    return image


def _run_tesseract(image: Image.Image) -> tuple[str, float | None, str]:
    data = pytesseract.image_to_data(image, lang=OCR_LANGUAGE, config="--psm 3", output_type=pytesseract.Output.DICT)
    words = []
    confidences = []
    for index, word in enumerate(data.get("text", [])):
        word = str(word).strip()
        try:
            confidence = float(data["conf"][index])
        except (ValueError, TypeError, KeyError, IndexError):
            confidence = -1
        if word:
            words.append((int(data["block_num"][index]), int(data["par_num"][index]), int(data["line_num"][index]), word))
            if confidence >= 0:
                confidences.append(confidence)
    # Reconstruct lines from layout metadata to keep some paragraph structure.
    lines: list[str] = []
    current_key = None
    current_words: list[str] = []
    for block, par, line, word in words:
        key = (block, par, line)
        if current_key is not None and key != current_key:
            lines.append(" ".join(current_words))
            current_words = []
        current_key = key
        current_words.append(word)
    if current_words:
        lines.append(" ".join(current_words))
    avg_confidence = round(statistics.mean(confidences), 2) if confidences else None
    try:
        version = str(pytesseract.get_tesseract_version())
    except Exception:
        version = "unknown"
    return "\n".join(lines), avg_confidence, version


def _get_or_create_page(db: Session, source_id: int, page_number: int) -> SourcePage:
    page = db.query(SourcePage).filter_by(source_id=source_id, page_number=page_number).one_or_none()
    if page is None:
        page = SourcePage(source_id=source_id, page_number=page_number, processing_status="pending", ocr_language=OCR_LANGUAGE)
        db.add(page)
        db.flush()
    return page


def process_source_ocr(db: Session, source: BookSource, retry_failed_only: bool = False) -> dict:
    """OCR every page of a supported source, committing page-level results incrementally."""
    path = Path(source.storage_path).resolve()
    upload_root = settings.upload_dir.resolve()
    if upload_root not in path.parents:
        raise ValueError("Stored source path is outside the configured upload directory")
    if not path.is_file():
        raise FileNotFoundError("The original uploaded file could not be found")

    ext = path.suffix.lower()
    if ext == ".pdf":
        document = fitz.open(path)
        if document.page_count > settings.max_pdf_pages:
            document.close()
            raise ValueError(f"This PDF contains more than the configured limit of {settings.max_pdf_pages} pages")
        page_count = document.page_count
        source.processing_status = "processing"
        db.commit()
        successes = failures = 0
        processed_dir = upload_root / "processed" / f"source-{source.id}"
        processed_dir.mkdir(parents=True, exist_ok=True)
        try:
            for page_index in range(page_count):
                page_number = page_index + 1
                page_record = _get_or_create_page(db, source.id, page_number)
                if retry_failed_only and page_record.processing_status not in {"failed", "pending"}:
                    continue
                page_record.processing_status = "processing"
                page_record.processing_error = None
                db.commit()
                try:
                    pix = document.load_page(page_index).get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    rendered_bytes = pix.tobytes("png")
                    image = Image.open(io.BytesIO(rendered_bytes))
                    original_render_path = processed_dir / f"original-page-{page_number:04d}.png"
                    original_render_path.write_bytes(rendered_bytes)  # unmodified page render; uploaded PDF remains untouched
                    processed = _preprocess_image(image)
                    processed_path = processed_dir / f"page-{page_number:04d}.jpg"
                    processed.save(processed_path, quality=92)
                    text, confidence, version = _run_tesseract(processed)
                    page_record.processed_image_path = str(processed_path)
                    page_record.original_image_path = str(original_render_path)
                    page_record.raw_ocr_text = text
                    page_record.normalized_text = normalize_text(text)
                    page_record.ocr_engine = "Tesseract"
                    page_record.ocr_engine_version = version
                    page_record.ocr_language = OCR_LANGUAGE
                    page_record.ocr_confidence = confidence
                    page_record.processing_status = "completed"
                    page_record.review_status = "needs_review"
                    db.commit()
                    successes += 1
                except Exception as exc:
                    page_record.processing_status = "failed"
                    page_record.processing_error = str(exc)[:2000]
                    db.commit()
                    failures += 1
        finally:
            document.close()
    else:
        page_count = 1
        source.processing_status = "processing"
        db.commit()
        page_record = _get_or_create_page(db, source.id, 1)
        if retry_failed_only and page_record.processing_status not in {"failed", "pending"}:
            return {"source_id": source.id, "page_count": 1, "completed": 0, "failed": 0, "skipped": 1, "status": source.processing_status}
        try:
            page_record.processing_status = "processing"
            page_record.processing_error = None
            db.commit()
            with Image.open(path) as original:
                processed = _preprocess_image(original)
            processed_dir = upload_root / "processed" / f"source-{source.id}"
            processed_dir.mkdir(parents=True, exist_ok=True)
            processed_path = processed_dir / "page-0001.jpg"
            processed.save(processed_path, quality=92)
            text, confidence, version = _run_tesseract(processed)
            page_record.original_image_path = str(path)
            page_record.processed_image_path = str(processed_path)
            page_record.raw_ocr_text = text
            page_record.normalized_text = normalize_text(text)
            page_record.ocr_engine = "Tesseract"
            page_record.ocr_engine_version = version
            page_record.ocr_language = OCR_LANGUAGE
            page_record.ocr_confidence = confidence
            page_record.processing_status = "completed"
            page_record.review_status = "needs_review"
            db.commit()
            successes, failures = 1, 0
        except Exception as exc:
            page_record.processing_status = "failed"
            page_record.processing_error = str(exc)[:2000]
            db.commit()
            successes, failures = 0, 1

    states = [p.processing_status for p in db.query(SourcePage).filter_by(source_id=source.id).all()]
    if states and all(state == "completed" for state in states):
        source.processing_status = "ocr_completed_review_required"
    elif any(state == "completed" for state in states):
        source.processing_status = "partially_completed"
    else:
        source.processing_status = "failed"
    db.commit()
    return {"source_id": source.id, "page_count": page_count, "completed": successes, "failed": failures, "status": source.processing_status}


def create_passages(db: Session, page: SourcePage, text: str) -> int:
    """Split reviewed text into plain-text chunks, keeping a link to the original page."""
    db.query(TextPassage).filter_by(source_page_id=page.id).delete(synchronize_session=False)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs or ([text.strip()] if text.strip() else []):
        while len(paragraph) > 1200:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(paragraph[:1200])
            paragraph = paragraph[1200:]
        if current and len(current) + len(paragraph) + 2 > 1200:
            chunks.append(current)
            current = paragraph
        else:
            current = f"{current}\n\n{paragraph}".strip()
    if current:
        chunks.append(current)
    for chunk in chunks:
        db.add(TextPassage(source_id=page.source_id, source_page_id=page.id, text=chunk, language="bg", processing_status="reviewed"))
    return len(chunks)
