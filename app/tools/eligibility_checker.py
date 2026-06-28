import logging
from datetime import datetime, date
from typing import Dict, List, Any

from app.tools.holding_timeline import HoldingTimelineTool

logger = logging.getLogger("stock_intelligence.eligibility_checker")

class EligibilityCheckerTool:
    """
    Evaluates dividend eligibility by cross-referencing dividend Ex-dates with the holding timeline.
    """

    @classmethod
    def check_eligibility(
        cls, 
        timeline: List[Dict[str, Any]], 
        symbol: str, 
        dividend_history: List[Dict[str, Any]],
        current_date_str: str = "2026-06-26"
    ) -> Dict[str, Any]:
        """
        Evaluates eligibility for each dividend in the history.
        Categorizes them into Received, Upcoming, and Missed.
        """
        eligible_events = []
        missed_events = []
        upcoming_events = []
        
        total_received = 0.0
        total_missed = 0.0
        total_upcoming = 0.0

        # Sort dividend history from oldest to newest
        sorted_dividends = sorted(dividend_history, key=lambda x: x["date"])
        historical_dividend_sum = sum(d["amount"] for d in sorted_dividends)

        for div in sorted_dividends:
            ex_date_str = div["date"]
            amount = div["amount"]
            
            record_date_str = div.get("record_date")
            if not record_date_str:
                record_date_str = ex_date_str
                
            shares_owned = 0.0
            shares_sold = 0.0
            symbol_events = sorted([e for e in timeline if e["symbol"] == symbol], key=lambda x: x["date"])
            
            ever_held_before = False
            for ev in symbol_events:
                if ev["date"] < ex_date_str:
                    if ev["shares_held_after"] > 0 or ev["event_type"] in ("SELL", "SELL_EXCESS"):
                        ever_held_before = True
                    if ev["event_type"] in ("SELL", "SELL_EXCESS"):
                        shares_sold += ev["quantity"]
                    shares_owned = ev["shares_held_after"]
                else:
                    break
                    
            if not ever_held_before:
                continue

            # 1. Upcoming: Ex-date is in the future
            if ex_date_str > current_date_str:
                if shares_owned > 0:
                    payout = shares_owned * amount
                    total_upcoming += payout
                    upcoming_events.append({
                        "symbol": symbol,
                        "ex_date": ex_date_str,
                        "record_date": record_date_str,
                        "amount_per_share": amount,
                        "shares_held": shares_owned,
                        "projected_payout": round(payout, 2),
                        "status": "Upcoming"
                    })
            else:
                # 2. Historical Received
                if shares_owned > 0:
                    payout = shares_owned * amount
                    total_received += payout
                    eligible_events.append({
                        "symbol": symbol,
                        "ex_date": ex_date_str,
                        "record_date": record_date_str,
                        "amount_per_share": amount,
                        "shares_held": shares_owned,
                        "payout": round(payout, 2),
                        "status": "Eligible"
                    })
                
                # 3. Historical Missed (on any shares sold before ex-date)
                if shares_sold > 0:
                    missed_payout = shares_sold * amount
                    total_missed += missed_payout
                    missed_events.append({
                        "symbol": symbol,
                        "ex_date": ex_date_str,
                        "record_date": record_date_str,
                        "amount_per_share": amount,
                        "previous_shares": shares_sold,
                        "missed_payout": round(missed_payout, 2),
                        "status": "Sold Before Ex-Date",
                        "reason": f"{shares_sold} shares sold before Ex-Date"
                    })

        return {
            "total_received": round(total_received, 2),
            "total_missed": round(total_missed, 2),
            "total_upcoming": round(total_upcoming, 2),
            "eligible": eligible_events,
            "missed": missed_events,
            "upcoming": upcoming_events,
            "historical_dividend_per_share": round(historical_dividend_sum, 2)
        }
