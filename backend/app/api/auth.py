"""Authentication: passwordless magic-link login + guest→volunteer activation."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import utcnow
from app.core.security import generate_token, hash_token
from app.core.session import make_session_token
from app.modules.communications.service import queue_email
from app.modules.identity.models import Person, TokenPurpose, VerificationToken
from app.modules.org.models import Organization
from app.modules.people.service import ActivationError, activate_volunteer

from .deps import get_db, get_public_org

router = APIRouter(prefix="/api/auth", tags=["auth"])


class EmailIn(BaseModel):
    email: EmailStr


class TokenIn(BaseModel):
    token: str
    password: str | None = None


class SessionOut(BaseModel):
    token: str


def _issue_login_token(db: Session, *, org_id: int, person: Person) -> str:
    token = generate_token()
    db.add(VerificationToken(
        org_id=org_id, person_id=person.id, purpose=TokenPurpose.account_activation,
        token_hash=hash_token(token),
        expires_at=utcnow() + timedelta(minutes=settings.activation_token_ttl_min),
    ))
    db.flush()
    return token


def _consume(db: Session, token: str) -> Person:
    row = db.scalar(select(VerificationToken).where(
        VerificationToken.token_hash == hash_token(token),
        VerificationToken.purpose == TokenPurpose.account_activation,
    ))
    if row is None or row.used_at is not None or row.expires_at < utcnow():
        raise HTTPException(status_code=400, detail="Invalid or expired link")
    row.used_at = utcnow()
    person = db.get(Person, row.person_id)
    db.flush()
    return person


@router.post("/request-login")
def request_login(payload: EmailIn, db: Session = Depends(get_db),
                  org: Organization = Depends(get_public_org)):
    person = db.scalar(select(Person).where(
        Person.org_id == org.id, Person.email == str(payload.email).lower()))
    # Always return 200 (don't reveal whether an account exists).
    if person is not None:
        token = _issue_login_token(db, org_id=org.id, person=person)
        queue_email(db, org_id=org.id, idempotency_key=f"login:{token[:16]}",
                    to_email=person.email, template_key="login_link",
                    context={"name": person.name,
                             "login_url": f"{settings.public_base_url}/login?token={token}"})
        db.commit()
    return {"message": "If that email is registered, a sign-in link is on its way."}


@router.post("/login", response_model=SessionOut)
def login(payload: TokenIn, db: Session = Depends(get_db)):
    person = _consume(db, payload.token)
    if person.user is None:
        db.rollback()
        raise HTTPException(status_code=409, detail="Activate your volunteer account first")
    db.commit()
    return SessionOut(token=make_session_token(user_id=person.user.id, org_id=person.org_id))


@router.post("/activate", response_model=SessionOut)
def activate(payload: TokenIn, db: Session = Depends(get_db)):
    person = _consume(db, payload.token)
    try:
        user = activate_volunteer(db, org_id=person.org_id, person_id=person.id,
                                  password=payload.password)
    except ActivationError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return SessionOut(token=make_session_token(user_id=user.id, org_id=person.org_id))
