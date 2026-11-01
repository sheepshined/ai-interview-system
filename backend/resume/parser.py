"""
resume/parser.py — PDF 简历解析模块

混合策略:
  1. pdfplumber 提取原始文本 (确定性)
  2. 正则提取 phone/email/location (确定性, 可靠)
  3. LLM 提取 name/skills/experience/projects/education/summary (语义理解, 普适)
  4. LLM 失败时回退到规则提取 (兜底)
"""
import os
import re
from typing import Dict, Optional


def parse_resume(pdf_path: str) -> Optional[Dict]:
    """解析 PDF 简历, 返回结构化内容

    Returns:
        {
            "raw_text": "完整文本",
            "summary": "摘要",
            "skills": ["Python", "Django", ...],
            "experience": "工作经历",
            "projects": "项目经历",
            "education": "教育背景",
            "name": "姓名",
            "phone": "电话",
            "email": "邮箱",
            "location": "城市",
            "char_count": 文本字符数
        }
        解析失败返回 None
    """
    try:
        import pdfplumber
    except ImportError:
        print("[ERROR] 请安装 pdfplumber: pip install pdfplumber")
        return None

    if not os.path.exists(pdf_path):
        print(f"[ERROR] 文件不存在: {pdf_path}")
        return None

    # ---- 1. 解析 PDF 文本 ----
    full_text_parts = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text_parts.append(text)
    except Exception as e:
        print(f"[ERROR] PDF 打开失败 (可能已加密): {e}")
        return None

    raw_text = "\n".join(full_text_parts)
    if not raw_text.strip():
        # 扫描件/图片型 PDF: 尝试视觉模型兜底 (千问 qwen-vl)
        from resume.vision_parser import parse_resume_by_vision, vision_available
        if vision_available():
            print("[INFO] 文本提取为空, 尝试视觉模型解析 (可能是扫描件)...")
            return parse_resume_by_vision(pdf_path)
        print("[ERROR] 无法从 PDF 中提取文字 (可能是扫描件, 未配置视觉模型则不支持 OCR)")
        return None

    return parse_resume_text(raw_text)


def parse_resume_text(raw_text: str) -> Optional[Dict]:
    """Parse already extracted resume text with the same pipeline as PDF input."""
    raw_text = _clean_text(raw_text or "")
    if not raw_text:
        return None

    # ---- 2. 正则提取确定性字段 ----
    contact = _extract_contact(raw_text)

    # ---- 3. LLM 提取语义字段 ----
    llm_result = _llm_extract(raw_text)

    if llm_result:
        # LLM 成功
        name = llm_result.name or _extract_name(raw_text)
        skills = llm_result.skills if llm_result.skills else _extract_skills(raw_text)
        experience = llm_result.experience or _extract_section(raw_text, [
            "工作经历", "工作经验", "职业经历", "Work Experience",
        ])
        projects = llm_result.projects or _extract_section(raw_text, [
            "项目经历", "项目经验", "项目背景", "主要项目",
        ])
        education = llm_result.education or _extract_section(raw_text, [
            "教育背景", "学历", "教育经历", "Education",
        ])
        summary = llm_result.summary or _build_summary(raw_text)
    else:
        # LLM 失败, 全部回退规则
        print("[WARN] LLM 解析不可用, 使用规则提取")
        name = _extract_name(raw_text)
        skills = _extract_skills(raw_text)
        experience = _extract_section(raw_text, [
            "工作经历", "工作经验", "职业经历", "Work Experience",
        ])
        projects = _extract_section(raw_text, [
            "项目经历", "项目经验", "项目背景", "主要项目",
        ])
        education = _extract_section(raw_text, [
            "教育背景", "学历", "教育经历", "Education",
        ])
        summary = _build_summary(raw_text)

    return {
        "raw_text": raw_text,
        "summary": summary,
        "skills": skills,
        "name": name,
        "phone": contact["phone"],
        "email": contact["email"],
        "location": contact["location"],
        "experience": experience,
        "projects": projects,
        "education": education,
        "char_count": len(raw_text),
    }


def build_resume_context(resume_data: Dict) -> str:
    """将简历数据转换为面试 Prompt 上下文 (严格控制在 800 字以内)
    主要控制 100<skill<200,150<exp<250,50<proj<100,50<edu<150"""
    parts = []
    budget = 800

    info_parts = []
    if resume_data.get("name"):
        info_parts.append(resume_data["name"])
    if resume_data.get("location"):
        info_parts.append(resume_data["location"])
    if resume_data.get("phone"):
        info_parts.append(resume_data["phone"])
    if resume_data.get("email"):
        info_parts.append(resume_data["email"])
    if info_parts:
        line = "候选人: " + " | ".join(info_parts)
        parts.append(line)
        budget -= len(line) + 2

    '''主要控制 100<skill<200,150<exp<250,50<proj<100,50<edu<150'''

    if resume_data.get("skills") and budget > 100:
        skills_str = "、".join(resume_data["skills"][:15])
        line = f"技能标签: {skills_str}"
        if len(line) > budget - 200:
            line = line[:budget - 203] + "..."
        parts.append(line)
        budget -= len(parts[-1]) + 2

    if resume_data.get("experience") and budget > 150:
        exp = resume_data["experience"]
        if len(exp) > budget - 250:
            exp = exp[:budget - 253] + "..."
        parts.append(f"工作经历: {exp}")
        budget -= len(parts[-1]) + 2

    if resume_data.get("projects") and budget > 100:
        proj = resume_data["projects"]
        if len(proj) > budget - 50:
            proj = proj[:budget - 53] + "..."
        parts.append(f"项目经历: {proj}")
        budget -= len(parts[-1]) + 2

    if resume_data.get("education") and budget > 50:
        edu = resume_data["education"][:budget - 53]
        parts.append(f"教育背景: {edu}")

    return "\n\n".join(parts)


# ============================================================
# LLM 提取 (主路径) — 委托给 resume.llm_parser
# ============================================================

def _llm_extract(text: str) -> Optional[object]:
    """调用 LLM 提取结构化简历信息

    Returns:
        ResumeInfo 对象, 失败返回 None
    """
    from resume.llm_parser import llm_extract
    return llm_extract(text)

# _______________________________________________________________________
# ============================================================
# 规则提取 (fallback)
# ============================================================

def _clean_text(text: str) -> str:
    """清洗 PDF 文本"""
    text = re.sub(r'第\s*\d+\s*页', '', text)
    text = re.sub(r'[-\s]*\d+\s*/\s*\d+\s*[-\s]*', ' ', text)
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    text = re.sub(r'[^\S\n]+', ' ', text)
    text = re.sub(r'\n{4,}', '\n\n\n', text)
    text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
    return text.strip()


def _extract_contact(text: str) -> Dict[str, str]:
    """提取联系方式: 电话 / 邮箱 / 城市"""
    result = {"phone": "", "email": "", "location": ""}

    phone_patterns = [
        r'1[3-9]\d{9}',
        r'\d{3}[-\s]\d{4}[-\s]\d{4}',
        r'\d{3}[-\s]\d{3}[-\s]\d{5}',
    ]
    for p in phone_patterns:
        m = re.search(p, text)
        if m:
            result["phone"] = m.group()
            break

    email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', text)
    if email_match:
        result["email"] = email_match.group()

    cities = [
        "北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京",
        "西安", "苏州", "长沙", "重庆", "天津", "青岛", "大连", "厦门",
        "宁波", "济南", "哈尔滨", "沈阳", "福州", "郑州", "昆明", "长春",
    ]
    for city in cities:
        if city in text:
            result["location"] = city
            break

    return result           #手机号和省份地址


def _extract_skills(text: str) -> list:
    """规则提取技能关键词 (fallback, 委托 common.extract_skills 统一词表)"""
    from common import extract_skills
    return extract_skills(text)


def _extract_name(text: str) -> str:
    """规则提取姓名 (fallback)"""
    patterns = [
        r'姓名[：:]\s*([一-鿿]{2,4})',
        r'([一-鿿]{2,4})\s*[男女]',
        r'([一-鿿]{2,4})\s*应聘',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)

    _NAME_BLACKLIST = {
        "个人简历", "基本信息", "联系方式", "个人中心", "求职意向",
        "教育背景", "工作经历", "项目经验", "专业技能", "自我评价",
        "本人求职", "应届毕业生", "往届毕业生", "联系电话", "电子邮箱",
        "通讯地址", "个人简介", "个人优势", "能力特长", "校园经历",
        "项目经历", "技能标签", "技术栈",
    }
    lines = [l.strip() for l in text.split('\n')[:5] if l.strip()]
    for line in lines:
        match = re.search(r'[一-鿿]{2,4}', line)
        if match and len(line) < 30 and match.group() not in _NAME_BLACKLIST:
            return match.group()
    return ""


def _extract_section(text: str, keywords: list) -> str:
    """规则提取段落 (fallback)"""
    lines = text.split('\n')

    for kw in keywords:
        kw_lower = kw.lower()
        start_idx = -1
        for i, line in enumerate(lines):
            if line.strip().lower().startswith(kw_lower):
                start_idx = i
                break
        if start_idx == -1:
            continue

        section_lines = []
        for j in range(start_idx + 1, len(lines)):
            line = lines[j].strip()
            if not line:
                if section_lines:
                    section_lines.append("")
                continue
            if _is_section_title(line):
                break
            section_lines.append(line)

        section_text = "\n".join(section_lines).strip()
        if section_text:
            return section_text[:800]
    return ""


_SECTION_TITLES = {
    "教育背景", "学历", "教育经历", "工作经历", "工作经验", "项目经验",
    "项目经历", "实习经历", "专业技能", "个人技能", "技能特长", "技术栈",
    "技能标签", "技能", "自我评价", "个人介绍", "个人简介", "联系方式",
    "基本信息", "求职意向", "校园经历", "获奖情况", "荣誉证书", "证书",
    "语言能力", "兴趣爱好", "个人优势", "能力特长",
    "Education", "Work Experience", "Projects", "Skills", "Summary",
}


def _is_section_title(line: str) -> bool:
    if len(line) <= 10 and line in _SECTION_TITLES:
        return True
    for title in _SECTION_TITLES:
        if line.startswith(title) and len(line) <= len(title) + 5:
            return True
    return False


def _build_summary(text: str) -> str:
    """规则构建摘要 (fallback)"""
    skip_search = ['@']
    lines = []
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
        if any(s in line for s in skip_search):
            continue
        if re.match(r'^[\d\s\-+()]+$', line):
            continue
        if _is_section_title(line):
            continue
        lines.append(line)
        if sum(len(l) for l in lines) >= 300:
            break
    return " ".join(lines)[:300]
