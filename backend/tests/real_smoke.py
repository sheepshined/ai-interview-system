"""真实 LLM WebSocket 冒烟测试（手动执行，不属于 pytest 默认套件）。

前置条件：后端已在 127.0.0.1:8000 启动，backend/.env 已配置 LLM Key。
"""
import asyncio
import json
import re
from pathlib import Path

import httpx
import websockets


WS_URL = "ws://127.0.0.1:8000/ws/chat"
API_URL = "http://127.0.0.1:8000/api"


def get_token() -> str:
    """登录演示账号获取 JWT (WS 握手鉴权用)。"""
    resp = httpx.post(f"{API_URL}/login", json={"username": "admin", "password": "123123"})
    resp.raise_for_status()
    return resp.json()["token"]


def load_reference_answers() -> dict[str, str]:
    """读取题库参考答案，让第二题稳定模拟一份正常、完整的回答。"""
    question_bank = Path(__file__).parents[1] / "data" / "python_dev.md"
    answers: dict[str, str] = {}
    current_id = ""
    for line in question_bank.read_text(encoding="utf-8").splitlines():
        match = re.match(r"<!-- id:([^ |]+)", line)
        if match:
            current_id = match.group(1)
        elif current_id and line.startswith("### A:"):
            answers[current_id] = line.removeprefix("### A:").strip()
            current_id = ""
    return answers


async def run_smoke() -> None:
    reference_answers = load_reference_answers()
    question_events = []
    followup_events = []
    answered_questions = set()
    answered_followups = set()
    report_requested = False

    async with websockets.connect(
        f"{WS_URL}?token={get_token()}", max_size=2_000_000
    ) as socket:
        await socket.send(json.dumps({
            "type": "config",
            "role": "python_dev",
            "question_count": 2,
            "difficulty": 2,
            "resume_context": "",
            "resume_skills": [],
        }, ensure_ascii=False))

        async with asyncio.timeout(600):
            while True:
                data = json.loads(await socket.recv())
                event_type = data.get("type")

                if event_type == "error":
                    raise RuntimeError(data.get("content") or "服务端返回未知错误")

                if event_type == "stream_end" and data.get("stream_type") == "question":
                    question_id = data.get("question_id")
                    question_index = int(data.get("question_index") or 0)
                    question_events.append((question_id, question_index))
                    if question_id not in answered_questions:
                        answered_questions.add(question_id)
                        answer = (
                            # 第一题给"方向正确但内容模糊"的回答, 目标落在 3-6 分档,
                            # 以覆盖追问路径(新分档下 1-2 分不再追问, 评分有波动, 见下方断言)
                            "我先说一下我的理解：这类问题通常要先讲清楚核心概念和基本原理，"
                            "再结合实际场景说明优缺点，最后提一下常见误区。我能给出大方向上的回答，"
                            "但具体细节、底层实现和边界情况掌握得不够扎实，可能有些点讲不全。"
                            if question_index == 1
                            else reference_answers.get(
                                question_id,
                                "我会说明核心概念、工作原理、适用场景、风险和验证方法。",
                            )
                        )
                        await socket.send(json.dumps({"type": "answer", "content": answer}, ensure_ascii=False))

                elif event_type == "stream_end" and data.get("stream_type") == "followup":
                    question_id = data.get("question_id")
                    followup_events.append(question_id)
                    if question_id not in answered_followups:
                        answered_followups.add(question_id)
                        await socket.send(json.dumps({
                            "type": "answer",
                            "content": (
                                "补充回答：需要结合调度机制、资源管理、异常处理和性能影响来分析，"
                                "并通过日志与测试验证实际行为。"
                            ),
                        }, ensure_ascii=False))

                elif event_type == "interview_ended" and not report_requested:
                    report_requested = True
                    if int(data.get("answered_count") or 0) != 2:
                        raise AssertionError(f"主问题完成数错误: {data}")
                    await socket.send(json.dumps({"type": "report"}))

                elif event_type == "report_ready":
                    report_id = data.get("report_id")
                    if not report_id:
                        raise AssertionError("report_ready 缺少 report_id")
                    break

    if len(question_events) != 2:
        raise AssertionError(f"题目输出次数应为 2，实际为 {question_events}")
    if len({question_id for question_id, _ in question_events}) != 2:
        raise AssertionError(f"题目 ID 不唯一: {question_events}")
    if followup_events not in ([question_events[0][0]], []):
        raise AssertionError(
            f"追问最多只能针对第一题(新分档下 1-2 分跳过、3-6 分追问), "
            f"实际追问题目为: {followup_events}"
        )

    async with httpx.AsyncClient(timeout=30) as client:
        report_response = await client.get(f"{API_URL}/reports/{report_id}")
        radar_response = await client.get(f"{API_URL}/reports/{report_id}/radar")
        report_response.raise_for_status()
        radar_response.raise_for_status()
        report = report_response.json()
        radar = radar_response.json()["radar"]

    if report.get("report_id") != report_id:
        raise AssertionError("Markdown 报告 ID 不一致")
    if radar.get("report_id") != report_id:
        raise AssertionError("雷达报告 ID 不一致")
    if radar.get("total_questions") != 2:
        raise AssertionError(f"雷达主问题数错误: {radar.get('total_questions')}")
    radar_ids = [question.get("question_id") for question in radar.get("questions", [])]
    event_ids = [question_id for question_id, _ in question_events]
    if radar_ids != event_ids:
        raise AssertionError(f"展示题目与报告题目不一致: {event_ids} != {radar_ids}")

    print(json.dumps({
        "success": True,
        "report_id": report_id,
        "question_events": question_events,
        "followup_count": len(followup_events),
        "avg_score": radar.get("avg_score"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(run_smoke())
