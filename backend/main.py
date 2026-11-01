"""题库管理入口。

用法：
  python main.py build      # 从 Markdown 题库构建向量库
  python main.py rebuild    # 删除现有向量库后重新构建
  python main.py variants   # 生成防背题变体题并重建 (可选 --count N)
"""
import os
import shutil
import sys

import config


def build_knowledge_base() -> None:
    """构建题库向量库。"""
    from retrieval.kb_builder import KnowledgeBaseBuilder

    success = KnowledgeBaseBuilder().build()
    if success:
        print("\n[完成] 题库已就绪，请启动 FastAPI 与 Vite 前端。")


def rebuild_knowledge_base() -> None:
    """删除现有向量库并重新构建。"""
    chroma_path = os.path.abspath(config.CHROMA_DB_PATH)
    if os.path.isdir(chroma_path):
        shutil.rmtree(chroma_path)
        print(f"[清理] 已删除旧向量库: {chroma_path}")
    build_knowledge_base()


def generate_variants_command(argv: list) -> None:
    """防背题: 每个分类生成变体题并重建向量库。"""
    count = 1
    if "--count" in argv:
        try:
            count = max(1, int(argv[argv.index("--count") + 1]))
        except (IndexError, ValueError):
            print("[参数] --count 需要一个整数, 使用默认 1")
    from agent.variants import generate_variants

    print(f"[变体] 每个分类生成 {count} 道变体题…")
    n = generate_variants(count_per_category=count)
    if n == 0:
        print("[变体] 没有生成任何变体, 跳过重建")
        return
    print(f"\n[变体] 已生成 {n} 道, 开始重建向量库…")
    rebuild_knowledge_base()


def main() -> None:
    command = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    if command == "build":
        build_knowledge_base()
    elif command == "rebuild":
        rebuild_knowledge_base()
    elif command == "variants":
        generate_variants_command(sys.argv[2:])
    elif command == "fetch-models":
        from model_manager import fetch_models
        fetch_models()
    else:
        print("AI 模拟面试官 — 题库管理")
        print("用法:")
        print("  python main.py build      # 构建题库")
        print("  python main.py rebuild    # 清空并重建题库")
        print("  python main.py variants   # 生成防背题变体并重建 (可选 --count N)")
        print("  python main.py fetch-models # 下载并校验本地语音模型")


if __name__ == "__main__":
    main()
