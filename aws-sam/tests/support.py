"""Utilitários compartilhados pelos testes unitários e de integração."""

import json

TABLE_KEYS = {
    "TeachersTable": ["teacherId"],
    "SubjectsTable": ["subjectId"],
    "ClassesTable": ["classId"],
    "QualificationsTable": ["teacherId", "subjectId"],
    "AvailabilityTable": ["teacherId", "availabilityId"],
    "SchedulesTable": ["scheduleId"],
    "UsersTable": ["userId"],
    "AuditTable": ["auditId"],
}

COORDINATOR = "coordenacao@classly.test"
TEACHER = "ana.souza@classly.test"
STRANGER = "visitante@classly.test"


def create_tables(dynamodb):
    """Recria as tabelas vazias com o mesmo modelo do template SAM."""
    existing = {table.name for table in dynamodb.tables.all()}
    for name, keys in TABLE_KEYS.items():
        if name in existing:
            dynamodb.Table(name).delete()
            dynamodb.Table(name).wait_until_not_exists()
        dynamodb.create_table(
            TableName=name,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[{"AttributeName": k, "AttributeType": "S"} for k in keys],
            KeySchema=[{"AttributeName": k, "KeyType": t} for k, t in zip(keys, ["HASH", "RANGE"])],
        ).wait_until_exists()


def http_event(method, path, body=None, email=None):
    """Evento no formato do API Gateway HTTP API (payload 2.0) após o autorizador JWT."""
    event = {"rawPath": path, "requestContext": {"http": {"method": method}}}
    if email:
        event["requestContext"]["authorizer"] = {
            "jwt": {"claims": {"sub": f"sub-{email}", "email": email, "name": email.split("@")[0]}}
        }
    if body is not None:
        event["body"] = body if isinstance(body, str) else json.dumps(body)
    return event


def call(handler, method, path, body=None, email=None):
    response = handler(http_event(method, path, body, email), None)
    payload = json.loads(response["body"]) if response.get("body") else None
    return response["statusCode"], payload
