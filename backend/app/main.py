import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .api.admin_routes import router as admin_router
from .api.auth_routes import router as auth_router
from .api.routes import router
from .config import settings
from .db import Base, SessionLocal, engine
from .seed import seed

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("ai_data_steward")

app = FastAPI(
    title="AI Data Steward API",
    version=settings.app_version,
    description="Guided information stewardship, quality, review, and publication.",
    docs_url="/docs" if settings.enable_api_docs else None,
    redoc_url="/redoc" if settings.enable_api_docs else None,
    openapi_url="/openapi.json" if settings.enable_api_docs else None,
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.trusted_host_list,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(router, prefix="/api")


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    if settings.seed_demo_data:
        with SessionLocal() as db:
            seed(db)
        logger.warning("Demo seed data is enabled.")
    logger.info(
        "AI Data Steward started env=%s version=%s auth_mode=%s",
        settings.app_env,
        settings.app_version,
        settings.auth_mode,
    )


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": settings.app_version,
        "environment": settings.app_env,
        "auth_mode": settings.auth_mode,
        "publisher": settings.catalog_publisher,
    }
