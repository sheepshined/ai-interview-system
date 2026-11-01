"""
retrieval/retriever.py — 混合检索器 (LangChain 版)

使用 LangChain 的 Chroma 向量存储 + BM25Retriever 关键词检索,
通过 Reciprocal Rank Fusion (RRF) 融合双路结果。

核心组件:
  - langchain_chroma.Chroma          → 向量检索
  - langchain_community.retrievers.BM25Retriever → 关键词检索
  - RRF 融合算法                      → 双路结果合并

接口兼容 InterviewRetriever, 保持业务逻辑不变。
"""
import os
import re
import random
from typing import List, Dict, Optional

import jieba
from langchain_chroma import Chroma
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document

import config
from retrieval.embeddings import get_embeddings


def _jieba_tokenize(text: str) -> List[str]:
    """jieba 中文分词 (用于 BM25 检索)"""
    return list(jieba.cut(text))


class HybridRetriever:
    """混合检索器 — BM25 + 向量双路检索 + RRF 融合

    出题阶段: get_question()  — 只检索题目文本, 不含答案
    评分阶段: get_answer()    — 按题号精确检索标准答案 + 得分点
    """

    def __init__(self, chroma_path: str = None, model_path: str = None):
        self.chroma_path = chroma_path or config.CHROMA_DB_PATH
        self.model_path = model_path or config.EMBEDDING_MODEL_PATH

        # 加载 Embeddings (全局缓存)
        print("[MODEL] 加载向量模型...")
        self.embeddings = get_embeddings()

        # 连接 Chroma 向量库
        self.vectorstore = Chroma(
            collection_name=config.COLLECTION_NAME,
            embedding_function=self.embeddings,
            persist_directory=self.chroma_path,
        )

        # BM25 检索器缓存 (按 role 缓存)
        self._bm25_cache: Dict[str, BM25Retriever] = {}
        # 标准答案缓存 (按 question_id, 题库不变则命中, 阶段3 提速)
        self._answer_cache: Dict[str, Dict] = {}

        print("[OK] 检索器就绪 (LangChain Hybrid)")

    def reload(self) -> None:
        """题库重建后调用: 重连向量集合并清空全部内存缓存。

        重建 (force_recreate) 会删除并重建同名 collection, 旧句柄会读到已删集合,
        因此必须重连; BM25 与标准答案缓存基于旧索引, 一并作废。
        """
        self.vectorstore = Chroma(
            collection_name=config.COLLECTION_NAME,
            embedding_function=self.embeddings,
            persist_directory=self.chroma_path,
        )
        self._bm25_cache = {}
        self._answer_cache = {}

    # ============================================================
    # BM25 检索器管理
    # ============================================================

    def _get_all_documents(self, role: str = None) -> List[Document]:
        """从 Chroma 中获取所有文档 (按 role 过滤)

        使用底层 collection 直接查询, 确保 ID 存入 metadata。
        """
        where_filter = {"role": role} if role else None
        results = self.vectorstore._collection.get(
            where=where_filter if where_filter else None,
            include=["documents", "metadatas"],
        )

        documents = []
        if results["ids"]:
            for i, doc_id in enumerate(results["ids"]):
                meta = results["metadatas"][i]
                # 确保 ID 在 metadata 中
                meta["id"] = doc_id
                documents.append(
                    Document(
                        page_content=results["documents"][i],
                        metadata=meta,
                    )
                )
        return documents

    def _get_bm25_retriever(self, role: str) -> BM25Retriever:
        """获取或创建指定 role 的 BM25 检索器 (带缓存)"""
        if role not in self._bm25_cache:
            docs = self._get_all_documents(role=role)
            if docs:
                self._bm25_cache[role] = BM25Retriever.from_documents(
                    docs,
                    preprocess_func=_jieba_tokenize,
                    k=config.TOP_K * 3,
                )
            else:
                self._bm25_cache[role] = None
        return self._bm25_cache[role]

    # ============================================================
    # 向量检索
    # ============================================================

    @staticmethod
    def _build_where_filter(role: str = None, difficulty: int = None) -> Optional[dict]:
        """构建 ChromaDB where 过滤条件 (ChromaDB 1.x 需要 $and 组合多条件)"""
        conditions = []
        if role:
            conditions.append({"role": role})
        if difficulty:
            conditions.append({"difficulty": difficulty})

        if not conditions:
            return None
        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}

    def _vector_search(
        self,
        topic: str,
        role: str = None,
        difficulty: int = None,
        top_k: int = 5,
    ) -> List[tuple]:
        """向量相似度检索

        使用底层 Chroma collection 直接查询, 确保 ID 可用。

        Returns:
            List of (doc_id, page_content, metadata, distance) tuples
        """
        where_filter = self._build_where_filter(role, difficulty)

        # 使用底层 collection 查询以获取文档 ID
        query_embedding = self.embeddings.embed_query(topic)
        results = self.vectorstore._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k * 3,
            where=where_filter,
            include=["documents", "distances", "metadatas"],
        )

        # 转换为统一格式: (doc_id, page_content, metadata, distance)
        output = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                page_content = results["documents"][0][i]
                metadata = results["metadatas"][0][i]
                distance = results["distances"][0][i] if results["distances"] else 0
                # 确保 ID 在 metadata 中
                metadata["id"] = doc_id
                output.append((doc_id, page_content, metadata, distance))

        return output

    # ============================================================
    # RRF 融合
    # ============================================================

    @staticmethod
    def _reciprocal_rank_fusion(
        vector_results: List[tuple],
        bm25_results: List[Document],
        exclude_ids: List[str],
        top_k: int,
    ) -> List[Dict]:
        """Reciprocal Rank Fusion 融合双路检索结果

        RRF 公式: score(d) = sum( 1 / (k + rank(d)) )

        Args:
            vector_results: 向量检索结果 [(doc_id, page_content, metadata, distance), ...]
            bm25_results:   BM25 检索结果 [Document, ...]
            exclude_ids:    要排除的题目ID
            top_k:          返回数量

        Returns:
            融合排序后的题目列表
        """
        rrf_k = config.RRF_K
        scores: Dict[str, float] = {}
        doc_data: Dict[str, dict] = {}  # doc_id -> {content, metadata}
        exclude_set = set(exclude_ids)

        # 向量检索结果 (weight = config.VECTOR_WEIGHT)
        for rank, (doc_id, page_content, metadata, distance) in enumerate(vector_results):
            if doc_id in exclude_set:
                continue
            rrf_score = config.VECTOR_WEIGHT / (rrf_k + rank + 1)
            scores[doc_id] = scores.get(doc_id, 0) + rrf_score
            doc_data[doc_id] = {"content": page_content, "metadata": metadata}

        # BM25 检索结果 (weight = config.BM25_WEIGHT)
        for rank, doc in enumerate(bm25_results):
            doc_id = doc.metadata.get("id", f"bm25_{rank}")
            if doc_id in exclude_set:
                continue
            rrf_score = config.BM25_WEIGHT / (rrf_k + rank + 1)
            scores[doc_id] = scores.get(doc_id, 0) + rrf_score
            if doc_id not in doc_data:
                doc_data[doc_id] = {"content": doc.page_content, "metadata": doc.metadata}

        # 按 RRF 分数排序
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)

        # 转换为输出格式
        results = []
        for doc_id in sorted_ids[:top_k]:
            data = doc_data[doc_id]
            meta = data["metadata"]
            results.append({
                "id": doc_id,
                "question": data["content"],
                "score": round(scores[doc_id], 6),
                "role": meta.get("role", ""),
                "category": meta.get("category", ""),
                "difficulty": meta.get("difficulty", 2),
                "difficulty_label": meta.get("difficulty_label", "中级"),
            })

        return results

    # ============================================================
    # 公共接口 (与原 InterviewRetriever 兼容)
    # ============================================================

    def get_question(
        self,
        topic: str,
        role: str = None,
        category: str = None,
        difficulty: int = None,
        exclude_ids: List[str] = None,
        top_k: int = 5,
    ) -> List[Dict]:
        """出题阶段: 混合检索候选题目 (不含答案)

        使用 BM25 + 向量双路检索, RRF 融合排序。
        """
        exclude_ids = exclude_ids or []

        # 向量检索
        vector_results = self._vector_search(
            topic=topic, role=role, difficulty=difficulty, top_k=top_k
        )

        # BM25 检索
        bm25_retriever = self._get_bm25_retriever(role) if role else None
        bm25_results = []
        if bm25_retriever:
            bm25_results = bm25_retriever.invoke(topic)

        # RRF 融合
        merged = self._reciprocal_rank_fusion(
            vector_results, bm25_results, exclude_ids, top_k
        )

        # 按 category 过滤 (如果指定)
        if category:
            merged = [m for m in merged if m.get("category") == category]

        return merged

    def get_answer(self, question_id: str) -> Optional[Dict]:
        """评分阶段: 按题号精确检索标准答案 + 得分点 (带缓存, 题库不变则命中)"""
        # 缓存命中 (阶段3 提速: 同一题反复检索标准答案走内存)
        if question_id in self._answer_cache:
            return self._answer_cache[question_id]

        results = self.vectorstore._collection.get(
            ids=[question_id],
            include=["documents", "metadatas"],
        )
        if not results["ids"]:
            return None

        meta = results["metadatas"][0]
        scoring_points_raw = meta.get("scoring_points", "")
        scoring_points = (
            scoring_points_raw.split("||") if scoring_points_raw else []
        )
        followup_raw = meta.get("followup_directions", "")
        followup_directions = (
            followup_raw.split("||") if followup_raw else []
        )
        good_raw = meta.get("good_points", "")
        good_points = good_raw.split("||") if good_raw else []
        bad_raw = meta.get("bad_points", "")
        bad_points = bad_raw.split("||") if bad_raw else []

        result = {
            "id": results["ids"][0],
            "question": results["documents"][0],
            "standard_answer": meta.get("answer", ""),
            "scoring_points": scoring_points,
            "good_points": good_points,
            "bad_points": bad_points,
            "max_score": meta.get("max_score", 10),
            "category": meta.get("category", ""),
            "difficulty": meta.get("difficulty", 2),
            "type": meta.get("type", "knowledge"),
            "scenario": meta.get("scenario", ""),
            "followup_directions": followup_directions,
        }
        self._answer_cache[question_id] = result
        return result

    def get_question_by_id(self, question_id: str) -> Optional[Dict]:
        """按题号精确取题 (不含标准答案, 供演示固定首题等场景)"""
        results = self.vectorstore._collection.get(
            ids=[question_id],
            include=["documents", "metadatas"],
        )
        if not results["ids"]:
            return None
        meta = results["metadatas"][0] or {}
        return {
            "id": results["ids"][0],
            "question": results["documents"][0],
            "role": meta.get("role", ""),
            "category": meta.get("category", ""),
            "difficulty": meta.get("difficulty", 2),
            "difficulty_label": meta.get("difficulty_label", "中级"),
            "type": meta.get("type", "knowledge"),
            "scenario": meta.get("scenario", ""),
        }

    def get_categories(self, role: str = None) -> List[str]:
        """获取某岗位的所有分类"""
        where_filter = {"role": role} if role else None
        results = self.vectorstore._collection.get(
            where=where_filter if where_filter else None,
            include=["metadatas"],
        )

        categories = set()
        if results["metadatas"]:
            for m in results["metadatas"]:
                cat = m.get("category", "")
                if cat:
                    categories.add(cat)
        return sorted(categories)

    def get_random_question(
        self,
        role: str = None,
        difficulty: int = None,
        exclude_ids: List[str] = None,
    ) -> Optional[Dict]:
        """随机抽一题"""
        exclude_ids = exclude_ids or []
        documents = self._get_all_documents(role=role)

        candidates = []
        for doc in documents:
            doc_id = doc.metadata.get("id", "")
            if doc_id in exclude_ids:
                continue
            if difficulty and doc.metadata.get("difficulty") != difficulty:
                continue
            candidates.append(doc)

        if not candidates:
            return None

        chosen = random.choice(candidates)
        meta = chosen.metadata
        return {
            "id": meta.get("id", ""),
            "question": chosen.page_content,
            "category": meta.get("category", ""),
            "difficulty": meta.get("difficulty", 2),
            "difficulty_label": meta.get("difficulty_label", "中级"),
        }
