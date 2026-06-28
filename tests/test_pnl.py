import pandas as pd
from unittest.mock import patch
from app.tools.pnl_calculator import PnlCalculatorTool

def test_pnl_calculations():
    # Buy 10 shares of RELIANCE @ 2000 (total cost 20000 + charges)
    # Sell 5 shares of RELIANCE @ 2200 (revenue 11000 - charges)
    # Remaining 5 shares held
    
    txs = [
        {"date": pd.to_datetime("2026-01-01"), "symbol": "RELIANCE", "stock_name": "RELIANCE", "action": "BUY", "quantity": 10.0, "price": 2000.0, "brokerage": 0.0, "gst": 0.0, "stt": 0.0, "exchange": "NSE"},
        {"date": pd.to_datetime("2026-01-10"), "symbol": "RELIANCE", "stock_name": "RELIANCE", "action": "SELL", "quantity": 5.0, "price": 2200.0, "brokerage": 0.0, "gst": 0.0, "stt": 0.0, "exchange": "NSE"},
    ]
    df_tx = pd.DataFrame(txs)
    
    timeline = [
        {"date": "2026-01-01", "symbol": "RELIANCE", "event_type": "BUY", "quantity": 10.0, "price": 2000.0, "charges": 0.0, "shares_held_after": 10.0, "average_cost_after": 2000.0, "realized_pnl": 0.0, "description": ""},
        {"date": "2026-01-10", "symbol": "RELIANCE", "event_type": "SELL", "quantity": 5.0, "price": 2200.0, "charges": 0.0, "shares_held_after": 5.0, "average_cost_after": 2000.0, "realized_pnl": 1000.0, "description": ""}
    ]
    
    # Mock get_current_price and get_stock_sector
    with patch("app.tools.pnl_calculator.get_current_price", return_value=2500.0), \
         patch("app.tools.pnl_calculator.get_stock_sector", return_value="Energy"):
        results = PnlCalculatorTool.calculate(df_tx, timeline)
        
    # Check results
    assert results["realized_profit"] == 1000.0
    # Unrealized profit: (2500 - 2000) * 5 = 2500
    assert results["unrealized_profit"] == 2500.0
    assert results["winning_trades"] == 1
    assert results["losing_trades"] == 0
    assert results["stock_wise_profit"]["RELIANCE"] == 1000.0
    assert results["sector_wise_profit"]["Energy"] == 1000.0
    assert results["monthly_profit"]["2026-01"] == 1000.0
    
    # Check that charges exist and are structured
    assert "charges" in results
    assert results["charges"]["net_charges"] > 0
    assert results["net_profit"] == 1000.0 - results["charges"]["net_charges"]
