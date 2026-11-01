"""persistence.py — 面试图与 assistant 图共用的 AsyncSqliteSaver 单例。

为什么共用是安全的: AsyncSqliteSaver 无 per-graph 状态, 写路径全在 self.lock
内串行。为什么不共用 thread_id 是致命的: checkpoint 只按 thread_id +
checkpoint_ns 分区, 两张图复用同一 thread 会串成同一条时间线
(checkpoint/sqlite/aio.py 的已知限制)。所以 assistant 一律 as_ 前缀,
面试一律 iv_ 前缀 (server.py:1151)。

不关连接会让 graph hang (checkpoint/sqlite/aio.py:53-61 的 Warning),
所以 server 的 shutdown 钩子必须调 close_shared_saver()。
"""
import logging
from typing import Optional

import config

logger = logging.getLogger(__name__)

_conn = None
_saver = None


async def get_shared_saver():
    """懒加载共享 checkpointer。依赖缺失时退回进程内 MemorySaver。"""
    global _conn, _saver
    if _saver is not None:
        return _saver
    try:
        import aiosqlite
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        _conn = await aiosqlite.connect(config.CHECKPOINT_DB_PATH)
        _saver = AsyncSqliteSaver(_conn)
        await _saver.setup()
        logger.info("checkpointer: SQLite 持久化 (%s)", config.CHECKPOINT_DB_PATH)
    except ImportError:
        from langgraph.checkpoint.memory import MemorySaver
        _saver = MemorySaver()
        logger.warning("langgraph-checkpoint-sqlite 未安装, 退回内存 checkpointer")
    return _saver


async def close_shared_saver() -> None:
    """幂等关闭。server shutdown 钩子调用。"""
    global _conn, _saver
    if _conn is not None:
        try:
            await _conn.close()
        except Exception as exc:
            logger.warning("关闭 checkpointer 连接失败: %s", exc)
    _conn = None
    _saver = None


def assistant_thread_id(username: str, session_id: int) -> str:
    """as_ 前缀是隔离的硬约束, 不要手拼 thread_id。"""
    return f"as_{username}_{session_id}"
