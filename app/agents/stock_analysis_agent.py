import os
import logging
import json
import re
import time
import numpy as np
import pandas as pd
import requests
import urllib3
import yfinance as yf
from datetime import datetime
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field

from app.config import settings
from app.state import State
from app.llm import LLMFactory
from app.tools.corporate_actions import resolve_symbol_for_yfinance, CorporateActionsTool
from app.tools.web_research import WebResearchTool

logger = logging.getLogger("stock_intelligence.stock_analysis_agent")

_QUERY_PARSE_CACHE: Dict[str, Dict[str, Any]] = {}
_TICKER_INFO_CACHE: Dict[str, Dict[str, Any]] = {}
_TICKER_HISTORY_CACHE: Dict[tuple[str, str, str], pd.DataFrame] = {}
_CORPORATE_ACTIONS_CACHE: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
_WEB_RESEARCH_CACHE: Dict[str, List[Dict[str, Any]]] = {}
CURRENT_YEAR = datetime.now().year


def _detect_query_intent(query: str) -> str:
    lowered = query.lower()
    if any(
        phrase in lowered
        for phrase in [
            "when was",
            "which year",
            "listing year",
            "listed in",
            "got listed",
            "stock market debut",
            "ipo year",
        ]
    ):
        return "listing_fact"
    if any(
        phrase in lowered
        for phrase in [
            "who is",
            "what is",
            "founder",
            "headquarters",
            "business model",
            "latest news",
        ]
    ):
        return "company_fact"
    return "market_analysis"


def _extract_query_fast(query: str) -> Optional[Dict[str, Any]]:
    normalized = " ".join(query.strip().split())
    if not normalized:
        return None

    years = sorted({int(year) for year in re.findall(r"\b(19\d{2}|20\d{2})\b", normalized)})
    lowered = normalized.lower()
    if years and any(phrase in lowered for phrase in ["to now", "up to now", "till now", "until now", "to date"]):
        years = list(range(min(years), CURRENT_YEAR + 1))
    elif len(years) == 2 and re.search(r"\b(?:to|through|until|-)\b", lowered):
        years = list(range(min(years), max(years) + 1))
    full_dividend_history = any(
        phrase in normalized.lower()
        for phrase in [
            "complete dividend history",
            "full dividend history",
            "all dividends",
            "dividend history",
            "from listing",
            "from ipo",
            "from inception",
        ]
    )

    stripped = re.sub(r"\b(20\d{2})\b", "", normalized)
    stripped = re.sub(
        r"\b(hey|hi|hello|can|could|would|you|please|kindly|analyze|analyse|analysis|research|report|overview|details?|information|info|show|get|give|tell|find|fetch|provide|need|want|me|my|for|of|on|about|the|a|an|whole|all|data|everything|what|who|is|business|model|founder|headquarters|stock|stocks|share|shares|equity|company|price|prices|performance|returns?|trend|chart|target|forecast|outlook|compare|comparison|versus|vs|with|complete|compelte|complte|full|history|dividend|dividends|fundamental|fundamentals|technical|technicals|when|was|which|year|market|debut|ipo|got|listed|in|from|listing|date|up|to|now|latest|current)\b",
        " ",
        stripped,
        flags=re.IGNORECASE,
    )
    stripped = re.sub(r"\s+", " ", stripped).strip(" ,.-")
    stripped = " ".join(stripped.split())

    if not stripped or len(stripped) < 2:
        return None

    return {
        "symbol": stripped,
        "years": years or [CURRENT_YEAR],
        "full_dividend_history": full_dividend_history,
        "intent": _detect_query_intent(normalized),
    }


def _normalize_dividend_yield(info: Dict[str, Any]) -> Optional[float]:
    try:
        trailing_yield = info.get("trailingAnnualDividendYield")
        if trailing_yield is not None:
            return float(trailing_yield) * 100
        displayed_yield = info.get("dividendYield")
        return float(displayed_yield) if displayed_yield is not None else None
    except (TypeError, ValueError):
        return None


def _get_web_research(query: str) -> List[Dict[str, Any]]:
    cache_key = " ".join(query.lower().split())
    if cache_key not in _WEB_RESEARCH_CACHE:
        _WEB_RESEARCH_CACHE[cache_key] = WebResearchTool.search(query)
    return _WEB_RESEARCH_CACHE[cache_key]


def _get_ticker_info(ticker: yf.Ticker, resolved_symbol: str) -> Dict[str, Any]:
    if resolved_symbol in _TICKER_INFO_CACHE:
        return _TICKER_INFO_CACHE[resolved_symbol]

    info: Dict[str, Any] = {}
    try:
        info = ticker.info or {}
    except Exception as err:
        logger.warning(f"ticker.info lookup failed for {resolved_symbol}: {err}")
        info = {}

    try:
        fast_info = getattr(ticker, "fast_info", None)
        if fast_info:
            if "currentPrice" not in info:
                current_price = fast_info.get("lastPrice")
                if current_price is not None:
                    info["currentPrice"] = current_price
            if "marketCap" not in info:
                market_cap = fast_info.get("marketCap")
                if market_cap is not None:
                    info["marketCap"] = market_cap
    except Exception as err:
        logger.warning(f"fast_info lookup failed for {resolved_symbol}: {err}")

    _TICKER_INFO_CACHE[resolved_symbol] = info
    return info


def _get_history_cached(ticker: yf.Ticker, resolved_symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    cache_key = (resolved_symbol, start_date, end_date)
    if cache_key in _TICKER_HISTORY_CACHE:
        return _TICKER_HISTORY_CACHE[cache_key].copy()

    try:
        hist = _get_history_http(resolved_symbol, start_date, end_date)
    except Exception as err:
        logger.warning(f"Direct chart request failed for {resolved_symbol}: {err}; trying yfinance.")
        try:
            hist = ticker.history(start=start_date, end=end_date)
        except Exception as fallback_err:
            logger.warning(f"yfinance history failed for {resolved_symbol}: {fallback_err}")
            hist = pd.DataFrame()
    _TICKER_HISTORY_CACHE[cache_key] = hist.copy()
    return hist


def _get_history_http(resolved_symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch chart data directly when yfinance's local TLS client is unavailable."""
    period1 = int(pd.Timestamp(start_date, tz="UTC").timestamp())
    period2 = int(pd.Timestamp(end_date, tz="UTC").timestamp())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{resolved_symbol}"
    params = {
        "period1": period1,
        "period2": period2,
        "interval": "1d",
        "events": "div,splits",
    }
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
    except Exception as verified_err:
        logger.warning(f"Verified Yahoo chart request failed for {resolved_symbol}: {verified_err}")
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.get(url, params=params, headers=headers, timeout=10, verify=False)
        response.raise_for_status()

    payload = response.json()
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result or not result.get("timestamp"):
        return pd.DataFrame()

    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    frame = pd.DataFrame(
        {
            "Open": quote.get("open", []),
            "High": quote.get("high", []),
            "Low": quote.get("low", []),
            "Close": quote.get("close", []),
            "Volume": quote.get("volume", []),
        },
        index=pd.to_datetime(result["timestamp"], unit="s", utc=True),
    )
    return frame.dropna(subset=["Open", "High", "Low", "Close"])


def _needs_deep_fundamentals(query: str) -> bool:
    lowered = query.lower()
    return any(
        phrase in lowered
        for phrase in [
            "complete stock analysis",
            "full stock analysis",
            "complete analysis",
            "full analysis",
            "fundamental",
            "fundamentals",
            "pe ratio",
            "pb ratio",
            "eps",
            "book value",
            "market cap",
            "roe",
            "roce",
            "debt",
        ]
    )


def _get_corporate_actions_cached(resolved_symbol: str) -> Dict[str, List[Dict[str, Any]]]:
    if resolved_symbol in _CORPORATE_ACTIONS_CACHE:
        return _CORPORATE_ACTIONS_CACHE[resolved_symbol]

    dividends = CorporateActionsTool.get_dividends(resolved_symbol)
    splits = CorporateActionsTool.get_splits_and_bonuses(resolved_symbol)
    payload = {"dividends": dividends, "splits": splits}
    _CORPORATE_ACTIONS_CACHE[resolved_symbol] = payload
    return payload

class StockQueryExtraction(BaseModel):
    symbol: str = Field(description="The stock ticker symbol or company name mentioned in the query.")
    years: List[int] = Field(description="The list of calendar years mentioned in the query. If none are specified, default to the current year [2026].")
    full_dividend_history: bool = Field(
        default=False,
        description="Set to true if the user is asking for the COMPLETE or FULL dividend history of a stock (e.g. 'from listing date', 'complete dividend history', 'all dividends ever paid', 'from IPO to now')."
    )

class WebResearchResponse(BaseModel):
    answer: str = Field(description="A concise factual answer based only on the supplied search results.")
    observations: List[str] = Field(description="Two or three useful clarifications supported by the sources.")

class DividendHistoryLLMResponse(BaseModel):
    summary: str = Field(description="A comprehensive markdown summary of the stock's complete dividend payment history, including total dividends paid, consistency, growth trends, and key observations.")
    observations: List[str] = Field(description="A list of 4-6 key observations about the stock's dividend history and policy.")

class YearlyAnalysis(BaseModel):
    year: int = Field(description="The calendar year.")
    narrative_summary: str = Field(description="Narrative explanation of why the stock moved, quarterly results, support/resistance zones, bullish/bearish phases, and strengths/weaknesses.")
    observations: List[str] = Field(description="A list of 3 to 5 key financial takeaways for this year.")

class StockAnalysisLLMResponse(BaseModel):
    overall_summary: str = Field(description="A comprehensive markdown summary report combining all years analyzed.")
    yearly_analyses: List[YearlyAnalysis] = Field(description="Specific analysis for each requested year.")

async def stock_analysis_agent_node(state: State) -> State:
    """
    Agent node to analyze a single stock over user-specified calendar years.
    Returns structured price metrics, monthly returns, fundamentals, and AI insights.
    """
    logger.info("Stock Analysis Agent node running...")
    tracer = state.get("tracer")
    
    if tracer:
        tracer.start_step("Stock Analysis Execution")

    messages = state.get("messages", [])
    if not messages:
        state["errors"].append("Stock Analysis Agent: No user query found.")
        if tracer:
            tracer.end_step("Stock Analysis Execution", status="failed")
        return state
        
    last_msg = messages[-1]
    query = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
    logger.info(f"Extracting stock parameters from query: '{query}'")

    # Step 1: Extract symbol, years and mode from user query
    full_dividend_history = False
    intent = _detect_query_intent(query)
    fast_extraction = _QUERY_PARSE_CACHE.get(query) or _extract_query_fast(query)
    if fast_extraction:
        _QUERY_PARSE_CACHE[query] = fast_extraction
        symbol = fast_extraction["symbol"]
        years = fast_extraction["years"]
        full_dividend_history = fast_extraction["full_dividend_history"]
        intent = fast_extraction.get("intent", intent)
    else:
        try:
            start_llm = time.time()
            extraction = LLMFactory.call_structured_llm(
                system_prompt=(
                    "You are a financial query parser. Extract:\n"
                    "1. The target stock name or ticker from the user's message.\n"
                    "2. Any specific years mentioned (e.g. 2024, 2023). If no years mentioned, default to [2026].\n"
                    "3. full_dividend_history: set to true if the user asks for COMPLETE, FULL, or ALL dividend history "
                    "of a stock, or uses phrases like 'from listing date', 'from IPO', 'from inception', 'all dividends', "
                    "'complete dividend history', 'entire dividend history', 'dividend history of [stock]'."
                ),
                user_prompt=query,
                response_format_class=StockQueryExtraction,
                temperature=0.0
            )
            llm_meta = LLMFactory.consume_last_call_info()
            symbol = extraction.symbol
            years = extraction.years
            full_dividend_history = extraction.full_dividend_history
            _QUERY_PARSE_CACHE[query] = {
                "symbol": symbol,
                "years": years,
                "full_dividend_history": full_dividend_history,
                "intent": intent,
            }
            if tracer:
                tracer.log_llm(
                    provider=(llm_meta or {}).get("provider", "mistral"),
                    model=(llm_meta or {}).get("model", settings.mistral_model or "mistral-large-latest"),
                    tokens_in=400,
                    tokens_out=60,
                    latency_ms=round((time.time() - start_llm) * 1000, 2)
                )
        except Exception as e:
            logger.error(f"Failed to extract parameters: {e}")
            symbol = query.split()[-1]
            years = [2026]
            full_dividend_history = False

    # Clean up symbol
    symbol = symbol.strip().upper().replace("$", "")
    if not symbol:
        state["errors"].append("Stock Analysis Agent: Could not identify stock symbol in the query.")
        if tracer:
            tracer.end_step("Stock Analysis Execution", status="failed")
        return state

    if intent in {"listing_fact", "company_fact"}:
        if intent == "listing_fact":
            search_query = f"{symbol} stock exchange listing date NSE BSE official"
        else:
            search_query = f"{symbol} company official {query}"
        sources = _get_web_research(search_query)
        source_lines = [
            f"{index + 1}. {item['title']}: {item['snippet']} ({item['url']})"
            for index, item in enumerate(sources)
        ]
        if sources:
            try:
                research = LLMFactory.call_structured_llm(
                    system_prompt=(
                        "You answer factual public-company questions using only the supplied web search results. "
                        "Do not guess. Distinguish the original company listing from later demerger or renamed-entity "
                        "listings when the sources indicate both. If the exact fact is not supported, say so."
                    ),
                    user_prompt=f"Question: {query}\n\nSources:\n" + "\n".join(source_lines),
                    response_format_class=WebResearchResponse,
                    temperature=0.0,
                )
                answer = research.answer
                observations = research.observations
            except Exception as err:
                logger.warning(f"Web research synthesis failed: {err}")
                evidence = "\n\n".join(
                    f"**{item['title']}**\n{item['snippet']}"
                    for item in sources[:3]
                    if item["snippet"]
                )
                answer = (
                    f"## Public information for {symbol.title()}\n\n"
                    "The language model was unavailable, so the verified search evidence is shown directly below "
                    "without adding an unsupported conclusion.\n\n"
                    f"{evidence}"
                )
                observations = [item["snippet"] for item in sources[:3] if item["snippet"]]

            source_markdown = "\n".join(
                f"- [{item['title']}]({item['url']})" for item in sources[:5]
            )
            state["result"] = {
                "agent_plan": (
                    "Step 1: Recognized a factual company question rather than a chart request.\n"
                    "Step 2: Searched public web sources without sending portfolio data.\n"
                    "Step 3: Synthesized the answer using only retrieved evidence."
                ),
                "summary": f"{answer}\n\n### Sources\n{source_markdown}",
                "insights": observations[:4],
                "structured_data": {
                    "company_name": symbol.title(),
                    "mode": "web_research",
                    "sources": sources,
                },
            }
        else:
            state["result"] = {
                "agent_plan": "Recognized a factual stock question and attempted public web research.",
                "summary": (
                    f"## {symbol.title()}\n\n"
                    "Public web sources are temporarily unavailable, so I cannot verify this fact safely right now."
                ),
                "insights": ["No portfolio or personal data was included in the web-search request."],
                "structured_data": {"company_name": symbol.title(), "mode": "web_research", "sources": []},
            }
        if tracer:
            tracer.end_step("Stock Analysis Execution", status="success")
        return state

    # Step 2: Resolve symbol to valid yfinance ticker
    resolved_symbol = resolve_symbol_for_yfinance(symbol)
    logger.info(f"Resolved symbol '{symbol}' to yfinance ticker '{resolved_symbol}'")

    try:
        ticker = yf.Ticker(resolved_symbol)
        info = _get_ticker_info(ticker, resolved_symbol)
        company_name = info.get("longName", resolved_symbol)
    except Exception as e:
        logger.error(f"Failed to fetch ticker info for {resolved_symbol}: {e}")
        state["errors"].append(f"Failed to fetch ticker info for '{resolved_symbol}'. The symbol may be invalid.")
        return state

    # ── FULL DIVIDEND HISTORY MODE ──────────────────────────────────────────────
    if full_dividend_history:
        logger.info(f"[Full Dividend History Mode] Fetching complete dividend history for {resolved_symbol}")
        try:
            all_dividends = CorporateActionsTool.get_dividends(resolved_symbol)
            
            if not all_dividends:
                state["result"] = {
                    "agent_plan": "Fetched complete dividend history from Yahoo Finance.",
                    "summary": f"# {company_name} — Dividend History\n\nNo dividend records were found for **{company_name}** ({resolved_symbol}) on Yahoo Finance. The company may not have paid any dividends, or the data may not be available.",
                    "insights": ["No dividend data available for this stock on Yahoo Finance."],
                    "structured_data": {
                        "ticker": resolved_symbol,
                        "company_name": company_name,
                        "mode": "full_dividend_history",
                        "dividends": [],
                        "fundamentals": {}
                    }
                }
                return state

            # Group dividends by year for display
            dividends_by_year: Dict[str, List[Dict]] = {}
            total_per_share = 0.0
            for d in all_dividends:
                yr = d["date"][:4]
                dividends_by_year.setdefault(yr, []).append(d)
                total_per_share += d["amount"]

            # Build yearly summary rows
            yearly_totals = []
            for yr in sorted(dividends_by_year.keys()):
                yr_divs = dividends_by_year[yr]
                yr_total = sum(d["amount"] for d in yr_divs)
                yearly_totals.append({
                    "year": yr,
                    "count": len(yr_divs),
                    "total_per_share": round(yr_total, 4),
                    "events": yr_divs
                })

            # Current dividend yield
            current_price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
            div_yield = _normalize_dividend_yield(info) or 0

            # Ask LLM to summarize
            div_text = "\n".join([
                f"Year {row['year']}: {row['count']} payment(s), total ₹{row['total_per_share']:.2f}/share"
                for row in yearly_totals
            ])
            lm_system = (
                "You are a dividend analysis expert. Given the complete dividend payment history of a stock, "
                "write a detailed and insightful markdown report. Include: total dividends paid per share over the entire history, "
                "dividend growth trends, years with highest payouts, consistency of payments, and what this reveals about the company's dividend policy. "
                "Do not wrap the answer in a ```markdown code fence. Do not output placeholder variables such as {{current_date}}."
            )
            lm_user = (
                f"Stock: {company_name} ({resolved_symbol})\n"
                f"Current Price: ₹{current_price}\nCurrent Dividend Yield: {div_yield:.2f}%\n"
                f"Total Cumulative Dividend Per Share (All Time): ₹{total_per_share:.2f}\n\n"
                f"Year-wise Summary:\n{div_text}\n\n"
                f"Full dividend records: {json.dumps(all_dividends[:50])}"
            )
            try:
                start_llm = time.time()
                llm_res = LLMFactory.call_structured_llm(
                    system_prompt=lm_system,
                    user_prompt=lm_user,
                    response_format_class=DividendHistoryLLMResponse,
                    temperature=0.0
                )
                llm_meta = LLMFactory.consume_last_call_info()
                if tracer:
                    tracer.log_llm(
                        provider=(llm_meta or {}).get("provider", "mistral"),
                        model=(llm_meta or {}).get("model", settings.mistral_model or "mistral-large-latest"),
                        tokens_in=1800,
                        tokens_out=450,
                        latency_ms=round((time.time() - start_llm) * 1000, 2)
                    )
                summary = llm_res.summary
                observations = llm_res.observations
            except Exception as lm_err:
                logger.warning(f"LLM dividend summary failed: {lm_err}. Using fallback.")
                summary = (
                    f"# {company_name} — Complete Dividend History\n\n"
                    f"**Total Cumulative Dividend Per Share (All Time):** ₹{total_per_share:.2f}\n\n"
                    f"**Current Dividend Yield:** {div_yield:.2f}%\n\n"
                    + "\n".join([f"- **{row['year']}**: {row['count']} payment(s) — ₹{row['total_per_share']:.2f}/share" for row in yearly_totals])
                )
                observations = [f"Total of {len(all_dividends)} dividend payments found across {len(yearly_totals)} years."]

            state["result"] = {
                "agent_plan": (
                    "Step 1: Detected full dividend history query.\n"
                    "Step 2: Resolved stock symbol via Yahoo Finance.\n"
                    "Step 3: Fetched complete dividend corporate actions history.\n"
                    "Step 4: Grouped by year and computed totals.\n"
                    "Step 5: Generated LLM narrative summary."
                ),
                "summary": summary,
                "insights": observations,
                "structured_data": {
                    "ticker": resolved_symbol,
                    "company_name": company_name,
                    "mode": "full_dividend_history",
                    "total_cumulative_dividend_per_share": round(total_per_share, 4),
                    "current_dividend_yield_pct": round(div_yield, 2),
                    "current_price": current_price,
                    "years_count": len(yearly_totals),
                    "dividends_count": len(all_dividends),
                    "yearly_totals": yearly_totals,
                    "all_dividends": all_dividends,
                    "fundamentals": {
                        "market_cap": info.get("marketCap"),
                        "pe_ratio": info.get("trailingPE"),
                        "dividend_yield": div_yield,
                        "eps": info.get("trailingEps"),
                        "book_value": info.get("bookValue"),
                    }
                }
            }
            return state

        except Exception as div_err:
            logger.error(f"Full dividend history fetch failed: {div_err}")
            state["errors"].append(f"Failed to fetch dividend history for {resolved_symbol}: {div_err}")
            return state
    # ── END FULL DIVIDEND HISTORY MODE ────────────────────────────────────────

    deep_fundamentals_required = _needs_deep_fundamentals(query)

    # Step 3: Fetch Fundamentals
    fundamentals = {}
    if info:
        # Extract fields and normalize types
        def safe_float(val, multiply_factor=1.0):
            try:
                return float(val) * multiply_factor if val is not None else None
            except:
                return None

        # Handle dividend yield (if e.g. 0.026, convert to 2.6%)
        div_yield = _normalize_dividend_yield(info)

        # Handle margins/returns (convert decimal to percentage)
        op_margin = safe_float(info.get("operatingMargins"), 100.0)
        roe = safe_float(info.get("returnOnEquity"), 100.0)

        fundamentals = {
            "market_cap": safe_float(info.get("marketCap")),
            "pe_ratio": safe_float(info.get("trailingPE")),
            "forward_pe": safe_float(info.get("forwardPE")),
            "pb_ratio": safe_float(info.get("priceToBook")),
            "eps": safe_float(info.get("trailingEps")),
            "dividend_yield": div_yield,
            "book_value": safe_float(info.get("bookValue")),
            "revenue": safe_float(info.get("totalRevenue")),
            "net_profit": safe_float(info.get("netIncomeToCommon") or info.get("netIncome")),
            "operating_margin_pct": op_margin,
            "roe_pct": roe,
            "roce_pct": None,  # Will calculate below
            "debt": safe_float(info.get("totalDebt")),
            "free_cash_flow": safe_float(info.get("freeCashflow")),
            "enterprise_value": safe_float(info.get("enterpriseValue")),
            "shares_outstanding": safe_float(info.get("sharesOutstanding"))
        }

    # Step 4: Calculate ROCE from financials only for deep fundamental requests
    if deep_fundamentals_required:
        try:
            financials = ticker.financials
            balance_sheet = ticker.balance_sheet
            if financials is not None and not financials.empty and balance_sheet is not None and not balance_sheet.empty:
                ebit = financials.loc["EBIT"].iloc[0] if "EBIT" in financials.index else None
                total_assets = balance_sheet.loc["Total Assets"].iloc[0] if "Total Assets" in balance_sheet.index else None
                current_liab = balance_sheet.loc["Current Liabilities"].iloc[0] if "Current Liabilities" in balance_sheet.index else 0.0
                if ebit is not None and total_assets is not None:
                    capital_employed = total_assets - current_liab
                    if capital_employed > 0:
                        fundamentals["roce_pct"] = float((ebit / capital_employed) * 100)
        except Exception as err:
            logger.warning(f"Failed to calculate ROCE for {resolved_symbol}: {err}")

    min_year = min(years)
    max_year = max(years)
    try:
        all_hist = _get_history_cached(ticker, resolved_symbol, f"{min_year}-01-01", f"{max_year + 1}-01-01")
        corporate_actions = (
            _get_corporate_actions_cached(resolved_symbol)
            if info
            else {"dividends": [], "splits": []}
        )
    except Exception as err:
        logger.error(f"Market data fetch failed for {resolved_symbol}: {err}")
        state["result"] = {
            "agent_plan": (
                "Step 1: Identified the requested company.\n"
                "Step 2: Resolved its market ticker.\n"
                "Step 3: Requested live market history and company metrics.\n"
                "Step 4: The market-data provider did not return usable data."
            ),
            "summary": (
                f"## {company_name} ({resolved_symbol})\n\n"
                "The stock was identified correctly, but live market data is temporarily unavailable. "
                "Please retry shortly; no portfolio or personal information was sent to the market-data provider."
            ),
            "insights": [
                "The request was routed to the Stock Analysis Agent.",
                "Ticker resolution completed, but price history could not be retrieved.",
            ],
            "structured_data": {
                "ticker": resolved_symbol,
                "company_name": company_name,
                "fundamentals": fundamentals,
                "years": {},
                "data_status": "temporarily_unavailable",
            },
        }
        if tracer:
            tracer.log_error(err)
            tracer.end_step("Stock Analysis Execution", status="failed")
        return state
    dividends = corporate_actions["dividends"]
    splits = corporate_actions["splits"]

    dividends_by_year: Dict[str, List[Dict[str, Any]]] = {}
    for item in dividends:
        dividends_by_year.setdefault(item["date"][:4], []).append(item)

    splits_by_year: Dict[str, List[Dict[str, Any]]] = {}
    for item in splits:
        splits_by_year.setdefault(item["date"][:4], []).append(item)

    # Step 5: Process each requested year
    yearly_data = {}
    for year in sorted(years):
        logger.info(f"Compiling historical price data for {resolved_symbol} in year {year}")

        try:
            hist = all_hist[(all_hist.index >= f"{year}-01-01") & (all_hist.index < f"{year + 1}-01-01")].copy()
            if hist.empty:
                logger.warning(f"No price history found for {resolved_symbol} in year {year}.")
                continue
                
            # Basic statistics
            year_open = float(hist["Open"].iloc[0])
            year_close = float(hist["Close"].iloc[-1])
            high = float(hist["High"].max())
            low = float(hist["Low"].min())
            annual_return_pct = float(((year_close - year_open) / year_open) * 100)
            avg_volume = float(hist["Volume"].mean())

            # Volatility
            daily_returns = hist["Close"].pct_change().dropna()
            volatility_pct = 0.0
            max_drawdown_pct = 0.0
            
            if not daily_returns.empty:
                volatility_pct = float(daily_returns.std() * (252 ** 0.5) * 100)
                cum_returns = (1 + daily_returns).cumprod()
                running_max = cum_returns.cummax()
                drawdown = (cum_returns - running_max) / running_max
                max_drawdown_pct = float(drawdown.min() * 100)

            # Monthly stats
            monthly_groups = hist.groupby(hist.index.month)
            monthly_metrics = []
            month_names = {
                1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
                7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"
            }
            for m_num, m_df in monthly_groups:
                if not m_df.empty:
                    m_open = float(m_df["Open"].iloc[0])
                    m_close = float(m_df["Close"].iloc[-1])
                    m_high = float(m_df["High"].max())
                    m_low = float(m_df["Low"].min())
                    m_return = float(((m_close - m_open) / m_open) * 100)
                    monthly_metrics.append({
                        "month": month_names.get(m_num, str(m_num)),
                        "open": round(m_open, 2),
                        "close": round(m_close, 2),
                        "high": round(m_high, 2),
                        "low": round(m_low, 2),
                        "return_pct": round(m_return, 2)
                    })

            # OHLCV Chart data
            ohlcv_chart_data = []
            for idx, row in hist.iterrows():
                ohlcv_chart_data.append({
                    "date": idx.strftime("%Y-%m-%d"),
                    "open": round(float(row["Open"]), 2),
                    "high": round(float(row["High"]), 2),
                    "low": round(float(row["Low"]), 2),
                    "close": round(float(row["Close"]), 2),
                    "volume": int(row["Volume"])
                })

            year_divs = [
                {
                    "date": d["date"],
                    "amount": d["amount"],
                    "description": d["description"]
                }
                for d in dividends_by_year.get(str(year), [])
            ]

            year_splits = [
                {
                    "date": s["date"],
                    "ratio": s["ratio"],
                    "description": s["description"]
                }
                for s in splits_by_year.get(str(year), [])
            ]

            yearly_data[str(year)] = {
                "price_metrics": {
                    "year_open": round(year_open, 2),
                    "year_close": round(year_close, 2),
                    "high": round(high, 2),
                    "low": round(low, 2),
                    "annual_return_pct": round(annual_return_pct, 2),
                    "avg_volume": round(avg_volume, 1),
                    "volatility_pct": round(volatility_pct, 2),
                    "max_drawdown_pct": round(max_drawdown_pct, 2)
                },
                "monthly_metrics": monthly_metrics,
                "ohlcv_chart_data": ohlcv_chart_data,
                "corporate_actions": {
                    "dividends": year_divs,
                    "splits_and_bonuses": year_splits
                }
            }
        except Exception as e:
            logger.error(f"Error compiling yearly data for {resolved_symbol} in {year}: {e}")

    if not yearly_data:
        state["result"] = {
            "agent_plan": (
                "Step 1: Identified the requested company and ticker.\n"
                "Step 2: Loaded available company fundamentals.\n"
                "Step 3: Checked price history for the requested period."
            ),
            "summary": (
                f"## {company_name} ({resolved_symbol})\n\n"
                f"No trading history was available for {', '.join(str(year) for year in years)}. "
                "This can happen for a newly listed company or when the selected year predates its listing."
            ),
            "insights": [
                "The Stock Analysis Agent was activated successfully.",
                "Try asking for the latest analysis or specify a year after the company listing date.",
            ],
            "structured_data": {
                "ticker": resolved_symbol,
                "company_name": company_name,
                "fundamentals": fundamentals,
                "years": {},
                "data_status": "no_history_for_period",
            },
        }
        if tracer:
            tracer.end_step("Stock Analysis Execution", status="success")
        return state

    # Step 6: Query LLM for narratives and observations
    # Prepare text summary of metrics for LLM
    metrics_summary_lines = []
    for yr, y_info in yearly_data.items():
        pm = y_info["price_metrics"]
        metrics_summary_lines.append(
            f"{yr}: open {pm['year_open']}, close {pm['year_close']}, high {pm['high']}, low {pm['low']}, "
            f"return {pm['annual_return_pct']}%, volatility {pm['volatility_pct']}%, "
            f"max drawdown {pm['max_drawdown_pct']}%, avg volume {pm['avg_volume']}"
        )

    compact_fundamentals = {
        key: fundamentals.get(key)
        for key in [
            "market_cap",
            "pe_ratio",
            "forward_pe",
            "pb_ratio",
            "eps",
            "dividend_yield",
            "book_value",
            "revenue",
            "net_profit",
            "operating_margin_pct",
            "roe_pct",
            "roce_pct",
            "debt",
            "free_cash_flow",
        ]
        if fundamentals.get(key) is not None
    }

    system_prompt = (
        "You are an expert financial analysis agent. Based on the provided historical and fundamental metrics, "
        "generate a comprehensive analysis report for the stock. "
        "Explain key trends, support/resistance zones, strengths/weaknesses, bullish/bearish phases, and narration of stock price movement. "
        "Separate your narration and observations into yearly segments as requested by the output format. "
        "Do not wrap the answer in a ```markdown code fence. Do not output placeholder variables such as {{current_date}}."
    )
    user_prompt = (
        f"Analyze the stock '{company_name}' ({resolved_symbol}) for the following years: {list(yearly_data.keys())}.\n\n"
        f"## COMPANY FUNDAMENTALS:\n{json.dumps(compact_fundamentals, separators=(',', ':'))}\n\n"
        f"## YEARLY PRICE STATISTICS:\n" + "\n".join(metrics_summary_lines) + "\n"
    )

    try:
        logger.info("Requesting structured analysis report from LLM...")
        start_llm = time.time()
        res = LLMFactory.call_structured_llm(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format_class=StockAnalysisLLMResponse,
            temperature=0.0
        )
        llm_meta = LLMFactory.consume_last_call_info()
        if tracer:
            latency_llm = round((time.time() - start_llm) * 1000, 2)
            tracer.log_llm(
                provider=(llm_meta or {}).get("provider", "mistral"),
                model=(llm_meta or {}).get("model", settings.mistral_model or "mistral-large-latest"),
                tokens_in=2500, # approximate
                tokens_out=600,
                latency_ms=latency_llm
            )
        
        summary = res.overall_summary
        
        # Merge LLM narrative/insights into structured yearly data
        insights_list = []
        for ya in res.yearly_analyses:
            yr_str = str(ya.year)
            if yr_str in yearly_data:
                yearly_data[yr_str]["narrative_summary"] = ya.narrative_summary
                yearly_data[yr_str]["observations"] = ya.observations
                insights_list.extend([f"[{yr_str}] {obs}" for obs in ya.observations])
        
    except Exception as err:
        logger.error(f"LLM analysis failed: {err}. Falling back to default summaries.")
        metric_lines = []
        insights_list = []
        for yr, details in yearly_data.items():
            metrics = details["price_metrics"]
            metric_lines.append(
                f"| {yr} | Rs.{metrics['year_open']:.2f} | Rs.{metrics['year_close']:.2f} | "
                f"{metrics['annual_return_pct']:.2f}% | {metrics['volatility_pct']:.2f}% |"
            )
            direction = "gained" if metrics["annual_return_pct"] >= 0 else "lost"
            insights_list.append(
                f"{yr}: the stock {direction} {abs(metrics['annual_return_pct']):.2f}% "
                f"with a maximum drawdown of {metrics['max_drawdown_pct']:.2f}%."
            )

        summary = (
            f"## {company_name} ({resolved_symbol}) Price Analysis\n\n"
            "Live market history was retrieved successfully. The narrative model was unavailable, "
            "so the report below is calculated directly from market data.\n\n"
            "| Year | Open | Close | Return | Volatility |\n"
            "|---|---:|---:|---:|---:|\n"
            + "\n".join(metric_lines)
        )

        for yr in yearly_data:
            yearly_data[yr]["narrative_summary"] = (
                "Calculated directly from verified daily market prices; AI narration was unavailable."
            )
            yearly_data[yr]["observations"] = [
                insight for insight in insights_list if insight.startswith(f"{yr}:")
            ]

    # Step 7: Format structured output
    structured_data = {
        "ticker": resolved_symbol,
        "company_name": company_name,
        "fundamentals": fundamentals,
        "years": yearly_data
    }

    agent_plan = (
        "Step 1: Extracted target symbol and calendar years from user query.\n"
        "Step 2: Resolved symbol to valid Yahoo Finance ticker.\n"
        "Step 3: Fetched live/cached company fundamentals and balance sheet.\n"
        "Step 4: Calculated annual and monthly performance metrics and ROCE.\n"
        "Step 5: Retrieved corporate action history for specified years.\n"
        "Step 6: Generated narrative analysis and observations via LLM."
    )

    state["result"] = {
        "agent_plan": agent_plan,
        "summary": summary,
        "insights": insights_list[:6],  # limit to top 6 observations
        "structured_data": structured_data
    }

    if tracer:
        tracer.end_step("Stock Analysis Execution", status="success")

    return state
