from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import logger, configure_logging
from app.api import (
    health,
    auth,
    me,
    values,
    priorities,
    links,
    alignment,
    voice,
    assistant,
    recommendations,
    discovery,
    goals,
    tasks,
    tasks_status,
    tasks_views,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup/shutdown."""
    # Startup
    configure_logging()
    logger.info(
        "Application starting",
        app_name=settings.app_name,
        env=settings.env,
    )
    
    yield
    
    # Shutdown
    from app.core.llm import llm_client
    await llm_client.close()
    logger.info("Application shutdown complete")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Backend API for Ascent Beacon: Priority Lock",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(me.router)
app.include_router(values.router)
app.include_router(priorities.router)
app.include_router(links.router)
app.include_router(alignment.router)
app.include_router(voice.router)
app.include_router(assistant.router)
app.include_router(recommendations.router)
app.include_router(discovery.router)
app.include_router(goals.router)
app.include_router(tasks.router)
app.include_router(tasks_status.router)
app.include_router(tasks_views.router)
app.include_router(tasks_views.completions_router)


@app.get("/", include_in_schema=False)
async def root_redirect() -> RedirectResponse:
    """Redirect root to API docs."""
    return RedirectResponse(url="/docs")
