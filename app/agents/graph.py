import logging
import pandas as pd
import os
import json
from langgraph.graph import StateGraph, START, END
from typing import Dict, Any

from app.state import State
from app.tools.excel_reader import read_and_normalize_excel, generate_mapping_plan
from app.tools.holding_timeline import HoldingTimelineTool

# Import agent nodes
from app.agents.supervisor import supervisor_node
from app.agents.portfolio_agent import portfolio_agent_node
from app.agents.pnl_agent import pnl_agent_node
from app.agents.dividend_agent import dividend_agent_node
from app.agents.stock_analysis_agent import stock_analysis_agent_node

logger = logging.getLogger("stock_intelligence.graph")

_PORTFOLIO_PREP_CACHE: Dict[str, Dict[str, Any]] = {}


def _cache_key(file_path: str, plan: Dict[str, Any] | None = None) -> str:
    """Stable cache key for parsed Excel data and derived timeline."""
    try:
        stat = os.stat(file_path)
        mtime = stat.st_mtime
        size = stat.st_size
    except OSError:
        mtime = 0
        size = 0
    plan_fingerprint = json.dumps(plan or {}, sort_keys=True, default=str)
    return f"{file_path}:{mtime}:{size}:{plan_fingerprint}"

async def read_excel_node(state: State) -> State:
    """
    Node to read the Excel file path from state, normalize columns via LLM schema analyzer,
    and save the transaction records back to the state.
    """
    logger.info("read_excel node running...")
    tracer = state.get("tracer")
    
    if state.get("selected_agent") == "stock_analysis_agent":
        logger.info("Bypassing read_excel node for stock_analysis_agent.")
        return state
        
    if tracer:
        tracer.start_step("Read Excel File")

    file_path = state.get("uploaded_file")
    if not file_path:
        logger.info("read_excel: No file uploaded. Skipping — supervisor will route to appropriate agent.")
        if tracer:
            tracer.end_step("Read Excel File", status="success", metadata={"file_status": "missing"})
        return state
        
    try:
        # Generate schema mapping plan via LLM
        plan = state.get("mapping_plan")
        if not plan:
            plan = generate_mapping_plan(file_path, tracer=tracer)
            state["mapping_plan"] = plan

        key = _cache_key(file_path, plan)
        cached = _PORTFOLIO_PREP_CACHE.get(key)
        if cached and "records" in cached:
            state["portfolio_dataframe"] = cached["records"]
            logger.info(f"Excel read served from cache: {len(cached['records'])} transactions.")
            if tracer:
                tracer.end_step(
                    "Read Excel File",
                    status="success",
                    metadata={"records_count": len(cached["records"]), "cache_hit": True},
                )
            return state
            
        df = read_and_normalize_excel(file_path, plan=plan, tracer=tracer)
        records = df.to_dict(orient="records")
        # Format Timestamp objects to string for state consistency
        for r in records:
            if "date" in r and hasattr(r["date"], "strftime"):
                r["date"] = r["date"].strftime("%Y-%m-%d")
        state["portfolio_dataframe"] = records
        _PORTFOLIO_PREP_CACHE[key] = {
            **_PORTFOLIO_PREP_CACHE.get(key, {}),
            "records": records,
            "mapping_plan": plan,
        }
        logger.info(f"Excel read successfully: parsed {len(records)} transactions using mapping plan.")
        
        if tracer:
            tracer.end_step("Read Excel File", status="success", metadata={"records_count": len(records), "cache_hit": False})
    except Exception as e:
        logger.error(f"Failed to read Excel file: {e}")
        state["errors"].append(f"Failed to read Excel file: {str(e)}")
        if tracer:
            tracer.log_error(e)
            tracer.end_step("Read Excel File", status="failed")
        
    return state

async def create_timeline_node(state: State) -> State:
    """
    Node to generate the chronological holding ledger (timeline) from transactions.
    """
    logger.info("create_timeline node running...")
    tracer = state.get("tracer")
    
    if state.get("selected_agent") == "stock_analysis_agent":
        logger.info("Bypassing create_timeline node for stock_analysis_agent.")
        return state
        
    if tracer:
        tracer.start_step("Create Holding Timeline")

    records = state.get("portfolio_dataframe")
    if not records:
        logger.info("create_timeline: Portfolio dataframe is empty. Skipping gracefully.")
        if tracer:
            tracer.end_step("Create Holding Timeline", status="success", metadata={"timeline_status": "empty"})
        return state
        
    try:
        file_path = state.get("uploaded_file")
        key = _cache_key(file_path, state.get("mapping_plan")) if file_path else None
        cached = _PORTFOLIO_PREP_CACHE.get(key) if key else None
        if cached and "timeline" in cached:
            state["holding_timeline"] = cached["timeline"]
            logger.info(f"Holding timeline served from cache with {len(cached['timeline'])} ledger events.")
            if tracer:
                tracer.end_step(
                    "Create Holding Timeline",
                    status="success",
                    metadata={"events_count": len(cached["timeline"]), "cache_hit": True},
                )
            return state

        df_tx = pd.DataFrame(records)
        if "date" in df_tx.columns:
            df_tx["date"] = pd.to_datetime(df_tx["date"])
            
        timeline = HoldingTimelineTool.generate_timeline(df_tx)
        state["holding_timeline"] = timeline
        if key:
            _PORTFOLIO_PREP_CACHE[key] = {
                **_PORTFOLIO_PREP_CACHE.get(key, {}),
                "timeline": timeline,
            }
        logger.info(f"Holding timeline generated successfully with {len(timeline)} ledger events.")
        
        if tracer:
            tracer.end_step("Create Holding Timeline", status="success", metadata={"events_count": len(timeline), "cache_hit": False})
    except Exception as e:
        logger.error(f"Failed to create holding timeline: {e}")
        state["errors"].append(f"Failed to create holding timeline: {str(e)}")
        if tracer:
            tracer.log_error(e)
            tracer.end_step("Create Holding Timeline", status="failed")
        
    return state

# 1. Define Routing Function
def route_to_agent(state: State) -> str:
    agent = state.get("selected_agent")
    if agent in ["portfolio_agent", "pnl_agent", "dividend_agent", "stock_analysis_agent"]:
        return agent
    logger.warning(f"Invalid selected agent '{agent}'. Routing to portfolio_agent as fallback.")
    return "portfolio_agent"

# 2. Build StateGraph Workflow
workflow = StateGraph(State)

# 3. Add Nodes
workflow.add_node("read_excel", read_excel_node)
workflow.add_node("create_timeline", create_timeline_node)
workflow.add_node("supervisor", supervisor_node)
workflow.add_node("portfolio_agent", portfolio_agent_node)
workflow.add_node("pnl_agent", pnl_agent_node)
workflow.add_node("dividend_agent", dividend_agent_node)
workflow.add_node("stock_analysis_agent", stock_analysis_agent_node)

# 4. Define Transitions
workflow.add_edge(START, "read_excel")
workflow.add_edge("read_excel", "create_timeline")
workflow.add_edge("create_timeline", "supervisor")

# 5. Define Conditional Routing from Supervisor
workflow.add_conditional_edges(
    "supervisor",
    route_to_agent,
    {
        "portfolio_agent": "portfolio_agent",
        "pnl_agent": "pnl_agent",
        "dividend_agent": "dividend_agent",
        "stock_analysis_agent": "stock_analysis_agent"
    }
)

# 6. Connect Agent Nodes to END
workflow.add_edge("portfolio_agent", END)
workflow.add_edge("pnl_agent", END)
workflow.add_edge("dividend_agent", END)
workflow.add_edge("stock_analysis_agent", END)

# 7. Compile Graph
app_graph = workflow.compile()
