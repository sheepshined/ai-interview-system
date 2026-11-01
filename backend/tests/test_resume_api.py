from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import auth
import jd_analysis
import server
from resume import store


client = TestClient(server.app)


@pytest.fixture(autouse=True)
def _resume_db(tmp_path, monkeypatch):
    store.init_db(str(tmp_path / "resumes.db"))
    monkeypatch.setattr(server, "parse_resume_text", lambda text: {
        "raw_text": text.strip(), "name": "张三", "phone": "", "email": "",
        "location": "", "summary": "", "skills": ["Python"],
        "experience": "", "projects": "", "education": "", "char_count": len(text),
    })


def _headers(name):
    try:
        auth.create_user(name, "password123")
    except ValueError:
        pass
    token = auth.create_access_token(name)
    return {"Authorization": f"Bearer {token}"}


def test_resume_api_is_user_isolated_and_requires_review_for_jd():
    alice = _headers("resume_alice")
    bob = _headers("resume_bob")
    created = client.post("/api/resume/parse-text", json={"content": "张三 Python"}, headers=alice)
    assert created.status_code == 200
    resume_id = created.json()["resume_id"]
    assert client.get(f"/api/resumes/{resume_id}", headers=bob).status_code == 404
    blocked = client.post("/api/jd/analyze", json={"resume_id": resume_id, "jd_text": "需要 Python"}, headers=alice)
    assert blocked.status_code == 409
    assert client.post(f"/api/resumes/{resume_id}/confirm", headers=alice).status_code == 200


def test_jd_contract_rejects_scores_and_bad_evidence(monkeypatch):
    resume = {"content": {}, "evidence": []}

    class FakeLlm:
        def __init__(self, payload): self.payload = payload
        def invoke(self, _): return SimpleNamespace(content=self.payload)

    import agent.llm
    monkeypatch.setattr(agent.llm, "get_llm", lambda **_: FakeLlm(
        '{"hard_constraints":[],"gaps":[],"next_questions":[],"keyword_matches":[],"missing_keywords":[],"suggestions":[],"score":99}'
    ))
    with pytest.raises(Exception):
        jd_analysis.analyze(resume, "Python")

    monkeypatch.setattr(agent.llm, "get_llm", lambda **_: FakeLlm(
        '{"hard_constraints":[{"requirement":"Python","status":"met","explanation":"x","evidence_refs":["/skills/9"]}],"gaps":[],"next_questions":[],"keyword_matches":[],"missing_keywords":[],"suggestions":[]}'
    ))
    with pytest.raises(ValueError, match="不存在"):
        jd_analysis.analyze(resume, "Python")
