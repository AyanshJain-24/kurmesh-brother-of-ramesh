from flask import Blueprint, current_app, jsonify

from app.config import Settings
from app.dependencies import Check, database_check, redis_check

health_blueprint = Blueprint("health", __name__)


def checks() -> dict[str, Check]:
    settings: Settings = current_app.config["KURMESH_SETTINGS"]
    return {"database": database_check(settings), "redis": redis_check(settings)}


def payload(status: str, services: dict[str, Check]):
    return {"status": status, "services": {name: {key: value for key, value in {"status": check.status, "detail": check.detail}.items() if value is not None} for name, check in services.items()}}


@health_blueprint.get("/live")
def live():
    return jsonify({"status": "LIVE", "service": "kurmesh-api"}), 200


@health_blueprint.get("")
@health_blueprint.get("/")
def health():
    dependencies = checks()
    overall = "LIVE" if all(check.status == "LIVE" for check in dependencies.values()) else "DEGRADED"
    return jsonify(payload(overall, dependencies)), 200


@health_blueprint.get("/ready")
def ready():
    dependencies = checks()
    is_ready = all(check.status == "LIVE" for check in dependencies.values())
    return jsonify(payload("LIVE" if is_ready else "UNAVAILABLE", dependencies)), 200 if is_ready else 503
