"""Local SQLite seeding script for KURMESH operational UI testing.

Creates all tables and idempotently populates default demo data:
- Operator user: operator@kurmesh.org / OperatorPass123!
- Research vessel: KURMESH Research Vessel (PC6 Ice-class)
- Antarctic research mission with origin & destination coordinates
- Authorized environmental provider observations (Sea Ice, Weather, Ocean)
- Generated Antarctic route candidates with Polar A* LineString coordinates
- Governed route for Human-in-the-Loop review & approval workflow
"""

import os
import sys
import uuid
from datetime import UTC, datetime, timedelta

# Ensure both backend directory and repo root are in path
backend_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(backend_dir)
sys.path.insert(0, repo_root)
sys.path.insert(0, backend_dir)

from geoalchemy2.elements import WKTElement
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

import math
from app.auth import password_hash
from app.database import Base
from app.models import (
    Alert,
    AuditEvent,
    EnvironmentObservation,
    EnvironmentSource,
    Mission,
    Role,
    Route,
    RouteCandidate,
    User,
    Vessel,
)
from app.services.routing_service import generate_candidates
from ml.adapter import default_adapter, compute_coriolis_f

DB_PATH = os.environ.get("DATABASE_URL", "sqlite:///backend/kurmesh.db")


def ensure_sqlite_dir(db_url: str) -> None:
    if db_url.startswith("sqlite:///"):
        filepath = db_url[len("sqlite:///"):]
        if filepath and not filepath.startswith(":"):
            dirpath = os.path.dirname(os.path.abspath(filepath))
            if dirpath:
                os.makedirs(dirpath, exist_ok=True)


def seed_database(db_url: str = DB_PATH) -> dict[str, str]:
    ensure_sqlite_dir(db_url)
    engine = create_engine(db_url, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with session_factory.begin() as session:
        # 1. Roles
        roles_map = {}
        for role_name in ("user", "operator", "admin"):
            role = session.scalar(select(Role).where(Role.name == role_name))
            if role is None:
                role = Role(name=role_name)
                session.add(role)
                session.flush()
            roles_map[role_name] = role

        # 2. Demo User
        demo_email = "operator@kurmesh.org"
        user = session.scalar(select(User).where(User.email == demo_email))
        if user is None:
            user = User(
                email=demo_email,
                full_name="Lead Polar Operator",
                password_hash=password_hash("OperatorPass123!"),
                is_active=True,
                roles=list(roles_map.values()),
            )
            session.add(user)
            session.flush()
        else:
            user.roles = list(roles_map.values())
            session.flush()

        # 3. Vessel
        vessel_name = "KURMESH Research Vessel"
        vessel = session.scalar(select(Vessel).where(Vessel.name == vessel_name))
        if vessel is None:
            vessel = Vessel(
                name=vessel_name,
                vessel_type="Research vessel",
                imo_number="IMO9876543",
                specifications={
                    "cruising_speed_knots": 12.0,
                    "ice_class": "PC6",
                    "length_m": 128.0,
                    "beam_m": 22.0,
                    "draft_m": 7.5,
                    "polar_code_category": "A",
                },
            )
            session.add(vessel)
            session.flush()

        # 4. Mission
        mission_name = "Antarctic Research Mission"
        mission = session.scalar(select(Mission).where(Mission.name == mission_name, Mission.created_by_id == user.id))
        now = datetime.now(UTC)
        if mission is None:
            mission = Mission(
                name=mission_name,
                state="ANALYZING",
                vessel_id=vessel.id,
                created_by_id=user.id,
                departure_at=now + timedelta(days=2),
                origin=WKTElement("POINT(20 -70)", srid=4326),
                destination=WKTElement("POINT(50 -68)", srid=4326),
            )
            session.add(mission)
            session.flush()

        # 5. Environmental Sources and Observations
        src_nsidc = session.scalar(select(EnvironmentSource).where(EnvironmentSource.provider == "NOAA / NSIDC"))
        if src_nsidc is None:
            src_nsidc = EnvironmentSource(
                provider="NOAA / NSIDC",
                source="G10016 Antarctic Sea Ice Concentration",
                url="https://nsidc.org/data/g10016",
                metadata_json={"resolution": "25km", "grid": "polar_stereographic"},
            )
            session.add(src_nsidc)
            session.flush()

        src_gfs = session.scalar(select(EnvironmentSource).where(EnvironmentSource.provider == "NOAA"))
        if src_gfs is None:
            src_gfs = EnvironmentSource(
                provider="NOAA",
                source="Global Forecast System (GFS)",
                url="https://nomads.ncep.noaa.gov",
                metadata_json={"resolution": "0.25deg"},
            )
            session.add(src_gfs)
            session.flush()

        src_copernicus = session.scalar(select(EnvironmentSource).where(EnvironmentSource.provider == "Copernicus Marine"))
        if src_copernicus is None:
            src_copernicus = EnvironmentSource(
                provider="Copernicus Marine",
                source="Global Ocean Physics Analysis and Forecast",
                url="https://marine.copernicus.eu",
                metadata_json={"dataset": "GLOBAL_ANALYSISFORECAST_PHY_001_024"},
            )
            session.add(src_copernicus)
            session.flush()

        src_byu = session.scalar(select(EnvironmentSource).where(EnvironmentSource.provider == "BYU"))
        if src_byu is None:
            src_byu = EnvironmentSource(
                provider="BYU",
                source="Antarctic Iceberg Tracking Database",
                url="https://www.scp.byu.edu/data/iceberg/",
                metadata_json={"method": "scatterometer", "target": "A-23A", "region": "Weddell / South Atlantic"},
            )
            session.add(src_byu)
            session.flush()

        # Compute authentic physical evaluations
        sea_ice_eval = default_adapter.predict_sea_ice_concentration({"bounds": [19.0, -71.0, 21.0, -69.0]})
        sea_ice_conc = round(sea_ice_eval["prediction"]["mean_concentration"], 4) if sea_ice_eval.get("prediction") else 0.25

        iceberg_features = {
            "latitude": -70.2,
            "longitude": 20.5,
            "length_m": 4200.0,
            "width_m": 3100.0,
            "estimated_draft_m": 250.0,
            "coriolis_f": compute_coriolis_f(-70.2),
        }
        iceberg_eval = default_adapter.predict_iceberg_drift(iceberg_features)
        pred_drift = iceberg_eval.get("prediction") or {}
        dx = float(pred_drift.get("dx_m", -0.459))
        dy = float(pred_drift.get("dy_m", 0.035))
        drift_speed = math.sqrt(dx * dx + dy * dy)

        # Observations
        existing_obs = session.scalar(select(EnvironmentObservation.id).limit(1))
        if existing_obs is None:
            obs_list = [
                EnvironmentObservation(
                    source_id=src_nsidc.id,
                    observation_type="sea_ice_concentration",
                    status="LIVE",
                    value={"concentration": sea_ice_conc},
                    units="fraction (0-1)",
                    quality="validated",
                    retrieved_at=now,
                    valid_from=now - timedelta(hours=6),
                    valid_to=now + timedelta(hours=18),
                    location=WKTElement("POINT(20 -70)", srid=4326),
                ),
                EnvironmentObservation(
                    source_id=src_byu.id,
                    observation_type="iceberg",
                    status="LIVE",
                    value={
                        "target_id": "A-23A",
                        "latitude": -70.2,
                        "longitude": 20.5,
                        "length_m": 4200.0,
                        "width_m": 3100.0,
                        "estimated_draft_m": 250.0,
                        "predicted_drift_dx_m": round(dx, 3),
                        "predicted_drift_dy_m": round(dy, 3),
                        "drift_speed_m_per_day": round(drift_speed, 3),
                    },
                    units="m/day",
                    quality="validated_trajectory",
                    retrieved_at=now,
                    valid_from=now - timedelta(hours=6),
                    valid_to=now + timedelta(hours=18),
                    location=WKTElement("POINT(20.5 -70.2)", srid=4326),
                ),
                EnvironmentObservation(
                    source_id=src_gfs.id,
                    observation_type="wind",
                    status="LIVE",
                    value={"speed": 18.5, "direction_deg": 240.0, "gust_knots": 24.0},
                    units="knots",
                    quality="forecast",
                    retrieved_at=now,
                    valid_from=now,
                    valid_to=now + timedelta(hours=12),
                    location=WKTElement("POINT(20 -70)", srid=4326),
                ),
                EnvironmentObservation(
                    source_id=src_gfs.id,
                    observation_type="air_temperature",
                    status="LIVE",
                    value={"temperature": -6.5},
                    units="°C",
                    quality="forecast",
                    retrieved_at=now,
                    valid_from=now,
                    valid_to=now + timedelta(hours=12),
                    location=WKTElement("POINT(20 -70)", srid=4326),
                ),
                EnvironmentObservation(
                    source_id=src_gfs.id,
                    observation_type="sea_level_pressure",
                    status="LIVE",
                    value={"pressure": 994.2},
                    units="hPa",
                    quality="forecast",
                    retrieved_at=now,
                    valid_from=now,
                    valid_to=now + timedelta(hours=12),
                    location=WKTElement("POINT(20 -70)", srid=4326),
                ),
                EnvironmentObservation(
                    source_id=src_copernicus.id,
                    observation_type="ocean_current",
                    status="LIVE",
                    value={"speed": 1.15, "direction_degrees": 110.0},
                    units="knots",
                    quality="modeled",
                    retrieved_at=now,
                    valid_from=now,
                    valid_to=now + timedelta(hours=24),
                    location=WKTElement("POINT(20 -70)", srid=4326),
                ),
                EnvironmentObservation(
                    source_id=src_copernicus.id,
                    observation_type="sea_water_temperature",
                    status="LIVE",
                    value={"temperature": -1.4},
                    units="°C",
                    quality="modeled",
                    retrieved_at=now,
                    valid_from=now,
                    valid_to=now + timedelta(hours=24),
                    location=WKTElement("POINT(20 -70)", srid=4326),
                ),
            ]
            session.add_all(obs_list)
            session.flush()
        else:
            # Ensure BYU iceberg observation exists if reseeding an existing database
            existing_iceberg_obs = session.scalar(select(EnvironmentObservation.id).where(EnvironmentObservation.observation_type == "iceberg").limit(1))
            if existing_iceberg_obs is None:
                session.add(
                    EnvironmentObservation(
                        source_id=src_byu.id,
                        observation_type="iceberg",
                        status="LIVE",
                        value={
                            "target_id": "A-23A",
                            "latitude": -70.2,
                            "longitude": 20.5,
                            "length_m": 4200.0,
                            "width_m": 3100.0,
                            "estimated_draft_m": 250.0,
                            "predicted_drift_dx_m": round(dx, 3),
                            "predicted_drift_dy_m": round(dy, 3),
                            "drift_speed_m_per_day": round(drift_speed, 3),
                        },
                        units="m/day",
                        quality="validated_trajectory",
                        retrieved_at=now,
                        valid_from=now - timedelta(hours=6),
                        valid_to=now + timedelta(hours=18),
                        location=WKTElement("POINT(20.5 -70.2)", srid=4326),
                    )
                )
                session.flush()

        # 6. Route Candidates
        existing_verified = session.scalar(
            select(RouteCandidate.id).where(
                RouteCandidate.mission_id == mission.id,
                RouteCandidate.risk_data_status == "VERIFIED"
            ).limit(1)
        )
        if existing_verified is None:
            # Clean up old unverified/draft candidates if present
            old_ids = list(session.scalars(select(RouteCandidate.id).where(RouteCandidate.mission_id == mission.id)))
            if old_ids:
                for old_route in session.scalars(select(Route).where(Route.route_candidate_id.in_(old_ids))):
                    session.delete(old_route)
                for old_c in session.scalars(select(RouteCandidate).where(RouteCandidate.mission_id == mission.id)):
                    session.delete(old_c)
                session.flush()

            candidates, _ = generate_candidates(session, mission)
            session.flush()
            mission.state = "ROUTES_AVAILABLE"
        else:
            candidates = list(session.scalars(select(RouteCandidate).where(RouteCandidate.mission_id == mission.id).order_by(RouteCandidate.version)))

        # 7. Governed Route for Candidate 1
        if candidates:
            primary_candidate = candidates[0]
            governed = session.scalar(select(Route).where(Route.route_candidate_id == primary_candidate.id))
            if governed is None:
                governed = Route(
                    route_candidate_id=primary_candidate.id,
                    status="UNDER_REVIEW",
                    geometry=primary_candidate.geometry,
                    metadata_json={"selected_by": str(user.id), "notes": "Candidate 1 selected for independent operator review"},
                )
                session.add(governed)
                session.flush()

        # 8. Alert
        existing_alert = session.scalar(select(Alert).where(Alert.mission_id == mission.id).limit(1))
        if existing_alert is None:
            alert = Alert(
                mission_id=mission.id,
                severity="MEDIUM",
                category="NAVIGATION",
                title="Marginal Ice Zone Approaching",
                status="OPEN",
                message="Sea ice concentration exceeding 30% near 35°E. Human operator review recommended before departure.",
            )
            session.add(alert)
            session.flush()

        # 9. Audit record
        audit = session.scalar(select(AuditEvent).where(AuditEvent.event_type == "DEMO_BOOTSTRAPPED", AuditEvent.entity_id == mission.id))
        if audit is None:
            session.add(
                AuditEvent(
                    actor_id=user.id,
                    event_type="DEMO_BOOTSTRAPPED",
                    entity_type="Mission",
                    entity_id=mission.id,
                    payload={"seed_identity": "kurmesh-local-sqlite-v1"},
                )
            )

        return {
            "status": "SEEDED",
            "user_email": demo_email,
            "user_password": "OperatorPass123!",
            "user_id": str(user.id),
            "vessel_id": str(vessel.id),
            "mission_id": str(mission.id),
            "candidates_count": str(len(candidates)),
        }


if __name__ == "__main__":
    args = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    db = args[0] if args else os.environ.get("DATABASE_URL", DB_PATH)
    if_empty = "--if-empty" in sys.argv or "--only-if-empty" in sys.argv

    if if_empty:
        ensure_sqlite_dir(db)
        temp_engine = create_engine(db, pool_pre_ping=True)
        Base.metadata.create_all(bind=temp_engine)
        with Session(temp_engine) as check_session:
            try:
                has_users = check_session.scalar(select(User.id).limit(1)) is not None
                has_candidates = check_session.scalar(select(RouteCandidate.id).limit(1)) is not None
                if has_users and has_candidates:
                    print(f"Database at {db} already has operational data; skipping seed.")
                    sys.exit(0)
            except Exception:
                pass

    print(f"Seeding KURMESH SQLite database at: {db}")
    res = seed_database(db)
    print("Database seeding completed successfully:")
    for k, v in res.items():
        print(f"  {k}: {v}")
