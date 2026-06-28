import logging
import json
import os
import time
import pandas as pd
from langchain_core.tools import tool
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage

from app.config import settings
from app.state import State
from app.llm import LLMFactory
from app.tools.pnl_calculator import PnlCalculatorTool

logger = logging.getLogger("stock_intelligence.pnl_agent")

# ── Tool ──────────────────────────────────────────────────────────────
@tool
def read_excel_sheet(file_path: str, sheet_name: str = None) -> str:
    """Read an Excel sheet and return it as a JSON string of records.
    Args:
        file_path:  Absolute or relative path to the .xlsx file.
        sheet_name: Sheet name to read. Reads first sheet if omitted.
    Returns:
        JSON string of all rows for the agent to reason over.
    """
    from app.tools.excel_reader import find_header_row_and_sheet
    sheet_name, header_idx = find_header_row_and_sheet(file_path)
    df = pd.read_excel(file_path, sheet_name=sheet_name or 0, header=header_idx)
    return df.to_json(orient="records", date_format="iso")

# ── Prompt Template ───────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a financial analysis agent specialised in Indian equity
brokerage statements. Your sole job is to ingest a transaction
Excel sheet and produce a complete Profit & Loss, charges, and
portfolio analysis report.

You are given one tool: read_excel_sheet.
You must reason step-by-step before every tool call and before
writing output. Never guess or hallucinate numbers. Every figure
in your output must be directly computed from the raw data you read.

## TOOL AVAILABLE

  read_excel_sheet(file_path, sheet_name=None) → DataFrame as JSON

## MANDATORY REASONING CHAIN (follow in order)

STEP 1 — INGEST
  Call read_excel_sheet on the provided file path.
  Identify all columns present. Map them to canonical names:
  Date, ScripName, Exchange, NetQty, BuyQty, SellQty,
  BuyValue, SellValue, NetValue, MarketRate,
  Brokerage, ExchTrxnCharges, SEBICharges, OtherCharges,
  StampDuty, ServiceTax, STT, IPFTCharges,
  NetRateWithSTT, NetRateWithoutSTT

STEP 2 — CLASSIFY TRADES
  If NetQty > 0  → BUY trade
  If NetQty < 0  → SELL trade
  Group all rows by ScripName.
  For each scrip determine: is it OPEN (no matching sell) or CLOSED
  (has at least one sell that fully or partially offsets buys)?

STEP 3 — COMPUTE TOTAL CHARGES PER ROW
  For every row:
  TotalCharges = Brokerage + ExchTrxnCharges + SEBICharges
               + OtherCharges + StampDuty + ServiceTax
               + STT + IPFTCharges

STEP 4 — REALISED P&L (closed positions only)
  For each closed scrip:
    GrossPnL      = TotalSellValue − TotalBuyValue
    TotalBuyCost  = TotalBuyValue + sum(TotalCharges on BUY rows)
    TotalSellNet  = TotalSellValue − sum(TotalCharges on SELL rows)
    NetPnL        = TotalSellNet − TotalBuyCost
    ReturnPct     = (NetPnL / TotalBuyCost) × 100

STEP 5 — OPEN POSITIONS (unrealised)
  For each open scrip:
    TotalSharesHeld  = sum of BuyQty across all tranches
    TotalCostBasis   = sum(BuyValue) + sum(TotalCharges on BUY rows)
    AvgCostPerShare  = TotalCostBasis / TotalSharesHeld
    List every tranche: Date, Qty, Price, Charges

STEP 6 — PORTFOLIO-LEVEL AGGREGATES
  TotalInvested       = sum of TotalCostBasis across ALL scrips (buy side)
  TotalRealisedPnL    = sum of NetPnL across closed scrips
  TotalOpenCost       = sum of TotalCostBasis across open scrips
  GrandTotalCharges   = sum of TotalCharges across ALL rows
  ChargesBreakdown    = group GrandTotalCharges by charge type

STEP 7 — OUTPUT
  Produce the report in this exact order:
    1. Portfolio Summary (4 headline numbers)
    2. Realised Trades section (one block per closed scrip)
    3. Open Positions table (one row per scrip)
    4. Charges Breakdown table (one row per charge type + total)
    5. Per-Trade Charges table (one row per transaction)
    6. Key Observations (3–5 bullet points of insight)

  Format all currency as ₹X,XX,XXX.XX (Indian numbering system).
  Format all percentages as X.XX%.
  Never skip a step. Never output before completing all steps.

Tools available:
{tools}

Available tool names:
{tool_names}

Use the ReAct format:
Thought: Do I need to use a tool? Yes
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (repeat until done)
Thought: Do I need to use a tool? No
Final Answer: <full report>"""

async def pnl_agent_node(state: State) -> State:
    """
    P&L Agent node. Computes profit and loss metrics using a ReAct agent,
    traces execution steps into the agent_plan, and outputs a complete P&L report.
    """
    logger.info("P&L Agent node running using ReAct agent executor...")
    tracer = state.get("tracer")
    
    if tracer:
        tracer.start_step("P&L Agent Execution")

    file_path = state.get("uploaded_file")
    timeline = state.get("holding_timeline", [])
    records = state.get("portfolio_dataframe", [])
    
    if not file_path or not os.path.exists(file_path):
        state["result"] = {
            "agent_plan": "No portfolio file found. Suggesting upload or stock analysis.",
            "summary": (
                "📂 **No Portfolio Data Uploaded Yet**\n\n"
                "The P&L Agent analyzes your personal trade profits and losses from your brokerage Excel sheet.\n\n"
                "**To get P&L data:**\n"
                "- 🔍 **To analyze a specific stock** (price, returns, fundamentals) — just type: `Analyze TCS for 2024`\n"
                "- 📊 **For YOUR personal P&L report** — upload your brokerage Excel sheet using the upload button on the home screen."
            ),
            "insights": ["Upload your portfolio Excel to get a detailed P&L breakdown."],
            "structured_data": {}
        }
        if tracer:
            tracer.end_step("P&L Agent Execution", status="success", metadata={"file_status": "missing"})
        return state

    # Extract client info dynamically from file
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
    try:
        # Compute deterministic structured data for the API response
        logger.info("[P&L Agent] Starting deterministic calculations for structured_data...")
        df_tx = pd.DataFrame(records)
        if "date" in df_tx.columns:
            df_tx["date"] = pd.to_datetime(df_tx["date"])
            
        import time
        start_calc = time.time()
        pnl_results = PnlCalculatorTool.calculate(df_tx, timeline)
        if tracer:
            tracer.log_tool_call(
                tool_name="P&L Calculator",
                tool_type="python",
                input=f"df_tx size: {len(df_tx)}, timeline size: {len(timeline)}",
                output=f"realized_profit: {pnl_results.get('realized_profit')}, net_profit: {pnl_results.get('net_profit')}",
                latency_ms=round((time.time() - start_calc) * 1000, 2),
                success=True
            )

        # Formulate prompt for LLM structured output
        pnl_summary_str = (
            f"Realized Gross Profit: ₹{pnl_results['realized_profit']:.1f}\n"
            f"Net Profit (After Charges): ₹{pnl_results['net_profit']:.1f}\n"
            f"Unrealized P&L: ₹{pnl_results['unrealized_profit']:.1f}\n"
            f"Total Charges: ₹{pnl_results['charges']['net_charges']:.1f}\n"
            f"Winning Trades: {pnl_results['winning_trades']}\n"
            f"Losing Trades: {pnl_results['losing_trades']}\n"
        )
        
        charges = pnl_results['charges'].get('charges_breakdown', [])
        sorted_charges = sorted(charges, key=lambda x: x.get('amount', 0.0), reverse=True)
        if len(sorted_charges) > 5:
            top_charges = sorted_charges[:5]
            other_charges_sum = sum(c.get('amount', 0.0) for c in sorted_charges[5:])
            charges_breakdown_str = "\n".join([
                f"- {c['charge_type']}: ₹{c['amount']:.1f}"
                for c in top_charges
            ]) + f"\n- Other Statutory Levies: ₹{other_charges_sum:.1f}"
        else:
            charges_breakdown_str = "\n".join([
                f"- {c['charge_type']}: ₹{c['amount']:.1f}"
                for c in sorted_charges
            ])

        system_prompt = (
            "You are a financial analysis agent specialised in Indian equity brokerage statements. "
            "Based on the calculated profit, loss, and charges data below, generate a beautiful, structured summary report in clean markdown. "
            "Do not wrap the answer in a ```markdown code fence. Do not output placeholder variables such as {{current_date}}. "
            "Do NOT include any 'Insights', 'Observations', or bullet points at the end of your markdown summary report, "
            "as they are already displayed separately in the UI panel. Keep the report focused on structured metrics and narrative description. "
            "Include a summary of P&L performance, charges analysis, and key trading metrics. "
            "Also, extract 3-5 high-value key observations (e.g. costs vs net profits, win/loss ratio, winning vs losing trades impact)."
        )

        user_prompt = (
            f"## P&L SUMMARY METRICS:\n{pnl_summary_str}\n"
            f"## CHARGES BREAKDOWN:\n{charges_breakdown_str}\n\n"
            "All client identifiers were intentionally masked before this LLM call.\n"
        )

        logger.info("[P&L Agent] Requesting structured output from LLM...")
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
                tokens_in=1500, # approximate
                tokens_out=400,
                latency_ms=latency_llm
            )

        final_answer = res.summary
        insights = res.observations
        
        agent_plan = (
            "Step 1: Loaded Excel transaction data successfully.\n"
            "Step 2: Calculated realized/unrealized P&L using FIFO logic.\n"
            "Step 3: Summed and categorized all regulatory and brokerage charges.\n"
            "Step 4: Generated structured P&L summary and observations report via LLM."
        )

        state["result"] = {
            "agent_plan": agent_plan,
            "summary": final_answer,
            "insights": insights,
            "structured_data": pnl_results
        }
        if tracer:
            tracer.end_step("P&L Agent Execution", status="success")

    except Exception as e:
        logger.error(f"P&L Agent ReAct execution failed: {e}", exc_info=True)
        state["errors"].append(f"P&L Agent ReAct error: {str(e)}")
        # Fallback to standard P&L calculations
        try:
            df_tx = pd.DataFrame(records)
            if "date" in df_tx.columns:
                df_tx["date"] = pd.to_datetime(df_tx["date"])
            pnl_results = PnlCalculatorTool.calculate(df_tx, timeline)
            state["result"] = {
                "agent_plan": "Failed to compile ReAct plan.",
                "summary": f"Failed to run ReAct agent. Standard Realized P&L is ₹{pnl_results['realized_profit']:.2f}",
                "insights": [],
                "structured_data": pnl_results
            }
        except:
            state["result"] = {
                "agent_plan": "Failed to compile ReAct plan.",
                "summary": f"Failed to calculate P&L metrics: {str(e)}",
                "insights": [],
                "structured_data": {}
            }
        if tracer:
            tracer.log_error(e)
            tracer.end_step("P&L Agent Execution", status="failed")
            
    return state
