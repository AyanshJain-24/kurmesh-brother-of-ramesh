from collections.abc import Generator
from contextlib import contextmanager
import json
import re
import sqlite3
import struct
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


@compiles(Geometry, "sqlite")
def compile_geometry_sqlite(type_, compiler, **kw):
    return "TEXT"


# Suppress SpatiaLite-only DDL triggers if using vanilla SQLite
try:
    import geoalchemy2.admin.dialects.sqlite as _geo_sqlite
    _geo_sqlite.before_create = lambda *a, **k: None
    _geo_sqlite.after_create = lambda *a, **k: None
    _geo_sqlite.before_drop = lambda *a, **k: None
    _geo_sqlite.after_drop = lambda *a, **k: None
except Exception:
    pass

try:
    import geoalchemy2.types.dialects.sqlite as _geo_types_sqlite
    _orig_bind_process = _geo_types_sqlite.bind_processor_process

    def _safe_bind_process(spatial_type, bindvalue):
        from geoalchemy2.elements import WKBElement
        if isinstance(bindvalue, WKBElement):
            val_str = str(bindvalue.data)
            coords = _extract_coords(val_str)
            if coords:
                if len(coords) == 1:
                    wkt = f"POINT({coords[0][0]} {coords[0][1]})"
                else:
                    pts = ", ".join(f"{p[0]} {p[1]}" for p in coords)
                    wkt = f"LINESTRING({pts})"
                srid = bindvalue.srid if getattr(bindvalue, "srid", -1) >= 0 else spatial_type.srid
                return _geo_types_sqlite.format_geom_type(wkt, default_srid=srid)
        return _orig_bind_process(spatial_type, bindvalue)

    _geo_types_sqlite.bind_processor_process = _safe_bind_process
except Exception:
    pass


def _wkt_to_ewkb(wkt: str | bytes | None, srid: int = 4326) -> str | None:
    if not wkt:
        return None
    s = str(wkt).strip()
    m_srid = re.match(r"SRID=(\d+);(.*)", s, re.I)
    if m_srid:
        srid = int(m_srid.group(1))
        s = m_srid.group(2).strip()
    m_pt = re.match(r"POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)", s, re.I)
    if m_pt:
        x, y = float(m_pt.group(1)), float(m_pt.group(2))
        return (struct.pack("<BII", 1, 0x20000001, srid) + struct.pack("<dd", x, y)).hex()
    m_ls = re.match(r"LINESTRING\s*\((.*)\)", s, re.I)
    if m_ls:
        pts = []
        for pair in m_ls.group(1).split(","):
            parts = pair.strip().split()
            if len(parts) >= 2:
                pts.append((float(parts[0]), float(parts[1])))
        buf = struct.pack("<BIII", 1, 0x20000002, srid, len(pts))
        for x, y in pts:
            buf += struct.pack("<dd", x, y)
        return buf.hex()
    return s


def _extract_coords(val: Any) -> list[tuple[float, float]] | None:
    if not val:
        return None
    if isinstance(val, str) and (val.startswith("0101") or val.startswith("0102")):
        try:
            b = bytes.fromhex(val)
            byteorder, geom_type, srid = struct.unpack("<BII", b[:9])
            if geom_type == 0x20000001:
                x, y = struct.unpack("<dd", b[9:25])
                return [(x, y)]
            elif geom_type == 0x20000002:
                count = struct.unpack("<I", b[9:13])[0]
                pts = []
                offset = 13
                for _ in range(count):
                    pts.append(struct.unpack("<dd", b[offset : offset + 16]))
                    offset += 16
                return pts
        except Exception:
            pass
    s = str(val).strip()
    m_srid = re.match(r"SRID=(\d+);(.*)", s, re.I)
    if m_srid:
        s = m_srid.group(2).strip()
    m_pt = re.match(r"POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)", s, re.I)
    if m_pt:
        return [(float(m_pt.group(1)), float(m_pt.group(2)))]
    m_ls = re.match(r"LINESTRING\s*\((.*)\)", s, re.I)
    if m_ls:
        pts = []
        for pair in m_ls.group(1).split(","):
            parts = pair.strip().split()
            if len(parts) >= 2:
                pts.append((float(parts[0]), float(parts[1])))
        return pts
    return None


def _sqlite_st_x(val: Any) -> float | None:
    pts = _extract_coords(val)
    return pts[0][0] if pts else None


def _sqlite_st_y(val: Any) -> float | None:
    pts = _extract_coords(val)
    return pts[0][1] if pts else None


def _sqlite_st_asgeojson(val: Any) -> str | None:
    pts = _extract_coords(val)
    if not pts:
        return None
    if len(pts) == 1:
        return json.dumps({"type": "Point", "coordinates": [pts[0][0], pts[0][1]]})
    return json.dumps({"type": "LineString", "coordinates": [[p[0], p[1]] for p in pts]})


def _sqlite_asewkb(val: Any) -> str | None:
    pts = _extract_coords(val)
    if not pts:
        return val
    if len(pts) == 1:
        return _wkt_to_ewkb(f"POINT({pts[0][0]} {pts[0][1]})")
    coords_str = ", ".join(f"{p[0]} {p[1]}" for p in pts)
    return _wkt_to_ewkb(f"LINESTRING({coords_str})")


@event.listens_for(Engine, "connect")
def _register_sqlite_spatial_functions(dbapi_conn, connection_record):
    if isinstance(dbapi_conn, sqlite3.Connection):
        dbapi_conn.create_function("PostGIS_Version", 0, lambda: "3.3.0 (SQLite)")
        dbapi_conn.create_function("AsEWKB", 1, _sqlite_asewkb)
        dbapi_conn.create_function("ST_AsEWKB", 1, _sqlite_asewkb)
        dbapi_conn.create_function("GeomFromEWKB", 1, lambda v: v)
        dbapi_conn.create_function("ST_GeomFromEWKB", 1, lambda v: v)
        dbapi_conn.create_function("GeomFromEWKT", 1, lambda v: v)
        dbapi_conn.create_function("ST_GeomFromEWKT", 1, lambda v: v)
        dbapi_conn.create_function("GeomFromText", 1, lambda v: v)
        dbapi_conn.create_function("GeomFromText", 2, lambda v, s: v)
        dbapi_conn.create_function("ST_GeomFromText", 1, lambda v: v)
        dbapi_conn.create_function("ST_GeomFromText", 2, lambda v, s: v)
        dbapi_conn.create_function("ST_X", 1, _sqlite_st_x)
        dbapi_conn.create_function("ST_Y", 1, _sqlite_st_y)
        dbapi_conn.create_function("ST_AsGeoJSON", 1, _sqlite_st_asgeojson)
        dbapi_conn.create_function("AsGeoJSON", 1, _sqlite_st_asgeojson)
        dbapi_conn.create_function("RecoverGeometryColumn", 5, lambda *a: 1)
        dbapi_conn.create_function("CheckSpatialIndex", 2, lambda *a: 0)
        dbapi_conn.create_function("DiscardGeometryColumn", 2, lambda *a: 1)
        dbapi_conn.create_function("AddGeometryColumn", -1, lambda *a: 1)


def init_spatial_extensions(engine_or_db: Any, database_url: str | None = None) -> None:
    """Initialize PostGIS spatial extensions if the dialect is PostgreSQL.

    If db.engine.dialect.name == "sqlite" or DATABASE_URL starts with "sqlite:",
    SKIP CREATE EXTENSION IF NOT EXISTS postgis and any PostGIS-only extension calls entirely.
    Only execute PostGIS extension initialization if the dialect is "postgresql".
    """
    engine = getattr(engine_or_db, "engine", engine_or_db)
    if isinstance(engine, sessionmaker):
        engine = engine.kw.get("bind")

    db_url = database_url or (str(engine.url) if engine and hasattr(engine, "url") else "")
    if db_url.startswith("sqlite:") or (engine and hasattr(engine, "dialect") and engine.dialect.name == "sqlite"):
        return

    if engine and hasattr(engine, "dialect") and engine.dialect.name == "postgresql":
        with engine.connect() as conn:
            import sqlalchemy as sa
            conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS postgis"))
            conn.commit()


def build_session_factory(database_url: str) -> sessionmaker[Session]:
    engine = create_engine(database_url, pool_pre_ping=True, future=True)
    if not database_url.startswith("sqlite:") and engine.dialect.name == "postgresql":
        init_spatial_extensions(engine, database_url)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@contextmanager
def transaction(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    """Commit atomically or roll back the entire unit of work."""
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
