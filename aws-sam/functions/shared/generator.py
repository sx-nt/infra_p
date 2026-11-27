"""Geração automática de uma proposta de grade.

Algoritmo guloso com escolha do professor: as turmas com menos professores
habilitados são alocadas primeiro; cada turma recebe um único professor (o
menos carregado que consiga cumprir toda a carga) e suas aulas são espalhadas
por dias diferentes, evitando bloqueios e conflitos (RN01, RN02, RN03, RN06).
Turmas que não couberem voltam em `unresolved` para ajuste manual.
"""

DEFAULT_DAYS = ["MON", "TUE", "WED", "THU", "FRI"]
DEFAULT_SLOTS = [
    ("08:00", "10:00"),
    ("10:00", "12:00"),
    ("13:30", "15:30"),
    ("15:30", "17:30"),
    ("19:00", "21:00"),
    ("21:00", "23:00"),
]


def _minutes(value):
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def _clock(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _lessons(weekly_hours):
    """Divide a carga semanal em aulas de 2h (e uma de 1h se for ímpar)."""
    weekly_hours = int(weekly_hours)
    return [120] * (weekly_hours // 2) + ([60] if weekly_hours % 2 else [])


def _overlaps(intervals, day, start, end):
    return any(d == day and start < e and s < end for d, s, e in intervals)


def generate(classes, subjects, teachers, qualifications, availability, days=None, slots=None):
    """Retorna (allocations, unresolved).

    classes: turmas do período; subjects/teachers: dicionários por id;
    qualifications: habilitações; availability: {teacherId: [restrições]}.
    """
    days = days or DEFAULT_DAYS
    slots = [(_minutes(s), _minutes(e)) for s, e in (slots or DEFAULT_SLOTS)]

    qualified = {}
    for q in qualifications:
        if q.get("enabled") and q["teacherId"] in teachers:
            qualified.setdefault(q["subjectId"], []).append(q["teacherId"])

    blocked, preferred = {}, {}
    for teacher_id, entries in availability.items():
        for entry in entries:
            interval = (entry["day"], _minutes(entry["start"]), _minutes(entry["end"]))
            target = preferred if entry.get("type") == "AVAILABLE" else blocked
            target.setdefault(teacher_id, []).append(interval)

    teacher_busy, class_busy, load = {}, {}, {t: 0 for t in teachers}
    allocations, unresolved = [], []

    def candidate_slots(teacher_id, class_id, duration, used_days):
        options = []
        for day_index, day in enumerate(days):
            for slot_index, (slot_start, slot_end) in enumerate(slots):
                if slot_end - slot_start < duration:
                    continue
                start, end = slot_start, slot_start + duration
                if (_overlaps(teacher_busy.get(teacher_id, []), day, start, end)
                        or _overlaps(class_busy.get(class_id, []), day, start, end)
                        or _overlaps(blocked.get(teacher_id, []), day, start, end)):
                    continue
                # Menor pontuação é melhor: dias novos para a turma, horários
                # marcados como disponíveis e dias com menos aulas do professor.
                score = (
                    (10 if day in used_days else 0)
                    - (5 if _overlaps(preferred.get(teacher_id, []), day, start, end) else 0)
                    + sum(1 for d, _, _ in teacher_busy.get(teacher_id, []) if d == day)
                )
                options.append((score, day_index, slot_index, day, start, end))
        return sorted(options)

    def plan(klass, teacher_id):
        """Tenta encaixar todas as aulas da turma com o professor; None se não couber."""
        placed, used_days = [], set()
        saved_teacher = list(teacher_busy.get(teacher_id, []))
        saved_class = list(class_busy.get(klass["classId"], []))
        for duration in _lessons(subjects[klass["subjectId"]]["weeklyHours"]):
            options = candidate_slots(teacher_id, klass["classId"], duration, used_days)
            if not options:
                teacher_busy[teacher_id] = saved_teacher
                class_busy[klass["classId"]] = saved_class
                return None
            _, _, _, day, start, end = options[0]
            teacher_busy.setdefault(teacher_id, []).append((day, start, end))
            class_busy.setdefault(klass["classId"], []).append((day, start, end))
            used_days.add(day)
            placed.append((day, start, end))
        return placed

    pending = [c for c in classes if c.get("subjectId") in subjects]
    pending.sort(key=lambda c: (len(qualified.get(c["subjectId"], [])),
                                -int(subjects[c["subjectId"]]["weeklyHours"]), c.get("code", "")))
    for klass in classes:
        if klass.get("subjectId") not in subjects:
            unresolved.append({"classId": klass["classId"], "reason": "A disciplina da turma não está cadastrada."})

    for klass in pending:
        subject = subjects[klass["subjectId"]]
        candidates = sorted(qualified.get(klass["subjectId"], []), key=lambda t: (load[t], teachers[t].get("name", "")))
        if not candidates:
            unresolved.append({"classId": klass["classId"], "reason": f"Nenhum professor habilitado para {subject.get('name')}."})
            continue
        for teacher_id in candidates:
            placed = plan(klass, teacher_id)
            if placed is None:
                continue
            for day, start, end in placed:
                allocations.append({
                    "classId": klass["classId"], "teacherId": teacher_id,
                    "subjectId": klass["subjectId"], "day": day,
                    "start": _clock(start), "end": _clock(end),
                })
                load[teacher_id] += (end - start) / 60
            break
        else:
            unresolved.append({
                "classId": klass["classId"],
                "reason": f"Não há horários livres suficientes para {subject.get('name')} com os professores habilitados.",
            })

    order = {day: index for index, day in enumerate(DEFAULT_DAYS + ["SAT", "SUN"])}
    allocations.sort(key=lambda a: (order.get(a["day"], 9), a["start"], a["classId"]))
    return allocations, unresolved

