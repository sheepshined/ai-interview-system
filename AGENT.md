# AGENT.md

面向 AI 编码智能体的项目工作指南。修改代码前先读本文件，再阅读相关模块和测试。

## 1. 项目定位

这是本地优先的 AI 模拟面试系统，核心闭环为：

**简历/JD 分析 → LangGraph 模拟面试 → 四维评分与报告 → 成长档案与复习**。

系统还包含统筹助手、技能运行时、个人知识库、题库管理、JD 版本管理和投递档案。当前唯一前端是 `frontend-v2/`，不要新建或恢复旧的 `frontend/`。

## 2. 技术栈与目录

| 路径 | 职责 |
|---|---|
| `backend/server.py` | FastAPI REST 与 WebSocket 入口 |
| `backend/agent/` | LangGraph 面试状态机、协议、评分与记忆 |
| `backend/assistant/` | 统筹助手、权限、工具、上下文压缩与持久化 |
| `backend/skills/` | 技能加载、frontmatter 元数据与统一运行时 |
| `backend/retrieval/` | 题库 BM25 + 向量混合检索 |
| `backend/knowledge.py` | 知识库笔记、双链、图谱与会话 |
| `backend/kb_parent.py` | 父文档检索与语义关联 |
| `backend/growth.py` | 报告趋势与成长档案 |
| `backend/applications.py` | 投递档案与状态联动 |
| `backend/jd_store.py` | JD 来源、解析与版本管理 |
| `backend/tests/` | 单元、集成、评测及真实模型烟雾脚本 |
| `frontend-v2/` | Vue 3 + Vite 单页应用，开发端口 3001 |
| `docs/` | 启动、设计、进度与项目导读文档 |

后端使用 FastAPI、LangGraph、LangChain、SQLite、Chroma 和本地 SenseVoice；前端使用 Vue 3、Vue Router 与 Vite。

## 3. 本地启动

以下命令默认在仓库根目录执行，详细准备步骤见 `README.md` 和 `docs/START_GUIDE.md`。

```powershell
# 一键启动：检查环境并启动 8000/3001 两个服务
.\start-demo.ps1
```

也可使用两个终端分别启动：

```powershell
# 后端
Set-Location backend
.\.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8000
```

```powershell
# 前端
Set-Location frontend-v2
npm run dev -- --host 127.0.0.1
```

- 后端健康检查：`http://127.0.0.1:8000/healthz`
- API 调试入口：`http://127.0.0.1:8000/docs`
- 前端入口：`http://127.0.0.1:3001`
- 首次使用需复制 `backend/.env.example` 为 `backend/.env` 并填写模型配置。

## 4. 修改代码时必须遵守的规则

### 面试状态机

- `backend/agent/graph.py` 中等待用户输入的节点会在 LangGraph 恢复时重新进入。
- `interrupt()` 之前不得加入随机选题、LLM 调用、写文件或其他副作用，避免恢复后重复出题或重复写入。
- WebSocket 命令必须继续通过 `backend/agent/protocol.py` 的阶段约束，不得绕过。
- 修改出题、评分、提示、追问或报告字段时，同时检查前端协议处理与相关测试。

### 统筹助手与技能

- 新增助手工具时，同步处理工具 schema、权限、确认流、事件输出和持久化。
- 有写入或外部副作用的操作必须保留用户确认与幂等保护，不得因自动执行而跳过。
- 助手不要重新实现业务逻辑，应复用题库、知识库、JD、投递等现有服务接口。
- 技能只通过 `backend/skills/` 的加载与运行时路径接入；frontmatter 名称和说明必须与实际能力一致。
- 修改技能或助手后，保持工具结果结构稳定，并更新对应测试。

### 数据与安全

- 所有报告、会话、简历、笔记、JD 和投递数据必须按用户隔离；REST 与 WebSocket 都要鉴权。
- 不得提交 `.env`、JWT 密钥、数据库、上传文件、向量库、模型、日志、缓存或评测输出。
- 不得把个人求职材料、面试准备材料或其他项目文件加入本仓库。
- 示例配置只能使用占位符，不得写入真实 API Key、Token 或密码。
- 优先使用环境变量覆盖本地路径，不要在源码中硬编码个人绝对路径。

### 前端

- 只修改 `frontend-v2/`；API 与 WebSocket 通过 Vite 代理连接后端。
- 修改接口字段时同步更新调用方、加载状态、错误状态和空状态。
- 完成前端修改后执行生产构建，不能只依赖开发服务器页面表现。

## 5. 验证命令

后端测试在 `backend/` 下运行，并保持单进程顺序执行：

```powershell
# 面试协议与状态机
python -m pytest tests/test_protocol.py tests/test_interview_graph.py tests/test_score_parser.py -q

# 统筹助手
python -m pytest tests/test_assistant_graph.py tests/test_assistant_tools.py tests/test_assistant_ws.py -q

# 技能运行时
python -m pytest tests/test_skills_loader.py tests/test_skills_runtime.py -q

# 修改投递、JD 或成长档案时
python -m pytest tests/test_application_api.py tests/test_jd_versions.py tests/test_growth.py -q
```

前端在 `frontend-v2/` 下验证：

```powershell
npm run build
```

根据改动范围补充对应测试文件。`real_smoke*.py`、`voice_real_test.py` 等真实模型或语音脚本只在外部模型配置具备且确实需要时单独运行；不得把它们的成功与健康检查、普通单元测试混为一谈。

## 6. 完成标准

提交前确认：

1. 只修改了任务所需文件，没有带入个人材料或本地产物。
2. 相关测试与前端构建通过；未执行的真实模型验收不得声称通过。
3. 新增或变更接口有鉴权、用户隔离和错误处理。
4. README、启动说明或 `docs/PROGRESS_HANDOVER.md` 与实际行为保持一致。
5. 不提交密钥、运行数据、依赖目录或生成的二进制文件。
