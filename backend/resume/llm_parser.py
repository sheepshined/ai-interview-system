"""
resume/llm_parser.py — LLM 简历提取 (主路径)

使用 LangChain LCEL Chain 调用 LLM 提取结构化简历信息。
从 agent/chains.py 和 agent/prompts.py 迁移至此, 使简历模块的依赖方向收拢。

对外暴露:
  - llm_extract(text) -> Optional[ResumeInfo]   核心入口
  - build_resume_extract_chain(llm)              Chain 构建器
  - get_resume_format_instructions() -> str      格式指令
"""
from typing import Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import StrOutputParser, PydanticOutputParser

from common import extract_json_object
from resume.models import ResumeInfo


# ============================================================

_RESUME_SYSTEM = """你是简历解析助手。从简历文本中提取关键信息, 输出精简的结构化结果。

要求:
  1. name: 姓名(中英文均可), 无则留空
  2. skills: 所有技术技能关键词, 按出现顺序去重, 不限于编程语言也包括框架/工具/数据库/云服务
  3. experience: 每段工作经历压缩为一行, 格式: "公司 职位 时间 | 1句核心成就", 多段换行
  4. projects: 每个项目压缩为一行, 格式: "项目名 | 技术栈 | 1句核心成果", 多个换行
  5. education: 1行, "学校 专业 学历 时间"
  6. summary: 100字以内概括候选人核心背景

只输出结构化结果, 不要输出其他内容。

{format_instructions}"""

_RESUME_USER = """简历文本:
{resume_text}"""

resume_extract_prompt = ChatPromptTemplate.from_messages([
    ("system", _RESUME_SYSTEM),
    ("human", _RESUME_USER),
])


# ============================================================
# Chain 构建 (从 agent/chains.py 迁移)
# ============================================================

def build_resume_extract_chain(llm: BaseChatModel):
    """构建简历解析 Chain

    Chain: resume_extract_prompt | llm | StrOutputParser | parse_resume_info

    输入参数:
        resume_text, format_instructions
    """
    return resume_extract_prompt | llm | StrOutputParser() | parse_resume_info


def get_resume_format_instructions() -> str:
    """获取 ResumeInfo 的 PydanticOutputParser 格式指令"""
    parser = PydanticOutputParser(pydantic_object=ResumeInfo)
    return parser.get_format_instructions()


# ============================================================
# JSON 解析 (带容错)
# ============================================================

def parse_resume_info(text: str) -> ResumeInfo:
    """解析 LLM 输出为 ResumeInfo, 带容错

    委托 common.extract_json_object 完成 JSON 提取
    (剥离代码块 → 直接解析 → 正则 → 平衡花括号)。
    """
    if not text:
        return ResumeInfo()

    data = extract_json_object(text)
    if data is None:
        return ResumeInfo()
    return _dict_to_resume_info(data)


def _dict_to_resume_info(data: dict) -> ResumeInfo:
    """将字典转换为 ResumeInfo"""
    return ResumeInfo(
        name=data.get("name", ""),
        skills=data.get("skills", []) if isinstance(data.get("skills"), list) else [],
        experience=data.get("experience", ""),
        projects=data.get("projects", ""),
        education=data.get("education", ""),
        summary=data.get("summary", ""),
    )


# ============================================================
# 核心入口
# ============================================================

def llm_extract(text: str) -> Optional[ResumeInfo]:
    """调用 LLM 提取结构化简历信息

    Args:
        text: PDF 提取的原始文本 (截断到 4000 字)

    Returns:
        ResumeInfo 对象, LLM 不可用时返回 None (由调用方回退规则提取)
    """
    try:
        from agent.llm import get_llm

        # 简历解析设 30s 超时上限, 避免上传接口长时间卡住
        llm = get_llm(temperature=0, max_tokens=2000, timeout=30)
        chain = build_resume_extract_chain(llm)
        format_instructions = get_resume_format_instructions()

        result = chain.invoke({
            "resume_text": text[:4000],
            "format_instructions": format_instructions,
        })
        return result
    except Exception as e:
        print(f"[WARN] LLM 简历解析失败 (将回退规则提取): {e}")
        return None
