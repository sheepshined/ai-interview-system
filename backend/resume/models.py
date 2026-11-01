"""
resume/models.py — 简历解析数据模型

定义 LLM 简历解析输出的结构化模型, 用于 PydanticOutputParser。
从 agent/models.py 迁移至此, 使简历模块的依赖方向收拢在 resume/ 内部。
"""
from typing import List
from pydantic import BaseModel, Field


class ResumeInfo(BaseModel):
    """LLM 简历解析结果 — 精简版, 每字段只保留关键信息"""
    name: str = Field(default="", description="候选人姓名")
    skills: List[str] = Field(
        default_factory=list,
        description="技术技能关键词列表, 按出现顺序去重"
    )
    experience: str = Field(
        default="",
        description="工作经历压缩, 每段一行: 公司 职位 时间 + 1句核心成就, 多段用换行分隔"
    )
    projects: str = Field(
        default="",
        description="项目经历压缩, 每个项目一行: 项目名 + 技术栈 + 1句成果"
    )
    education: str = Field(
        default="",
        description="教育背景, 1行: 学校 专业 学历 时间"
    )
    summary: str = Field(
        default="",
        description="候选人核心背景概括, 100字以内"
    )
