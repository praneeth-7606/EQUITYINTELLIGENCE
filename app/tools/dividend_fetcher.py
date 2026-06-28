import logging
from typing import List, Dict, Any, Optional
from langchain_core.tools import tool

from app.tools.corporate_actions import CorporateActionsTool

logger = logging.getLogger("stock_intelligence.dividend_fetcher")

@tool
def get_dividend_history(symbol: str, exchange: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Fetches the historical dividends for a given stock symbol.
    Each dividend event in the list contains the Ex-Date and the Dividend Amount per share.
    """
    logger.info(f"get_dividend_history called for {symbol} (exchange: {exchange})")
    try:
        dividends = CorporateActionsTool.get_dividends(symbol, exchange)
        return dividends
    except Exception as e:
        logger.error(f"Error fetching dividends for {symbol}: {e}")
        return []
