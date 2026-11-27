"""Importação de restrições de horário a partir do Google Calendar.

O frontend obtém do Google um token de acesso de leitura da agenda
(escopo calendar.readonly) e o envia uma única vez; o backend consulta os
horários ocupados (API freeBusy) e transforma compromissos que se repetem
semanalmente em bloqueios. O token não é armazenado.
"""

import json
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

FREEBUSY_URL = "https://www.googleapis.com/calendar/v3/freeBusy"
# Horário de Brasília (sem horário de verão desde 2019).
LOCAL_TZ = timezone(timedelta(hours=-3), "America/Sao_Paulo")
WEEKDAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
LOOKAHEAD_WEEKS = 4
# Um compromisso vira restrição semanal se aparecer em pelo menos 2 semanas.
MIN_OCCURRENCES = 2
# Eventos de dia inteiro (ou muito longos) não representam horários de aula.
MAX_EVENT_HOURS = 12


class CalendarError(Exception):
    pass


def fetch_busy(access_token, now=None, opener=urllib.request.urlopen):
    """Consulta os intervalos ocupados da agenda principal nas próximas semanas."""
    now = now or datetime.now(timezone.utc)
    body = {
        "timeMin": now.isoformat(),
        "timeMax": (now + timedelta(weeks=LOOKAHEAD_WEEKS)).isoformat(),
        "timeZone": "America/Sao_Paulo",
        "items": [{"id": "primary"}],
    }
    request = urllib.request.Request(
        FREEBUSY_URL,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener(request, timeout=10) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise CalendarError("A autorização do Google expirou ou foi negada. Autorize novamente.")
        raise CalendarError(f"O Google Calendar respondeu com erro {error.code}. Tente mais tarde.")
    except (urllib.error.URLError, TimeoutError):
        raise CalendarError("O Google Calendar está indisponível no momento. Tente mais tarde.")

    calendar = payload.get("calendars", {}).get("primary", {})
    if calendar.get("errors"):
        raise CalendarError("Não foi possível ler a agenda principal do Google.")
    return calendar.get("busy", [])


def weekly_restrictions(busy):
    """Converte intervalos ocupados em bloqueios semanais recorrentes."""
    weeks_by_slot = {}
    for interval in busy:
        start = datetime.fromisoformat(interval["start"].replace("Z", "+00:00")).astimezone(LOCAL_TZ)
        end = datetime.fromisoformat(interval["end"].replace("Z", "+00:00")).astimezone(LOCAL_TZ)
        if end - start >= timedelta(hours=MAX_EVENT_HOURS) or end <= start:
            continue
        if end.date() != start.date():
            end = start.replace(hour=23, minute=59)
        key = (WEEKDAYS[start.weekday()], start.strftime("%H:%M"), end.strftime("%H:%M"))
        weeks_by_slot.setdefault(key, set()).add(start.isocalendar()[:2])

    restrictions = [
        {"day": day, "start": start, "end": end, "type": "BLOCKED", "origin": "GOOGLE"}
        for (day, start, end), weeks in weeks_by_slot.items()
        if len(weeks) >= MIN_OCCURRENCES
    ]
    return sorted(restrictions, key=lambda r: (WEEKDAYS.index(r["day"]), r["start"]))
