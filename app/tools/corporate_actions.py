import os
import json
import logging
import yfinance as yf
import pandas as pd
from datetime import datetime, date
from typing import Dict, List, Optional, Any
from app.config import settings

logger = logging.getLogger("stock_intelligence.corporate_actions")

import requests

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

    if is_isin or has_spaces or is_long_name:
        # Lookup online
        logger.info(f"Looking up ticker symbol for query '{symbol}' online...")
        resolved = lookup_ticker_online(symbol)
        if resolved:
            logger.info(f"Successfully resolved '{symbol}' to '{resolved}'")
            return resolved

    # Fallback to appending exchange suffix
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
