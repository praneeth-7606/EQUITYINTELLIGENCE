import os
import json
import logging
import yfinance as yf
import pandas as pd
from datetime import datetime
from typing import Dict, List, Any, Optional

from app.config import settings
from app.tools.corporate_actions import resolve_symbol_for_yfinance

logger = logging.getLogger("stock_intelligence.pnl_calculator")

# Sector mapping for common stocks to avoid yfinance rate limits/failures
COMMON_SECTOR_MAP = {
    "TCS": "Technology",
    "INFY": "Technology",
    "WIPRO": "Technology",
    "HCLTECH": "Technology",
    "RELIANCE": "Energy",
    "HDFCBANK": "Financial Services",
    "ICICIBANK": "Financial Services",
    "SBIN": "Financial Services",
    "KOTAKBANK": "Financial Services",
    "AXISBANK": "Financial Services",
    "ITC": "Consumer Defensive",
    "TATASTEEL": "Basic Materials",
    "AAPL": "Technology",
    "MSFT": "Technology",
    "GOOG": "Technology",
    "GOOGL": "Technology",
    "AMZN": "Consumer Cyclical",
    "META": "Technology",
    "TSLA": "Automotive",
    "NVDA": "Technology",
}

def get_stock_sector(symbol: str, exchange: str = None) -> str:
    """
    Retrieves the sector of the stock, checking local map first, then caching via yfinance.
    """
    clean_sym = symbol.upper().strip()
    if clean_sym in COMMON_SECTOR_MAP:
        return COMMON_SECTOR_MAP[clean_sym]
        
    resolved_sym = resolve_symbol_for_yfinance(clean_sym, exchange)
    cache_path = os.path.join(settings.cache_dir, f"sector_{resolved_sym.replace('.', '_')}.txt")
    
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r") as f:
                return f.read().strip()
        except:
            pass
            
    try:
        ticker = yf.Ticker(resolved_sym)
        sector = ticker.info.get("sector", "Other")
        with open(cache_path, "w") as f:
            f.write(sector)
        return sector
    except Exception as e:
        logger.warning(f"Failed to fetch sector for {resolved_sym}: {e}")
        return "Other"

def get_current_price(symbol: str, exchange: str = None) -> float:
    """
    Fetches the current price for a stock via yfinance, cached for 1 hour.
    """
    resolved_sym = resolve_symbol_for_yfinance(symbol, exchange)
    cache_path = os.path.join(settings.cache_dir, f"price_{resolved_sym.replace('.', '_')}.json")
    
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r") as f:
                data = json.load(f)
            # 1 hour cache
            if (datetime.now().timestamp() - data["timestamp"]) < 3600:
                return data["price"]
        except:
            pass
            
    try:
        ticker = yf.Ticker(resolved_sym)
        hist = ticker.history(period="1d")
        if not hist.empty:
            price = float(hist["Close"].iloc[-1])
            with open(cache_path, "w") as f:
                json.dump({"price": price, "timestamp": datetime.now().timestamp()}, f)
            return price
    except Exception as e:
        logger.error(f"Failed to fetch current price for {resolved_sym}: {e}")
        
    return 0.0

def calculate_charges(action: str, qty: float, price: float) -> Dict[str, float]:
    """
    Calculates charges based on Indian stock delivery rates (Zerodha standards):
    - Brokerage: 0 (or 20 max, we use 0 for equity delivery)
    - STT: 0.1% on Buy and Sell
    - Exchange transaction charges: 0.00345% of turnover
    - GST: 18% of (Brokerage + Exchange charges)
    - SEBI charges: 0.0001% of turnover (10 INR per crore)
    - Stamp duty: 0.015% on Buy, 0 on Sell
    - DP charges: 13.5 + 18% GST = 15.93 INR per Sell transaction per stock
    """
    turnover = qty * price
    brokerage = 0.0
    stt = round(turnover * 0.001, 2)
    exchange_charges = round(turnover * 0.0000345, 2)
    sebi_charges = round(turnover * 0.000001, 2)
    
    gst = round((brokerage + exchange_charges) * 0.18, 2)
    
    if action.upper() == "BUY":
        stamp_duty = round(turnover * 0.00015, 2)
        dp_charges = 0.0
    else: # SELL
        stamp_duty = 0.0
        dp_charges = 15.93 # Zerodha standard DP charge incl GST
        
    net_charges = brokerage + stt + exchange_charges + gst + sebi_charges + stamp_duty + dp_charges
    
    return {
        "brokerage": brokerage,
        "stt": stt,
        "gst": gst,
        "exchange_charges": exchange_charges,
        "sebi_charges": sebi_charges,
        "stamp_duty": stamp_duty,
        "dp_charges": dp_charges,
        "net_charges": round(net_charges, 2)
    }

class PnlCalculatorTool:
    """
    Deterministic P&L Calculator that analyzes timeline events and transaction logs.
    """

    @classmethod
    def calculate(cls, df_transactions: pd.DataFrame, timeline: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Executes P&L logic.
        """
        # 1. Calculate Transaction Charges (sum of what's in sheet or fallback to calculated)
        total_brokerage = 0.0
        total_stt = 0.0
        total_gst = 0.0
        total_exchange_charges = 0.0
        total_sebi_charges = 0.0
        total_stamp_duty = 0.0
        total_dp_charges = 0.0
        total_net_charges = 0.0

        for _, row in df_transactions.iterrows():
            act = row["action"]
            qty = row["quantity"]
            prc = row["price"]
            
            # Check if columns are in df and have non-zero values
            sheet_brokerage = row.get("brokerage", 0.0)
            sheet_gst = row.get("gst", 0.0)
            sheet_stt = row.get("stt", 0.0)
            sheet_exch = row.get("exchange_charges", 0.0)
            sheet_sebi = row.get("sebi_charges", 0.0)
            sheet_stamp = row.get("stamp_duty", 0.0)
            sheet_other = row.get("other_charges", 0.0)
            
            calc = calculate_charges(act, qty, prc)
            
            # Use sheet values if present, else use calculated
            tb = float(sheet_brokerage) if not pd.isna(sheet_brokerage) and sheet_brokerage > 0 else calc["brokerage"]
            tg = float(sheet_gst) if not pd.isna(sheet_gst) and sheet_gst > 0 else calc["gst"]
            ts = float(sheet_stt) if not pd.isna(sheet_stt) and sheet_stt > 0 else calc["stt"]
            te = float(sheet_exch) if not pd.isna(sheet_exch) and sheet_exch > 0 else calc["exchange_charges"]
            tse = float(sheet_sebi) if not pd.isna(sheet_sebi) and sheet_sebi > 0 else calc["sebi_charges"]
            tst = float(sheet_stamp) if not pd.isna(sheet_stamp) and sheet_stamp > 0 else calc["stamp_duty"]
            
            # DP charges are usually not in contract notes
            sheet_dp = row.get("dp_charges", 0.0)
            tdp = float(sheet_dp) if not pd.isna(sheet_dp) and sheet_dp > 0 else calc["dp_charges"]
            
            to = float(sheet_other) if not pd.isna(sheet_other) else 0.0
            
            total_brokerage += tb
            total_gst += tg
            total_stt += ts
            total_exchange_charges += te
            total_sebi_charges += tse
            total_stamp_duty += tst
            total_dp_charges += tdp
            total_net_charges += to
            
        total_net_charges += (
            total_brokerage + total_stt + total_gst +
            total_exchange_charges + total_sebi_charges +
            total_stamp_duty + total_dp_charges
        )

        # Mapping symbol to scrip_name
        sym_to_name = {}
        if not df_transactions.empty and "symbol" in df_transactions.columns:
            for _, r in df_transactions.iterrows():
                sym = str(r["symbol"]).upper().strip()
                name = r.get("stock_name", sym)
                if name and not pd.isna(name):
                    sym_to_name[sym] = str(name).strip()

        # 2. Process Sells and Realized Profit from Timeline
        realized_profit = 0.0
        winning_trades_count = 0
        losing_trades_count = 0
        best_trade: Optional[Dict[str, Any]] = None
        worst_trade: Optional[Dict[str, Any]] = None
        
        stock_pnl: Dict[str, float] = {}
        sector_pnl: Dict[str, float] = {}
        monthly_pnl: Dict[str, float] = {}
        yearly_pnl: Dict[str, float] = {}
        
        for ev in timeline:
            if ev["event_type"] in ("SELL", "SELL_EXCESS"):
                pnl = ev["realized_pnl"]
                realized_profit += pnl
                sym = ev["symbol"]
                dt = ev["date"]
                yr = dt.split("-")[0]
                mth = "-".join(dt.split("-")[:2])
                
                logger.info(f"[Math Engine] Processing SELL event for {sym} on {dt}: Qty={ev['quantity']}, Price={ev['price']}, Realized Gross P&L={pnl:.2f}")
                
                # Winning / Losing
                if pnl > 0:
                    winning_trades_count += 1
                elif pnl < 0:
                    losing_trades_count += 1
                    
                # Best / Worst
                if best_trade is None or pnl > best_trade["pnl"]:
                    best_trade = {"symbol": sym, "date": dt, "pnl": pnl, "quantity": ev["quantity"], "price": ev["price"]}
                if worst_trade is None or pnl < worst_trade["pnl"]:
                    worst_trade = {"symbol": sym, "date": dt, "pnl": pnl, "quantity": ev["quantity"], "price": ev["price"]}
                    
                # Groupings
                stock_pnl[sym] = stock_pnl.get(sym, 0.0) + pnl
                
                sect = get_stock_sector(sym)
                sector_pnl[sect] = sector_pnl.get(sect, 0.0) + pnl
                
                monthly_pnl[mth] = monthly_pnl.get(mth, 0.0) + pnl
                yearly_pnl[yr] = yearly_pnl.get(yr, 0.0) + pnl

        # 3. Calculate Unrealized Profit for remaining holdings
        unrealized_profit = 0.0
        holdings: Dict[str, Dict[str, Any]] = {}
        
        # Get final state of holdings from the end of the timeline
        unique_syms = df_transactions["symbol"].unique() if not df_transactions.empty else []
        for sym in unique_syms:
            # Find the last timeline event for this symbol to know remaining shares and average cost
            sym_events = [e for e in timeline if e["symbol"] == sym]
            if not sym_events:
                continue
            last_ev = sym_events[-1]
            shares = last_ev["shares_held_after"]
            avg_cost = last_ev.get("average_buy_price_after", last_ev["average_cost_after"])
            
            if shares > 0:
                curr_price = get_current_price(sym)
                # Fallback to last trade price if yfinance fails
                if curr_price == 0.0:
                    curr_price = last_ev["price"]
                
                unr_pnl = (curr_price - avg_cost) * shares
                unrealized_profit += unr_pnl
                
                logger.info(f"[Math Engine] Position for {sym}: Shares={shares}, Avg Buy Price={avg_cost:.2f}, Current Price={curr_price:.2f}, Unrealized P&L={unr_pnl:.2f}")
                
                holdings[sym] = {
                    "shares": shares,
                    "average_cost": round(avg_cost, 2),
                    "current_price": round(curr_price, 2),
                    "unrealized_pnl": round(unr_pnl, 2),
                    "current_value": round(shares * curr_price, 2),
                    "total_cost": round(shares * avg_cost, 2)
                }

        net_profit = realized_profit - total_net_charges

        # Clean groupings for response (round values)
        stock_pnl_cleaned = {k: round(v, 2) for k, v in stock_pnl.items()}
        sector_pnl_cleaned = {k: round(v, 2) for k, v in sector_pnl.items()}
        monthly_pnl_cleaned = {k: round(v, 2) for k, v in sorted(monthly_pnl.items())}
        yearly_pnl_cleaned = {k: round(v, 2) for k, v in sorted(yearly_pnl.items())}

        # ── CHART-READY: charges_breakdown as array ───────────────────
        charge_map = {
            "Brokerage":         round(total_brokerage, 2),
            "STT":               round(total_stt, 2),
            "GST":               round(total_gst, 2),
            "Exchange Charges":  round(total_exchange_charges, 2),
            "SEBI Charges":      round(total_sebi_charges, 2),
            "Stamp Duty":        round(total_stamp_duty, 2),
            "DP Charges":        round(total_dp_charges, 2),
        }
        charges_breakdown_array = [
            {
                "type":          ctype,
                "charge_type":   ctype,
                "amount":        amount,
                "pct_of_total":  round((amount / total_net_charges * 100) if total_net_charges > 0 else 0.0, 2),
            }
            for ctype, amount in charge_map.items()
            if amount > 0
        ]

        # ── CHART-READY: monthly_pnl as [{month, realised_pnl, cumulative_pnl}] ──
        cumulative = 0.0
        monthly_pnl_array: List[Dict[str, Any]] = []
        for mth, mpnl in sorted(monthly_pnl_cleaned.items()):
            cumulative = round(cumulative + mpnl, 2)
            monthly_pnl_array.append({
                "month":          mth,
                "realised_pnl":   round(mpnl, 2),
                "cumulative_pnl": cumulative,
            })

        # ── CHART-READY: trading_stats ────────────────────────────────
        total_trades = winning_trades_count + losing_trades_count
        win_rate_pct = round((winning_trades_count / total_trades * 100) if total_trades > 0 else 0.0, 2)
        avg_win_pnl  = 0.0
        avg_loss_pnl = 0.0
        win_pnls  = [ev["realized_pnl"] for ev in timeline if ev["event_type"] in ("SELL", "SELL_EXCESS") and ev["realized_pnl"] > 0]
        loss_pnls = [ev["realized_pnl"] for ev in timeline if ev["event_type"] in ("SELL", "SELL_EXCESS") and ev["realized_pnl"] < 0]
        if win_pnls:
            avg_win_pnl = round(sum(win_pnls) / len(win_pnls), 2)
        if loss_pnls:
            avg_loss_pnl = round(sum(loss_pnls) / len(loss_pnls), 2)
        charge_leakage_pct = round((total_net_charges / realized_profit * 100) if realized_profit > 0 else 0.0, 2)

        trading_stats = {
            "win_rate_pct":        win_rate_pct,
            "avg_win_pnl":         avg_win_pnl,
            "avg_loss_pnl":        avg_loss_pnl,
            "charge_leakage_pct":  charge_leakage_pct,
            "total_trades":        total_trades,
        }

        # ── CHART-READY: realised_trades list with return_pct & per-trade charges ──
        realised_trades_list: List[Dict[str, Any]] = []
        for ev in timeline:
            if ev["event_type"] not in ("SELL", "SELL_EXCESS"):
                continue
            sym       = ev["symbol"]
            qty       = ev["quantity"]
            sell_price = ev["price"]
            gross_pnl  = ev["realized_pnl"]

            buy_price = ev.get("buy_price", 0.0)
            if buy_price == 0.0 and qty > 0:
                buy_price = round(sell_price - (gross_pnl / qty), 2)
            buy_price = max(buy_price, 0.01)  # guard against zero division

            sell_charges = calculate_charges("SELL", qty, sell_price)
            buy_charges  = calculate_charges("BUY",  qty, buy_price)
            total_trade_charges = round(sell_charges["net_charges"] + buy_charges["net_charges"], 2)
            net_pnl      = round(gross_pnl - total_trade_charges, 2)

            cost_total       = round(qty * buy_price, 2)
            return_pct       = round((net_pnl / cost_total * 100) if cost_total > 0 else 0.0, 2)
            gross_return_pct = round((gross_pnl / cost_total * 100) if cost_total > 0 else 0.0, 2)

            # Determine buy_date of matched first buy
            sym_buy_events = [e for e in timeline if e["symbol"] == sym and e["event_type"] == "BUY"]
            buy_date = sym_buy_events[0]["date"] if sym_buy_events else ev["date"]

            scrip_name = sym_to_name.get(sym, sym)

            realised_trades_list.append({
                "scrip_name":       scrip_name,
                "symbol":           sym,
                "date":             ev["date"],
                "buy_date":         buy_date,
                "sell_date":        ev["date"],
                "qty":              qty,
                "quantity":         qty,
                "buy_price":        round(buy_price, 2),
                "sell_price":       round(sell_price, 2),
                "buy_value":        round(qty * buy_price, 2),
                "sell_value":       round(qty * sell_price, 2),
                "net_pnl":          net_pnl,
                "gross_pnl":        round(gross_pnl, 2),
                "return_pct":       return_pct,
                "gross_return_pct": gross_return_pct,
                "trade_charges": {
                    "brokerage":        round(sell_charges["brokerage"] + buy_charges["brokerage"], 2),
                    "stt":              round(sell_charges["stt"] + buy_charges["stt"], 2),
                    "gst":              round(sell_charges["gst"] + buy_charges["gst"], 2),
                    "exchange_charges": round(sell_charges["exchange_charges"] + buy_charges["exchange_charges"], 2),
                    "stamp":            round(buy_charges["stamp_duty"], 2),
                    "dp_charges":       round(sell_charges["dp_charges"], 2),
                    "total":            total_trade_charges,
                },
            })
        realised_trades_list.sort(key=lambda x: x["net_pnl"], reverse=True)

        # ── CHART-READY: open_positions list with return_pct & holding days ──
        open_positions_list: List[Dict[str, Any]] = []
        today = datetime.now()
        for sym, h in holdings.items():
            sym_buy_events = [e for e in timeline if e["symbol"] == sym and e["event_type"] == "BUY"]
            first_buy = sym_buy_events[0]["date"] if sym_buy_events else ""
            try:
                days_held = (today - datetime.strptime(first_buy, "%Y-%m-%d")).days if first_buy else 0
            except Exception:
                days_held = 0
            
            scrip_name = sym_to_name.get(sym, sym)
            open_positions_list.append({
                "scrip_name":     scrip_name,
                "symbol":         sym,
                "qty":            h["shares"],
                "avg_cost":       h["average_cost"],
                "cmp":            h["current_price"],
                "total_invested": h["total_cost"],
                "unrealised_pnl": h["unrealized_pnl"],
                "days_held":      days_held,
                "first_buy_date": first_buy,
                "return_pct":     round((h["unrealized_pnl"] / h["total_cost"] * 100) if h["total_cost"] > 0 else 0.0, 2)
            })

        # ── CHART-READY: portfolio_summary ────────────────────────────
        total_open_invested = sum(h["total_cost"] for h in holdings.values())
        total_open_current = sum(h["current_value"] for h in holdings.values())
        portfolio_summary = {
            "total_invested":      round(total_open_invested, 2),
            "total_realised_pnl":  round(realized_profit, 2),
            "total_current_value": round(total_open_current, 2),
            "total_charges":       round(total_net_charges, 2)
        }

        return {
            "realized_profit":   round(realized_profit, 2),
            "unrealized_profit": round(unrealized_profit, 2),
            "charges": {
                "brokerage":        round(total_brokerage, 2),
                "stt":              round(total_stt, 2),
                "gst":              round(total_gst, 2),
                "exchange_charges": round(total_exchange_charges, 2),
                "sebi_charges":     round(total_sebi_charges, 2),
                "stamp_duty":       round(total_stamp_duty, 2),
                "dp_charges":       round(total_dp_charges, 2),
                "net_charges":      round(total_net_charges, 2),
            },
            "net_profit":      round(net_profit, 2),
            "winning_trades":  winning_trades_count,
            "losing_trades":   losing_trades_count,
            "best_trade":      best_trade,
            "worst_trade":     worst_trade,
            "sector_wise_profit": sector_pnl_cleaned,
            "stock_wise_profit":  stock_pnl_cleaned,
            "monthly_profit":     monthly_pnl_cleaned,
            "yearly_profit":      yearly_pnl_cleaned,
            "holdings":           holdings,
            # ── Chart-ready fields ────────────────────────────────────
            "portfolio_summary":  portfolio_summary,
            "open_positions":     open_positions_list,
            "charges_breakdown":  charges_breakdown_array,   # [{type, amount, pct_of_total}]
            "monthly_pnl":        monthly_pnl_array,         # [{month, realised_pnl, cumulative_pnl}]
            "trading_stats":      trading_stats,             # {win_rate_pct, avg_win_pnl, avg_loss_pnl, charge_leakage_pct}
            "realised_trades":    realised_trades_list,      # [{symbol, date, return_pct, trade_charges{...}}]
            "charts_metadata": {
                "sector_wise_profit": [{"sector": k, "profit": v} for k, v in sector_pnl_cleaned.items()],
                "stock_wise_profit":  [{"symbol": k, "profit": v} for k, v in stock_pnl_cleaned.items()],
                "monthly_profit":     [{"month": k, "profit": v} for k, v in monthly_pnl_cleaned.items()],
                "yearly_profit":      [{"year": k, "profit": v} for k, v in yearly_pnl_cleaned.items()],
            },
        }
