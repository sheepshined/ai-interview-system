"""history 接线验证(手动执行): 算法岗 2-3 题正常回答,
确认面试官衔接体现"连续心智"(能引用候选人之前回答过的内容),
而非每题独立无记忆。

前置: 后端已在 127.0.0.1:8000 启动(加载最新代码), .env 已配 Key。
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

# 正常、有内容的回答——让面试官有"可记住"的具体信息
ANSWERS = [
    # Q1(快排): 给出原理+复杂度
    "快速排序基于分治思想：选一个基准pivot，把小于pivot的放左边、大于的放右边，"
    "然后递归排序左右子数组。平均时间复杂度O(nlogn)，最坏情况O(n²)发生在数组已有序"
    "且选端点为pivot时。优化方法包括随机选pivot、三数取中、小数组切到插入排序等。",
    # Q2(复杂度): 给出概念+例子
    "时间复杂度衡量算法运行时间随输入规模n的增长趋势，空间复杂度衡量额外内存占用。"
    "O(1)如数组下标取值，O(logn)如二分查找，O(n)如线性遍历，O(nlogn)如归并排序，"
    "O(n²)如冒泡排序的双重循环。",
    # Q3(动态规划): 给出定义+背包举例
    "动态规划用于具有最优子结构和重叠子问题的最优化问题。以0-1背包为例，"
    "dp[i][j]表示前i件物品容量j的最大价值，状态转移方程是"
    "dp[i][j]=max(dp[i-1][j], dp[i-1][j-w[i]]+v[i])，即放或不放第i件。"
    "可以压缩成一维逆序遍历。",
]


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
            "question_count": 3,
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
                    if stype in ("question", "followup") and answer_idx < len(ANSWERS):
                        await socket.send(json.dumps({
                            "type": "answer", "content": ANSWERS[answer_idx],
                        }, ensure_ascii=False))
                        answer_idx += 1

                elif event_type == "interview_ended" and not report_requested:
                    report_requested = True
                    await socket.send(json.dumps({"type": "report"}))

                elif event_type == "report_ready":
                    break

    print("\n========== 面试输出文本(正常回答场景) ==========")
    for idx, (stype, full) in enumerate(texts):
        print(f"\n--- [{idx}] {stype} ---\n{full}")

    # 连续心智检查: 第2题及之后的衔接, 是否能体现"记得之前聊过什么"
    print("\n========== 连续心智检查 ==========")
    if len(texts) >= 2:
        later = " ".join(full for _, full in texts[1:])
        # 连续心智的标志: 面试官能具体引用候选人之前回答的内容/表现
        # 不只是"上一题/刚才"这类泛指, 更包括"你答得.../你提到.../你举的例子"
        recall_hints = [
            "刚才", "之前", "上一题", "前面",  # 泛指回指
            "你答", "你提到", "你举", "你说的", "你理解",  # 具体内容回指
            "答得很", "抓得很准", "很贴切", "很到位",  # 表现评价回指
        ]
        hits = [h for h in recall_hints if h in later]
        if hits:
            print(f"✅ 后续衔接体现连续心智, 回指措辞: {hits}")
        else:
            print("⚠️ 后续衔接未出现明显回指措辞(不一定是问题, 但连续心智未体现)")
    print(f"\n共 {len(texts)} 段输出。")


if __name__ == "__main__":
    asyncio.run(run())
