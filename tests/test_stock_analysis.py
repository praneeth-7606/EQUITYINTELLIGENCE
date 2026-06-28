import pytest
from app.state import State
from app.agents.stock_analysis_agent import stock_analysis_agent_node

def test_stock_analysis_agent_basic():
    """
    Test stock_analysis_agent_node with a mock query for ITC in 2024.
    """
    state: State = {
        "uploaded_file": None,
        "portfolio_dataframe": None,
        "holding_timeline": None,
        "selected_agent": "stock_analysis_agent",
        "messages": ["Analyze ITC for 2024"],
        "result": None,
        "errors": []
    }

    new_state = stock_analysis_agent_node(state)
    
    assert not new_state["errors"], f"Encountered errors: {new_state['errors']}"
    assert new_state["result"] is not None
    res = new_state["result"]
    assert "structured_data" in res
    
    sd = res["structured_data"]
    assert sd["ticker"] == "ITC.NS"
    assert "fundamentals" in sd
    assert "2024" in sd["years"]
    
    year_data = sd["years"]["2024"]
    assert "price_metrics" in year_data
    assert "ohlcv_chart_data" in year_data
    assert "monthly_metrics" in year_data
    
    pm = year_data["price_metrics"]
    assert pm["year_open"] > 0
    assert pm["year_close"] > 0
    assert pm["high"] >= pm["low"]
    
    # Check that monthly metrics have records
    assert len(year_data["monthly_metrics"]) > 0
    assert year_data["monthly_metrics"][0]["month"] in ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
