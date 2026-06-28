import pandas as pd
from unittest.mock import patch
from app.tools.holding_timeline import HoldingTimelineTool

def test_holding_timeline_basic():
    """
    Tests basic BUY and SELL flow.
    - Buy 10 shares @ 100 (charges = 5.0) => avg_cost = 10.5
    - Sell 5 shares @ 120 (charges = 3.0) => realized_pnl = 5 * 120 - 3 - 5 * 10.5 = 600 - 3 - 525 = 72
    """
    txs = [
        {"date": pd.to_datetime("2026-01-01"), "symbol": "TCS", "stock_name": "TCS", "action": "BUY", "quantity": 10.0, "price": 100.0, "brokerage": 2.0, "gst": 1.0, "stt": 2.0, "exchange": "NSE"},
        {"date": pd.to_datetime("2026-01-05"), "symbol": "TCS", "stock_name": "TCS", "action": "SELL", "quantity": 5.0, "price": 120.0, "brokerage": 1.0, "gst": 1.0, "stt": 1.0, "exchange": "NSE"},
    ]
    df_tx = pd.DataFrame(txs)
    
    # Mock CorporateActionsTool.get_splits_and_bonuses to return empty
    with patch("app.tools.holding_timeline.CorporateActionsTool.get_splits_and_bonuses", return_value=[]):
        timeline = HoldingTimelineTool.generate_timeline(df_tx)
        
    assert len(timeline) == 2
    
    # Check Buy Event
    buy_ev = timeline[0]
    assert buy_ev["event_type"] == "BUY"
    assert buy_ev["shares_held_after"] == 10.0
    assert buy_ev["average_cost_after"] == 100.5  # (1000 + 5) / 10 = 100.5
    
    # Check Sell Event
    sell_ev = timeline[1]
    assert sell_ev["event_type"] == "SELL"
    assert sell_ev["shares_held_after"] == 5.0
    assert sell_ev["average_cost_after"] == 100.5  # average cost remains same
    # realized_pnl (gross) = 5 * (120 - 100) = 100.0
    assert sell_ev["realized_pnl"] == 100.0
    # realized_pnl_net = (5 * 120 - 3) - (5 * 100.5) = 597 - 502.5 = 94.5
    assert sell_ev["realized_pnl_net"] == 94.5

def test_holding_timeline_split():
    """
    Tests splits.
    - Buy 10 shares @ 100 (charges = 0)
    - Split 2:1 on 2026-01-03
    - Verify shares = 20, average cost = 50
    """
    txs = [
        {"date": pd.to_datetime("2026-01-01"), "symbol": "AAPL", "stock_name": "AAPL", "action": "BUY", "quantity": 10.0, "price": 100.0, "brokerage": 0.0, "gst": 0.0, "stt": 0.0, "exchange": "NASDAQ"},
    ]
    df_tx = pd.DataFrame(txs)
    
    mock_split = [
        {"date": "2026-01-03", "ratio": 2.0, "type": "SPLIT", "description": "Stock Split 2:1"}
    ]
    
    with patch("app.tools.holding_timeline.CorporateActionsTool.get_splits_and_bonuses", return_value=mock_split):
        timeline = HoldingTimelineTool.generate_timeline(df_tx)
        
    assert len(timeline) == 2
    
    # Split Event
    split_ev = timeline[1]
    assert split_ev["event_type"] == "SPLIT"
    assert split_ev["shares_held_after"] == 20.0
    assert split_ev["average_cost_after"] == 50.0
