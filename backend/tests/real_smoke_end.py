"""验证用户报障路径: 标准模式答题 + 中途「提前结束」(server.py:1116 曾经的协程崩溃点)"""
import asyncio
import json

import httpx
import websockets

API = "http://127.0.0.1:8001/api"
WS = "ws://127.0.0.1:8001/ws/chat"


async def main() -> None:
    async with httpx.AsyncClient(timeout=30) as c:
        token = (await c.post(f"{API}/login", json={"username": "admin", "password": "123123"})).json()["token"]
    print("✓ 登录")

    async with websockets.connect(f"{WS}?token={token}", max_size=2_000_000) as ws:
        await ws.send(json.dumps({
            "type": "config", "role": "llm_app", "question_count": 5,
            "difficulty": 2, "resume_context": "", "resume_skills": [],
        }, ensure_ascii=False))

        # 等第一题出完
        while True:
            d = json.loads(await asyncio.wait_for(ws.recv(), timeout=240))
            if d.get("type") == "error":
                raise RuntimeError(d.get("content"))
            if d.get("type") == "stream_end" and d.get("stream_type") == "question":
                print(f"✓ 出题完成: {d.get('question_id')}")
                break

        await asyncio.sleep(2.5)
        await ws.send(json.dumps({"type": "answer", "content":
            "常见的分块方法有四种：固定长度按字符数硬切，简单但容易截断语义；"
            "正则按分隔符切；Spacy 按句法分句，更懂语言结构；"
            "LangChain 的 CharacterTextSplitter 支持分隔符加 overlap，"
            "能缓解切分边界语义断裂。结构规整文档适合正则，自由文本适合 Spacy 加 overlap。"},
            ensure_ascii=False))
        print("✓ 已回答第 1 题")

        # 等评分结束 → decision end
        while True:
            d = json.loads(await asyncio.wait_for(ws.recv(), timeout=240))
            t = d.get("type")
            if t == "error":
                raise RuntimeError(d.get("content"))
            if t == "decision":
                print(f"  decision: {d.get('action')} ({d.get('reason', '')[:40]})")
                if d.get("action") == "followup":
                    await asyncio.sleep(2.5)
                    await ws.send(json.dumps({"type": "answer", "content": "overlap 就是切块之间保留的重叠区，比如每块 500 字、相邻块重叠 75 字，这样跨界的句子至少完整出现在一块里，检索召回不会因为切断而漏掉。"}, ensure_ascii=False))
                    continue
                if d.get("action") in ("end", "next"):
                    break

        # ---- 用户报障的路径: 提前结束面试 ----
        await asyncio.sleep(1.0)
        await ws.send(json.dumps({"type": "end"}))
        print("✓ 已发送 end（提前结束）")
        while True:
            d = json.loads(await asyncio.wait_for(ws.recv(), timeout=240))
            t = d.get("type")
            if t == "error":
                raise RuntimeError(f"end 路径报错: {d.get('content')}")
            if t == "stream_end" and d.get("stream_type") == "closing":
                print("✓ 收到收尾语 (提前结束不报错, 正常停在等待生成报告阶段)")
                break
    print("\n✅ 用户报障路径已修复：答题与提前结束均正常")


if __name__ == "__main__":
    asyncio.run(main())
