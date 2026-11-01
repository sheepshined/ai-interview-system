"""loader.py — 内置技能目录扫描、frontmatter 解析与校验 (SKILL_RUNTIME_PLAN §3/§6)。

职责:
  - 扫描技能根目录 (默认 backend/skills/), 每个子目录一个技能;
  - 解析 SKILL.md 的 frontmatter (YAML); 无 frontmatter 视为非法;
  - 执行 §3 校验: name 正则/长度/与目录同名/不含 anthropic|claude;
    description 长度与不得含 <> ; allowed-tools 每一项必须已在工具 registry;
  - 失败隔离: 单技能校验失败不影响其他技能 (进 diagnostics, 不阻断整体);
  - 缓存 + reload()。

硬约定: 技能目录只读扫描, 不加载可写目录 (SKILL_RUNTIME_PLAN §9.2)。
"""
import logging
import os
import re
from typing import Dict, List, Optional, Tuple

import yaml

import config
from assistant.tools.base import get_spec
from skills.models import LoadedSkill, SkillIssue, SkillMeta

logger = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_FORBIDDEN_WORDS = ("anthropic", "claude")
MAX_NAME_LEN = 64
MAX_DESCRIPTION_LEN = 1024

# 内置技能根 (随代码走); 用户级根留 P2 (SKILL_RUNTIME_PLAN §3)。
SKILLS_ROOT = os.path.join(config.BASE_DIR, "skills")

# 技能目录内约定子目录 (SKILL_RUNTIME_PLAN §3)
_FRONT_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.S)

_cache: Dict[str, LoadedSkill] = {}
_issues: List[SkillIssue] = []
_loaded_root: Optional[str] = None


def _split_frontmatter(text: str) -> Tuple[Optional[dict], str]:
    """切出 frontmatter 与正文; 无 frontmatter 返回 (None, 原文)。"""
    match = _FRONT_RE.match(text or "")
    if not match:
        return None, text or ""
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return "PARSE_ERROR", match.group(2).strip()
    return data, (match.group(2) or "").strip()


def _validate(data: object, dir_name: str, dir_path: str) -> Tuple[Optional[SkillMeta], str]:
    """返回 (SkillMeta, "") 或 (None, 失败原因)。全部规则见 SKILL_RUNTIME_PLAN §3。"""
    if data == "PARSE_ERROR":
        return None, "frontmatter YAML 解析失败"
    if not isinstance(data, dict):
        return None, "SKILL.md 缺少 frontmatter (---)"

    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        return None, "缺少 name 字段"
    name = name.strip()
    if len(name) > MAX_NAME_LEN or not _NAME_RE.match(name):
        return None, f"name 非法: {name!r} (须匹配 ^[a-z0-9]+(-[a-z0-9]+)*$ 且 ≤64 字符)"
    if name != dir_name:
        return None, f"name {name!r} 与目录名 {dir_name!r} 不一致"
    lowered = name.lower()
    if any(word in lowered for word in _FORBIDDEN_WORDS):
        return None, f"name 不得包含 {_FORBIDDEN_WORDS}"

    description = data.get("description")
    if not isinstance(description, str) or not description.strip():
        return None, "缺少 description 字段"
    description = description.strip()
    if len(description) > MAX_DESCRIPTION_LEN:
        return None, f"description 超过 {MAX_DESCRIPTION_LEN} 字符"
    if "<" in description or ">" in description:
        return None, "description 不得包含 < 或 >"

    allowed_raw = data.get("allowed-tools")
    allowed: List[str] = []
    if allowed_raw:
        if isinstance(allowed_raw, str):
            allowed = allowed_raw.split()
        elif isinstance(allowed_raw, list):
            allowed = [str(item) for item in allowed_raw]
        else:
            return None, "allowed-tools 格式非法 (应为空格分隔字符串)"
        unknown = [tool for tool in allowed if get_spec(tool) is None]
        if unknown:
            return None, f"allowed-tools 引用了未注册工具: {unknown}"

    metadata_raw = data.get("metadata") or {}
    if not isinstance(metadata_raw, dict):
        return None, "metadata 必须是键值映射"
    metadata = {str(k): str(v) for k, v in metadata_raw.items()}

    meta = SkillMeta(name=name, description=description, allowed_tools=allowed,
                     metadata=metadata, dir=dir_path)
    return meta, ""


def _load_one(dir_path: str, dir_name: str) -> Tuple[Optional[LoadedSkill], str]:
    md_path = os.path.join(dir_path, "SKILL.md")
    if not os.path.isfile(md_path):
        return None, "缺少 SKILL.md"
    with open(md_path, encoding="utf-8") as fh:
        text = fh.read()
    data, body = _split_frontmatter(text)
    meta, reason = _validate(data, dir_name, dir_path)
    if meta is None:
        return None, reason
    return LoadedSkill(meta=meta, body=body), ""


def _scan(root: str) -> Tuple[Dict[str, LoadedSkill], List[SkillIssue]]:
    skills: Dict[str, LoadedSkill] = {}
    issues: List[SkillIssue] = []
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return skills, issues   # 根目录不存在 = 无技能, 不是错误
    for entry in entries:
        path = os.path.join(root, entry)
        if not os.path.isdir(path) or entry.startswith((".", "_")) \
                or entry == "__pycache__":
            continue
        try:
            skill, reason = _load_one(path, entry)
        except Exception as exc:   # 失败隔离: 单技能异常不拖垮其他技能
            skill, reason = None, f"加载异常: {type(exc).__name__}: {exc}"
        if skill is None:
            issues.append(SkillIssue(name=entry, reason=reason))
        else:
            skills[skill.meta.name] = skill
    return skills, issues


def reload(root: Optional[str] = None) -> dict:
    """重新扫描技能根并刷新缓存。root 为空时沿用上次根 (默认 SKILLS_ROOT)。"""
    global _cache, _issues, _loaded_root
    if root is not None:
        _loaded_root = root
    if _loaded_root is None:
        _loaded_root = SKILLS_ROOT
    # 确保工具 registry 已填充 (校验 allowed-tools 合法性时需要)
    import assistant.tools  # noqa: F401
    skills, issues = _scan(_loaded_root)
    _cache, _issues = skills, issues
    for issue in issues:
        logger.warning("技能 %s 加载失败: %s", issue.name, issue.reason)
    return {"skills": list(skills.values()), "issues": issues}


def get_skills() -> List[LoadedSkill]:
    if _loaded_root is None:
        reload()
    return list(_cache.values())


def get_skill(name: str) -> Optional[LoadedSkill]:
    if _loaded_root is None:
        reload()
    return _cache.get(name)


def get_issues() -> List[SkillIssue]:
    if _loaded_root is None:
        reload()
    return list(_issues)
