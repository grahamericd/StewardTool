from sqlalchemy import URL, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings


def _database_url():
    if settings.db_host:
        return URL.create(
            drivername="postgresql+psycopg",
            username=settings.db_user,
            password=settings.db_password,
            host=settings.db_host,
            port=settings.db_port,
            database=settings.db_name,
        )
    return settings.database_url


database_url = _database_url()
connect_args = {"check_same_thread": False} if str(database_url).startswith("sqlite") else {}
engine = create_engine(database_url, future=True, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
