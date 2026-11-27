"""Importação de restrições do Google Calendar (API simulada)."""

import io
import json
import urllib.error
from datetime import datetime, timezone

import pytest

from shared import app, google_calendar
from support import TEACHER


def busy(*intervals):
    return [{"start": s, "end": e} for s, e in intervals]


def test_recurring_commitments_become_weekly_blocks():
    restrictions = google_calendar.weekly_restrictions(busy(
        # Toda segunda 08:00-10:00 (horário de Brasília), em duas semanas.
        ("2026-12-07T11:00:00Z", "2026-12-07T13:00:00Z"),
        ("2026-12-14T08:00:00-03:00", "2026-12-14T10:00:00-03:00"),
        # Compromisso isolado: não vira restrição semanal.
        ("2026-12-09T14:00:00-03:00", "2026-12-09T15:00:00-03:00"),
        # Evento de dia inteiro: ignorado.
        ("2026-12-10T03:00:00Z", "2026-12-11T03:00:00Z"),
        ("2026-12-17T03:00:00Z", "2026-12-18T03:00:00Z"),
    ))
    assert restrictions == [{"day": "MON", "start": "08:00", "end": "10:00", "type": "BLOCKED", "origin": "GOOGLE"}]


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_fetch_busy_calls_freebusy_with_token():
    captured = {}

    def opener(request, timeout):
        captured["auth"] = request.headers["Authorization"]
        captured["body"] = json.loads(request.data)
        return FakeResponse(json.dumps({"calendars": {"primary": {"busy": busy(("a", "b"))}}}).encode())

    now = datetime(2026, 12, 1, tzinfo=timezone.utc)
    assert google_calendar.fetch_busy("tok", now=now, opener=opener) == [{"start": "a", "end": "b"}]
    assert captured["auth"] == "Bearer tok"
    assert captured["body"]["items"] == [{"id": "primary"}]
    assert captured["body"]["timeMax"].startswith("2026-12-29")


@pytest.mark.parametrize("error, message", [
    (urllib.error.HTTPError("u", 401, "x", {}, None), "expirou"),
    (urllib.error.HTTPError("u", 500, "x", {}, None), "erro 500"),
    (urllib.error.URLError("sem rede"), "indisponível"),
])
def test_fetch_busy_explains_failures(error, message):
    def opener(request, timeout):
        raise error

    with pytest.raises(google_calendar.CalendarError, match=message):
        google_calendar.fetch_busy("tok", opener=opener)


def test_sync_keeps_manual_entries_and_replaces_previous_import(api, catalog, monkeypatch):
    tid = catalog["teacher"]["teacherId"]
    api("PUT", f"/teachers/{tid}/availability", {"availability": [
        {"day": "FRI", "start": "08:00", "end": "12:00"},
        {"day": "TUE", "start": "07:00", "end": "08:00", "origin": "GOOGLE"},
    ]}, email=TEACHER)
    monkeypatch.setattr(google_calendar, "fetch_busy", lambda token: busy(
        ("2026-12-07T19:00:00-03:00", "2026-12-07T21:00:00-03:00"),
        ("2026-12-14T19:00:00-03:00", "2026-12-14T21:00:00-03:00"),
    ))
    status, result = api("POST", f"/teachers/{tid}/availability/google", {"accessToken": "tok"}, email=TEACHER)
    assert status == 200 and result["imported"] == 1
    entries = {(e["day"], e["start"], e["origin"]) for e in api("GET", f"/teachers/{tid}/availability")[1]}
    assert entries == {("FRI", "08:00", "MANUAL"), ("MON", "19:00", "GOOGLE")}


def test_sync_errors_and_permissions(api, catalog, monkeypatch):
    tid = catalog["teacher"]["teacherId"]
    assert api("POST", f"/teachers/{tid}/availability/google", {}, email=TEACHER)[0] == 400

    def expired(token):
        raise google_calendar.CalendarError("A autorização do Google expirou ou foi negada. Autorize novamente.")

    monkeypatch.setattr(google_calendar, "fetch_busy", expired)
    status, body = api("POST", f"/teachers/{tid}/availability/google", {"accessToken": "x"}, email=TEACHER)
    assert status == 502 and "expirou" in body["message"]
    assert api("POST", f"/teachers/{tid}/availability/google", {"accessToken": "x"}, email="intruso@classly.test")[0] == 403
    assert app.TABLES["availability"]
