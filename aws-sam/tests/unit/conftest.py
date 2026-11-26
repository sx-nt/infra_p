import boto3
import pytest
from moto import mock_aws

from support import COORDINATOR, TEACHER, call, create_tables
from shared import app


@pytest.fixture
def aws(monkeypatch):
    """DynamoDB e SES em memória (moto), recriados a cada teste."""
    monkeypatch.delenv("DYNAMODB_ENDPOINT", raising=False)
    with mock_aws():
        create_tables(boto3.resource("dynamodb", region_name="us-east-1"))
        yield


@pytest.fixture
def api(aws):
    """Atalho: api(método, rota, corpo, email) -> (status, json)."""
    return lambda method, path, body=None, email=COORDINATOR: call(app.handler, method, path, body, email)


@pytest.fixture
def catalog(api):
    """Professor habilitado, disciplina de 4h e turma do período 2026.2."""
    _, teacher = api("POST", "/teachers", {"name": "Ana Souza", "email": TEACHER})
    _, subject = api("POST", "/subjects", {"code": "ISN", "name": "Infraestrutura", "weeklyHours": 4})
    _, klass = api("POST", "/classes", {"code": "T1", "term": "2026.2", "subjectId": subject["subjectId"]})
    api("PUT", f"/teachers/{teacher['teacherId']}/subjects/{subject['subjectId']}", {"enabled": True})
    return {"teacher": teacher, "subject": subject, "class": klass}


def allocation(catalog, day, start, end):
    return {
        "classId": catalog["class"]["classId"],
        "teacherId": catalog["teacher"]["teacherId"],
        "subjectId": catalog["subject"]["subjectId"],
        "day": day,
        "start": start,
        "end": end,
    }
