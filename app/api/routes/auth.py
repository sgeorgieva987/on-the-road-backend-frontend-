from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.db import get_db
from app.dependencies import get_current_user
from app.models import Destination, SavedDestination, User, UserPreference
from app.schemas import LoginRequest, PreferenceUpdate, RegisterRequest, TokenOut, UserOut, DestinationOut

router = APIRouter(prefix="/api/auth", tags=["authentication"])


def _token_response(user: User) -> TokenOut:
    return TokenOut(
        access_token=create_access_token(str(user.id), user.is_admin),
        expires_in_minutes=settings.access_token_minutes,
        user=UserOut.model_validate(user),
    )


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(email=payload.email, password_hash=hash_password(payload.password))
    user.preferences = UserPreference()
    db.add(user)
    db.commit()
    db.refresh(user)
    return _token_response(user)


@router.post("/login", response_model=TokenOut)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.strip().lower()).first()
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password", headers={"WWW-Authenticate": "Bearer"})
    return _token_response(user)


@router.get("/me", response_model=UserOut)
def get_me(user: User = Depends(get_current_user)):
    return user


@router.get("/me/preferences")
def get_preferences(user: User = Depends(get_current_user)):
    pref = user.preferences
    if pref is None:
        return {"interests": [], "interest_weights": {}, "preferred_transport": "car", "budget_eur": None, "trip_duration_minutes": None, "prefers_lesser_known": False}
    return {
        "interests": pref.interests or [],
        "interest_weights": pref.interest_weights or {},
        "preferred_transport": pref.preferred_transport,
        "budget_eur": pref.budget_eur,
        "trip_duration_minutes": pref.trip_duration_minutes,
        "prefers_lesser_known": pref.prefers_lesser_known,
    }


@router.put("/me/preferences")
def update_preferences(payload: PreferenceUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pref = user.preferences
    if pref is None:
        pref = UserPreference(user_id=user.id)
        db.add(pref)
    for key, value in payload.model_dump().items():
        setattr(pref, key, value)
    db.commit()
    return payload


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(user)
    db.commit()
    return None


@router.get("/me/saved-destinations", response_model=list[DestinationOut])
def saved_destinations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(Destination)
        .join(SavedDestination, SavedDestination.destination_id == Destination.id)
        .filter(SavedDestination.user_id == user.id)
        .order_by(SavedDestination.created_at.desc())
        .all()
    )


@router.post("/me/saved-destinations/{destination_id}", status_code=status.HTTP_201_CREATED)
def save_destination(destination_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not db.get(Destination, destination_id):
        raise HTTPException(status_code=404, detail="Destination not found")
    existing = db.query(SavedDestination).filter_by(user_id=user.id, destination_id=destination_id).first()
    if existing:
        return {"saved": True, "destination_id": destination_id, "already_saved": True}
    db.add(SavedDestination(user_id=user.id, destination_id=destination_id))
    db.commit()
    return {"saved": True, "destination_id": destination_id}


@router.delete("/me/saved-destinations/{destination_id}", status_code=status.HTTP_204_NO_CONTENT)
def unsave_destination(destination_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.query(SavedDestination).filter_by(user_id=user.id, destination_id=destination_id).first()
    if row:
        db.delete(row)
        db.commit()
    return None
