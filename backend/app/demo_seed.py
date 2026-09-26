"""Idempotent public-demo identity and mission bootstrap.

This module deliberately creates no environmental observations, predictions,
route candidates, routes, reviews, or approvals.  It is invoked by the backend
container only when ``KURMESH_DEMO_SEED=true`` is configured.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth import password_hash
from app.config import Settings
from app.database import build_session_factory
from app.models import AuditEvent, Mission, Role, RouteCandidate, User, Vessel

DEMO_EMAIL = "KURMESH_DEMO_EMAIL"
DEMO_PASSWORD = "KURMESH_DEMO_PASSWORD"
DEMO_FULL_NAME = "KURMESH_DEMO_FULL_NAME"
DEMO_SEED = "KURMESH_DEMO_SEED"
DEMO_VESSEL_NAME = "KURMESH Research Vessel"
DEMO_MISSION_NAME = "Antarctic Research Mission"


def enabled() -> bool:
    return os.environ.get(DEMO_SEED, "false").strip().lower() == "true"


@dataclass(frozen=True)
class DemoSeedConfiguration:
    email: str
    password: str
    full_name: str

    @classmethod
    def from_environment(cls) -> "DemoSeedConfiguration":
        email = os.environ.get(DEMO_EMAIL, "").strip().lower()
        password = os.environ.get(DEMO_PASSWORD, "")
        full_name = os.environ.get(DEMO_FULL_NAME, "KURMESH Demo User").strip()
        if not email or not password or not full_name:
            raise ValueError("KURMESH_DEMO_EMAIL, KURMESH_DEMO_PASSWORD, and KURMESH_DEMO_FULL_NAME must be configured when KURMESH_DEMO_SEED=true")
        if len(password) < 12:
            raise ValueError("KURMESH_DEMO_PASSWORD must contain at least 12 characters")
        return cls(email=email, password=password, full_name=full_name)


@dataclass(frozen=True)
class DemoSeedResult:
    status: str
    user_id: str | None = None
    vessel_id: str | None = None
    mission_id: str | None = None


def seed_demo_data(session_factory: sessionmaker[Session], configuration: DemoSeedConfiguration) -> DemoSeedResult:
    """Create or reuse the public-demo records in one transaction.

    The fixed vessel and mission labels are seed identities, not operational
    data.  A route-bearing mission is never reset to ``ANALYZING`` so running
    the bootstrap again cannot discard a judge's route workflow.
    """
    with session_factory.begin() as session:
        role = session.scalar(select(Role).where(Role.name == "user"))
        if role is None:
            role = Role(name="user")
            session.add(role)
            session.flush()

        user = session.scalar(select(User).where(User.email == configuration.email))
        if user is None:
            user = User(email=configuration.email, full_name=configuration.full_name, password_hash=password_hash(configuration.password), roles=[role])
            session.add(user)
            session.flush()

        vessel = session.scalar(select(Vessel).where(Vessel.name == DEMO_VESSEL_NAME).order_by(Vessel.created_at, Vessel.id))
        if vessel is None:
            vessel = Vessel(name=DEMO_VESSEL_NAME, vessel_type="Research vessel", imo_number=None,
                            specifications={"cruising_speed_knots": 12.0, "seed_identity": "kurmesh-public-demo-v1"})
            session.add(vessel)
            session.flush()
        elif not isinstance((vessel.specifications or {}).get("cruising_speed_knots"), (int, float)) or vessel.specifications["cruising_speed_knots"] <= 0:
            vessel.specifications = {**(vessel.specifications or {}), "cruising_speed_knots": 12.0, "seed_identity": "kurmesh-public-demo-v1"}

        mission = session.scalar(select(Mission).where(Mission.name == DEMO_MISSION_NAME, Mission.created_by_id == user.id).order_by(Mission.created_at, Mission.id))
        if mission is None:
            mission = Mission(name=DEMO_MISSION_NAME, state="ANALYZING", vessel_id=vessel.id, created_by_id=user.id,
                              origin=WKTElement("POINT(20 -70)", srid=4326), destination=WKTElement("POINT(50 -68)", srid=4326))
            session.add(mission)
            session.flush()
        else:
            mission.vessel_id = vessel.id
            if mission.origin is None:
                mission.origin = WKTElement("POINT(20 -70)", srid=4326)
            if mission.destination is None:
                mission.destination = WKTElement("POINT(50 -68)", srid=4326)
            has_candidates = session.scalar(select(RouteCandidate.id).where(RouteCandidate.mission_id == mission.id).limit(1)) is not None
            if not has_candidates and mission.state not in {"ANALYZING", "ROUTES_AVAILABLE", "UNDER_REVIEW", "APPROVED", "REJECTED", "COMPLETED"}:
                mission.state = "ANALYZING"

        audit = session.scalar(select(AuditEvent).where(AuditEvent.event_type == "DEMO_BOOTSTRAPPED", AuditEvent.entity_type == "Mission", AuditEvent.entity_id == mission.id))
        if audit is None:
            session.add(AuditEvent(actor_id=user.id, event_type="DEMO_BOOTSTRAPPED", entity_type="Mission", entity_id=mission.id,
                                   payload={"seed_identity": "kurmesh-public-demo-v1"}))
        return DemoSeedResult("SEEDED", str(user.id), str(vessel.id), str(mission.id))


def main() -> None:
    if not enabled():
        print("KURMESH demo seed disabled")
        return
    settings = Settings.from_environment()
    settings.validate()
    result = seed_demo_data(build_session_factory(settings.database_url), DemoSeedConfiguration.from_environment())
    print(f"KURMESH demo seed {result.status}: mission={result.mission_id}")


if __name__ == "__main__":
    main()
