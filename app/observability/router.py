"""
Observability API router — all endpoints for the Developer Dashboard.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from bson import ObjectId

from app.auth.service import get_current_user
from app.db import traces_col

logger = logging.getLogger("stock_intelligence.observability")
router = APIRouter(prefix="/obs", tags=["Observability"])


def _serialize(doc: dict) -> dict:
    doc["_id"] = str(doc["_id"])
    return doc


def _parse_int_or_none(v) -> Optional[int]:
    try:
        return int(v)
    except Exception:
        return None


# ── Traces ─────────────────────────────────────────────────────────────────────

@router.get("/traces")
async def list_traces(
    user_id: Optional[str] = Query(None),
    agent: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    filt: dict = {}
    if user_id:
        filt["user_id"] = user_id
    if session_id:
        filt["session_id"] = session_id
    if agent:
        filt["$or"] = [
            {"user_request.selected_agent": agent},
            {"supervisor.agent_selected": agent},
            {"final_output.agent_used": agent},
        ]
    if status:
        filt["status"] = status
    if date_from:
        filt.setdefault("created_at", {})["$gte"] = date_from
    if date_to:
        filt.setdefault("created_at", {})["$lte"] = date_to

    col = traces_col()
    total = await col.count_documents(filt)
    skip = (page - 1) * page_size
    cursor = col.find(filt, {"workflow_steps": 0, "tool_calls": 0, "llm_calls": 0, "db_operations": 0}) \
                .sort("created_at", -1).skip(skip).limit(page_size)
    docs = [_serialize(d) async for d in cursor]
    return {"total": total, "page": page, "page_size": page_size, "traces": docs}


@router.get("/traces/{trace_id}")
async def get_trace(trace_id: str, current_user: dict = Depends(get_current_user)):
    doc = await traces_col().find_one({"trace_id": trace_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Trace not found")
    return _serialize(doc)


@router.get("/live")
async def live_traces(current_user: dict = Depends(get_current_user)):
    col = traces_col()
    cursor = col.find({"status": "running"}).sort("created_at", -1).limit(50)
    docs = [_serialize(d) async for d in cursor]
    return {"active_count": len(docs), "traces": docs}


# ── Analytics ─────────────────────────────────────────────────────────────────

@router.get("/analytics/agents")
async def agent_analytics(current_user: dict = Depends(get_current_user)):
    pipeline = [
        {"$group": {
            "_id": "$final_output.agent_used",
            "count": {"$sum": 1},
            "avg_latency_ms": {"$avg": "$total_latency_ms"},
            "success_count": {"$sum": {"$cond": [{"$eq": ["$status", "success"]}, 1, 0]}},
            "error_count": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
        }},
        {"$sort": {"count": -1}},
    ]
    result = [doc async for doc in traces_col().aggregate(pipeline)]
    return {"agents": result}


@router.get("/analytics/tools")
async def tool_analytics(current_user: dict = Depends(get_current_user)):
    pipeline = [
        {"$unwind": "$tool_calls"},
        {"$group": {
            "_id": "$tool_calls.tool_name",
            "total_calls": {"$sum": 1},
            "success_calls": {"$sum": {"$cond": ["$tool_calls.success", 1, 0]}},
            "failed_calls": {"$sum": {"$cond": [{"$not": "$tool_calls.success"}, 1, 0]}},
            "avg_latency_ms": {"$avg": "$tool_calls.latency_ms"},
        }},
        {"$sort": {"total_calls": -1}},
    ]
    result = [doc async for doc in traces_col().aggregate(pipeline)]
    return {"tools": result}


@router.get("/analytics/llm")
async def llm_analytics(current_user: dict = Depends(get_current_user)):
    pipeline = [
        {"$unwind": "$llm_calls"},
        {"$group": {
            "_id": "$llm_calls.model",
            "total_calls": {"$sum": 1},
            "total_tokens_in": {"$sum": "$llm_calls.tokens_in"},
            "total_tokens_out": {"$sum": "$llm_calls.tokens_out"},
            "total_cost_usd": {"$sum": "$llm_calls.cost_usd"},
            "avg_latency_ms": {"$avg": "$llm_calls.latency_ms"},
            "provider": {"$first": "$llm_calls.provider"},
        }},
        {"$sort": {"total_calls": -1}},
    ]
    result = [doc async for doc in traces_col().aggregate(pipeline)]
    total_cost = sum(r.get("total_cost_usd", 0) for r in result)
    return {"models": result, "total_cost_usd": round(total_cost, 4)}


@router.get("/analytics/errors")
async def error_analytics(current_user: dict = Depends(get_current_user)):
    pipeline = [
        {"$unwind": "$errors"},
        {"$group": {
            "_id": "$errors.exception_type",
            "count": {"$sum": 1},
            "agents": {"$addToSet": "$final_output.agent_used"},
            "last_seen": {"$max": "$errors.logged_at"},
        }},
        {"$sort": {"count": -1}},
    ]
    result = [doc async for doc in traces_col().aggregate(pipeline)]
    failed_queries = await traces_col().count_documents({"status": "failed"})
    return {"error_types": result, "failed_queries_total": failed_queries}


@router.get("/analytics/cost")
async def cost_analytics(current_user: dict = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    async def _cost_for_filter(filt: dict) -> float:
        pipeline = [
            {"$match": filt},
            {"$group": {"_id": None, "total": {"$sum": "$cost_analytics.total_cost_usd"}}},
        ]
        docs = [d async for d in traces_col().aggregate(pipeline)]
        return round(docs[0]["total"] if docs else 0.0, 6)

    daily = await _cost_for_filter({"created_at": {"$gte": today_start}})
    monthly = await _cost_for_filter({"created_at": {"$gte": month_start}})
    total = await _cost_for_filter({})

    # Per-user breakdown
    user_pipeline = [
        {"$group": {
            "_id": "$username",
            "cost_usd": {"$sum": "$cost_analytics.total_cost_usd"},
            "queries": {"$sum": 1},
        }},
        {"$sort": {"cost_usd": -1}},
        {"$limit": 20},
    ]
    per_user = [d async for d in traces_col().aggregate(user_pipeline)]

    # Per-agent breakdown
    agent_pipeline = [
        {"$group": {
            "_id": "$final_output.agent_used",
            "cost_usd": {"$sum": "$cost_analytics.total_cost_usd"},
        }},
        {"$sort": {"cost_usd": -1}},
    ]
    per_agent = [d async for d in traces_col().aggregate(agent_pipeline)]

    return {
        "daily_cost_usd": daily,
        "monthly_cost_usd": monthly,
        "total_cost_usd": total,
        "per_user": per_user,
        "per_agent": per_agent,
    }


@router.get("/analytics/performance")
async def performance_analytics(current_user: dict = Depends(get_current_user)):
    pipeline = [
        {"$group": {
            "_id": None,
            "avg_total_latency_ms": {"$avg": "$performance.total_latency_ms"},
            "avg_llm_latency_ms": {"$avg": "$performance.llm_latency_ms"},
            "avg_tool_latency_ms": {"$avg": "$performance.tool_latency_ms"},
            "avg_db_latency_ms": {"$avg": "$performance.db_latency_ms"},
            "p95_latency": {"$percentile": {"input": "$performance.total_latency_ms", "p": [0.95], "method": "approximate"}},
            "total_requests": {"$sum": 1},
        }},
    ]
    try:
        docs = [d async for d in traces_col().aggregate(pipeline)]
        perf = docs[0] if docs else {}
        perf.pop("_id", None)
    except Exception:
        # Percentile not available in older Mongo — fallback
        pipeline_fb = [{"$group": {"_id": None,
            "avg_total_latency_ms": {"$avg": "$performance.total_latency_ms"},
            "avg_llm_latency_ms": {"$avg": "$performance.llm_latency_ms"},
            "avg_tool_latency_ms": {"$avg": "$performance.tool_latency_ms"},
            "avg_db_latency_ms": {"$avg": "$performance.db_latency_ms"},
            "total_requests": {"$sum": 1}}}]
        docs = [d async for d in traces_col().aggregate(pipeline_fb)]
        perf = docs[0] if docs else {}
        perf.pop("_id", None)
    return perf


@router.get("/analytics/daily-trend")
async def daily_trend(days: int = Query(14), current_user: dict = Depends(get_current_user)):
    """Returns daily query count and cost for the last N days."""
    pipeline = [
        {"$project": {"day": {"$substr": ["$created_at", 0, 10]}, "cost": "$cost_analytics.total_cost_usd", "status": 1}},
        {"$group": {
            "_id": "$day",
            "queries": {"$sum": 1},
            "cost_usd": {"$sum": "$cost"},
            "errors": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
        }},
        {"$sort": {"_id": 1}},
        {"$limit": days},
    ]
    result = [d async for d in traces_col().aggregate(pipeline)]
    return {"trend": result}
