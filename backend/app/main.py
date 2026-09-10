from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .config import settings
from .db import Base, SessionLocal, engine
from .seed import seed

app = FastAPI(title="AI Data Steward Stage 2 API", version="0.2.0", description="Governance, metadata, quality, publication lifecycle, and CKAN integration proof of concept.")
origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router, prefix="/api")

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed(db)

@app.get("/health")
def health():
    return {"status": "ok", "version": "0.2.0", "auth_mode": settings.auth_mode, "publisher": settings.catalog_publisher}
