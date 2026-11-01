"""deps.py — 跨模块依赖的懒加载入口。

为什么不直接 import server: server 在模块导入期就 import assistant.graph,
若 assistant.tools 在导入期 import server 会成环。把 import 推迟到函数体内,
环就不存在 (assistant.tools 的模块导入不触碰 server)。
复用 server 的懒加载单例, 避免 HybridRetriever 被构造两次 (chroma + bm25 很重)。
"""


def get_retriever():
    import server  # 延迟导入, 见模块 docstring
    return server.get_retriever()
