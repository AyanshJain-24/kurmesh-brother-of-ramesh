import uuid
from functools import wraps

from flask import current_app, g, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash, generate_password_hash

from app.models import User


class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        self.code, self.message, self.status = code, message, status


def serializer() -> URLSafeTimedSerializer:
    secret = current_app.config["KURMESH_SETTINGS"].auth_secret
    if not secret:
        raise ApiError("AUTH_NOT_CONFIGURED", "Authentication is not configured", 503)
    return URLSafeTimedSerializer(secret_key=secret, salt="kurmesh-auth-v1")


def issue_token(user: User) -> str:
    return serializer().dumps({"sub": str(user.id)})


def authenticate(session: Session) -> User:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise ApiError("UNAUTHENTICATED", "Bearer authentication is required", 401)
    try:
        payload = serializer().loads(header[7:], max_age=3600)
        user = session.get(User, uuid.UUID(payload["sub"]))
    except (BadSignature, SignatureExpired, KeyError, ValueError):
        raise ApiError("UNAUTHENTICATED", "Invalid or expired token", 401) from None
    if user is None or not user.is_active:
        raise ApiError("UNAUTHENTICATED", "User is unavailable", 401)
    g.current_user = user
    return user


def require_roles(*allowed: str):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = authenticate(g.db)
            if allowed and not {role.name for role in user.roles}.intersection(allowed):
                raise ApiError("FORBIDDEN", "Insufficient role", 403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def password_hash(password: str) -> str:
    return generate_password_hash(password)


def password_matches(stored: str, supplied: str) -> bool:
    return check_password_hash(stored, supplied)
