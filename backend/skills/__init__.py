"""skills 包入口 — 后端 Skill 运行时 (SKILL_RUNTIME_PLAN.md)。

三级渐进披露:
  L1 loader.get_skills()      元数据 (name + description), 每轮注入
  L2 runtime.read_skill_body() 正文, 技能激活时注入
  L3 runtime.list_references / read_reference / run_script  按需
"""
from skills import loader, models, runtime  # noqa: F401
from skills.models import LoadedSkill, SkillIssue, SkillMeta  # noqa: F401

__all__ = ["loader", "models", "runtime",
           "LoadedSkill", "SkillIssue", "SkillMeta"]
