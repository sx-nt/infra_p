"""Regras puras: horários, sobreposição e normalização de cadastros."""

import pytest

from shared import app


@pytest.mark.parametrize("data, message", [
    ({"day": "XYZ", "start": "08:00", "end": "10:00"}, "day deve ser"),
    ({"day": "MON", "start": "8h", "end": "10:00"}, "start deve usar"),
    ({"day": "MON", "start": "10:00", "end": "10:00"}, "end deve ser posterior"),
    ({"day": "MON", "start": "11:00", "end": "10:00"}, "end deve ser posterior"),
])
def test_interval_rejects_invalid_ranges(data, message):
    with pytest.raises(ValueError, match=message):
        app._interval(data)


def test_interval_accepts_valid_range():
    day, start, end = app._interval({"day": "FRI", "start": "07:30", "end": "09:10"})
    assert day == "FRI"
    assert (end - start).total_seconds() == 100 * 60


def test_overlap_ignores_adjacent_slots():
    a = app._interval({"day": "MON", "start": "08:00", "end": "10:00"})
    b = app._interval({"day": "MON", "start": "10:00", "end": "12:00"})
    c = app._interval({"day": "MON", "start": "09:00", "end": "11:00"})
    assert not app._overlap(a[1], a[2], b[1], b[2])
    assert app._overlap(a[1], a[2], c[1], c[2])


def test_teacher_email_is_normalized_and_validated(aws):
    data = {"name": "Ana", "email": "  Ana.Souza@Classly.TEST "}
    app._normalize("teachers", data)
    assert data["email"] == "ana.souza@classly.test"
    with pytest.raises(ValueError, match="email inválido"):
        app._normalize("teachers", {"email": "sem-arroba"})


@pytest.mark.parametrize("hours", [0, -2, 2.5, "4", True])
def test_subject_requires_positive_integer_hours(hours):
    with pytest.raises(ValueError, match="weeklyHours"):
        app._normalize("subjects", {"weeklyHours": hours})


def test_body_must_be_json_object():
    with pytest.raises(ValueError):
        app._body({"body": "{inválido"})
    with pytest.raises(ValueError):
        app._body({"body": "[1, 2]"})
    assert app._body({}) == {}
