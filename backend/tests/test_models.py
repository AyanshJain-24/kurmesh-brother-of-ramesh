from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models import EnvironmentObservation, Mission, RouteCandidate


def test_spatial_columns_compile_for_postgis():
    mission_ddl = str(CreateTable(Mission.__table__).compile(dialect=postgresql.dialect()))
    observation_ddl = str(CreateTable(EnvironmentObservation.__table__).compile(dialect=postgresql.dialect()))
    route_ddl = str(CreateTable(RouteCandidate.__table__).compile(dialect=postgresql.dialect()))
    assert "geometry(POINT,4326)" in mission_ddl
    assert "geometry(GEOMETRY,4326)" in observation_ddl
    assert "geometry(LINESTRING,4326)" in route_ddl
