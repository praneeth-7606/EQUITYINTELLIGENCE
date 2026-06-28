# Equity Intelligence

Equity Intelligence is a full-stack, AI-assisted platform for Indian equity portfolio analytics and public-stock research. It validates Excel transaction statements, builds chronological holdings, calculates P&L and charges deterministically, tracks dividends, and provides cited market research through a multi-agent workflow.

The backend uses FastAPI, LangGraph, MongoDB, and a resilient LLM provider chain. The frontend is a React and TypeScript dashboard with authenticated projects, file-specific chat sessions, portfolio visualizations, and an observability workspace for developers.

## Demo

[Watch the Equity Intelligence demo](https://drive.google.com/file/d/1ewYySuQ2O5yPHXtSdWMXKZCzMm9uJR0s/view?usp=drive_link)

## Features

- **Portfolio Agent** summarizes holdings, investment duration, diversification, and concentration.
- **P&L Agent** calculates realized and unrealized P&L, open positions, trade outcomes, and Indian delivery charges with deterministic Python logic.
- **Dividend Agent** resolves NSE symbols, retrieves corporate actions, checks holding-date eligibility, and estimates received, missed, and upcoming payouts.
- **Stock Analysis Agent** handles public-company questions without requiring a portfolio upload. It supports historical price and monthly performance, volatility, drawdown, fundamentals, corporate actions, full dividend history, and year-specific narrative analysis.
- **Supervisor routing** selects the appropriate specialist from natural-language requests.
- **Provider failover** tries Mistral first, then Grok or Groq, and finally Gemini. Providers without configured keys are skipped, and structured-output calls have a JSON fallback path.
- **Market-data fallbacks** use Yahoo Finance for prices, company data, and corporate actions; NSE-aware symbol resolution and keyless web research supplement missing or factual public-company data.
- **Privacy masking** redacts emails, PANs, account and demat identifiers, client metadata, filenames, and asset names where appropriate before sensitive samples or portfolio prompts reach an LLM. Public web searches contain only public-company questions, never portfolio data.
- **Multi-file projects** retain every uploaded workbook as a separate file and chat session under a project, so users can revisit and analyze multiple statements without overwriting earlier uploads.
- **Authentication and persistence** provide JWT access/refresh tokens, user profiles, projects, sessions, chat history, reports, and transaction snapshots backed by MongoDB.
- **Developer dashboard** exposes live and historical traces, workflow steps, tool and database calls, LLM usage, errors, latency, token/cost analytics, and daily trends at `/developer`.
- **Modern UI** includes portfolio, P&L, dividend, stock-analysis, raw-data, and ReAct activity views.

## LLM and data fallback order

The application attempts configured LLM providers in this order:

1. Mistral (`MISTRAL_API_KEY`)
2. Grok (`XAI_API_KEY`) or Groq when the supplied key begins with `gsk_`
3. Gemini (`GEMINI_API_KEY`)

At least one provider key is required for AI-generated narratives. Core spreadsheet normalization, holding timelines, P&L, fees, and other deterministic calculations do not depend on an LLM.

Stock research primarily uses Yahoo Finance. The Stock Analysis Agent also performs NSE-aware ticker resolution and can use a DuckDuckGo HTML search fallback for public facts or when normal market metadata is incomplete. Network-sourced financial information can be delayed or unavailable and should not be treated as investment advice.

## Privacy model

The privacy layer masks common personal and brokerage identifiers in logs, validation errors, spreadsheet samples, and LLM-bound text. Portfolio asset symbols can be replaced with aliases during narrative generation and restored in the response. Uploaded workbooks are stored in the local `data/` directory using user/file-specific names, while metadata and chat history are stored in MongoDB.

This is application-level masking, not a substitute for infrastructure controls. For production use, secure MongoDB and the host filesystem, restrict CORS, use TLS, rotate provider keys, set a strong `JWT_SECRET`, and define an appropriate data-retention policy.

## Project structure

```text
.
├── app/
│   ├── agents/             # Supervisor and specialist LangGraph agents
│   ├── auth/               # JWT authentication and profile endpoints
│   ├── observability/      # Tracing middleware, persistence, and APIs
│   ├── tools/              # Excel, timeline, P&L, dividend, and web tools
│   ├── llm.py              # Mistral → Grok/Groq → Gemini provider chain
│   ├── privacy.py          # Masking and asset-alias helpers
│   ├── router.py           # Portfolio, project, session, and chat APIs
│   └── main.py             # FastAPI application
├── frontend/               # React, TypeScript, Vite, and MUI application
├── tests/                  # Backend unit tests
├── .env.example            # Configuration template
├── main.py                 # Backend launcher
└── pyproject.toml          # Python dependencies and tooling
```

## Prerequisites

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)
- Node.js and npm
- MongoDB
- At least one supported LLM API key

## Setup

1. Install backend dependencies:

   ```bash
   uv sync
   ```

2. Copy `.env.example` to `.env` and configure MongoDB, a strong JWT secret, and one or more LLM keys:

   ```dotenv
   MISTRAL_API_KEY=your-mistral-api-key
   MONGODB_URI=mongodb://localhost:27017
   JWT_SECRET=replace-with-a-long-random-secret
   ```

3. Install frontend dependencies:

   ```bash
   cd frontend
   npm install
   ```

## Run locally

Start MongoDB, then launch the API from the repository root:

```bash
uv run main.py
```

The API is available at `http://localhost:8000`; OpenAPI documentation is at `http://localhost:8000/docs`.

In another terminal, start the frontend:

```bash
cd frontend
npm run dev
```

Vite prints the frontend URL, normally `http://localhost:5173`.

To create a sample transaction workbook:

```bash
uv run create_sample_portfolio.py
```

## Typical workflow

1. Register or sign in.
2. Create or select a project.
3. Upload one or more `.xlsx` or `.xls` transaction statements. Each upload is validated, normalized, stored independently, and assigned its own chat session.
4. Review or adjust column mappings when a broker uses non-standard headings.
5. Run a portfolio, P&L, or dividend report, or ask a natural-language question.
6. Ask a public-stock question such as “Analyze TCS for 2025” without uploading a workbook.
7. Inspect execution details and operational analytics in the Developer Dashboard.

## Main API endpoints

All application endpoints use the `/api/v1` prefix. Protected routes require a bearer access token.

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/register`, `/login`, `/refresh`, `/logout` | Authentication |
| `GET`, `PUT` | `/me` | Read or update the user profile |
| `POST` | `/upload` | Upload and validate one Excel workbook; optionally associate it with a project |
| `POST`, `GET` | `/projects` | Create or list projects |
| `GET` | `/projects/{project_id}` | Get a project and all of its uploaded files/sessions |
| `GET` | `/user/sessions` | List a user's file-specific chat sessions |
| `GET` | `/chat/history/{session_id}` | Load persisted conversation history |
| `POST` | `/agent/portfolio` | Run portfolio analysis |
| `POST` | `/agent/pnl` | Run deterministic P&L and charge analysis |
| `POST` | `/agent/dividend` | Run portfolio dividend analysis |
| `POST` | `/agent/stock_analysis` | Analyze a named public stock |
| `POST` | `/chat` | Route a request through the supervisor |
| `GET` | `/obs/traces`, `/obs/live` | Query historical or active traces |
| `GET` | `/obs/analytics/*` | Query agent, tool, LLM, error, cost, and performance analytics |

See the generated OpenAPI documentation for complete request and response schemas.

## Tests and checks

Run backend tests:

```bash
uv run pytest
```

Run frontend checks:

```bash
cd frontend
npm run lint
npm run build
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).

## Disclaimer

Equity Intelligence is an analytics and educational tool. Its output may be incomplete, delayed, or incorrect and is not financial, tax, or investment advice.
