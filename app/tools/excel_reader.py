import os
import pandas as pd
import numpy as np
import logging
import json
import time
from typing import Dict, List, Optional, Any

from app.config import settings
from app.llm import LLMFactory
from app.privacy import redact_sample_value

logger = logging.getLogger("stock_intelligence.excel_reader")
_HEADER_SCAN_CACHE: Dict[str, tuple[Optional[str], int]] = {}

COLUMN_SYNONYMS = {
    "date": ["date", "trade date", "transaction date", "tx date", "execution date"],
    "buy_date": ["buy date", "buy_date", "purchase date", "trade date", "date", "transaction date", "tx date", "execution date"],
    "sell_date": ["sell date", "sell_date", "sale date"],
    "buy_price": ["buy price", "buy_price", "purchase price"],
    "sell_price": ["sell price", "sell_price", "sale price"],
    "price": ["price", "rate", "execution price", "avg price", "average price", "value", "marketrate", "market rate", "market_rate", "net rate w/o stt", "net rate with stt", "net rate"],
    "buy_qty": ["buy qty", "buy_qty", "buy quantity", "bought qty"],
    "sell_qty": ["sell qty", "sell_qty", "sell quantity", "sold qty"],
    "net_qty": ["net qty", "net_qty", "net quantity"],
    "quantity": ["qty", "quantity", "shares", "vol", "volume", "no of shares", "no. of shares", "units"],
    "brokerage": ["brokerage", "brokerage charges", "broker", "brokerage_charges", "commission"],
    "gst": ["gst", "tax", "service tax", "service_tax", "cgst", "sgst", "igst"],
    "stt": ["stt", "securities transaction tax", "securities_transaction_tax", "stt charges"],
    "exchange_charges": ["exch trxn charges", "exch_trxn_charges", "exchange transaction charges", "exchange charges", "exch charges"],
    "sebi_charges": ["sebi charges", "sebi_charges", "sebi fee", "sebi fees"],
    "stamp_duty": ["stamp duty", "stamp_duty", "stamp charges"],
    "other_charges": ["other charges", "other_charges", "ipft charges", "ipft_charges", "other fees"],
    "exchange": ["exchange", "bse", "nse", "market"],
    "stock_name": ["stock name", "company", "company name", "stock", "stock_name", "name", "description", "scripname", "scrip name", "scrip"],
    "symbol": ["symbol", "ticker", "code", "stock symbol", "scrip code", "scrip", "instrument", "scripcode"],
    "action": ["action", "type", "transaction type", "transaction_type", "buy/sell", "buy_sell", "trade type", "trade_type", "side"],
}

def normalize_column_name(col_name: str) -> Optional[str]:
    """
    Standard hardcoded normalization (acts as fallback if LLM is offline).
    """
    if not isinstance(col_name, str):
        return None
    cleaned = col_name.strip().lower().replace("_", " ").replace("-", " ")
    for standard_name, synonyms in COLUMN_SYNONYMS.items():
        if cleaned in synonyms or col_name.strip().lower() == standard_name:
            return standard_name
    return None

def normalize_action(action_val: Any) -> str:
    """
    Normalizes trade action strings to 'BUY' or 'SELL'.
    """
    if pd.isna(action_val):
        return "BUY"
    val = str(action_val).strip().upper()
    if val in ["BUY", "B", "PURCHASE", "IN", "RECEIVE", "ADD"]:
        return "BUY"
    if val in ["SELL", "S", "SALE", "OUT", "REDEEM", "SUBTRACT"]:
        return "SELL"
    return "BUY"

def find_header_row_and_sheet(file_path: str) -> tuple[Optional[str], int]:
    """
    Scans Excel sheets and finds the header row.
    """
    if file_path in _HEADER_SCAN_CACHE:
        return _HEADER_SCAN_CACHE[file_path]

    with pd.ExcelFile(file_path) as xls:
        sheet_names = xls.sheet_names
        preferred_sheets = ["trades", "transactions", "holdings", "orders", "sheet1"]
        ordered_sheets = []
        for pref in preferred_sheets:
            for sheet in sheet_names:
                if pref in sheet.lower():
                    ordered_sheets.append(sheet)
        for sheet in sheet_names:
            if sheet not in ordered_sheets:
                ordered_sheets.append(sheet)
                
        best_sheet = ordered_sheets[0] if ordered_sheets else None
        best_header_row = 0
        max_matches = -1
        
        for sheet in ordered_sheets:
            try:
                df_preview = pd.read_excel(xls, sheet_name=sheet, nrows=15, header=None)
                for idx, row in df_preview.iterrows():
                    matches = 0
                    for cell in row:
                        if cell and isinstance(cell, str):
                            normalized = normalize_column_name(cell)
                            if normalized:
                                matches += 1
                    if matches > max_matches:
                        max_matches = matches
                        best_sheet = sheet
                        best_header_row = idx
            except Exception as e:
                logger.error(f"Failed to scan sheet {sheet}: {e}")
                
        result = (best_sheet, best_header_row)
        _HEADER_SCAN_CACHE[file_path] = result
        return result


def _heuristic_mapping_plan(columns_list: List[Any]) -> Dict[str, Any] | None:
    mappings: Dict[str, Any] = {}
    for col in columns_list:
        norm = normalize_column_name(str(col))
        if norm and norm not in mappings:
            mappings[norm] = col

    if not mappings:
        return None

    score = 0
    for required in ("symbol", "stock_name", "date", "quantity", "price", "buy_qty", "sell_qty", "net_qty"):
        if required in mappings:
            score += 1
    if score < 3:
        return None

    layout_type = "standard_row"
    if "buy_qty" in mappings and "sell_qty" in mappings:
        layout_type = "split_qty_row"
    elif "buy_date" in mappings and "sell_date" in mappings:
        layout_type = "matched_row"

    return {
        "layout_type": layout_type,
        "mappings": mappings,
        "action_values_map": {"B": "BUY", "S": "SELL", "BUY": "BUY", "SELL": "SELL"},
    }

def generate_mapping_plan(file_path: str, tracer=None) -> Dict[str, Any]:
    """
    Inspects Excel columns and generates an LLM-driven Mapping Plan.
    """
    logger.info("Generating column mapping plan via LLM...")
    sheet_name, header_idx = find_header_row_and_sheet(file_path)
    if not sheet_name:
        raise ValueError("No sheets found in Excel file.")

    with pd.ExcelFile(file_path) as xls:
        df_preview = pd.read_excel(xls, sheet_name=sheet_name, nrows=2, header=header_idx)
        
    columns_list = list(df_preview.columns)
    heuristic_plan = _heuristic_mapping_plan(columns_list)
    if heuristic_plan:
        logger.info(f"Heuristic mapping plan generated without LLM. Layout detected: {heuristic_plan.get('layout_type')}")
        return heuristic_plan

    sample_rows = df_preview.fillna("").to_dict(orient="records")
    
    # Clean and truncate string values to limit context token count
    cleaned_samples = []
    for r in sample_rows:
        row_dict = {}
        for k, v in r.items():
            row_dict[k] = redact_sample_value(str(k), v)
        cleaned_samples.append(row_dict)

    system_prompt = (
        "You are the Data Architect of the Stock Intelligence Platform.\n"
        "Your task is to analyze the columns and sample data of an uploaded stock ledger sheet, "
        "and map the actual Excel column headers to our standard internal headers.\n\n"
        "Standard Internal Fields:\n"
        "- date: Date of trade transaction\n"
        "- buy_date: Buy Date (only for matched-rows containing buy/sell in same row)\n"
        "- sell_date: Sell Date (only for matched-rows)\n"
        "- symbol: Ticker symbol (e.g. RELIANCE, TCS, AAPL)\n"
        "- stock_name: Full name of the company\n"
        "- action: Column indicating Trade Type, Action, Side (BUY/SELL)\n"
        "- quantity: Share quantity for standard layouts\n"
        "- buy_qty: Buy Quantity column (if sheet has separate Buy Qty and Sell Qty columns)\n"
        "- sell_qty: Sell Quantity column (if separate Buy and Sell Qty columns exist)\n"
        "- net_qty: Net Quantity column (if it keeps net transaction volume change)\n"
        "- price: Executed rate/price per share (e.g. MarketRate)\n"
        "- buy_price: Buy Price (only for matched-rows)\n"
        "- sell_price: Sell Price (only for matched-rows)\n"
        "- brokerage: Brokerage charges\n"
        "- gst: GST / Service Tax\n"
        "- stt: Securities Transaction Tax\n"
        "- exchange_charges: Exchange transaction charges\n"
        "- sebi_charges: SEBI turnover fees\n"
        "- stamp_duty: Stamp duty tax\n"
        "- other_charges: Other charges (IPFT, transaction fees, etc.)\n"
        "- exchange: Exchange name (BSE/NSE/NASDAQ etc.)\n\n"
        "Analyze the columns carefully. Decide if the sheet has:\n"
        "- 'matched_row' layout: contains separate columns for both buy_date/buy_price AND sell_date/sell_price in the same row.\n"
        "- 'split_qty_row' layout: contains separate columns for 'Buy Qty' and 'Sell Qty' in a single row.\n"
        "- 'standard_row' layout: normal sequential rows (one action per row).\n\n"
        "Return your mapping in JSON format matching this schema. "
        "Do NOT include any comments (like // or /*) or extra text inside the JSON object:\n"
        "{\n"
        "  \"layout_type\": \"standard_row\" | \"split_qty_row\" | \"matched_row\",\n"
        "  \"mappings\": {\n"
        "    \"standard_field_name\": \"actual_column_name_or_null\"\n"
        "  },\n"
        "  \"action_values_map\": {\n"
        "    \"actual_cell_value\": \"BUY\" | \"SELL\"\n"
        "  }\n"
        "}"
    )

    user_content = (
        f"Sheet name: {sheet_name}\n"
        f"Available columns: {columns_list}\n"
        f"Sample rows:\n{json.dumps(cleaned_samples, indent=2, default=str)}"
    )

    try:
        start_llm = time.time()
        response = LLMFactory.invoke_text_llm(
            system_prompt=system_prompt,
            user_prompt=user_content,
            temperature=0.0,
            primary_provider="mistral"
        )
        llm_meta = LLMFactory.consume_last_call_info()
        
        raw_content = response.content
        if isinstance(raw_content, list):
            text = "".join([block.get("text", "") if isinstance(block, dict) else str(block) for block in raw_content])
        else:
            text = str(raw_content)

        if "{" in text:
            text = text[text.find("{"):text.rfind("}")+1]
            
        # Clean inline comments
        clean_lines = []
        for line in text.splitlines():
            if "//" in line:
                parts = line.split("//")
                if parts[0].count('"') % 2 == 0:
                    line = parts[0]
            clean_lines.append(line)
        text = "\n".join(clean_lines)

        plan = json.loads(text)
        logger.info(f"LLM Mapping Plan successfully generated. Layout detected: {plan.get('layout_type')}")
        if tracer and llm_meta:
            tracer.log_llm(
                provider=llm_meta["provider"],
                model=llm_meta["model"],
                tokens_in=900,
                tokens_out=220,
                latency_ms=round((time.time() - start_llm) * 1000, 2),
            )
        return plan
        
    except Exception as e:
        logger.warning(f"Failed to generate dynamic mapping plan: {e}. Falling back to default parser.")
        # Fallback Plan matching standard Zerodha/Synonyms structures
        fallback_plan = {
            "layout_type": "standard_row",
            "mappings": {},
            "action_values_map": {"B": "BUY", "S": "SELL", "BUY": "BUY", "SELL": "SELL"}
        }
        # Attempt basic synonym mapping
        for col in columns_list:
            norm = normalize_column_name(col)
            if norm:
                fallback_plan["mappings"][norm] = col
        # If we have both buy_qty and sell_qty, change layout
        if "buy_qty" in fallback_plan["mappings"] and "sell_qty" in fallback_plan["mappings"]:
            fallback_plan["layout_type"] = "split_qty_row"
        elif "buy_date" in fallback_plan["mappings"] and "sell_date" in fallback_plan["mappings"]:
            fallback_plan["layout_type"] = "matched_row"
        return fallback_plan

def read_and_normalize_excel(file_path: str, plan: Optional[Dict[str, Any]] = None, tracer=None) -> pd.DataFrame:
    """
    Reads an Excel file and standardizes it using the provided Mapping Plan.
    If no plan is provided, generates one dynamically using the LLM.
    """
    generated_plan = plan.copy() if plan else generate_mapping_plan(file_path, tracer=tracer)
    
    # Merge custom user plan mappings if provided
    if plan and not generated_plan is plan:
        if "layout_type" in plan and plan["layout_type"]:
            generated_plan["layout_type"] = plan["layout_type"]
        if "mappings" in plan and plan["mappings"]:
            for std_col, act_col in plan["mappings"].items():
                if act_col:
                    generated_plan["mappings"][std_col] = act_col
        if "action_values_map" in plan and plan["action_values_map"]:
            for k, v in plan["action_values_map"].items():
                if v:
                    generated_plan["action_values_map"][k] = v
                    
    plan = generated_plan

    sheet_name, header_idx = find_header_row_and_sheet(file_path)
    df = pd.read_excel(file_path, sheet_name=sheet_name, header=header_idx)

    # Map actual columns to standard columns
    mappings = plan.get("mappings", {})
    layout_type = plan.get("layout_type", "standard_row")
    action_map = plan.get("action_values_map", {})

    for std_col, act_col in mappings.items():
        if act_col and act_col in df.columns:
            df[std_col] = df[act_col]

    # Fill default columns if missing
    for col in ["brokerage", "gst", "stt", "exchange_charges", "sebi_charges", "stamp_duty", "other_charges"]:
        if col not in df.columns:
            df[col] = 0.0
        else:
            df[col] = df[col].fillna(0.0).astype(float)

    if "exchange" not in df.columns:
        df["exchange"] = "NSE"

    # Synchronize symbol and stock_name fallback rename
    if "symbol" not in df.columns and "stock_name" in df.columns:
        df["symbol"] = df["stock_name"]
    elif "stock_name" not in df.columns and "symbol" in df.columns:
        df["stock_name"] = df["symbol"]

    if "stock_name" not in df.columns:
        df["stock_name"] = ""

    found_cols = set(df.columns)

    if layout_type == "matched_row" and "buy_date" in found_cols and "sell_date" in found_cols:
        logger.info("Splitting matched-row trades.")
        transactions = []
        for _, row in df.iterrows():
            symbol = row.get("symbol")
            if pd.isna(symbol):
                continue
            symbol = str(symbol).strip().upper()
            stock_name = row.get("stock_name", symbol)
            qty = float(row.get("quantity", 0.0)) if not pd.isna(row.get("quantity")) else 0.0
            if qty <= 0:
                continue

            buy_date = row.get("buy_date")
            buy_price = row.get("buy_price", row.get("price"))
            if pd.isna(buy_price) or float(buy_price) == 0.0:
                buy_val = row.get("buy_value")
                if not pd.isna(buy_val) and qty > 0:
                    buy_price = float(buy_val) / qty
                else:
                    buy_price = 0.0
            else:
                buy_price = float(buy_price)

            if not pd.isna(buy_date):
                transactions.append({
                    "date": pd.to_datetime(buy_date),
                    "symbol": symbol,
                    "stock_name": stock_name,
                    "action": "BUY",
                    "quantity": qty,
                    "price": buy_price,
                    "brokerage": float(row.get("brokerage", 0.0)),
                    "gst": float(row.get("gst", 0.0)),
                    "stt": float(row.get("stt", 0.0)),
                    "exchange_charges": float(row.get("exchange_charges", 0.0)),
                    "sebi_charges": float(row.get("sebi_charges", 0.0)),
                    "stamp_duty": float(row.get("stamp_duty", 0.0)),
                    "other_charges": float(row.get("other_charges", 0.0)),
                    "exchange": str(row.get("exchange", "NSE")).strip().upper()
                })

            sell_date = row.get("sell_date")
            sell_price = row.get("sell_price", row.get("price"))
            if pd.isna(sell_price) or float(sell_price) == 0.0:
                sell_val = row.get("sell_value")
                if not pd.isna(sell_val) and qty > 0:
                    sell_price = float(sell_val) / qty
                else:
                    sell_price = 0.0
            else:
                sell_price = float(sell_price)

            if not pd.isna(sell_date):
                transactions.append({
                    "date": pd.to_datetime(sell_date),
                    "symbol": symbol,
                    "stock_name": stock_name,
                    "action": "SELL",
                    "quantity": qty,
                    "price": sell_price,
                    "brokerage": float(row.get("brokerage", 0.0)),
                    "gst": float(row.get("gst", 0.0)),
                    "stt": float(row.get("stt", 0.0)),
                    "exchange_charges": float(row.get("exchange_charges", 0.0)),
                    "sebi_charges": float(row.get("sebi_charges", 0.0)),
                    "stamp_duty": float(row.get("stamp_duty", 0.0)),
                    "other_charges": float(row.get("other_charges", 0.0)),
                    "exchange": str(row.get("exchange", "NSE")).strip().upper()
                })
        normalized_df = pd.DataFrame(transactions)
    else:
        # Standard layouts (standard_row or split_qty_row)
        # Determine action from Buy Qty and Sell Qty columns first if split
        if layout_type == "split_qty_row" or ("buy_qty" in found_cols and "sell_qty" in found_cols):
            bq = df["buy_qty"].fillna(0.0).astype(float) if "buy_qty" in df.columns else 0.0
            sq = df["sell_qty"].fillna(0.0).astype(float) if "sell_qty" in df.columns else 0.0
            df["action"] = np.where(bq > 0.0, "BUY", "SELL")
            df["quantity"] = np.where(df["action"] == "BUY", bq, sq)
            
            # Net Qty fallback
            if "net_qty" in df.columns:
                net_q = df["net_qty"].fillna(0.0).astype(float)
                df["quantity"] = np.where(df["quantity"] == 0.0, net_q.abs(), df["quantity"])
        else:
            # Map action values using LLM mapping rules
            if "action" in df.columns:
                df["action"] = df["action"].apply(
                    lambda x: action_map.get(str(x).strip(), normalize_action(x))
                )
            else:
                if "quantity" in df.columns:
                    df["action"] = np.where(df["quantity"] < 0, "SELL", "BUY")
                else:
                    df["action"] = "BUY"

            if "quantity" not in df.columns:
                if "net_qty" in df.columns:
                    df["quantity"] = df["net_qty"].abs()
                else:
                    df["quantity"] = 0.0

        # Resolve Price dynamically if missing or 0
        if "price" not in df.columns or df["price"].fillna(0.0).astype(float).sum() == 0.0:
            if "buy_price" in df.columns or "sell_price" in df.columns:
                bp = df["buy_price"].fillna(0.0).astype(float) if "buy_price" in df.columns else 0.0
                sp = df["sell_price"].fillna(0.0).astype(float) if "sell_price" in df.columns else 0.0
                df["price"] = np.where(df["action"] == "BUY", bp, sp)
            elif "buy_value" in df.columns or "sell_value" in df.columns:
                bv = df["buy_value"].fillna(0.0).astype(float) if "buy_value" in df.columns else 0.0
                sv = df["sell_value"].fillna(0.0).astype(float) if "sell_value" in df.columns else 0.0
                val = np.where(df["action"] == "BUY", bv, sv)
                df["price"] = np.where(df["quantity"] > 0, val / df["quantity"], 0.0)

        # Normalize buy_date column name to date
        if "buy_date" in df.columns and "date" not in df.columns:
            df["date"] = df["buy_date"]

        required = ["date", "symbol", "quantity", "price"]
        for req in required:
            if req not in df.columns:
                # Basic synonyms fallback check
                fallback_found = False
                for syn in COLUMN_SYNONYMS.get(req, []):
                    # Find if any synonym is in columns
                    matches = [c for c in df.columns if c.strip().lower() == syn]
                    if matches:
                        df[req] = df[matches[0]]
                        fallback_found = True
                        break
                if not fallback_found:
                    raise ValueError(f"Missing required column: {req}.")

        # Drop missing records
        df = df.dropna(subset=["symbol", "quantity"])
        
        # Clean data structures
        df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()
        df["quantity"] = df["quantity"].astype(float)
        df["price"] = df["price"].astype(float)
        df["date"] = pd.to_datetime(df["date"])

        # Correct negative quantities
        df["action"] = np.where((df["action"] == "BUY") & (df["quantity"] < 0), "SELL", df["action"])
        df["quantity"] = df["quantity"].abs()

        df["stock_name"] = df["stock_name"].fillna(df["symbol"])
        df["exchange"] = df["exchange"].astype(str).str.strip().str.upper()

        normalized_df = df[[
            "date", "symbol", "stock_name", "action", "quantity", "price", 
            "brokerage", "gst", "stt", "exchange_charges", "sebi_charges", "stamp_duty", "other_charges", "exchange"
        ]].copy()

    # Sort chronological order
    normalized_df = normalized_df.sort_values(by=["date"]).reset_index(drop=True)
    return normalized_df
