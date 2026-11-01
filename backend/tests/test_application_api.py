import auth
import application_store
import server
from fastapi.testclient import TestClient


client = TestClient(server.app)


def _headers(username):
    try:
        auth.create_user(username, "password123")
    except ValueError:
        pass
    return {"Authorization": f"Bearer {auth.create_access_token(username)}"}


def _body(**overrides):
    data = {
        "company": "示例科技",
        "role_title": "后端工程师",
        "job_url": "https://example.test/jobs/1",
        "jd_text": "负责服务端研发",
        "stage": "saved",
        "resume_id": None,
    }
    data.update(overrides)
    return data


def test_application_lifecycle_and_user_isolation(tmp_path):
    application_store.init_db(str(tmp_path / "applications.db"))
    alice = _headers("application_alice")
    bob = _headers("application_bob")

    created = client.post("/api/applications", json=_body(), headers=alice)
    assert created.status_code == 200
    item = created.json()["application"]
    app_id = item["id"]
    assert item["stage"] == "saved"

    listing = client.get("/api/applications", headers=alice).json()["applications"]
    assert [row["id"] for row in listing] == [app_id]
    assert client.get(f"/api/applications/{app_id}", headers=bob).status_code == 404

    updated = client.put(
        f"/api/applications/{app_id}", json=_body(stage="interview"), headers=alice
    )
    assert updated.status_code == 200
    assert updated.json()["application"]["stage"] == "interview"
    assert any(e["kind"] == "stage_changed" for e in updated.json()["application"]["events"])

    event = client.post(
        f"/api/applications/{app_id}/events", json={"note": "完成一面"}, headers=alice
    )
    assert event.status_code == 200
    assert event.json()["application"]["events"][-1]["note"] == "完成一面"

    outcome = client.put(
        f"/api/applications/{app_id}/outcome",
        json={"result": "进入二面", "reflection": "系统设计需要更清晰", "tags": ["系统设计"]},
        headers=alice,
    )
    assert outcome.status_code == 200
    assert outcome.json()["application"]["outcome"]["tags"] == ["系统设计"]
    assert client.put(
        f"/api/applications/{app_id}/outcome", json={"result": "越权"}, headers=bob
    ).status_code == 404

    assert client.delete(f"/api/applications/{app_id}", headers=alice).status_code == 200
    assert client.get("/api/applications", headers=alice).json()["applications"] == []


def test_application_validation_and_resume_ownership(tmp_path):
    application_store.init_db(str(tmp_path / "applications.db"))
    alice = _headers("app_resume_alice")
    bob = _headers("app_resume_bob")

    resume = client.post(
        "/api/resume/parse-text", json={"content": "候选人 Python 工程师"}, headers=bob
    )
    assert resume.status_code == 200
    resume_id = resume.json()["resume_id"]

    assert client.post(
        "/api/applications", json=_body(resume_id=resume_id), headers=alice
    ).status_code == 422
    assert client.post(
        "/api/applications", json=_body(stage="unknown"), headers=alice
    ).status_code == 422
    assert client.post(
        "/api/applications", json=_body(company=""), headers=alice
    ).status_code == 422
    for body in (_body(company="   "), _body(job_url="javascript:alert(1)"), _body(resume_id=True)):
        assert client.post("/api/applications", json=body, headers=alice).status_code == 422


def test_interview_report_attachment_is_idempotent_and_scoped(tmp_path):
    application_store.init_db(str(tmp_path / "applications.db"))
    alice = "application_report_alice"
    bob = "application_report_bob"
    first = application_store.create(alice, _body())
    second = application_store.create(bob, _body(company="另一家公司"))

    assert application_store.attach_interview(alice, first["id"], "report-001") is True
    assert application_store.attach_interview(alice, first["id"], "report-001") is True
    assert len(application_store.get(alice, first["id"])["interviews"]) == 1
    assert application_store.attach_interview(bob, first["id"], "report-002") is False
    assert application_store.attach_interview(alice, second["id"], "report-003") is False
    third = application_store.create(alice, _body(company="third"))
    assert application_store.attach_interview(alice, third["id"], "report-001") is False
    assert application_store.attach_interview(alice, third["id"], "") is False


def test_application_context_uses_owned_reviewed_resume(tmp_path):
    import pytest
    from resume import store as resumes
    resumes.init_db(str(tmp_path / "resumes.db"))
    record = resumes.create_resume("alice", "Python", {"skills": ["Python"], "summary": "Python"})
    item = _body(resume_id=record["id"])
    with pytest.raises(ValueError):
        server._application_interview_context("alice", item, {})
    resumes.confirm_import("alice", record["id"])
    context = server._application_interview_context("alice", item, {"resume_context": "forged"})
    assert "Python" in context["resume_context"]
    assert item["jd_text"] in context["resume_context"]
    assert "forged" not in context["resume_context"]
    assert context["resume_skills"] == ["Python"]
    with pytest.raises(ValueError):
        server._application_interview_context("bob", item, {})
