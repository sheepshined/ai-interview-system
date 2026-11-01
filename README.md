# AI 模拟面试官

基于 FastAPI、LangGraph 和 Vue 3 的本机模拟面试系统。答辩演示采用两个本地服务：

- FastAPI 后端：`http://127.0.0.1:8000`
- Vite 前端（墨卷档案 frontend-v2）：`http://127.0.0.1:3001`

## 核心流程

一条完整闭环：**简历/JD 分析 → LangGraph 模拟面试 → 四维评分与报告 → 成长档案与复习**。
统筹助手通过可确认的工具调用串联报告、题库、知识库和投递档案；语音转写、本地数据库与向量检索均可在本机运行。

## 主要功能

- 用户体系：JWT 登录 + 在线注册（预置演示账号 `admin / 123123`），报告与会话按用户隔离
- PDF 简历解析或粘贴文本简历
- 简历原文与结构化字段按用户落库，支持编辑、证据核验与确认后复用
- JD 结构化分析与简历匹配建议，不输出录用结论、概率或虚构评分
- 投递档案：阶段跟踪、时间线备注、审核简历关联、模拟面试报告和结果复盘，按登录用户隔离
- JD 来源与不可变版本历史：保存正文及来源、查看历史、恢复为新版本；并发更新时保留草稿并拒绝覆盖
- 大模型应用开发工程师专场、混合检索题库
- 个人知识库：双链笔记 + 父文档检索（短文整篇/长文子块索引+父块返回）+ RAG 问答与知识图谱
- 笔记预览内打开关联笔记、原信息/AI 解读/插入笔记切换、全屏阅读与可收起侧栏
- LangGraph 人在回路面试、低分追问和合并重评
- 本地 SenseVoice + Silero VAD 语音输入，以及浏览器原生 TTS 暂停、继续和跳过
- Markdown 报告、雷达数据和本场报告精确跳转
- 全局统筹助手：报告/题库/知识库工具调用、长期记忆、上下文摘要压缩、持久会话、确认提案与页面交接
- 技能运行时：`SKILL.md` 目录即技能，三级渐进披露、`allowed-tools` 预授权与误触发率指标
- 能力成长档案：跨报告确定性聚合——场均分走势、四维雷达叠加、分类掌握度与难度分布（零 LLM，数字可复核）
- 角色分级与设置中心：JWT 内建 admin/user 角色，自助改密码；管理员可管理用户（重置密码/启停/角色）与题库（JSON 导入校验、删除、运行时重建向量索引）
- 首页题量等数字全部来自真实接口，不再硬编码

## 核心流程

```text
登录 → 选择简历匹配或自主选岗 → 配置题量 → 开始面试
  → 出题 → 等待回答 → 评分 → 可选追问 → 下一题
  → 收尾 → 点击生成报告 → 本场总结页
```

LangGraph 将选题、流式输出和 `interrupt()` 等待拆成独立节点，恢复回答时不会重复选择或重复输出同一道题。

统筹助手走独立闭环：

```text
登录 → 打开统筹助手 → 连续对话或调用只读工具
  → 生成面试/知识库提案，或投递档案/JD 写入确认卡
  → 用户批准、修改或拒绝 → 执行批准的操作或交接页面
```

助手会话、消息和长期记忆保存在 `assistant.db`，图状态保存在 SQLite
checkpointer；刷新或后端重启后可恢复待确认提案。单后端进程内对同一用户会话做互斥保护。
投递档案和 JD 写工具每次都需要独立确认；JD 更新、恢复携带当前版本号，
确认期间发生外部更新时不会覆盖新内容，也不会自动重试写入。不自动向雇主投递或联系招聘方。

## 项目结构

```text
TOtal/
├── backend/
│   ├── server.py          FastAPI、REST、WebSocket
│   ├── main.py            题库 build/rebuild
│   ├── agent/             LangGraph、状态、提示词、评分
│   ├── assistant/         统筹助手图、工具、权限、会话与记忆
│   ├── skills/            技能运行时与内置技能（SKILL.md 目录即技能）
│   ├── growth.py          能力成长档案：跨报告确定性聚合
│   ├── retrieval/         BGE、BM25、Chroma、RRF
│   ├── resume/            PDF 与文本简历解析
│   ├── application_store.py 投递档案、复盘、报告关联与 JD 版本存储
│   ├── application_models.py 档案与 JD 参数校验
│   ├── jd_analysis.py     已审核简历的证据化 JD 分析
│   ├── data/              当前专场题库
│   ├── kb_parent.py       知识库父文档检索（子块索引/父块返回）
│   └── tests/             自动化测试和真实烟雾脚本
├── frontend-v2/            Vue 3 SPA（墨卷档案，唯一前端）
├── docs/                   项目文档与历史方案
├── start-demo.ps1          一键演示启动（后端+前端+健康检查+开浏览器）
├── AGENT.md                AI 编码智能体开发指南
└── README.md               项目入口与使用说明
```

## 文档导航

- [本机启动手册](docs/START_GUIDE.md)
- [AI 编码智能体开发指南](AGENT.md)
- [作品说明书](docs/作品说明书.md)
- [当前进度与验证记录](docs/PROGRESS_HANDOVER.md)
- 设计与历史方案：[统筹助手](docs/AGENT_PLAN.md) · [技能运行时](docs/SKILL_RUNTIME_PLAN.md) · [简历升级](docs/RESUME_UPGRADE_PLAN.md) · [历史优化](docs/OPTIMIZATION_PLAN.md)
- [项目导读与评审](docs/PROJECT_GUIDE_AND_REVIEW.md)

## 首次准备

后端：

```powershell
cd E:\hiagent\DEMO3\TOtal\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

编辑 `.env` 并填写 `LLM_API_KEY`。首次运行或题库变更后构建向量库：

```powershell
python main.py build
python main.py fetch-models
```

`fetch-models` 按固定清单下载 SenseVoice 与 Silero VAD，逐个校验文件大小和
SHA-256，并支持断点续传。BGE 嵌入模型仍由 Hugging Face 加载器或
`LOCAL_BGE_MODEL_PATH` 管理；浏览器 TTS 使用系统 `SpeechSynthesis`，不下载本地语音合成模型。

前端：

```powershell
cd E:\hiagent\DEMO3\TOtal\frontend-v2
npm install
```

## 日常启动

一键启动（推荐，自动健康检查并打开浏览器）：

```powershell
cd E:\hiagent\DEMO3\TOtal
.\start-demo.ps1
```

或手动分两个 PowerShell 窗口：

窗口 1：

```powershell
cd E:\hiagent\DEMO3\TOtal\backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

窗口 2：

```powershell
cd E:\hiagent\DEMO3\TOtal\frontend-v2
npm run dev -- --host 127.0.0.1
```

浏览器打开 `http://127.0.0.1:3001`。详细步骤见 [START_GUIDE.md](docs/START_GUIDE.md)。

## 测试

```powershell
cd E:\hiagent\DEMO3\TOtal\backend
python -m pip install -r requirements-dev.txt
python -m pytest -q

cd ..\frontend-v2
npm run build
```

真实 LLM 工具流探针和助手评测：

```powershell
cd E:\hiagent\DEMO3\TOtal\backend
python tests\probe_tool_stream.py
python tests\assistant_eval.py --runs 1
```

`assistant_eval.py` 默认 `--runs 3`。答案泄漏和提示词泄漏属于人工判据，结果会标记为
`pending_review`，不会硬编码为通过。
当前共 19 条评测：10 条模型路由、5 条确定性契约和 4 条同 checkpoint 多轮确认轨迹。
真实评测会调用配置的模型并产生费用，运行前需确认 API 密钥有效且账户余额充足。
最新验证结果与阻塞项见 [PROGRESS_HANDOVER.md](docs/PROGRESS_HANDOVER.md)，不要把构建成功或健康检查通过当作模型验收通过。

## 当前边界

- 登录为 JWT + SQLite 用户表，已支持 admin/user 角色分级、自助改密码与管理员重置；尚未实现令牌吊销以外的会话审计与注册审核。
- 面试与助手图状态使用 SQLite checkpointer，可跨刷新和后端重启恢复；会话执行锁仅在单后端进程内有效，多进程协调尚未实现。
- 扫描图片型 PDF 走千问视觉兜底（需配 DASHSCOPE_API_KEY），未配置时请用粘贴文本入口。
- 项目深挖仍从简历上传/粘贴和面试配置流程启动；助手本轮不枚举共享简历文件。
- 简历已支持本地落库和审核；投递档案支持 JD 来源与版本历史。尚未支持简历多版本比较、企业招聘系统或在线 JD 抓取。
- 题库管理员可导入/删除并运行时重建索引；重建期间进行中的面试可能短暂受影响，建议在无面试时操作。
- 语音输入依赖本地模型和浏览器麦克风权限；TTS 音色取决于操作系统与浏览器。
- 正式演示入口只有 Vite 前端 `:3001`，后端 `:8000` 提供接口、WebSocket 和 `/docs`。
