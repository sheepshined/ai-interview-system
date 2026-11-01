"""qbank_admin.py — 题库管理 (管理员专用, v1.3)

题库的唯一事实源是 backend/data/<role>.md (kb_builder 的解析格式),
向量索引只是它的派生物。因此管理操作全部落在 markdown 上:

- import_questions: 校验结构化题目 (JSON), 序列化为题库 markdown 块并原子追加;
- delete_question: 按 id 定位所在文件, 删除对应 --- 块后原子重写;
- load_questions: 解析当前全部题目 (复用 kb_builder.parse_questions_from_file);
- stats: 按分类/难度/类型聚合 + 向量索引状态 (由调用方传入索引计数);
- rebuild_index: 运行时重建 Chroma (KnowledgeBaseBuilder) 并清空检索器缓存。

并发约束: 重建期间进行中的面试查询可能短暂失败 (集合被删除重建),
管理端需提示"建议在无进行中面试时重建"。重建互斥由模块级 asyncio.Lock 保证。
"""
import asyncio
import logging
import os
import re
import threading
import uuid
from collections import Counter
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

DIFFICULTY_LABELS = {1: "初级", 2: "中级", 3: "高级"}
VALID_TYPES = {"knowledge", "scenario"}
# id 禁止首尾横线: 删除定位用 \bid:...\b 词边界, 尾横线后接空格时无词边界会永远删不掉
_ID_RE = re.compile(r"^(?!-)[A-Za-z0-9_\-]+(?<!-)$")

# 题库 markdown 块结构保留序列:
# - 行首的 --- / ### / <!-- 会劈开分块或新增块级结构;
# - 行内的 ### 字段标记同样危险——kb_builder 的字段正则未锚定行首,
#   answer 里出现 "### S:" 会劫持解析、静默顶替真实字段。
# 因此在单点校验直接拒绝 (清洗会掩盖用户意图)。
_RESERVED_BLOCK_RE = re.compile(r"(^|\n)\s*(---|###|<!--)\s*")
_RESERVED_INLINE_RE = re.compile(r"###\s*(?:Q|A|SCENARIO|S|GOOD|BAD|FOLLOWUP)\s*:")

_rebuild_lock = asyncio.Lock()
# import/delete 是同步端点 (线程池), 与 rebuild 的 asyncio 锁分开;
# RLock: existing_ids_for 与 import_questions 可嵌套获取而不死锁
_file_lock = threading.RLock()


class ImportError_(ValueError):
    """题目导入校验失败 (携带逐条错误)。"""


def _check_reserved(text: str, where: str, field: str, errors: List[str]) -> bool:
    """内容含块结构保留序列时记一条错误, 返回是否违规。"""
    if not text:
        return False
    if _RESERVED_BLOCK_RE.search(text):
        errors.append(f"{where}: {field} 含题库保留序列 (独立成行的 --- / ### / <!--), "
                      f"会破坏题库文件结构, 请改写后重试")
        return True
    if _RESERVED_INLINE_RE.search(text):
        errors.append(f"{where}: {field} 含行内字段标记 (如 '### S:'), "
                      f"会在重建时劫持题目字段, 请改写后重试")
        return True
    return False


def _sanitize_meta(value: str) -> str:
    """元信息不能包含块分隔符/管道/注释闭合, 出现即清洗。"""
    return str(value or "").replace("|", "/").replace("-->", "").replace("\n", " ").strip()


def _ensure_meta_block(content: str) -> str:
    """新文件需要文件头; 已有内容不动。"""
    if content.strip():
        return content
    return "# 大模型应用开发工程师面试题库\n"


def validate_questions(items: List[dict], existing_ids: List[str]) -> tuple:
    """校验导入题目, 返回 (normalized, errors)。

    规则: question/answer 非空且不含题库保留序列; difficulty∈1-3; type 合法;
    id 匹配 [A-Za-z0-9_-] 且唯一 (与现有题库、与本批次内都不得冲突;
    缺省自动生成 imp_<uuid8>); 列表项内部换行清洗为空格。
    """
    normalized: List[dict] = []
    errors: List[str] = []
    seen = set(existing_ids)
    for idx, item in enumerate(items):
        where = f"第 {idx + 1} 条"
        if not isinstance(item, dict):
            errors.append(f"{where}: 不是对象")
            continue
        question = str(item.get("question") or "").strip()
        answer = str(item.get("answer") or "").strip()
        scenario = str(item.get("scenario") or "").strip()
        if not question:
            errors.append(f"{where}: question 为空")
            continue
        if not answer:
            errors.append(f"{where}: answer 为空")
            continue
        if _check_reserved(question, where, "question", errors):
            continue
        if _check_reserved(answer, where, "answer", errors):
            continue
        if _check_reserved(scenario, where, "scenario", errors):
            continue
        try:
            difficulty = int(item.get("difficulty", 2))
        except (TypeError, ValueError):
            difficulty = 0
        if difficulty not in DIFFICULTY_LABELS:
            errors.append(f"{where}: difficulty 须为 1/2/3")
            continue
        qtype = str(item.get("type") or "knowledge").strip().lower()
        if qtype not in VALID_TYPES:
            errors.append(f"{where}: type 须为 knowledge 或 scenario")
            continue

        qid = str(item.get("id") or "").strip()
        if qid:
            if not _ID_RE.fullmatch(qid):
                errors.append(f"{where}: id 须为字母/数字/下划线/短横线, 得到 '{qid}'")
                continue
            if qid in seen:
                errors.append(f"{where}: 题目 id '{qid}' 与现有题库或本批次重复")
                continue
        else:
            qid = f"imp_{uuid.uuid4().hex[:8]}"
            while qid in seen:
                qid = f"imp_{uuid.uuid4().hex[:8]}"
        seen.add(qid)

        def _str_list(value) -> List[str]:
            if isinstance(value, str):
                raw = [line.strip() for line in value.splitlines() if line.strip()]
            elif isinstance(value, list):
                raw = [str(v).strip() for v in value if str(v).strip()]
            else:
                raw = []
            # 列表项内部换行会被解析器截断, 清洗为分号保持单行
            return [re.sub(r"\s*\n\s*", "；", v) for v in raw]

        # 列表项以 "- " 开头或为纯横线时, 解析器的 strip("- ") 会吃掉内容
        bad_list_item = False
        for field in ("scoring_points", "good_points", "bad_points", "followup_directions"):
            for v in _str_list(item.get(field)):
                if v.startswith("- ") or re.fullmatch(r"-+", v):
                    errors.append(f"{where}: {field} 的列表项 '{v[:30]}' 以横线开头/由横线组成, "
                                  f"解析时会被当作列表标记吃掉, 请改写")
                    bad_list_item = True
                    break
            if bad_list_item:
                break
        if bad_list_item:
            continue

        normalized.append({
            "id": qid,
            "category": _sanitize_meta(str(item.get("category") or "未分类")) or "未分类",
            "difficulty": difficulty,
            "difficulty_label": DIFFICULTY_LABELS[difficulty],
            "type": qtype,
            "scenario": scenario,
            "question": question,
            "answer": answer,
            "scoring_points": _str_list(item.get("scoring_points")),
            "good_points": _str_list(item.get("good_points")),
            "bad_points": _str_list(item.get("bad_points")),
            "followup_directions": _str_list(item.get("followup_directions")),
        })
    return normalized, errors


def render_question_markdown(q: dict) -> str:
    """把一道题序列化为题库 markdown 块 (与 kb_builder 解析格式一致)。"""
    difficulty = int(q.get("difficulty", 2))
    label = q.get("difficulty_label") or DIFFICULTY_LABELS.get(difficulty, "中级")
    meta = (f"id:{q['id']} | category:{_sanitize_meta(q['category'])} | "
            f"difficulty:{difficulty} | difficulty_label:{label} | "
            f"type:{q['type']}")
    lines = [
        "---",
        f"<!-- {meta} -->",
        f"### Q: {q['question']}",
    ]
    if q.get("scenario"):
        lines.append(f"### SCENARIO: {q['scenario']}")
    lines.append("### A:")
    lines.append(q["answer"])
    for key, header in (("scoring_points", "S"), ("good_points", "GOOD"),
                        ("bad_points", "BAD"), ("followup_directions", "FOLLOWUP")):
        items = q.get(key) or []
        if not items:
            continue
        lines.append(f"### {header}:")
        lines.extend(f"- {it}" for it in items)
    return "\n".join(lines)


def import_questions(data_path: str, items: List[dict], existing_ids: List[str],
                     dry_run: bool = False) -> dict:
    """校验并把通过的题目追加到题库 markdown; 返回导入报告。

    写入为原子追加: 先写完整新内容到 <file>.tmp 再 os.replace。
    """
    normalized, errors = validate_questions(items, existing_ids)
    if dry_run:
        return {"validated": len(normalized), "errors": errors, "written": 0,
                "ids": [q["id"] for q in normalized]}
    if not normalized:
        return {"validated": 0, "errors": errors, "written": 0, "ids": []}

    block = "\n\n" + "\n\n".join(render_question_markdown(q) for q in normalized) + "\n"
    tmp_path = f"{data_path}.tmp"
    with _file_lock:
        with open(data_path, "r", encoding="utf-8") as f:
            content = f.read()
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(_ensure_meta_block(content) + block)
        os.replace(tmp_path, data_path)
    return {"validated": len(normalized), "errors": errors,
            "written": len(normalized), "ids": [q["id"] for q in normalized]}


def load_questions(data_dir: str) -> List[dict]:
    """解析 data/ 下全部题库 markdown (带 source_file), 供列表/统计/删除定位。"""
    from retrieval.kb_builder import parse_questions_from_file

    questions: List[dict] = []
    if not os.path.isdir(data_dir):
        return questions
    for filename in sorted(os.listdir(data_dir)):
        if not filename.endswith(".md"):
            continue
        parsed = parse_questions_from_file(os.path.join(data_dir, filename))
        for q in parsed:
            q["source_file"] = filename
            q["role"] = filename[:-3]
        questions.extend(parsed)
    return questions


def stats(questions: List[dict]) -> dict:
    """按分类/难度/类型聚合的确定性统计。"""
    by_category = Counter(q.get("category", "未分类") for q in questions)
    by_difficulty = Counter(str(q.get("difficulty", 2)) for q in questions)
    by_type = Counter(q.get("type", "knowledge") for q in questions)
    return {
        "total": len(questions),
        "categories": [{"name": k, "count": v}
                       for k, v in sorted(by_category.items(), key=lambda kv: -kv[1])],
        "difficulty": {k: by_difficulty.get(k, 0) for k in ("1", "2", "3")},
        "type": {k: by_type.get(k, 0) for k in ("knowledge", "scenario")},
        "ids": [q["id"] for q in questions],
    }


def existing_ids_for(data_path: str) -> List[str]:
    """读取某题库文件的现有题目 id (锁内), 供导入去重使用。"""
    from retrieval.kb_builder import parse_questions_from_file

    with _file_lock:
        if not os.path.isfile(data_path):
            return []
        return [q["id"] for q in parse_questions_from_file(data_path)]


def delete_question(data_dir: str, question_id: str) -> dict:
    """从题库 markdown 中删除一道题 (按 id 定位块), 读与写在同一把锁内, 原子重写。

    返回 {deleted: bool, source_file}: id 不存在或重复出现时报错。
    """
    pattern = re.compile(r"<!--\s*.*?\bid:" + re.escape(question_id) + r"\b.*?-->")
    for filename in sorted(os.listdir(data_dir)):
        if not filename.endswith(".md"):
            continue
        path = os.path.join(data_dir, filename)
        with _file_lock:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            if not pattern.search(content):
                continue
            # 块以 --- 分隔; 定位包含该 id 的块并整体移除
            blocks = re.split(r"\n---\n", content)
            kept = [b for b in blocks if not pattern.search(b)]
            removed = len(blocks) - len(kept)
            if removed != 1:
                raise ValueError(f"题库中 id '{question_id}' 出现 {removed} 次, 拒绝删除")
            tmp_path = f"{path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write("\n---\n".join(kept))
            os.replace(tmp_path, path)
        return {"deleted": True, "source_file": filename}
    return {"deleted": False, "source_file": ""}


async def rebuild_index(retriever_holder, data_dir: str, chroma_path: str) -> dict:
    """运行时重建向量索引并清空检索器缓存 (互斥; 不校验进行中的面试)。

    retriever_holder: 可调用, 返回当前 HybridRetriever 单例 (重建后调用其 reload())。
    """
    async with _rebuild_lock:
        def _build():
            from retrieval.kb_builder import KnowledgeBaseBuilder

            builder = KnowledgeBaseBuilder(data_dir=data_dir, chroma_path=chroma_path)
            return builder.build(force_recreate=True)

        ok = await asyncio.to_thread(_build)
        if not ok:
            return {"ok": False, "message": "题库解析为空, 重建已取消 (原索引未受影响)"}
        try:
            retriever = retriever_holder()
            if retriever is not None and hasattr(retriever, "reload"):
                await asyncio.to_thread(retriever.reload)
        except Exception:
            logger.warning("检索器缓存刷新失败 (重启后自愈)", exc_info=True)
        questions = load_questions(data_dir)
        return {"ok": True, "total": len(questions),
                "message": f"重建完成, 当前题库 {len(questions)} 题"}
