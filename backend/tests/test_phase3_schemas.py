import pytest
from pydantic import ValidationError

from app.api.v1.application import TRANSITIONS
from app.api.v1.schemas import LoginRequest, MissionCreateRequest, MissionUpdateRequest, RegisterRequest


def test_registration_requires_safe_profile_fields():
    request = RegisterRequest(email="USER@example.com", password="sufficiently-long-password", full_name="Example User")
    assert str(request.email) == "USER@example.com"
    with pytest.raises(ValidationError):
        RegisterRequest(email="not-an-email", password="sufficiently-long-password", full_name="Example User")
    with pytest.raises(ValidationError):
        RegisterRequest(email="user@example.com", password="short", full_name="Example User")


def test_login_does_not_require_registration_profile_fields():
    request = LoginRequest(email="user@example.com", password="sufficiently-long-password")
    assert str(request.email) == "user@example.com"


def test_mission_create_and_partial_update_validation():
    assert MissionCreateRequest(name="Test mission").name == "Test mission"
    assert MissionUpdateRequest(name="Renamed mission").name == "Renamed mission"
    with pytest.raises(ValidationError):
        MissionCreateRequest(name="Test mission", state="APPROVED")


def test_transition_policy_has_no_direct_approval_from_draft():
    assert "PLANNING" in TRANSITIONS["DRAFT"]
    assert "APPROVED" not in TRANSITIONS["DRAFT"]
