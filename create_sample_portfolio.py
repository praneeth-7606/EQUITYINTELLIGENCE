import os
import pandas as pd

def create_sample_excel():
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(PROJECT_ROOT, "sample_portfolio.xlsx")
    
    # Real-world-like stock transaction data
    data = {
        "Trade Date": [
            "2024-01-15",
            "2024-02-10",
            "2024-03-05",
            "2024-05-20",
            "2024-08-12",
            "2024-11-05",
            "2024-12-10",
            "2025-02-18",
            "2025-04-10",
            "2025-05-15",
        ],
        "Stock Symbol": [
            "RELIANCE",
            "TCS",
            "INFY",
            "RELIANCE",
            "TCS",
            "RELIANCE",
            "INFY",
            "INFY",
            "RELIANCE",
            "TCS",
        ],
        "Stock Name": [
            "Reliance Industries Ltd.",
            "Tata Consultancy Services Ltd.",
            "Infosys Ltd.",
            "Reliance Industries Ltd.",
            "Tata Consultancy Services Ltd.",
            "Reliance Industries Ltd.",
            "Infosys Ltd.",
            "Infosys Ltd.",
            "Reliance Industries Ltd.",
            "Tata Consultancy Services Ltd.",
        ],
        "Action": [
            "BUY",
            "BUY",
            "BUY",
            "SELL",
            "BUY",
            "BUY",
            "SELL",
            "BUY",
            "SELL",
            "SELL",
        ],
        "Quantity": [10, 5, 20, 5, 5, 8, 10, 15, 6, 4],
        "Price": [
            2450.00,
            3800.00,
            1600.00,
            2700.00,
            3950.00,
            2520.00,
            1850.00,
            1720.00,
            2850.00,
            4200.00,
        ],
        "Brokerage": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "GST": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "STT": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "Exchange": [
            "NSE",
            "NSE",
            "NSE",
            "NSE",
            "NSE",
            "NSE",
            "NSE",
            "NSE",
            "NSE",
            "NSE",
        ],
    }

    df = pd.DataFrame(data)
    df.to_excel(file_path, index=False, sheet_name="Trades")
    print(f"Sample portfolio Excel sheet created successfully at: {file_path}")

if __name__ == "__main__":
    create_sample_excel()
