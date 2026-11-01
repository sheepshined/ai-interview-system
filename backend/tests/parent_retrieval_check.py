"""
parent_retrieval_check.py — 父文档检索模式 线上数据验证 (手动执行)

无需启动服务, 直接读 knowledge.db, 全部走本地 BGE, 无 API 成本。

查询构造 (基于真实笔记):
  - 每篇笔记: 标题查询
  - 长文 (>1200字): 正文 10% / 50% / 90% 位置的完整句子 ("深层探针")
  - 短文: 50% 位置句子 (内容够长时)

检查项:
  - Hit@5 / MRR / 源笔记分数: 检索能否召回源笔记 (长文深层位置是重点)
  - 父块完整性: 命中笔记的 excerpt 是否包含探针句子本身
    (子块命中 → 返回父块, 探针句应在父块文本中)

用法:
  cd backend
  python tests/parent_retrieval_check.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import knowledge
import kb_parent

TOP_K = 5


def build_queries(notes):
    queries = []
    for note in notes:
        nid = note["id"]
        content = note.get("content") or ""
        group = "long" if len(content) > kb_parent.LONG_DOC_THRESHOLD else "short"
        queries.append((group, "title", nid, note["title"], content))

        sents = kb_parent._natural_units(content, kb_parent.PARENT_CHUNK_SIZE)
        offsets = []
        cursor = 0
        for s in sents:
            idx = content.find(s, cursor)
            if idx >= 0:
                offsets.append((idx, s))
                cursor = idx + len(s)

        def pick(frac):
            pos = int(len(content) * frac)
            cand = [(abs(i - pos), s) for i, s in offsets if len(s) >= 12]
            return min(cand, key=lambda x: x[0])[1] if cand else None

        fracs = (0.1, 0.5, 0.9) if group == "long" else (0.5,)
        seen = set()
        for frac in fracs:
            q = pick(frac)
            if q and q not in seen and q != note["title"]:
                seen.add(q)
                label = {0.1: "p10", 0.5: "p50", 0.9: "p90"}[frac]
                queries.append((group, label, nid, q, content))
    return queries


def source_result(results, nid):
    for rank, r in enumerate(results, 1):
        if r["note_id"] == nid:
            return rank, r
    return None, None


def metrics(rows, rank_i):
    n = len(rows)
    hits = sum(1 for r in rows if r[rank_i] is not None)
    mrr = sum(1.0 / r[rank_i] for r in rows if r[rank_i] is not None) / n
    scores = [r[rank_i + 1] for r in rows if r[rank_i + 1] is not None]
    return n, hits, hits / n * 100, mrr * 100, (sum(scores) / len(scores) if scores else 0)


def main():
    username = os.getenv("CMP_USER", "admin")
    knowledge.init_db(config.KB_DB_PATH)

    note_rows = knowledge.list_notes(username)
    notes = [knowledge.get_note(username, m["id"]) for m in note_rows]
    notes = [n for n in notes if n]
    print(f"用户 {username}: {len(notes)} 篇笔记 "
          f"(长文 {sum(1 for n in notes if len(n.get('content') or '') > kb_parent.LONG_DOC_THRESHOLD)}, "
          f"短文 {sum(1 for n in notes if len(n.get('content') or '') <= kb_parent.LONG_DOC_THRESHOLD)})")

    print("\n[1/2] 全量构建父文档索引 (请等待)...")
    stats = kb_parent.build_user_index(username, wipe=True)
    print(f"  父块 {stats['parents']} 个, 子块 {stats['children']} 条 "
          f"(长文 {stats['long_notes']} 篇, 清理过期 {stats['stale_removed']})")

    print("\n[2/2] 探针检索 + 父块完整性检查...")
    queries = build_queries(notes)
    print(f"  共 {len(queries)} 条查询\n")

    buckets = {}
    integrity_bad = []
    for group, kind, nid, q, content in queries:
        results = kb_parent.search(username, q, top_k=TOP_K)
        rank, hit = source_result(results, nid)
        score = hit.get("score") if hit else None
        buckets.setdefault((group, kind), []).append((rank, score))
        if kind != "title" and hit is not None:
            probe_norm = "".join(q.split())
            ex_norm = "".join((hit.get("excerpt") or "").split())
            if probe_norm not in ex_norm:
                integrity_bad.append((group, kind, q))

    order = [("short", "title"), ("short", "p50"),
             ("long", "title"), ("long", "p10"), ("long", "p50"), ("long", "p90")]

    print("=" * 78)
    print("分组        探针    N   | Hit@5          MRR      源笔记均分")
    print("-" * 78)
    for key in order:
        rows = buckets.get(key)
        if not rows:
            continue
        n, h, rate, mrr, avg = metrics(rows, 0)
        print(f"{key[0]:5} {key[1]:>8} {n:4} | "
              f"{h:3}/{n:<3} {rate:6.1f}% {mrr:6.1f}% {avg:8.2f}")
    print("=" * 78)

    for group in ("short", "long"):
        rows = [r for k, v in buckets.items() if k[0] == group for r in v]
        n, h, rate, mrr, avg = metrics(rows, 0)
        print(f"[{group} 文档汇总] Hit@5 {rate:.1f}%  MRR {mrr:.1f}%  均分 {avg:.2f}")

    print(f"\n父块完整性: {'全部通过 (探针句均包含在返回父块中)' if not integrity_bad else f'{len(integrity_bad)} 条异常'}")
    for group, kind, q in integrity_bad[:10]:
        print(f"  [{group}/{kind}] {q[:60]}")


if __name__ == "__main__":
    main()
