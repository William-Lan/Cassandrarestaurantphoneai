from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from pathlib import Path
from dotenv import load_dotenv

from .database import engine, Base
from .routers import inventory, menu, suppliers, orders, imports, ai, preferences

load_dotenv()

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Cassandra Restaurant Inventory",
    description="AI-powered inventory tracking and automatic reordering for restaurants",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# All API routes live under /api
app.include_router(inventory.router,   prefix="/api")
app.include_router(menu.router,        prefix="/api")
app.include_router(suppliers.router,   prefix="/api")
app.include_router(orders.router,      prefix="/api")
app.include_router(imports.router,     prefix="/api")
app.include_router(ai.router,          prefix="/api")
app.include_router(preferences.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Serve the built React frontend (production)
FRONTEND_DIST = Path(os.getenv(
    "FRONTEND_DIST",
    str(Path(__file__).parent.parent.parent / "frontend" / "dist")
))

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        index = FRONTEND_DIST / "index.html"
        return FileResponse(str(index))
