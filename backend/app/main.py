import logging
from contextlib import asynccontextmanager

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    if settings.seed_demo_data:
        with SessionLocal() as db:
            seed(db)
        logger.warning("Demo seed data is enabled.")
    if settings.auth_mode.lower() == "demo":
        logger.warning(
            "AUTH_MODE=demo: the X-User-Email header is accepted as the caller's "
            "identity. Never expose this deployment beyond localhost."
        )
    logger.info(
        "AI Data Steward started env=%s version=%s auth_mode=%s",
        settings.app_env,
        settings.app_version,
        settings.auth_mode,
    )
    yield


app = FastAPI(
    title="AI Data Steward API",
    version=settings.app_version,
    description="Guided information stewardship, quality, review, and publication.",
    docs_url="/docs" if settings.enable_api_docs else None,
    redoc_url="/redoc" if settings.enable_api_docs else None,
    openapi_url="/openapi.json" if settings.enable_api_docs else None,
    lifespan=lifespan,
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


@app.get("/health")
def health():
    # Deployment details are useful while developing but are not worth
    # disclosing to unauthenticated callers on a public host.
    if settings.app_env.lower() == "production":
        return {"status": "ok"}
    return {
        "status": "ok",
        "version": settings.app_version,
        "environment": settings.app_env,
        "auth_mode": settings.auth_mode,
        "publisher": settings.catalog_publisher,
    }
