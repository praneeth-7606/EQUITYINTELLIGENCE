# Stock Intelligence Platform

A production-grade AI-powered stock portfolio analytics and dividend intelligence platform. It parses transactions from uploaded Excel sheets, builds chronological holding ledgers, performs deterministic financial calculations, fetches corporate action data, and provides deep insights using xAI's Grok with a seamless Google Gemini 2.5 Flash failover fallback.

---

## Technical Features

- **Multi-Agent LangGraph Workflow**: Led by a Supervisor node that orchestrates tasks between specialized agents:
  - **Portfolio Agent**: Analyzes holdings summaries, investment durations, and concentration profiles.
  - **P&L Agent**: Runs deterministic Python code to calculate realized/unrealized profit/loss, winning/losing trades, and aggregates results.
  - **Dividend Agent**: Resolves stock symbols, fetches historical dividends via Yahoo Finance, checks eligibility, and calculates upcoming and missed payouts.
- **Fail-safe LLM Factory**: Primary routing and generation are handled by **Grok (xAI)**, with automated, invocation-level failover to **Gemini 2.5 Flash** if Grok rate limits, times out, or errors.
- **Tax and Fee Calculator**: Auto-calculates STT, GST, SEBI charges, Stamp Duty, Exchange charges, and DP charges using standard Indian delivery transaction rules.
- **Local Cache**: Caches stock sectors, prices, and dividend histories locally to optimize speed and avoid API rate limits.
- **Modern Standards**: Developed with Python 3.12, fully type-hinted, formatted with Black/Ruff, and packaged with `uv`.

---

## Project Structure

```
stock-intelligence/
├── pyproject.toml         # Dependency declarations
├── .env                  # API keys and config (create from template)
├── main.py               # Launcher entrypoint
├── create_sample_portfolio.py  # Script to generate sample spreadsheet
├── app/
│   ├── config.py         # Configuration loader via pydantic-settings
│   ├── models.py         # FastAPI schemas
│   ├── state.py          # LangGraph state TypedDict
│   ├── llm.py            # Reusable LLM Factory with with_fallbacks()
│   ├── router.py         # API router /upload, /agent/*, /chat
│   ├── main.py           # FastAPI app instance
│   ├── agents/
│   │   ├── supervisor.py       # Supervisor routing agent
│   │   ├── portfolio_agent.py  # Portfolio report agent
│   │   ├── pnl_agent.py        # Profit/loss report agent
│   │   ├── dividend_agent.py   # Dividend tracker agent
│   │   └── graph.py            # LangGraph workflow compilation
│   └── tools/
│       ├── excel_reader.py     # Excel scanner and normalizer
│       ├── corporate_actions.py # yfinance splits and dividends scraper
│       ├── holding_timeline.py # Chronological ledger builder
│       ├── pnl_calculator.py   # Deterministic P&L math engine
│       ├── dividend_fetcher.py # Dividend tool wrapper
│       ├── eligibility_checker.py # Eligibility and payout validator
│       └── registry.py         # LangChain tool interfaces
└── tests/                # Unit & integration tests
```

---

## Getting Started

### 1. Installation
Install the project dependencies and set up the virtual environment:
```bash
# Sync environment
uv sync
```

### 2. Configuration
Copy the `.env` template and set your API keys:
```bash
# Edit .env and input your keys
XAI_API_KEY=your_xai_key
GEMINI_API_KEY=your_gemini_key
```

### 3. Generate Sample Portfolio
Generate a sample Excel sheet with mock transactions to test the system:
```bash
uv run create_sample_portfolio.py
```
This creates `sample_portfolio.xlsx` in the project root.

### 4. Run the Server
Launch the FastAPI server:
```bash
uv run main.py
```
The server will start at `http://localhost:8000`. You can access the interactive API docs at `http://localhost:8000/docs`.

---

## API Documentation

### 1. Upload Portfolio
- **Endpoint**: `POST /api/v1/upload`
- **Payload**: Form-data containing `file: sample_portfolio.xlsx`
- **Response**: Standardized verification response showing recognized columns, symbols, and transactions.

### 2. Direct Agent Endpoints
Execute report pipelines directly on the last uploaded file:
- **POST `/api/v1/agent/portfolio`**: Triggers portfolio summary.
- **POST `/api/v1/agent/pnl`**: Triggers profit/loss, charges breakdown, and performance charts metadata.
- **POST `/api/v1/agent/dividend`**: Triggers eligibility checker, company-wise dividends, upcoming dividend projections, and missed payouts.

### 3. Chat Endpoint
- **Endpoint**: `POST /api/v1/chat`
- **Payload**:
  ```json
  {
    "message": "How much total profit did I make?"
  }
  ```
- **Routing**: The Supervisor agent automatically detects the query intent and forwards it to the P&L agent to generate the calculation and response.

### 4. Standard Response Format
All `/agent/*` and `/chat` endpoints return a consistent structured JSON:
```json
{
  "success": true,
  "execution_time": 0.3541,
  "agent_used": "pnl_agent",
  "summary": "Your realized profit is 1,200.00 with net charges of 85.34...",
  "insights": [
    "Winning trades percentage is 75%.",
    "RELIANCE represents the largest source of profit."
  ],
  "structured_data": {
    "realized_profit": 1200.00,
    "net_profit": 1114.66,
    "winning_trades": 3,
    "losing_trades": 1,
    "best_trade": { ... },
    "charts_metadata": { ... }
  }
}
```

---

## Running Tests

Verify the calculations and excel normalization:
```bash
uv run pytest
```
