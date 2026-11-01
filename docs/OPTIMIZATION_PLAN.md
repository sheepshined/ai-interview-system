# AI 模拟面试官系统 · 优化升级方案

> 目标：将遗留的 LangChain LCEL 多 Chain 架构，重构为 LangGraph 驱动的状态图编排，同时修复运行问题、增强功能、提升问答速度，最终形成可演示/答辩的完整系统。
> 原则：**先稳后重构、分阶段交付、每阶段可演示**。

---

## 一、现状与核心问题清单

### 1.1 项目结构
- 三个版本并存：`mock_interview_langchain`（子模块，纯后端原型）、`total DEMO`（早期快照）、`TOtal`（最完整主线）。
- 用户决策：**只保留 TOtal**，另两个归档/删除。
- 根目录散落 5 个答辩 HTML 快照 + `_files` 目录（浏览器"另存为"产物，非应用代码）。

### 1.2 架构痛点（用户最关注）
1. **7 个 LCEL Chain 碎片化**：question/scoring/followup/summary/reaction/opening/closing，其中 `reaction_chain` 是死代码（`generate_reaction_stream` 从未被调用，但每次 `__init__` 仍构建）。
2. **编排分散在三层**：`chains.py`（建链）→ `engine.py`（`Phase` 枚举 + 大量实例变量手动状态机）→ `server.py` 的 `ws_chat`（手动 if/elif 调用各 generate_*_stream）。状态流转逻辑散落，难讲清、难维护。
3. **状态全靠实例变量**：`asked_ids/records/current_question/followup_count/...` 散落在 `InterviewEngine`，无集中 State，断线即丢失。

### 1.3 运行/配置问题（影响"能否跑起来"）
| # | 问题 | 位置 |
|---|------|------|
| 1 | 默认模型名 `deepseek-v4-flash` 疑似无效（DeepSeek 实际为 `deepseek-chat`/`deepseek-reasoner`） | `config.py:43` |
| 2 | API Key 变量名不一致：读 `DEEPSEEK_API_KEY`，报错却写 `ZHIPUAI_API_KEY`，`.env.example` 还列了从不读取的 `ALIYUN_API_KEY` | `config.py:41` / `llm.py:36` |
| 3 | Embedding 路径硬编码 `D:/BGE_BASE_ZN_1.5/...`，换机即失效 | `config.py:34-38` |
| 4 | CORS `allow_origins=["*"]` + `allow_credentials=True`（浏览器禁止组合） | `server.py:51-57` |
| 5 | 报告写死 `reports/interview_report.md`，并发覆盖（记录文件已用时间戳，不一致） | `engine.py:887` |
| 6 | 登录硬编码 `admin/123123` + MD5 token 且后续接口不校验（演示场景可暂留，但需注明） | `server.py:158` |

### 1.4 代码质量问题
- **静默吞异常**：`engine.py:622/889`、`memory.py:127`、`kb_builder.py:131` 多处 `except: pass`。
- **循环依赖**：`retrieval` ↔ `agent` 互相 import（`get_embeddings` 应下沉）。
- **Chroma 私有 API**：`retriever.py` 大量用 `vectorstore._collection.*`。
- **async/sync 混用**：`/api/config`、`/api/roles`、`/api/resume/parse-text` 是 `async def` 却跑同步阻塞逻辑。
- **重复代码**：岗位匹配逻辑 3 处、难度映射 3 处、技能关键词表 2 套、JSON 容错解析 2 套。
- **死代码**：`build_scoring_chain` 内未用的 `pydantic_parser`、`import shutil`、`models.py` 末尾注释类。
- **小错**：`parser.py:20` docstring 多空格、`InterviewConfig` 用 `[]` 可变默认值。

### 1.5 工程化缺失
无测试、无 Docker、无 CI/CD、无部署脚本、无根 README；前端未构建进 `backend/static/`（生产态无法单服务运行）。

---

## 二、架构决策（针对开放问题）

### 2.1 是否全面换 ReAct / Plan-and-Execute？
**建议：不全面换，采用"确定性 StateGraph 骨架 + 关键节点 agent 能力"的混合架构。** 理由：
- 面试流程有明确阶段和约束（开场→出题→评分→决策→结束→报告），完全 ReAct 会让流程不可预测——答辩演示时无法保证稳定走完。
- 但纯规则决策（当前 `decide()`）较死板。改进：**`decide` 节点保留确定性兜底规则，可选叠加 LLM 智能决策**（如根据回答质量动态决定追问深度/是否换方向），让面试更自然但仍可控。
- `ask` 节点可**选**用 ReAct（LLM 自主调用检索工具组织题目），作为"增强模式"开关，默认走确定性检索+生成（更快更稳）。

> 结论：LangGraph 同时支持确定性边和 LLM 决策边，混合架构最契合"答辩要稳、又要体现 agent 能力"的诉求。

### 2.2 提示词是否要改？
**需要改，但以适配和精简为主，不推翻重写。** 现有 8 套提示词写得较细，迁移时：
- 删除 `reaction_prompt`（死代码）。
- 适配 LangGraph 节点输入（从 `State` 字段取值，而非旧的 chain input_dict）。
- 优化 `question/scorer/followup` 提示词以提速（更短、更聚焦、明确要求不啰嗦）。
- 评分提示词强化"只输出 JSON、不要解释"，减少 `RobustScoreParser` 兜底命中率。

### 2.3 问答速度怎么提起来？
**多管齐下（详见阶段三）：**
1. **模型分层选型**：出题/评分/追问/开场/收尾用快速模型（`deepseek-chat`，非 `reasoner`）；仅总结报告用更强模型（可控）。
2. **流式首字优先**：保留 `astream`，确保用户秒级看到首字。
3. **检索并行化**：出题时 BM25+向量本就并行；评分时"检索标准答案"与"评分"可拆分，答案已在 `receive_answer` 预取，避免串行。
4. **Embedding 加速**：本地 BGE 懒加载 + 启动预热；或提供在线 Embedding（智谱 embedding-2）作为可切换项，降低首启成本。
5. **减少不必要的 LLM 调用**：删 `reaction`；决策用规则（不调 LLM）；开场/收尾/追问文本量可控。
6. **结果缓存**：`RobustScoreParser`、BM25 按 role 已缓存，保持并扩展标准答案缓存。

---

## 三、方案总览（分五阶段，每阶段可演示）

```
阶段0 基线清理与修复      ── 让现有系统稳定可跑（不改架构）
   ↓
阶段1 LangGraph 核心迁移   ── 架构重构（激进式 StateGraph + interrupt + checkpointer）
   ↓
阶段2 功能增强            ── 报告管理/维度/断线续接/新题库/前端丰富
   ↓
阶段3 性能与提示词优化     ── 速度/模型分层/提示词精简
   ↓
阶段4 工程化与文档        ── README/Docker/前端集成/答辩验证
```

---

## 四、阶段0 · 基线清理与修复（不改架构，先稳住）

### 4.1 项目瘦身
- 将 `mock_interview_langchain`、`total DEMO` 移出主工作区（归档到 `_archive/`，确认无引用后再清理）。
- 清理根目录散落的答辩 HTML 快照（`AI 模拟面试*.html` + `*_files/` + `AI-fixed-v2.html`），它们是浏览器另存产物，源头在 `TOtal/defense-ppt/`。
- 保留 `TOtal/defense-ppt/`（答辩演示源）和 `cleanup_html.py`/`fix_encoding.py`（辅助脚本，可选保留）。

### 4.2 配置与运行修复
- `config.py`：默认模型 `deepseek-v4-flash` → `deepseek-chat`；统一 API Key 变量名为 `LLM_API_KEY`（同时兼容读 `DEEPSEEK_API_KEY` 做向后兼容）；移除从不读取的 `ALIYUN_API_KEY` 配置项。
- `llm.py`：修正报错信息中的变量名为 `LLM_API_KEY`。
- `config.py`：`EMBEDDING_MODEL_PATH` 默认值改为相对/可移植路径 + 启动时缺失友好报错（提供在线 Embedding 回退开关）。
- `server.py`：CORS 改为 `allow_origins` 读配置（开发态 `["http://localhost:5173","http://localhost:3000"]`），`allow_credentials=True`。
- `engine.py`：报告写入改为时间戳命名 `reports/interview_report_{ts}.md`，与记录文件一致。
- 静默异常改 `except Exception as e: logger.warning(...)`（新增轻量 logging 配置）。

### 4.3 死代码与重复清理
- 删除 `reaction_chain` 全套：`build_reaction_chain`、`_reaction_chain`、`generate_reaction_stream`、`reaction_prompt`（引用处同步清理）。
- `chains.py:build_scoring_chain`：删未用的 `pydantic_parser` 局部变量。
- 删 `server.py` 的 `import shutil`、`models.py` 末尾注释类。
- 抽公共函数：`match_role(skills)`（消除 3 处重复）、`DIFFICULTY_LABELS` 常量（消除 3 处）、`parse_json_robust(text)`（消除 2 套解析）、统一技能关键词表。
- 修复 `parser.py` docstring、`InterviewConfig` 用 `Field(default_factory=list)`。

### 4.4 循环依赖与架构小修
- 新建 `agent/embeddings.py`（或 `retrieval/embeddings.py`）持有 `get_embeddings`，`retrieval` 不再 `from agent.llm import`，打破循环。
- `retriever.py`：尽量用 LangChain-Chroma 公开 API，私有 `_collection.*` 调用加注释/封装，降低升级风险。
- `server.py`：`/api/roles`、`/api/parse-text` 内纯 CPU 逻辑用 `def`（FastAPI 线程池）而非 `async def`，避免阻塞事件循环。

> **阶段0 验收**：系统能稳定跑通一场完整面试（开场→问答→评分→追问→报告），无静默报错。

---

## 五、阶段1 · LangGraph 核心迁移（架构重构核心）

### 5.1 依赖与目录
- `requirements.txt` 新增 `langgraph`、`langgraph-checkpoint-sqlite`（SQLite 持久化 checkpointer）。
- 新增 `agent/graph.py`（图定义）、`agent/state.py`（State 定义）；保留 `prompts.py`、`models.py`；`chains.py` 降级为"节点内的 LLM 调用工具函数"或合并进 `graph.py`。

### 5.2 面试状态定义 `agent/state.py`
集中所有状态（替代散落的实例变量）：
```python
class InterviewState(TypedDict):
    thread_id: str                  # 一场面试的唯一 id（= WS 会话）
    role_key: str; role_info: dict; difficulty: int; difficulty_label: str
    total_count: int; resume_context: str; resume_skills: list; candidate_name: str
    asked_ids: list; asked_categories: list; main_question_count: int; followup_count: int
    current_question: dict; current_answer_data: dict
    last_user_answer: str
    records: list[dict]             # 每轮评分记录
    messages: list                  # 对话历史（LangGraph 内置消息状态）
    md_path: str
    phase: str                      # 调试/日志用
    human_answer: str | None        # 人类输入恢复通道
```

### 5.3 图结构 `agent/graph.py`
```
   configure ──▶ opening ──▶ ask ──▪ interrupt(等回答) ──▶ receive_answer ──▶ score ──▶ decide
                                                                                       │
                          ┌─────────────────────────────────────────────────────────────┤
                          ▼                ▼ next                                       ▼ end
                       followup           ask(interrupt)                            closing ──▶ summary
                          │
                          ▼ interrupt(等回答) ──▶ receive_answer ──▶ score ──▶ decide ...
```
- **节点**：`configure / opening / ask / receive_answer / score / decide / followup / closing / summary`。
- **interrupt 点**：`ask` 末尾、`followup` 末尾各 `interrupt()`，暂停等用户回答。
- **条件边**：`decide` 输出 `followup|next|end`（确定性规则 + 可选 LLM 增强）。
- **checkpointer**：`SqliteSaver` 按 `thread_id` 持久化暂停点（断线续接的基础）。

### 5.4 流式输出落地（关键技术点）
- 节点内用 `llm.astream()` 生成文本，通过 **`get_stream_writer()` custom event** 推送 chunk。
- `server.py` 的 `ws_chat` 用 `async for ev in graph.astream(input, config, stream_mode="custom")` 接收 chunk → 转发 WebSocket（`stream_chunk` 消息）。
- 节点 `interrupt()` 后，`astream` 自然结束该轮；WebSocket 把已推内容呈现给前端，等待用户 `answer`。
- 用户回答到达 → `graph.astream(Command(resume=answer), config, stream_mode="custom")` 恢复进入 `receive_answer`。

### 5.5 Memory 重构
- LangGraph 内置 `messages` 通道 + checkpointer 可替代手动 `InterviewMemory`。
- 摘要压缩：保留为图的一个"压缩节点"或在 `receive_answer` 内按阈值触发（逻辑复用 `compress_prompt`），不再手搓 `InMemoryChatMessageHistory` 重建。

### 5.6 WebSocket 重构 `server.py`
- `ws_chat` 从"手动 if/elif 编排"变为"graph 驱动器"：接收 `config/answer/report` → 转为图的 `invoke/astream(Command(resume=...))`，不再手动调用 `generate_*_stream`。
- `config` → 新建 thread，`graph.astream(config_input)` 跑到首个 interrupt（ask 前），推送 opening+第一题。
- `answer` → `graph.astream(Command(resume=answer))`，跑到下一 interrupt 或结束，推送评分/决策/追问/下一题/收尾。
- `report` → `graph.astream(Command(resume="report"))` 触发 summary 节点（或单独 invoke summary 子图）。

> **阶段1 验收**：一场面试全流程由 LangGraph 驱动跑通，流式正常，状态可从 checkpointer 恢复。可向评委讲清"状态机、人在回路、持久化"三层技术点。

---

## 六、阶段2 · 功能增强

### 6.1 报告管理
- 报告时间戳命名 `reports/interview_report_{ts}_{role}.md`。
- 新增 `GET /api/reports`（列表：时间/岗位/平均分）、`GET /api/reports/{id}`（详情）。
- 前端 `/summary` 页增加"历史报告"入口与列表。

### 6.2 报告维度增强
- `summary` 节点/`_prepare_summary` 扩展统计：**按分类平均分、四维雷达数据、强弱项、改进建议**。
- 新增 `GET /api/reports/{id}/radar` 返回雷达图 JSON。
- 前端报告页用 **ECharts** 渲染雷达图、分类柱状图、得分趋势。

### 6.3 断线续接与回放
- 基于 `SqliteSaver` + `thread_id`：断线重连时前端带 `thread_id`，后端 `graph.aget_state(config)` 恢复到中断点继续。
- 新增 `GET /api/interviews`（进行中的面试会话列表）、`GET /api/interviews/{thread_id}/replay`（按 records 回放）。
- 前端重连提示 + 回放视图（按轮次展示问答/评分）。

### 6.4 新岗位题库
- `data/` 新增 `algorithm.md`（算法）、`devops.md`（运维）、`data_analyst.md`（数据分析），沿用现有格式。
- `config.ROLES` 增加对应岗位与 tags；`main.py build` 一键重建知识库。
- 前端选岗位页同步展示新岗位。

### 6.5 前端丰富
- 面试页：打字机流式效果、评分反馈即时气泡、追问高亮、进度条（第 X/N 题）。
- 报告页：ECharts 雷达图 + 分类统计 + 改进建议卡 + 导出 Markdown/PDF 按钮。
- 全局：加载态、错误提示、断线重连提示。

---

## 七、阶段3 · 性能与提示词优化

- **模型分层**：`config` 增 `LLM_MODEL_FAST`（出题/评分/追问/开场/收尾，默认 `deepseek-chat`）与 `LLM_MODEL_STRONG`（总结，可配更强）。`llm.py` 暴露 `get_fast_llm()/get_strong_llm()`。
- **提示词精简**：删 `reaction_prompt`；`scorer_prompt` 强约束纯 JSON；`question/followup` 缩短、要求不啰嗦以降延迟。
- **检索提速**：标准答案按题 id 加 LRU 缓存；BM25 按 role 已缓存保持；向量检索保持本地 BGE（启动预热）+ 在线 Embedding 可选回退。
- **并发**：`receive_answer` 内取答案与（后续）评分解耦；`_prepare_followup` 的多次 `get_answer` 用 `asyncio.gather`/线程并行。
- **首字延迟**：确保 `astream` 立即 yield 首 chunk；避免节点内同步 `invoke` 攒全文。

---

## 八、阶段4 · 工程化与文档

- 根 `README.md`：项目介绍、架构图（LangGraph 状态图）、启动步骤、答辩要点。
- `TOtal/backend/`：新增 `logging.conf`/统一日志；`.env.example` 更新为正确变量名。
- 前端构建集成：`npm run build` 产物拷入 `backend/static/`，`server.py` 单服务可跑（生产态）。
- Docker（可选）：后端 `Dockerfile` + `docker-compose`（含 chroma_db 卷）。
- 答辩演示验证：跑通端到端、录制演示路径、更新 `defense-ppt` 中架构图（体现 LangGraph 重构）。

---

## 九、实施顺序与里程碑

| 里程碑 | 阶段 | 产出 | 可演示性 |
|--------|------|------|----------|
| M1 | 阶段0 | 清理+修复后的稳定系统 | 能跑通完整面试 |
| M2 | 阶段1 | LangGraph 驱动的面试流程 | 状态图可讲、断线可续 |
| M3 | 阶段2 | 报告管理/维度/新题库/前端丰富 | 报告有图、多岗位可选 |
| M4 | 阶段3 | 性能优化、提示词精简 | 问答明显提速 |
| M5 | 阶段4 | 文档/Docker/答辩材料 | 一键启动、可答辩 |

---

## 十、风险与对策
- **风险1：interrupt + 流式 + WebSocket 三者结合复杂度**。对策：先在最小子图（ask→interrupt→receive_answer）跑通流式，再扩展全流程；保留旧 `InterviewEngine` 作回退直到 M2 验证通过。
- **风险2：LangGraph API 版本变动**。对策：锁定 `langgraph` 版本，关键调用加封装层。
- **风险3：本地 BGE 路径/加载问题**。对策：阶段0 即提供在线 Embedding 回退开关。
- **风险4：删除旧子项目后丢失参考**。对策：先归档到 `_archive/` 而非直接删，确认无引用后再清理。
