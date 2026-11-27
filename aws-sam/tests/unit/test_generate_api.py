"""Rota de geração: a proposta gerada passa na mesma validação da grade."""

from support import TEACHER


def test_generated_proposal_is_valid_and_can_be_saved(api, catalog):
    status, proposal = api("POST", "/schedules/generate", {"term": "2026.2"})
    assert status == 200
    assert proposal["unresolved"] == [] and proposal["errors"] == []
    assert sum(1 for a in proposal["allocations"]) == 2
    status, saved = api("POST", "/schedules", {"term": "2026.2", "allocations": proposal["allocations"]})
    assert status == 201


def test_generate_validates_input(api, catalog):
    assert api("POST", "/schedules/generate", {})[0] == 400
    assert api("POST", "/schedules/generate", {"term": "1999.1"})[0] == 400
    assert api("POST", "/schedules/generate", {"term": "2026.2", "days": ["XYZ"]})[0] == 400
    assert api("POST", "/schedules/generate", {"term": "2026.2", "slots": [{"start": "10:00", "end": "09:00"}]})[0] == 400
    assert api("POST", "/schedules/generate", {"term": "2026.2"}, email=TEACHER)[0] == 403
