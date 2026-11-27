"""Registro de operações críticas na auditoria."""

import json

from shared import app
from support import STRANGER, TEACHER


def actions(api):
    _, items = api("GET", "/audit")
    return [(i["action"], i["entity"]) for i in items]


def query_audit(**params):
    event = {"rawPath": "/audit", "queryStringParameters": params,
             "requestContext": {"http": {"method": "GET"}, "authorizer": {"jwt": {"claims": {
                 "sub": "sub-coordenacao@classly.test", "email": "coordenacao@classly.test"}}}}}
    response = app.handler(event, None)
    return response["statusCode"], json.loads(response["body"])


def test_crud_and_lifecycle_are_audited(api, catalog):
    _, schedule = api("POST", "/schedules", {"term": "2026.2", "allocations": [
        {"classId": catalog["class"]["classId"], "teacherId": catalog["teacher"]["teacherId"],
         "subjectId": catalog["subject"]["subjectId"], "day": day, "start": "08:00", "end": "10:00"}
        for day in ("MON", "WED")
    ]})
    sid = schedule["scheduleId"]
    for action in ("submit", "approve", "publish"):
        api("POST", f"/schedules/{sid}/{action}")
    api("DELETE", f"/teachers/{catalog['teacher']['teacherId']}/subjects/{catalog['subject']['subjectId']}")

    recorded = actions(api)
    for expected in [
        ("CREATE", "teachers"), ("CREATE", "subjects"), ("CREATE", "classes"),
        ("UPDATE", "qualifications"), ("CREATE", "schedule"), ("SCHEDULE_IN_REVIEW", "schedule"),
        ("SCHEDULE_APPROVED", "schedule"), ("SCHEDULE_PUBLISHED", "schedule"),
        ("NOTIFICATION_SENT", "schedule"), ("DELETE", "qualifications"), ("USER_CREATED", "user"),
    ]:
        assert expected in recorded, expected
    # Mais recentes primeiro.
    assert recorded[0] == ("DELETE", "qualifications")


def test_audit_records_who_did_what(api):
    api("POST", "/subjects", {"subjectId": "s1", "code": "A", "name": "Álgebra", "weeklyHours": 2})
    api("PUT", "/subjects/s1", {"code": "A", "name": "Álgebra Linear", "weeklyHours": 2})
    _, items = api("GET", "/audit")
    update = [i for i in items if i["action"] == "UPDATE"][0]
    assert update["email"] == "coordenacao@classly.test"
    assert update["details"]["before"]["name"] == "Álgebra"
    assert update["details"]["after"]["name"] == "Álgebra Linear"


def test_role_changes_are_audited(api):
    _, stranger = api("GET", "/me", email=STRANGER)
    api("PUT", f"/users/{stranger['userId']}/role", {"role": "TEACHER"})
    _, items = api("GET", "/audit")
    change = [i for i in items if i["action"] == "ROLE_CHANGED"][0]
    assert change["details"] == {"email": STRANGER, "from": "PENDING", "to": "TEACHER"}


def test_audit_is_only_for_coordination(api, catalog):
    assert api("GET", "/audit", email=TEACHER)[0] == 403


def test_login_trigger_records_login(aws):
    event = {"triggerSource": "PostAuthentication_Authentication", "userName": "u1",
             "request": {"userAttributes": {"sub": "u1", "email": "ana@classly.test"}}}
    assert app.login_event_handler(event, None) is event
    [item] = app._items(app.TABLES["audit"])
    assert (item["action"], item["email"], item["entityId"]) == ("LOGIN", "ana@classly.test", "u1")


def test_audit_failure_never_breaks_the_operation(api, monkeypatch):
    monkeypatch.setitem(app.TABLES, "audit", "TabelaInexistente")
    assert api("POST", "/subjects", {"code": "A", "name": "B", "weeklyHours": 2})[0] == 201


def test_audit_can_be_filtered(api, catalog):
    status, items = query_audit(entity="subjects")
    assert status == 200 and [i["action"] for i in items] == ["CREATE"]
    status, items = query_audit(limit="1")
    assert len(items) == 1
    assert query_audit(limit="muitos")[0] == 400
