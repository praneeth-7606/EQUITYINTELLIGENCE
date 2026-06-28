import logging
import json
import os
import time
import pandas as pd
from datetime import datetime
from typing import Any, Dict, List
from langchain_core.tools import tool
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage

from app.config import settings
from app.state import State
from app.llm import LLMFactory
from app.privacy import build_asset_alias_map, restore_alias_list, restore_alias_text
from app.tools.corporate_actions import CorporateActionsTool
from app.tools.eligibility_checker import EligibilityCheckerTool

logger = logging.getLogger("stock_intelligence.dividend_agent")

# ── Tools ──────────────────────────────────────────────────────────────
@tool
def read_excel_sheet(file_path: str, sheet_name: str = None) -> str:
    """Read an Excel file and return JSON records."""
    from app.tools.excel_reader import find_header_row_and_sheet
    sheet_name, header_idx = find_header_row_and_sheet(file_path)
    df = pd.read_excel(file_path, sheet_name=sheet_name or 0, header=header_idx)
    return df.to_json(orient="records", date_format="iso")

@tool
def fetch_dividend_history(ticker: str, start_date: str, end_date: str) -> str:
    """
    Fetch ex-dividend dates and per-share amounts from Yahoo Finance.
    ticker: NSE format e.g. 'LEMONTREE.NS'
    start_date / end_date: 'YYYY-MM-DD'
    """
    sym = ticker
    exchange = None
    if ".NS" in sym:
        sym = sym.replace(".NS", "")
        exchange = "NSE"
    elif ".BO" in sym:
        sym = sym.replace(".BO", "")
        exchange = "BSE"
    
    divs = CorporateActionsTool.get_dividends(sym, exchange)
    result = []
    for d in divs:
        ex_date = d["date"]
        if start_date <= ex_date <= end_date:
            result.append({
                "ex_date": ex_date,
                "amount_per_share": d["amount"]
            })
    return json.dumps(result)

@tool
def get_upcoming_dividends(ticker: str) -> str:
    """
    Return the next announced or estimated dividend event for a ticker.
    Returns JSON with ex_date, amount_per_share, certainty or null.
    """
    sym = ticker
    exchange = None
    if ".NS" in sym:
        sym = sym.replace(".NS", "")
        exchange = "NSE"
    elif ".BO" in sym:
        sym = sym.replace(".BO", "")
        exchange = "BSE"
        
    from app.tools.corporate_actions import resolve_symbol_for_yfinance
    resolved = resolve_symbol_for_yfinance(sym, exchange)
    try:
        import yfinance as yf
        t = yf.Ticker(resolved)
        cal = t.calendar
        if cal is not None and "Ex-Dividend Date" in cal:
            return json.dumps({
                "ex_date": str(cal["Ex-Dividend Date"]),
                "amount_per_share": cal.get("Dividend Rate", "unknown"),
                "certainty": "announced"
            })
    except Exception as e:
        logger.warning(f"Failed to get upcoming dividends for {resolved}: {e}")
    return json.dumps(None)

# ── Prompt Template ───────────────────────────────────────────────────
DIVIDEND_SYSTEM = """You are a dividend intelligence analyst for an Indian equity platform.
You receive a brokerage transaction sheet and answer everything about
dividend history, received payouts, missed opportunities, and upcoming
dividend projections.

You never invent dividend data. Every payout figure must come from
the fetch_dividend_history tool. Every eligibility decision must
be computed by comparing ex-dividend dates against the user's
holding timeline derived from the transaction sheet.

## TOOLS AVAILABLE

  read_excel_sheet(file_path, sheet_name=None) → DataFrame as JSON
    Read the transaction sheet once at the start.

  fetch_dividend_history(ticker: str, start_date: str, end_date: str) → JSON
    Fetches ex-dividend dates and per-share payout amounts from
    Yahoo Finance for a given ticker between start_date and end_date.
    Date format: "YYYY-MM-DD". Ticker format: "SYMBOL.NS" for NSE.
    Returns list of {{ ex_date, amount_per_share, record_date, pay_date }}.

  get_upcoming_dividends(ticker: str) → JSON
    Returns projected upcoming dividend events if any are announced.
    Returns {{ ex_date, amount_per_share, certainty: "announced|estimated" }}
    or null if no upcoming dividend is known.

## MANDATORY REASONING CHAIN

STEP 1 — INGEST TRANSACTION SHEET
  Call read_excel_sheet.
  For each unique ScripName, extract:
    - All buy dates and quantities
    - All sell dates and quantities (if any)
    - Map ScripName to NSE ticker format for Yahoo Finance calls
      (e.g. "LEMON TREE HOTELS LTD" → "LEMONTREE.NS")

STEP 2 — BUILD HOLDING TIMELINE PER SCRIP
  For each scrip, compute a timeline of:
    holding_start = first buy date
    holding_end   = last sell date (or TODAY if still held)
    quantity_held_on(date) = cumulative buys - cumulative sells up to that date

  This tells you exactly how many shares were held on any given date.

STEP 3 — FETCH DIVIDEND HISTORY
  For each scrip, call:
    fetch_dividend_history(ticker, holding_start, holding_end)

  This returns all ex-dividend events that occurred while you might
  have held the stock.

STEP 4 — ELIGIBILITY CHECK (per dividend event per scrip)
  For each ex_dividend_date found:
    shares_held_on_ex_date = quantity_held_on(ex_dividend_date)

    if shares_held_on_ex_date > 0:
      → RECEIVED dividend
      dividend_amount = shares_held_on_ex_date × amount_per_share
      status = "received"

    if shares_held_on_ex_date == 0 AND scrip was held before ex_date:
      → MISSED dividend (sold too early before ex-date)
      missed_amount = last_qty_before_sale × amount_per_share
      status = "missed"

    if scrip not yet held on ex_date:
      → NOT ELIGIBLE (bought after)
      status = "not_eligible"

STEP 5 — UPCOMING DIVIDENDS
  For each scrip currently held (holding_end = TODAY):
    Call get_upcoming_dividends(ticker).
    If result is not null:
      projected_income = current_qty_held × amount_per_share
      certainty = result.certainty  ("announced" or "estimated")

STEP 6 — COMPUTE DIVIDEND YIELD
  total_dividends_received = sum of all "received" dividend_amount values
  total_capital_invested   = sum of BuyValue from the transaction sheet
  dividend_yield_on_cost   = (total_dividends_received / total_capital_invested) × 100

STEP 7 — OUTPUT (in this exact order)
  1. Dividend summary (total received, total missed, yield on cost)
  2. Received dividends table:
     (ScripName | Ex-Date | Shares Held | Per Share | Total Received)
  3. Missed dividends table:
     (ScripName | Ex-Date | Shares at Time | Per Share | Amount Missed | Reason)
  4. Upcoming dividends table:
     (ScripName | Ex-Date | Shares Held | Projected Income | Certainty)
  5. Observations:
     - Which stock contributed the most dividend income?
     - Was any significant dividend missed due to early exit?
     - Any upcoming dividend that could influence a hold/sell decision?

  Format all currency as ₹X,XX,XXX.XX.
  If fetch_dividend_history returns empty for a scrip, state:
  "No dividend events found for [ScripName] during holding period."
  Do NOT invent or estimate dividend amounts.

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

async def dividend_agent_node(state: State) -> State:
    """
    Dividend Agent node. Orchestrates the dividend intelligence pipeline
    using a ReAct agent, and outputs a complete dividend report.
    """
    logger.info("Dividend Agent node running using ReAct executor...")
    tracer = state.get("tracer")
    
    if tracer:
        tracer.start_step("Dividend Agent Execution")

    file_path = state.get("uploaded_file")
    timeline = state.get("holding_timeline", [])
    records = state.get("portfolio_dataframe", [])
    
    if not file_path or not os.path.exists(file_path):
        # Extract user query
        user_question = ""
        messages = state.get("messages", [])
        if messages:
            last_msg = messages[-1]
            user_question = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
        
        state["result"] = {
            "agent_plan": "No portfolio file found. Directing to stock_analysis_agent path.",
            "summary": (
                "📂 **No Portfolio Data Uploaded Yet**\n\n"
                "The Dividend Agent works with your personal holdings to calculate dividends received, missed, and upcoming from YOUR portfolio.\n\n"
                "**To get dividend data:**\n"
                "- 🔍 **For a specific stock's dividend history** — just type: `Get dividend history of ITC` or `Show me complete dividends of Reliance`\n"
                "- 📊 **For YOUR personal dividend report** — upload your brokerage Excel sheet using the upload button on the home screen."
            ),
            "insights": ["Use the Stock Analysis agent to fetch dividend history for any specific stock without uploading a portfolio."],
            "structured_data": {}
        }
        if tracer:
            tracer.end_step("Dividend Agent Execution", status="success", metadata={"file_status": "missing"})
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
        logger.info("[Dividend Agent] Starting deterministic calculations for structured_data...")
        df_tx = pd.DataFrame(records)
        if "date" in df_tx.columns:
            df_tx["date"] = pd.to_datetime(df_tx["date"])
            
        symbols = list(df_tx["symbol"].unique()) if not df_tx.empty else []
        capital_invested = 0.0
        for sym in symbols:
            sym_events = [e for e in timeline if e["symbol"] == sym]
            if sym_events:
                last_ev = sym_events[-1]
                shares = last_ev["shares_held_after"]
                avg_cost = last_ev["average_cost_after"]
                if shares > 0:
                    capital_invested += (shares * avg_cost)
                    
        if capital_invested == 0.0 and not df_tx.empty:
            buy_tx = df_tx[df_tx["action"] == "BUY"]
            capital_invested = float((buy_tx["quantity"] * buy_tx["price"]).sum())

        total_received = 0.0
        total_missed = 0.0
        total_upcoming = 0.0
        company_dividends = {}
        company_historical_dividends = {}
        year_dividends = {}
        combined_timeline = []
        all_missed = []
        all_upcoming = []
        
        for sym in symbols:
            exchange = df_tx[df_tx["symbol"] == sym]["exchange"].iloc[0] if "exchange" in df_tx.columns else None
            div_history = CorporateActionsTool.get_dividends(sym, exchange)
            if not div_history:
                continue
            
            # Pass today's date dynamically
            current_date_str = datetime.now().strftime("%Y-%m-%d")
            report = EligibilityCheckerTool.check_eligibility(
                timeline, sym, div_history, current_date_str=current_date_str
            )
            total_received += report["total_received"]
            total_missed += report["total_missed"]
            total_upcoming += report["total_upcoming"]
            
            company_historical_dividends[sym] = report["historical_dividend_per_share"]
            if report["total_received"] > 0:
                company_dividends[sym] = round(report["total_received"], 2)
                
            for item in report["eligible"]:
                combined_timeline.append(item)
                yr = item["ex_date"].split("-")[0]
                year_dividends[yr] = year_dividends.get(yr, 0.0) + item["payout"]
                
            for item in report["missed"]:
                all_missed.append(item)
            for item in report["upcoming"]:
                all_upcoming.append(item)

        combined_timeline.sort(key=lambda x: x["ex_date"], reverse=True)
        all_missed.sort(key=lambda x: x["ex_date"], reverse=True)
        all_upcoming.sort(key=lambda x: x["ex_date"], reverse=True)
        
        year_dividends_cleaned = {k: round(v, 2) for k, v in sorted(year_dividends.items())}
        highest_payer = None
        if company_dividends:
            highest_sym = max(company_dividends, key=company_dividends.get)
            highest_payer = {
                "symbol": highest_sym,
                "amount": company_dividends[highest_sym]
            }
            
        dividend_yield = 0.0
        if capital_invested > 0:
            dividend_yield = (total_received / capital_invested) * 100

        # ── CHART-READY: year field on each received timeline event ────
        for item in combined_timeline:
            if "year" not in item:
                item["year"] = item["ex_date"].split("-")[0]

        # ── CHART-READY: per_stock_dividend [{symbol, received, missed}]
        missed_by_stock: Dict[str, float] = {}
        for m in all_missed:
            sym = m.get("symbol", "")
            missed_by_stock[sym] = missed_by_stock.get(sym, 0.0) + m.get("missed_payout", 0.0)

        all_syms_div = set(list(company_dividends.keys()) + list(missed_by_stock.keys()))
        per_stock_dividend = [
            {
                "symbol":   sym,
                "received": round(company_dividends.get(sym, 0.0), 2),
                "missed":   round(missed_by_stock.get(sym, 0.0), 2),
            }
            for sym in sorted(all_syms_div)
        ]

        # ── CHART-READY: cumulative_dividend_timeline [{date, cumulative}]
        sorted_recv = sorted(combined_timeline, key=lambda x: x["ex_date"])
        cum_div = 0.0
        cumulative_dividend_timeline: List[Dict[str, Any]] = []
        for item in sorted_recv:
            cum_div = round(cum_div + item.get("payout", 0.0), 2)
            cumulative_dividend_timeline.append({
                "date":       item["ex_date"],
                "cumulative": cum_div,
            })

        # ── CHART-READY: projected_income + yield_pct on upcoming events
        enriched_upcoming: List[Dict[str, Any]] = []
        for item in all_upcoming:
            shares_held = item.get("shares_held", 0)
            per_share   = item.get("amount_per_share", 0.0)
            projected_income = round(shares_held * per_share, 2)
            # Compute invested cost for this symbol for yield calc
            sym_cost = 0.0
            sym_ev   = [e for e in timeline if e["symbol"] == item.get("symbol", "")]
            if sym_ev:
                last   = sym_ev[-1]
                sym_cost = round(last.get("shares_held_after", 0) * last.get("average_cost_after", 0.0), 2)
            yield_pct = round((projected_income / sym_cost * 100) if sym_cost > 0 else 0.0, 2)
            enriched_upcoming.append({
                **item,
                "projected_income": projected_income,
                "yield_pct":        yield_pct,
            })

        structured_data = {
            "total_dividend_received":  round(total_received, 2),
            "total_dividend_upcoming":  round(total_upcoming, 2),
            "total_dividend_missed":    round(total_missed, 2),
            "dividend_yield_percent":   round(dividend_yield, 2),
            "highest_dividend_payer":   highest_payer,
            "company_wise_dividend":    company_dividends,
            "company_historical_dividend_per_share": company_historical_dividends,
            "year_wise_dividend":       year_dividends_cleaned,
            "upcoming_dividends":       enriched_upcoming,
            "missed_dividends":         all_missed,
            "dividend_timeline":        combined_timeline,
            # ── Chart-ready additions ──────────────────────────────────
            "per_stock_dividend":           per_stock_dividend,          # [{symbol, received, missed}]
            "cumulative_dividend_timeline": cumulative_dividend_timeline, # [{date, cumulative}]
        }

        alias_map = build_asset_alias_map(symbols)
        aliased_question = user_question
        for original_symbol, alias in alias_map.items():
            aliased_question = aliased_question.replace(original_symbol, alias)

        # Formulate prompt for LLM structured output
        dividend_summary_str = (
            f"Total Dividends Received: ₹{total_received:.1f}\n"
            f"Total Dividends Missed: ₹{total_missed:.1f}\n"
            f"Total Upcoming Dividends: ₹{total_upcoming:.1f}\n"
            f"Dividend Yield on Cost: {dividend_yield:.1f}%\n"
            f"Highest Dividend Payer: {alias_map.get(highest_payer['symbol'], highest_payer['symbol']) if highest_payer else 'None'} (₹{highest_payer['amount'] if highest_payer else 0.0:.1f})\n"
        )
        
        historical_div_str = "\n".join([
            f"- {alias_map.get(sym, sym)}: Total Historical Dividend Released Per Share since listing = ₹{amt:.1f}"
            for sym, amt in company_historical_dividends.items()
        ])
        
        received_timeline_str = "\n".join([
            f"- {alias_map.get(item['symbol'], item['symbol'])}: Ex-Date={item['ex_date']}, Shares={item['shares_held']}, Payout Per Share=₹{item['amount_per_share']:.1f}, Total Received=₹{item['payout']:.1f}"
            for item in combined_timeline[:10]
        ])
        
        sorted_missed = sorted(all_missed, key=lambda x: x.get('missed_payout', 0.0), reverse=True)
        if len(sorted_missed) > 5:
            missed_timeline_str = "\n".join([
                f"- {alias_map.get(item['symbol'], item['symbol'])}: Ex-Date={item['ex_date']}, Payout=₹{item['amount_per_share']:.1f}, Missed Payout=₹{item['missed_payout']:.1f} ({item['reason']})"
                for item in sorted_missed[:5]
            ]) + f"\n- (+ {len(sorted_missed) - 5} other missed events)"
        else:
            missed_timeline_str = "\n".join([
                f"- {alias_map.get(item['symbol'], item['symbol'])}: Ex-Date={item['ex_date']}, Payout=₹{item['amount_per_share']:.1f}, Missed Payout=₹{item['missed_payout']:.1f} ({item['reason']})"
                for item in sorted_missed
            ])
            
        sorted_upcoming = sorted(all_upcoming, key=lambda x: x.get('projected_payout', 0.0), reverse=True)
        if len(sorted_upcoming) > 5:
            upcoming_timeline_str = "\n".join([
                f"- {alias_map.get(item['symbol'], item['symbol'])}: Ex-Date={item['ex_date']}, Projected Income=₹{item['projected_payout']:.1f} ({item['certainty']})"
                for item in sorted_upcoming[:5]
            ]) + f"\n- (+ {len(sorted_upcoming) - 5} other upcoming events)"
        else:
            upcoming_timeline_str = "\n".join([
                f"- {alias_map.get(item['symbol'], item['symbol'])}: Ex-Date={item['ex_date']}, Projected Income=₹{item['projected_payout']:.1f} ({item['certainty']})"
                for item in sorted_upcoming
            ])

        system_prompt = (
            "You are a dividend intelligence analyst for an Indian equity platform. "
            "Based on the calculated dividend metrics below, generate a beautiful, structured analysis summary report in clean markdown. "
            "Do not wrap the answer in a ```markdown code fence. Do not output placeholder variables such as {{current_date}}. "
            "Do NOT include any 'Insights', 'Observations', or bullet points at the end of your markdown summary report, "
            "as they are already displayed separately in the UI panel. Keep the report focused on structured metrics and narrative description. "
            "Include details of dividend payouts received, missed opportunities (exited early), upcoming projections, "
            "and a dedicated section/table listing the Total Historical Dividend Released Per Share for each stock in the portfolio since its listing history. "
            "Generate this full report and tables even if the user's received, missed, or upcoming dividend amounts are zero, "
            "as they need to see the historical dividend metrics of their holdings. "
            "Also, extract 3-5 key observations (such as which stock contributed the most, missed opportunities impact, and upcoming dividend decisions)."
        )

        user_prompt = (
            f"## DIVIDEND SUMMARY METRICS:\n{dividend_summary_str}\n"
            f"## HISTORICAL DIVIDENDS RELEASED PER SHARE SINCE LISTING:\n{historical_div_str if historical_div_str else 'None'}\n"
            f"## RECEIVED DIVIDENDS TIMELINE (Top 10):\n{received_timeline_str if received_timeline_str else 'None'}\n"
            f"## MISSED DIVIDENDS:\n{missed_timeline_str if missed_timeline_str else 'None'}\n"
            f"## UPCOMING ANNOUNCED DIVIDENDS:\n{upcoming_timeline_str if upcoming_timeline_str else 'None'}\n\n"
            f"Report generated on: {datetime.now().strftime('%Y-%m-%d')}\n"
            f"User's specific question (if any): {aliased_question}\n"
        )

        logger.info("[Dividend Agent] Requesting structured output from LLM...")
        from app.models import AgentResponseFormat
        import time
        start_llm = time.time()
        res = LLMFactory.call_structured_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format_class=AgentResponseFormat,
            temperature=0.0,
            primary_provider="mistral"
        )
        llm_meta = LLMFactory.consume_last_call_info()
        if tracer:
            latency_llm = round((time.time() - start_llm) * 1000, 2)
            tracer.log_llm(
                provider=(llm_meta or {}).get("provider", "mistral"),
                model=(llm_meta or {}).get("model", settings.mistral_model or "mistral-large-latest"),
                tokens_in=2000, # approximate
                tokens_out=500,
                latency_ms=latency_llm
            )

        final_answer = restore_alias_text(res.summary, alias_map)
        insights = restore_alias_list(res.observations, alias_map)
        
        agent_plan = (
            "Step 1: Loaded Excel transaction data successfully.\n"
            "Step 2: Compiled chronological holding ledger for each symbol.\n"
            "Step 3: Queried historical dividend announcements via CorporateActions API.\n"
            "Step 4: Checked ex-dividend eligibility against holding dates in Python engine.\n"
            "Step 5: Generated structured dividend summary report and observations via LLM."
        )

        state["result"] = {
            "agent_plan": agent_plan,
            "summary": final_answer,
            "insights": insights,
            "structured_data": structured_data
        }
        if tracer:
            tracer.end_step("Dividend Agent Execution", status="success")

    except Exception as e:
        logger.error(f"Dividend Agent failed: {e}", exc_info=True)
        state["errors"].append(f"Dividend Agent error: {str(e)}")
        state["result"] = {
            "agent_plan": "Failed to compile ReAct plan.",
            "summary": f"Failed to run Dividend Agent: {str(e)}",
            "insights": [],
            "structured_data": {}
        }
        if tracer:
            tracer.log_error(e)
            tracer.end_step("Dividend Agent Execution", status="failed")
            
    return state
