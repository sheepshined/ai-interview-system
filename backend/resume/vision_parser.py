"""
resume/vision_parser.py — 视觉模型简历解析 (扫描件/图片型 PDF 兜底)

适用场景: pdfplumber 无法提取文字(扫描件、图片型 PDF)时,
将每页渲染为图片, 调用千问视觉模型 (qwen-vl, DashScope OpenAI 兼容接口)
一次性输出"全文转写 + 结构化字段"的 JSON。

依赖:
  - PyMuPDF (fitz): PDF 页渲染为 PNG
  - DASHSCOPE_API_KEY: 系统环境变量或 .env (未配置则 vision_available()=False,
    parse_resume 直接走原失败路径, 行为与接入前一致)

输出 dict 结构与 resume.parser.parse_resume 完全一致, 下游零改动。
"""
import base64
import logging
import os
from typing import Dict, List, Optional

import config
from common import extract_json_object

logger = logging.getLogger(__name__)

# 渲染 DPI: 150 兼顾清晰度与 token 成本 (一页约 1-2k tokens)
_RENDER_DPI = 150
# 最多发送的页数 (简历一般 1-3 页, 防超长文档打爆 token)
_MAX_PAGES = 5

_VISION_SYSTEM = """你是简历解析助手。用户会给你一份简历的页面图片(可能是扫描件)。
请仔细观察图片内容, 输出一个纯 JSON 对象(不要代码块, 不要解释文字), 字段如下:

{
  "raw_text": "将图片中的简历文字完整转写为纯文本(保留换行)",
  "name": "姓名(中英文均可), 无则留空",
  "skills": ["所有技术技能关键词, 按出现顺序去重"],
  "experience": "每段工作经历压缩为一行: 公司 职位 时间 | 1句核心成就, 多段换行",
  "projects": "每个项目压缩为一行: 项目名 | 技术栈 | 1句核心成果, 多个换行",
  "education": "1行: 学校 专业 学历 时间",
  "summary": "100字以内概括候选人核心背景"
}

要求: 只输出 JSON; 转写要忠实于图片内容, 不得虚构图片中不存在的信息。"""


def vision_available() -> bool:
    """视觉解析是否可用 (Key 已配置且 PyMuPDF 可导入)"""
    if not config.DASHSCOPE_API_KEY:
        return False
    try:
        import pymupdf  # noqa: F401
    except ImportError:
        return False
    return True


def pdf_to_base64_images(pdf_path: str, max_pages: int = _MAX_PAGES) -> List[str]:
    """将 PDF 每页渲染为 PNG 并转 base64 (用于 OpenAI 兼容接口的 image_url)

    Returns:
        base64 字符串列表 (无 data URI 前缀); 失败返回空列表
    """
    import pymupdf

    images: List[str] = []
    try:
        with pymupdf.open(pdf_path) as doc:
            zoom = _RENDER_DPI / 72
            matrix = pymupdf.Matrix(zoom, zoom)
            for page in doc:
                if len(images) >= max_pages:
                    logger.warning("简历页数超过 %d, 仅解析前 %d 页", max_pages, max_pages)
                    break
                pixmap = page.get_pixmap(matrix=matrix)
                images.append(base64.b64encode(pixmap.tobytes("png")).decode("ascii"))
    except Exception as exc:
        logger.warning("PDF 渲染图片失败: %s", exc)
        return []
    return images


def parse_resume_by_vision(pdf_path: str) -> Optional[Dict]:
    """视觉模型解析简历, 返回与 parser.parse_resume 相同的 dict 结构

    Returns:
        结构化 dict; 不可用/失败返回 None (调用方按原失败路径处理)
    """
    if not vision_available():
        logger.info("视觉解析不可用 (未配置 DASHSCOPE_API_KEY 或缺少 PyMuPDF)")
        return None

    images = pdf_to_base64_images(pdf_path)
    if not images:
        return None

    # 构造多模态消息 (OpenAI 兼容格式)
    content: List[Dict] = [
        {"type": "text", "text": f"以下是简历的 {len(images)} 页图片, 请解析:"}
    ]
    for img in images:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{img}"},
        })

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=config.DASHSCOPE_API_KEY,
            base_url=config.VISION_BASE_URL,
            timeout=120,
        )
        response = client.chat.completions.create(
            model=config.VISION_MODEL,
            messages=[
                {"role": "system", "content": _VISION_SYSTEM},
                {"role": "user", "content": content},
            ],
            temperature=0,
            max_tokens=4000,
        )
        text = (response.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.warning("视觉模型调用失败: %s", exc)
        return None

    data = extract_json_object(text)
    if data is None:
        logger.warning("视觉模型输出无法解析为 JSON: %s", text[:200])
        return None

    raw_text = str(data.get("raw_text", "") or "")
    if not raw_text.strip():
        logger.warning("视觉模型未转写出任何文字")
        return None

    # 联系方式走 parser 的确定性正则 (与主路径一致, 更可靠)
    from resume.parser import _extract_contact

    contact = _extract_contact(raw_text)
    skills = data.get("skills", [])
    if not isinstance(skills, list):
        skills = []
    skills = [str(s).strip() for s in skills if str(s).strip()]

    return {
        "raw_text": raw_text,
        "summary": str(data.get("summary", "") or ""),
        "skills": skills,
        "name": str(data.get("name", "") or ""),
        "phone": contact["phone"],
        "email": contact["email"],
        "location": contact["location"],
        "experience": str(data.get("experience", "") or ""),
        "projects": str(data.get("projects", "") or ""),
        "education": str(data.get("education", "") or ""),
        "char_count": len(raw_text),
        "parse_mode": "vision",  # 标识来源, 便于排查
    }
