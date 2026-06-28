import os
import json
import logging
import re
from difflib import SequenceMatcher
from io import StringIO
import yfinance as yf
import pandas as pd
from datetime import datetime, date
from typing import Dict, List, Optional, Any
from app.config import settings

logger = logging.getLogger("stock_intelligence.corporate_actions")

import requests

_NSE_SECURITY_MASTER: Optional[List[Dict[str, str]]] = None
_NSE_MASTER_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"


def _normalize_company_name(value: str) -> str:
    normalized = re.sub(r"[^A-Z0-9 ]+", " ", value.upper())
    replacements = {
        "MAGZON": "MAZAGON",
        "SHIP BUILDER": "DOCK SHIPBUILDERS",
        "SHIPBUILDERS": "SHIPBUILDERS",
        "COMPELTE": "",
        "COMPLTE": "",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    stopwords = {
        "LIMITED", "LTD", "THE", "STOCK", "SHARE", "SHARES", "ANALYSIS",
        "COMPLETE", "COMPANY", "INDIA", "INDIAN",
    }
    return " ".join(word for word in normalized.split() if word not in stopwords)


def _load_nse_security_master() -> List[Dict[str, str]]:
    global _NSE_SECURITY_MASTER
    if _NSE_SECURITY_MASTER is not None:
        return _NSE_SECURITY_MASTER

    cache_path = os.path.join(settings.cache_dir, "nse_equity_master.csv")
    csv_text = ""
    if os.path.exists(cache_path) and (datetime.now().timestamp() - os.path.getmtime(cache_path)) < 86400:
        try:
            with open(cache_path, "r", encoding="utf-8") as handle:
                csv_text = handle.read()
        except Exception as exc:
            logger.warning(f"Failed reading NSE security-master cache: {exc}")

    if not csv_text:
        try:
            response = requests.get(
                _NSE_MASTER_URL,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=8,
            )
            response.raise_for_status()
            csv_text = response.text
        except Exception as verified_exc:
            logger.warning(f"Verified NSE security-master request failed: {verified_exc}")
            try:
                response = requests.get(
                    _NSE_MASTER_URL,
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=8,
                    verify=False,
                )
                response.raise_for_status()
                csv_text = response.text
            except Exception as fallback_exc:
                logger.warning(f"NSE security-master fallback failed: {fallback_exc}")

        if csv_text:
            try:
                with open(cache_path, "w", encoding="utf-8") as handle:
                    handle.write(csv_text)
            except Exception as exc:
                logger.warning(f"Failed caching NSE security master: {exc}")

    if not csv_text:
        _NSE_SECURITY_MASTER = []
        return _NSE_SECURITY_MASTER

    frame = pd.read_csv(StringIO(csv_text))
    frame.columns = [str(column).strip() for column in frame.columns]
    symbol_col = next((column for column in frame.columns if column.upper() == "SYMBOL"), None)
    name_col = next((column for column in frame.columns if "NAME OF COMPANY" in column.upper()), None)
    if not symbol_col or not name_col:
        _NSE_SECURITY_MASTER = []
        return _NSE_SECURITY_MASTER

    _NSE_SECURITY_MASTER = [
        {
            "symbol": str(row[symbol_col]).strip(),
            "name": str(row[name_col]).strip(),
        }
        for _, row in frame.iterrows()
        if str(row[symbol_col]).strip() and str(row[name_col]).strip()
    ]
    return _NSE_SECURITY_MASTER


def lookup_ticker_from_nse_master(query: str) -> Optional[str]:
    normalized_query = _normalize_company_name(query)
    if not normalized_query:
        return None

    best_symbol = None
    best_score = 0.0
    for security in _load_nse_security_master():
        symbol = security["symbol"].upper()
        normalized_name = _normalize_company_name(security["name"])
        if normalized_query == symbol or normalized_query == normalized_name:
            return f"{symbol}.NS"
        score = max(
            SequenceMatcher(None, normalized_query, normalized_name).ratio(),
            SequenceMatcher(None, normalized_query, symbol).ratio(),
        )
        if score > best_score:
            best_score = score
            best_symbol = symbol

    if best_symbol and best_score >= 0.64:
        logger.info(f"NSE security master resolved '{query}' to '{best_symbol}.NS' (score={best_score:.2f})")
        return f"{best_symbol}.NS"
    return None

def lookup_ticker_online(query: str) -> Optional[str]:
    """
    Queries Yahoo Finance Search API to find the best matching ticker symbol.
    """
    try:
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&newsCount=0"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            quotes = data.get("quotes", [])
            for q in quotes:
                ticker = q.get("symbol")
                # We prefer NSE/BSE tickers (.NS or .BO)
                if ticker and (ticker.endswith(".NS") or ticker.endswith(".BO")):
                    return ticker
            # If no .NS/.BO ticker is found, return the first symbol found
            if quotes:
                return quotes[0].get("symbol")
    except Exception as e:
        logger.warning(f"Failed to lookup ticker online for query '{query}': {e}")
    return None

def resolve_symbol_for_yfinance(symbol: str, exchange: str = None) -> str:
    """
    Resolves symbols, ISINs, and company names to valid Yahoo Finance tickers (.NS or .BO).
    """
    symbol = symbol.strip()
    if not symbol:
        return symbol

    # If it's already a resolved ticker with a suffix, return it
    if "." in symbol and symbol.split(".")[-1].upper() in ("NS", "BO", "O", "N", "Q"):
        return symbol.upper()

    # Determine if it's an ISIN or full company name
    is_isin = len(symbol) == 12 and symbol[:2].isalpha() and symbol[2:].isalnum()
    has_spaces = " " in symbol
    is_long_name = len(symbol) > 10

    symbol_upper = symbol.upper()
    if exchange:
        exch = exchange.upper().strip()
        if "NSE" in exch:
            return f"{symbol_upper}.NS"
        if "BSE" in exch:
            return f"{symbol_upper}.BO"
            
    # Quick filter for common US tickers
    us_tickers = {"AAPL", "MSFT", "GOOG", "GOOGL", "AMZN", "META", "TSLA", "NVDA", "NFLX", "AMD"}
    if symbol_upper in us_tickers:
        return symbol_upper

    # Always search public symbol registries before assuming an NSE ticker.
    logger.info(f"Looking up ticker symbol for query '{symbol}' online...")
    resolved = lookup_ticker_online(symbol)
    if resolved:
        logger.info(f"Yahoo symbol search resolved '{symbol}' to '{resolved}'")
        return resolved

    nse_resolved = lookup_ticker_from_nse_master(symbol)
    if nse_resolved:
        return nse_resolved
        
    return f"{symbol_upper}.NS"

class CorporateActionsTool:
    """
    Utility tool to fetch and cache corporate actions: splits, bonuses, dividends, and mock buybacks/rights.
    """
    
    @staticmethod
    def _get_cache_path(symbol: str) -> str:
        return os.path.join(settings.cache_dir, f"corp_actions_{symbol.replace('.', '_')}.json")

    @classmethod
    def get_actions(cls, symbol: str, exchange: str = None) -> List[Dict[str, Any]]:
        """
        Retrieves corporate actions for a stock symbol from local cache or Yahoo Finance.
        """
        resolved_symbol = resolve_symbol_for_yfinance(symbol, exchange)
        cache_path = cls._get_cache_path(resolved_symbol)
        
        # Check cache
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r") as f:
                    cache_data = json.load(f)
                
                # Check if cache is fresh (e.g., less than 1 day old)
                mtime = os.path.getmtime(cache_path)
                if (datetime.now().timestamp() - mtime) < 86400:  # 1 day
                    logger.info(f"Loaded corporate actions for {resolved_symbol} from cache.")
                    return cache_data
            except Exception as e:
                logger.error(f"Failed reading cache for {resolved_symbol}: {e}")

        logger.info(f"Fetching corporate actions for {resolved_symbol} from Yahoo Finance...")
        actions = []
        try:
            ticker = yf.Ticker(resolved_symbol)
            
            # Fetch Splits
            try:
                splits = ticker.splits
                if not splits.empty:
                    for ts, ratio in splits.items():
                        actions.append({
                            "symbol": symbol,
                            "date": ts.strftime("%Y-%m-%d"),
                            "type": "SPLIT",
                            "ratio": float(ratio),
                            "description": f"Stock Split {ratio}:1"
                        })
            except Exception as e:
                logger.warning(f"Failed fetching splits for {resolved_symbol}: {e}")

            # Fetch Dividends
            try:
                dividends = ticker.dividends
                if not dividends.empty:
                    for ts, amt in dividends.items():
                        actions.append({
                            "symbol": symbol,
                            "date": ts.strftime("%Y-%m-%d"),
                            "type": "DIVIDEND",
                            "amount": float(amt),
                            "description": f"Cash Dividend of {amt} per share"
                        })
            except Exception as e:
                logger.warning(f"Failed fetching dividends for {resolved_symbol}: {e}")

            # Deduplicate and sort chronologically
            actions.sort(key=lambda x: x["date"])
            
            # Save to cache
            with open(cache_path, "w") as f:
                json.dump(actions, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed fetching data from yfinance for {resolved_symbol}: {e}")
            # Try to return empty list or older cache if exists
            if os.path.exists(cache_path):
                try:
                    with open(cache_path, "r") as f:
                        return json.load(f)
                except:
                    pass
            return []

        return actions

    @classmethod
    def get_splits_and_bonuses(cls, symbol: str, exchange: str = None) -> List[Dict[str, Any]]:
        """
        Helper to filter only splits and bonuses.
        Note: Yahoo Finance represents bonuses as splits (e.g., a 1:1 bonus is a 2:1 split).
        We will handle splits in the holding timeline.
        """
        actions = cls.get_actions(symbol, exchange)
        return [a for a in actions if a["type"] in ("SPLIT", "BONUS")]

    @classmethod
    def get_dividends(cls, symbol: str, exchange: str = None) -> List[Dict[str, Any]]:
        """
        Helper to filter only dividends.
        """
        actions = cls.get_actions(symbol, exchange)
        return [a for a in actions if a["type"] == "DIVIDEND"]
