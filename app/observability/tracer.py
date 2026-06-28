"""
AgentTracer — lightweight, non-blocking observability engine.

Usage inside any agent node:
    tracer: AgentTracer = state.get("tracer")
    if tracer:
        tracer.log_step("Read Portfolio", status="success", latency_ms=120)
        tracer.log_tool_call("YahooFinance", input={"symbol": "TCS"}, output={...}, latency_ms=340)
        tracer.log_llm(provider="google", model="gemini-flash", tokens_in=800, tokens_out=420, latency_ms=1200)
"""
import uuid
import logging
import asyncio
import traceback
from datetime import datetime, timezone
from typing import Any, Optional
from app.privacy import mask_free_text

logger = logging.getLogger("stock_intelligence.tracer")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_preview(text: str) -> str:
    cleaned = (text or "").strip()
    for prefix in ("```markdown", "```md", "```text", "```"):
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            break
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()
    cleaned = cleaned.replace("{{current_date}}", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    cleaned = cleaned.replace("{current_date}", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    return mask_free_text(cleaned)


def _ms(start_iso: str) -> float:
    """Compute elapsed milliseconds from an ISO timestamp string."""
    start = datetime.fromisoformat(start_iso)
    return round((datetime.now(timezone.utc) - start).total_seconds() * 1000, 2)


# Cost table (USD per 1M tokens) — approximate
_LLM_COST_TABLE = {
    "gemini-flash":         {"in": 0.075, "out": 0.30},
    "gemini-1.5-flash":     {"in": 0.075, "out": 0.30},
    "gemini-2.0-flash":     {"in": 0.075, "out": 0.30},
    "gemini-2.5-flash":     {"in": 0.15,  "out": 0.60},
    "gpt-4o":               {"in": 2.50,  "out": 10.0},
    "gpt-4o-mini":          {"in": 0.15,  "out": 0.60},
    "claude-sonnet":        {"in": 3.00,  "out": 15.0},
    "llama-3.3-70b":        {"in": 0.59,  "out": 0.79},
    "mistral-large":        {"in": 2.00,  "out": 6.00},
}


def _estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    key = next((k for k in _LLM_COST_TABLE if k in model.lower()), None)
    if not key:
        return 0.0
    rates = _LLM_COST_TABLE[key]
    return round((tokens_in * rates["in"] + tokens_out * rates["out"]) / 1_000_000, 6)


class AgentTracer:
    """Thread-safe, in-memory trace builder. Persisted to MongoDB at the end of each request."""

    def __init__(self, user_id: str, username: str, session_id: str, query: str, selected_agent: Optional[str] = None):
        self.trace_id = str(uuid.uuid4())
        self.user_id = user_id
        self.username = username
        self.session_id = session_id
        self.query = query
        self.selected_agent = selected_agent

        self._start = _now()
        self._status = "running"
        self._steps: list[dict] = []
        self._tool_calls: list[dict] = []
        self._llm_calls: list[dict] = []
        self._errors: list[dict] = []
        self._supervisor: dict = {}
        self._final_output: dict = {}
        self._db_ops: list[dict] = []
        self._active_steps: dict[str, str] = {}  # step_name → start_time

    # ── Supervisor ────────────────────────────────────────────────────────────

    def log_supervisor(self, agent_selected: str, reasoning: str, confidence: float = 1.0):
        self._supervisor = {
            "agent_selected": agent_selected,
            "reasoning": reasoning,
            "confidence_score": confidence,
            "logged_at": _now(),
        }

    # ── Workflow Steps ────────────────────────────────────────────────────────

    def start_step(self, name: str):
        self._active_steps[name] = _now()

    def end_step(self, name: str, status: str = "success", metadata: dict = None):
        start = self._active_steps.pop(name, _now())
        self._steps.append({
            "step_name": name,
            "start_time": start,
            "end_time": _now(),
            "latency_ms": _ms(start),
            "status": status,
            "metadata": metadata or {},
        })

    def log_step(self, name: str, status: str = "success", latency_ms: float = 0.0, metadata: dict = None):
        """Single-call shortcut when you already know the latency."""
        self._steps.append({
            "step_name": name,
            "start_time": _now(),
            "end_time": _now(),
            "latency_ms": latency_ms,
            "status": status,
            "metadata": metadata or {},
        })

    # ── Tool Calls ────────────────────────────────────────────────────────────

    def log_tool_call(
        self,
        tool_name: str,
        tool_type: str = "python",
        input: Any = None,
        output: Any = None,
        latency_ms: float = 0.0,
        retry_count: int = 0,
        success: bool = True,
        error: Optional[str] = None,
    ):
        self._tool_calls.append({
            "tool_name": tool_name,
            "tool_type": tool_type,
            "input": mask_free_text(str(input))[:500] if input else None,
            "output_preview": mask_free_text(str(output))[:500] if output else None,
            "latency_ms": latency_ms,
            "retry_count": retry_count,
            "success": success,
            "error": error,
            "logged_at": _now(),
        })

    # ── LLM Calls ─────────────────────────────────────────────────────────────

    def log_llm(
        self,
        provider: str,
        model: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
        latency_ms: float = 0.0,
        temperature: float = 0.0,
        prompt_version: str = "v1",
    ):
        cost = _estimate_cost(model, tokens_in, tokens_out)
        self._llm_calls.append({
            "provider": provider,
            "model": model,
            "prompt_version": prompt_version,
            "temperature": temperature,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "total_tokens": tokens_in + tokens_out,
            "latency_ms": latency_ms,
            "cost_usd": cost,
            "logged_at": _now(),
        })

    # ── DB Operations ─────────────────────────────────────────────────────────

    def log_db_op(self, operation: str, collection: str, latency_ms: float, status: str = "success"):
        self._db_ops.append({
            "operation": operation,
            "collection": collection,
            "latency_ms": latency_ms,
            "status": status,
            "logged_at": _now(),
        })

    # ── Errors ────────────────────────────────────────────────────────────────

    def log_error(self, exc: Exception, recovery_method: str = "none", fallback_triggered: bool = False, retry_attempts: int = 0):
        self._errors.append({
            "exception_type": type(exc).__name__,
            "message": mask_free_text(str(exc)),
            "stack_trace": mask_free_text(traceback.format_exc()),
            "recovery_method": recovery_method,
            "fallback_triggered": fallback_triggered,
            "retry_attempts": retry_attempts,
            "logged_at": _now(),
        })

    # ── Final Output & Persist ────────────────────────────────────────────────

    def finalize(self, summary: str = "", agent_used: str = "", result_size_bytes: int = 0, status: str = "success"):
        self._status = status
        self._final_output = {
            "summary_preview": _clean_preview(summary)[:500],
            "agent_used": agent_used,
            "response_size_bytes": result_size_bytes,
            "finalized_at": _now(),
        }

    def _build_document(self) -> dict:
        end_time = _now()
        total_tokens = sum(c["total_tokens"] for c in self._llm_calls)
        total_cost = round(sum(c["cost_usd"] for c in self._llm_calls), 6)
        total_latency = _ms(self._start)
        llm_latency = sum(c["latency_ms"] for c in self._llm_calls)
        tool_latency = sum(c["latency_ms"] for c in self._tool_calls)
        db_latency = sum(c["latency_ms"] for c in self._db_ops)

        return {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "username": mask_free_text(self.username),
            "created_at": self._start,
            "ended_at": end_time,
            "total_latency_ms": total_latency,
            "status": self._status,
            "user_request": {
                "original_prompt": mask_free_text(self.query),
                "selected_agent": self.selected_agent,
            },
            "supervisor": self._supervisor,
            "workflow_steps": self._steps,
            "tool_calls": self._tool_calls,
            "llm_calls": self._llm_calls,
            "db_operations": self._db_ops,
            "errors": self._errors,
            "performance": {
                "total_latency_ms": total_latency,
                "llm_latency_ms": llm_latency,
                "tool_latency_ms": tool_latency,
                "db_latency_ms": db_latency,
                "network_latency_ms": round(total_latency - llm_latency - tool_latency - db_latency, 2),
            },
            "cost_analytics": {
                "total_tokens": total_tokens,
                "total_cost_usd": total_cost,
                "llm_calls_count": len(self._llm_calls),
            },
            "final_output": self._final_output,
        }

    async def persist(self):
        """Async persist to MongoDB traces collection."""
        try:
            from app.db import traces_col
            doc = self._build_document()
            await traces_col().replace_one({"trace_id": self.trace_id}, doc, upsert=True)
            logger.info(f"[Tracer] Trace {self.trace_id} persisted ({self._status})")
        except Exception as e:
            logger.error(f"[Tracer] Failed to persist trace {self.trace_id}: {e}")

    def persist_sync(self):
        """Sync wrapper — schedule persist as background task."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.persist())
            else:
                loop.run_until_complete(self.persist())
        except Exception as e:
            logger.error(f"[Tracer] persist_sync error: {e}")
