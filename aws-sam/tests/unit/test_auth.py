"""Identidade, perfis e autorização por perfil."""

import pytest

from shared import app
from support import COORDINATOR, STRANGER, TEACHER


def test_claims_from_http_api_jwt():
    event = {"requestContext": {"authorizer": {"jwt": {"claims": {"sub": "abc", "email": "x@y.z"}}}}}
    assert app._claims(event)["sub"] == "abc"


def test_claims_from_rest_api_cognito_authorizer():
    event = {"requestContext": {"authorizer": {"claims": {"sub": "abc"}}}}
    assert app._claims(event)["sub"] == "abc"


def test_missing_token_is_unauthorized():
    with pytest.raises(app.Unauthorized):
        app._claims({"requestContext": {}})


def test_local_dev_user_only_when_configured(monkeypatch):
    monkeypatch.setenv("LOCAL_DEV_USER", "dev@classly.test")
    assert app._claims({})["email"] == "dev@classly.test"


def test_health_is_public(api):
    assert api("GET", "/health", email=None)[0] == 200


def test_protected_route_without_token_returns_401(api):
    status, body = api("GET", "/teachers", email=None)
    assert status == 401
    assert "Autenticação" in body["message"]


def test_admin_email_becomes_coordinator(api):
    status, me = api("GET", "/me", email=COORDINATOR.upper())
    assert status == 200
    assert me["role"] == "COORDINATOR"


def test_unknown_email_stays_pending_and_is_blocked(api):
    assert api("GET", "/me", email=STRANGER)[1]["role"] == "PENDING"
    assert api("GET", "/teachers", email=STRANGER)[0] == 403
    assert api("GET", "/schedules", email=STRANGER)[0] == 403


def test_registered_teacher_email_is_linked(api, catalog):
    _, me = api("GET", "/me", email=TEACHER)
    assert me["role"] == "TEACHER"
    assert me["teacherId"] == catalog["teacher"]["teacherId"]


def test_pending_user_is_promoted_when_teacher_is_registered(api):
    assert api("GET", "/me", email=TEACHER)[1]["role"] == "PENDING"
    api("POST", "/teachers", {"name": "Ana", "email": TEACHER})
    assert api("GET", "/me", email=TEACHER)[1]["role"] == "TEACHER"


@pytest.mark.parametrize("method, path, body", [
    ("POST", "/teachers", {"name": "X", "email": "x@classly.test"}),
    ("POST", "/subjects", {"code": "A", "name": "B", "weeklyHours": 2}),
    ("GET", "/users", None),
    ("POST", "/schedules/validate", {"allocations": []}),
])
def test_teacher_cannot_run_coordinator_operations(api, catalog, method, path, body):
    assert api(method, path, body, email=TEACHER)[0] == 403


def test_teacher_manages_only_own_availability(api, catalog):
    own = f"/teachers/{catalog['teacher']['teacherId']}/availability"
    body = {"availability": [{"day": "MON", "start": "08:00", "end": "10:00"}]}
    assert api("PUT", own, body, email=TEACHER)[0] == 200
    api("POST", "/teachers", {"teacherId": "bruno", "name": "Bruno", "email": "bruno@classly.test"})
    assert api("GET", "/teachers/bruno/availability", email=TEACHER)[0] == 403


def test_coordinator_changes_roles_but_not_own(api):
    _, stranger = api("GET", "/me", email=STRANGER)
    status, updated = api("PUT", f"/users/{stranger['userId']}/role", {"role": "TEACHER"})
    assert status == 200 and updated["role"] == "TEACHER"
    _, me = api("GET", "/me")
    assert api("PUT", f"/users/{me['userId']}/role", {"role": "TEACHER"})[0] == 400
    assert api("PUT", f"/users/{stranger['userId']}/role", {"role": "ROOT"})[0] == 400
