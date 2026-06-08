"""
Application entry point.
Configures FastAPI with all middleware, routers, and lifecycle hooks.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from src.config.settings import get_settings
from src.api.router import api_router
from src.core.exceptions import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    ValidationError,
)
from src.core.middleware import (
    RequestIDMiddleware,
    TenantContextMiddleware,
    TimingMiddleware,
)
from src.repositories.base import initialize_elasticsearch, close_elasticsearch

logger = structlog.get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifecycle manager."""
    logger.info(
        "starting_application",
        environment=settings.app_env,
        version=settings.app_version,
        debug=settings.app_debug,
    )

    # Initialize connections
    await initialize_elasticsearch()

    logger.info("elasticsearch_connected", host=settings.elasticsearch.host)

    yield

    # Cleanup connections
    await close_elasticsearch()
    logger.info("application_shutdown_complete")


def create_application() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        description="""
        ## Marketing Notification Platform
        
        Production-grade multi-tenant SaaS notification system.
        
        ### Features
        - **Email Notifications**: HTML templates, raw HTML, hybrid mode
        - **SMS Notifications**: Twilio integration with template support
        - **Bulk Campaigns**: Send to thousands of recipients in one call
        - **Analytics**: Real-time delivery tracking and metrics
        - **Multi-tenant**: Full data isolation per workspace
        """,
        version=settings.app_version,
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # Middleware (order matters - first added = outermost)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(TimingMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(TenantContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.is_development else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception handlers
    app.add_exception_handler(AuthenticationError, _handle_auth_error)
    app.add_exception_handler(NotFoundError, _handle_not_found_error)
    app.add_exception_handler(RateLimitError, _handle_rate_limit_error)
    app.add_exception_handler(ValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)

    # Routers
    app.include_router(api_router, prefix="/api")

    # Health check
    @app.get("/health", tags=["Health"], include_in_schema=False)
    async def health_check() -> dict:
        return {"status": "healthy", "version": settings.app_version}

    @app.get("/ready", tags=["Health"], include_in_schema=False)
    async def readiness_check() -> dict:
        from src.repositories.base import get_elasticsearch_client

        client = get_elasticsearch_client()
        if client:
            await client.ping()
            return {"status": "ready", "elasticsearch": "connected"}
        return {"status": "not_ready", "elasticsearch": "disconnected"}

    return app


def _handle_auth_error(request: Request, exc: AuthenticationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"error": {"code": "AUTH_FAILED", "message": str(exc)}},
    )


def _handle_not_found_error(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"error": {"code": "NOT_FOUND", "message": str(exc)}},
    )


def _handle_rate_limit_error(request: Request, exc: RateLimitError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"error": {"code": "RATE_LIMITED", "message": str(exc)}},
        headers={"Retry-After": str(exc.retry_after)} if exc.retry_after else {},
    )


def _handle_validation_error(request: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": {"code": "VALIDATION_ERROR", "message": str(exc), "details": exc.details}},
    )


def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "unhandled_exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred"}},
    )


app = create_application()


def main() -> None:
    """Run the application with uvicorn."""
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        workers=settings.workers if not settings.is_development else 1,
        reload=settings.is_development,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()