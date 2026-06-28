"""
MongoDB helper operations for persisting files, messages, sessions, reports, and portfolio data.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import bson

from app.db import (
    files_col, chat_sessions_col, chat_messages_col,
    reports_col, portfolio_col
)

logger = logging.getLogger("stock_intelligence.db_ops")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Files ──────────────────────────────────────────────────────────────────────

async def save_file_metadata(
    user_id: str,
    original_filename: str,
    file_path: str,
    file_size: int,
    status: str = "processed"
) -> str:
    doc = {
        "user_id": user_id,
        "original_filename": original_filename,
        "file_path": file_path,
        "file_size": file_size,
        "processing_status": status,
        "uploaded_at": _now()
    }
    res = await files_col().insert_one(doc)
    return str(res.inserted_id)


# ── Chat Sessions & Messages ──────────────────────────────────────────────────

async def get_or_create_session(session_id: Optional[str], user_id: str, query: str) -> str:
    col = chat_sessions_col()
    if session_id:
        try:
            doc = await col.find_one({"_id": bson.ObjectId(session_id), "user_id": user_id})
            if doc:
                await col.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"updated_at": _now()}}
                )
                return session_id
        except Exception:
            pass

    # Create new session
    conv_name = query[:40] + "..." if len(query) > 40 else query
    doc = {
        "user_id": user_id,
        "conversation_name": conv_name,
        "created_at": _now(),
        "updated_at": _now()
    }
    res = await col.insert_one(doc)
    return str(res.inserted_id)


async def save_chat_message(
    session_id: str,
    user_id: str,
    role: str,
    content: str,
    agent_used: Optional[str] = None,
    structured_data: Optional[Dict[str, Any]] = None,
    insights: Optional[List[str]] = None
) -> str:
    doc = {
        "session_id": session_id,
        "user_id": user_id,
        "role": role,
        "content": content,
        "agent_used": agent_used,
        "structured_data": structured_data,
        "insights": insights,
        "timestamp": _now()
    }
    res = await chat_messages_col().insert_one(doc)
    return str(res.inserted_id)


# ── Portfolio & Reports ────────────────────────────────────────────────────────

async def save_portfolio_transactions(user_id: str, transactions: List[Dict[str, Any]], summary: Dict[str, Any]):
    col = portfolio_col()
    # Replace existing portfolio for user to avoid duplication
    await col.delete_many({"user_id": user_id})
    doc = {
        "user_id": user_id,
        "parsed_transactions": transactions,
        "portfolio_summary": summary,
        "updated_at": _now()
    }
    await col.insert_one(doc)
    logger.info(f"Saved {len(transactions)} transactions and summary to portfolio collection for user {user_id}")


async def save_report(
    user_id: str,
    session_id: str,
    report_type: str,  # portfolio, pnl, dividend, stock_analysis
    summary: str,
    structured_data: Dict[str, Any]
) -> str:
    doc = {
        "user_id": user_id,
        "session_id": session_id,
        "report_type": report_type,
        "summary": summary,
        "structured_data": structured_data,
        "created_at": _now()
    }
    res = await reports_col().insert_one(doc)
    return str(res.inserted_id)
