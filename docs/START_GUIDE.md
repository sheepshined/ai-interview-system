# DEMO3 本机启动手册

## 首次运行一次

### 1. 准备后端

```powershell
cd E:\hiagent\DEMO3\TOtal\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

编辑 `.env`，填写：

```env
LLM_API_KEY=你的API密钥
```

确认模型账户有可用余额。DeepSeek 返回 HTTP 402 时需补充余额或配置可用的兼容模型，
反复重试不会解决账户问题。`/healthz` 和 `/readyz` 不验证模型账户余额。

构建题库：

```powershell
python main.py build
python main.py fetch-models
```

第二条命令下载并校验本地语音输入所需的 SenseVoice 与 Silero VAD 模型；已存在且
校验通过的文件会自动跳过。BGE 嵌入模型仍按 `.env` 中的
`LOCAL_BGE_MODEL_PATH` 或 Hugging Face 默认路径加载。面试朗读使用浏览器原生 TTS，
无需下载额外语音合成模型。

### 2. 准备前端

```powershell
cd E:\hiagent\DEMO3\TOtal\frontend-v2
npm install
```

## 每次演示

打开两个 PowerShell 窗口。

### 窗口 1：后端

```powershell
cd E:\hiagent\DEMO3\TOtal\backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

看到 `Uvicorn running on http://127.0.0.1:8000` 即启动成功。

若出现 `[WinError 10048]`，说明 `8000` 端口已被其他程序占用。先关闭旧后端或占用该端口的终端，再重新执行启动命令；可用 `netstat -ano | findstr :8000` 查看占用进程。

### 窗口 2：前端

```powershell
cd E:\hiagent\DEMO3\TOtal\frontend-v2
npm run dev -- --host 127.0.0.1
```

浏览器打开：

```text
http://127.0.0.1:3001
```

登录账号：

```text
用户名：admin
密码：123123
```

## 快速检查

- 后端接口：`http://127.0.0.1:8000/api/roles`
- 接口文档：`http://127.0.0.1:8000/docs`
- 前端页面：`http://127.0.0.1:3001`

若岗位为空或简历请求失败，先确认 `/api/roles` 能返回「大模型应用开发」专场岗位，再刷新前端页面。

## 统筹助手验收

登录后点击右下角的统筹助手按钮，依次检查：

1. 发送普通消息，确认流式回复结束后仍可在同一会话继续追问。
2. 发送“帮我面一场，中级难度，8 题”，刷新页面后确认提案卡片仍存在。
3. 修改题量并确认，页面应只跳转一次到面试页；拒绝提案时不跳转。
4. 发送“去知识库聊 RAG 分块”，确认后应进入知识库对话页并预填问题。

项目深挖请先进入简历页上传 PDF 或粘贴简历，再从面试配置页开始。助手不会扫描共享上传目录寻找简历。

## 新增能力验收

1. 在“我的笔记”打开含 `[[关联笔记]]` 的笔记并进入预览，点击链接后应在右侧出现“插入笔记”页签，当前草稿和路由保持不变；同时检查全屏按钮和侧栏收起按钮。
2. 在简历页上传或粘贴内容，编辑结构化字段并完成审核确认；刷新后记录仍应存在，未确认简历不能进入 JD 分析。
3. 在简历匹配页粘贴 JD，确认结果只给出证据、匹配项和差距，不显示 ATS 分、录用概率或录用结论。
4. 点击麦克风后先完成短暂噪声校准，转写文本只写入输入框并保留 3 秒复核时间，不会自动发送。
5. 开启面试朗读后，检查暂停/继续和跳过当前朗读按钮。
6. 在“投递记录”新建自己的档案，选择已审核简历，记录阶段、备注和复盘；从档案开始模拟面试，报告应关联到同一档案。此功能只记录投递，不实际联系招聘方。

## JD 版本与助手写入验收

1. 从投递档案进入“JD 分析”，修改正文或来源链接后保存，历史目录应新增版本；刷新后当前正文和历史都保留。
2. 选择较早版本，核对历史正文、来源与 SHA-256。恢复后应追加新版本，原历史不会被覆盖。
3. 两个页面打开同一档案，在其中一个页面保存后，再用旧页面保存应提示版本冲突，并保留旧页面的本地草稿。重新载入或离开前应提示丢弃草稿，可取消。
4. 向助手发送“读取档案 #ID 的当前 JD 和版本，再把正文改为……，保留来源”。服务端确认卡出现前不能写入，批准后只执行一次；再次写入仍需新的确认。
5. 拒绝助手的 JD 操作不应改变版本。确认期间在其他页面修改该 JD，再批准旧操作，不应覆盖新内容或自动重试。

其他用户不能按 ID 读取、保存或恢复这些 JD 版本；归档档案的历史保留为只读。

## 回归验证

后端测试必须单进程顺序执行：

```powershell
cd E:\hiagent\DEMO3\TOtal\backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe tests\probe_tool_stream.py
.\.venv\Scripts\python.exe tests\assistant_eval.py --runs 1
```

真实评测共 19 条，结果写到 `backend/tests/results/assistant_eval_latest.json`；安全类样本的
`pending_review` 需要人工阅读答案摘录，不代表自动通过。一次真实评测调用会产生费用；
默认重复 3 次，上面的 `--runs 1` 用于单轮验收。模型调用失败会使对应用例失败，不会硬编码成功。

本轮后端 `176 passed`，前端构建成功；最新真实评测为 `14 passed / 2 pending_review / 3 failed`，
后三条确认轨迹遇到 DeepSeek HTTP 402 余额不足，补充余额后仍需重跑，不能视为验收完成。
详细状态与浏览器验收记录见 `PROGRESS_HANDOVER.md`。

关闭服务时，分别在两个 PowerShell 窗口按 `Ctrl + C`。
