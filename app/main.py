import os
import logging
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load env before other imports to ensure configurations are loaded first
load_dotenv()

from app.config import settings
from app.db import db_lifespan
from app.router import router as core_router
from app.auth.router import router as auth_router
from app.observability.router import router as obs_router

# Setup Logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("stock_intelligence")

from app.observability.middleware import TraceMiddleware

# Create FastAPI App with Lifespan
app = FastAPI(
    title="Stock Intelligence Platform",
    description="A production-grade AI Agent system that analyzes stock portfolio transactions from Excel files using LangGraph, LangChain, and FastAPI.",
    version="1.0.0",
    lifespan=db_lifespan
)

# Request Tracing Middleware (should run early in chain)
app.add_middleware(TraceMiddleware)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(core_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(obs_router, prefix="/api/v1")

@app.get("/")
def read_root():
    return {
        "name": "Stock Intelligence Platform API",
        "version": "1.0.0",
        "status": "healthy",
        "docs_url": "/docs"
    }

if __name__ == "__main__":
    logger.info(f"Starting server on {settings.host}:{settings.port}")
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)

