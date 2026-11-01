# AI 模拟面试官 · 项目全景理解文档

> 更新日期：2026-09-18（2026-09-19 增补第八章学习手册）｜ 结构：先总览 → 后端篇 → 前端篇 → 联调与闭环 → 测试与演进 → 学习手册
> 面向"从零了解本项目"的读者。建议按章节顺序读；每节独立成段，也可按需跳读。
> **想系统学代码的读者直接看第八章**：前置概念地图 → 五阶段学习路线 → 16 段精读清单 → 动手实验 → FAQ 预答。
>
> ⚠️ **2026-10-08 路径变更**：旧前端 `frontend/`（端口 3000）**已删除**，唯一前端是
> `frontend-v2/`（墨卷档案，端口 3001）。**本文中所有 `frontend/src/...` 路径请按
> `frontend-v2/src/...` 阅读**；端口 3000 一律改为 3001。前端组件结构（Vditor/KaTeX/
> cytoscape/useWebSocket/markdown 渲染等）在两棵树里同名对应，差异见 `AGENT_PLAN §7`。

---

## 〇、阅读路径

| 你是谁 | 建议路径 |
|---|---|
| 第一次接触本项目 | 一 → 二 → 三 → 四，顺序通读（约 30 分钟） |
| 想系统学习/吃透代码 | 一 → **八.1 概念地图** → 按八.2 阶段读代码（配合八.3 精读清单与八.4 实验） |
| 只改后端 | 一 → 二 → 四.1 |
| 只改前端 | 一 → 三 → 四 |
| 答辩/汇报准备 | 一 → 四 → 五 → 六 → 七 |
| 遇到具体疑问 | 先查八.5 FAQ 预答，再看八.6 调试手段 |

---

## 一、项目定位与技术栈

**一句话**：本地部署的 AI 模拟面试系统——上传简历或选岗 → LangGraph 驱动"出题/作答/评分/低分追问"多轮面试 → 生成四维评估报告 → 薄弱点一键沉淀进个人知识库（双链笔记 + RAG 问答 + 知识图谱），形成"面试 → 复盘 → 学习"闭环。当前专注「大模型应用开发工程师」单一岗位（基础题库 56 题，可 `python main.py variants` 生成防背题变体扩充）。

| 层 | 技术 | 说明 |
|---|---|---|
| 后端框架 | FastAPI + uvicorn | REST + WebSocket 双通道，[http://127.0.0.1:8000](http://127.0.0.1:8000)，`/docs` 可调试 |
| 流程编排 | LangGraph + `interrupt()` | 人在回路面试状态机，AsyncSqliteSaver 持久化（重启可续接） |
| LLM 编排 | LangChain LCEL | 9 条链；ChatOpenAI 兼容 DeepSeek；fast/strong 双模型分层 |
| 嵌入/检索 | BAAI/bge-base-zh-v1.5 + Chroma + BM25(jieba) | 题库走 RRF 混合检索；知识库走父文档检索（短文整篇 / 长文子块索引+父块返回） |
| 数据存储 | SQLite ×3 + Chroma ×2 + 文件 | users.db / knowledge.db / checkpoints.db；题库 chroma_db 与知识库 kb_parent_chroma 隔离 |
| 认证 | bcrypt + JWT(HS256) + 登出吊销 + 登录限流 | |
| 前端 | Vue 3 + Vite + Vue Router + Vditor + KaTeX + cytoscape(fcose) | [http://127.0.0.1:3001](http://127.0.0.1:3001)（frontend-v2），Vite 代理 `/api`、`/ws` |

**启动**（两个终端）：

```powershell
# 后端
cd E:\hiagent\DEMO3\TOtal\backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn server:app --host 127.0.0.1 --port 8000

# 前端
cd E:\hiagent\DEMO3\TOtal\frontend-v2
npm run dev -- --host 127.0.0.1
```

演示账号 `admin / 123123`。首次需要 `.env`（复制 `.env.example`，填 `LLM_API_KEY`）与 `python main.py build`（构建题库向量库）。

---

## 二、后端篇（Python / FastAPI）

### 2.1 目录结构与职责

```text
backend/
├── server.py          ★ 中枢：全部 REST 接口 + /ws/chat 驱动器（约1300行，建议先读接口清单再按需深入）
├── main.py           题库 CLI：build / rebuild / variants(防背题变体)
├── config.py         全局配置（路径/检索权重/模型分层/角色/人设/难度/阈值）
├── auth.py           注册登录、bcrypt、JWT、REST/WS 鉴权依赖、登出黑名单、登录限流
├── common.py         工具：岗位匹配、技能抽取、难度标签、JSON 提取
├── knowledge.py      知识库 SQLite：笔记 CRUD、双链解析、图谱构建、聊天会话
├── kb_parent.py      知识库父文档检索（短文整篇/长文父子两层）+ 语义边生成（阈值0.66 + kNN top3）
├── kb_llm.py         知识库 LLM：结构化入库、RAG 回答、AI 整理、自动分类
├── kb_extract.py     上传文件原文提取（PDF/MD）
├── agent/            ★ LangGraph 面试引擎（见 2.5）
├── retrieval/        题库混合检索（见 2.6）
├── resume/           简历解析：parser(规则) / llm_parser(LLM) / vision_parser(千问视觉兜底)
├── data/llm_app.md   当前唯一启用题库（8个历史岗位在 data_disabled/ 可恢复）
├── reports/          面试报告产物：*.md(全文) + *.json(雷达/元数据)
├── agent/interview_records_*.md  逐题面试记录（按用户隔离）
└── tests/            pytest 单测 + real_smoke*.py 真实 LLM 烟雾脚本
```

### 2.2 server.py：接口全景

REST（除 login/register 外全部 `Depends(get_current_user)`，数据按 username 隔离、越权 404）：

| 分组 | 接口 |
|---|---|
| 认证 | POST `/api/login`（限流：5次失败锁15分钟）、`/api/register`、`/api/logout`（token 入黑名单） |
| 面试配置 | POST `/api/config`、GET `/api/roles` |
| 简历 | POST `/api/resume/parse-text`、`/api/upload/resume`（PDF≤10MB） |
| 报告 | GET `/api/reports`、`/{id}`、`/{id}/radar`、`/{id}/weak-points` |
| 逐题记录 | GET/DELETE `/api/interview-records[/{filename}]`（文件名正则白名单） |
| 知识库笔记 | GET/POST/PUT/DELETE `/api/kb/notes*`、`/api/kb/categories`、`/api/kb/graph`、`/api/kb/search`、`/api/kb/qa` |
| 知识库工具 | POST `/api/kb/tidy`、`/auto-category`、`/rebuild`、**`/api/kb/notes/{id}/auto-link`（智能关联）**、`/api/kb/notes/from-report`（薄弱点一键入库+自动双链） |
| 文件 | POST `/api/kb/notes/upload`（≤10个、≤50MB、文件名净化）、GET `/api/kb/files/{filename}`（鉴权下载，替代公开静态挂载） |
| 实时对话 | **WebSocket `/ws/chat`**（握手需 `?token=<jwt>`） |

**WebSocket 协议**（前端发 → 后端推）：
- 前端发：`config` / `answer` / `end` / `report` / `hint`
- 后端推：`config_ok` / `stream_start` / `stream_chunk` / `stream_end`（打字机流）/ `decision` / `interview_ended` / `report_ready` / `hint` / `status` / `error`
- 阶段校验（[agent/protocol.py](file:///e:/hiagent/DEMO3/TOtal/backend/agent/protocol.py)）：`answer/hint/end` 只允许在 `await_answer/await_followup`；`report` 只允许在 `await_report`。服务端把消息转为 `Command(resume=...)` 喂给 LangGraph，图的 custom event 原样转发前端。
- 进程内全局：`_sessions`（会话登记）、`_hints`（每题提示计数）、`_graph`（懒加载编译后的图）。

### 2.3 认证体系（[auth.py](file:///e:/hiagent/DEMO3/TOtal/backend/auth.py)）

- 密码 bcrypt（限 72 字节防截断）；JWT HS256，密钥未配置时自动生成落盘 `.jwt_secret`，默认 24h 过期。
- 登出：token 摘要入 `revoked_tokens` 黑名单，鉴权时校验。
- 统一校验入口 `get_user_from_token(token)`：吊销名单 → JWT 有效性 → 用户仍存在，REST 与 WS 共用。
- 登录限流（进程内、按 IP+用户名）：`LOGIN_MAX_FAILURES=5` / 窗口 5 分钟 / 锁定 15 分钟，返回 429 + retry_after。

### 2.4 一次面试在后端发生了什么（LangGraph 引擎）

面试流程由 14 节点 StateGraph 驱动（[agent/graph.py](file:///e:/hiagent/DEMO3/TOtal/backend/agent/graph.py)）：

```text
START → configure → opening → prepare_question → emit_question → wait_answer①
  → score_initial → 初始分3~6? ─是→ prepare_followup → emit_followup → wait_followup②
  │                                              → score_combined（两段回答合并重评）
  └─否→ finalize_question → 题满/结束? ─否→ 回 prepare_question
                           └─是→ closing → wait_report③ → summary → END
```

- ①②③ 是三个 `interrupt()` 人在回路等待点。**关键约束：等待节点在 interrupt 前不能做任何随机选题/LLM 调用/写文件**——LangGraph resume 时会从节点开头重跑，否则恢复时会重复出题。这是全项目最重要的工程纪律。
- 共享状态 [InterviewState](file:///e:/hiagent/DEMO3/TOtal/backend/agent/state.py)（TypedDict）：配置、人设、进度（asked_ids/records）、当前轮（question/answer）、评分（initial/final_result）、自适应（streak/difficulty_changes）、phase 等。`InterviewMemory` 不可序列化，作为闭包字典 `_memories[thread_id]` 管理而非进 state。
- 已落地的业务规则（精华）：

| 规则 | 逻辑 |
|---|---|
| 追问分档 | 初始分 3~6 才追问；<3（不会/跑题）与 ≥7（已答好）直接下一题 |
| 评分自一致性 | 同一回答独立评分 `SCORING_SAMPLES=3` 次取中位数，得分点过半投票 |
| 提示封顶 | 用 1 次提示最高 8 分、2 次最高 6 分（四维按比例缩放） |
| 自适应难度 | 连续 2 次 ≥7 升一级；单次 <4 立即降级；锁定 1~3（报告记录变化轨迹） |
| 防幻觉契约 | 跨题出题只读候选人原文+档位（不读评分产出）；低分回答硬性禁止虚构"候选人说过" |
| 合并重评 | 只拼候选人两段回答，追问文本不混入，避免提示性内容被算给候选人 |
| 双模式 | standard=题库检索；project=按简历 LLM 生成深挖问题（失败回退题库） |
| 报告三级降级 | 强模型 → 快速模型重试 → 纯模板；`ai_summary_mode` 写入报告 JSON |
| 面试官人设 | strict_cto / warm_hr / deep_tech 随机注入全部 prompt |

- 产物：`reports/{report_id}.md`（全文）+ `.json`（雷达数据：四维均值/分类均值/逐题/难度轨迹/薄弱点/学习建议）；逐题记录写入 `agent/interview_records_*.md`（头部含"用户"字段做隔离）。

### 2.5 检索层（[retrieval/retriever.py](file:///e:/hiagent/DEMO3/TOtal/backend/retrieval/retriever.py)）

题库混合检索：BM25（jieba 分词，权重 0.4）+ 向量（BGE，权重 0.6）双路 → RRF 融合（K=60，TOP_K=5）。出题 `get_question()` 只取题面；评分 `get_answer()` 按题号精确取标准答案/得分点，两者分离。与知识库用**不同的 Chroma 目录/集合**（chroma_db/`interview_questions` vs kb_parent_chroma/`kb_parent_children`）物理隔离。

### 2.6 知识库（与题库完全隔离的个人学习库）

**数据模型**（[knowledge.py](file:///e:/hiagent/DEMO3/TOtal/backend/knowledge.py)）：
- SQLite `notes` 表：title/content/tags/category/note_type(note/file/url)/file_path/source…
- 双链：正文中 `[[标题]]` 由 `WIKI_LINK_RE` 解析 → 图谱实线边 + 反向链接（backlinks）
- `kb_chat_sessions/messages`：RAG 问答会话持久化
- 图谱 `build_graph()`：节点=笔记（含未创建的"虚节点"）；边=wiki 实线 + semantic 虚线（读 `sem_links` 表）

**检索模式：父文档检索（Parent Document Retrieval，[kb_parent.py](file:///e:/hiagent/DEMO3/TOtal/backend/kb_parent.py)）**——取代旧"整篇一条向量"，短文与长文走不同路径：
- **短文（≤1200字）**：整篇 = 1 父块 + 1 子块，子块嵌入文本为"标题+分类+正文"（与旧模式逐字对齐，行为零退化）；
- **长文（>1200字）**：按"行 → 标点句 → 字符硬切"层级切父块（~1200字，边界不切断句子），父块再切子块（~350字，70字重叠）；**只索引子块**，检索时子块命中 → 按"(笔记×父块)取最高分 → 笔记聚合"两层融合 → 返回命中父块（每笔记最多 4 个父块，控制上下文）——小块保证精准匹配，父块保证上下文完整；
- 存储：子块向量在 Chroma 集合 `kb_parent_children`（目录 kb_parent_chroma，可用环境变量 KB_PARENT_CHROMA_PATH 覆盖）；父块文本在 knowledge.db 的 `parent_blocks` 表；笔记增删改走增量同步（`sync_note`/`remove_note`，失败只告警不阻断）；
- 实测（admin 21 篇真实笔记、60 条探针）：短文 Hit@5 100%（MRR 95.3%），长文 Hit@5 97.7%（MRR 87.3%），探针句 100% 包含在返回父块中——全面优于旧模式（短文 94.7%、长文 90.9%）。

**语义边生成**（[kb_parent.py](file:///e:/hiagent/DEMO3/TOtal/backend/kb_parent.py) `rebuild()`）：笔记级嵌入两两余弦相似度，**阈值 0.66 + 每笔记只保留 top3 邻居（kNN 截断）**——防止同质语料把图谱连成全连接毛球。需在图谱页手动"重建索引"触发（同时重建父文档索引）。

**融入图谱的两条路（`[[ ]]` 双链是核心）**：
1. **入库自动关联**：报告薄弱点一键入库时（`POST /api/kb/notes/from-report`），每条新笔记用"标题+建议"检索已有库，相关度 ≥0.66 的 top3 自动追加 `## 相关笔记\n- [[xxx]]` 到正文——新笔记即时带实线边入图，无需重建索引。同名笔记跳过不覆盖（幂等）。
2. **智能关联**（`POST /api/kb/notes/{id}/auto-link`，笔记编辑页按钮）：为**已存在**的老笔记补全缺失双链，标准同上；已有链接不重复追加。

**RAG 问答**（`POST /api/kb/qa`）：检索 → [kb_llm.answer_from_knowledge](file:///e:/hiagent/DEMO3/TOtal/backend/kb_llm.py) 生成带来源的回答 → 自动持久化会话。top1 < 0.35 时标 `sparse` 提示导入资料。

### 2.7 配置速查（[config.py](file:///e:/hiagent/DEMO3/TOtal/backend/config.py)）

| 想改什么 | 位置 |
|---|---|
| 检索权重/数量 | TOP_K=5、BM25_WEIGHT=0.4、VECTOR_WEIGHT=0.6、RRF_K=60 |
| 评分采样次数 | SCORING_SAMPLES=3（.env 可覆盖） |
| 父文档切分/语义边 | kb_parent.py：LONG_DOC_THRESHOLD=1200、子块350+重叠70、SEM_LINK_THRESHOLD=0.66、SEM_LINK_TOP_K=3 |
| 模型分层 | .env：LLM_MODEL_FAST（出题评分，温度0.7）/ LLM_MODEL_STRONG（总结，温度0.3） |
| 追问分档/难度规则 | graph.py：initial_score_router、finalize_question_node |
| 提示封顶 | graph.py：_apply_hint_cap（8/6 两档） |
| 人设/难度标签 | INTERVIEWER_PERSONAS / DIFFICULTY_LABELS |
| 记忆窗口/压缩 | MEMORY_WINDOW_SIZE=10 / MEMORY_COMPRESS_THRESHOLD=6000 |
| 演示固定首题 | graph.py：DEMO_FIRST_QUESTION_ID（置空关闭） |
| 存储路径 | *_DB_PATH / REPORTS_DIR / CHROMA_DB_PATH / KB_PARENT_CHROMA_PATH |

---

## 三、前端篇（Vue 3 / Vite）

### 3.1 目录结构

```text
frontend/src/
├── main.js / App.vue
├── auth.js               localStorage 令牌 + JWT 本地过期检查
├── router/index.js       路由表 + 登录守卫
├── api/index.js          ★ 请求层：自动 Bearer、30s/90s 超时、401 跳登录、kbFileUrl(鉴权文件链接)
├── composables/
│   └── useWebSocket.js   ★ WS 连接、打字机缓冲(24ms)、TTS 朗读、消息协议解析
├── utils/
│   └── markdown.js       ★ 安全 Markdown 渲染 + KaTeX 数学公式（AI 对话用）
├── components/           AppLayout / TopNav / RadarChart / DSIcon
└── views/
    ├── LoginView.vue     登录/注册
    ├── HomeView.vue       首页（单岗位入口）
    ├── ResumeUploadView.vue   简历上传(PDF)或粘贴文本
    ├── JobMatchingView.vue    按简历技能匹配岗位
    ├── ChooseJobView.vue      自主选岗+题量（localStorage 记忆上次配置）
    ├── InterviewView.vue  ★ 面试对话页（WS + 打字机 + 语音输入 + 提示 + 历史记录抽屉）
    ├── SummaryView.vue    ★ 报告页（雷达图/逐题/好坏答案对比/薄弱点入库+覆盖检测）
    ├── InterviewRecordsView.vue  逐题记录回看（列表自动选中并加载内容）
    └── knowledge/
        ├── KnowledgeView.vue    笔记列表/搜索/上传/网址收藏
        ├── NoteEditorView.vue   ★ Vditor 编辑器：[[双链]]联想、AI 整理/分类、智能关联按钮
        ├── GraphView.vue        ★ 知识图谱（fcose 布局）
        └── KbChatView.vue       ★ RAG 对话（Markdown+公式渲染、来源卡片、稀疏提示）
```

### 3.2 路由与页面

`/login` → `/`(首页) → `/resume-upload | /choose-job | /job-matching` → `/interview` → `/summary/:reportId` → `/interview-records`；知识库：`/knowledge`(列表) → `/knowledge/note/:id | /new`(编辑) → `/knowledge/graph`(图谱) → `/knowledge/chat`(AI 对话)。路由守卫：未登录一律重定向 login。

### 3.3 请求层（[api/index.js](file:///e:/hiagent/DEMO3/TOtal/frontend/src/api/index.js)）

- `request()`：自动附 `Authorization: Bearer`；FormData 不设 Content-Type；AbortController 超时（默认 30s、上传 90s、KB LLM 操作 120~300s）；401 清登录态跳登录页。
- 面试配置传递：ChooseJob/JobMatching 把 `{key,title,questionCount,resumeContext,resumeSkills}` 写 sessionStorage（本次跳转）+ localStorage `interviewConfig`（刷新/重进免重选）。
- `kbFileUrl(path)`：笔记原文件下载走 `/api/kb/files/{name}?token=`（`<a>` 标签无法带请求头）。

### 3.4 WebSocket 组合式函数（[useWebSocket.js](file:///e:/hiagent/DEMO3/TOtal/frontend/src/composables/useWebSocket.js)）

- 握手 `?token=<jwt>`；10s 连接超时。
- **打字机**：chunk 先进 `pending` 缓冲，24ms 定时器按节奏搬到 `content`（积压越多每次吐越多）；报告流 `instant` 直通不走打字机。
- **TTS**：面试官发言（opening/question/followup/closing）吐完字后用浏览器 SpeechSynthesis 朗读，`ttsEnabled` 可关；STT 开始时自动停读防回声。
- InterviewView 的"思考中"逻辑：首字到达前只显示一条"AI 正在思考…"指示器（空的流式气泡不渲染，避免双气泡）；首字到达后让位给流式气泡。

### 3.5 Markdown 渲染器（[utils/markdown.js](file:///e:/hiagent/DEMO3/TOtal/frontend/src/utils/markdown.js)）

零框架依赖（仅 katex）的安全渲染：**先 HTML 转义再生成标签**，链接只允许 http(s)/相对路径（防 XSS）。支持：代码围栏、行内代码、**数学公式**（`$$块级$$` 居中 / `$行内$`，KaTeX 渲染、坏 LaTeX 降级为等宽文本不崩溃、内容含中文或空格的 `$` 不当公式防误伤）、标题、分割线、列表、引用、表格、加粗斜体。
内部用 `MDXV*` 前缀哨兵占位（源码可见，防不可见字符导致的死循环——曾因 NUL 哨兵写岔导致页面卡死，已加"循环强制前进"兜底）。KaTeX 样式由消费页面引入（KbChatView：`import 'katex/dist/katex.min.css'`）。

### 3.6 面试页关键交互（[InterviewView.vue](file:///e:/hiagent/DEMO3/TOtal/frontend/src/views/InterviewView.vue)）

- 输入框：自适应高度 `<textarea>`（1~120px），`spellcheck=false`，Enter 发送 / Shift+Enter 换行，`isComposing` 时不误发（中文输入法）。
- 提示按钮每题最多 2 次（后端同步封顶评分）；题目进度/计时/题号面板在右侧栏，还有历史记录抽屉。
- 报告生成后写 sessionStorage 并跳转 SummaryView。

### 3.7 知识图谱（[GraphView.vue](file:///e:/hiagent/DEMO3/TOtal/frontend/src/views/knowledge/GraphView.vue)）

- 布局 **fcose**（Cytoscape 官方推荐，`quality:"proof"` 去重叠 + 标签计入避让 + `packComponents` 分量打包 + 孤立节点 tiling 网格平铺），依赖 `cytoscape-fcose` + `cytoscape-layout-utilities`。
- 力导向参数：wiki 双链 45px 强弹簧（真实关系聚团）、语义边 100px 弱弹簧（弱桥接不拉散簇）、gravity 0.4。
- 视觉：节点 10~22px 小圆点、单行 9 字灰标签（全名 hover 看，`deg<2` 的叶子标签更淡）、边 1px 细淡。
- 开关（常驻工具行）：显示语义边（默认开，本库双链少）、**隐藏孤立节点**（本地即时过滤）、分类筛选。
- hover 聚焦：虚化无关节点、突出当前节点及邻域；点击节点跳笔记/创建虚节点笔记；"重建索引"重算向量+语义边。

### 3.8 报告页与薄弱点入库（[SummaryView.vue](file:///e:/hiagent/DEMO3/TOtal/frontend/src/views/SummaryView.vue)）

雷达图 + 逐题 + 好坏答案对比 + 学习建议。"存入知识库"按钮：调 from-report 接口 → **页面内绿色/红色提示条**反馈（非阻塞，替代原生 alert；错误态可"重试入库"）→ 下方展示"知识库覆盖情况"（每条薄弱点已有几条相关笔记可点击跳转，无相关则建议导入资料）。

---

## 四、前后端联调：端到端数据流

### 4.1 一次完整面试（九步）

1. 登录拿 JWT → 选岗/传简历 → 配置（题量/难度/简历上下文）写 storage。
2. InterviewView 建 WS（带 token）→ 发 `config`。
3. 后端登记 `_sessions[thread_id]`，构造 initial_state，`graph.astream()` 启动。
4. configure → opening → 出题流式 chunk → 前端打字机显示 + TTS 朗读 → 停在 wait_answer 的 interrupt。
5. 前端发 `answer` → 服务端校验 phase → 附 hint_count → `Command(resume=...)` 恢复。
6. score_initial（3 次评分→中位数→提示封顶）→ 3~6 分触发追问 → 合并重评 → 循环至题满。
7. closing 推 `interview_ended` → 前端发 `report` → summary 流式生成 → 落盘 md+json → 推 `report_ready`。
8. 前端跳 SummaryView，按 reportId 拉全文与雷达。
9. 点"存入知识库"→ 新笔记自动检索关联追加 `[[双链]]` → 图谱立即可见（无需重建）。

**排查口诀**：流程问题看 graph.py 的 phase；内容问题看 prompts.py+chains.py；鉴权 404 看 auth.py 与 username 比对；检索不准看 retriever/kb_parent；渲染问题看 markdown.js。

### 4.2 学习闭环

面试 → 报告（薄弱点+建议）→ 入库（自动双链连入图谱）→ 图谱可视化复盘 → RAG 对话深挖 → AI 整理笔记 → 再面试验证。孤立老笔记用编辑页"智能关联"补链。

---

## 五、测试与验证

```powershell
# 后端单测（75 项，覆盖 auth/graph/protocol/kb/数据完整性）
cd backend; .\.venv\Scripts\python.exe -m pytest -q

# 前端构建
cd frontend; npm run build

# 真实 LLM 烟雾（需后端在跑）
cd backend; .\.venv\Scripts\python.exe tests\real_smoke.py
```

端到端浏览器实测（2026-09-18）：登录→5题面试（含追问）→报告→入库（同名正确跳过+覆盖检测）→图谱（四团簇无叠字）→AI 对话（列表/表格/公式/来源正常）。发现问题均已修复，见下节。

---

## 六、近期改动记录（截至 2026-09-18）

**安全与正确性**
- 上传文件名净化 `_sanitize_upload_filename`（防路径穿越）；`/kb_files` 公开静态挂载 → `GET /api/kb/files/{name}` 鉴权下载（Bearer 或 ?token=，须归属当前用户笔记）。
- 登录限流（IP+用户名，5次/5分钟 → 锁15分钟，429+retry_after）。
- `/api/config` 非法岗位兜底 general_hr（已移除，必然 KeyError）→ llm_app。
- graph.py 删除被覆盖的重复 `score_candidate` 死代码。

**图谱优化**
- 语义边：阈值 0.55→0.66 + kNN top3 截断（rebuild 后 23→13 条）。
- 前端换 fcose 布局（proof 质量/标签避让/分量打包/孤立点平铺）；节点缩小+标签弱化+边变细；"显示语义边/隐藏孤立节点"开关。
- 薄弱点入库自动 `[[双链]]` + 编辑页"智能关联"按钮（老笔记补链）。

**AI 对话与渲染**
- 自研 markdown.js（替代简陋正则版）；修复 NUL 哨兵不一致导致的**渲染死循环卡死页面**；新增 KaTeX 数学公式（$$/$，防货币误伤）。
- SummaryView 入库反馈 alert → 页面内非阻塞提示条。

**面试体验**
- 开场双气泡修复（空流式帧不渲染，"思考中"首字后让位）。
- 回答输入框 input→textarea（自适应高度/无拼写红线/Shift+Enter 换行/中文输入法保护）。
- 面试配置 localStorage 持久化（刷新免重选）；面试记录页自动加载选中记录内容（原"加载失败"）。
- 知识图谱节点标签两行→单行+tooltip；首页移除"9 覆盖岗位"统计格。

---

## 七、已知边界与优化方向

**边界**
- 会话/记忆/提示计数在进程内（`_sessions/_hints/_memories`），后端重启后仅图状态（checkpoints.db）可续接，对话记忆丢失。
- 依赖未锁版本；运行产物（db/测试文件）曾入库（建议补 .gitignore）。
- `@app.on_event` 已弃用（应改 lifespan）；语义边限流等单进程实现。

**优化方向（按优先级）**
- P1：server.py 拆分 routers/；`_sessions/_hints/_memories` 迁 SQLite；评分 3 次采样改 `asyncio.gather` 并发。
- P2：评分置信度产品化（展示采样分布）；错题本间隔复习（SM-2）；黄金题集离线评测 LLM 评分 vs 人工分；LLM 调用结构化日志与 /admin/metrics；Docker 部署。

---

## 八、学习手册：从"能跑"到"吃透"（2026-09-19 增补）

> 本节回答"**怎么学**"：先用概念地图把抽象框架锚到具体代码，再按五阶段路线读，每阶段有通关检验；配 8 个可回滚的动手实验和 12 条 FAQ 预答。总预算 4~6 天。
> 学习原则：**先跑通、再主线、后支线；每阶段动手做一次实验，不做"只读不练"的学习。**

### 8.1 前置知识地图（概念 → 本项目落点）

不需要先系统学完框架，按"用到哪补哪"推进。每行给出概念的一句话解释 + 它在本项目的落点，抽象概念立刻有实物对应。

**后端**

| 概念 | 一句话解释 | 本项目落点 |
|---|---|---|
| FastAPI 依赖注入 `Depends` | 把鉴权等公共逻辑声明成函数参数，框架自动调用 | [auth.py](backend/auth.py) `get_current_user` → 所有接口的 `user: dict = Depends(...)` |
| Pydantic 模型 | 类字段声明请求/响应结构，自动校验+序列化 | server.py `InterviewConfig`；agent/models.py `ScoreResult`（评分输出 schema） |
| LangGraph StateGraph | 流程建模为"节点+条件边"的状态机，state 在节点间流转 | [graph.py](backend/agent/graph.py) `build_interview_graph`（14 节点） |
| `interrupt()` / `Command(resume=)` | 图执行到 interrupt 暂停等人输入；恢复时**从该节点开头重跑** | graph.py 三个 wait_* 节点；server.py WS 驱动器喂 resume |
| checkpointer / thread_id | 按 thread_id 把每步 state 落盘，重启可续接 | server.py `get_graph`（AsyncSqliteSaver → checkpoints.db） |
| `get_stream_writer()` custom event | 图内节点向外发自定义流式事件 | graph.py `_stream_chain` → server.py `run_graph_stream` 转发前端 |
| LCEL 管道 | `prompt \| llm \| parser` 声明式组合，天然支持 astream/异步 | [chains.py](backend/agent/chains.py) 全部 `build_*_chain` |
| 结构化输出 | 让 LLM 按固定 JSON schema 输出并强校验 | chains.py `get_format_instructions` + `RobustScoreParser` 容错 |
| ChatOpenAI 兼容接口 | DeepSeek/智谱等提供 OpenAI 格式 API，换 base_url 即接入 | [llm.py](backend/agent/llm.py) `get_llm`；fast/strong 双模型分层 |
| Embedding（BGE） | 文本→向量，语义近则距离近 | retrieval/embeddings.py（bge-base-zh-v1.5） |
| Chroma 向量库 | 向量存取 + metadata 过滤 | 题库 collection=`interview_questions`；知识库=`kb_notes`（物理隔离） |
| BM25 + jieba | 关键词打分检索，中文需先分词 | retriever.py `_jieba_tokenize`、`_get_bm25_retriever` |
| RRF 融合 | 双路结果按 `权重/(k+rank)` 求和，免调分归一 | retriever.py `_reciprocal_rank_fusion`（约 L167） |
| RAG | 先检索相关片段再让 LLM 带依据回答 | [kb_llm.py](backend/kb_llm.py) `answer_from_knowledge`（带来源标注） |
| bcrypt / JWT / 吊销 | 密码哈希、无状态令牌、登出黑名单 | auth.py `hash_password` / `create_access_token` / `revoke_token` |
| WebSocket 生命周期 | accept → 收发 JSON 帧 → 断开；握手可带 query 鉴权 | server.py `/ws/chat`；auth.py `ws_authenticate` |
| 对话记忆压缩 | 超阈值把旧消息 LLM 压成摘要 | [memory.py](backend/agent/memory.py) `maybe_compress`（SummaryBuffer 模式） |

**前端**

| 概念 | 一句话解释 | 本项目落点 |
|---|---|---|
| Vue3 组合式 API | `setup` + ref/computed 组织响应式逻辑 | 所有 views；重点 InterviewView.vue |
| 组合式函数 composable | 可复用的响应式逻辑单元 | [useWebSocket.js](frontend/src/composables/useWebSocket.js)（WS+打字机+TTS 全在这） |
| Vite 代理 | dev server 把 `/api`、`/ws` 转发到 8000，免 CORS | frontend/vite.config.js（另保留 `/kb_files` 旧代理） |
| 路由守卫 | 跳转前拦截未登录 | router/index.js |
| AbortController | fetch 可取消，超时即 abort | api/index.js `request()`（30s/90s/120~300s 分级） |
| 打字机缓冲 | chunk 先进 pending，定时器匀速吐字 | useWebSocket.js `REVEAL_INTERVAL_MS = 24` |
| 安全 Markdown + KaTeX | 先 HTML 转义再生成标签；`$$/$` 渲染公式 | [markdown.js](frontend/src/utils/markdown.js) |
| Vditor | 所见即所得 Markdown 编辑器 | NoteEditorView.vue（`[[双链]]`联想补全） |
| Cytoscape + fcose | 图可视化 + 力导向布局（去重叠/标签避让） | GraphView.vue |
| ECharts 雷达图 | 四维评分雷达 | RadarChart.vue（消费报告 radar JSON） |

### 8.2 五阶段学习路线（每阶段有"通关检验"）

**阶段 0｜跑起来并点通全流程（0.5 天）**
- 动作：按第一章启动 → admin/123123 登录 → 完整走一次 5 题面试（主动用 1 次提示、答一个 3~6 分水平的回答触发追问）→ 看报告雷达 → 薄弱点"存入知识库" → 图谱页"重建索引" → 知识库 AI 对话问刚入库的知识点。
- 同时：打开 `http://127.0.0.1:8000/docs` 扫一遍接口；浏览器 F12 → Network → WS 看面试消息帧（stream_chunk/decision 肉眼可见）。
- **通关检验**：不看文档能说出"从登录到知识库"经过哪些页面、调了哪些接口。

**阶段 1｜后端主线：一次回答的生命周期（1~2 天，最重要）**
- 主线问题："前端发一条 `answer` 之后发生了什么？"按 8.3 清单 ①→⑨ 顺序读：protocol.py（25 行）→ state.py（80 行）→ graph.py 的 wait_* 节点与三个 router → score_candidate/评分合并 → 追问分支 → finalize/自适应难度 → 记忆 → 报告降级。chains.py 与 prompts.py 对照着读（prompt 模板决定 LLM 行为，chain 决定解析方式）。
- **通关检验**（能答出即过关）：
  1. 为什么 wait_answer_node 的 `interrupt()` 之前不能调 LLM？（resume 从节点头重跑，否则重复出题）
  2. 追问为什么只对 3~6 分触发？<3 与 ≥7 的考量各是什么？
  3. 同一回答评分 3 次，总分与得分点分别怎么合并？
  4. 提示封顶 8/6 在哪一步生效，四维分怎么处理？

**阶段 2｜检索层（0.5~1 天）**
- 读 retriever.py 全文 + retrieval/kb_builder.py 的 `parse_questions_from_file`，打开 data/llm_app.md 对照题库 8 字段格式（注释元数据 + Q/SCENARIO/A/S/GOOD/BAD/FOLLOWUP）。
- **通关检验**：说清"出题用 get_question()、评分用 get_answer()，为什么必须分开"（出题只取题面防泄答案）；手算一遍 RRF（两路各取 top3 融合排序）。

**阶段 3｜知识库子系统（1 天）**
- 按 knowledge.py（表结构/`WIKI_LINK_RE` 双链解析/`build_graph`）→ kb_parent.py（父子两层索引/`search` 两层聚合/`rebuild` 语义边 kNN 截断）→ kb_llm.py（`answer_from_knowledge` RAG）顺序读。
- **通关检验**：画出"报告页点存入知识库"的完整数据流（from-report 接口 → 建笔记 → 自动检索追加 `[[双链]]` → upsert 向量 → 图谱立即出现实线边，无需重建索引）。

**阶段 4｜前端一条线（1 天）**
- 读 api/index.js → auth.js → router → useWebSocket.js 全文 → InterviewView.vue → markdown.js → GraphView.vue。
- **通关检验**：讲清打字机"24ms 定时 + 积压加速"（>80 字每次吐 6 字、>30 吐 3、否则 1）；讲清"空流式气泡不渲染、首字到达后让位"防双气泡；讲清 markdown.js 为什么先转义再生成标签（防 XSS）。

**阶段 5｜测试与工程视角（0.5 天）**
- 跑 `pytest -q`；精读 test_protocol.py（最小）、test_interview_graph.py（核心）、test_kb_v08.py 各 1~2 个用例；后端运行时跑一次 tests/real_smoke.py。
- **通关检验**：能为 protocol.py 新写一个 phase 组合的参数化用例。

### 8.3 精读代码清单（16 段，按学习优先级）

每段先自问"它在解决什么问题"，再读实现。行号以当前版本为准。

| # | 位置 | 学什么 / 为什么必读 |
|---|---|---|
| ① | [protocol.py](backend/agent/protocol.py) 全文（25 行） | 最小闭环：WS 命令 × graph phase 白名单校验；纯函数设计便于测试 |
| ② | [state.py](backend/agent/state.py) 全文 | 一次面试的全部共享数据一览；streak/难度语义都写在注释里 |
| ③ | graph.py:780 `wait_answer_node` | interrupt() 人在回路的标准范式；回答入记忆；force_end 传递 |
| ④ | graph.py:294 `_build_prev_context` | **全项目最精华的注释**：数据契约——跨题出题只读候选人原文+档位，不读评分产出（防幻觉根源） |
| ⑤ | graph.py:56 `_merge_score_samples` | 自一致性集成：总分/四维取中位数、得分点过半投票、同义归一 |
| ⑥ | chains.py:82 `RobustScoreParser._dict_to_result` | LLM 输出不可信的工程兜底：总分校准（偏差>2 或方向性矛盾 → 以四维均值为准） |
| ⑦ | graph.py:817 `initial_score_router` + graph.py:962~1010 自适应难度段 | 追问分档；streak 驱动升降级（连续 2 次 ≥7 升 / 单次 <4 立即降，锁定 1~3） |
| ⑧ | memory.py:88 `maybe_compress` | 超 6000 字把旧消息压成摘要；压缩失败降级为截断 |
| ⑨ | graph.py:1194~1228 `summary_node` 降级段 | 强模型 → 快速模型 → 纯模板三级降级；`ai_summary_mode` 落盘可观测 |
| ⑩ | server.py:146 `run_graph_stream` | `astream(stream_mode=["custom","values"])` 双通道转发；phase 同步 `_sessions`；decision 去重推送 |
| ⑪ | server.py:125 `get_graph` | AsyncSqliteSaver 懒加载；依赖缺失自动回退 MemorySaver |
| ⑫ | auth.py:268 `get_user_from_token` | REST/WS 共用鉴权链：吊销名单 → JWT 校验 → 用户存在性 |
| ⑬ | retriever.py:167 `_reciprocal_rank_fusion` | RRF 逐行实现；0.6/0.4 权重如何进入公式 |
| ⑭ | kb_parent.py `rebuild` | 父文档索引 + 语义边重建：kNN 截断防"全连接毛球"：阈值 0.66 + top3 + 双向并集 |
| ⑮ | useWebSocket.js 全文 | 前端流式消费的全部复杂度：握手/10s 超时/打字机/首字让位/TTS/报告直通 |
| ⑯ | markdown.js:11~18 与 :240 | `MDXV*` 哨兵占位体系；"未知行型强制前进"防渲染死循环兜底 |

（其余文件按 8.2 阶段路线顺带读，不必逐行。）

### 8.4 动手实验清单（8 个，全部可 `git checkout -- <file>` 回滚）

> 守则：实验只改工作区、不提交；每做完一个，回到 8.2 对应阶段解释"为什么出现这个现象"——解释不出来说明还没懂。

| 实验 | 改动 | 预期现象与理解点 |
|---|---|---|
| L1 关闭演示固定首题 | graph.py:53 `DEMO_FIRST_QUESTION_ID = ""` | 首题改回随机检索；理解演示钩子只作用于第一题 |
| L2 关闭评分自一致性 | backend/.env 加 `SCORING_SAMPLES=1` | 评分延迟降为约 1/3、分数波动变大；理解中位数机制的意义 |
| L3 收紧记忆窗口 | config.py:104 `MEMORY_WINDOW_SIZE = 2` | 几题之后出题"承上启下"明显退化；理解 history 的对话感来源 |
| L4 放宽语义边阈值 | kb_parent.py `SEM_LINK_THRESHOLD = 0.5` | 图谱页重建索引后边数暴增、聚成一团毛球；理解 top-k 截断必要性 |
| L5 打乱阶段约束 | protocol.py 把 answer 白名单里的 `await_followup` 删掉 | 追问阶段提交回答被拒（"当前阶段不能执行回答"）；理解 phase 状态机 |
| L6 打字机调速 | useWebSocket.js:56 `REVEAL_INTERVAL_MS` 24→2 / 24→200 | 2ms 接近直出、200ms 明显迟滞；理解匀速吐字与积压加速的取舍 |
| L7 公式渲染回归 | backend 下 `node _tmp_mathtest.mjs`（7 用例临时脚本） | 全 PASS；理解货币 `$` 防误伤、代码块内不当公式、坏 LaTeX 降级 |
| L8 测试红线 | auth.py `get_user_from_token` 里提前 `return None` | pytest 多用例变红；理解测试如何锁定鉴权契约；改完还原 |

### 8.5 常见疑问预答（FAQ）

**Q1：resume 之后，LangGraph 为什么会"从节点开头重跑"？**
interrupt() 语义是"该节点尚未提交"。恢复时框架重放整个节点直到再次到达 interrupt 取到 resume 值。所以等待节点必须"纯"——随机性/副作用（选题、LLM、写文件）全部前置到独立节点（prepare_question/emit_question）。这是全项目最重要的工程纪律（graph.py 文件头注释）。

**Q2：InterviewMemory 为什么不放进 InterviewState？**
state 会被 checkpointer 序列化落盘，而 InMemoryChatMessageHistory + LLM 实例不可序列化。所以用闭包字典 `_memories[thread_id]` 进程内管理（graph.py:402）。代价：后端重启后对话记忆丢失（第七章已知边界）。

**Q3：后端重启后，进行中的面试能续接吗？**
图状态能（checkpoints.db 按 thread_id 续接）；但 `_sessions/_hints/_memories` 是进程内的——phase 校验登记、提示计数、对话记忆会丢。实际表现："能继续答，但 AI 失忆、提示次数清零"。

**Q4：为什么评分 3 次取中位数，而不是 1 次？**
LLM 单次评分方差大（同一回答可能浮动 4~7 分）。3 次独立采样取中位数抑制单次抽风；得分点按"过半采样命中"投票，避免偶然提及算成得分。代价是评分耗时 ×3，故 P1 方向是 asyncio.gather 并发。

**Q5：追问为什么只挑 3~6 分触发？**
<3 是"不会/跑题"，追问没有信息增量；≥7 已答好，再追问显得刁难。3~6 = 部分正确，恰是深挖价值最大的区间。

**Q6：为什么 BM25 和向量检索都要？**
BM25 擅长关键词精确命中（"MCP"等术语字面匹配），向量擅长语义泛化（"上下文窗口"≈"context length"）。RRF 按排名而非分数融合，天然免疫两路分数量纲不一致。中文场景 BM25 必须先 jieba 分词。

**Q7：知识库和题库为什么要两套 Chroma 存储？**
物理隔离：题库（chroma_db/`interview_questions`）是全局共享只读语料，知识库（kb_parent_chroma/`kb_parent_children`）是按用户隔离的可写语料，metadata 结构也不同。混库会让权限过滤和重建索引互相纠缠。

**Q8：报告的雷达 JSON 是谁生成的？**
summary_node 落盘 md 全文的同时组装 radar dict（四维均值/分类均值/逐题/难度轨迹/薄弱点/学习建议）写成 .json（graph.py:1272 附近）。前端 `/api/reports/{id}/radar` 只是读文件；薄弱点入库接口读的也是它。

**Q9：知识库为什么改成父文档检索，而不是继续整篇一条向量？**
旧模式对长文有两个写死的缺陷：嵌入只取前 800 字（后段内容永远召不回）+ 多主题长文一条向量产生语义稀释（主题被平均、相似度差一口气）。父文档检索让长文"小块精准检索、父块完整返回"；但短文不切——实测短文整篇命中 100%，切了反而因缺背景降到 67%。所以方案是按长度分流：短文整篇、长文父子两层，而不是无脑切片。

**Q10：数据怎么按用户隔离？**
三条线：REST 靠 `Depends(get_current_user)` 拿 username 过滤查询（越权一律 404，不暴露资源存在性）；面试靠 WS config 时把 username 注入 initial_state → 报告 JSON 带 username；知识库笔记/会话表全部带 username 列。

**Q11：笔记附件下载为什么走 `?token=` 查询参数而不是请求头？**
下载用 `<a href>`/浏览器导航，带不了 Authorization 头。所以 `kbFileUrl()` 把 JWT 拼进 query；后端 `/api/kb/files/{name}` 两种方式都接受，且校验文件归属当前用户。

**Q12：出题链的"承上启下"为什么只给原文+档位，不给 hit/missed？**
评分产出是"对照标准答案的依据"。出题链若读到 missed_points，会倾向把它们复述成"候选人没提到 XXX"甚至虚构"候选人提到过"——对没说过的话这就是幻觉。graph.py:294 注释称之为数据契约。

**Q13：DEMO_FIRST_QUESTION_ID 会不会影响正常使用？**
只影响 llm_app 岗位第一题（保证演示可复现），之后恢复正常混合检索；置空即关闭（实验 L1）。

### 8.6 观测与调试手段速查

| 想看什么 | 手段 |
|---|---|
| 接口调试 | `http://127.0.0.1:8000/docs`（Swagger，先 login 拿 token，右上角 authorize） |
| 面试 WS 消息流 | 浏览器 F12 → Network → WS → Messages（stream_chunk/decision/interview_ended 一目了然） |
| 图状态落盘 | `backend/checkpoints.db`（sqlite 工具查看）；后端启动日志有 checkpointer 初始化行 |
| 评分链路 | 在 `_merge_score_samples` 里临时 `logging.info` 各采样分，对比中位数结果 |
| 检索质量 | Python REPL 里 `HybridRetriever().get_question(topic="RAG", role="llm_app")` 看 top5 |
| 后端单测 | `.\.venv\Scripts\python.exe -m pytest -q`（可 `-k protocol` 只跑一类） |
| 真实 LLM 冒烟 | 后端运行时跑 `tests\real_smoke*.py`（按场景分文件：auth/kb/antihall/history…） |
| 公式渲染回归 | backend 下 `node _tmp_mathtest.mjs` |
| 前端构建检查 | `npm run build` |

排查口诀补充（4.1 之外）：**面试卡住** → 先看 WS 帧有无 error，再查 checkpoints.db 该 thread 的 phase；**图谱异常**（聚团/过稀）→ 图谱页重建索引，核对 `SEM_LINK_THRESHOLD/SEM_LINK_TOP_K`；**报告没生成** → 看 reports/ 是否落盘 + JSON 里 `ai_summary_mode` 判断走了哪级降级。

### 8.7 根目录其他文档导读（别读错版本）

| 文档 | 定位 | 建议 |
|---|---|---|
| README.md | 门面简介 + 启动命令 | 可读，但结构树/题量数据过时（仍写 8 岗位/86 题），以本文档为准 |
| START_GUIDE.md | 启动手册（端口占用 WinError 10048 排查） | 启动命令有效；"返回 8 个岗位"检查项过时 |
| SmartSteer_Status.md | v0.1→v1.0 逐版本变更日志（最详尽） | 想知道"某设计是哪个版本、为什么加的"来查它；v1.0（§13）为 2026-09-19 父文档检索改造 |
| OPTIMIZATION_PLAN.md | LangGraph 迁移期五阶段规划 | 历史档案；答辩讲"架构演进"时有用 |
| PROJECT_EVALUATION_AND_OPTIMIZATION.md | 实施前基线评估（P0/P1 问题清单） | 历史档案；其中 P0（interrupt 恢复安全）已修复 |
| SmartSteer_Status-v-0.1-v-.md | v0.1 冻结副本 | 可忽略 |
| LLM大模型提示词工程最佳实践.md | 通用提示词学习笔记（CO-STAR 等） | 与本项目工程无关，作背景阅读 |

**当前唯一反映项目现状的就是本文档 + 代码本身**；其余文档都按上表定位使用，避免学到过时信息。
