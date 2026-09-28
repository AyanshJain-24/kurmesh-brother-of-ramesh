import logging
import os
import uuid

from celery import Celery

logger = logging.getLogger(__name__)

broker_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
celery_app = Celery("kurmesh", broker=broker_url, backend=broker_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)


@celery_app.task(name="app.worker.generate_routing_task", bind=True)
def generate_routing_task(self, mission_id_str: str) -> dict:
    """Asynchronously triggers the routing service without blocking the main API thread."""
    from app.config import Settings
    from app.database import build_session_factory
    from app.models import AuditEvent, Mission
    from app.services.routing_service import default_routing_service

    mission_uuid = uuid.UUID(mission_id_str)
    settings = Settings.from_environment()
    session_factory = build_session_factory(settings.database_url)

    with session_factory() as session:
        mission = session.get(Mission, mission_uuid)
        if mission is None:
            logger.error("Mission %s not found for async routing", mission_id_str)
            return {"error": "Mission not found", "mission_id": mission_id_str}

        try:
            candidates, warnings = default_routing_service.generate_candidates(session, mission)

            if mission.state == "ANALYZING":
                mission.state = "ROUTES_AVAILABLE"
                session.add(
                    AuditEvent(
                        actor_id=None,
                        event_type="MISSION_TRANSITIONED",
                        entity_type="Mission",
                        entity_id=mission.id,
                        payload={"state": "ROUTES_AVAILABLE", "reason": "async_route_candidates_generated"},
                    )
                )

            for candidate in candidates:
                session.add(
                    AuditEvent(
                        actor_id=None,
                        event_type="ROUTE_CANDIDATE_GENERATED",
                        entity_type="RouteCandidate",
                        entity_id=candidate.id,
                        payload={
                            "algorithm_version": candidate.algorithm_version,
                            "route_type": candidate.metadata_json.get("route_type", "UNKNOWN"),
                            "status": candidate.status,
                            "risk_data_status": candidate.risk_data_status,
                        },
                    )
                )

            session.commit()
            logger.info("Successfully generated %d candidates for mission %s", len(candidates), mission_id_str)
            return {
                "mission_id": mission_id_str,
                "candidate_count": len(candidates),
                "candidate_ids": [str(c.id) for c in candidates],
                "warnings": warnings,
                "status": "SUCCESS",
            }
        except Exception as exc:
            session.rollback()
            logger.exception("Failed async candidate generation for mission %s: %s", mission_id_str, exc)
            return {"error": str(exc), "mission_id": mission_id_str, "status": "FAILED"}
