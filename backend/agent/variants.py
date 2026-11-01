"""agent/variants.py — 题目变体生成 (v0.9)

防背题: 把题库里的题目按考点"换壳不换魂"——同一个知识点, 换一个业务场景
重新包装成新题, 由 LLM 生成后追加到对应岗位题库文件, 再 rebuild 向量库即用。

用法 (在 backend 目录):
    python main.py variants            # 每个分类生成 1 道变体
    python main.py variants --count 2  # 每个分类生成 2 道

生成结果直接追加到 data/llm_app.md (变体 id 带后缀 _vN), 并自动触发向量库重建。
"""
from __future__ import annotations
import json
import logging
import os
import re
from collections import OrderedDict

import config

logger = logging.getLogger(__name__)

VARIANT_PROMPT = """你是大模型应用开发领域的资深面试官与出题人。

下面是一道面试真题。请保持考察的核心知识点不变, 把题目的"场景外壳"完全换掉,
生成一道变体题——让背过原题的候选人无法直接照搬答案, 但扎实掌握该考点的人
依然能答好。

要求:
  1. 核心考点与难度保持一致, 场景务必不同(换行业/换业务/换角色视角)
  2. SCENARIO: 换一个新的面试情境(1-2 句)
  3. A: 参考答案重写(可调整叙述顺序与案例, 知识点不能少)
  4. S: 得分点改写(3-5 条, 覆盖同一考点)
  5. GOOD/BAD: 各 2-3 条, 针对新场景
  6. FOLLOWUP: 1-2 个追问, 与原题追问不同角度
  7. 严格按输出格式, 不要输出其他内容

输出格式 (严格遵守):

### Q: <新问题>
### SCENARIO: <新情境>
### A:
<参考答案>
### S:
- <得分点1>
- <得分点2>
### GOOD:
- <好回答特征>
### BAD:
- <差回答特征>
### FOLLOWUP:
- <追问>

原题:
{original}"""


def _parse_blocks(md_path: str) -> "OrderedDict[str, dict]":
    """把题库 md 按 `---` 分隔解析成 {category: [blocks]}, 附原始题干"""
    with open(md_path, encoding="utf-8") as f:
        content = f.read()
    by_cat: "OrderedDict[str, list]" = OrderedDict()
    for block in re.split(r"\n---\n", content):
        if "### Q:" not in block:
            continue
        m_cat = re.search(r"category:\s*([^|]+?)\s*(?:\||-->)", block)
        cat = m_cat.group(1).strip() if m_cat else "其他"
        m_q = re.search(r"### Q:\s*(.+)", block)
        by_cat.setdefault(cat, []).append({"block": block.strip(), "question": m_q.group(1).strip() if m_q else ""})
    return by_cat


def generate_variants(count_per_category: int = 1, role: str = "llm_app") -> int:
    """每个分类挑一道题生成变体, 追加到题库 md, 返回生成数量"""
    from agent.llm import get_strong_llm

    md_path = os.path.join(config.DATA_DIR, f"{role}.md")
    if not os.path.isfile(md_path):
        raise FileNotFoundError(md_path)

    by_cat = _parse_blocks(md_path)
    existing_ids = set(re.findall(r"id:([a-zA-Z0-9_]+)", open(md_path, encoding="utf-8").read()))

    llm = get_strong_llm()
    generated = 0
    additions: list[str] = []

    for cat, blocks in by_cat.items():
        for i in range(count_per_category):
            src = blocks[i % len(blocks)]
            print(f"  [{cat}] 变体基于: {src['question'][:44]}…")
            try:
                out = llm.invoke(VARIANT_PROMPT.format(original=src["block"]))
                text = out.content if hasattr(out, "content") else str(out)
                text = text.strip()
            except Exception as exc:
                print(f"    ✗ 生成失败: {exc}")
                continue
            if not all(tag in text for tag in ("### Q:", "### A:", "### S:")):
                print("    ✗ 输出缺少必要小节, 跳过")
                continue
            # 剥掉 LLM 可能自带的代码块围栏与原 id
            text = re.sub(r"```[a-z]*\n?|```", "", text).strip()
            base = re.search(r"id:([a-zA-Z0-9_]+)", src["block"])
            base_id = base.group(1) if base else cat
            n = 1
            while f"{base_id}_v{n}" in existing_ids:
                n += 1
            new_id = f"{base_id}_v{n}"
            existing_ids.add(new_id)
            # 替换/注入 id 头注释
            header = f"<!-- id:{new_id} | category:{cat} | difficulty:2 | difficulty_label:中级 | type:scenario | variant_of:{base_id} -->"
            body = re.sub(r"^<!--.*?-->\s*", "", text)
            body = re.sub(r"^### Q:", "### Q:", body.strip())
            additions.append(f"{header}\n{body}")
            generated += 1
            print(f"    ✓ {new_id}")

    if additions:
        with open(md_path, "a", encoding="utf-8") as f:
            f.write("\n\n---\n\n" + "\n\n---\n\n".join(additions) + "\n")
    return generated


if __name__ == "__main__":
    n = generate_variants()
    print(json.dumps({"generated": n}, ensure_ascii=False))
