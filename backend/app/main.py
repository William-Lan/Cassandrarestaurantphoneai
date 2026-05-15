from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv

from .database import engine, Base
from .routers import inventory, menu, suppliers, orders, imports, ai, preferences

load_dotenv()

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Cassandra Restaurant Inventory",
    description="AI-powered inventory tracking and automatic reordering for restaurants",
    version="1.0.0",
)

origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(inventory.router)
app.include_router(menu.router)
app.include_router(suppliers.router)
app.include_router(orders.router)
app.include_router(imports.router)
app.include_router(ai.router)
app.include_router(preferences.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {
        "app": "Cassandra Restaurant Inventory",
        "version": "1.0.0",
        "docs": "/docs",
    }
