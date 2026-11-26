"""Fluxo completo de um período letivo contra o DynamoDB Local.

Cada requisição é entregue à Lambda que o template SAM associa à rota,
como faz o API Gateway, e os dados passam pelo DynamoDB real (Local).
"""

from conftest import ROUTES
from support import COORDINATOR, STRANGER, TEACHER


def test_every_function_route_is_reachable():
    handlers = {handler.__module__ for _, _, handler in ROUTES}
    assert handlers == {
        "teachers.handler", "subjects.handler", "classes.handler", "qualifications.handler",
        "availability.handler", "schedules.handler", "users.handler", "health.handler",
    }


def test_complete_term_from_registration_to_publication(api):
    # Coordenação entra pela primeira vez e recebe o perfil pelo ADMIN_EMAILS.
    assert api("GET", "/me")[1]["role"] == "COORDINATOR"

    # Cadastros.
    _, ana = api("POST", "/teachers", {"name": "Ana Souza", "email": TEACHER})
    _, bruno = api("POST", "/teachers", {"name": "Bruno Lima", "email": "bruno@classly.test"})
    _, infra = api("POST", "/subjects", {"code": "ISN", "name": "Infraestrutura", "weeklyHours": 4})
    _, redes = api("POST", "/subjects", {"code": "RED", "name": "Redes", "weeklyHours": 2})
    _, t_infra = api("POST", "/classes", {"code": "ADS-5", "term": "2026.2", "subjectId": infra["subjectId"]})
    _, t_redes = api("POST", "/classes", {"code": "ADS-3", "term": "2026.2", "subjectId": redes["subjectId"]})
    for teacher, subject in ((ana, infra), (bruno, redes), (ana, redes)):
        status, _ = api("PUT", f"/teachers/{teacher['teacherId']}/subjects/{subject['subjectId']}", {"enabled": True})
        assert status == 200
    assert len(api("GET", "/qualifications")[1]) == 3

    # A professora entra com o e-mail cadastrado e informa um bloqueio.
    _, me = api("GET", "/me", email=TEACHER)
    assert me["role"] == "TEACHER" and me["teacherId"] == ana["teacherId"]
    status, _ = api("PUT", f"/teachers/{ana['teacherId']}/availability",
                    {"availability": [{"day": "FRI", "start": "07:00", "end": "12:00"}]}, email=TEACHER)
    assert status == 200

    # Uma grade que viola o bloqueio é recusada.
    def alloc(klass, teacher, subject, day, start, end):
        return {"classId": klass["classId"], "teacherId": teacher["teacherId"],
                "subjectId": subject["subjectId"], "day": day, "start": start, "end": end}

    conflicting = [
        alloc(t_infra, ana, infra, "MON", "08:00", "10:00"),
        alloc(t_infra, ana, infra, "FRI", "08:00", "10:00"),
        alloc(t_redes, bruno, redes, "MON", "08:00", "10:00"),
    ]
    status, body = api("POST", "/schedules", {"term": "2026.2", "allocations": conflicting})
    assert status == 422
    assert [e["reason"] for e in body["errors"]] == ["O horário conflita com uma restrição do professor."]

    # Ajustada, a grade é salva como rascunho e publicada.
    conflicting[1]["day"] = "WED"
    status, draft = api("POST", "/schedules", {"term": "2026.2", "allocations": conflicting})
    assert status == 201 and draft["version"] == 1
    status, published = api("POST", f"/schedules/{draft['scheduleId']}/publish")
    assert status == 200 and published["status"] == "PUBLISHED"

    # Professores enxergam a grade publicada; quem não foi liberado, não.
    _, visible = api("GET", "/schedules", email=TEACHER)
    assert [s["scheduleId"] for s in visible] == [draft["scheduleId"]]
    assert len(visible[0]["allocations"]) == 3
    assert api("GET", "/schedules", email=STRANGER)[0] == 403

    # A coordenação libera o visitante e ele passa a enxergar a grade.
    pending = [u for u in api("GET", "/users")[1] if u["email"] == STRANGER][0]
    api("PUT", f"/users/{pending['userId']}/role", {"role": "TEACHER"})
    assert api("GET", "/schedules", email=STRANGER)[0] == 200


def test_routes_not_in_template_return_404(api):
    assert api("GET", "/admin")[0] == 404
    assert api("DELETE", "/teachers")[0] == 404


def test_health_is_public(api):
    assert api("GET", "/health", email=None) == (200, {"status": "ok", "service": "classly-api"})


def test_users_are_persisted_between_requests(api):
    api("GET", "/me", email=TEACHER)
    api("GET", "/me", email=TEACHER)
    users = api("GET", "/users", email=COORDINATOR)[1]
    assert sorted(u["email"] for u in users) == sorted([COORDINATOR, TEACHER])
