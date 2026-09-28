from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException
from flask_cors import CORS

from app.api.v1.health import health_blueprint
from app.api.v1.application import api_blueprint
from app.api.v1.ml import ml_blueprint
from app.api.v1.ml_demo import ml_demo_blueprint
from app.api.v1.workflow import workflow_blueprint
from app.auth import ApiError
from app.config import Settings
from app.database import build_session_factory
from app.logging import configure_logging
from app.ml_demo.iceberg import IcebergDemoModelService


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or Settings.from_environment()
    settings.validate()
    configure_logging(settings.log_level)
    app = Flask(__name__)
    app.config["KURMESH_SETTINGS"] = settings
    app.config["KURMESH_SESSION_FACTORY"] = build_session_factory(settings.database_url)
    # Load once during startup. An absent/corrupt artifact remains explicitly
    # unavailable rather than preventing the rest of the application from serving.
    app.extensions["kurmesh_demo_iceberg_model"] = IcebergDemoModelService.startup(
        settings.demo_iceberg_model_artifact_path,
    )
    cors_origins = settings.cors_origins
    allowed_origins = "*" if ("*" in cors_origins or not cors_origins) else cors_origins
    CORS(
        app,
        resources={
            r"/api/*": {
                "origins": allowed_origins,
                "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
                "allow_headers": ["Content-Type", "Authorization", "X-Requested-With", "Accept"],
                "expose_headers": ["Content-Type", "Authorization"],
            }
        },
        supports_credentials=True,
    )
    app.register_blueprint(health_blueprint, url_prefix="/api/v1/health")

    @app.before_request
    def open_database_session() -> None:
        # Flask does not assign request.blueprint for a method-mismatch (405),
        # even when the request targets a blueprint rule. Route by the stable
        # API prefix so every application API request receives the same scoped
        # session, while dependency-free health probes remain session-free.
        if request.path.startswith("/api/v1/") and not request.path.startswith(("/api/v1/health", "/api/v1/demo/ml/", "/api/v1/ml/")):
            g.db = app.config["KURMESH_SESSION_FACTORY"]()

    @app.teardown_request
    def close_database_session(error: BaseException | None) -> None:
        session = g.pop("db", None)
        if session is None:
            return
        if error is not None:
            session.rollback()
        session.close()

    @app.errorhandler(ApiError)
    def api_error(error: ApiError):
        return jsonify({"error": {"code": error.code, "message": error.message}}), error.status

    @app.errorhandler(HTTPException)
    def http_error(error: HTTPException):
        if request.path.startswith("/api/"):
            return jsonify({"error": {"code": error.name.upper().replace(" ", "_"), "message": error.description}}), error.code
        return error

    @app.errorhandler(Exception)
    def unexpected_error(error: Exception):
        if request.path.startswith("/api/"):
            app.logger.exception("Unhandled API error")
            return jsonify({"error": {"code": "INTERNAL_ERROR", "message": "An unexpected server error occurred"}}), 500
        raise error

    app.register_blueprint(api_blueprint, url_prefix="/api/v1")
    app.register_blueprint(workflow_blueprint, url_prefix="/api/v1")
    app.register_blueprint(ml_demo_blueprint, url_prefix="/api/v1/demo/ml")
    app.register_blueprint(ml_blueprint, url_prefix="/api/v1/ml")

    @app.get("/api/v1")
    def api_root() -> dict[str, str]:
        return {"service": "kurmesh-api", "version": "v1", "status": "FOUNDATION"}

    return app
