"""反幻觉真实 LLM 冒烟(手动执行): 算法岗 5 题全垃圾回答,
打印每题 stream_end 的 full_text, 人工确认下一题开场不出现
"你刚刚提到/你刚才提到"等把标准答案或 hit_points 安到候选人头上的幻觉。

前置: 后端已在 127.0.0.1:8000 启动, backend/.env 已配置 LLM Key。
"""
import asyncio
import json

import httpx
import websockets

WS_URL = "ws://127.0.0.1:8000/ws/chat"
API_URL = "http://127.0.0.1:8000/api"


def get_token() -> str:
    """登录演示账号获取 JWT (WS 握手鉴权用)。"""
    resp = httpx.post(f"{API_URL}/login", json={"username": "admin", "password": "123123"})
    resp.raise_for_status()
    return resp.json()["token"]

GARBAGE_ANSWERS = ["不知道", "不清楚", "不想说", "哈哈", "有吗"]
HALLUCINATION_HINTS = ["你刚刚提到", "你刚才提到", "你提到了", "正如你所说", "你所说"]


async def run() -> None:
    texts: list[tuple[str, str]] = []  # (stream_type, full_text)
    answer_idx = 0
    report_requested = False

    async with websockets.connect(
        f"{WS_URL}?token={get_token()}", max_size=2_000_000
    ) as socket:
        await socket.send(json.dumps({
            "type": "config",
            "role": "algorithm",
            "question_count": 5,
            "difficulty": 2,
            "resume_context": "",
            "resume_skills": [],
        }, ensure_ascii=False))

        async with asyncio.timeout(600):
            while True:
                data = json.loads(await socket.recv())
                event_type = data.get("type")

                if event_type == "error":
                    raise RuntimeError(data.get("content") or "服务端未知错误")

                if event_type == "stream_end":
                    stype = data.get("stream_type")
                    full = data.get("full_text") or ""
                    if stype in ("question", "closing"):
                        texts.append((stype, full))
                    # 任何需要回答的题(主问题/追问)都回垃圾
                    if stype in ("question", "followup") and answer_idx < len(GARBAGE_ANSWERS):
                        await socket.send(json.dumps({
                            "type": "answer", "content": GARBAGE_ANSWERS[answer_idx],
                        }, ensure_ascii=False))
                        answer_idx += 1

                elif event_type == "interview_ended" and not report_requested:
                    report_requested = True
                    await socket.send(json.dumps({"type": "report"}))

                elif event_type == "report_ready":
                    break

    # 输出每段文本, 标记疑似幻觉措辞
    print("\n========== 面试输出文本 ==========")
    flagged = []
    for idx, (stype, full) in enumerate(texts):
        print(f"\n--- [{idx}] {stype} ---\n{full}")
        hits = [h for h in HALLUCINATION_HINTS if h in full]
        if hits:
            flagged.append((idx, stype, hits, full))

    print("\n========== 幻觉检查 ==========")
    if flagged:
        print(f"⚠️ 发现 {len(flagged)} 段疑似幻觉:")
        for idx, stype, hits, full in flagged:
            print(f"  [{idx}] {stype} 命中 {hits}")
        print("\n结论: 仍存在把候选人未说过内容当作'候选人提到过'复述的幻觉。")
    else:
        print("✅ 未发现'你刚刚提到/你刚才提到'等幻觉措辞。")
    print(f"\n共 {len(texts)} 段输出 (question/closing)。")


if __name__ == "__main__":
    asyncio.run(run())
