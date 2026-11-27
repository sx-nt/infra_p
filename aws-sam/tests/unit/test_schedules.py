"""Validação, rascunho, publicação e notificação de grades."""

import boto3

from conftest import allocation
from shared import app
from support import TEACHER


def errors_of(api, body):
    status, result = api("POST", "/schedules/validate", body)
    assert status == 200
    return [e["reason"] for e in result["errors"]]


def test_valid_schedule_has_no_errors(api, catalog):
    body = {"term": "2026.2", "allocations": [
        allocation(catalog, "MON", "08:00", "10:00"),
        allocation(catalog, "WED", "08:00", "10:00"),
    ]}
    assert errors_of(api, body) == []


def test_weekly_hours_must_match_subject(api, catalog):
    reasons = errors_of(api, {"allocations": [allocation(catalog, "MON", "08:00", "10:00")]})
    assert any("Carga horária alocada (2h)" in r for r in reasons)


def test_teacher_cannot_be_in_two_places(api, catalog):
    reasons = errors_of(api, {"allocations": [
        allocation(catalog, "MON", "08:00", "10:00"),
        allocation(catalog, "MON", "09:00", "11:00"),
    ]})
    assert any("Conflito de horário para professor" in r for r in reasons)


def test_blocked_availability_is_respected(api, catalog):
    teacher_id = catalog["teacher"]["teacherId"]
    api("PUT", f"/teachers/{teacher_id}/availability",
        {"availability": [{"day": "TUE", "start": "07:00", "end": "12:00", "type": "BLOCKED"}]})
    reasons = errors_of(api, {"allocations": [
        allocation(catalog, "TUE", "08:00", "10:00"),
        allocation(catalog, "THU", "08:00", "10:00"),
    ]})
    assert reasons == ["O horário conflita com uma restrição do professor."]


def test_unqualified_teacher_and_wrong_term(api, catalog):
    path = f"/teachers/{catalog['teacher']['teacherId']}/subjects/{catalog['subject']['subjectId']}"
    api("PUT", path, {"enabled": False})
    reasons = errors_of(api, {"term": "2027.1", "allocations": [
        allocation(catalog, "MON", "08:00", "10:00"),
        allocation(catalog, "WED", "08:00", "10:00"),
    ]})
    assert "O professor não está habilitado para esta disciplina." in reasons
    assert "A turma não pertence ao período informado para a grade." in reasons


def test_invalid_schedule_is_not_saved(api, catalog):
    status, body = api("POST", "/schedules", {"term": "2026.2", "allocations": [
        allocation(catalog, "MON", "08:00", "10:00"),
    ]})
    assert status == 422 and body["errors"]
    assert api("GET", "/schedules")[1] == []


def approve(api, schedule_id):
    """Rascunho -> Em validação -> Aprovada."""
    assert api("POST", f"/schedules/{schedule_id}/submit")[1]["status"] == "IN_REVIEW"
    status, approved = api("POST", f"/schedules/{schedule_id}/approve")
    assert status == 200 and approved["status"] == "APPROVED"
    return approved


def publish(api, schedule_id):
    approve(api, schedule_id)
    return api("POST", f"/schedules/{schedule_id}/publish")


def save_draft(api, catalog, days=("MON", "WED")):
    status, schedule = api("POST", "/schedules", {"term": "2026.2", "allocations": [
        allocation(catalog, day, "08:00", "10:00") for day in days
    ]})
    assert status == 201
    return schedule


def test_publish_flow_versions_and_visibility(api, catalog):
    first = save_draft(api, catalog)
    assert first["status"] == "DRAFT" and first["version"] == 1
    assert api("GET", "/schedules", email=TEACHER)[1] == []
    assert api("GET", f"/schedules/{first['scheduleId']}", email=TEACHER)[0] == 404

    status, published = publish(api, first["scheduleId"])
    assert status == 200 and published["status"] == "PUBLISHED"
    assert [h["status"] for h in published["history"]] == ["DRAFT", "IN_REVIEW", "APPROVED", "PUBLISHED"]
    assert published["notification"]["skipped"]
    assert [s["scheduleId"] for s in api("GET", "/schedules", email=TEACHER)[1]] == [first["scheduleId"]]
    assert api("DELETE", f"/schedules/{first['scheduleId']}")[0] == 409
    assert api("PUT", f"/schedules/{first['scheduleId']}", {"allocations": []})[0] == 409
    assert api("POST", f"/schedules/{first['scheduleId']}/publish")[0] == 409

    second = save_draft(api, catalog, days=("TUE", "THU"))
    assert second["version"] == 2
    publish(api, second["scheduleId"])
    archived = api("GET", f"/schedules/{first['scheduleId']}")[1]
    assert archived["status"] == "ARCHIVED"
    assert archived["history"][-1]["status"] == "ARCHIVED"


def test_draft_can_be_deleted(api, catalog):
    draft = save_draft(api, catalog)
    assert api("DELETE", f"/schedules/{draft['scheduleId']}")[0] == 204
    assert api("GET", f"/schedules/{draft['scheduleId']}")[0] == 404


def test_publish_revalidates_changed_data(api, catalog):
    draft = save_draft(api, catalog)
    approve(api, draft["scheduleId"])
    path = f"/teachers/{catalog['teacher']['teacherId']}/subjects/{catalog['subject']['subjectId']}"
    api("PUT", path, {"enabled": False})
    status, body = api("POST", f"/schedules/{draft['scheduleId']}/publish")
    assert status == 422 and body["errors"]


def test_publication_email_lists_teacher_slots(api, catalog, monkeypatch):
    monkeypatch.setenv("SENDER_EMAIL", "noreply@classly.test")
    monkeypatch.setenv("APP_URL", "https://classly.test")
    boto3.client("ses", region_name="us-east-1").verify_email_identity(EmailAddress="noreply@classly.test")
    sent = []
    real_client = boto3.client

    def spy(name, **kwargs):
        client = real_client(name, **kwargs)
        if name == "sesv2":
            original = client.send_email
            client.send_email = lambda **kw: sent.append(kw) or original(**kw)
        return client

    monkeypatch.setattr(app.boto3, "client", spy)
    draft = save_draft(api, catalog)
    _, published = publish(api, draft["scheduleId"])

    assert published["notification"] == {"sent": 1, "failed": []}
    assert sent[0]["Destination"]["ToAddresses"] == [TEACHER]
    text = sent[0]["Content"]["Simple"]["Body"]["Text"]["Data"]
    assert "Segunda 08:00–10:00: Infraestrutura (turma T1)" in text
    assert "https://classly.test" in text


def test_email_failure_is_reported_not_raised(api, catalog, monkeypatch):
    # Remetente não verificado: o SES recusa, mas a grade é publicada.
    monkeypatch.setenv("SENDER_EMAIL", "nao-verificado@classly.test")
    draft = save_draft(api, catalog)
    status, published = publish(api, draft["scheduleId"])
    assert status == 200 and published["status"] == "PUBLISHED"
    assert published["notification"]["sent"] == 0
    assert published["notification"]["failed"][0]["teacherId"] == catalog["teacher"]["teacherId"]

    # Depois de verificar o remetente, a coordenação reenvia só o que falhou.
    boto3.client("ses", region_name="us-east-1").verify_email_identity(EmailAddress="nao-verificado@classly.test")
    status, resent = api("POST", f"/schedules/{draft['scheduleId']}/notify")
    assert status == 200
    assert resent["notification"]["sent"] == 1 and resent["notification"]["failed"] == []
    assert api("POST", f"/schedules/{draft['scheduleId']}/notify")[0] == 409
