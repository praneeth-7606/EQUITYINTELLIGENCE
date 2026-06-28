import logging
import json
import pandas as pd
from typing import List, Dict, Any, Optional
from langchain_core.tools import tool

from app.tools.excel_reader import read_and_normalize_excel
from app.tools.holding_timeline import HoldingTimelineTool
from app.tools.pnl_calculator import PnlCalculatorTool
from app.tools.corporate_actions import CorporateActionsTool
from app.tools.eligibility_checker import EligibilityCheckerTool

logger = logging.getLogger("stock_intelligence.tools_registry")

@tool
def excel_tool(file_path: str) -> str:
    """
    Reads stock transactions from an Excel file, normalizes the columns,
    and returns a JSON string representing the list of transaction records.
    """
    logger.info(f"excel_tool executing for file: {file_path}")
    try:
        df = read_and_normalize_excel(file_path)
        records = df.to_dict(orient="records")
        # Format timestamps to string for JSON serialization
        for r in records:
            if "date" in r and hasattr(r["date"], "strftime"):
                r["date"] = r["date"].strftime("%Y-%m-%d")
        return json.dumps(records)
    except Exception as e:
        logger.error(f"Excel Tool error: {e}")
        return json.dumps({"error": str(e)})

@tool
def holding_timeline_tool(transactions_json: str) -> str:
    """
    Takes a JSON string of transaction records, processes them chronologically,
    adjusts for corporate splits and bonus issues, and returns a JSON string
    containing the detailed holding ledger.
    """
    logger.info("holding_timeline_tool executing...")
    try:
        records = json.loads(transactions_json)
        df = pd.DataFrame(records)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            
        timeline = HoldingTimelineTool.generate_timeline(df)
        return json.dumps(timeline)
    except Exception as e:
        logger.error(f"Holding Timeline Tool error: {e}")
        return json.dumps({"error": str(e)})

@tool
def corporate_action_tool(symbol: str, exchange: Optional[str] = None) -> str:
    """
    Retrieves all corporate actions (such as Splits, Bonuses, Dividends,
    Buybacks, and Rights issues) for a stock symbol.
    """
    logger.info(f"corporate_action_tool executing for {symbol}")
    try:
        actions = CorporateActionsTool.get_actions(symbol, exchange)
        return json.dumps(actions)
    except Exception as e:
        logger.error(f"Corporate Action Tool error: {e}")
        return json.dumps({"error": str(e)})

@tool
def eligibility_tool(timeline_json: str, symbol: str, dividend_history_json: str) -> str:
    """
    Cross-references a holding timeline with a dividend payment history for a stock symbol
    to determine if the investor was eligible for each dividend payment.
    """
    logger.info(f"eligibility_tool executing for {symbol}")
    try:
        timeline = json.loads(timeline_json)
        div_history = json.loads(dividend_history_json)
        report = EligibilityCheckerTool.check_eligibility(timeline, symbol, div_history)
        return json.dumps(report)
    except Exception as e:
        logger.error(f"Eligibility Tool error: {e}")
        return json.dumps({"error": str(e)})

@tool
def pnl_tool(transactions_json: str, timeline_json: str) -> str:
    """
    Performs deterministic calculations for portfolio P&L (Realized, Unrealized,
    Gross Profit, and Net Profit after fees) using transactions and holding timeline.
    """
    logger.info("pnl_tool executing...")
    try:
        transactions = json.loads(transactions_json)
        timeline = json.loads(timeline_json)
        df_tx = pd.DataFrame(transactions)
        if "date" in df_tx.columns:
            df_tx["date"] = pd.to_datetime(df_tx["date"])
            
        pnl_data = PnlCalculatorTool.calculate(df_tx, timeline)
        return json.dumps(pnl_data)
    except Exception as e:
        logger.error(f"P&L Tool error: {e}")
        return json.dumps({"error": str(e)})
