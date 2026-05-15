# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running locally

```bash
./start.sh
```

Backend on `:8000`, frontend on `:5173`. API docs at `http://localhost:8000/api/docs`. Copy `backend/.env.example` → `backend/.env` and add `ANTHROPIC_API_KEY`.

## Architecture

**Dev:** Vite (`:5173`) proxies `/api/*` → FastAPI (`:8000`) — prefix is NOT stripped.
**Prod:** FastAPI serves built React from `frontend/dist/` as static files. Everything on one URL.

**Backend** — `backend/app/`
- `models.py` / `schemas.py` — all models and Pydantic schemas in one file each
- `routers/` — one file per resource; all mounted under `/api` in `main.py`
- `services/ai_service.py` — all three Claude calls: reorder suggestions, file parsing, inventory matching

**Key data rules:**
- `InventoryTransaction.quantity_change` is signed (positive = in, negative = out)
- Stock updates happen in two places: `POST /api/inventory/transactions/` and `PATCH /api/orders/{id}/status` when status → `received`
- `ReorderRule.rule_type`: `ai_driven | manual_threshold | hybrid`

**AI import flow:** `POST /api/import/upload` → Claude extracts line items + fuzzy-matches to inventory IDs → `POST /api/import/confirm` writes transactions and optionally creates new items.

## Adding a route

1. Add model to `models.py`, schema to `schemas.py`
2. Create `routers/yourrouter.py` with `router = APIRouter(prefix="/yourprefix")`
3. In `main.py`: `app.include_router(yourrouter.router, prefix="/api")`
4. Add API call to `frontend/src/api/inventory.js`

## Deployment

Railway: connect repo → add PostgreSQL addon → set `ANTHROPIC_API_KEY`. Dockerfile handles the rest.
