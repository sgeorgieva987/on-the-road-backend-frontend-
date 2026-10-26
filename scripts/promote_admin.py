"""Promote an already registered account to administrator.
Usage: python -m scripts.promote_admin user@example.com
"""
import sys
from app.db import SessionLocal
from app.models import User


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.promote_admin EMAIL")
        return 2
    email = sys.argv[1].strip().lower()
    with SessionLocal() as db:
        user = db.query(User).filter_by(email=email).first()
        if not user:
            print("No user with that email exists. Register via the app first.")
            return 1
        user.is_admin = True
        db.commit()
        print(f"Administrator privileges granted to {email}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
