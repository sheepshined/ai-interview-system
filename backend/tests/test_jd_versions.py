import asyncio
import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import application_store as store
import auth
import server
from assistant.tools import applications as tools

client = TestClient(server.app)


@pytest.fixture(autouse=True)
def isolated(tmp_path):
    store.init_db(str(tmp_path / "applications.db"))


def headers(user="jd_alice"):
    try:
        auth.create_user(user, "password123")
    except ValueError:
        pass
    return {"Authorization": f"Bearer {auth.create_access_token(user)}"}


def body(**changes):
    return {"company": "Alpha", "role_title": "Developer", "jd_text": "Python\nSQL", "job_url": "https://example.test/job/1", **changes}


def test_jd_version_lifecycle_and_restoration():
    h = headers()
    app = client.post("/api/applications", json=body(), headers=h).json()["application"]
    path = f"/api/applications/{app['id']}/jd"
    v1 = app["jd_version"]
    assert v1["version"] == 1
    assert v1["content_hash"] == hashlib.sha256(b"Python\nSQL").hexdigest()
    changed = {"jd_text": "Python\nSQL\nRedis", "source_url": app["job_url"], "expected_version": 1}
    result = client.put(path, json=changed, headers=h)
    assert result.status_code == 200
    assert result.json()["application"]["jd_version"]["version"] == 2
    assert result.json()["application"]["events"][-1]["kind"] == "jd_updated"
    assert client.put(path, json=changed, headers=h).status_code == 409
    changed["expected_version"] = 2
    assert client.put(path, json=changed, headers=h).json()["application"]["jd_version"]["version"] == 2
    result = client.post(f"{path}/versions/{v1['id']}/restore", json={"expected_version": 2}, headers=h)
    assert result.status_code == 200
    restored = result.json()["application"]
    assert restored["jd_text"] == app["jd_text"]
    assert restored["jd_version"]["version"] == 3
    assert restored["jd_version"]["restored_from"] == v1["id"]
    assert restored["jd_version"]["source"] == "restore"
    assert restored["events"][-1]["kind"] == "jd_restored"
    assert len(client.get(f"{path}/versions", headers=h).json()["versions"]) == 3
    assert client.get(f"{path}/versions/{v1['id']}", headers=h).json()["version"]["jd_text"] == app["jd_text"]


def test_jd_versions_are_user_and_application_scoped():
    app = store.create("jd_alice", body())
    other = store.create("jd_alice", body(company="Beta"))
    v1 = app["jd_version"]["id"]
    path = f"/api/applications/{app['id']}/jd"
    for url in (f"{path}/versions", f"{path}/versions/{v1}"):
        assert client.get(url, headers=headers("jd_bob")).status_code == 404
        assert client.get(url).status_code == 401
    assert client.put(path, headers=headers("jd_bob"), json={"jd_text": "foreign", "expected_version": 1}).status_code == 404
    assert client.post(f"{path}/versions/{v1}/restore", headers=headers("jd_bob"), json={"expected_version": 1}).status_code == 404
    assert client.get(f"/api/applications/{other['id']}/jd/versions/{v1}", headers=headers()).status_code == 404
    assert client.post(f"/api/applications/{other['id']}/jd/versions/{v1}/restore", headers=headers(), json={"expected_version": 1}).status_code == 404
    assert store.get("jd_alice", app["id"])["jd_version"]["version"] == 1


@pytest.mark.parametrize("changes", [
    {"source_url": "javascript:alert(1)"}, {"jd_text": 12}, {"jd_text": "x" * 20001},
    {"expected_version": True}, {"expected_version": -1}, {"expected_version": "1"},
    {"fetched_at": "fake"},
])
def test_jd_invalid_write_has_no_side_effect(changes):
    app = store.create("jd_alice", body())
    data = {"jd_text": "new", "expected_version": 1, **changes}
    assert client.put(f"/api/applications/{app['id']}/jd", json=data, headers=headers()).status_code == 422
    assert store.get("jd_alice", app["id"])["jd_text"] == "Python\nSQL"
    assert len(store.list_jd_versions("jd_alice", app["id"])) == 1


def test_jd_empty_content_source_changes_and_application_edit():
    app = store.create("jd_alice", body(jd_text="", job_url=""))
    assert app["jd_version"] is None
    app = store.save_jd("jd_alice", app["id"], "Python", "", 0)
    assert app["jd_version"]["version"] == 1
    app = store.update("jd_alice", app["id"], {"stage": "interview"})
    assert app["jd_version"]["version"] == 1
    app = store.update("jd_alice", app["id"], {"job_url": "https://example.test/new", "expected_jd_version": 1})
    assert app["jd_version"]["version"] == 2
    assert app["jd_version"]["content_hash"] == hashlib.sha256(b"Python").hexdigest()
    result = client.put(f"/api/applications/{app['id']}", headers=headers(), json=body(expected_jd_version=1))
    assert result.status_code == 409
    assert store.get("jd_alice", app["id"])["stage"] == "interview"
    app = store.save_jd("jd_alice", app["id"], "", "", 2)
    assert app["jd_version"]["version"] == 3
    assert app["jd_text"] == app["job_url"] == ""


def test_archived_application_versions_remain_read_only():
    app = store.create("jd_alice", body())
    store.archive("jd_alice", app["id"])
    path = f"/api/applications/{app['id']}/jd"
    assert client.get(f"{path}/versions", headers=headers()).status_code == 200
    assert client.put(path, headers=headers(), json={"jd_text": "new", "expected_version": 1}).status_code == 404
    assert client.post(f"{path}/versions/{app['jd_version']['id']}/restore", headers=headers(), json={"expected_version": 1}).status_code == 404
    assert store.update("jd_alice", app["id"], body()) is None


def test_application_edit_cannot_bypass_jd_version_check():
    app = store.create("jd_alice", body())
    path = f"/api/applications/{app['id']}"
    for missing in ({}, {"expected_jd_version": None}):
        result = client.put(path, headers=headers(), json=body(jd_text="new", stage="offer", **missing))
        assert result.status_code == 409
        assert store.get("jd_alice", app["id"])["stage"] == "saved"
        assert len(store.list_jd_versions("jd_alice", app["id"])) == 1
    # Legacy clients may still change non-JD fields without a version number.
    assert client.put(path, headers=headers(), json=body(stage="interview")).status_code == 200
    assert client.put(path, headers=headers(), json=body(jd_text="new", expected_jd_version=1)).status_code == 200


def test_restore_identical_historical_content_still_records_restoration():
    app = store.create("jd_alice", body())
    v1 = app["jd_version"]["id"]
    store.save_jd("jd_alice", app["id"], "Redis", app["job_url"], 1)
    store.save_jd("jd_alice", app["id"], app["jd_text"], app["job_url"], 2)
    restored = store.save_jd("jd_alice", app["id"], "", "", 3, restore_id=v1)
    assert restored["jd_version"]["version"] == 4
    assert restored["jd_version"]["restored_from"] == v1
    assert restored["events"][-1]["kind"] == "jd_restored"


def test_concurrent_jd_writes_have_one_winner():
    app = store.create("alice", body())

    def write(text):
        try:
            return store.save_jd("alice", app["id"], text, "", 1) is not None
        except store.JdVersionConflict:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(write, ["new one", "new two"])) == [False, True]
    assert len(store.list_jd_versions("alice", app["id"])) == 2


def test_backfill_is_idempotent_and_preserves_existing_data():
    app = store.create("alice", body())
    with sqlite3.connect(store._DB_PATH) as conn:
        conn.execute("DROP TABLE application_jd_versions")
    store.init_db()
    store.init_db()
    restored = store.get("alice", app["id"])
    assert restored["jd_text"] == app["jd_text"]
    assert restored["events"] == app["events"]
    assert restored["jd_version"]["source"] == "migration"
    assert len(store.list_jd_versions("alice", app["id"])) == 1


def test_jd_tools_share_validation_and_ownership():
    run = asyncio.run
    rt = SimpleNamespace(state={"username": "alice"})
    foreign = SimpleNamespace(state={"username": "bob"})
    app = store.create("alice", body())
    aid = app["id"]
    read = run(tools.read_application_jd(aid, runtime=rt))
    assert read["current_version"] == 1 and read["found"]
    assert not run(tools.read_application_jd(aid, runtime=foreign))["ok"]
    assert not run(tools.update_application_jd(aid, "foreign", 1, runtime=foreign))["ok"]
    updated = run(tools.update_application_jd(aid, "Redis", 1, runtime=rt))
    assert updated["application"]["jd_version"]["version"] == 2
    assert run(tools.update_application_jd(aid, "stale", 1, runtime=rt))["conflict"]
    restored = run(tools.restore_application_jd(aid, app["jd_version"]["id"], 2, runtime=rt))
    assert restored["application"]["jd_version"]["version"] == 3
    assert not run(tools.restore_application_jd(aid, app["jd_version"]["id"], 3, runtime=foreign))["ok"]
