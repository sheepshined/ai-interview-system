"""三闸门权限判定单测 (AGENT_PLAN §5.6)。"""
from assistant import permission

READ = {"name": "list_reports", "risk": "read", "needs_approval": False}
WRITE_AUTO = {"name": "remember", "risk": "write", "needs_approval": True,
              "auto_accept_default": True}
WRITE_HARD = {"name": "forget_memory", "risk": "write", "needs_approval": True,
              "auto_accept_default": False}
EXEC = {"name": "propose_interview", "risk": "execute", "needs_approval": True}

S = lambda level: {"auto_accept_level": level, "memory_enabled": True}


def setup_function(_):
    permission.reset_for_tests()


def test_default_level_matrix():
    assert permission.evaluate(READ, "d1", S("read_auto")) == permission.ALLOW
    assert permission.evaluate(READ, "d1", S("all_confirm")) == permission.ASK
    assert permission.evaluate(WRITE_AUTO, "d2", S("read_auto")) == permission.ALLOW
    assert permission.evaluate(WRITE_HARD, "d3", S("read_auto")) == permission.ASK
    assert permission.evaluate(WRITE_HARD, "d3", S("exec_only")) == permission.ALLOW
    # execute 任何档位都必须人确认
    for level in ("all_confirm", "read_auto", "exec_only"):
        assert permission.evaluate(EXEC, "d4", S(level)) == permission.ASK


def test_no_match_defaults_to_ask():
    unknown = {"name": "brand_new_tool", "risk": "weird"}
    assert permission.evaluate(unknown, "d9", S("exec_only")) == permission.ASK


def test_approval_is_per_fingerprint_not_per_tool():
    permission.record_approval("forget_memory", "sha256:aaa")
    assert permission.evaluate(WRITE_HARD, "sha256:aaa", S("all_confirm")) \
        == permission.ALLOW
    # 换参数就是新提案, 必须重新问 (analysis_zcode s09:40)
    assert permission.evaluate(WRITE_HARD, "sha256:bbb", S("all_confirm")) \
        == permission.ASK


def test_memory_disabled_denies_remember():
    assert permission.evaluate(WRITE_AUTO, "d5",
                               {"auto_accept_level": "read_auto",
                                "memory_enabled": False}) == permission.DENY


def test_denial_reason_roundtrip():
    permission.record_denial("propose_interview", "sha256:ccc", "用户不想面试")
    assert permission.denial_reason("propose_interview", "sha256:ccc") \
        == "用户不想面试"


def test_approval_isolated_by_user_and_session():
    permission.record_approval("forget_memory", "same", "alice", 1)
    assert permission.evaluate(WRITE_HARD, "same", S("all_confirm"), "alice", 1) == permission.ALLOW
    assert permission.evaluate(WRITE_HARD, "same", S("all_confirm"), "bob", 1) == permission.ASK
    assert permission.evaluate(WRITE_HARD, "same", S("all_confirm"), "alice", 2) == permission.ASK


def test_disabled_memory_wins_over_cached_approval():
    permission.record_approval("remember", "same", "alice", 1)
    assert permission.evaluate(WRITE_AUTO, "same", {"memory_enabled": False},
                               "alice", 1) == permission.DENY


def test_application_write_always_requires_fresh_confirmation():
    meta = {"name": "create_application", "risk": "write", "always_confirm": True}
    permission.record_approval("create_application", "same", "alice", 1)
    for level in ("read_auto", "exec_only", "all_confirm"):
        assert permission.evaluate(meta, "same", S(level), "alice", 1) == permission.ASK
