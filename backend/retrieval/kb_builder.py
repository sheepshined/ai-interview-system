"""
retrieval/kb_builder.py — 离线知识库构建器 (LangChain 版)

使用 LangChain Chroma 向量存储构建面试题库。
解析 .md 题库文件, 向量化后存入 ChromaDB。

题库格式 (每道题用 --- 分隔):
  <!-- id:py_001 | category:基础 | difficulty:1 | difficulty_label:初级 | type:knowledge -->
  ### Q: 题目文本
  ### SCENARIO: 场景描述 (可选, 场景题用, 供面试官自然引入)
  ### A: 标准答案
  ### S: 得分点/评分要点列表
  ### GOOD: 好答案特征列表 (可选, 报告展示"好答案 vs 差答案"对比)
  ### BAD: 差答案特征列表 (可选)
  ### FOLLOWUP: 预设追问方向列表 (可选, 场景题建议提供)
"""
import os
import re
import logging
from typing import List, Dict

from langchain_chroma import Chroma
from langchain_core.documents import Document

import config
from retrieval.embeddings import get_embeddings

logger = logging.getLogger(__name__)


def parse_questions_from_file(filepath: str) -> List[Dict]:
    """解析单个 .md 题库文件, 提取每道题的结构化信息"""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 按 --- 分割, 每道题独立
    blocks = re.split(r"\n---\n", content)
    questions = []

    for block in blocks:
        if not block.strip():
            continue

        # 提取元信息 <!-- id:xxx | category:xxx | difficulty:x | difficulty_label:xxx | type:xxx -->
        meta_match = re.search(r"<!--\s*(.*?)\s*-->", block)
        meta = {"id": "", "category": "", "difficulty": "2", "difficulty_label": "中级", "type": "knowledge"}
        if meta_match:                  #group(1) 捕获纯净文本
            pairs = meta_match.group(1).split("|")   #  管道符切割元信息【id:xxx | category:xxx | difficulty:x | difficulty_label:xxx | type:xxx】
            for pair in pairs:
                kv = pair.strip().split(":", 1)    #  冒号切割元信息
                if len(kv) == 2:
                    meta[kv[0].strip()] = kv[1].strip()

        # 提取 Q / SCENARIO / A / S / GOOD / BAD / FOLLOWUP 字段
        q_match = re.search(r"### Q:\s*(.*?)(?=\n###|$)", block, re.DOTALL)
        scenario_match = re.search(r"### SCENARIO:\s*(.*?)(?=\n###|$)", block, re.DOTALL)
        a_match = re.search(r"### A:\s*(.*?)(?=\n###|$)", block, re.DOTALL)
        s_match = re.search(r"### S:\s*(.*?)(?=\n###|$)", block, re.DOTALL)
        good_match = re.search(r"### GOOD:\s*(.*?)(?=\n###|$)", block, re.DOTALL)
        bad_match = re.search(r"### BAD:\s*(.*?)(?=\n###|$)", block, re.DOTALL)
        followup_match = re.search(r"### FOLLOWUP:\s*(.*?)(?=\n###|$)", block, re.DOTALL)

        if not q_match or not a_match:
            continue

        question_text = q_match.group(1).strip()
        answer_text = a_match.group(1).strip()
        scenario_text = scenario_match.group(1).strip() if scenario_match else ""

        def _parse_list(match):
            """提取以 '- ' 开头的列表项"""
            if not match:
                return []
            return [
                line.strip("- ").strip()
                for line in match.group(1).strip().split("\n")
                if line.strip().startswith("-")
            ]

        scoring_lines = _parse_list(s_match)
        good_lines = _parse_list(good_match)
        bad_lines = _parse_list(bad_match)
        followup_lines = _parse_list(followup_match)

        # 规范化 type: 只接受 knowledge / scenario, 其他值回落 knowledge
        question_type = meta.get("type", "knowledge").strip().lower()
        if question_type not in {"knowledge", "scenario"}:
            question_type = "knowledge"

        questions.append({
            "id": meta["id"],
            "category": meta["category"],
            "difficulty": int(meta["difficulty"]),
            "difficulty_label": meta["difficulty_label"],
            "type": question_type,
            "scenario": scenario_text,
            "question": question_text,
            "answer": answer_text,
            "scoring_points": scoring_lines,
            "good_points": good_lines,
            "bad_points": bad_lines,
            "followup_directions": followup_lines,
            "max_score": 10,
        })

    return questions


class KnowledgeBaseBuilder:
    """离线知识库构建器 (LangChain Chroma 版)"""

    def __init__(self, data_dir=None, chroma_path=None):
        self.data_dir = data_dir or config.DATA_DIR
        self.chroma_path = chroma_path or config.CHROMA_DB_PATH
        self.collection_name = config.COLLECTION_NAME

    def load_all_questions(self) -> List[Dict]:
        """遍历 data/ 下所有 .md 文件, 解析全部题目"""
        all_questions = []
        for filename in sorted(os.listdir(self.data_dir)):
            if not filename.endswith(".md"):
                continue
            filepath = os.path.join(self.data_dir, filename)
            role = filename.replace(".md", "")
            questions = parse_questions_from_file(filepath)
            for q in questions:
                q["role"] = role
                q["source_file"] = filename
            all_questions.extend(questions)         # 加入末尾 合并所有角色的题目[python_dev,java_dev]
            print(f"  {filename}: 解析出 {len(questions)} 道题")
        return all_questions

    def build(self, force_recreate=True):
        """离线建库主流程"""
        print("=" * 60)
        print("[Build] 知识库离线构建 (LangChain Chroma 版)")
        print("=" * 60)

        # Step 1: 解析题库
        print("\n[1/3] 解析面试题库...")
        questions = self.load_all_questions()
        if not questions:
            print("[ERROR] 没有解析到题目, 请检查 data/ 目录下的 .md 文件格式")
            return False
        print(f"  共解析 {len(questions)} 道题")

        # Step 2: 加载 Embeddings + 创建 ChromaDB
        print("\n[2/3] 加载 BGE 模型并创建 ChromaDB...")
        print(f"  模型路径: {config.EMBEDDING_MODEL_PATH}")
        os.makedirs(self.chroma_path, exist_ok=True)

        embeddings = get_embeddings()           #  加载agent.llm 里面实例化的 BGE 模型, 用于向量化题目

        # 如果强制重建, 先删除旧集合
        if force_recreate:
            import chromadb
            client = chromadb.PersistentClient(path=self.chroma_path)
            try:
                client.delete_collection(self.collection_name)
                print("  已清空旧向量库 (将重建)")
            except Exception as e:
                logger.warning("清空旧集合失败 (首次构建时正常, 忽略): %s", e)

        # Step 3: 构建 LangChain Document 列表并写入 Chroma
        print("\n[3/3] 向量化并存入 ChromaDB...")

        documents = []
        ids = []

        for q in questions:
            qid = q["id"] or f"{q['role']}_{q['category']}_{len(ids)+1}"

            # 检索键 = 题目文本 (+ 场景/分类, 帮助场景题被关键词命中, 不含答案避免泄漏)
            searchable = q["question"]
            if q.get("scenario"):
                searchable += f"\n场景: {q['scenario']}"
            if q.get("category"):
                searchable += f"\n分类: {q['category']}"
            if q.get("type") == "scenario":
                searchable += "\n类型: 场景设计题"

            # 检索键 = 题目文本 (不含答案, 避免答案泄漏到检索阶段)
            doc = Document(
                page_content=searchable,
                metadata={
                    "source_file": q["source_file"],
                    "role": q["role"],
                    "category": q["category"],
                    "difficulty": q["difficulty"],
                    "difficulty_label": q["difficulty_label"],
                    "type": q.get("type", "knowledge"),
                    # 答案 + 得分点存在 metadata 中, 评分阶段单独取出
                    "answer": q["answer"],
                    "scoring_points": "||".join(q["scoring_points"]),
                    "good_points": "||".join(q.get("good_points", [])),
                    "bad_points": "||".join(q.get("bad_points", [])),
                    "scenario": q.get("scenario", ""),
                    "followup_directions": "||".join(q.get("followup_directions", [])),
                    "max_score": q["max_score"],
                },
            )
            documents.append(doc)
            ids.append(qid)

        # 使用 LangChain Chroma 批量写入
        vectorstore = Chroma.from_documents(
            documents=documents,
            embedding=embeddings,
            ids=ids,
            collection_name=self.collection_name,
            persist_directory=self.chroma_path,
            collection_metadata={"hnsw:space": "cosine"},
        )

        print(f"\n[OK] 知识库构建完成!")
        print(f"  题目总数: {len(questions)}")
        print(f"  ChromaDB: {os.path.abspath(self.chroma_path)}")
        print("  下一步: 启动 FastAPI 与 Vite 前端")

        # 按角色统计
        role_counts = {}
        for q in questions:
            role_counts[q["role"]] = role_counts.get(q["role"], 0) + 1  # 各角色题量: {'Java': 15, 'Python': 12, '前端': 8}
        print(f"  各角色题量: {role_counts}")
        return True


if __name__ == "__main__":
    builder = KnowledgeBaseBuilder()
    builder.build()
