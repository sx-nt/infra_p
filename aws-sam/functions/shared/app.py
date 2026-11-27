"""API serverless do Classly: dados acadêmicos, usuários, auditoria e ciclo de vida das grades."""

import json
import os
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr, Key
from botocore.exceptions import ClientError

from shared import generator, google_calendar


TABLES = {
    "teachers": os.environ.get("TEACHERS_TABLE", "TeachersTable"),
    "subjects": os.environ.get("SUBJECTS_TABLE", "SubjectsTable"),
    "classes": os.environ.get("CLASSES_TABLE", "ClassesTable"),
    "qualifications": os.environ.get("QUALIFICATIONS_TABLE", "QualificationsTable"),
    "availability": os.environ.get("AVAILABILITY_TABLE", "AvailabilityTable"),
    "schedules": os.environ.get("SCHEDULES_TABLE", "SchedulesTable"),
    "users": os.environ.get("USERS_TABLE", "UsersTable"),
    "audit": os.environ.get("AUDIT_TABLE", "AuditTable"),
}

WEEKDAYS = {"MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"}
WEEKDAY_ORDER = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
WEEKDAY_NAMES = {
    "MON": "Segunda", "TUE": "Terça", "WED": "Quarta", "THU": "Quinta",
    "FRI": "Sexta", "SAT": "Sábado", "SUN": "Domingo",
}
ROLES = ("COORDINATOR", "TEACHER", "PENDING")
# Ciclo de vida: Rascunho -> Em validação -> Aprovada -> Publicada (-> Arquivada).
STATUS_NAMES = {
    "DRAFT": "Rascunho", "IN_REVIEW": "Em validação", "APPROVED": "Aprovada",
    "PUBLISHED": "Publicada", "ARCHIVED": "Arquivada",
}
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
        if original is None:
            _audit(user, "USER_CREATED", "user", user["userId"], {"role": user["role"]})
        elif original.get("role") != user["role"]:
            _audit(user, "ROLE_ASSIGNED", "user", user["userId"], {"from": original.get("role"), "to": user["role"]})
    return user


def _require(user, *roles):
    if user["role"] not in roles:
        raise Forbidden()


# --- Auditoria ---

def _audit(user, action, entity, entity_id, details=None):
    """Registra uma operação crítica. Falhas no registro nunca desfazem a operação."""
    now = datetime.now(timezone.utc)
    item = {
        # Microssegundos no identificador mantêm a ordem de operações no mesmo segundo.
        "auditId": f"{now.strftime('%Y-%m-%dT%H:%M:%S.%fZ')}#{uuid.uuid4().hex[:8]}",
        "at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "userId": (user or {}).get("userId", "system"), "email": (user or {}).get("email", "system"),
        "action": action, "entity": entity, "entityId": str(entity_id),
    }
    if details:
        item["details"] = details
    try:
        _db().Table(TABLES["audit"]).put_item(Item=item)
    except Exception as error:  # noqa: BLE001 - a auditoria não pode derrubar a requisição
        print(json.dumps({"event": "audit_error", "action": action, "error": str(error)}))
    print(json.dumps({"event": "audit", **item}, default=str))
    return item


def _audit_list(event):
    params = event.get("queryStringParameters") or {}
    items = _items(TABLES["audit"])
    for field in ("entity", "action", "email"):
        if params.get(field):
            items = [i for i in items if i.get(field) == params[field]]
    items.sort(key=lambda i: i["auditId"], reverse=True)
    try:
        limit = max(1, min(int(params.get("limit", 200)), 1000))
    except ValueError:
        raise ValueError("limit deve ser um número inteiro.")
    return items[:limit]


# --- Notificações ---

def _notify(schedule, teacher_ids=None):
    """Envia a cada professor da grade publicada seus horários (Amazon SES)."""
    sender = os.environ.get("SENDER_EMAIL")
    if not sender:
        return {"sent": 0, "failed": [], "skipped": "Remetente de e-mail não configurado."}

    subjects = {s["subjectId"]: s for s in _items(TABLES["subjects"])}
    classes = {c["classId"]: c for c in _items(TABLES["classes"])}
    by_teacher = {}
    for allocation in schedule["allocations"]:
        if teacher_ids is None or allocation["teacherId"] in teacher_ids:
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


# --- Grades ---

def _schedule_or_404(schedule_id, user):
    schedule = _get(TABLES["schedules"], {"scheduleId": schedule_id})
    visible = schedule and (user["role"] == "COORDINATOR" or schedule.get("status") == "PUBLISHED")
    return schedule if visible else None


def _transition(schedule, user, status, **fields):
    """Muda o estado da grade registrando histórico e auditoria."""
    entry = {"status": status, "at": _now(), "by": user["email"]}
    if fields.get("reason"):
        entry["reason"] = fields["reason"]
    previous = schedule["status"]
    schedule["status"] = status
    schedule.setdefault("history", []).append(entry)
    _audit(user, f"SCHEDULE_{status}", "schedule", schedule["scheduleId"],
           {"term": schedule["term"], "version": schedule.get("version"), "from": previous, **fields})


def _conflicts(schedule):
    _, errors = _validate_schedule({"term": schedule["term"], "allocations": schedule["allocations"]})
    return errors


def _schedule_action(event, user, schedule, action):
    """Ações do ciclo de vida: submit, approve, reject, publish e notify."""
    table = _db().Table(TABLES["schedules"])
    expected = {"submit": ("DRAFT",), "approve": ("IN_REVIEW",), "reject": ("IN_REVIEW", "APPROVED"),
                "publish": ("APPROVED",), "notify": ("PUBLISHED",)}[action]
    if schedule["status"] not in expected:
        allowed = " ou ".join(STATUS_NAMES[s] for s in expected)
        return _response(409, {"message": f"Esta ação exige uma grade em: {allowed}."})

    # Os dados podem ter mudado desde o rascunho: toda etapa de avanço revalida.
    if action in ("submit", "approve", "publish"):
        errors = _conflicts(schedule)
        if errors:
            return _response(422, {"message": "A grade contém conflitos.", "errors": errors})

    if action == "submit":
        _transition(schedule, user, "IN_REVIEW")
    elif action == "approve":
        schedule.update({"approvedAt": _now(), "approvedBy": user["email"]})
        _transition(schedule, user, "APPROVED")
    elif action == "reject":
        reason = str(_body(event).get("reason", "")).strip()
        if not reason:
            raise ValueError("Informe o motivo da devolução (reason).")
        _transition(schedule, user, "DRAFT", reason=reason)
    elif action == "publish":
        previous = _items(TABLES["schedules"], FilterExpression=Attr("term").eq(schedule["term"]) & Attr("status").eq("PUBLISHED"))
        for old in previous:
            _transition(old, user, "ARCHIVED", replacedBy=schedule["scheduleId"])
            table.put_item(Item=old)
        schedule.update({"publishedAt": _now(), "publishedBy": user["email"]})
        _transition(schedule, user, "PUBLISHED")
        schedule["notification"] = _notify(schedule)
        _audit(user, "NOTIFICATION_SENT", "schedule", schedule["scheduleId"], schedule["notification"])
    elif action == "notify":
        # Reenvia aos professores que falharam (ou a todos com {"all": true}).
        resend_all = _body(event).get("all") is True
        previous = schedule.get("notification") or {"sent": 0, "failed": []}
        targets = None if resend_all else {f["teacherId"] for f in previous.get("failed", [])}
        if targets == set():
            return _response(409, {"message": "Não há envios com falha para reenviar."})
        result = _notify(schedule, targets)
        schedule["notification"] = {
            "sent": (0 if resend_all else int(previous.get("sent", 0))) + result["sent"],
            "failed": result["failed"], "lastAttemptAt": _now(),
            **({"skipped": result["skipped"]} if result.get("skipped") else {}),
        }
        _audit(user, "NOTIFICATION_RESENT", "schedule", schedule["scheduleId"], result)

    table.put_item(Item=schedule)
    return _response(200, schedule)


def _generate(data):
    term = data.get("term")
    if not term:
        raise ValueError("Campos obrigatórios: term")
    classes = _items(TABLES["classes"], FilterExpression=Attr("term").eq(term))
    if not classes:
        raise ValueError(f"Não há turmas cadastradas para o período {term}.")
    teachers = {t["teacherId"]: t for t in _items(TABLES["teachers"])}
    subjects = {s["subjectId"]: s for s in _items(TABLES["subjects"])}
    availability = {}
    for entry in _items(TABLES["availability"]):
        availability.setdefault(entry["teacherId"], []).append(entry)
    days = data.get("days")
    if days is not None and (not isinstance(days, list) or not set(days) <= WEEKDAYS or not days):
        raise ValueError("days deve ser uma lista de dias (MON a SUN).")
    slots = data.get("slots")
    if slots is not None:
        if not isinstance(slots, list) or not slots:
            raise ValueError("slots deve ser uma lista de {start, end}.")
        parsed = []
        for slot in slots:
            _, start, end = _interval({"day": "MON", **slot})
            parsed.append((start.strftime("%H:%M"), end.strftime("%H:%M")))
        slots = parsed
    allocations, unresolved = generator.generate(
        classes, subjects, teachers, _items(TABLES["qualifications"]), availability, days, slots,
    )
    _, errors = _validate_schedule({"term": term, "allocations": allocations}) if allocations else ([], [])
    return {"term": term, "allocations": allocations, "unresolved": unresolved, "errors": errors}


# --- Disponibilidade ---

def _normalize_availability(teacher_id, entries):
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
        origin = entry.get("origin", "MANUAL")
        if origin not in ("MANUAL", "GOOGLE"):
            raise ValueError("origin deve ser MANUAL ou GOOGLE.")
        normalized.append({
            "teacherId": teacher_id, "availabilityId": str(uuid.uuid4()),
            "day": day, "start": start.strftime("%H:%M"),
            "end": end.strftime("%H:%M"), "type": kind, "origin": origin,
        })
    return normalized


def _replace_availability(teacher_id, normalized):
    table = _db().Table(TABLES["availability"])
    old = table.query(KeyConditionExpression=Key("teacherId").eq(teacher_id)).get("Items", [])
    with table.batch_writer() as batch:
        for item in old:
            batch.delete_item(Key={"teacherId": teacher_id, "availabilityId": item["availabilityId"]})
        for item in normalized:
            batch.put_item(Item=item)


# --- Roteamento ---

COLLECTIONS = {
    "teachers": ("teacherId", ("name", "email")),
    "subjects": ("subjectId", ("code", "name", "weeklyHours")),
    "classes": ("classId", ("code", "term", "subjectId")),
}
SCHEDULE_ACTIONS = ("submit", "approve", "reject", "publish", "notify")


def _route(event, method, parts):
    if method == "GET" and parts == ["health"]:
        return _response(200, {"status": "ok", "service": "classly-api"})

    user = _current_user(event)

    if parts == ["me"] and method == "GET":
        return _response(200, user)

    if parts == ["users"] and method == "GET":
        _require(user, "COORDINATOR")
        return _response(200, sorted(_items(TABLES["users"]), key=lambda u: u.get("email", "")))

    if parts == ["audit"] and method == "GET":
        _require(user, "COORDINATOR")
        return _response(200, _audit_list(event))

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
        previous = target["role"]
        target["role"] = role
        table.put_item(Item=target)
        _audit(user, "ROLE_CHANGED", "user", target["userId"], {"email": target["email"], "from": previous, "to": role})
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
            _audit(user, "CREATE", parts[0], item[id_key], item)
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
            _audit(user, "DELETE", name, parts[1], existing)
            return _response(204)
        if method == "PUT":
            data = _body(event)
            _required(data, *fields)
            _normalize(name, data)
            updated = {**{field: data[field] for field in fields}, id_key: parts[1]}
            table.put_item(Item=updated)
            _audit(user, "UPDATE", name, parts[1], {"before": existing, "after": updated})
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
            entity_id = f"{teacher_id}/{subject_id}"
            if method == "DELETE":
                table.delete_item(Key={"teacherId": teacher_id, "subjectId": subject_id})
                _audit(user, "DELETE", "qualifications", entity_id)
                return _response(204)
            data = _body(event)
            enabled = data.get("enabled", True)
            if not isinstance(enabled, bool):
                raise ValueError("enabled deve ser booleano.")
            qualification = {"teacherId": teacher_id, "subjectId": subject_id, "enabled": enabled}
            table.put_item(Item=qualification)
            _audit(user, "UPDATE", "qualifications", entity_id, {"enabled": enabled})
            return _response(200, qualification)

    if len(parts) in (3, 4) and parts[0] == "teachers" and parts[2] == "availability":
        teacher_id = parts[1]
        # O professor gerencia a própria disponibilidade; a coordenação, a de todos.
        if user["role"] != "COORDINATOR" and user.get("teacherId") != teacher_id:
            raise Forbidden()
        if not _get(TABLES["teachers"], {"teacherId": teacher_id}):
            return _response(404, {"message": "Professor não encontrado."})
        table = _db().Table(TABLES["availability"])
        current = table.query(KeyConditionExpression=Key("teacherId").eq(teacher_id)).get("Items", [])

        if len(parts) == 3 and method == "GET":
            return _response(200, current)
        if len(parts) == 3 and method == "PUT":
            normalized = _normalize_availability(teacher_id, _body(event).get("availability"))
            _replace_availability(teacher_id, normalized)
            _audit(user, "UPDATE", "availability", teacher_id, {"entries": len(normalized)})
            return _response(200, {"teacherId": teacher_id, "availability": normalized})
        if parts[3:] == ["google"] and method == "POST":
            token = _body(event).get("accessToken")
            if not token:
                raise ValueError("Campos obrigatórios: accessToken")
            try:
                imported = google_calendar.weekly_restrictions(google_calendar.fetch_busy(token))
            except google_calendar.CalendarError as error:
                return _response(502, {"message": str(error)})
            # Mantém o que foi informado manualmente e substitui a importação anterior.
            manual = [e for e in current if e.get("origin", "MANUAL") != "GOOGLE"]
            normalized = _normalize_availability(teacher_id, manual + imported)
            _replace_availability(teacher_id, normalized)
            _audit(user, "CALENDAR_SYNC", "availability", teacher_id, {"imported": len(imported)})
            message = (f"{len(imported)} compromisso(s) semanal(is) importado(s) do Google Calendar."
                       if imported else "Nenhum compromisso semanal recorrente encontrado nas próximas 4 semanas.")
            return _response(200, {"teacherId": teacher_id, "imported": len(imported),
                                   "message": message, "availability": normalized})

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

    if parts == ["schedules", "generate"] and method == "POST":
        _require(user, "COORDINATOR")
        return _response(200, _generate(_body(event)))

    if parts == ["schedules"] and method == "POST":
        _require(user, "COORDINATOR")
        data = _body(event)
        _required(data, "term")
        allocations, errors = _validate_schedule(data)
        if errors:
            return _response(422, {"message": "A grade contém conflitos.", "errors": errors})
        versions = _items(TABLES["schedules"], FilterExpression=Attr("term").eq(data["term"]))
        now = _now()
        schedule = {
            "scheduleId": str(uuid.uuid4()), "term": data["term"],
            "status": "DRAFT", "version": max([int(s.get("version", 0)) for s in versions] + [0]) + 1,
            "createdAt": now, "createdBy": user["email"],
            "allocations": allocations,
            "history": [{"status": "DRAFT", "at": now, "by": user["email"]}],
        }
        _db().Table(TABLES["schedules"]).put_item(Item=schedule)
        _audit(user, "CREATE", "schedule", schedule["scheduleId"], {"term": schedule["term"], "version": schedule["version"]})
        return _response(201, schedule)

    if len(parts) == 2 and parts[0] == "schedules":
        schedule = _schedule_or_404(parts[1], user)
        if not schedule:
            return _response(404, {"message": "Grade não encontrada."})
        if method == "GET":
            return _response(200, schedule)
        _require(user, "COORDINATOR")
        table = _db().Table(TABLES["schedules"])
        if schedule["status"] != "DRAFT":
            return _response(409, {"message": "Somente rascunhos podem ser alterados ou excluídos."})
        if method == "DELETE":
            table.delete_item(Key={"scheduleId": parts[1]})
            _audit(user, "DELETE", "schedule", parts[1], {"term": schedule["term"], "version": schedule.get("version")})
            return _response(204)
        if method == "PUT":
            # Ajuste manual do rascunho: a grade publicada nunca muda silenciosamente.
            allocations, errors = _validate_schedule({"term": schedule["term"], "allocations": _body(event).get("allocations")})
            if errors:
                return _response(422, {"message": "A grade contém conflitos.", "errors": errors})
            schedule.update({"allocations": allocations, "updatedAt": _now(), "updatedBy": user["email"]})
            table.put_item(Item=schedule)
            _audit(user, "UPDATE", "schedule", parts[1], {"term": schedule["term"], "allocations": len(allocations)})
            return _response(200, schedule)

    if len(parts) == 3 and parts[0] == "schedules" and parts[2] in SCHEDULE_ACTIONS and method == "POST":
        _require(user, "COORDINATOR")
        schedule = _schedule_or_404(parts[1], user)
        if not schedule:
            return _response(404, {"message": "Grade não encontrada."})
        return _schedule_action(event, user, schedule, parts[2])

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


def login_event_handler(event, context):
    """Gatilho pós-autenticação do Cognito: registra cada login na auditoria."""
    attributes = event.get("request", {}).get("userAttributes", {})
    user = {"userId": attributes.get("sub", event.get("userName", "")), "email": attributes.get("email", "")}
    _audit(user, "LOGIN", "user", user["userId"], {"source": event.get("triggerSource")})
    return event
