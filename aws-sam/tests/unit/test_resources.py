"""Cadastros de professores, disciplinas, turmas e habilitações."""


def test_crud_teacher(api):
    status, teacher = api("POST", "/teachers", {"name": "Ana", "email": "ANA@classly.test"})
    assert status == 201 and teacher["email"] == "ana@classly.test"
    path = f"/teachers/{teacher['teacherId']}"
    assert api("GET", path)[1]["name"] == "Ana"
    assert api("PUT", path, {"name": "Ana Souza", "email": "ana@classly.test"})[1]["name"] == "Ana Souza"
    assert api("DELETE", path)[0] == 204
    assert api("GET", path)[0] == 404


def test_duplicate_id_returns_409(api):
    body = {"teacherId": "t1", "name": "Ana", "email": "ana@classly.test"}
    assert api("POST", "/teachers", body)[0] == 201
    assert api("POST", "/teachers", body)[0] == 409


def test_missing_fields_return_400(api):
    status, body = api("POST", "/subjects", {"name": "Sem código"})
    assert status == 400
    assert "code" in body["message"]


def test_class_requires_existing_subject(api):
    assert api("POST", "/classes", {"code": "T1", "term": "2026.2", "subjectId": "nao-existe"})[0] == 400


def test_subject_with_class_cannot_be_deleted(api, catalog):
    status, _ = api("DELETE", f"/subjects/{catalog['subject']['subjectId']}")
    assert status == 409


def test_qualifications_are_listed_and_removed(api, catalog):
    _, items = api("GET", "/qualifications")
    assert len(items) == 1 and items[0]["enabled"] is True
    path = f"/teachers/{catalog['teacher']['teacherId']}/subjects/{catalog['subject']['subjectId']}"
    assert api("PUT", path, {"enabled": "sim"})[0] == 400
    assert api("DELETE", path)[0] == 204
    assert api("GET", "/qualifications")[1] == []


def test_options_and_unknown_routes(api):
    assert api("OPTIONS", "/teachers", email=None)[0] == 204
    assert api("GET", "/nada")[0] == 404
    assert api("POST", "/teachers", "{quebrado")[0] == 400
