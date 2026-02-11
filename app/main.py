from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
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
)

# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Backend API for Ascent Beacon: Priority Lock",
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


@app.get("/", include_in_schema=False)
async def root_redirect():
    return RedirectResponse(url="/docs")


@app.on_event("startup")
async def startup():
    """Startup event handler."""
    print(f"🚀 {settings.app_name} starting up...")
    print(f"   Environment: {settings.env}")
    print(f"   Database: {settings.database_url.split('@')[1] if '@' in settings.database_url else 'configured'}")


@app.on_event("shutdown")
async def shutdown():
    """Shutdown event handler."""
    from app.core.llm import llm_client
    await llm_client.close()
    print("👋 Shutting down...")
