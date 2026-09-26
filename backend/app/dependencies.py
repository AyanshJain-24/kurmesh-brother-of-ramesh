from dataclasses import dataclass

from redis import Redis
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings


@dataclass(frozen=True)
class Check:
    status: str
    detail: str | None = None


def database_check(settings: Settings) -> Check:
    if not settings.database_url:
        return Check("UNAVAILABLE", "DATABASE_URL is not configured")
    try:
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            postgis = connection.execute(text("SELECT PostGIS_Version()"))
            version = postgis.scalar_one()
        engine.dispose()
        return Check("LIVE", f"PostGIS {version}")
    except SQLAlchemyError:
        return Check("ERROR", "Database or PostGIS is unavailable")


def redis_check(settings: Settings) -> Check:
    if not settings.redis_url:
        return Check("UNAVAILABLE", "REDIS_URL is not configured")
    try:
        client = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
        client.ping()
        client.close()
        return Check("LIVE")
    except Exception:  # Network details are intentionally not exposed in health responses.
        return Check("ERROR", "Redis is unavailable")
