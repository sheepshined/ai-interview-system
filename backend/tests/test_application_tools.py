import asyncio
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import application_store
from assistant.tools import applications as tools
from resume import store as resumes


@pytest.fixture(autouse=True)
def isolated(tmp_path):
    application_store.init_db(str(tmp_path / "applications.db"))
    resumes.init_db(str(tmp_path / "resumes.db"))


def rt(user="alice"):
    return SimpleNamespace(state={"username": user, "session_id": 1})


def run(awaitable):
    return asyncio.run(awaitable)


def test_application_tools_owned_lifecycle():
    first = run(tools.create_application("Alpha", "Developer", runtime=rt()))["application"]
    aid = first["id"]
    assert run(tools.list_applications(runtime=rt("bob")))["applications"] == []
    assert not run(tools.read_application(aid, runtime=rt("bob")))["found"]
    assert not run(tools.update_application_stage(aid, "offer", runtime=rt("bob")))["ok"]
    assert not run(tools.add_application_note(aid, "foreign", runtime=rt("bob")))["ok"]
    assert not run(tools.save_application_reflection(aid, result="foreign", runtime=rt("bob")))["ok"]
    assert run(tools.update_application_stage(aid, "interview", runtime=rt()))["ok"]
    assert run(tools.add_application_note(aid, "first round", runtime=rt()))["ok"]
    assert run(tools.save_application_reflection(aid, result="advanced", tags=["design"], runtime=rt()))["ok"]
    item = run(tools.read_application(aid, runtime=rt()))["application"]
    assert item["stage"] == "interview"
    assert item["events"][-1]["note"] == "first round"
    assert item["outcome"]["tags"] == ["design"]
    application_store.archive("alice", aid)
    assert not run(tools.add_application_note(aid, "archived", runtime=rt()))["ok"]


def test_application_tools_validate_and_reject_foreign_resume():
    foreign = resumes.create_resume("bob", "Python", {"skills": ["Python"]})
    assert not run(tools.create_application("Alpha", "Dev", resume_id=foreign["id"], runtime=rt()))["ok"]
    with pytest.raises(ValidationError):
        run(tools.create_application("   ", "Dev", runtime=rt()))
    with pytest.raises(ValidationError):
        run(tools.update_application_stage(1, "invalid", runtime=rt()))
    with pytest.raises(ValidationError):
        run(tools.add_application_note(1, "   ", runtime=rt()))
