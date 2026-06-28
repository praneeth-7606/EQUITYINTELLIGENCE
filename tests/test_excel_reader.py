import os
import pytest
import pandas as pd
from unittest.mock import patch
from app.tools.excel_reader import read_and_normalize_excel

@pytest.fixture
def temp_excel_dir(tmp_path):
    return tmp_path

def test_standard_transaction_rows(temp_excel_dir):
    """
    Test standard Excel file with separate row-by-row transaction records.
    """
    file_path = os.path.join(temp_excel_dir, "trades_standard.xlsx")
    
    # Create fake data
    data = {
        "Trade Date": ["2026-01-10", "2026-01-15"],
        "Ticker": ["INFY", "INFY"],
        "Buy/Sell": ["Buy", "Sell"],
        "Qty": [10, 5],
        "Execution Price": [1500.0, 1550.0],
        "Brokerage charges": [10.0, 12.0],
        "GST": [1.8, 2.16],
        "STT": [15.0, 15.5]
    }
    df = pd.DataFrame(data)
    df.to_excel(file_path, index=False, sheet_name="Trades")
    
    mock_plan = {
        "layout_type": "standard_row",
        "mappings": {
            "date": "Trade Date",
            "symbol": "Ticker",
            "action": "Buy/Sell",
            "quantity": "Qty",
            "price": "Execution Price",
            "brokerage": "Brokerage charges",
            "gst": "GST",
            "stt": "STT"
        },
        "action_values_map": {"Buy": "BUY", "Sell": "SELL"}
    }
    
    # Read & normalize
    with patch("app.tools.excel_reader.generate_mapping_plan", return_value=mock_plan):
        df_norm = read_and_normalize_excel(file_path)
    
    assert len(df_norm) == 2
    assert list(df_norm.columns) == [
        "date", "symbol", "stock_name", "action", "quantity", "price", 
        "brokerage", "gst", "stt", "exchange_charges", "sebi_charges", "stamp_duty", "other_charges", "exchange"
    ]
    assert df_norm.iloc[0]["symbol"] == "INFY"
    assert df_norm.iloc[0]["action"] == "BUY"
    assert df_norm.iloc[1]["action"] == "SELL"
    assert df_norm.iloc[0]["quantity"] == 10.0
    assert df_norm.iloc[1]["price"] == 1550.0

def test_matched_buy_sell_rows(temp_excel_dir):
    """
    Test matched row layout where buy and sell parameters are in the same row.
    """
    file_path = os.path.join(temp_excel_dir, "trades_matched.xlsx")
    
    # Create fake data with matched BUY and SELL in one row
    data = {
        "Symbol": ["TCS"],
        "Buy Date": ["2026-02-01"],
        "Buy Price": [3200.0],
        "Qty": [20],
        "Sell Date": ["2026-02-15"],
        "Sell Price": [3400.0],
        "Brokerage": [5.0]
    }
    df = pd.DataFrame(data)
    df.to_excel(file_path, index=False, sheet_name="Holdings")
    
    mock_plan = {
        "layout_type": "matched_row",
        "mappings": {
            "symbol": "Symbol",
            "buy_date": "Buy Date",
            "buy_price": "Buy Price",
            "quantity": "Qty",
            "sell_date": "Sell Date",
            "sell_price": "Sell Price",
            "brokerage": "Brokerage"
        },
        "action_values_map": {}
    }
    
    # Read & normalize
    with patch("app.tools.excel_reader.generate_mapping_plan", return_value=mock_plan):
        df_norm = read_and_normalize_excel(file_path)
    
    # It should split into 2 transactions: BUY and SELL
    assert len(df_norm) == 2
    assert df_norm.iloc[0]["action"] == "BUY"
    assert df_norm.iloc[0]["date"].strftime("%Y-%m-%d") == "2026-02-01"
    assert df_norm.iloc[0]["price"] == 3200.0
    
    assert df_norm.iloc[1]["action"] == "SELL"
    assert df_norm.iloc[1]["date"].strftime("%Y-%m-%d") == "2026-02-15"
    assert df_norm.iloc[1]["price"] == 3400.0
    assert df_norm.iloc[0]["quantity"] == 20
    assert df_norm.iloc[1]["quantity"] == 20

def test_broker_excel_columns(temp_excel_dir):
    """
    Test regression on broker Excel output containing 'Buy Qty', 'Sell Qty',
    'Net Qty', 'MarketRate', and 'ScripName' columns.
    """
    file_path = os.path.join(temp_excel_dir, "broker_sheet.xlsx")
    
    data = {
        "Client Code": ["C100"],
        "Client Name": ["User"],
        "exchange": ["NSE"],
        "date": ["2026-06-25"],
        "ScripName": ["Reliance Industries Ltd."],
        "symbol": ["RELIANCE"],
        "action": ["Buy"],
        "Buy Qty": [10.0],
        "Sell Qty": [0.0],
        "Net Qty": [10.0],
        "MarketRate": [2450.00],
        "brokerage": [0.0],
        "gst": [0.0],
        "stt": [0.0]
    }
    df = pd.DataFrame(data)
    df.to_excel(file_path, index=False)
    
    mock_plan = {
        "layout_type": "split_qty_row",
        "mappings": {
            "exchange": "exchange",
            "date": "date",
            "stock_name": "ScripName",
            "symbol": "symbol",
            "buy_qty": "Buy Qty",
            "sell_qty": "Sell Qty",
            "net_qty": "Net Qty",
            "price": "MarketRate",
            "brokerage": "brokerage",
            "gst": "gst",
            "stt": "stt"
        },
        "action_values_map": {"Buy": "BUY"}
    }
    
    with patch("app.tools.excel_reader.generate_mapping_plan", return_value=mock_plan):
        df_norm = read_and_normalize_excel(file_path)
    
    assert len(df_norm) == 1
    assert df_norm.iloc[0]["quantity"] == 10.0
    assert df_norm.iloc[0]["price"] == 2450.00
    assert df_norm.iloc[0]["stock_name"] == "Reliance Industries Ltd."
    assert df_norm.iloc[0]["action"] == "BUY"
