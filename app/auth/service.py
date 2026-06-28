"""
Authentication service: password hashing, JWT creation/validation, current-user dependency.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.config import settings

logger = logging.getLogger("stock_intelligence.auth")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


# ── Password helpers ───────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    pw_bytes = plain.encode('utf-8')
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pw_bytes, salt).decode('utf-8')


def verify_password(plain: str, hashed: str) -> bool:
    try:
        pw_bytes = plain.encode('utf-8')
        hashed_bytes = hashed.encode('utf-8')
        return bcrypt.checkpw(pw_bytes, hashed_bytes)
    except Exception:
        return False


# ── JWT helpers ────────────────────────────────────────────────────────────────

def _create_token(data: dict, expires_delta: timedelta, kind: str) -> str:
    payload = data.copy()
    payload["kind"] = kind
    payload["exp"] = datetime.now(timezone.utc) + expires_delta
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str, email: str, role: str) -> str:
    return _create_token(
        {"sub": user_id, "email": email, "role": role},
        timedelta(minutes=settings.access_token_expire_minutes),
        kind="access",
    )


def create_refresh_token(user_id: str) -> str:
    return _create_token(
        {"sub": user_id},
        timedelta(days=settings.refresh_token_expire_days),
        kind="refresh",
    )


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Current user dependency ────────────────────────────────────────────────────

async def get_current_user(token: Optional[str] = Depends(oauth2_scheme)):
    """FastAPI dependency — reads Bearer token, returns user dict from MongoDB."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated — provide Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(token)
    if payload.get("kind") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    from app.db import users_col
    user = await users_col().find_one({"_id": __import__("bson").ObjectId(payload["sub"])})
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    user["id"] = str(user["_id"])
    return user


async def get_current_user_optional(token: Optional[str] = Depends(oauth2_scheme)):
    """Same as get_current_user but returns None instead of raising (for dev bypass)."""
    if not token:
        return None
    try:
        return await get_current_user(token)
    except HTTPException:
        return None
