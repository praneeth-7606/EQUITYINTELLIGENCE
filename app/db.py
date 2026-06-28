"""
Motor async MongoDB client and collection accessors.
"""
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.config import settings

logger = logging.getLogger("stock_intelligence.db")

# Global client — initialised in lifespan
_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    if _client is None:
        raise RuntimeError("MongoDB client is not initialised. Did the lifespan startup run?")
    return _client


def get_db():
    return get_client()[settings.mongodb_db]


# ── Collection helpers ─────────────────────────────────────────────────────────

def users_col():
    return get_db()["users"]

def files_col():
    return get_db()["files"]

def portfolio_col():
    return get_db()["portfolio"]

def chat_sessions_col():
    return get_db()["chat_sessions"]

def chat_messages_col():
    return get_db()["chat_messages"]

def reports_col():
    return get_db()["reports"]

def traces_col():
    return get_db()["traces"]

def projects_col():
    return get_db()["projects"]


# ── Lifespan context manager ───────────────────────────────────────────────────

@asynccontextmanager
async def db_lifespan(app: FastAPI):
    """Connect to MongoDB on startup, close on shutdown."""
    global _client
    logger.info(f"Connecting to MongoDB at {settings.mongodb_uri} ...")
    _client = AsyncIOMotorClient(settings.mongodb_uri)
    db = _client[settings.mongodb_db]

    # Ensure indexes
    await db["users"].create_index("email", unique=True)
    await db["users"].create_index("username", unique=True)
    await db["traces"].create_index("trace_id", unique=True)
    await db["traces"].create_index("user_id")
    await db["traces"].create_index("created_at")
    await db["chat_sessions"].create_index("user_id")
    await db["chat_messages"].create_index("session_id")
    await db["files"].create_index("user_id")
    await db["projects"].create_index("user_id")

    # Seed default admin user if not exists
    from app.auth.service import hash_password
    existing = await db["users"].find_one({"email": "admin@stock.ai"})
    if not existing:
        await db["users"].insert_one({
            "email": "admin@stock.ai",
            "username": "admin",
            "full_name": "Platform Admin",
            "hashed_password": hash_password("Admin@1234"),
            "role": "admin",
            "is_active": True,
            "created_at": __import__("datetime").datetime.utcnow().isoformat(),
            "login_history": [],
        })
        logger.info("Seeded default admin user: admin@stock.ai / Admin@1234")

    logger.info("MongoDB connected and indexes ensured.")
    yield

    logger.info("Closing MongoDB connection...")
    _client.close()
