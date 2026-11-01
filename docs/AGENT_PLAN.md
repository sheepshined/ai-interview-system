# AI 模拟面试系统 · 统筹智能体（Assistant Agent）建设计划书 v2

> **2026-10-09 实施状态**：本文件保留原设计及研究出处，不作为已完成声明。统筹助手、按用户隔离的简历落库与审核、投递档案及复盘、JD 来源与版本历史、基础语音和上下文摘要已实现；后端 176 项测试及前端构建通过。最新 19 条真实评测为 14 通过、2 待人工审核、3 因 DeepSeek 余额不足失败，最终模型验收未完成。完整的已实现、已验证与待完成清单见 `PROGRESS_HANDOVER.md`。

> **一句话定位**：在现有「面试 + 知识库」两套能力之上，新增一个有长期记忆的**总助手 agent**。它是用户进系统后面对的第一个交互面：你用它说话，它调用工具去读你的报告和笔记、综合作答；你说要面试，它抽取参数并**提议**起一场面试，你确认后它才把你交接给面试官引擎。
>
> **核心不变量**：agent 层只"提议"，永不"擅自执行"。面试 StateGraph、知识库内核、检索链路**一行不改**（唯一例外见 §5.10 的两处受控小改，与 §0 第 4 批的 R5，均已单独标注）。
>
> **v2 修订说明**：本版为深度修订。相比 v1：新增 §0 项目总路线图、§2.4 断言核实台账（v1 出现过一次"凭推理当事实"的错误——播放进度归属问题——本版把核实变成受控产物）、§5.2 图结构落到节点签名级、§5.4 工具执行语义（并行/SQLite 并发）、§5.12 会话历史与设置持久化、§5.13 REST API 面、§7 前端组件树与交接时序、P6 收尾阶段。全部新增断言按 §2.4 台账逐条核过源码。

---

## 0. 文档体系与总路线图（v2.0）

本仓库现在有三份计划，分工如下，**不要往错的那份里塞需求**：

| 文档 | 管什么 | 改不改面试图 |
|---|---|---|
| `AGENT_PLAN.md`（本文件） | 统筹智能体层：抽屉、工具层、路由、提议-确认、长期记忆 | 不改 |
| `RESUME_UPGRADE_PLAN.md` | 简历结构化（R 系列）、JD 匹配（J 系列）、报告补展示（Z 系列）、语音（V 系列） | 只有 R5 改，且单独排期 |
| `OPTIMIZATION_PLAN.md` | 历史文档：LangGraph 迁移，已基本完成，仅作沿革参考 | — |

发布列车（人日为粗估，按"每阶段可演示"切分）：

```
批次          内容                                    前置
─────────────────────────────────────────────────────────────
AGENT P0      地基：通道/图骨架/工具注册/事件协议        requirements 版本修正
AGENT P1      只读工具 + 综合分析（剧本 B/C）
RESUME 第 0 批 Z1-Z4 Z6 R7（纯前端展示 + 摘分数）         无，可随时
RESUME 第 1 批 R1-R4（简历落库 + evidence 底座）           与 AGENT P2 并行
AGENT P2      意图路由 + 提议-确认（剧本 A）              AGENT P1
RESUME 第 1.5 批 V7 前置实验（TTS 合成延迟实测）           无
AGENT P3      长期记忆（剧本 D）                          AGENT P2
RESUME 第 2 批 J 系列 + R6；第 3 批 V1-V3 V6 → V7         与 AGENT P3 并行
AGENT P4      权限分级 + 预算 + 可观测
AGENT P5      语音接抽屉 + 评测集
AGENT P6      收尾：健康检查/README/部署                  全部
RESUME 第 4 批 R5（evidence 喂出题，改面试图）             AGENT P2 之后
```

---

## 一、范围

### 1.1 做

| # | 能力 | 说明 |
|---|---|---|
| 1 | 全局侧边抽屉 + 悬浮小圆点 | 挂在 `AppLayout`，任何页面可唤起，面试进行中也能用 |
| 2 | 独立 agent 通道 `/ws/assistant` | 与 `/ws/chat`（面试）互不干扰，两条连接并存 |
| 3 | 工具层（只读 12 + 提议型 2 + 记忆 3） | 读报告/雷达/弱项、读面试记录、KB 检索与问答、读笔记、读简历、记忆读写 |
| 4 | 意图路由 + 缺槽追问 | "我要面试"→ 抽 `role/count/difficulty/mode/resume`，缺什么问什么 |
| 5 | 提议-确认卡片 | `start_interview` 产出待确认提案（offerpilot `PendingAction` 契约），前端渲染成**可编辑**卡片 |
| 6 | 跨会话长期记忆 | 新表 `agent_memory`，agent 自主 `remember`，检索注入，界面可查看/删除/清空 |
| 7 | 工具确认分级 + 用户可配的自动接受 | 写操作必须确认；只读操作可在设置里选逐条确认或自动放行 |
| 8 | 会话历史持久化与恢复 | 抽屉对话可翻历史、可续聊、断线重连不丢（§5.12） |
| 9 | 语音输入 | 复用 v1.1 的 `useVoiceInput` + `/api/asr` |
| 10 | 可扩展工具注册约定 | "后续接入别的功能"落成一套声明式约定，加一个文件即注册 |
| 11 | agent 评测集与回归 | 意图路由 / 工具选择 / 参数抽取 / 记忆信噪比 四指标 |

### 1.2 不做（明确排除，避免范围漂移）

- **不改 `backend/agent/graph.py` 的面试图和其节点/边/router**。不 agentic 化面试官的 `decide`、选题、难度规则。
- **不改知识库内核**：`kb_parent.py`、`kb_llm.py`、`knowledge.py`、`retrieval/` 只被**调用**，不被修改（新增只读函数除外，且必须向后兼容）。
- **不做多 agent 协作**（Supervisor + 角色分工）。判据来自 `agent-study/multiagent-handbook:59-64,82`：多 agent 需同时满足"可分解 / 信息隔离有意义 / 可独立验收 / 收益大于 15× token"，本层四条都不成立——单一统筹 agent 足够，且 `:82` 的第一性原则是"能 workflow 就别 agent"。
- **不引入 CrewAI / CAMEL**。理由：`start_interview` 这类被 UI 硬约束打断的流程，恰好落在框架自治协作的对立面；依赖体积与调试成本不划算。
- **不做 MCP server 封装**。这个 agent 的对外形态是"被调用的 agent 本身"，不是把它的工具摊成共享工具面。
- **不恢复多岗位题库**。`config.ROLES` 目前只剩 `llm_app`（`config.py:109`），岗位路由暂时无意义，列为后续独立议题。

### 1.3 受控例外（会触碰既有文件，逐条列清，避免"说不动手却动了"）

| 文件 | 改动 | 性质 |
|---|---|---|
| `backend/server.py` | **追加** assistant 的 WS 端点与 REST 路由；§5.10 所述把 checkpointer 连接的创建抽到 `assistant/persistence.py`（约 15 行等价搬移，行为不变）；追加 `@app.on_event("shutdown")` 关连接 | 追加 + 一处受控搬移 |
| `backend/requirements.txt` | 版本下界改为实装基准（§2.1） | 修正 |
| `backend/config.py` | 追加 assistant 的路径/预算配置项 | 追加 |
| `backend/tests/conftest.py` | 追加 `ASSISTANT_DB_PATH` 等环境变量隔离 | 追加 |

除以上四项，agent 层全部是**新文件**。

---

## 二、关键前提核实（实现前必须知道的三个事实）

### 2.1 ⚠️ 版本事实：实装 LangGraph 1.x，不是 `requirements.txt` 写的 0.2

`backend/requirements.txt:5,10` 写 `langgraph>=0.2` / `langchain-openai>=0.2`，但 venv 实际安装（`.venv/Lib/site-packages/*.dist-info`）是：

| 包 | 实装版本 |
|---|---|
| langgraph | **1.2.10** |
| langchain | **1.3.14** |
| langchain-core | **1.5.3** |
| langgraph-prebuilt | **1.1.0** |
| langgraph-checkpoint-sqlite | **3.1.1** |
| langchain-openai | **1.4.2** |

**影响**：`langgraph.prebuilt.create_react_agent` 在 1.1.0 已 `@deprecated`（`chat_agent_executor.py:274`，指向 `langchain.agents.create_agent`）。计划书所有 API 选型按 **1.x** 基准，不看 0.2 的教程。**P0 阶段要把 `requirements.txt` 的下界改成实际基准**（`langgraph>=1.0,<2`、`langchain>=1.0,<2`、`langchain-openai>=1.0,<2`），否则换机即崩。

### 2.2 已核实的可用 API（逐个在 venv 源码里确认存在，行号为实读）

| API | 用途 | 出处 |
|---|---|---|
| `create_agent(model, tools, *, system_prompt, middleware, checkpointer, store, ...)` | 官方新 API（**`prompt` 已改名 `system_prompt`，`pre/post_model_hook` 已被 `middleware` 取代**）。本计划**不采用**，理由见下 | `langchain/agents/factory.py:740,744-750` |
| `ToolRuntime` | 工具参数命名为 `runtime: ToolRuntime` 即自动注入 `state / context / config / store / stream_writer / tool_call_id / tools`，**不暴露给 LLM**。注意：**没有 username 字段**，username 走 state（§5.3） | `langgraph/prebuilt/tool_node.py:1663,1673-1728`；导出 `langchain/tools/__init__.py:11,20` |
| `InjectedState` / `InjectedStore` | 按参数注解注入，自动从 tool schema 排除 | `tool_node.py:1753,1829`；导出 `langchain/tools/__init__.py:11,15,16` |
| `ToolNode` / `tools_condition` | 工具执行节点与路由函数 | `tool_node.py:622,1582` |
| **工具可返回 `Command`** | 工具返回值允许 `ToolMessage \| Command \| list[...]`，用于从工具内部更新图状态 | `tool_node.py:864,927-936,969-971` |
| **未知工具名返回 ToolMessage 而非抛异常** | `_validate_tool_call` 合成非法工具消息——配对不变量在 ToolNode 层已有内建支持 | `tool_node.py:944-947` |
| **多个 tool_call 并行执行** | 异步路径 `asyncio.gather`（`:858`）；同步路径线程池 `executor.map`（`:821-824`）。§5.4 据此设计并发 | `tool_node.py:855-858,821-824` |
| `add_messages` | 消息通道的合并 reducer | `langgraph/graph/message.py:61` → `from langgraph.graph.message import add_messages` |
| `AIMessageChunk.__add__` | 流式分块相加合并成完整 AIMessage（含 tool_calls） | `langchain_core/messages/ai.py:418,633` |
| `ChatOpenAI.bind_tools` | 绑定工具调用 | `langchain_openai/chat_models/base.py:2221` |
| `interrupt()` / `Command(resume=...)` / `get_stream_writer()` | 已在本项目跑通：`graph.py:26,781,1089`；`server.py:148-180` | 现有代码 |
| `StreamMode` | `values/updates/checkpoints/tasks/debug/messages/custom`，现有 `["custom","values"]`（`server.py:159`） | `langgraph/types.py:120` |
| 工具体内 `interrupt()` 被允许 | `except GraphBubbleUp: raise`，不被错误处理吞掉（**但我们仍不用**，理由见 §5.2） | `tool_node.py:973-983` |

### 2.3 环境里已经跑通的等价模式（可直接照抄，不必冒险）

`graph.py:781`（`wait_answer_node`）和 `graph.py:1089`（`wait_report_node`）已经证明：**interrupt + Command(resume=结构化载荷) + get_stream_writer 推 custom 事件 + AsyncSqliteSaver 持久化** 这套组合在本项目、本模型（DeepSeek 兼容接口）、本前端下可用。`graph.py:115-139` 的 `_stream_chain` 证明了**节点内 LLM astream + writer 逐字推流**的模式可用。统筹 agent 复用同一套模式，不引入新的运行时风险。

> 由此得出明确选型：**主循环手写四节点 StateGraph（load_context / agent / tools / wait_confirm + budget_guard 条件边），而不是 `create_agent` + `HumanInTheLoopMiddleware`**。三条理由：
> 1. HITL 中间件的 resume 契约要求 `{"decisions":[...]}` 且**决策条数必须等于挂起 tool call 条数**，否则 `ValueError`（`human_in_the_loop.py:438`）；`DecisionType` 有 4 种含 `respond`，前端只做 approve/reject 就会漏。
> 2. `interrupt()` 写在工具体内依赖 contextvar + scratchpad（`types.py:910-913`），脱离原 task 上下文就 KeyError；且**节点重跑会重放工具前半段副作用**——与 `graph.py:1-13` 文件头记录的坑同源，已经吃过一次。
> 3. 手写图与面试图同构，答辩/维护时一套心智模型讲两个图。此外 `create_agent` 的 middleware 体系（`SummarizationMiddleware` 等）是 1.x 才稳定的新面，引入它等于把两处风险换成一处未验证风险，不符合"每阶段可演示"。

### 2.4 断言核实台账（防错机制，v2 新增）

v1 出过一次错误：把"barge-in 需要服务端知道播放进度"写进了计划书，事实是**播放进度只有浏览器知道**（已在两份计划中修正）。根源是把"应该如此"当"确实如此"。本版的对策是把核实变成**受控产物**：

**规则：任何一条会指导写代码的机制断言，落笔前必须满足三者之一——(a) 我在本仓库读到出处并给出 file:line；(b) 我在 `.venv` 源码读到出处并给出 file:line；(c) 明确标注"实现时先验证"，且写明验证方法。**

台账（本版新增断言的核实状态）：

| 断言 | 状态 | 出处 / 验证方法 |
|---|---|---|
| venv 实装版本为 1.x | ✅ 已核 | `.venv/Lib/site-packages/*.dist-info`（§2.1 表） |
| `ToolRuntime` 字段集合（无 username） | ✅ 已核 | `tool_node.py:1673-1728` |
| 多 tool_call 并行执行 | ✅ 已核 | `tool_node.py:855-858`（gather）、`:821-824`（executor） |
| 工具可返回 Command 更新 state | ✅ 已核 | `tool_node.py:864,969-971` |
| **工具返回 Command 时不会自动补 ToolMessage** | ✅ 已核 | `tool_node.py:881-916`：只有非 Command 输出被包成 `{messages_key:[...]}`；纯 Command 输出直接追加 → **提议工具必须自己把配对 ToolMessage 放进 `update["messages"]`**，否则悬空 tool_call |
| 未知工具名合成错误 ToolMessage | ✅ 已核 | `tool_node.py:944-947` |
| `add_messages` reducer | ✅ 已核 | `langgraph/graph/message.py:61` |
| `AIMessageChunk` 可 `+` 合并 | ✅ 已核 | `langchain_core/messages/ai.py:633` |
| `bind_tools` | ✅ 已核 | `langchain_openai/chat_models/base.py:2221` |
| SQLite 并发写安全基线 | ✅ 已核 | `knowledge.py:29-32` 的 `sqlite3.connect(_DB_PATH, timeout=10)`——busy timeout 10s，与现有 REST 端点（def + 线程池）同等并发强度 |
| Chroma 持久客户端模式 | ✅ 已核 | `kb_parent.py:75-86`（`PersistentClient` + `get_or_create_collection` + `hnsw:space=cosine`），记忆索引照此镜像 |
| `server.py` 用已废弃的 `@app.on_event`，无 shutdown 钩子 | ✅ 已核 | `server.py:834`（startup），全文无 shutdown——§5.10 要补 |
| DeepSeek 兼容接口 tool_calls 流式 | 🔶 实现时验证 | P0 写一个 20 行脚本：`bind_tools` 后 `astream`，打印 chunk 的 `tool_call_chunks` 是否分片到达、最终 `+` 合并后 `tool_calls` 是否完整。**这是唯一押在服务行为而非本地源码上的断言** |
| **`runtime` 参数必须有 `ToolRuntime` 类型注解才会被注入** | ✅ 已核（实现期踩到） | `_get_all_injected_args` 用 `get_type_hints(func)` 检测（`tool_node.py:1983-2004`）；只写 `runtime=None` 不写注解 → 检测不到 → 运行时 `runtime is None`。全部工具签名已改为 `runtime: ToolRuntime = None` |
| **`handle_tool_errors` 的处理器签名必须是 Exception 子类注解** | ✅ 已核（实现期踩到） | 写 `exc: BaseException` 会在构图时直接 `ValueError`（`tool_node.py:468-496`）；已改为 `exc: Exception` |
| **工具返回 dict 会被序列化成 JSON 字符串** | ✅ 已核 | `msg_content_output` 对任意对象尝试 JSON 序列化（`tool_node.py:309-321`），所以提案标记走内容解析是可行的；但返回 `Command` 时不补配对消息（见上条） |
| offerpilot / agent-study 引用 | ⚠️ 来源为子代理调研，出处已标注但未逐条亲验 | 实现对应机制时按需抽查；§11 表中带 🔶 的条目尤其如此 |

---

## 三、目标形态与验收剧本

计划书好不好，看能不能拿这五段对话跑通。每段都是**可验证**的验收用例。

### 剧本 A：一句话起面试（意图路由 + 抽参 + 确认 + 交接）

```
用户（抽屉）: 帮我面一场，中级难度，8 题，用我上周传的那份简历
agent: 思考 → tool: read_resume_summary()
       → 参数齐了 → 触发 start_interview 提案（模型不可主动调用，§5.5）
       → [interrupt: proposal_asked]
agent: 「准备好了：大模型应用开发 · 8 题 · Intermediate · 用简历 2026-09-13 那份」
       ┌────────────────────────────────┐
       │ 岗位   [大模型应用开发 ▾]        │   ← 可编辑（服务端声明的白名单字段）
       │ 题量   [8]  难度 [Intermediate ▾]│
       │ 模式   (●) 题库  ( ) 项目深挖     │
       │        [ 开始面试 ]  [ 取消 ]    │
       └────────────────────────────────┘
用户点「开始面试」
前端: handoff 事件 → router.push('/interview') → 自动 sendConfig(...) → 面试图接管
```

**验收**：`[开始面试]` 后面试能在 8 题 · Intermediate 下正常开局；**没有任何路径能让 agent 绕过卡片造成面试会话**（写成测试：调用提案流程后断言无 `iv_` 前缀面试 thread 被创建）。

### 剧本 B：跨报告分析（多工具编排 + 只读自动执行）

```
用户: 根据我最近三次面试报告，说我该补什么
agent: tool: list_reports() → 取最近 3 个 report_id
       → 并行: read_report_radar(id1) (id2) (id3)      ← §5.4 并行执行
       → tool: read_report_weak_points(id1..id3)
       → 综合 → 回答，并按 kind=weakness_pattern 调 remember
```

**验收**：回答里引用的每个分数都能在对应 JSON 里找到出处；`agent_memory` 里出现一条带 `source_ref` 指向三个 report_id 的记录。**工具调用次数由 LLM 依对话自行决定**——问"上次面试"就 1 份，问"最近三次"就 3 份。

### 剧本 C：知识库问答路由（复用既有 KB 能力，不重造）

```
用户: 我笔记里关于 RAG 分块重叠是怎么记的？
agent: tool: kb_ask(question=..., top_k=5)   ← 内部就是 kb_parent.search + kb_llm.answer_from_knowledge
       → 回答 + 附来源笔记标题
```

**验收**：走的是 `server.py:906` 同一条检索链，**没有**新增第二套 RAG。

### 剧本 D：记忆闭环（写入、检索、可见、可删）

```
用户: 别再给我一堆客套话了，直接说技术
agent: tool: remember(kind="preference", text="要求直给、不要客套铺垫", importance=8)
       → 「收到」（回答立刻变短）
—— 第二天新会话 ——
用户: 帮我准备一面
agent: load_context 已把该偏好注入 system prompt → 直接给硬核版
抽屉「记忆」面板: 列出这条，可删除
```

**验收**：新会话无需重复交代；删除后不再注入。**面板必须存在**——产品化里不可见的记忆就是黑箱。

### 剧本 E：会话历史与断线恢复（v2 新增，§5.12）

```
—— 抽屉聊了 8 轮后刷新页面 ——
前端: GET /api/assistant/sessions → 列表（含标题、时间）
用户点开
前端: 新开 WS，携 session_id → 后端 load_context 读 checkpointer 恢复 thread →
      历史消息从 assistant_messages 表渲染 → 继续: "接着刚才的，把我上次说的再展开"
agent: 无需重新交代任何上下文
```

**验收**：刷新/断网重连后对话可续；删除会话后 checkpointer 线程与消息表同步清理（无孤儿数据）。

---

## 四、架构总览

```
┌──────────────────────── Vue3 前端 ────────────────────────┐
│  AppLayout.vue                                            │
│   ├─ side-nav（现有，不动）                                │
│   ├─ .app-main → router-view（现有）                       │
│   └─ ★ AssistantDock（新增）                              │
│        ├─ FAB 小圆点（position:fixed 右下角）               │
│        └─ Drawer: MessageStream / ToolTrace / ProposalCard │
│             / MemoryPanel / SessionList / AssistantSettings│
│        useAssistantSocket.js（新增，独立于 useWebSocket）    │
│        useAssistantHistory.js（§5.12 历史与设置，纯 REST）    │
└──────┬─────────────────────────────────┬──────────────────┘
   /ws/assistant（新）               REST /api/assistant/*（新）
       │                                 │
┌──────▼─────────────────────────┐  ┌────▼──────────────────┐
│  ★ assistant 层（新）           │  │ assistant/db.py       │
│  state.py  AssistantState       │  │  assistant_sessions   │
│  graph.py  四节点图             │  │  assistant_messages   │
│   load_context → agent ⇄ tools  │  │  assistant_settings   │
│   + wait_confirm + budget_guard │  │  agent_memory         │
│  tools/registry + 16 个工具     │  └───────────────────────┘
│  permission.py 三闸门           │  assistant/vector_index.py
│  events.py 事件枚举（单一源）    │   （Chroma, 镜像 kb_parent 模式）
│  persistence.py 共享 checkpointer│
└──────┬─────────────────────────┘
       │ 只调用，不修改（§1.3 例外除外）
   ┌───▼─────────┬──────────┬──────────┬──────────────┐
   ▼             ▼          ▼          ▼              ▼
 reports/*.json knowledge.db kb_parent  resume/解析   HybridRetriever
                 (notes,只读) (向量,只读) (只读)       (只读)
```

**关键接缝**：agent 与面试引擎**只通过"提案 + 前端跳转"交接，不在后端互相调用**。agent 永远碰不到面试图的 `astream(Command(resume=...))`。这条边界一旦破，面试官的相位守卫（`protocol.py:6`）就形同虚设。

**数据所有权划分**（谁建表谁管迁移）：

| 数据 | 库 | 表 | 归属模块 |
|---|---|---|---|
| 会话/消息/设置/记忆 | `assistant.db`（新，`config.ASSISTANT_DB_PATH`） | `assistant_sessions / assistant_messages / assistant_settings / agent_memory` | `assistant/db.py` |
| 记忆向量 | `assistant_chroma/`（新目录） | 集合 `agent_memory` | `assistant/vector_index.py` |
| 图状态 | `checkpoints.db`（现有） | LangGraph 自管 | `assistant/persistence.py`（共享连接） |

不复用 `knowledge.db` 的原因：知识库表归 `knowledge.py` 管（§1.2 不改内核），往别人的库里加表等于内核变更。独立库 + `conftest.py` 加 `ASSISTANT_DB_PATH` 覆盖，沿用现有隔离约定（`tests/conftest.py:18-25`）。

---

## 五、后端 agent 层设计

### 5.0 文件清单（全部新增；`server.py` 只按 §1.3 追加）

```
backend/assistant/
  __init__.py
  state.py           # AssistantState
  graph.py           # 四节点图 + 路由函数 + budget_guard
  prompts.py         # 八区块 system prompt 模板 + 拼装函数
  events.py          # WS 事件枚举（前后端契约的单一事实源）
  persistence.py     # 共享 AsyncSqliteSaver 连接（§5.10）
  permission.py      # 三闸门 + 批准指纹缓存
  budget.py          # 迭代/token/输出上限
  db.py              # assistant.db: sessions/messages/settings/agent_memory
  vector_index.py    # 记忆向量索引（镜像 kb_parent 的 Chroma 模式）
  tools/
    __init__.py      # registry 收集
    base.py          # @assistant_tool 装饰器 + AssistantTool 协议
    reports.py       # list_reports / read_report_md / read_report_radar / read_report_weak_points
    records.py       # list_interview_records / read_interview_record
    kb.py            # kb_search / kb_ask / list_notes / read_note
    question_bank.py # search_questions / list_categories
    resume.py        # read_resume_summary / list_resume_files
    memory.py        # remember / recall_memory / forget_memory
    actions.py       # propose_interview / propose_kb_session（提议型，模型不可见）
backend/tests/
  test_assistant_tools.py      # 工具单测（不打 LLM）
  test_assistant_graph.py      # 图/审批契约/配对不变量（假 LLM）
  test_assistant_memory.py     # 写入门槛/取代/衰减/recall-loop
  test_assistant_db.py         # 会话/设置 CRUD 与级联删除
  test_assistant_permission.py # 三闸门与指纹
  assistant_eval.py            # 评测跑分（真 LLM，需 key）
  data/assistant_cases.jsonl   # 评测样本
  probe_tool_stream.py         # P0 的 DeepSeek tool_calls 流式探针（§2.4）
```

### 5.1 状态定义

```python
from typing import Annotated, TypedDict
from langgraph.graph.message import add_messages

class AssistantState(TypedDict, total=False):
    # 消息通道: add_messages 合并 reducer（langgraph/graph/message.py:61）
    messages: Annotated[list, add_messages]
    # ---- 身份（server 在 thread 启动时注入, 模型与工具参数都不可见）----
    thread_id: str            # as_{username}_{session_id}（§5.10 前缀隔离）
    username: str
    session_id: int           # assistant.db 的会话 id
    # ---- 每轮动态段（load_context 写, 不进消息历史）----
    system_prompt: str
    memory_injected: list     # 本轮注入的记忆 id（recall-loop 防护）
    # ---- 提案（§5.5）----
    pending_action: dict      # offerpilot PendingAction 契约
    proposal_id: str          # arguments_digest，批准指纹缓存用
    decision: dict            # {action: approve|edit|reject, args, reason}
    denied_reasons: list      # 拒绝理由回灌
    # ---- 观测与预算 ----
    tool_trace: list          # 本轮 [{tool, args_digest, ok, ms, bytes}]（前端轨迹+评测断言）
    iter_count: int
    token_spent: int
    budget_exceeded: bool
    phase: str                # idle|thinking|awaiting_confirm|completed|error
```

`tool_trace` 单独存而不是只埋在 messages 里：前端"工具轨迹"面板和评测的 `expected_tools` 断言都要读它，放消息里会让轨迹断言退化成字符串匹配。

`username` 注入链路（闭环写死，不留缝）：`ws_assistant` 握手鉴权拿到 `user["username"]` → 构造 `initial_state = {"username": ..., "session_id": ...}` → 工具体内 `runtime.state["username"]`（`ToolRuntime.state` 已核存在，`tool_node.py:1722`）→ 工具实现把它传给 `db.py` / `kb_*` 的既有按用户隔离函数。**模型侧永远见不到这个值**：它不在任何工具 args_schema 里，也不进消息历史。

### 5.2 图结构（节点签名级）

```
START → load_context → agent_node ──route_after_agent──┬─(有 tool_calls)→ tools_node ──route_after_tools──┐
                  ▲                                    └─(无 tool_calls)→ END                          │
                  │                                                                                     │
                  └─(预算未超且未确认完) ◄──────────────────────────────────────────────────────────────┘
   tools_node ─(state.pending_action 存在且未决)→ wait_confirm ─interrupt─→ confirm_router
                                                                 ├─ approve/edit → agent_node（收尾话术）→ handoff
                                                                 └─ reject → END（带说明+配对消息）
   tools_node ─(iter/token 超限)→ budget_guard: 注入收敛指令一次 → agent_node（最后一次，不带工具）→ END
```

六个节点的签名与职责（`runtime.state` 之外不引入魔法）：

```python
def load_context_node(state: AssistantState) -> dict:
    """每轮入口: 拼 system prompt 的动态段（§5.8），做记忆检索注入（§5.7）。
    返回 {"system_prompt": ..., "memory_injected": [...], "tool_trace": [], "iter_count": 0, ...}。
    单独成节点是为了让动态段落在静态前缀之后（缓存友好，context-handbook:112）。"""

async def agent_node(state: AssistantState) -> dict:
    """唯一调 LLM 的节点。不执行工具。
    llm = get_fast_llm().bind_tools(visible_tools)   # bind_tools 已核 base.py:2221
    msgs = [SystemMessage(state["system_prompt"]), *state["messages"]]
    merged = None
    async for chunk in llm.astream(msgs):
        merged = chunk if merged is None else merged + chunk   # AIMessageChunk.__add__ 已核 ai.py:633
        if chunk.content:
            writer({"type": "assistant_delta", "text": str(chunk.content)})   # 逐字推流
    return {"messages": [merged], "iter_count": state.get("iter_count", 0) + 1,
            "token_spent": state.get("token_spent", 0) + _estimate_tokens(merged)}

def route_after_agent(state) -> str:
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else END

async def tools_node(state) -> ...:   # ToolNode 实例, 见下
    ...

def route_after_tools(state) -> str:
    if state.get("budget_exceeded"):        return "agent"       # 收敛轮（不带工具）
    if state.get("pending_action") and not state.get("decision"): return "wait_confirm"
    return "agent"

async def wait_confirm_node(state) -> dict:
    """interrupt() 放这个独立节点, 与 graph.py:781 wait_answer 同构。
    工具体内绝不调 interrupt()——理由 §2.3 第 2 条。"""
```

**`tools_node` 用 `ToolNode` 实例还是自写？** 用 `ToolNode(tools, handle_tool_errors=custom)`，因为三件事它已经做对且已核实：并行执行（`:855-858`）、未知工具名合成错误 ToolMessage（`:944-947`）、`handle_tool_errors` 把异常转成可自纠消息（§5.11 要的就是这个）。我们要自定义的只有 error handler 的文案。

**`system_prompt` 不进 `messages`**：每次调用时由 `agent_node` 临时拼 `[SystemMessage, *history]`，历史里永远只有用户/助手/工具消息。好处：改 system prompt 不产生历史噪音；`assistant_messages` 表存的就是纯对话，前端渲染历史不用过滤系统消息。

**流式的两条通路**：正文 token 走 `agent_node` 内 `astream + writer`（`assistant_delta`，模式已被 `graph.py:115-139` 验证）；工具起止与结果走 `ToolNode` 的 `runtime.stream_writer`（工具内 `writer({"type":"tool_call"/"tool_result", ...})`）。**不启用 `messages` stream mode**——两条 custom 通路已覆盖我们前端需要的全部事件，少一个 mode 少一份前端解析分支。

### 5.3 工具注册约定（"后续接入别的功能"的落点）

每个工具一个 `@assistant_tool` 声明，`registry.py` 自动收集。字段设计抄 `analysis_zcode s03_tool_dual_schema:26-29` 的"契约冻结"思路 + `mcp-handbook:299-303` 的 annotations：

```python
@assistant_tool(
    name="read_report_radar",
    description=(            # description 是写给 LLM 的 API 文档，五要素缺一不可
        "读取一份面试报告的雷达数据（四维分、分类均分、逐题分、强弱项、难度变化）。"
        "用于任何基于分数的分析。"
        "不要用读整份 markdown 来找分数——radar 更准更省 token。"      # 何时【不】用
        "report_id 来自 list_reports。"                              # 参数来源
        "report_id 不存在时返回 found=false，不是错误。"              # 失败返回什么
    ),
    args_schema=ReadRadarArgs,        # pydantic：required 标齐、枚举写 enum
    risk="read",                       # read | write | execute
    needs_approval=False,
    model_visible=True,                # False = 从 bind_tools 的可见面摘除（§5.5 提案工具）
    max_output_chars=4000,             # 超限落盘留指针（§5.8 压缩第 1 步）
)
def read_report_radar(report_id: str, runtime: ToolRuntime) -> dict:
    username = runtime.state["username"]    # §5.1 注入链路
    ...
```

四条硬约定：

1. **`username` 永远不是工具参数**，从 `runtime.state` 取。这是多用户隔离的唯一防线，写进单测（构造一个"模型试图传 username"的 tool_call，断言它不在 args_schema、注入值不被覆盖）。
2. **`risk` 必须如实标注**，但**服务端不依赖注解做安全决策**（`mcp-handbook:305` 明说注解是给模型看的提示，不是权限）；真正的门控在 `permission.py`（§5.6）。
3. **返回值一律是 dict + `found`/`ok` 字段**，不抛异常给上层循环。唯一例外：**提议型工具返回 `Command(update=...)`**（§5.5，`tool_node.py:864` 已核支持）。
4. **工具数量控制**：只读工具若超过 15 个，按 `mcp-handbook:396` 合并成"一个工具 + `method` 参数承载子操作"；`multiagent-handbook:71` 的原则是工具面**只减不增**，每加一个都要说清它降低了哪类误选。

**初始工具清单（17 个）**

| 工具 | risk | 审批 | 模型可见 | 复用的现成实现 |
|---|---|---|---|---|
| `list_reports` | read | 否 | ✅ | `server.py:444` 列表逻辑（抽公共函数，等价搬移） |
| `read_report_md` | read | 否 | ✅ | `api_get_report` `server.py:472` |
| `read_report_radar` | read | 否 | ✅ | `api_get_report_radar` `server.py:488` |
| `read_report_weak_points` | read | 否 | ✅ | `api_get_report_weak_points` `server.py:512` |
| `list_interview_records` | read | 否 | ✅ | `server.py:599` |
| `read_interview_record` | read | 否 | ✅ | `server.py:624` |
| `kb_search` | read | 否 | ✅ | `kb_parent.search` `server.py:869` |
| `kb_ask` | read | 否 | ✅ | `kb_parent.search` + `kb_llm.answer_from_knowledge` `server.py:906` |
| `list_notes` | read | 否 | ✅ | `knowledge.list_notes` |
| `read_note` | read | 否 | ✅ | `knowledge.get_note` |
| `search_questions` | read | 否 | ✅（面试进行中可用，但仅返回题面/分类/难度/ID） | `HybridRetriever.get_question`（只读） |
| `list_categories` | read | 否 | ✅ | `HybridRetriever.get_categories` |
| `read_resume_summary` | read | 否 | ✅ | uploads + `resume.parser`；R1 落库后换数据源（RESUME 计划 §六） |
| `remember` | **write** | **是（默认自动放行，可配置）** | ✅ | 新 `agent_memory` 表 |
| `recall_memory` | read | 否 | ✅ | 同上 |
| `forget_memory` | **write** | **必须** | ✅ | 同上（删除记忆比写入更危险） |
| `propose_interview` | **execute** | **必须** | ❌ **模型不可见** | 只写 `pending_action`，不碰面试图 |
| `propose_kb_session` | execute | 必须 | ❌ | 提议跳转 `/knowledge/chat` 并预填问题 |

> `remember` 特殊：它是写操作，但你选的是"agent 自主调 remember"，所以默认 `needs_approval=True + auto_accept 白名单命中`。设置里可切成"每条记忆都要我点确认"。

### 5.4 工具执行语义（并发与数据安全，v2 新增）

已核实 `ToolNode` 异步路径用 `asyncio.gather` 并行执行同一轮的多个 tool_call（`tool_node.py:855-858`）。这带来三个必须显式处理的事实：

1. **只读工具并行是白捡的延迟优化**——剧本 B 的"并行读 3 份 radar"就靠它，不需要我们写任何并发代码。
2. **同步工具函数会怎样？** `_afunc` 里 `_arun_one` 对同步工具的处理走 Runnable 的异步包装（LangChain 对 sync runnable 默认在线程池执行）。**写规则：所有工具统一写成 `async def`**，体内对同步的重操作（sqlite、chroma、文件 IO）用 `await asyncio.to_thread(...)` 包——项目已有同款模式（`server.py:52` 引入 `run_in_threadpool`，ASR 端点即此用法），统一 `async def + to_thread` 避免混用两套线程化机制。
3. **SQLite 并发写**：`knowledge.py:29-32` 的连接带 `timeout=10`（busy timeout），与现有 REST def 端点（线程池并发）同强度，写冲突概率可忽略。`assistant/db.py` 沿用 `sqlite3.connect(path, timeout=10)` 同款约定，并在 `init_db` 里执行 `PRAGMA journal_mode=WAL`（读不受写阻塞，抽屉高频读+偶发写场景正合适）。**禁止跨线程复用连接**——每函数 `_connect()` 新开（knowledge.py 同款，`kb_parent.py:93` 也是即开即用）。
4. **一个全局互斥锁必须存在**：`remember`（写 agent_memory + 向量索引）与 `forget_memory` 同轮并行时向量库与表可能不一致。`assistant/db.py` 提供 `asyncio.Lock`，memory 两个写工具进入时先取锁。

### 5.5 提议-确认机制（整层的心脏）

> **本节契约照抄 offerpilot 的 `PendingAction`**（`web/src/types/chat.ts:92-134`）。它是已验证过的实现，比自创结构省一轮返工。

**第一条修正：`start_interview` 不由模型主动调用。**

offerpilot 的做法是意图路由走**确定性动作通道**：前端显式传 `pilot_action`，服务端据此构造 PendingAction，`kind ∈ normal_agent | collecting_jd | pending_confirmation | cancelled`（`ai/deterministic_actions.py:64-91`），并明确"**普通对话关键词不触发写**"。写动作在工具元数据里可声明为**模型不可主动调用**（`specs/2026-08-12-application-outcome-feedback-design.md:82-87`）。

我们采纳同一条：`propose_interview` 的 `model_visible=False`（§5.3 表），改由两条入口之一触发——

- 用户在抽屉里点「开始面试」快捷入口（显式）；或
- 模型输出一个**结构化标记**（`{"intent":"start_interview","slots":{...}}`），由 `agent_node` 的后置解析器识别，服务端据此构造提案。模型只是在"表达意图"，**执行权不在它手上**。

理由：起面试是我们这一层唯一的高代价动作。让模型自主决定何时调一个有副作用的工具，等于把"用户没想面试却被打进面试流程"的风险交给采样噪声。抽参归模型（它擅长），发起归代码（它必须确定）。

**第二条修正：可编辑字段由服务端声明，不由模型给。**

```python
EditableField{
    field: str,            # "question_count" | "difficulty" | "mode" | ...
    value_type: str,       # string | long_text | enum | datetime | number | boolean
    options: list | None,  # enum 的封闭取值
    clearable: bool, clear_value: Any,
}
```

出处 `ai/tool_specs/metadata.py:358-371`。三条要点照搬：

1. **可编辑范围是白名单，后端逐字段复验并拒绝越界**（`ai/confirmation.py:42-60`）——用户改不动 `role_key` 之外的身份字段。
2. **摘要由服务端按 descriptor 重渲染**（`confirmation.py:101-158`）。模型给的文案只当"给用户看的一段话"，卡片上的参数永远是服务端渲染的。
3. **身份字段结构性不可编辑**：哪个岗位、哪份简历，一旦进提案就锁死。

**提案对象（我们的裁剪版）**

```python
PendingAction{
    operation_id: str,
    kind: "interview" | "kb_session",
    human: str,                    # 服务端渲染的人类可读摘要
    args: dict,                    # 提案参数
    editable_fields: list[EditableField],
    evidence: list[{source, path, excerpt}],
    confirmation_token: str,       # 绑 session_id + revision + args_digest
    risk_hint: str,
}
```

**三态与指纹**（`contracts.py:654-661`、`agent_contracts.py:161-184`）：`ConfirmationRequired | ReadyToExecute | PreparedToolCall`；提案绑 `sha256:` 定长 `arguments_digest`，用户编辑后另存 `effective_args_digest`——**原提案、最终批准参数、提交事实三份独立**。权威易主（同 thread 出现更新版提案）时旧的直接判定 `StalePendingAction`，不静默覆盖。offerpilot 专门立 ADR 治"用户改了参数、模型又提回旧值"（`decisions/0006-edited-confirmation-receipts.md:16-27`）：**编辑后的确认回执要绑定确定性策略并终结模型自动续答**。我们照做：`edit` 之后不再让模型自由发挥，直接发 `handoff`。

**图上的落地——包括两个已核实的关键细节**：

```python
def propose_interview(args, runtime) -> dict:
    # ① 参数校验: 必填齐不齐、枚举合不合法 → 不齐返回错误文本让模型去追问
    # ② 构造 PendingAction
    # ③ 返回普通 dict, 内容带 __proposal__ 标记。
    #    刻意不用 Command: ToolNode 对返回 Command 的工具不补配对 ToolMessage
    #    (tool_node.py:881-916), 而返回 dict 会被 msg_content_output 序列化成
    #    JSON 字符串并自动配对 (tool_node.py:309-321, 881-887)。
    #    提案载荷由 tools_node 解析 ToolMessage 内容后写入 state["pending_action"]。
    return {"ok": True, "found": True, "__proposal__": pending, "human": ...}
```

`route_after_tools` 检测 `state["pending_action"]` 存在且无 `decision` → 转 `wait_confirm`（独立节点放 `interrupt()`，与 `graph.py:781` 同构）。恢复载荷是我们自己的结构，不是 HITL 中间件的 `{"decisions":[...]}` 契约：

```python
async def wait_confirm_node(state):
    writer = get_stream_writer()
    writer({"type": "proposal_asked", "pending": state["pending_action"]})   # 全量契约下发
    decision = interrupt({"operation_id": ..., "kind": ...})
    return {"decision": _normalise_decision(decision), "phase": "confirm_received"}
```

- 恢复载荷：`{"action": "approve"|"edit"|"reject", "args": {...}, "reason": "..."}`
- `edit` → 服务端按 `editable_fields` 白名单逐字段合入，重算 `effective_args_digest`，发确定性回执并 `handoff`。
- `reject` → `reason` 进 `denied_reasons`，补一条配对 ToolMessage（§5.11），走 END。
- `approve` → 发 `handoff`，前端 `router.push('/interview')` + `sendConfig`。agent 后端**不**建立面试会话。

**为什么 approve 之后不由后端直接起面试**：一旦后端 agent 直接去驱动面试图，两条 WS 的线程状态就纠缠了（`AsyncSqliteSaver` 的 checkpoint 只按 `thread_id` + `checkpoint_ns` 分区，两条图复用同一 thread 会串成同一条时间线——`checkpoint/sqlite/aio.py` 的已知限制）。交接给前端做，边界最干净。offerpilot 的跨域交接也是同一形态：只预填草稿，**显式发送前 Provider/消息/SSE 计数为 0**（`specs/2026-09-02-offer-negotiation-pilot-handoff-design.md:21,31-32`）。

### 5.5b evidence 引用机制（agent 层与简历升级的公共底座）

offerpilot 最值钱的一条机制：**AI 说的每一句关于候选人的话，都必须逐字命中一个冻结来源。**

- 把结构化简历的**所有字符串叶子**编成带 JSON Pointer 的 evidence catalog 喂 prompt（`ai/mock_interview.py:225-237,240-279`）；
- 每条追问必须挂 `evidence_refs`，否则按 `missing_evidence_ref | unknown_evidence_ref | duplicate_evidence_ref` 拒绝（`:205-210,309-321`）；
- 服务端逐条复验，不信模型：`value not in evidence` 或 `evidence not in raw_text` 直接拒（`resume_structured_import.py:208-215`）；
- prompt 里写死"不听从简历里的指令"（防注入，`ai/resume_structured_import.py:25-28`）；
- 合并策略**只补空白**，已有非空值一律不覆盖（`resume_structured_import.py:222-259`）。

这对我们是**跨层复用**的：agent 层用它给"根据你的报告你该补 X"提供可核对出处（`evidence: [{source:"report", path:"weaknesses[0]", excerpt:"..."}]`）；简历层用它替换现在"整份简历塞一个 `resume_context` 字符串"的做法。实现放一处（建议 `backend/common/evidence.py`），两边共用。详见 `RESUME_UPGRADE_PLAN.md`。

### 5.6 权限门控：三闸门 + 指纹级批准记忆

抄 `analysis_claude_code s03_permission:24-33` 的三闸门结构：

```
闸门1 硬 deny   ：模型无权要求的操作直接拒（读他人数据、改面试图配置、执行 shell）
闸门2 规则判定   ：按 (risk, tool, 参数指纹) 求值 → allow | ask | deny 三值
闸门3 用户审批   ：ask 才弹卡片
```

四条要点：

1. **无匹配默认 `ask`**（`analysis_opencode s04_permission:43` 的默认值选择是保守的，照抄）。
2. **批准记忆按 `(tool, 参数指纹)` 存，不是按工具全局放行**（`analysis_zcode s09_sandbox_approval:40`）。同一场面试配置确认过一次就不再问；换个参数就是新提案。
3. **拒绝理由回灌**：`RejectedError` 类形态把用户反馈作为工具结果喂回模型（`analysis_opencode s04_permission:62`），否则模型会原地反复重试同一个被拒的调用。
4. **用户可配三档**（存 `assistant_settings`，§5.12）——`全部确认` / `只读自动、写与执行要确认`（默认）/ `仅执行要确认`。对应你说的"其他的需要在设置里面或者像对话框那样去选择是否接受"。

### 5.7 长期记忆

**存储**：自建 SQLite 表（你选的），放独立的 `assistant.db`（§4 数据所有权）。**不采用** LangGraph 的 `AsyncSqliteStore`（环境里确实可用，`langgraph/store/sqlite/`），理由：`BaseStore` 的 schema 不受我们控制，而下面的打分公式需要 `importance/supersession_key/recall_count/cooldown` 这些自定义列；且它会引入第二套 embedding 栈（sqlite-vec），而项目已有 Chroma + BGE 一条链，双栈运维不划算。

```sql
CREATE TABLE IF NOT EXISTS agent_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,            -- 作用域，永远后端注入
    kind TEXT NOT NULL,                -- fact | weakness_pattern | preference | project
    origin TEXT NOT NULL,              -- user_said | agent_inferred | report_derived
    text TEXT NOT NULL,
    importance INTEGER NOT NULL,       -- 写入时打一次分，<6 拒写
    source_ref TEXT NOT NULL DEFAULT '',   -- report_id / note_id / thread_id，可追溯
    trigger_keywords TEXT NOT NULL DEFAULT '',
    ts TEXT NOT NULL,
    last_recalled_at TEXT,
    recall_count INTEGER NOT NULL DEFAULT 0,
    superseded INTEGER NOT NULL DEFAULT 0, -- 取代标记，不做删除
    supersession_key TEXT NOT NULL DEFAULT '',
    cooldown_s INTEGER NOT NULL DEFAULT 86400,
    expires_at TEXT                    -- 意图类默认 90 天
);
```

字段来源：`context-handbook:489,190,217,206`。三条机制是这套记忆能不能用的分水岭：

1. **写入三门槛**（`context-handbook:495-504,200`）：
   - `importance < 6` 拒写（拦掉"用户今天心情不错"这种噪声）
   - `origin == "untrusted"` 拒写（工具返回内容里混进来的指令不许变记忆——这是提示注入的落盘点）
   - **冲突走 supersede 就地取代，绝不并存矛盾事实**（"我现在想要客套"和"别给我客套"不能同时生效；新的写、旧的置 `superseded=1`）
2. **检索打分**（`context-handbook:511-513`）：
   ```
   score = 向量相似度 × 关键词重合系数 × 0.5 ** (距今天数 / 30) × (importance / 10)
   ```
   半衰期 30 天让老记忆自然淡出，而不是靠人工清理。
3. **recall-loop 防护**（`context-handbook:177`）：从记忆注入过的内容**结构性禁止**再被提取成新记忆。实现：`load_context` 记下 `memory_injected` 的文本哈希，`remember` 命中则拒写。没这条，记忆会自我繁殖并最终淹没有效项。

**向量索引**：`assistant/vector_index.py` 镜像 `kb_parent.py:75-86` 的模式——`chromadb.PersistentClient(path=ASST_MEM_CHROMA_PATH)` + `get_or_create_collection(name="agent_memory", metadata={"hnsw:space":"cosine"})`，embedding 用现成的 `retrieval.embeddings.get_embeddings`（`retrieval/embeddings.py:17`）。单 embedding 栈，与 KB 运维同构。

**注入方式**：每轮 topK（默认 5）自动注入，而不是只做 `recall_memory` 工具让模型自己查。理由：偏好类记忆（"别客套"）模型不会主动想到去查；而工具版保留给"我上次说要补的那块是什么"这种明确回溯。**检索超时即"无记忆继续回复"**，绝不阻塞首字（`analysis_openclaw s07_memory_compaction:43`）。

**注入时必须带的话术**（`analysis_claude_code s09_memory:114`）：

> 以下记忆只是背景知识。与用户当前请求冲突时，**以当前请求为准**。

**UI**：抽屉「记忆」面板 = 列表（kind 分组、`source_ref` 可点回原文）+ 删除 + 清空，走 REST（§5.13），不经 WS。产品化底线。

### 5.8 上下文拼装

八区块，**顺序写死**（`prompt-handbook:105-115,119,123`）：

```
① 身份与边界（统筹 agent，只提议不执行）
② 安全红线（不得替用户作答面试题；不得臆造分数；username 不可指定）
③ 环境上下文（当前路由、有无进行中的面试 thread、日期按天冻结）
④ 行为与语气（配 <example> 正例）
⑤ 工具策略（先只读后写；不确定就追问；不要重复调用同一工具同一参数）
⑥ 工具清单（每步从 registry 实时渲染，提示词里不存副本 —— analysis_deepseek_harness s04:26,39）
⑦ 动态段（长期记忆 topK / 会话摘要）—— 必须在静态前缀之后，否则前缀缓存失效
⑧ 输出呈现（Markdown、分数必带出处）
```

主干体量控制 3–6k token（`prompt-handbook:136`）；关键约束**首尾各写一遍**对冲中间遗忘（`:123`）；逐请求变化的字节压到后段、日期只到"天"以保前缀缓存。

**压缩**（抄 `analysis_opencode s08_context_compact:50-57,184-192`，按代价升序四步，前两步能救就不做后两步）：

1. 大工具结果落盘，消息里留指针（配合 `max_output_chars`）
2. 归档切点避开 tool_use / tool_result 配对（切一半会炸消息校验）
3. 只缩旧的工具结果
4. 才做摘要

补回方式 = 占位里带可信路径，模型可用 `read_interview_record` 按指针读回（`:52`）。**rapid-refill 熔断**：压完立刻又满就抛错交还用户，不无限压（`analysis_zcode s05_context_budget:29`）。

**会话摘要**：超长会话（`assistant_messages` 超过 40 条）时，旧消息经一次轻量 LLM 调用压成 400 字摘要存 `assistant_sessions.summary`，`load_context` 注入第 ⑦ 区块。面试图同款思路见 `agent/memory.py` 的压缩阈值（`config.py:105`）。

### 5.9 预算与停机

| 项 | 默认 | 依据 |
|---|---|---|
| `max_iterations` | 6 | 一次典型分析（list→读 3 份→答）是 5 步；6 留一档余量 |
| `max_tool_calls_per_iter` | 4 | 防单步爆炸 |
| `token_budget` | 8k/轮 | 超出→`budget_guard` 逼模型收敛给结论 |
| 单工具输出上限 | 4000 字 | 超限落盘留指针 |
| 工具超时 | 30s（对齐 `api/index.js:6`） | KB 问答含 LLM，慢 |
| 总墙钟 | 60s | 超时推 `budget_exceeded` + 已有结论 |
| 记忆注入条数 | topK=5 | `context-handbook` 惯例 |

停机靠语义事件而非纯计数（`analysis_zcode s01_three_layer_loop:34`）：模型不再发 `tool_calls` 即结束，预算只是天花板。超限的收尾方式抄 `analysis_opencode s01_runloop:33,65`：末轮**追加**"预算已用尽，请基于已有信息给结论"的指令再走一轮（且这轮 `bind_tools([])` 不带工具），比一刀切断用户体验好。

### 5.10 通道与线程隔离（一个会致命的细节）

**现状核实**：`server.py:136-145` 在 `get_graph()` 里 `aiosqlite.connect` 后把 `AsyncSqliteSaver(conn)` 存进模块级 `_checkpointer`，懒加载单例；全文只有 `@app.on_event("startup")`（`:834`），**没有 shutdown 钩子**——`AsyncSqliteSaver` 的文档警告：不关连接会让 graph hang（`checkpoint/sqlite/aio.py:53-61`）。

**方案**（`server.py` 两处受控小改，§1.3 已列）：

1. 新建 `assistant/persistence.py`，持有连接与 saver 的懒加载单例：
   ```python
   _conn: aiosqlite.Connection | None = None
   _saver: AsyncSqliteSaver | None = None
   async def get_shared_saver() -> AsyncSqliteSaver: ...   # 建连 + setup()，幂等
   async def close_shared_saver() -> None: ...             # 幂等关闭
   ```
2. `server.py` 的 `get_graph()` 改为调 `get_shared_saver()`（等价搬移约 15 行，行为不变：同一路径 `config.CHECKPOINT_DB_PATH`、同一个实例）。
3. `server.py` 追加：
   ```python
   @app.on_event("shutdown")     # 与现有 startup 风格一致，不引入 lifespan 重构
   async def _close_checkpointer():
       await persistence.close_shared_saver()
   ```

**共用是允许的、串线是不允许的**：`AsyncSqliteSaver` 实例可被两张图共用（写路径全在 `self.lock` 内串行，源码层面无 per-graph 状态），但 **checkpoint 只按 `thread_id` + `checkpoint_ns` 分区**。所以：

- assistant thread_id 前缀必须是 `as_`，面试是 `iv_`（`server.py:1151`）。同前缀不同图复用 thread_id 会让 `get_state` 读到另一张图的状态。
- **P0 写一条测试**：两张图各起一个 thread，断言互相 `aget_state` 读不到对方的 state。

### 5.11 配对不变量（最该抄的一条）

> **任何路径下，每个 `tool_call` 必须有配对的 `tool_result`** —— 包括异常、被拒、被取消、非法工具名、参数 schema 不匹配、以及**工具返回 Command 的路径**。

依据：`analysis_codex s03_tool_registry:31,47` 与 `analysis_zcode s03_tool_dual_schema:30,46`。它们落地为：registry miss 与 schema 失败都合成 `{ok:false, error}` 作为工具结果落历史，模型下一轮自行纠正；早退不发结果会让 UI 行永久停在 inputStreaming。

对本项目是硬约束，三条理由：
1. LangGraph 节点重放会重跑含 `interrupt` 的节点，悬空 tool_call 直接炸消息校验；
2. 前端"工具轨迹"面板靠配对渲染，缺一条就卡转圈；
3. ToolNode 已经内建了前两种（未知工具 `tool_node.py:944-947`、异常转 `handle_tool_errors` 文案）——**第三种（Command 返回路径）它不管**（`:881-916`），所以 §5.5 的提议工具必须自己补。

实现清单：
- `ToolNode(handle_tool_errors=...)` 自定义文案：错误消息带"可自纠"指引（如"report_id 不存在，请先用 list_reports 查询"），不裸抛 traceback；
- `wait_confirm` 的 reject 分支补发配对 ToolMessage；
- `propose_*` 的 `Command(update={"messages": [ToolMessage(...)]})`；
- **写进测试**：`test_assistant_graph.py` 对每个结束路径断言消息序列里无悬空 tool_call。

重试只放行瞬态错误（429/5xx/网络抖，判定基于 errorChain 而非字符串匹配——`analysis_deepseek_harness s06_llm_adapter:38-40`），其余一律回灌给模型不发火。

### 5.12 会话历史与设置持久化（v2 新增）

**为什么 checkpointer 不够**：它按 thread 存图状态（消息在 state 里），但**不支持**按用户列出会话、渲染历史 UI、删除会话（GDPR 式清理）——它不是 UI 数据源。所以双轨：

```
写路径: WS 处理器每轮结束后 append assistant_messages(user + assistant + tool_trace)
        图内状态走 checkpointer（断点续跑）
读路径: 前端 GET /api/assistant/sessions/{id} 渲染历史（REST）
        新开 WS 携 session_id → 后端用同 thread_id 让图续跑 → 上下文无缝
```

表结构（`assistant/db.py`，沿用 `knowledge.py` 的 `_connect(timeout=10)` + `row_factory` + `_migrate_columns` 风格，`knowledge.py:29-32,117-122`）：

```sql
CREATE TABLE IF NOT EXISTS assistant_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '新对话',
    summary TEXT NOT NULL DEFAULT '',        -- 超长会话的压缩摘要（§5.8）
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assistant_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    role TEXT NOT NULL,                      -- user | assistant
    content TEXT NOT NULL,
    tool_trace TEXT NOT NULL DEFAULT '[]',   -- 本轮工具轨迹 JSON（前端轨迹面板渲染用）
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assistant_settings (
    username TEXT PRIMARY KEY,
    auto_accept_level TEXT NOT NULL DEFAULT 'read_auto',   -- all_confirm | read_auto | exec_only
    memory_enabled INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);
-- agent_memory 表见 §5.7
```

**删除语义必须一次想清**（产品化的硬要求）：删会话 = 删 `assistant_sessions` + 级联删 `assistant_messages` + **删 checkpointer 对应 thread**（`AsyncSqliteSaver` 有 `adelete_thread`——实现时先核对该方法存在于 3.1.1 版，核对方法：`Grep "adelete_thread" .venv/.../checkpoint/sqlite/aio.py`；不存在则按 thread_id 批量 `adelete_checkpoint`）。**"用户可删"若删不干净，比"没有记忆"更糟**——留下的是幽灵数据。

### 5.13 REST API 面（v2 新增，全部挂 `get_current_user`）

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/assistant/sessions` | 会话列表（标题/时间/最后一条摘要） |
| POST | `/api/assistant/sessions` | 新建会话 |
| GET | `/api/assistant/sessions/{id}` | 历史消息（含 tool_trace） |
| PATCH | `/api/assistant/sessions/{id}` | 改标题 |
| DELETE | `/api/assistant/sessions/{id}` | 删除（含 checkpointer thread，§5.12） |
| GET / PUT | `/api/assistant/settings` | 自动接受档位等 |
| GET | `/api/assistant/memories?kind=&q=` | 记忆面板列表（不走向量，直接 SQL + 关键词） |
| DELETE | `/api/assistant/memories/{id}` | 删单条 |
| DELETE | `/api/assistant/memories` | 清空本人全部记忆 |
| GET | `/healthz` / `/readyz` | 存活/就绪分离（`interview-prep-app app.py:107-132` 的做法；readyz 检查 LLM key 配置、DB 可写、模型目录存在，不满足报 503 带修复指引） |

前端走现成的 `request()` 封装（`api/index.js:9`，Bearer + 超时 + 401 回登录已内建）。

---

## 六、WS 事件协议（`/ws/assistant`）

握手沿用 `?token=<jwt>` + `ws_authenticate`（`auth.py:299`），无效 token 直接 `close(4401)`（与 `server.py:1131` 同款）。**事件枚举落成 `events.py` 单一事实源**——现有 `/ws/chat` 的事件是散字符串，agent 层不重复这个债。

| 方向 | 事件 | 载荷 |
|---|---|---|
| C→S | `user_message` | `{text, session_id?}` |
| C→S | `proposal_decision` | `{operation_id, action, args, reason}` |
| C→S | `interrupt_turn` | `{}` |
| S→C | `turn_start` / `turn_end` | `{turn_id, usage, ms}` |
| S→C | `assistant_delta` | `{text}` 流式正文 |
| S→C | `tool_call` | `{call_id, name, args_digest}` |
| S→C | `tool_result` | `{call_id, ok, ms, bytes, summary}` |
| S→C | `proposal_asked` | `{pending: PendingAction 全量契约}` |
| S→C | `proposal_decided` | `{operation_id, action, effective_args_digest}` |
| S→C | `memory_written` | `{id, kind, text}` 让写入对用户可见 |
| S→C | `handoff` | `{target: interview, config}` 前端据此跳转 + sendConfig |
| S→C | `budget_exceeded` | `{used, limit, partial_answer}` |
| S→C | `error` | `{code, message, retryable}` |

**发送侧纪律**（抄 `analysis_opencode s09_app_server:36,55`）：发送队列满（128 帧）**显式回 `error` 且不静默丢事件**；WS 心跳 10s。

**WS 生命周期**：一条连接绑定一个 session（`session_id` 在第一条 `user_message` 或连接时指定）；`interrupt_turn` 只置 `cancelled` 标志让当前 `astream` 协程在下一个 chunk 边界退出，不硬杀任务（与 `run_graph_stream` 的异常传播风格一致，`server.py:181-192`）。

---

## 七、前端改动（目标树：`frontend-v2`，墨卷档案）

> **v2 修订**：本仓库原有两棵前端（`frontend/` 端口 3000，`frontend-v2/` 端口 3001）。
> **v1 已于 2026-10-08 删除，`frontend-v2`（墨卷档案）是唯一前端**（用户拍板）。
> 最新提交与已构建 dist 都在 v2，**抽屉只装 v2**（用户拍板）。v1 不做任何改动。
> v2 的差异已核实并适配：设计令牌是 `--paper/--ink/--vermilion` 一套（`styles/tokens.css`），
> 图标组件是 `Icon.vue`（名字 camelCase：`x/mic/chat/plus/trash/pen`），**没有 `useVoiceInput`**
> （已从 v1 移植），壳是 `App.vue` 的 Rail + `.main`，且 `layout: 'bare'` 的页面（首页、面试间）
> 不经过 Rail——所以抽屉必须挂在 `App.vue` 根上，这也正好满足"面试中也能用"。

### 7.1 组件树

```
App.vue（改一处: 根上挂 <AssistantDock />, bare 布局页同样可用）
└── components/assistant/
    ├── AssistantDock.vue      FAB(右下 fixed) + Drawer(420px)
    ├── MessageStream.vue      消息流（复用 v2 utils/markdown 的 renderMarkdown）+ 麦克风
    ├── ToolTrace.vue          本轮工具轨迹（折叠卡，name/ms/ok）
    ├── ProposalCard.vue       提案卡片（editable_fields 驱动渲染, 服务端 schema 即 UI schema）
    ├── MemoryPanel.vue        记忆面板（REST）
    ├── SessionList.vue        会话列表（REST）
    └── AssistantSettings.vue  三档自动接受 + 记忆开关
composables/
    ├── useAssistantSocket.js   WS（独立于 useWebSocket.js）
    ├── useAssistantHistory.js  REST: sessions/settings/memories
    └── useVoiceInput.js        自 v1 移植（本地 SenseVoice 链路不变）
```

**位置约束（必须 fixed）**：v2 的 `.main` 是文档流内容器，FAB 与抽屉若进文档流会挤版；
`position: fixed` + 高 z-index，与 toast-host 同级挂根。

### 7.2 抽屉前端状态机

```
closed → open → {idle | streaming | awaiting_confirm | error}
awaiting_confirm: 收 proposal_asked 渲染卡片 → 用户操作 → 发 proposal_decision
                  → 收 proposal_decided → (approve|edit) 收 handoff → router.push
streaming: assistant_delta 追加; tool_call/tool_result 进 ToolTrace; turn_end → idle
```

打字机复用 `useWebSocket.js:56-97` 的 reveal 机制思路但**独立实现**（那份和面试消息协议强耦合，直接 import 会把 `_speakableTypes` 等 TTS 逻辑带进来）。

### 7.3 交接时序（剧本 A 的落地）

```
Drawer                          InterviewView
  │ 收 proposal_asked              │
  │ 渲染可编辑卡片 ◄─ 用户点开始     │
  │ 发 proposal_decision(approve)   │
  │ 收 proposal_decided + handoff   │
  │ sessionStorage.assistant_pending = config  │
  │ router.push('/interview') ─────►│ onMounted: 读 assistant_pending
  │                                 │ connect() → sendConfig(role, count, difficulty, resume)
  │                                 │   （useWebSocket.js:237 已有该方法, 复用）
  │ 抽屉自动收起, 状态回到 idle      │ 面试图接管, phase 守卫生效
```

`InterviewView.vue` 的改动限于 onMounted 读预填并自动 connect+sendConfig（原手动流程保留，预填不存在时行为不变）。

### 7.4 TTS / 麦克风互斥（真实边界，不处理就是缺陷）

面试页 TTS 默认开启并会念题（`useWebSocket.js:19`）。抽屉里 agent 若也朗读，会与念题打架。规则：**存在进行中的面试 thread 时，agent 一律不朗读、麦克风归面试页独占**；agent 语音输入需用户显式按下、且此时暂停 TTS（`useVoiceInput` 已有这层：STT 开始时自动 stopTts，`InterviewView.vue:218-219`）。

### 7.5 其余改动（均在 frontend-v2）

| 文件 | 改动 |
|---|---|
| `views/InterviewView.vue` | §7.3 预填逻辑（读 `assistant_pending`，直接发原始 config 以携带 mode）；解构里补 `send` |
| `views/knowledge/KbChatView.vue` | 读 `assistant_kb_question` 预填输入框，**不自动发送** |
| `api/index.js` | 追加 §5.13 的 REST 封装 + `transcribeAudio`（v2 原本没有），沿用其 `request()` 约定 |
| `router/index.js` | 无新增路由（抽屉是全局组件，不是页面） |

---

## 八、分阶段实施（每阶段可演示）

### P0 地基（不改任何既有行为，估 2-3 人日）
- 修正 `requirements.txt` 版本下界为实装基准（§2.1）
- `probe_tool_stream.py`：**先跑 DeepSeek tool_calls 流式探针**（§2.4 最后一条），验证 `AIMessageChunk +` 合并后 tool_calls 完整——这是全计划唯一押在外部服务行为上的断言，最先消掉
- `assistant/` 目录、`AssistantState`、四节点图骨架（假工具、假 LLM 可跑通 turn）
- `/ws/assistant` 端点 + 握手鉴权 + `events.py` 枚举 + 心跳
- `tools/base.py` 注册约定 + `model_visible` 过滤 + `runtime.state["username"]` 注入链路
- `persistence.py` 共享 saver + `server.py` 两处受控小改（§5.10）+ shutdown 钩子
- 前端：FAB + Drawer + `useAssistantSocket`，能 echo 一条流式回复
- 测试：两图 thread 互不可见；"模型传 username 被忽略"

**验收**：抽屉能连通、能流式；`/ws/chat` 面试流程回归全绿；现有测试套件 `pytest backend/tests` 不新增失败。

### P1 只读工具 + 综合分析（第一次能演"聪明"，估 4-5 人日）
- `reports` / `records` / `kb` / `notes` / `question_bank` / `resume` 六组只读工具（全部 `async def` + `to_thread`，§5.4）
- 八区块 prompt + `load_context` 节点
- 工具轨迹面板
- `tools/` 全量单测（不打 LLM）
- 并行执行验证（剧本 B 的"3 份 radar 并行"）

**验收**：剧本 B、剧本 C 跑通；轨迹里每个 `tool_call` 都有配对 `tool_result`；只读并行确有延迟收益（对比日志）。

### P2 意图路由 + 抽参 + 提议-确认（估 4-6 人日）
- `propose_interview` / `propose_kb_session`（`Command(update=...)` 带配对消息，§5.5）
- `wait_confirm` 节点 + `interrupt` + approve/edit/reject 三路
- 缺槽追问（必填不齐 → 模型必须问，**不许自己填默认值**——这条写进 prompt 红线与评测判据）
- 前端可编辑提案卡片 + `handoff` → 跳转 + InterviewView 预填（§7.3）

**验收**：剧本 A 跑通；**agent 无法绕过卡片造成面试会话**（测试：走完提案流程断言无 `iv_` thread 创建）；`edit` 后模型不反提旧值（生效 digest 与提案 digest 不同且 history 里可见回执）。

### P3 长期记忆（估 4-5 人日）
- `assistant.db` 四表 + `vector_index.py`（镜像 kb_parent 模式）
- `remember` / `recall_memory` / `forget_memory` + 写锁
- 三门槛写入、supersede、衰减打分、recall-loop 防护
- 记忆面板 UI（REST）

**验收**：剧本 D 跑通；构造冲突记忆断言只剩一条生效；注入内容不会被再次写成记忆；`importance<6` 的噪声被拒。

### P4 权限分级 + 预算 + 可观测（估 3-4 人日）
- 三闸门 `permission.py` + 指纹级批准缓存 + 拒绝回灌
- 设置三档自动接受（落 `assistant_settings`）
- `budget_guard` + 压缩四步 + rapid-refill 熔断
- token/延迟统计进 `turn_end`；`/healthz` `/readyz`

**验收**：默认档下写与执行必弹、只读不弹；连问 30 轮不炸上下文；同参数二次确认不再弹窗；readyz 在缺 key 时 503 带指引。

### P5 语音 + 评测 + 会话历史（估 5-6 人日）
- 抽屉接 `useVoiceInput` + `/api/asr`；TTS/麦克风互斥（§7.4）
- §5.12 会话历史/断线恢复/删除级联（含 `adelete_thread` 存在性核对）
- `assistant_cases.jsonl`（25–35 条）+ `assistant_eval.py` 跑分
- 错误分类落盘

**验收**：剧本 E 跑通；评测四指标达标（§9 表）；说"帮我准备面试"能整句进抽屉并起提案。

### P6 收尾（估 2-3 人日）
- README 架构图更新（两个图并列：面试图 + assistant 图）
- 前端构建集成（`npm run build` → `backend/static/`，补齐 OPTIMIZATION_PLAN 阶段 4 未竟项）
- 部署脚本 / `.env.example` 更新（`ASSISTANT_DB_PATH` 等）
- 全量回归 + 演示路径录制

**验收**：单服务可跑；换机按 README 从零起服务不超 30 分钟。

---

## 九、评测方案

**判据优先级不可跳层**（`eval-handbook:84-111,300-313`）：单元（prompt 格式/拒答/注入抵抗 + 工具单测）→ 轨迹 → 端到端。

样本 schema（`eval-handbook:300-313`）：

```json
{"id":"route-007","type":"routing","difficulty":"mid",
 "input":"根据我最近三次面试报告，说我该补什么",
 "context":{"reports":3,"memories":2},
 "criteria":{"type":"state_assert","assert":"tool_trace.read_report_radar.count==3"},
 "expected_tools":["list_reports","read_report_radar","read_report_weak_points"],
 "notes":"测多份聚合，不接受只读 1 份"}
```

四个指标与判据：

| 指标 | 判据 | 目标 |
|---|---|---|
| 意图路由准确率 | `criteria.type=state_assert`（落到哪个工具/分支） | ≥ 90% |
| 工具选择正确率 | `expected_tools` 对照 `tool_trace`，检幻觉工具/参数错/顺序错/冗余调用四类（`:509`） | ≥ 85% |
| 参数抽取完整率 | schema 校验必填齐不齐，缺失必须生成追问而非默认值兜底（`workflow-handbook:47,197`） | 100%（这条不该有例外） |
| 记忆写入信噪比 | 人工抽检：有效条 / 总写入条 | ≥ 0.7 |

外加：**一致性 pass^k，k=3**，三次全过才算过（`eval-handbook:513`）—— agent 的输出方差远大于普通接口，单次通过没意义。

**题目来源**必须是真实会话的四信号：空检索、低分、**用户换措辞重问同一件事**、点踩（`eval-handbook:271-274`）。**禁止用 LLM 凭空合成首批题**（`:281`）。失败归因用五分类标签：工具错 / 规划错 / 幻觉 / 环境错 / 判据错（`:585-591`）。评测集版本指纹要和 `agent_memory` 快照一起记（`context-handbook:287`），否则记忆一改分数就不可比。

---

## 十、风险与对策

| # | 风险 | 具体表现 | 对策 |
|---|---|---|---|
| 1 | **版本基准错** | 按 0.2 教程写 → `create_react_agent(prompt=...)` 静默不生效 | §2.1/2.2 已核实；P0 先改 `requirements.txt`；优先手写图 |
| 2 | **DeepSeek tool_calls 流式异常** | chunk 合并后 tool_calls 碎裂/丢失 | P0 探针先行（§2.4 唯一未核断言）；不通过则退 `llm.astream` 收 token、工具调用走整段 `ainvoke`（牺牲首字延迟保正确性） |
| 3 | **工具体内 interrupt 失效** | 脱离原 task context 时 KeyError，或审批被静默跳过 | 审批放独立 `wait_confirm` 节点，工具体不审批（§5.2/§2.3） |
| 4 | **两张图串时间线** | 复用 `iv_` thread → `get_state` 读到面试图状态 | `as_` 前缀强制；P0 测试断言两图 state 互不可见（§5.10） |
| 5 | **graph hang** | 连接不关 → 请求卡死 | `persistence.close_shared_saver()` + shutdown 钩子（§5.10） |
| 6 | **Command 工具悬空 tool_call** | 提案工具只返回 Command → 消息校验炸 | update 里自带 ToolMessage（§5.5，`tool_node.py:881-916` 已核）；配对不变量写进测试（§5.11） |
| 7 | **延迟叠加** | KB 问答本身含一次 LLM；agent 一轮可含 5 次调用 | 只读工具并行（ToolNode gather 白捡）；`kb_ask` 命中改 `kb_search` 自答；首字优先流式；预算硬顶 |
| 8 | **意图误判** | 把指令当答案、把答案当指令 | 边界靠**两条独立 WS + 相位守卫**天然消歧（`protocol.py:6` 不动）；agent 永不接触面试 resume；提案工具模型不可见 |
| 9 | **记忆污染** | 噪声记忆越攒越多、互相矛盾 | 三门槛 + supersede + 衰减 + recall-loop 防护 + 面板可删（§5.7） |
| 10 | **提示注入** | 笔记/报告文本里混进"忽略以上指令"，并被 `remember` 固化 | `origin=="untrusted"` 拒写；注入话术声明"当前请求优先"；工具返回内容不进 system prompt 通道 |
| 11 | **SQLite 并发写锁** | 同轮并行工具同时写 | 连接 `timeout=10`（knowledge.py 同款）+ WAL + memory 写工具全局锁（§5.4） |
| 12 | **删除不干净** | 删会话留 checkpointer 孤儿 thread | 删除级联三步走；`adelete_thread` 存在性先核对（§5.12） |
| 13 | **TTS 打架** | 面试念题与 agent 播报互相打断 | §7.4 互斥规则 |
| 14 | **单岗位空转** | 岗位路由只能路由到 `llm_app`，看着像 bug | 明确标注为现状约束（§1.2）；prompt 红线：不承诺多岗位 |

---

## 十一、借鉴映射表

### 11a `E:\hiagent\agent-study` → 本项目

| 借鉴点 | 出处 | 本项目落点 | 采纳 |
|---|---|---|---|
| tool_call 必有配对 result，异常不抛而合成 `{ok:false}` | `analysis_codex s03:31,47`；`analysis_zcode s03:30,46` | §5.11 | ✅ 核心 |
| 三闸门权限 + 无匹配默认 ask | `analysis_claude_code s03:24-33,43` | §5.6 | ✅ |
| 批准按 (tool, 参数指纹) 记忆 | `analysis_zcode s09:40` | §5.6 要点2 | ✅ |
| 拒绝理由回灌模型 | `analysis_opencode s04:62` | §5.5 | ✅ |
| 压缩四步按代价升序 + 指针落盘可回读 | `analysis_opencode s08:50-57,52` | §5.8 | ✅ |
| 末轮"预算已尽请给结论"而非硬闸 | `analysis_opencode s01:33,65` | §5.9 | ✅ |
| rapid-refill 熔断 | `analysis_zcode s05:29` | §5.8 | ✅ |
| 事件词汇表单一事实源 + 审批是反向 request | `deepseek-harness known-event-types.ts:22-79`；`analysis_codex common.rs:1752-1800` | §6 | ✅（枚举照建，RPC 层用 LangGraph interrupt 替代） |
| 背压满则显式拒绝不静默丢 | `analysis_opencode s09:36,55` | §6 | ✅ |
| 记忆三门槛 / 衰减公式 / supersede / recall-loop | `context-handbook:495-516,177,200` | §5.7 | ✅ |
| 分层记忆 + 检索超时不阻塞 + curation 移出热路径 | `analysis_openclaw s07:29-30,43,65` | §5.7 | ✅ |
| 八区块 prompt / 动态段放缓存前缀后 / 关键约束首尾各写 | `prompt-handbook:105-123`；`context-handbook:112` | §5.8 | ✅ |
| 工具 description 五要素（做什么/何时用/何时不用/参数/失败返回） | `mcp-handbook:385-393` | §5.3 | ✅ |
| annotations 标注但服务端不依赖 | `mcp-handbook:305,391` | §5.3 要点2 | ✅ |
| 能 workflow 就别 agent；supervisor 单 agent | `multiagent-handbook:59-88` | §1.2 / §5.2 | ✅ 定位依据 |
| 评测 schema + criteria 优先级 + pass^k + 四信号出题 | `eval-handbook:300-313,509-513,271-274` | §9 | ✅ |
| 失败归因五分类 | `eval-handbook:585-591` | §9 | ✅ |
| 推导视图：能算的不存第二份 | `interview-prep-app app.py:219-221` | 记忆只存事实，弱项画像实时推导 | ✅ |
| 原子写（lock + tmp + `os.replace`） | `app.py:81-91` | `assistant.db` 写入 | ✅ |
| liveness/readiness 分离、索引缺失报 503 | `app.py:107-132` | `/healthz` `/readyz`（§5.13） | ✅ P4 |
| 技能"只留目录、按需读全文"的渐进加载 | `analysis_claude_code s07:34-39` | 工具 >15 个时的裁剪手段 | 🔶 预留 |
| `HumanInTheLoopMiddleware` | `langchain/agents/middleware/human_in_the_loop.py` | decisions 条数契约脆弱 | ❌ 用独立 wait 节点替代 |
| CrewAI Crews/Flows、CAMEL Workforce | `crewai/README.md:169-181,388`；`camel/.../multiple_single_agents.py:66-107` | 与"UI 硬约束打断流程"对立 | ❌ 不引入 |
| interview-prep-app 的 agent 设计 | 核查结论：该项目**无 agent、无 LLM**（纯 CRUD 刷题站） | 仅工程细节可抄 | ❌ 形态无参考价值 |

### 11b 来自 offerpilot 的修正（`E:\hiagent\review\offerpilot`）

| 借鉴点 | 出处 | 本项目落点 | 采纳 |
|---|---|---|---|
| **写动作声明为"模型不可主动调用"**，意图走前端显式 `pilot_action` | `ai/deterministic_actions.py:64-91`；`specs/2026-08-12-...:82-87` | §5.5 第一条修正 | ✅ 推翻 v1 设计 |
| `PendingAction` 契约（human 摘要 / token / risk_hint / evidence） | `web/src/types/chat.ts:92-134` | §5.5 | ✅ 直接照抄 |
| **可编辑字段由工具自声明且带类型**，后端逐字段复验 + 重渲染摘要 | `ai/tool_specs/metadata.py:358-371`；`ai/confirmation.py:42-60,101-158` | §5.5 第二条修正 | ✅ |
| 三态 `ConfirmationRequired/ReadyToExecute/PreparedToolCall` + 陈旧提案抛错 | `contracts.py:654-661` | §5.5 | ✅ |
| 提案/生效/提交**三份 digest 独立**；编辑后确定性回执**终结模型自动续答** | `agent_contracts.py:161-184`；ADR `0006:16-27` | §5.5 | ✅ 治"模型反提旧值" |
| evidence catalog：字符串叶子编 Pointer，每条产出必须挂逐字引用 | `ai/mock_interview.py:240-279,309-321` | §5.5b + 简历计划 | ✅ 跨层复用 |
| 服务端逐字复验 `value in evidence in raw_text`；只补空白不覆盖 | `resume_structured_import.py:208-215,222-259` | 简历计划 | ✅ |
| **明确拒绝 ATS 总分与匹配百分比**，改确定性三态体检 | `specs/2026-08-06-resume-evidence-audit-design.md:17,39,65` | 简历计划；我们 `match_score` 应收敛成三态 | ✅ 反向修正 |
| 交接只预填草稿，显式确认前副作用计数为 0 | `specs/2026-09-02-...:21,31-32` | §5.5 | ✅ 印证 |
| 未确认的助手草稿不入库；记忆用版本化表 + request_id 幂等 | `knowledge-system.md:33,42,156`；ADR `0008:17-27,38-45` | §5.7 备选强化 | 🔶 二期 |
| readiness 前置清单四态（就绪/需补充/来源已变/暂不可用），满足才启用主按钮 | `specs/2026-08-14-immersive-interview-studio-design.md:51-93,378` | 提案卡片可加"就绪度"段 | 🔶 P2 视情 |
| 转写必须先确认（可编辑 TextArea + 授权按钮）；"停顿后自动提交"是已否决方案 | `VoiceAnswerComposer.tsx:1063-1080`；studio design `:42,468` | RESUME 计划 V2 | ✅ 印证 |
| Live2D 吉祥物皮与功能解耦，隐藏不影响 | `README.md:32` | 我们的 FAB 同理，别做成依赖 | ✅ 原则 |

### 11c 对用户那张 GitHub 参照表的核实修正

三条主张与实情不符，**照原表做会白做工**：

| 表里主张 | 核实结果 | 判定 |
|---|---|---|
| open-resume 有「**ATS 评分维度设计**」，可丰富 SummaryView | **不成立**。作者 `xitanggg/open-resume`，README 里的 "ATS friendly to Greenhouse/Lever" 指**模板可被 ATS 解析**，不是评分功能；页面无任何分数或维度输出。且该仓库**最后提交 2024-10-29**，近两年停滞 | ❌ 撤掉这条需求 |
| open-resume 的 pdfjs 版面坐标解析「准确率远高于纯文本」 | **部分成立但被高估**。机制是真的（带 x/y + bold + 换行标记的 text item，水平间距<平均字宽则拼 token，标题靠 bold+全大写，小节靠 1.4× 行高，字段用 feature scoring 逐行打分）；**但官方明确只支持英文、单栏，不还原分栏与表格**，"远高于"是作者自述无量化 | 🔶 只抄思路，且中文要自建词典；成本中 |
| JadeAI 是「逐条 JD 要求 vs 覆盖度的 **gap 表**」 | **形态不符**。实际 schema 是 `keywordMatches[] / missingKeywords[] / suggestions[{section,current,suggested}] / atsScore / overallScore`（`src/lib/ai/jd-analysis-schema.ts`）——**关键词级命中/缺失 + 按分区的"现状→改法"**；纯 LLM + schema 校验，**无 embedding 无规则引擎**。star 数未能核实 | ✅ 仍值得抄（成本低），但按它真实形态抄；逐条三态覆盖表去抄 offerpilot（§11b） |
| pipecat/livekit 的 barge-in 可以"只抄交互模式" | **成立，但难点归因要改**。需要播放游标的是**前端**（只有浏览器知道播到哪个字）而非服务端；真正的障碍是**回声**——念题时开麦，SenseVoice 会把面试官自己的声音转写成候选人答案。OP 干脆"TTS 期间不开麦"，只提供手动暂停/继续/跳过（`VoiceAnswerComposer.tsx:401`；`continuousVoiceSessionController.ts:176-180`）。**结论：先做 V7（本地 TTS）把音频所有权拿回来，barge-in 才干净** | 🔶 依赖 RESUME 计划 V7 |
| vad-web「免按键说话，说完自动转写发送」 | **机制成立，两处措辞要改**：① `positive suffix / speechTimeout` 在现版文档查不到，别按它设计；真实默认是 `redemptionMs 1400`（静音多久算说完）/ `minSpeechMs 400`（不足则 `onVADMisfire` 丢弃）/ `preSpeechPadMs 800`（回补段首）；② 它**自带采集**，喂不进现有 `ScriptProcessor` 帧，落地等于**替换采集层**（好消息：`processorType:"auto"` 自带 AudioWorklet）。`onSpeechEnd` 给 16000Hz 单声道 Float32Array，**与 SenseVoice 输入要求天然对齐** | ✅ 值得做，成本 低-中 |

一个附带的好证据：pipecat 的 faster-whisper 服务本身就是 `SegmentedSTTService`——**VAD 说完再整段送 ASR，非流式**。这说明我们"分段上传到 `/api/asr`"的形态成立，**不需要**为此引入 WebSocket 音频帧通道。

---

## 十二、还需要你拍板的事

**agent 层（本计划书）**

1. **`remember` 要不要默认免确认**。默认走"自动写入 + 面板可见可删"（体验顺、有风险感），备选"每条都要我点确认"（安全、啰嗦）。
2. **面试进行中 agent 能不能查题库**。已决定允许 `search_questions`，但工具输出严格限定为题面、分类、难度与 ID，不返回标准答案；安全评测继续人工检查最终回答是否泄题。
3. **交接后 agent 是否主动问"要不要把弱项记下来"**。

**跨层（见 `RESUME_UPGRADE_PLAN.md`）**

4. **简历落库已实施**。原文“解析结果完全不落库”为设计时旧状态；当前由 `backend/resume/store.py` 按用户保存原文、结构化字段、证据和审核状态，已接入投递档案及 JD 分析。简历多版本比较、同步和企业系统对接仍待完成。
5. **`score_roles` 那套命中打分是废弃还是改三态**。offerpilot 明确验证过总分是伪结论（§11b），我们要么改成 `met/unmet/unknown` 三态，要么把分数入口从主 UI 摘掉——继续留着"总分"就是留着已知会误导的东西。
6. **语音升级做到哪一档**：只加浏览器 VAD 自动断句（成本低），还是 V7 本地 TTS 之后连 barge-in 一起做（依赖音频所有权，成本中）。
