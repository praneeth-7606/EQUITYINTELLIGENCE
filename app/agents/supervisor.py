import logging
import time
from datetime import datetime
from pydantic import BaseModel, Field

from app.config import settings
from app.state import State
from app.llm import LLMFactory

logger = logging.getLogger("stock_intelligence.supervisor")

class RoutingDecision(BaseModel):
    route: str = Field(
        description="Must be one of: 'portfolio_agent', 'pnl_agent', 'dividend_agent', 'stock_analysis_agent', 'direct'."
    )
    confidence: str = Field(
        description="Must be one of: 'high', 'medium', 'low'."
    )
    reason: str = Field(
        description="One sentence explaining the routing decision."
    )
    user_query_summary: str = Field(
        description="5-word summary of what the user wants."
    )

SUPERVISOR_SYSTEM = """You are a routing supervisor for a financial analytics platform.
Your ONLY job is to read the user's message and decide which
specialist agent should handle it. You do not answer questions
yourself. You do not perform calculations.

## GOLDEN RULE (ALWAYS CHECK THIS FIRST)

  *** IF THE USER MENTIONS A SPECIFIC COMPANY OR STOCK NAME (e.g. ITC, TCS, Reliance,
  Eternal, Tata Steel, Zomato, HDFC, Infosys, Wipro, etc.) AND ASKS ABOUT:
    - dividend history / dividends / payout / yield
    - price / returns / performance / analysis
    - fundamentals / PE / PB / EPS / market cap
    - corporate actions / splits / bonus
    - any financial metric of THAT SPECIFIC STOCK
  → ALWAYS route to stock_analysis_agent. No exceptions.

  The dividend_agent is ONLY for questions about the USER'S OWN portfolio dividends.
  ANY question about a named stock's dividends → stock_analysis_agent. ***

## HOW TO CLASSIFY

  STOCK ANALYSIS intent (route → stock_analysis_agent):
    - Any question about a SPECIFIC NAMED STOCK (with or without personal pronouns).
    - "Get me the complete dividend history of ITC" → stock_analysis_agent
    - "Show me ITC dividends from listing date" → stock_analysis_agent
    - "What dividends has Reliance paid?" → stock_analysis_agent
    - "Analyze TCS for 2024" → stock_analysis_agent
    - "What is ITC's PE ratio?" → stock_analysis_agent
    - "Eternal stock analysis", "TCS returns 2023" → stock_analysis_agent
    - "Dividend history of [any stock name]" → stock_analysis_agent

  PORTFOLIO intent (route → portfolio_agent):
    - ONLY when user says "MY portfolio", "MY holdings", "MY stocks".
    - "What do I hold?", "Show me MY portfolio", "MY capital deployed".

  PNL intent (route → pnl_agent):
    - ONLY when user says "MY profit", "MY P&L", "MY charges", "MY returns".
    - "Did I make money?", "What are MY charges?", "MY Net P&L".

  DIVIDEND intent (route → dividend_agent):
    - ONLY when user says "MY dividends", "Did I get dividends?", "MY portfolio dividends".
    - NEVER use dividend_agent for named stock dividend queries.

## FEW-SHOT EXAMPLES

  Query: "Get me the complete dividend history of ITC stock from listing date"
  → route: "stock_analysis_agent"  (named stock + dividend history)

  Query: "Hey get me the complete dividend history of ITC stock from listing date to up to now"
  → route: "stock_analysis_agent"  (named stock + dividend history, no personal pronoun)

  Query: "What dividends has Tata Steel paid?"
  → route: "stock_analysis_agent"  (named stock + dividends)

  Query: "Reliance dividend yield?"
  → route: "stock_analysis_agent"  (named stock + yield)

  Query: "Did I get dividends from my portfolio?"
  → route: "dividend_agent"  (personal pronoun "I" + "my portfolio")

  Query: "What dividends did I miss?"
  → route: "dividend_agent"  (personal pronoun "I")

  Query: "Analyze TCS for 2024"
  → route: "stock_analysis_agent"  (named stock + year)

  Query: "Show me my P&L"
  → route: "pnl_agent"  (personal pronoun "my" + P&L)

  Query: "What stocks do I hold?"
  → route: "portfolio_agent"  (personal pronoun "I" + holdings)

## OUTPUT FORMAT

Respond with ONLY a JSON object. No prose. No explanation.

{
  "route": "<portfolio_agent | pnl_agent | dividend_agent | stock_analysis_agent>",
  "confidence": "<high | medium | low>",
  "reason": "<one sentence explaining the routing decision>",
  "user_query_summary": "<5-word summary of what the user wants>"
}

## BYPASS RULE

If the system context tells you the user has already selected an
agent directly via API endpoint, output:
{ "route": "direct", "reason": "user pre-selected agent" }
and terminate immediately. Do not process further."""

STOCK_ANALYSIS_KEYWORDS = {
    "stock",
    "share",
    "shares",
    "price",
    "returns",
    "return",
    "performance",
    "analysis",
    "analyze",
    "chart",
    "target",
    "resistance",
    "support",
    "pe",
    "pb",
    "eps",
    "market cap",
    "fundamentals",
    "dividend",
    "dividends",
    "yield",
    "bonus",
    "split",
    "history",
}
PORTFOLIO_KEYWORDS = {"portfolio", "holdings", "allocation", "capital deployed", "invested", "current value"}
PNL_KEYWORDS = {"p&l", "profit", "loss", "charges", "realized", "unrealized", "net p&l", "net pnl"}
DIVIDEND_KEYWORDS = {"dividends", "dividend", "payout", "yield on cost", "missed dividends", "upcoming dividends"}
COMMON_FILLER_WORDS = {
    "get", "give", "show", "tell", "about", "for", "with", "and", "the", "my", "me", "complete", "full",
    "please", "from", "to", "of", "on", "in", "a", "an", "up", "now", "latest"
}


def _contains_phrase(query: str, phrases: set[str]) -> bool:
    query_lower = query.lower()
    return any(phrase in query_lower for phrase in phrases)


def _looks_like_named_stock_query(query: str) -> bool:
    import re

    query_clean = re.sub(r"[^A-Za-z0-9&.\-\s]", " ", query)
    if re.search(r"\b(?:stock|stocks|share|shares)\s+(?:of\s+)?[a-z0-9][a-z0-9&.\-\s]{2,}", query.lower()):
        return True
    title_chunks = re.findall(r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,4}|[A-Z]{2,}(?:\s+[A-Z]{2,}){0,4})\b", query_clean)
    filtered = [
        chunk.strip()
        for chunk in title_chunks
        if chunk.strip().lower() not in COMMON_FILLER_WORDS and len(chunk.strip()) >= 3
    ]
    return bool(filtered)


def _rule_route(query: str) -> tuple[str | None, str, float]:
    normalized = " ".join(query.strip().split())
    if not normalized:
        return None, "", 0.0

    lowered = normalized.lower()
    has_my_context = any(token in lowered for token in [" my ", " i ", " me ", " portfolio ", " holdings "]) or lowered.startswith("my ")
    named_stock = _looks_like_named_stock_query(normalized)
    stock_signal = _contains_phrase(lowered, STOCK_ANALYSIS_KEYWORDS)

    if named_stock and stock_signal and not has_my_context:
        return "stock_analysis_agent", "Deterministic route: named stock with stock-analysis intent.", 0.99

    if named_stock and any(term in lowered for term in ["compare", "vs", "versus"]):
        return "stock_analysis_agent", "Deterministic route: company comparison query.", 0.98

    if "stock analysis" in lowered or "analyze " in lowered or "analysis for" in lowered:
        return "stock_analysis_agent", "Deterministic route: explicit stock-analysis request.", 0.96

    if has_my_context and _contains_phrase(lowered, DIVIDEND_KEYWORDS):
        return "dividend_agent", "Deterministic route: portfolio dividend question.", 0.95

    if has_my_context and _contains_phrase(lowered, PNL_KEYWORDS):
        return "pnl_agent", "Deterministic route: portfolio profit and loss question.", 0.95

    if has_my_context and _contains_phrase(lowered, PORTFOLIO_KEYWORDS):
        return "portfolio_agent", "Deterministic route: portfolio holdings question.", 0.95

    if named_stock and stock_signal:
        return "stock_analysis_agent", "Deterministic route: stock-specific market query.", 0.93

    return None, "", 0.0

async def supervisor_node(state: State) -> State:
    """
    Supervisor node that routes the query to the correct worker agent.
    If 'selected_agent' is already set (e.g. from a direct API route), it applies the bypass rule.
    """
    logger.info("Supervisor node running...")
    tracer = state.get("tracer")
    
    # 1. Bypass Rule
    if state.get("selected_agent"):
        logger.info(f"Agent already pre-selected: {state['selected_agent']}. Skipping supervisor routing.")
        if tracer:
            tracer.log_supervisor(
                agent_selected=state["selected_agent"],
                reasoning="Bypassed supervisor: agent pre-selected by API endpoint or auto-routing option",
                confidence=1.0
            )
        return state

    # 2. Extract last user message
    messages = state.get("messages", [])
    if not messages:
        logger.warning("No messages in state. Defaulting to portfolio_agent.")
        state["selected_agent"] = "portfolio_agent"
        if tracer:
            tracer.log_supervisor(
                agent_selected="portfolio_agent",
                reasoning="No messages in state. Defaulted to portfolio_agent as fallback.",
                confidence=1.0
            )
        return state
        
    last_msg = messages[-1]
    query = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
    logger.info(f"Routing query: '{query}'")

    if tracer:
        tracer.start_step("Supervisor Routing")

    selected = "portfolio_agent"
    reason = "Default fallback"
    confidence_score = 0.5

    try:
        rule_selected, rule_reason, rule_confidence = _rule_route(query)
        if rule_selected:
            state["selected_agent"] = rule_selected
            if tracer:
                tracer.log_supervisor(
                    agent_selected=rule_selected,
                    reasoning=rule_reason,
                    confidence=rule_confidence
                )
                tracer.end_step("Supervisor Routing", status="success")
            logger.info(f"Rule-based supervisor routing: {rule_selected} ({rule_reason})")
            return state

        start_llm = time.time() if "time" in globals() else datetime.now().timestamp()
        decision = LLMFactory.call_structured_llm(
            system_prompt=SUPERVISOR_SYSTEM,
            user_prompt=query,
            response_format_class=RoutingDecision,
            temperature=0.0,
            primary_provider="mistral"
        )
        llm_meta = LLMFactory.consume_last_call_info()
        selected = decision.route
        reason = decision.reason
        
        conf_map = {"high": 0.95, "medium": 0.70, "low": 0.30}
        confidence_score = conf_map.get(decision.confidence.lower(), 0.50)
        
        logger.info(f"Structured supervisor routing: {selected} ({reason})")
        
        if tracer:
            latency_llm = round((time.time() - start_llm) * 1000, 2)
            tracer.log_llm(
                provider=(llm_meta or {}).get("provider", "mistral"),
                model=(llm_meta or {}).get("model", settings.mistral_model or "mistral-large-latest"),
                tokens_in=300,
                tokens_out=50,
                latency_ms=latency_llm
            )
            
        if selected in ["portfolio_agent", "pnl_agent", "dividend_agent", "stock_analysis_agent"]:
            state["selected_agent"] = selected
        else:
            logger.warning(f"Invalid agent selected or direct: {selected}. Defaulting to portfolio_agent.")
            state["selected_agent"] = "portfolio_agent"
            selected = "portfolio_agent"
            reason = "Invalid routing route, fallback to portfolio_agent"
            
        if tracer:
            tracer.log_supervisor(
                agent_selected=selected,
                reasoning=reason,
                confidence=confidence_score
            )
            tracer.end_step("Supervisor Routing", status="success")
            
    except Exception as e:
        logger.error(f"Supervisor failed to route: {e}. Defaulting to portfolio_agent.")
        state["errors"].append(f"Supervisor routing error: {str(e)}")
        state["selected_agent"] = "portfolio_agent"
        if tracer:
            tracer.log_error(e)
            tracer.log_supervisor(
                agent_selected="portfolio_agent",
                reasoning=f"Routing exception: {str(e)}. Defaulted to portfolio_agent.",
                confidence=0.1
            )
            tracer.end_step("Supervisor Routing", status="failed")

    return state
