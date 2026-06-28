import logging
import json
import os
import time
import pandas as pd
from datetime import datetime
from langchain_core.tools import tool
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage

from app.config import settings
from app.state import State
from app.llm import LLMFactory
from app.privacy import build_asset_alias_map, restore_alias_list, restore_alias_text
from app.tools.pnl_calculator import PnlCalculatorTool, get_current_price as fetch_price

logger = logging.getLogger("stock_intelligence.portfolio_agent")

# ── Tools ──────────────────────────────────────────────────────────────
@tool
def read_excel_sheet(file_path: str, sheet_name: str = None) -> str:
    """Read an Excel file and return JSON records."""
    from app.tools.excel_reader import find_header_row_and_sheet
    sheet_name, header_idx = find_header_row_and_sheet(file_path)
    df = pd.read_excel(file_path, sheet_name=sheet_name or 0, header=header_idx)
    return df.to_json(orient="records", date_format="iso")

@tool
def get_current_price(ticker_symbol: str) -> str:
    """Fetch latest market price via Yahoo Finance. Use NSE format: SYMBOL.NS"""
    sym = ticker_symbol
    exch = None
    if ".NS" in sym:
        sym = sym.replace(".NS", "")
        exch = "NSE"
    elif ".BO" in sym:
        sym = sym.replace(".BO", "")
        exch = "BSE"
    price = fetch_price(sym, exch)
    return str(round(price, 2))

# ── Prompt Template ───────────────────────────────────────────────────
PORTFOLIO_SYSTEM = """You are a portfolio structure analyst for an Indian equity brokerage
platform. You receive a brokerage transaction Excel sheet and answer
questions about the macro structure, holding durations, and total
portfolio value. You never guess. Every number must be computed
from the raw data you read.

## TOOLS AVAILABLE

  read_excel_sheet(file_path, sheet_name=None) → DataFrame as JSON
    Use this once at the start. Do not call it again.

  get_current_price(ticker_symbol: str) → float
    Returns the latest market price for a stock.
    Use NSE ticker format (e.g. "LEMONTREE.NS").

## MANDATORY REASONING CHAIN

STEP 1 — INGEST
  Call read_excel_sheet. Identify these columns:
  Date, ScripName, NetQty, BuyQty, SellQty, BuyValue, SellValue, NetValue.
  Parse all Date fields to datetime objects.

STEP 2 — DETERMINE PORTFOLIO WINDOW
  earliest_date = min(all Date values)
  latest_date   = max(all Date values)
  total_days    = (latest_date - earliest_date).days
  active_period = f"{{total_days}} days ({{total_days//30}} months)"

STEP 3 — CLASSIFY EACH SCRIP
  For each unique ScripName:
    total_bought = sum(BuyQty where NetQty > 0)
    total_sold   = abs(sum(SellQty where NetQty < 0))
    net_held     = total_bought - total_sold

    if net_held > 0  → ACTIVE holding
    if net_held == 0 → REALIZED holding (fully exited)

STEP 4 — ACTIVE HOLDINGS (for each active scrip)
  avg_buy_price    = sum(BuyValue) / sum(BuyQty)   [across all buy tranches]
  total_cost_basis = sum(BuyValue) [buy tranches only]
  current_price    = get_current_price(ticker)
  current_value    = net_held × current_price
  unrealized_pnl   = current_value - total_cost_basis
  unrealized_pct   = (unrealized_pnl / total_cost_basis) × 100
  holding_duration = today - first_buy_date for this scrip

STEP 5 — REALIZED HOLDINGS (for each fully exited scrip)
  total_buy_value  = sum(BuyValue)
  total_sell_value = abs(sum(SellValue))
  gross_pnl        = total_sell_value - total_buy_value
  entry_date       = first buy date for this scrip
  exit_date        = last sell date for this scrip
  holding_duration = exit_date - entry_date

STEP 6 — PORTFOLIO-LEVEL AGGREGATES
  total_capital_deployed = sum(BuyValue across ALL rows)
  total_current_value    = sum(current_value for all active scrips)
                         + sum(total_sell_value for realized scrips)
  total_unrealized_pnl   = sum(unrealized_pnl across active scrips)
  total_realized_pnl     = sum(gross_pnl across realized scrips)
  [Note: charges are excluded here — pnl_agent handles those]

STEP 7 — LLM OBSERVATIONS
  After computing all numbers, generate 3–5 observations covering:
  - Concentration risk (is >40% in one stock?)
  - Holding pattern (short-term trader vs long-term investor signals)
  - Any scrip with significant unrealized loss worth flagging
  - Diversification across sectors if inferable from scrip names

STEP 8 — OUTPUT (in this exact order)
  1. Portfolio window (earliest → latest date, total days)
  2. Total capital deployed
  3. Active holdings table (ScripName | Qty | Avg Cost | CMP | Current Value | Unrealised P&L% | Days Held)
  4. Realized holdings table (ScripName | Buy Cost | Sell Value | Gross P&L | Days Held)
  5. Portfolio summary (total current value, total deployed, net P&L)
  6. Observations (3–5 bullet points)

Format all currency as ₹X,XX,XXX.XX. Format all % as X.XX%.

Tools available:
{tools}

Available tool names:
{tool_names}

Use ReAct format:
Thought: ...
Action: tool_name
Action Input: {{ "param": "value" }}
Observation: ...
Final Answer: <full report>"""

async def portfolio_agent_node(state: State) -> State:
    """
    Portfolio Agent node. Computes portfolio summary metrics,
    uses the ReAct LLM agent to draft a plan, summary, and insights, and updates state['result'].
    """
    logger.info("Portfolio Agent node running using ReAct executor...")
    tracer = state.get("tracer")
    
    if tracer:
        tracer.start_step("Portfolio Agent Execution")

    file_path = state.get("uploaded_file")
    timeline = state.get("holding_timeline", [])
    records = state.get("portfolio_dataframe", [])
    
    if not file_path or not os.path.exists(file_path):
        # Extract the user's query to form a helpful response
        user_question = ""
        messages = state.get("messages", [])
        if messages:
            last_msg = messages[-1]
            user_question = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
        
        state["result"] = {
            "agent_plan": "No portfolio file found. Suggesting stock analysis agent or upload.",
            "summary": (
                "📂 **No Portfolio Data Uploaded Yet**\n\n"
                "I need your brokerage transaction sheet to answer portfolio questions.\n\n"
                "**Two options:**\n"
                "- 🔍 **To analyze a specific stock** (e.g. ITC, Reliance) — just type: `Analyze ITC for 2024` or `Get me the dividend history of Reliance`\n"
                "- 📊 **To analyze YOUR portfolio** — upload your brokerage Excel sheet using the upload button on the home screen."
            ),
            "insights": ["Upload your portfolio Excel to get personalized portfolio insights."],
            "structured_data": {}
        }
        if tracer:
            tracer.end_step("Portfolio Agent Execution", status="success", metadata={"file_status": "missing"})
        return state

    # Parse client info dynamically from file
    client_name = "Unknown Client"
    client_code = "Unknown Code"
    try:
        with pd.ExcelFile(file_path) as xls:
            df_preview = pd.read_excel(xls, sheet_name=0, nrows=3)
        for col in df_preview.columns:
            if "client name" in str(col).lower():
                client_name = str(df_preview[col].iloc[0])
            elif "client code" in str(col).lower():
                client_code = str(df_preview[col].iloc[0])
    except Exception as parse_err:
        logger.warning(f"Failed to parse client info: {parse_err}")

    # Extract user question if any
    user_question = ""
    messages = state.get("messages", [])
    if messages:
        last_msg = messages[-1]
        user_question = last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    try:
        # Compute deterministic structured data for the API response
        logger.info("[Portfolio Agent] Starting deterministic calculations for structured_data...")
        df_tx = pd.DataFrame(records)
        if "date" in df_tx.columns:
            df_tx["date"] = pd.to_datetime(df_tx["date"])
            
        import time
        start_calc = time.time()
        pnl_results = PnlCalculatorTool.calculate(df_tx, timeline)
        if tracer:
            tracer.log_tool_call(
                tool_name="Portfolio Calculator",
                tool_type="python",
                input=f"df_tx size: {len(df_tx)}, timeline size: {len(timeline)}",
                output=f"realized: {pnl_results.get('realized_profit')}, unrealized: {pnl_results.get('unrealized_profit')}",
                latency_ms=round((time.time() - start_calc) * 1000, 2),
                success=True
            )
        
        # Extract unique symbols & timeline summary
        all_symbols = list(df_tx["symbol"].unique()) if not df_tx.empty else []
        min_date = df_tx["date"].min() if not df_tx.empty else datetime.now()
        max_date = df_tx["date"].max() if not df_tx.empty else datetime.now()
        duration_days = (max_date - min_date).days if not df_tx.empty else 0
        
        today = datetime.now()

        # ── Open positions with chart-ready enrichment ─────────────────
        total_open_value = sum(
            v["current_value"]
            for v in pnl_results.get("holdings", {}).values()
        )

        current_holdings = []
        for k, v in pnl_results.get("holdings", {}).items():
            # Derive first_buy_date from timeline
            sym_buy_events = [
                e for e in timeline if e["symbol"] == k and e["event_type"] == "BUY"
            ]
            first_buy_date = sym_buy_events[0]["date"] if sym_buy_events else min_date.strftime("%Y-%m-%d")
            try:
                holding_days = (today - datetime.strptime(first_buy_date, "%Y-%m-%d")).days
            except Exception:
                holding_days = 0

            # Sector lookup (cached)
            from app.tools.pnl_calculator import get_stock_sector
            sym_exchange = df_tx[df_tx["symbol"] == k]["exchange"].iloc[0] if "exchange" in df_tx.columns and not df_tx[df_tx["symbol"] == k].empty else None
            sector = get_stock_sector(k, sym_exchange)

            allocation_pct = round(
                (v["current_value"] / total_open_value * 100) if total_open_value > 0 else 0.0, 2
            )

            current_holdings.append({
                "symbol":         k,
                "shares":         v["shares"],
                "average_cost":   v["average_cost"],
                "current_price":  v["current_price"],
                "total_cost":     v["total_cost"],
                "current_value":  v["current_value"],
                "unrealized_pnl": v["unrealized_pnl"],
                # ── Chart-ready additions ──────────────────────────────
                "return_pct":     round(
                    (v["unrealized_pnl"] / v["total_cost"] * 100) if v["total_cost"] > 0 else 0.0, 2
                ),
                "allocation_pct": allocation_pct,
                "sector":         sector,
                "holding_days":   holding_days,
                "first_buy_date": first_buy_date,
            })

        # ── Realized holdings with enrichment ──────────────────────────
        realized_holdings = []
        for sym in all_symbols:
            sym_events = [e for e in timeline if e["symbol"] == sym]
            if not sym_events or sym_events[-1]["shares_held_after"] != 0:
                continue
            buy_events  = [e for e in sym_events if e["event_type"] == "BUY"]
            sell_events = [e for e in sym_events if e["event_type"] in ("SELL", "SELL_EXCESS")]
            total_invested  = round(sum(e["quantity"] * e["price"] for e in buy_events), 2)
            total_realised  = round(sum(abs(e["quantity"]) * e["price"] for e in sell_events), 2)
            gross_pnl       = round(sum(e["realized_pnl"] for e in sell_events), 2)
            first_buy = buy_events[0]["date"] if buy_events else ""
            last_sell = sell_events[-1]["date"] if sell_events else ""
            try:
                r_hold_days = (
                    datetime.strptime(last_sell, "%Y-%m-%d") - datetime.strptime(first_buy, "%Y-%m-%d")
                ).days if first_buy and last_sell else 0
            except Exception:
                r_hold_days = 0

            realized_holdings.append({
                "symbol":         sym,
                "trades_count":   len(buy_events) + len(sell_events),
                "total_invested":  total_invested,
                "total_realised":  total_realised,
                "gross_pnl":       gross_pnl,
                "holding_days":    r_hold_days,
                "return_pct":      round((gross_pnl / total_invested * 100) if total_invested > 0 else 0.0, 2),
            })

        # ── Chart arrays ───────────────────────────────────────────────
        # Grouped bar: invested vs current value per stock
        cost_vs_value = [
            {
                "stock":    h["symbol"],
                "invested": h["total_cost"],
                "current":  h["current_value"],
            }
            for h in current_holdings
        ]

        # Open vs realised split (total capital)
        open_cost      = sum(h["total_cost"] for h in current_holdings)
        realised_cost  = sum(r["total_invested"] for r in realized_holdings)
        open_vs_realised = [
            {"label": "Open",    "value": round(open_cost, 2)},
            {"label": "Exited",  "value": round(realised_cost, 2)},
        ]

        capital_invested = open_cost + pnl_results.get("charges", {}).get("net_charges", 0.0)

        structured_data = {
            "unique_stocks_count": len(all_symbols),
            "investment_period": {
                "start_date":   min_date.strftime("%Y-%m-%d") if not df_tx.empty else "",
                "end_date":     max_date.strftime("%Y-%m-%d") if not df_tx.empty else "",
                "duration_days": int(duration_days),
            },
            "capital_invested":        round(capital_invested, 2),
            "current_investment_value": round(sum(h["current_value"] for h in current_holdings), 2),
            "current_holdings":         current_holdings,
            "realized_holdings":        realized_holdings,
            "total_unrealized_pnl":     pnl_results.get("unrealized_profit", 0.0),
            # ── Frontend-expected structures ───────────────────────────
            "portfolio_summary":  pnl_results.get("portfolio_summary"),
            "open_positions":     pnl_results.get("open_positions"),
            "realised_trades":    pnl_results.get("realised_trades"),
            "charges_breakdown":  pnl_results.get("charges_breakdown"),
            # ── Chart-ready arrays ─────────────────────────────────────
            "cost_vs_value":    cost_vs_value,     # [{stock, invested, current}]
            "open_vs_realised": open_vs_realised,  # [{label:'Open',value},{label:'Exited',value}]
        }

        alias_map = build_asset_alias_map(all_symbols)
        aliased_question = user_question
        for original_symbol, alias in alias_map.items():
            aliased_question = aliased_question.replace(original_symbol, alias)

        # Format prompt for the LLM structured call
        portfolio_summary_str = (
            f"Unique Stocks: {len(all_symbols)}\n"
            f"Analysis Period: {min_date.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')} ({duration_days} days)\n"
            f"Total Capital Deployed: ₹{structured_data['capital_invested']:,.2f}\n"
            f"Current Value: ₹{structured_data['current_investment_value']:,.2f}\n"
            f"Unrealized P&L: ₹{structured_data['total_unrealized_pnl']:,.2f}\n"
        )
        
        active_holdings_str = "\n".join([
            f"- {alias_map.get(h['symbol'], h['symbol'])}: Qty={h['shares']}, Avg Cost=₹{h['average_cost']:.1f}, CMP=₹{h['current_price']:.1f}, Current Value=₹{h['current_value']:.1f}, P&L=₹{h['unrealized_pnl']:.1f}"
            for h in current_holdings
        ])
        
        if len(realized_holdings) > 10:
            realized_holdings_to_send = realized_holdings[:10]
            others_count = len(realized_holdings) - 10
            realized_holdings_str = "\n".join([
                f"- {alias_map.get(r['symbol'], r['symbol'])}: Trades={r['trades_count']}"
                for r in realized_holdings_to_send
            ]) + f"\n- (+ {others_count} other fully realized positions)"
        else:
            realized_holdings_str = "\n".join([
                f"- {alias_map.get(r['symbol'], r['symbol'])}: Trades={r['trades_count']}"
                for r in realized_holdings
            ])

        system_prompt = (
            "You are a premium portfolio structure analyst for an Indian equity platform. "
            "Based on the calculated portfolio numbers, generate a beautiful, structured analysis summary report in clean markdown. "
            "Do not wrap the answer in a ```markdown code fence. Do not output placeholder variables such as {{current_date}}. "
            "Do NOT include any 'Insights', 'Observations', or bullet points at the end of your markdown summary report, "
            "as they are already displayed separately in the UI panel. Keep the report focused on structured metrics and narrative description. "
            "Also, extract 3-5 high-value observations covering concentration risk, holding patterns, and unrealized losses."
        )

        user_prompt = (
            f"## PORTFOLIO METRICS:\n{portfolio_summary_str}\n"
            f"## ACTIVE HOLDINGS:\n{active_holdings_str}\n"
            f"## REALIZED HOLDINGS:\n{realized_holdings_str if realized_holdings_str else 'None'}\n\n"
            f"User's specific query (if any): {aliased_question}\n"
        )

        logger.info("[Portfolio Agent] Requesting structured output from LLM...")
        from app.models import AgentResponseFormat
        start_llm = time.time()
        res = LLMFactory.call_structured_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format_class=AgentResponseFormat,
            temperature=0.0
        )
        llm_meta = LLMFactory.consume_last_call_info()
        if tracer:
            latency_llm = round((time.time() - start_llm) * 1000, 2)
            tracer.log_llm(
                provider=(llm_meta or {}).get("provider", "mistral"),
                model=(llm_meta or {}).get("model", settings.mistral_model or "mistral-large-latest"),
                tokens_in=1800, # approximate
                tokens_out=450,
                latency_ms=latency_llm
            )

        final_answer = restore_alias_text(res.summary, alias_map)
        insights = restore_alias_list(res.observations, alias_map)
        
        agent_plan = (
            "Step 1: Loaded Excel transaction data successfully.\n"
            "Step 2: Constructed portfolio timeline ledger.\n"
            "Step 3: Fetched live/cached market prices from Yahoo Finance.\n"
            "Step 4: Executed portfolio calculations in Python math engine.\n"
            "Step 5: Generated structured markdown summary and observations via LLM."
        )

        state["result"] = {
            "agent_plan": agent_plan,
            "summary": final_answer,
            "insights": insights,
            "structured_data": structured_data
        }
        if tracer:
            tracer.end_step("Portfolio Agent Execution", status="success")

    except Exception as e:
        logger.error(f"Portfolio Agent failed: {e}", exc_info=True)
        state["errors"].append(f"Portfolio Agent error: {str(e)}")
        state["result"] = {
            "agent_plan": "Failed to compile ReAct plan.",
            "summary": f"Failed to run Portfolio agent: {str(e)}",
            "insights": [],
            "structured_data": {}
        }
        if tracer:
            tracer.log_error(e)
            tracer.end_step("Portfolio Agent Execution", status="failed")
        
    return state
