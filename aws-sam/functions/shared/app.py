"""API serverless do Classly: dados acadêmicos, usuários, validação e publicação de grades."""

import json
import os
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError


TABLES = {
    "teachers": os.environ.get("TEACHERS_TABLE", "TeachersTable"),
    "subjects": os.environ.get("SUBJECTS_TABLE", "SubjectsTable"),
    "classes": os.environ.get("CLASSES_TABLE", "ClassesTable"),
    "qualifications": os.environ.get("QUALIFICATIONS_TABLE", "QualificationsTable"),
    "availability": os.environ.get("AVAILABILITY_TABLE", "AvailabilityTable"),
    "schedules": os.environ.get("SCHEDULES_TABLE", "SchedulesTable"),
    "users": os.environ.get("USERS_TABLE", "UsersTable"),
}

WEEKDAYS = {"MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"}
WEEKDAY_ORDER = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
WEEKDAY_NAMES = {
    "MON": "Segunda", "TUE": "Terça", "WED": "Quarta", "THU": "Quinta",
    "FRI": "Sexta", "SAT": "Sábado", "SUN": "Domingo",
}
ROLES = ("COORDINATOR", "TEACHER", "PENDING")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class DuplicateResourceError(Exception):
    pass


class Unauthorized(Exception):
    pass


class Forbidden(Exception):
    pass


def _db():
    endpoint = os.environ.get("DYNAMODB_ENDPOINT") or None
    return boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"), endpoint_url=endpoint)


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _response(status, payload=None):
    response = {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
        },
    }
    if payload is not None:
        response["body"] = json.dumps(payload, ensure_ascii=False, default=_json_default)
    return response


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


def _items(table_name, **scan_kwargs):
    table = _db().Table(table_name)
    response = table.scan(**scan_kwargs)
    items = response.get("Items", [])
    while "LastEvaluatedKey" in response:
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"], **scan_kwargs)
        items.extend(response.get("Items", []))
    return items


def _get(table_name, key):
    return _db().Table(table_name).get_item(Key=key).get("Item")


def _normalize(name, data):
    """Normaliza campos antes de gravar professores, disciplinas e turmas."""
    if name == "teachers":
        email = str(data.get("email", "")).strip().lower()
        if not EMAIL_RE.match(email):
            raise ValueError("email inválido.")
        data["email"] = email
    if name == "subjects":
        hours = data.get("weeklyHours")
        if not isinstance(hours, int) or isinstance(hours, bool) or hours <= 0:
            raise ValueError("weeklyHours deve ser um número inteiro maior que zero.")
    if name == "classes" and not _get(TABLES["subjects"], {"subjectId": data.get("subjectId", "")}):
        raise ValueError("subjectId precisa corresponder a uma disciplina cadastrada.")


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
            "allocationId": item.get("allocationId") or str(uuid.uuid4()), "classId": item["classId"],
            "teacherId": item["teacherId"], "subjectId": item["subjectId"],
            "day": day, "start": start.strftime("%H:%M"), "end": end.strftime("%H:%M"),
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


# --- Usuários e perfis ---

def _claims(event):
    """Claims do token validado pelo autorizador JWT do API Gateway.

    No SAM local não há autorizador; LOCAL_DEV_USER (env.json) identifica o
    usuário de desenvolvimento. Essa variável não existe na nuvem.
    """
    authorizer = (event.get("requestContext") or {}).get("authorizer") or {}
    claims = (authorizer.get("jwt") or {}).get("claims") or authorizer.get("claims")
    if claims and claims.get("sub"):
        return claims
    local_user = os.environ.get("LOCAL_DEV_USER")
    if local_user:
        return {"sub": f"local-{local_user}", "email": local_user, "name": local_user}
    raise Unauthorized()


def _admin_emails():
    return {e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()}


def _teacher_by_email(email):
    if not email:
        return None
    matches = _items(TABLES["teachers"], FilterExpression=Attr("email").eq(email))
    return matches[0] if matches else None


def _current_user(event):
    """Obtém (ou cria no primeiro acesso) o registro do usuário autenticado.

    Perfis: e-mails em ADMIN_EMAILS são coordenadores; e-mails cadastrados
    como professor viram TEACHER; os demais ficam PENDING até a coordenação
    liberar o acesso.
    """
    claims = _claims(event)
    email = str(claims.get("email", "")).lower()
    table = _db().Table(TABLES["users"])
    user = table.get_item(Key={"userId": claims["sub"]}).get("Item")
    teacher = _teacher_by_email(email)
    original = dict(user) if user else None

    if not user:
        user = {
            "userId": claims["sub"], "email": email,
            "name": claims.get("name") or email, "role": "PENDING", "createdAt": _now(),
        }
    if email in _admin_emails():
        user["role"] = "COORDINATOR"
    elif user["role"] == "PENDING" and teacher:
        user["role"] = "TEACHER"
    if teacher:
        user["teacherId"] = teacher["teacherId"]
    else:
        user.pop("teacherId", None)

    if user != original:
        table.put_item(Item=user)
    return user


def _require(user, *roles):
    if user["role"] not in roles:
        raise Forbidden()


# --- Notificações ---

def _notify_publication(schedule):
    """Envia a cada professor da grade publicada seus horários (Amazon SES)."""
    sender = os.environ.get("SENDER_EMAIL")
    if not sender:
        return {"sent": 0, "failed": [], "skipped": "Remetente de e-mail não configurado."}

    subjects = {s["subjectId"]: s for s in _items(TABLES["subjects"])}
    classes = {c["classId"]: c for c in _items(TABLES["classes"])}
    by_teacher = {}
    for allocation in schedule["allocations"]:
        by_teacher.setdefault(allocation["teacherId"], []).append(allocation)

    ses = boto3.client("sesv2")
    app_url = os.environ.get("APP_URL", "")
    sent, failed = 0, []
    for teacher_id, allocations in by_teacher.items():
        teacher = _get(TABLES["teachers"], {"teacherId": teacher_id})
        if not teacher or not teacher.get("email"):
            failed.append({"teacherId": teacher_id, "reason": "Professor sem e-mail cadastrado."})
            continue
        allocations.sort(key=lambda a: (WEEKDAY_ORDER.index(a["day"]), a["start"]))
        lines = [
            f"- {WEEKDAY_NAMES[a['day']]} {a['start']}–{a['end']}: "
            f"{subjects.get(a['subjectId'], {}).get('name', a['subjectId'])} "
            f"(turma {classes.get(a['classId'], {}).get('code', a['classId'])})"
            for a in allocations
        ]
        text = (
            f"Olá, {teacher.get('name', '')}.\n\n"
            f"A grade de horários do período {schedule['term']} foi publicada. Seus horários:\n\n"
            + "\n".join(lines)
            + (f"\n\nConsulte a grade completa em {app_url}" if app_url else "")
            + "\n\nClassly"
        )
        try:
            ses.send_email(
                FromEmailAddress=sender,
                Destination={"ToAddresses": [teacher["email"]]},
                Content={"Simple": {
                    "Subject": {"Data": f"Grade {schedule['term']} publicada", "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": text, "Charset": "UTF-8"}},
                }},
            )
            sent += 1
        except ClientError as error:
            print(json.dumps({"event": "notification_error", "teacherId": teacher_id, "error": str(error)}))
            failed.append({"teacherId": teacher_id, "reason": error.response["Error"].get("Message", "Falha no envio.")})
    return {"sent": sent, "failed": failed}


# --- Roteamento ---

COLLECTIONS = {
    "teachers": ("teacherId", ("name", "email")),
    "subjects": ("subjectId", ("code", "name", "weeklyHours")),
    "classes": ("classId", ("code", "term", "subjectId")),
}


def _route(event, method, parts):
    if method == "GET" and parts == ["health"]:
        return _response(200, {"status": "ok", "service": "classly-api"})

    user = _current_user(event)

    if parts == ["me"] and method == "GET":
        return _response(200, user)

    if parts == ["users"] and method == "GET":
        _require(user, "COORDINATOR")
        return _response(200, sorted(_items(TABLES["users"]), key=lambda u: u.get("email", "")))

    if len(parts) == 3 and parts[0] == "users" and parts[2] == "role" and method == "PUT":
        _require(user, "COORDINATOR")
        role = _body(event).get("role")
        if role not in ROLES:
            raise ValueError("role deve ser COORDINATOR, TEACHER ou PENDING.")
        if parts[1] == user["userId"] and role != "COORDINATOR":
            raise ValueError("Não é possível remover o próprio perfil de coordenação.")
        table = _db().Table(TABLES["users"])
        target = table.get_item(Key={"userId": parts[1]}).get("Item")
        if not target:
            return _response(404, {"message": "Usuário não encontrado."})
        target["role"] = role
        table.put_item(Item=target)
        return _response(200, target)

    if user["role"] == "PENDING":
        raise Forbidden()

    if len(parts) == 1 and parts[0] in COLLECTIONS:
        id_key, fields = COLLECTIONS[parts[0]]
        if method == "GET":
            return _response(200, _items(TABLES[parts[0]]))
        if method == "POST":
            _require(user, "COORDINATOR")
            data = _body(event)
            _required(data, *fields)
            _normalize(parts[0], data)
            try:
                item = _create_entity(id_key, fields, data)
            except DuplicateResourceError as error:
                return _response(409, {"message": str(error)})
            return _response(201, item)

    if len(parts) == 2 and parts[0] in COLLECTIONS:
        name = parts[0]
        id_key, fields = COLLECTIONS[name]
        table = _db().Table(TABLES[name])
        key = {id_key: parts[1]}
        existing = table.get_item(Key=key).get("Item")
        if method == "GET":
            return _response(200, existing) if existing else _response(404, {"message": "Registro não encontrado."})
        _require(user, "COORDINATOR")
        if not existing:
            return _response(404, {"message": "Registro não encontrado."})
        if method == "DELETE":
            if name == "subjects" and _items(TABLES["classes"], FilterExpression=Attr("subjectId").eq(parts[1])):
                return _response(409, {"message": "A disciplina está associada a uma turma."})
            table.delete_item(Key=key)
            return _response(204)
        if method == "PUT":
            data = _body(event)
            _required(data, *fields)
            _normalize(name, data)
            updated = {**{field: data[field] for field in fields}, id_key: parts[1]}
            table.put_item(Item=updated)
            return _response(200, updated)

    if parts == ["qualifications"] and method == "GET":
        return _response(200, _items(TABLES["qualifications"]))

    if len(parts) == 4 and parts[0] == "teachers" and parts[2] == "subjects":
        teacher_id, subject_id = parts[1], parts[3]
        if method in ("PUT", "DELETE"):
            _require(user, "COORDINATOR")
            if not _get(TABLES["teachers"], {"teacherId": teacher_id}) or not _get(TABLES["subjects"], {"subjectId": subject_id}):
                return _response(404, {"message": "Professor ou disciplina não encontrado."})
            table = _db().Table(TABLES["qualifications"])
            if method == "DELETE":
                table.delete_item(Key={"teacherId": teacher_id, "subjectId": subject_id})
                return _response(204)
            data = _body(event)
            enabled = data.get("enabled", True)
            if not isinstance(enabled, bool):
                raise ValueError("enabled deve ser booleano.")
            qualification = {"teacherId": teacher_id, "subjectId": subject_id, "enabled": enabled}
            table.put_item(Item=qualification)
            return _response(200, qualification)

    if len(parts) == 3 and parts[0] == "teachers" and parts[2] == "availability":
        teacher_id = parts[1]
        # O professor gerencia a própria disponibilidade; a coordenação, a de todos.
        if user["role"] != "COORDINATOR" and user.get("teacherId") != teacher_id:
            raise Forbidden()
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

    if parts == ["schedules"] and method == "GET":
        if user["role"] == "COORDINATOR":
            schedules = _items(TABLES["schedules"])
        else:
            schedules = _items(TABLES["schedules"], FilterExpression=Attr("status").eq("PUBLISHED"))
        return _response(200, sorted(schedules, key=lambda s: s.get("createdAt", ""), reverse=True))

    if parts == ["schedules", "validate"] and method == "POST":
        _require(user, "COORDINATOR")
        allocations, errors = _validate_schedule(_body(event))
        return _response(200, {"valid": not errors, "allocations": allocations, "errors": errors})

    if parts == ["schedules"] and method == "POST":
        _require(user, "COORDINATOR")
        data = _body(event)
        _required(data, "term")
        allocations, errors = _validate_schedule(data)
        if errors:
            return _response(422, {"message": "A grade contém conflitos.", "errors": errors})
        versions = _items(TABLES["schedules"], FilterExpression=Attr("term").eq(data["term"]))
        schedule = {
            "scheduleId": str(uuid.uuid4()), "term": data["term"],
            "status": "DRAFT", "version": max([int(s.get("version", 0)) for s in versions] + [0]) + 1,
            "createdAt": _now(), "createdBy": user["email"],
            "allocations": allocations,
        }
        _db().Table(TABLES["schedules"]).put_item(Item=schedule)
        return _response(201, schedule)

    if len(parts) == 2 and parts[0] == "schedules":
        table = _db().Table(TABLES["schedules"])
        schedule = table.get_item(Key={"scheduleId": parts[1]}).get("Item")
        visible = schedule and (user["role"] == "COORDINATOR" or schedule.get("status") == "PUBLISHED")
        if not visible:
            return _response(404, {"message": "Grade não encontrada."})
        if method == "GET":
            return _response(200, schedule)
        if method == "DELETE":
            _require(user, "COORDINATOR")
            if schedule["status"] != "DRAFT":
                return _response(409, {"message": "Somente rascunhos podem ser excluídos."})
            table.delete_item(Key={"scheduleId": parts[1]})
            return _response(204)

    if len(parts) == 3 and parts[0] == "schedules" and parts[2] == "publish" and method == "POST":
        _require(user, "COORDINATOR")
        table = _db().Table(TABLES["schedules"])
        schedule = table.get_item(Key={"scheduleId": parts[1]}).get("Item")
        if not schedule:
            return _response(404, {"message": "Grade não encontrada."})
        if schedule["status"] != "DRAFT":
            return _response(409, {"message": "Somente rascunhos podem ser publicados."})
        # RN07: os dados podem ter mudado desde o rascunho; valida novamente.
        _, errors = _validate_schedule({"term": schedule["term"], "allocations": schedule["allocations"]})
        if errors:
            return _response(422, {"message": "A grade contém conflitos.", "errors": errors})
        for previous in _items(TABLES["schedules"], FilterExpression=Attr("term").eq(schedule["term"]) & Attr("status").eq("PUBLISHED")):
            previous["status"] = "ARCHIVED"
            table.put_item(Item=previous)
        schedule.update({"status": "PUBLISHED", "publishedAt": _now(), "publishedBy": user["email"]})
        schedule["notification"] = _notify_publication(schedule)
        table.put_item(Item=schedule)
        return _response(200, schedule)

    return _response(404, {"message": "Rota não encontrada."})


def handler(event, context):
    method = event.get("httpMethod") or (event.get("requestContext", {}).get("http", {}).get("method")) or "GET"
    path = event.get("path") or event.get("rawPath", "/")
    parts = [part for part in path.strip("/").split("/") if part]
    try:
        if method == "OPTIONS":
            return _response(204)
        return _route(event, method, parts)
    except ValueError as error:
        return _response(400, {"message": str(error)})
    except Unauthorized:
        return _response(401, {"message": "Autenticação necessária."})
    except Forbidden:
        return _response(403, {"message": "Seu perfil não tem permissão para esta operação."})
    except Exception as error:  # Keep API Gateway responses useful while Lambda logs retain the traceback.
        print(json.dumps({"event": "api_error", "path": path, "error": str(error)}))
        return _response(500, {"message": "Erro interno ao processar a solicitação."})
