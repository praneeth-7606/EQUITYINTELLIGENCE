"""
Authentication router: register, login, refresh, logout, profile.
"""
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, status, Depends
import bson

from app.auth.models import (
    UserCreate, UserLogin, UserProfile, TokenPair,
    RefreshRequest, PasswordResetRequest
)
from app.auth.service import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    decode_token, get_current_user,
)
from app.db import users_col

logger = logging.getLogger("stock_intelligence.auth.router")
router = APIRouter(prefix="/auth", tags=["Authentication"])


def _user_to_profile(user: dict) -> UserProfile:
    return UserProfile(
        id=str(user["_id"]),
        email=user["email"],
        username=user["username"],
        full_name=user["full_name"],
        role=user.get("role", "user"),
        is_active=user.get("is_active", True),
        created_at=user.get("created_at", ""),
    )


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def register(body: UserCreate):
    col = users_col()
    if await col.find_one({"email": body.email}):
        raise HTTPException(status_code=409, detail="Email already registered")
    if await col.find_one({"username": body.username}):
        raise HTTPException(status_code=409, detail="Username already taken")

    doc = {
        "email": body.email,
        "username": body.username,
        "full_name": body.full_name,
        "hashed_password": hash_password(body.password),
        "role": "user",
        "is_active": True,
        "created_at": datetime.utcnow().isoformat(),
        "login_history": [],
    }
    result = await col.insert_one(doc)
    user_id = str(result.inserted_id)

    access = create_access_token(user_id, body.email, "user")
    refresh = create_refresh_token(user_id)
    await col.update_one({"_id": result.inserted_id}, {"$set": {"refresh_token": refresh}})

    doc["_id"] = result.inserted_id
    return TokenPair(access_token=access, refresh_token=refresh, user=_user_to_profile(doc))


@router.post("/login", response_model=TokenPair)
async def login(body: UserLogin):
    col = users_col()
    user = await col.find_one({"email": body.email})
    if not user or not verify_password(body.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="Account is disabled")

    user_id = str(user["_id"])
    access = create_access_token(user_id, user["email"], user.get("role", "user"))
    refresh = create_refresh_token(user_id)

    await col.update_one(
        {"_id": user["_id"]},
        {"$set": {"refresh_token": refresh},
         "$push": {"login_history": {"ts": datetime.utcnow().isoformat(), "action": "login"}}},
    )
    return TokenPair(access_token=access, refresh_token=refresh, user=_user_to_profile(user))


@router.post("/refresh", response_model=TokenPair)
async def refresh_token(body: RefreshRequest):
    payload = decode_token(body.refresh_token)
    if payload.get("kind") != "refresh":
        raise HTTPException(status_code=401, detail="Not a refresh token")

    user = await users_col().find_one({"_id": bson.ObjectId(payload["sub"])})
    if not user or user.get("refresh_token") != body.refresh_token:
        raise HTTPException(status_code=401, detail="Refresh token revoked or invalid")

    user_id = str(user["_id"])
    new_access = create_access_token(user_id, user["email"], user.get("role", "user"))
    new_refresh = create_refresh_token(user_id)
    await users_col().update_one({"_id": user["_id"]}, {"$set": {"refresh_token": new_refresh}})
    return TokenPair(access_token=new_access, refresh_token=new_refresh, user=_user_to_profile(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(current_user: dict = Depends(get_current_user)):
    await users_col().update_one(
        {"_id": current_user["_id"]},
        {"$unset": {"refresh_token": ""}, "$push": {"login_history": {"ts": datetime.utcnow().isoformat(), "action": "logout"}}},
    )


@router.get("/me", response_model=UserProfile)
async def get_me(current_user: dict = Depends(get_current_user)):
    return _user_to_profile(current_user)


@router.put("/me", response_model=UserProfile)
async def update_me(updates: dict, current_user: dict = Depends(get_current_user)):
    allowed = {k: v for k, v in updates.items() if k in ("full_name", "username")}
    if allowed:
        await users_col().update_one({"_id": current_user["_id"]}, {"$set": allowed})
    user = await users_col().find_one({"_id": current_user["_id"]})
    return _user_to_profile(user)


@router.post("/forgot-password")
async def forgot_password(body: PasswordResetRequest):
    """Scaffolded — email delivery requires SMTP config."""
    user = await users_col().find_one({"email": body.email})
    if not user:
        return {"message": "If the email exists, a reset link will be sent."}
    reset_token = create_refresh_token(str(user["_id"]))
    await users_col().update_one({"_id": user["_id"]}, {"$set": {"reset_token": reset_token}})
    logger.info(f"[Auth] Password reset token generated for {body.email} (SMTP not configured — token not sent)")
    return {"message": "If the email exists, a reset link will be sent.", "dev_token": reset_token}
