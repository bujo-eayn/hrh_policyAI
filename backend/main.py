"""
FastAPI main application for HRH-PolicyAI.
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import asyncio

from backend.config import settings
from backend.api.routes import router
from backend.database.connection import check_db_connection, init_db
from backend.services.ollama_client import ollama_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan event handler for startup and shutdown.
    """
    # Startup
    print(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")

    # Check database connection
    print("Checking database connection...")
    if check_db_connection():
        print("✓ Database connected successfully")
    else:
        print("✗ Database connection failed - please check your database configuration")

    # Check Ollama connection
    print("Checking Ollama connection...")
    if await ollama_client.check_connection():
        print("✓ Ollama connected successfully")
    else:
        print("✗ Ollama connection failed - make sure Ollama is running on http://localhost:11434")

    # Initialize database tables
    print("Initializing database tables...")
    try:
        init_db()
        print("✓ Database tables initialized")
    except Exception as e:
        print(f"✗ Database initialization failed: {e}")

    print(f"\n{settings.APP_NAME} is ready!")
    print(f"API docs available at: http://{settings.API_HOST}:{settings.API_PORT}/docs")

    yield

    # Shutdown
    print(f"Shutting down {settings.APP_NAME}")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-Powered RAG Chatbot for Kenya's Health Workforce Policy Interpretation",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all uncaught exceptions."""
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc) if settings.DEBUG else "An unexpected error occurred"
        }
    )


# Include routers
app.include_router(router, prefix="/api/v1")


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
        "api_prefix": "/api/v1"
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.API_RELOAD
    )
