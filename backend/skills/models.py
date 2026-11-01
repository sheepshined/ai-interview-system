"""models.py — 技能数据模型 (SKILL_RUNTIME_PLAN §6)。

SkillMeta:    单技能的元数据 (frontmatter 解析结果), 是 L1 注入与路由的唯一来源。
LoadedSkill:  元数据 + 正文 (L2), 激活时注入。
SkillIssue:   加载/校验诊断, 供 list_skills 暴露与启动日志告警 (失败隔离原则)。
"""
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class SkillMeta:
    name: str
    description: str
    allowed_tools: List[str] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)
    dir: str = ""            # 技能目录绝对路径


@dataclass
class LoadedSkill:
    meta: SkillMeta
    body: str = ""           # SKILL.md 正文 (frontmatter 之后)


@dataclass
class SkillIssue:
    name: str                # 目录名 (无法解析声明名时)
    reason: str
