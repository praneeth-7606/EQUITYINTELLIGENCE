import logging
import pandas as pd
from datetime import datetime, date
from typing import Dict, List, Any, Optional

from app.tools.corporate_actions import CorporateActionsTool

logger = logging.getLogger("stock_intelligence.holding_timeline")

class HoldingTimelineTool:
    """
    Builds a chronological ledger of transactions and corporate actions (splits/bonuses)
    to calculate the running balance of shares, average cost, and realized P&L.
    """

    @classmethod
    def generate_timeline(cls, df_transactions: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Processes normalized transactions and applies splits/bonuses.
        Returns a sorted list of all ledger events.
        """
        symbols = df_transactions["symbol"].unique()
        all_timeline_events = []

        for symbol in symbols:
            # Filter transactions for this stock
            df_sym = df_transactions[df_transactions["symbol"] == symbol].copy()
            
            # Fetch splits & bonuses
            # We assume yfinance can fetch splits/bonuses for the symbol.
            # To be safe, we retrieve exchange info from the transaction if available
            exchange = df_sym["exchange"].iloc[0] if "exchange" in df_sym.columns else None
            splits = CorporateActionsTool.get_splits_and_bonuses(symbol, exchange)
            
            # Prepare events
            events = []
            
            # Add transactions as events
            for _, row in df_sym.iterrows():
                # Extract date as string YYYY-MM-DD
                dt_str = row["date"].strftime("%Y-%m-%d")
                charges = (
                    float(row.get("brokerage", 0.0)) +
                    float(row.get("gst", 0.0)) +
                    float(row.get("stt", 0.0)) +
                    float(row.get("exchange_charges", 0.0)) +
                    float(row.get("sebi_charges", 0.0)) +
                    float(row.get("stamp_duty", 0.0)) +
                    float(row.get("other_charges", 0.0))
                )
                events.append({
                    "date": dt_str,
                    "type": "TRANSACTION",
                    "action": row["action"],
                    "quantity": float(row["quantity"]),
                    "price": float(row["price"]),
                    "charges": charges,
                    "description": f"{row['action']} {row['quantity']} shares @ {row['price']}"
                })
                
            # Add splits as events
            for split in splits:
                events.append({
                    "date": split["date"],
                    "type": "SPLIT",
                    "action": "SPLIT",
                    "ratio": split["ratio"],
                    "description": split["description"]
                })
                
            # Sort events chronologically. For the same date: SPLIT should happen before TRANSACTION
            # (or after depending on context, typically splits happen at market open, 
            # and transactions happen during the day. Let's process SPLIT first if they fall on same day)
            events.sort(key=lambda x: (x["date"], 0 if x["type"] == "SPLIT" else 1))
            
            # Process running totals
            shares_held = 0.0
            average_cost = 0.0          # Net cost basis (with charges)
            average_buy_price = 0.0     # Gross cost basis (excluding charges)
            total_capital = 0.0         # Net capital invested
            total_capital_gross = 0.0   # Gross capital invested
            
            for ev in events:
                dt = ev["date"]
                
                if ev["type"] == "SPLIT":
                    ratio = ev["ratio"]
                    if shares_held > 0:
                        old_shares = shares_held
                        shares_held *= ratio
                        average_cost /= ratio
                        average_buy_price /= ratio
                        total_capital = shares_held * average_cost
                        total_capital_gross = shares_held * average_buy_price
                        logger.info(f"[{symbol}] Split event on {dt}: {old_shares} shares -> {shares_held} shares. Avg Cost: {average_cost}, Avg Buy Price: {average_buy_price}")
                        
                        all_timeline_events.append({
                            "date": dt,
                            "symbol": symbol,
                            "event_type": "SPLIT",
                            "quantity": ratio,
                            "price": 0.0,
                            "charges": 0.0,
                            "shares_held_after": shares_held,
                            "average_cost_after": average_cost,
                            "average_buy_price_after": average_buy_price,
                            "realized_pnl": 0.0,
                            "realized_pnl_net": 0.0,
                            "description": f"Stock Split {ratio}:1. Shares updated from {old_shares} to {shares_held}"
                        })
                else: # TRANSACTION
                    action = ev["action"]
                    qty = ev["quantity"]
                    price = ev["price"]
                    charges = ev["charges"]
                    
                    realized_pnl_gross = 0.0
                    realized_pnl_net = 0.0
                    
                    if action == "BUY":
                        total_trade_value = (qty * price) + charges
                        total_trade_value_gross = qty * price
                        
                        shares_held += qty
                        total_capital += total_trade_value
                        total_capital_gross += total_trade_value_gross
                        
                        average_cost = total_capital / shares_held if shares_held > 0 else 0.0
                        average_buy_price = total_capital_gross / shares_held if shares_held > 0 else 0.0
                        
                        all_timeline_events.append({
                            "date": dt,
                            "symbol": symbol,
                            "event_type": "BUY",
                            "quantity": qty,
                            "price": price,
                            "charges": charges,
                            "shares_held_after": shares_held,
                            "average_cost_after": average_cost,
                            "average_buy_price_after": average_buy_price,
                            "realized_pnl": 0.0,
                            "realized_pnl_net": 0.0,
                            "description": f"Bought {qty} shares @ {price} (Charges: {charges})"
                        })
                    elif action == "SELL":
                        if shares_held == 0:
                            # Short sell or missing buy transaction, log warning
                            logger.warning(f"Selling {qty} shares of {symbol} on {dt} with 0 shares in holding.")
                            realized_pnl_gross = qty * price
                            realized_pnl_net = (qty * price) - charges
                            all_timeline_events.append({
                                "date": dt,
                                "symbol": symbol,
                                "event_type": "SELL",
                                "quantity": qty,
                                "price": price,
                                "charges": charges,
                                "shares_held_after": 0.0,
                                "average_cost_after": 0.0,
                                "average_buy_price_after": 0.0,
                                "realized_pnl": realized_pnl_gross,
                                "realized_pnl_net": realized_pnl_net,
                                "description": f"Short Sold {qty} shares @ {price} (Charges: {charges})"
                            })
                            continue
                            
                        # If quantity sold exceeds shares held, cap it
                        sell_qty = min(qty, shares_held)
                        
                        cost_basis_sold_gross = sell_qty * average_buy_price
                        revenue_gross = sell_qty * price
                        realized_pnl_gross = revenue_gross - cost_basis_sold_gross
                        
                        cost_basis_sold_net = sell_qty * average_cost
                        revenue_net = (sell_qty * price) - charges
                        realized_pnl_net = revenue_net - cost_basis_sold_net
                        
                        shares_held -= sell_qty
                        total_capital = shares_held * average_cost
                        total_capital_gross = shares_held * average_buy_price
                        
                        if shares_held == 0:
                            average_cost = 0.0
                            average_buy_price = 0.0
                            total_capital = 0.0
                            total_capital_gross = 0.0
                            
                        all_timeline_events.append({
                            "date": dt,
                            "symbol": symbol,
                            "event_type": "SELL",
                            "quantity": qty,
                            "price": price,
                            "charges": charges,
                            "shares_held_after": shares_held,
                            "average_cost_after": average_cost,
                            "average_buy_price_after": average_buy_price,
                            "realized_pnl": realized_pnl_gross,
                            "realized_pnl_net": realized_pnl_net,
                            "description": f"Sold {qty} shares @ {price} (Charges: {charges})"
                        })
                        
                        # If we have residual sales (more than held), record that too
                        if qty > sell_qty:
                            extra_qty = qty - sell_qty
                            extra_pnl_gross = (extra_qty * price)
                            extra_pnl_net = (extra_qty * price)
                            logger.warning(f"Excess sell of {extra_qty} shares of {symbol} on {dt}")
                            all_timeline_events.append({
                                "date": dt,
                                "symbol": symbol,
                                "event_type": "SELL_EXCESS",
                                "quantity": extra_qty,
                                "price": price,
                                "charges": 0.0,
                                "shares_held_after": 0.0,
                                "average_cost_after": 0.0,
                                "average_buy_price_after": 0.0,
                                "realized_pnl": extra_pnl_gross,
                                "realized_pnl_net": extra_pnl_net,
                                "description": f"Excess Sold {extra_qty} shares @ {price}"
                            })
                            
        # Sort all timeline events by date and symbol
        all_timeline_events.sort(key=lambda x: (x["date"], x["symbol"]))
        return all_timeline_events

    @classmethod
    def get_shares_on_date(cls, timeline: List[Dict[str, Any]], symbol: str, target_date_str: str) -> float:
        """
        Determines the number of shares held for a symbol at the end of a specific date.
        """
        shares = 0.0
        # Sort timeline events chronologically
        sorted_events = sorted([e for e in timeline if e["symbol"] == symbol], key=lambda x: x["date"])
        
        for ev in sorted_events:
            if ev["date"] <= target_date_str:
                shares = ev["shares_held_after"]
            else:
                break
        return shares
