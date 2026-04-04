"""Structured logging configuration using loguru.

Usage in modules:
    from app.core.logging import logger
    
    logger.info("User created", user_id=user.id)
    logger.error("Operation failed", error=str(e), context={"key": "value"})
"""

import sys
from typing import Any

from loguru import logger

from app.core.config import settings


def configure_logging() -> None:
    """Configure structured logging for the application.
    
    Call this once at application startup (in main.py).
    """
    # Remove default handler
    logger.remove()
    
    # Determine log level from environment
    log_level = "DEBUG" if settings.env == "local" else "INFO"
    
    # Console output format
    if settings.env == "local":
        # Human-readable format for development
        format_string = (
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        )
    else:
        # JSON format for production (structured logging)
        format_string = "{message}"
    
    # Add console handler
    logger.add(
        sys.stderr,
        format=format_string,
        level=log_level,
        colorize=settings.env == "local",
        serialize=settings.env != "local",  # JSON in production
        backtrace=settings.env == "local",
        diagnose=settings.env == "local",
    )
    
    # Add file handler for production
    if settings.env != "local":
        logger.add(
            "logs/app.log",
            rotation="100 MB",
            retention="7 days",
            compression="gz",
            format=format_string,
            level="INFO",
            serialize=True,
        )
    
    logger.info("Logging configured", env=settings.env, level=log_level)


def get_request_logger(request_id: str | None = None) -> Any:
    """Get a logger bound with request context.
    
    Usage:
        log = get_request_logger(request_id="abc123")
        log.info("Processing request")
    """
    return logger.bind(request_id=request_id)


# Export configured logger for use throughout the app
__all__ = ["logger", "configure_logging", "get_request_logger"]
