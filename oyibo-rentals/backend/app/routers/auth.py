from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..security import create_token, current_user, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])
REFERRAL_BONUS = 500


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    phone: str = Field(min_length=7, max_length=20)
    password: str = Field(min_length=8, max_length=72)
    referral_code: str | None = None

    @field_validator("name", "phone")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("cannot be empty")
        return value.strip()


class LoginIn(BaseModel):
    email: EmailStr
    password: str


def user_out(user: User) -> dict:
    return {"id": user.id, "name": user.name, "email": user.email, "phone": user.phone, "role": user.role,
            "loyalty_points": user.loyalty_points, "referral_code": user.referral_code}


@router.post("/register")
def register(data: RegisterIn, db: Session = Depends(get_db)):
    email = data.email.lower()
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(409, "An account with this email already exists.")
    user = User(name=data.name, email=email, phone=data.phone, password_hash=hash_password(data.password),
                referral_code="OY" + secrets.token_hex(3).upper())
    if data.referral_code:
        referrer = db.scalar(select(User).where(User.referral_code == data.referral_code.strip().upper()))
        if referrer is None:
            raise HTTPException(422, "That referral code is not valid.")
        referrer.loyalty_points += REFERRAL_BONUS
        user.loyalty_points = REFERRAL_BONUS
    db.add(user)
    db.commit()
    return {"token": create_token(user), "user": user_out(user)}


@router.post("/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == data.email.lower()))
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Email or password is incorrect.")
    return {"token": create_token(user), "user": user_out(user)}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_out(user)
