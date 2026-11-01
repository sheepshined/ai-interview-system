"""
common.py — 跨模块公共工具

集中存放被多处重复的逻辑: 岗位匹配、难度标签、技能提取、JSON 容错解析。
消除 server.py / main.py / chains.py / llm_parser.py / parser.py 之间的重复代码。
"""
import json
import re
from typing import Optional, Dict, List, Tuple

import config


# ============================================================
# 难度标签
# ============================================================

def get_difficulty_label(difficulty: int) -> str:
    """难度数字 → 文字标签 (1=Junior, 2=Intermediate, 3=Senior)"""
    return config.DIFFICULTY_LABELS.get(difficulty, "Intermediate")


# ============================================================
# 岗位匹配
# ============================================================

def match_role(skills: List[str]) -> Tuple[Optional[str], int]:
    """根据技能列表匹配最佳岗位

    遍历 config.ROLES, 计算每个岗位 tags 与 skills 的匹配数, 返回最佳岗位。

    Args:
        skills: 从简历提取的技能列表

    Returns:
        (best_role_key, best_score), 无匹配时 best_role_key 为 None
    """
    best_role: Optional[str] = None
    best_score = 0
    for rk, ri in config.ROLES.items():
        match = sum(
            1 for t in ri["tags"] if any(t.lower() in s.lower() for s in skills)
        )
        if match > best_score:
            best_score = match
            best_role = rk
    return best_role, best_score


def score_roles(skills: List[str]) -> List[Tuple[str, int]]:
    """计算所有岗位的匹配分, 按分数降序返回 [(role_key, score), ...]

    供 CLI 展示全部岗位匹配排名 (match_role 只返回最佳)。
    """
    scores = []
    for rk, ri in config.ROLES.items():
        match = sum(1 for t in ri["tags"] if any(
            t.lower() in s.lower() for s in skills))
        scores.append((rk, match))
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores


# ============================================================
# 技能关键词表 (resume 规则提取 + server 文本简历解析共用)
# ============================================================

TECH_KEYWORDS: List[str] = [
    "Python", "Java", "JavaScript", "TypeScript", "Go", "Rust", "C++", "C#",
        "SQL", "Shell", "PHP", "Ruby", "Scala", "Kotlin", "Swift", "Node.js",
    "HTML", "CSS", "React", "Vue", "Vue.js", "Angular", "Next.js",
    "Django", "DRF", "Flask", "FastAPI", "Spring", "Spring Boot",
    "Express", "NestJS", "Gin", "Rails", "Laravel",
    "SQLAlchemy", "Celery", "pytest", "requests", "Pydantic",
    "MySQL", "PostgreSQL", "MongoDB", "Redis", "Elasticsearch", "Oracle",
    "SQLite", "ClickHouse", "Neo4j",
    "Docker", "Kubernetes", "K8s", "AWS", "Azure", "GCP",
    "CI/CD", "Jenkins", "GitHub Actions", "Terraform", "Ansible",
    "Nginx", "Apache", "Linux", "Helm", "Prometheus", "Grafana", "ELK",
    "Spark", "Hadoop", "Flink", "Kafka", "RabbitMQ", "Airflow",
    "TensorFlow", "PyTorch", "Pandas", "NumPy", "Scikit-learn",
    "LangChain", "Transformers", "FAISS", "Chroma", "BGE",
    "Git", "GitHub", "GitLab", "Jira", "Figma",
    "RESTful", "gRPC", "GraphQL", "Microservices",
]


def extract_skills(text: str) -> List[str]:
    """从文本中提取技能关键词 (基于 TECH_KEYWORDS 词表, 带词边界防子串误匹配)

    例: "SQL" 不会在 "MySQL" 中间误命中 (用负向断言)。
    """
    text_lower = text.lower()
    found: List[str] = []
    for kw in TECH_KEYWORDS:
        kw_lower = kw.lower()
        if kw_lower in text_lower and kw not in found:
            pattern = rf"(?<![a-z0-9#.+]){re.escape(kw_lower)}(?![a-z0-9])"
            if re.search(pattern, text_lower):
                found.append(kw)
    return found


# ============================================================
# JSON 容错解析 (供 RobustScoreParser / parse_resume_info 共用)
# ============================================================

def extract_json_object(text: str) -> Optional[dict]:
    """从 LLM 输出中提取 JSON 对象 (带容错)

    策略:
      1. 剥离 markdown 代码块 (```json ... ```)
      2. 直接 json.loads
      3. 正则提取最外层花括号块
      4. 平衡花括号匹配

    Returns:
        解析成功返回 dict, 全部失败返回 None
    """
    if not text:
        return None

    cleaned = text.strip()

    # Step 1: 剥离 markdown 代码块
    code_block = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if code_block:
        cleaned = code_block.group(1).strip()

    # Step 2: 直接解析
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        pass

    # Step 3: 正则提取最外层花括号
    try:
        match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except (json.JSONDecodeError, TypeError):
        pass

    # Step 4: 平衡花括号匹配
    json_str = _balanced_json_extract(cleaned)
    if json_str:
        try:
            return json.loads(json_str)
        except (json.JSONDecodeError, TypeError):
            pass

    return None


def _balanced_json_extract(text: str) -> Optional[str]:
    """平衡花括号匹配, 返回第一个完整的 {...} 字符串"""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None
