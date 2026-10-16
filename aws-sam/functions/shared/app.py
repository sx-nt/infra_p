"""Classly's first serverless API: academic data and schedule validation."""

import json
import os
import uuid
from datetime import datetime
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key


TABLES = {
    "teachers": os.environ.get("TEACHERS_TABLE", "TeachersTable"),
    "subjects": os.environ.get("SUBJECTS_TABLE", "SubjectsTable"),
    "classes": os.environ.get("CLASSES_TABLE", "ClassesTable"),
    "qualifications": os.environ.get("QUALIFICATIONS_TABLE", "QualificationsTable"),
    "availability": os.environ.get("AVAILABILITY_TABLE", "AvailabilityTable"),
    "schedules": os.environ.get("SCHEDULES_TABLE", "SchedulesTable"),
}

WEEKDAYS = {"MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"}


class DuplicateResourceError(Exception):
    pass


def _db():
    endpoint = os.environ.get("DYNAMODB_ENDPOINT") or None
    return boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"), endpoint_url=endpoint)


def _response(status, payload):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
        },
        "body": json.dumps(payload, ensure_ascii=False, default=_json_default),
    }


def _json_default(value):
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    raise TypeError(f"Tipo não serializável: {type(value).__name__}")


def _body(event):
    try:
        value = json.loads(event.get("body") or "{}")
    except (TypeError, json.JSONDecodeError):
        raise ValueError("O corpo da requisição precisa ser um JSON válido.")
    if not isinstance(value, dict):
        raise ValueError("O corpo da requisição precisa ser um objeto JSON.")
    return value


def _required(data, *fields):
    missing = [field for field in fields if data.get(field) in (None, "")]
    if missing:
        raise ValueError("Campos obrigatórios: " + ", ".join(missing))


def _items(table_name):
    return _db().Table(table_name).scan().get("Items", [])


def _get(table_name, key):
    return _db().Table(table_name).get_item(Key=key).get("Item")


def _create_entity(table_key, fields, data):
    _required(data, *fields)
    item = {key: data[key] for key in fields}
    item[table_key] = str(data.get(table_key) or uuid.uuid4())
    table = _db().Table(TABLES[{"teacherId": "teachers", "subjectId": "subjects", "classId": "classes"}[table_key]])
    try:
        table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(#id)",
            ExpressionAttributeNames={"#id": table_key},
        )
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        raise DuplicateResourceError(f"{table_key} já está cadastrado.")
    return item


def _parse_time(value, field):
    try:
        return datetime.strptime(value, "%H:%M")
    except (TypeError, ValueError):
        raise ValueError(f"{field} deve usar o formato HH:MM.")


def _interval(data):
    day = data.get("day")
    if day not in WEEKDAYS:
        raise ValueError("day deve ser um dia da semana (MON a SUN).")
    start = _parse_time(data.get("start"), "start")
    end = _parse_time(data.get("end"), "end")
    if start >= end:
        raise ValueError("end deve ser posterior a start.")
    return day, start, end


def _overlap(start_a, end_a, start_b, end_b):
    return start_a < end_b and start_b < end_a


def _validate_schedule(data):
    allocations = data.get("allocations")
    if not isinstance(allocations, list) or not allocations:
        raise ValueError("allocations precisa conter ao menos uma alocação.")

    errors = []
    prepared = []
    by_class = {}
    for index, allocation in enumerate(allocations):
        if not isinstance(allocation, dict):
            errors.append({"allocation": index, "reason": "A alocação precisa ser um objeto."})
            continue
        try:
            _required(allocation, "classId", "teacherId", "subjectId")
            day, start, end = _interval(allocation)
            hours = (end - start).total_seconds() / 3600
            prepared.append((index, allocation, day, start, end, hours))
            by_class[allocation["classId"]] = by_class.get(allocation["classId"], 0) + hours
        except ValueError as error:
            errors.append({"allocation": index, "reason": str(error)})

    db = _db()
    records = []
    teacher_slots = {}
    class_slots = {}
    for index, item, day, start, end, hours in prepared:
        teacher = _get(TABLES["teachers"], {"teacherId": item["teacherId"]})
        course = _get(TABLES["subjects"], {"subjectId": item["subjectId"]})
        classroom = _get(TABLES["classes"], {"classId": item["classId"]})
        if not teacher or not course or not classroom:
            errors.append({"allocation": index, "reason": "Professor, disciplina ou turma não encontrada."})
            continue
        if classroom.get("subjectId") != item["subjectId"]:
            errors.append({"allocation": index, "reason": "A disciplina não corresponde à turma informada."})
        if data.get("term") and classroom.get("term") != data["term"]:
            errors.append({"allocation": index, "reason": "A turma não pertence ao período informado para a grade."})
        qualification = _get(TABLES["qualifications"], {
            "teacherId": item["teacherId"], "subjectId": item["subjectId"]
        })
        if not qualification or not qualification.get("enabled", False):
            errors.append({"allocation": index, "reason": "O professor não está habilitado para esta disciplina."})

        for owner, slots, label in ((item["teacherId"], teacher_slots, "Professor"),
                                    (item["classId"], class_slots, "Turma")):
            for old_day, old_start, old_end in slots.get(owner, []):
                if old_day == day and _overlap(start, end, old_start, old_end):
                    errors.append({"allocation": index, "reason": f"Conflito de horário para {label.lower()} {owner}."})
            slots.setdefault(owner, []).append((day, start, end))

        blocked = db.Table(TABLES["availability"]).query(
            KeyConditionExpression=Key("teacherId").eq(item["teacherId"])
        ).get("Items", [])
        for restriction in blocked:
            if restriction.get("day") != day or restriction.get("type", "BLOCKED") != "BLOCKED":
                continue
            blocked_start = _parse_time(restriction.get("start"), "availability.start")
            blocked_end = _parse_time(restriction.get("end"), "availability.end")
            if _overlap(start, end, blocked_start, blocked_end):
                errors.append({"allocation": index, "reason": "O horário conflita com uma restrição do professor."})

        records.append({
            "allocationId": str(uuid.uuid4()), "classId": item["classId"],
            "teacherId": item["teacherId"], "subjectId": item["subjectId"],
            "day": day, "start": item["start"], "end": item["end"],
        })

    for class_id, allocated_hours in by_class.items():
        classroom = _get(TABLES["classes"], {"classId": class_id})
        if not classroom:
            continue
        subject = _get(TABLES["subjects"], {"subjectId": classroom.get("subjectId", "")})
        required_hours = (subject or {}).get("weeklyHours")
        if required_hours is not None and allocated_hours != float(required_hours):
            errors.append({
                "classId": class_id,
                "reason": f"Carga horária alocada ({allocated_hours:g}h) diferente da carga semanal exigida ({required_hours}h).",
            })
    return records, errors


def handler(event, context):
    method = event.get("httpMethod") or (event.get("requestContext", {}).get("http", {}).get("method")) or "GET"
    path = event.get("path") or event.get("rawPath", "/")
    parts = [part for part in path.strip("/").split("/") if part]
    try:
        if method == "OPTIONS":
            return _response(204, {})
        if method == "GET" and path == "/health":
            return _response(200, {"status": "ok", "service": "classly-api"})

        collection = {"teachers": ("teachers", ("name", "email")),
                      "subjects": ("subjects", ("code", "name", "weeklyHours")),
                      "classes": ("classes", ("code", "term", "subjectId"))}
        if len(parts) == 1 and parts[0] in collection:
            name, fields = collection[parts[0]]
            if method == "GET":
                return _response(200, _items(TABLES[name]))
            if method == "POST":
                data = _body(event)
                if name == "subjects":
                    hours = data.get("weeklyHours")
                    if not isinstance(hours, int) or isinstance(hours, bool) or hours <= 0:
                        raise ValueError("weeklyHours deve ser um número inteiro maior que zero.")
                if name == "classes" and not _get(TABLES["subjects"], {"subjectId": data.get("subjectId", "")}):
                    return _response(400, {"message": "subjectId precisa corresponder a uma disciplina cadastrada."})
                try:
                    item = _create_entity({"teachers": "teacherId", "subjects": "subjectId", "classes": "classId"}[name], fields, data)
                except DuplicateResourceError as error:
                    return _response(409, {"message": str(error)})
                return _response(201, item)

        if len(parts) == 2 and parts[0] in collection:
            name = collection[parts[0]][0]
            id_key = {"teachers": "teacherId", "subjects": "subjectId", "classes": "classId"}[name]
            table = _db().Table(TABLES[name])
            key = {id_key: parts[1]}
            existing = table.get_item(Key=key).get("Item")
            if method == "GET":
                return _response(200, existing) if existing else _response(404, {"message": "Registro não encontrado."})
            if method == "DELETE":
                if not existing:
                    return _response(404, {"message": "Registro não encontrado."})
                if name == "subjects" and any(c.get("subjectId") == parts[1] for c in _items(TABLES["classes"])):
                    return _response(409, {"message": "A disciplina está associada a uma turma."})
                table.delete_item(Key=key)
                return _response(204, {})
            if method == "PUT":
                if not existing:
                    return _response(404, {"message": "Registro não encontrado."})
                data = _body(event)
                fields = collection[parts[0]][1]
                _required(data, *fields)
                if name == "subjects" and (not isinstance(data["weeklyHours"], int) or isinstance(data["weeklyHours"], bool) or data["weeklyHours"] <= 0):
                    raise ValueError("weeklyHours deve ser um número inteiro maior que zero.")
                if name == "classes" and not _get(TABLES["subjects"], {"subjectId": data["subjectId"]}):
                    raise ValueError("subjectId precisa corresponder a uma disciplina cadastrada.")
                updated = {**{field: data[field] for field in fields}, id_key: parts[1]}
                table.put_item(Item=updated)
                return _response(200, updated)

        if len(parts) == 4 and parts[0] == "teachers" and parts[2] == "subjects":
            teacher_id, subject_id = parts[1], parts[3]
            if method in ("PUT", "DELETE"):
                if not _get(TABLES["teachers"], {"teacherId": teacher_id}) or not _get(TABLES["subjects"], {"subjectId": subject_id}):
                    return _response(404, {"message": "Professor ou disciplina não encontrado."})
                table = _db().Table(TABLES["qualifications"])
                if method == "DELETE":
                    table.delete_item(Key={"teacherId": teacher_id, "subjectId": subject_id})
                    return _response(204, {})
                data = _body(event)
                enabled = data.get("enabled", True)
                if not isinstance(enabled, bool):
                    raise ValueError("enabled deve ser booleano.")
                qualification = {"teacherId": teacher_id, "subjectId": subject_id, "enabled": enabled}
                table.put_item(Item=qualification)
                return _response(200, qualification)

        if len(parts) == 3 and parts[0] == "teachers" and parts[2] == "availability":
            teacher_id = parts[1]
            if not _get(TABLES["teachers"], {"teacherId": teacher_id}):
                return _response(404, {"message": "Professor não encontrado."})
            table = _db().Table(TABLES["availability"])
            if method == "GET":
                return _response(200, table.query(KeyConditionExpression=Key("teacherId").eq(teacher_id)).get("Items", []))
            if method == "PUT":
                data = _body(event)
                entries = data.get("availability")
                if not isinstance(entries, list):
                    raise ValueError("availability precisa ser uma lista.")
                normalized = []
                for entry in entries:
                    if not isinstance(entry, dict):
                        raise ValueError("Cada restrição precisa ser um objeto.")
                    day, start, end = _interval(entry)
                    kind = entry.get("type", "BLOCKED")
                    if kind not in ("BLOCKED", "AVAILABLE"):
                        raise ValueError("type deve ser BLOCKED ou AVAILABLE.")
                    normalized.append({
                        "teacherId": teacher_id, "availabilityId": str(uuid.uuid4()),
                        "day": day, "start": start.strftime("%H:%M"),
                        "end": end.strftime("%H:%M"), "type": kind,
                        "origin": entry.get("origin", "MANUAL"),
                        **({"externalEventId": entry["externalEventId"]} if entry.get("externalEventId") else {}),
                    })
                old = table.query(KeyConditionExpression=Key("teacherId").eq(teacher_id)).get("Items", [])
                with table.batch_writer() as batch:
                    for item in old:
                        batch.delete_item(Key={"teacherId": teacher_id, "availabilityId": item["availabilityId"]})
                    for item in normalized:
                        batch.put_item(Item=item)
                return _response(200, {"teacherId": teacher_id, "availability": normalized})

        if parts == ["schedules", "validate"] and method == "POST":
            allocations, errors = _validate_schedule(_body(event))
            return _response(200, {"valid": not errors, "allocations": allocations, "errors": errors})

        if parts == ["schedules"] and method == "POST":
            data = _body(event)
            _required(data, "term")
            allocations, errors = _validate_schedule(data)
            if errors:
                return _response(422, {"message": "A grade contém conflitos.", "errors": errors})
            schedule = {
                "scheduleId": str(uuid.uuid4()), "term": data["term"],
                "status": "DRAFT", "version": 1,
                "createdAt": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "allocations": allocations,
            }
            _db().Table(TABLES["schedules"]).put_item(Item=schedule)
            return _response(201, schedule)

        if len(parts) == 2 and parts[0] == "schedules" and method == "GET":
            schedule = _get(TABLES["schedules"], {"scheduleId": parts[1]})
            return _response(200, schedule) if schedule else _response(404, {"message": "Grade não encontrada."})

        return _response(404, {"message": "Rota não encontrada."})
    except ValueError as error:
        return _response(400, {"message": str(error)})
    except Exception as error:  # Keep API Gateway responses useful while Lambda logs retain the traceback.
        print(json.dumps({"event": "api_error", "path": path, "error": str(error)}))
        return _response(500, {"message": "Erro interno ao processar a solicitação."})
