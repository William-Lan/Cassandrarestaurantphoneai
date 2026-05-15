# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this app does

Cassandra is a restaurant inventory management app with AI-powered reordering. Key capabilities:
- Track stock levels and log transactions (purchase, usage, waste, adjustment)
- Import historical purchase data from any supplier format (CSV, Excel, PDF, images) — Claude AI extracts and normalizes the data
- AI reorder suggestions using Claude, which analyzes stock, 30-day usage, purchase history, and per-item rules
- Purchase order workflow: pending → approved → ordered → received (receiving auto-updates stock)
- Menu items linked to inventory ingredients for usage tracking
- PWA: installable on iPhone via Safari → Add to Home Screen

## Running locally

```bash
./start.sh          # installs deps, starts both servers
```

Or individually:

```bash
# Backend (from backend/)
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add ANTHROPIC_API_KEY
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend (from frontend/)
npm install
npm run dev            # http://localhost:5173
```

API docs at `http://localhost:8000/api/docs` (FastAPI Swagger UI).

## Architecture

**Single-origin production, proxied dev.** In production (Docker/Railway), FastAPI serves the built React app as static files alongside the API — everything on one URL. In development, Vite runs on `:5173` and proxies `/api/*` requests to the FastAPI backend on `:8000`. The proxy does **not** strip the `/api` prefix; all FastAPI routers are mounted under `/api`.

**Backend** — `backend/app/`
- `main.py` — FastAPI app, mounts all routers under `/api`, serves `frontend/dist/` as static files when it exists
- `models.py` — all SQLAlchemy models (single file)
- `schemas.py` — all Pydantic request/response schemas (single file)
- `database.py` — SQLAlchemy engine setup; handles both SQLite (dev) and PostgreSQL (prod, auto-converts `postgres://` → `postgresql://`)
- `routers/` — one file per resource (`inventory`, `menu`, `suppliers`, `orders`, `imports`, `ai`, `preferences`)
- `services/ai_service.py` — all Claude API calls (three functions: reorder suggestions, file parsing, inventory matching)

**Frontend** — `frontend/src/`
- `api/inventory.js` — every API call in one file, using an Axios client with `baseURL: '/api'`
- `App.jsx` — router with sidebar nav; `AlertsBanner` polls `/api/inventory/alerts` every 60s
- Pages are self-contained with their own modal state and data fetching — no global state manager

**Database schema key relationships:**
- `InventoryItem` is the central table — linked to `Supplier`, `InventoryTransaction` (all stock changes), `MenuItemIngredient` (ingredient usage per dish), `ReorderRule` (one-to-one), and `PurchaseOrderItem`
- `InventoryTransaction.quantity_change` is signed: positive = stock in, negative = stock out
- Stock is updated in two places: `POST /api/inventory/transactions/` (adjusts `current_stock` immediately) and `PATCH /api/orders/{id}/status` when status becomes `received`
- `ReorderRule.rule_type` is `ai_driven | manual_threshold | hybrid` — the AI prompt in `ai_service.py` respects these when building suggestions

**AI import pipeline** (`routers/imports.py` + `services/ai_service.py`):
1. `POST /api/import/upload` — sends file bytes to `parse_file_for_purchases()` (Claude reads PDF/image via base64 or CSV/text as text), then `match_items_to_inventory()` (Claude fuzzy-matches extracted names to existing inventory IDs)
2. `POST /api/import/confirm` — writes `InventoryTransaction` rows with `type=historical_import`, optionally creates new `InventoryItem` rows for unmatched products, updates `current_stock`

## Environment variables

```
ANTHROPIC_API_KEY   # required for AI features
DATABASE_URL        # defaults to sqlite:///./inventory.db; set to postgres:// for production
FRONTEND_DIST       # path to built React app; defaults to ../frontend/dist relative to backend/app/
```

## Deployment

Docker multi-stage build: Node builds the React app, Python image copies `frontend/dist/` and serves it.

```bash
docker build -t cassandra .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=... cassandra
```

On Railway: connect GitHub repo → add PostgreSQL addon → set `ANTHROPIC_API_KEY` env var. Railway auto-detects the Dockerfile.

## Adding a new API route

1. Add the model to `models.py` and schema to `schemas.py`
2. Create `backend/app/routers/yourrouter.py` with `router = APIRouter(prefix="/yourprefix", tags=[...])`
3. Include it in `main.py`: `app.include_router(yourrouter.router, prefix="/api")`
4. Add the API call to `frontend/src/api/inventory.js`
