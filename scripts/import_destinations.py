"""Import or update destinations from a JSON file.

Usage: python -m scripts.import_destinations path/to/destinations.json
"""
from pathlib import Path
import sys

from app.db import SessionLocal
from app.services.destination_import import read_destination_file, upsert_destinations


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.import_destinations path/to/destinations.json")
        return 2
    path = Path(sys.argv[1]).resolve()
    if not path.is_file():
        print(f"File not found: {path}")
        return 2
    try:
        records = read_destination_file(path)
        with SessionLocal() as db:
            created, updated = upsert_destinations(db, records)
    except (OSError, ValueError) as exc:
        print(f"Import failed: {exc}")
        return 1
    print(f"Imported {len(records)} records: {created} created, {updated} updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
