from datetime import timezone

from sqlalchemy import URL, DateTime, TypeDecorator, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import settings


class UTCDateTime(TypeDecorator):
    """A timestamp that is always timezone-aware UTC in Python.

    PostgreSQL returns aware datetimes for TIMESTAMP WITH TIME ZONE; SQLite has
    no such type and returns naive ones. Without this decorator, any code that
    compares a stored timestamp against datetime.now(timezone.utc) raises
    "can't compare offset-naive and offset-aware datetimes" on SQLite only,
    which is what made the default development configuration unusable.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    @staticmethod
    def _as_utc(value):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_bind_param(self, value, dialect):
        return self._as_utc(value)

    def process_result_value(self, value, dialect):
        return self._as_utc(value)


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
