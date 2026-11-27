"""Geração automática de proposta de grade."""

from shared import generator


def subject(sid, hours):
    return {"subjectId": sid, "name": sid.upper(), "weeklyHours": hours}


def klass(cid, sid):
    return {"classId": cid, "code": cid, "term": "2026.2", "subjectId": sid}


def qual(tid, sid, enabled=True):
    return {"teacherId": tid, "subjectId": sid, "enabled": enabled}


TEACHERS = {"ana": {"teacherId": "ana", "name": "Ana"}, "bia": {"teacherId": "bia", "name": "Bia"}}


def hours_by_class(allocations):
    total = {}
    for a in allocations:
        h = (int(a["end"][:2]) * 60 + int(a["end"][3:]) - int(a["start"][:2]) * 60 - int(a["start"][3:])) / 60
        total[a["classId"]] = total.get(a["classId"], 0) + h
    return total


def no_overlap(allocations, key):
    seen = {}
    for a in allocations:
        for other in seen.get((a[key], a["day"]), []):
            assert not (a["start"] < other["end"] and other["start"] < a["end"]), (a, other)
        seen.setdefault((a[key], a["day"]), []).append(a)


def test_fills_weekly_hours_with_qualified_teachers():
    subjects = {"isn": subject("isn", 4), "red": subject("red", 3)}
    classes = [klass("t1", "isn"), klass("t2", "red")]
    allocations, unresolved = generator.generate(
        classes, subjects, TEACHERS, [qual("ana", "isn"), qual("bia", "red")], {})
    assert unresolved == []
    assert hours_by_class(allocations) == {"t1": 4, "t2": 3}
    assert {a["teacherId"] for a in allocations if a["classId"] == "t1"} == {"ana"}
    # Aulas da mesma turma em dias diferentes.
    assert len({a["day"] for a in allocations if a["classId"] == "t1"}) == 2


def test_respects_blocks_and_avoids_conflicts():
    subjects = {f"s{i}": subject(f"s{i}", 4) for i in range(6)}
    classes = [klass(f"c{i}", f"s{i}") for i in range(6)]
    quals = [qual("ana", f"s{i}") for i in range(6)]
    blocked = {"ana": [{"day": "MON", "start": "07:00", "end": "23:00", "type": "BLOCKED"}]}
    allocations, unresolved = generator.generate(classes, subjects, TEACHERS, quals, blocked)
    assert unresolved == []
    assert all(a["day"] != "MON" for a in allocations)
    no_overlap(allocations, "teacherId")
    no_overlap(allocations, "classId")


def test_balances_load_between_teachers():
    subjects = {"isn": subject("isn", 2)}
    classes = [klass(f"c{i}", "isn") for i in range(4)]
    allocations, _ = generator.generate(classes, subjects, TEACHERS, [qual("ana", "isn"), qual("bia", "isn")], {})
    per_teacher = {}
    for a in allocations:
        per_teacher[a["teacherId"]] = per_teacher.get(a["teacherId"], 0) + 1
    assert per_teacher == {"ana": 2, "bia": 2}


def test_prefers_available_slots():
    subjects = {"isn": subject("isn", 2)}
    available = {"ana": [{"day": "THU", "start": "19:00", "end": "21:00", "type": "AVAILABLE"}]}
    allocations, _ = generator.generate([klass("t1", "isn")], subjects, TEACHERS, [qual("ana", "isn")], available)
    assert (allocations[0]["day"], allocations[0]["start"]) == ("THU", "19:00")


def test_reports_what_could_not_be_allocated():
    subjects = {"isn": subject("isn", 4), "red": subject("red", 2)}
    classes = [klass("t1", "isn"), klass("t2", "red"), klass("t3", "fantasma")]
    blocked = {"ana": [{"day": d, "start": "00:00", "end": "23:59", "type": "BLOCKED"} for d in generator.DEFAULT_DAYS]}
    allocations, unresolved = generator.generate(
        classes, subjects, TEACHERS, [qual("ana", "isn"), qual("bia", "red", enabled=False)], blocked)
    reasons = {u["classId"]: u["reason"] for u in unresolved}
    assert allocations == []
    assert "horários livres" in reasons["t1"]
    assert "Nenhum professor habilitado" in reasons["t2"]
    assert "não está cadastrada" in reasons["t3"]


def test_custom_days_and_slots():
    subjects = {"isn": subject("isn", 2)}
    allocations, _ = generator.generate([klass("t1", "isn")], subjects, TEACHERS, [qual("ana", "isn")], {},
                                        days=["SAT"], slots=[("07:30", "09:30")])
    assert allocations == [{"classId": "t1", "teacherId": "ana", "subjectId": "isn",
                            "day": "SAT", "start": "07:30", "end": "09:30"}]
