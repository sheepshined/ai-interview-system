"""技能加载与校验单测 (SKILL_RUNTIME_PLAN §3/§6)。

不依赖 pytest-asyncio: 无异步用例。
覆盖: 加载与校验 / 失败隔离 / 目录同名 / allowed-tools 合法性。
"""
import pytest

from assistant import tools as registry
from skills import loader


@pytest.fixture(autouse=True)
def _restore_root():
    """每个用例结束后把 loader 根恢复为内置根, 避免污染其他测试。"""
    yield
    loader.reload(loader.SKILLS_ROOT)


def _write_skill(root, dir_name, frontmatter, body="# 正文\n\n步骤一。\n"):
    """frontmatter 为空串表示不带 frontmatter; 为 None 表示不写 SKILL.md。"""
    directory = root / dir_name
    directory.mkdir(parents=True, exist_ok=True)
    if frontmatter is None:
        return directory
    text = f"---\n{frontmatter}\n---\n{body}" if frontmatter else body
    (directory / "SKILL.md").write_text(text, encoding="utf-8")
    return directory


def test_builtin_skills_load_and_pass_validation():
    """内置根 (backend/skills) 的两个技能应全部通过校验, 且 allowed-tools 全合法。"""
    loader.reload(loader.SKILLS_ROOT)
    names = {s.meta.name for s in loader.get_skills()}
    assert {"weekly-interview-review", "jd-gap-analysis"} <= names
    assert loader.get_issues() == []
    for skill in loader.get_skills():
        assert skill.body.strip(), skill.meta.name
        for tool in skill.meta.allowed_tools:
            assert registry.get_spec(tool) is not None, (skill.meta.name, tool)


def test_name_must_match_directory(tmp_path):
    _write_skill(tmp_path, "good-name",
                 "name: other-name\ndescription: 做某事。用户需要时使用。")
    loader.reload(str(tmp_path))
    assert loader.get_skill("other-name") is None
    assert loader.get_skills() == []
    assert "目录名" in loader.get_issues()[0].reason


@pytest.mark.parametrize("bad_name,keyword", [
    ("My_Name", "name 非法"),        # 大写 + 下划线违反正则
    ("my--skill", "name 非法"),      # 连续 -- 违反正则
    ("claude-helper", "anthropic"),  # 触犯开放标准保留词
])
def test_name_regex_and_forbidden_words(tmp_path, bad_name, keyword):
    _write_skill(tmp_path, bad_name,
                 f"name: {bad_name}\ndescription: 做某事。用户需要时使用。")
    loader.reload(str(tmp_path))
    assert loader.get_skills() == []
    assert keyword in loader.get_issues()[0].reason


@pytest.mark.parametrize("frontmatter,keyword", [
    ("name: demo-skill", "缺少 description"),
    ("name: demo-skill\ndescription: 含尖括号 <b> 非法。", "< 或 >"),
    ("name: demo-skill\ndescription: " + "很长的描述。" * 200, "1024"),
])
def test_description_rules(tmp_path, frontmatter, keyword):
    _write_skill(tmp_path, "demo-skill", frontmatter)
    loader.reload(str(tmp_path))
    assert loader.get_skills() == []
    assert keyword in loader.get_issues()[0].reason


def test_allowed_tools_must_exist_in_registry(tmp_path):
    _write_skill(tmp_path, "demo-skill",
                 "name: demo-skill\ndescription: 做某事。用户需要时使用。\n"
                 "allowed-tools: list_reports not_a_real_tool")
    loader.reload(str(tmp_path))
    # 声明了不存在的权限 -> 该技能整体不加载
    assert loader.get_skills() == []
    assert "未注册工具" in loader.get_issues()[0].reason


def test_valid_allowed_tools_and_metadata_parsed(tmp_path):
    _write_skill(tmp_path, "demo-skill",
                 "name: demo-skill\ndescription: 做某事。用户需要时使用。\n"
                 "allowed-tools: list_reports read_report_weak_points\n"
                 "metadata:\n  version: '2.0'\n  owner: assistant")
    loader.reload(str(tmp_path))
    skill = loader.get_skill("demo-skill")
    assert skill is not None
    assert skill.meta.allowed_tools == ["list_reports", "read_report_weak_points"]
    assert skill.meta.metadata == {"version": "2.0", "owner": "assistant"}
    assert skill.body.startswith("# 正文")


def test_failure_isolation(tmp_path):
    """单个技能校验失败不影响其他技能加载 (SKILL_RUNTIME_PLAN §3)。"""
    _write_skill(tmp_path, "good-skill",
                 "name: good-skill\ndescription: 正常技能。用户需要时使用。")
    _write_skill(tmp_path, "bad-skill", "name: WRONG\ndescription: 坏技能。")
    loader.reload(str(tmp_path))
    assert [s.meta.name for s in loader.get_skills()] == ["good-skill"]
    assert [i.name for i in loader.get_issues()] == ["bad-skill"]


def test_missing_skill_md_and_frontmatter_reported(tmp_path):
    _write_skill(tmp_path, "no-md-skill", None)                 # 目录无 SKILL.md
    _write_skill(tmp_path, "no-front-skill", "", "# 只有正文\n")  # 无 frontmatter
    loader.reload(str(tmp_path))
    reasons = {i.name: i.reason for i in loader.get_issues()}
    assert "缺少 SKILL.md" in reasons["no-md-skill"]
    assert "frontmatter" in reasons["no-front-skill"]


def test_reload_switches_root_and_caches(tmp_path):
    """reload 换根后缓存随之刷新; 根目录不存在时视为无技能 (非错误)。"""
    _write_skill(tmp_path, "one-skill",
                 "name: one-skill\ndescription: 第一个。用户需要时使用。")
    loader.reload(str(tmp_path))
    assert {s.meta.name for s in loader.get_skills()} == {"one-skill"}

    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    loader.reload(str(empty_root))
    assert loader.get_skills() == [] and loader.get_issues() == []

    loader.reload(str(tmp_path / "not-exist"))
    assert loader.get_skills() == []
