"""Ciclo de vida da grade: rascunho, validação, aprovação, devolução e edição."""

from conftest import allocation


def draft(api, catalog, days=("MON", "WED")):
    status, schedule = api("POST", "/schedules", {"term": "2026.2", "allocations": [
        allocation(catalog, day, "08:00", "10:00") for day in days
    ]})
    assert status == 201
    return schedule


def test_publish_requires_approval(api, catalog):
    schedule = draft(api, catalog)
    sid = schedule["scheduleId"]
    assert api("POST", f"/schedules/{sid}/publish")[0] == 409
    assert api("POST", f"/schedules/{sid}/approve")[0] == 409
    assert api("POST", f"/schedules/{sid}/submit")[1]["status"] == "IN_REVIEW"
    assert api("POST", f"/schedules/{sid}/publish")[0] == 409
    assert api("POST", f"/schedules/{sid}/approve")[1]["status"] == "APPROVED"
    status, published = api("POST", f"/schedules/{sid}/publish")
    assert status == 200 and published["status"] == "PUBLISHED"
    assert published["approvedBy"] == published["publishedBy"] == "coordenacao@classly.test"


def test_reject_returns_to_draft_with_reason(api, catalog):
    sid = draft(api, catalog)["scheduleId"]
    api("POST", f"/schedules/{sid}/submit")
    assert api("POST", f"/schedules/{sid}/reject", {})[0] == 400
    status, rejected = api("POST", f"/schedules/{sid}/reject", {"reason": "Trocar a aula de quarta"})
    assert status == 200 and rejected["status"] == "DRAFT"
    assert rejected["history"][-1] == {**rejected["history"][-1], "status": "DRAFT", "reason": "Trocar a aula de quarta"}


def test_draft_can_be_adjusted_but_not_after_submission(api, catalog):
    sid = draft(api, catalog)["scheduleId"]
    moved = [allocation(catalog, "TUE", "10:00", "12:00"), allocation(catalog, "THU", "10:00", "12:00")]
    status, updated = api("PUT", f"/schedules/{sid}", {"allocations": moved})
    assert status == 200 and {a["day"] for a in updated["allocations"]} == {"TUE", "THU"}

    conflicting = [allocation(catalog, "TUE", "10:00", "12:00")]
    assert api("PUT", f"/schedules/{sid}", {"allocations": conflicting})[0] == 422

    api("POST", f"/schedules/{sid}/submit")
    assert api("PUT", f"/schedules/{sid}", {"allocations": moved})[0] == 409


def test_submit_revalidates(api, catalog):
    sid = draft(api, catalog)["scheduleId"]
    api("PUT", f"/subjects/{catalog['subject']['subjectId']}",
        {"code": "ISN", "name": "Infraestrutura", "weeklyHours": 6})
    status, body = api("POST", f"/schedules/{sid}/submit")
    assert status == 422 and "Carga horária" in body["errors"][0]["reason"]


def test_only_coordination_moves_the_lifecycle(api, catalog):
    sid = draft(api, catalog)["scheduleId"]
    for action in ("submit", "approve", "reject", "publish", "notify"):
        assert api("POST", f"/schedules/{sid}/{action}", email="ana.souza@classly.test")[0] in (403, 404)
