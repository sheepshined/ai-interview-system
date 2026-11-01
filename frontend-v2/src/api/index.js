import { getToken, clearAuth } from '../auth'

const BASE = '/api'

// 上传等长耗时操作的超时阈值 (毫秒)
const DEFAULT_TIMEOUT = 30000   // 普通请求 30s
const UPLOAD_TIMEOUT = 90000     // 上传 (含 LLM 解析) 90s

async function request(url, options = {}) {
  const headers = { ...options.headers }
  const isFormData = options.body instanceof FormData

  // 鉴权: 除 login/register 外自动携带 Bearer token
  if (!options.skipAuth) {
    const token = getToken()
    if (token) headers['Authorization'] = `Bearer ${token}`
  }

  // FormData: 不设置 Content-Type, 让浏览器自动添加 boundary
  // JSON: 设置 Content-Type 并序列化 body
  if (options.body && !isFormData) {
    headers['Content-Type'] = 'application/json'
    options.body = JSON.stringify(options.body)
  }

  // 超时控制: AbortController
  const timeout = options.timeout || DEFAULT_TIMEOUT
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  // 透传用户传入的 signal (如有) 与超时 signal 合并
  if (options.signal) {
    options.signal.addEventListener('abort', () => controller.abort())
  }

  let res
  try {
    res = await fetch(`${BASE}${url}`, {
      ...options,
      headers,
      signal: controller.signal,
    })
  } catch (err) {
    clearTimeout(timer)
    if (err.name === 'AbortError') {
      return { success: false, status: 0, message: '请求超时，请稍后重试（简历解析较慢，最多需 90 秒）' }
    }
    return {
      success: false,
      status: 0,
      message: '无法连接后端服务，请确认 FastAPI 已在 127.0.0.1:8000 启动',
    }
  } finally {
    clearTimeout(timer)
  }

  if (!res.ok) {
    // 尝试从响应体提取错误信息
    let detail = ''
    try {
      const errBody = await res.json()
      detail = errBody.detail || errBody.message || ''
    } catch (_) {
      detail = await res.text().catch(() => '')
    }
    // Pydantic 校验错误的 detail 是数组 [{loc, msg}], 拼成可读文本而非 "[object Object]"
    if (Array.isArray(detail)) {
      detail = detail.map((d) => `${(d.loc || []).slice(-1)[0] || ''} ${d.msg || ''}`.trim()).join('; ')
    }
    // 401 (除登录本身): token 缺失/过期 → 清除本地登录态并送回登录页
    // 护栏: 已在 /login 时不再跳转, 否则任何"未登录页面挂载后拉鉴权接口"的组件
    // 都会把页面拖进 重定向死循环 (表现为持续闪烁)
    if (res.status === 401 && !options.skipAuth) {
      clearAuth()
      if (!window.location.pathname.startsWith('/login')) {
        const redirect = encodeURIComponent(window.location.pathname + window.location.search)
        window.location.href = `/login?redirect=${redirect}`
      }
      return { success: false, status: 401, message: '登录已过期，请重新登录' }
    }
    return {
      success: false,
      status: res.status,
      message: res.status === 404
        ? '接口不存在（404），请确认启动的是当前项目后端'
        : res.status === 500 && !detail
          ? '后端未启动或代理连接失败，请确认 FastAPI 已在 127.0.0.1:8000 启动'
          : `请求失败 (${res.status})` + (detail ? `: ${detail}` : ''),
    }
  }

  try {
    return await res.json()
  } catch (err) {
    return { success: false, message: `响应解析失败: ${err.message}` }
  }
}

export const getRoles = () => request('/roles')

export const login = (username, password) =>
  request('/login', { method: 'POST', body: { username, password }, skipAuth: true })

export const register = (username, password) =>
  request('/register', { method: 'POST', body: { username, password }, skipAuth: true })

export const uploadResume = (file) => {
  const fd = new FormData()
  fd.append('file', file)
  return request('/upload/resume', {
    method: 'POST',
    body: fd,
    timeout: UPLOAD_TIMEOUT,
  })
}

export const parseTextResume = (content) =>
  request('/resume/parse-text', { method: 'POST', body: { content } })

export const listResumes = () => request('/resumes')
export const getLatestResume = () => request('/resumes/latest')
export const getResume = (id) => request(`/resumes/${id}`)
export const updateResume = (id, content, title = '') =>
  request(`/resumes/${id}`, { method: 'PUT', body: { content, title } })
export const confirmResume = (id) =>
  request(`/resumes/${id}/confirm`, { method: 'POST' })
export const analyzeJd = (resumeId, jdText) =>
  request('/jd/analyze', {
    method: 'POST', body: { resume_id: resumeId, jd_text: jdText }, timeout: 90000,
  })

// 个人知识库 (v0.7 + v0.8)
export const kbListNotes = (search = '', tag = '', category = '') =>
  request(`/kb/notes?search=${encodeURIComponent(search)}&tag=${encodeURIComponent(tag)}&category=${encodeURIComponent(category)}`)

export const kbGetNote = (id) => request(`/kb/notes/${id}`)

export const kbCreateNote = (title, content = '', tags = [], category = '') =>
  request('/kb/notes', { method: 'POST', body: { title, content, tags, category } })

export const kbUpdateNote = (id, title, content, tags, category = '') =>
  request(`/kb/notes/${id}`, { method: 'PUT', body: { title, content, tags, category } })

export const kbDeleteNote = (id) =>
  request(`/kb/notes/${id}`, { method: 'DELETE' })

export const kbGraph = (semantic = true, category = '') =>
  request(`/kb/graph?semantic=${semantic}&category=${encodeURIComponent(category)}`)

export const kbCategories = () => request('/kb/categories')

export const kbUploadFiles = (fileList) => {
  const fd = new FormData()
  for (const f of fileList) fd.append('files', f)
  return request('/kb/notes/upload', {
    method: 'POST', body: fd, timeout: 300000,  // 5min: 多文件提取+LLM
  })
}

export const kbCreateUrlNote = (url, title, description, category = '') =>
  request('/kb/notes/url', { method: 'POST', body: { url, title, description, category } })

export const kbSearch = (q, topK = 5) =>
  request(`/kb/search?q=${encodeURIComponent(q)}&top_k=${topK}`)

export const kbQa = (question, topK = 5, sessionId = null) =>
  request('/kb/qa', { method: 'POST', body: { question, top_k: topK, session_id: sessionId }, timeout: 120000 })

export const kbInterpretNote = (noteId, title, content) =>
  request('/kb/interpret', {
    method: 'POST',
    body: { note_id: noteId, title, content },
    timeout: 120000,
  })

// v0.9: 对话会话
export const kbChatListSessions = () => request('/kb/chat/sessions')
export const kbChatCreateSession = () => request('/kb/chat/sessions', { method: 'POST' })
export const kbChatGetSession = (id) => request(`/kb/chat/sessions/${id}`)
export const kbChatRenameSession = (id, title) =>
  request(`/kb/chat/sessions/${id}`, { method: 'PATCH', body: { title } })
export const kbChatDeleteSession = (id) =>
  request(`/kb/chat/sessions/${id}`, { method: 'DELETE' })

export const kbTidy = (noteId) =>
  request(`/kb/tidy?note_id=${noteId}`, { method: 'POST', timeout: 180000 })

export const kbAutoCategory = (noteId) =>
  request(`/kb/auto-category?note_id=${noteId}`, { method: 'POST', timeout: 120000 })

// 智能关联: 为已有笔记检索 top3 高相关笔记并追加 [[双链]] (孤立笔记融入图谱)
export const kbAutoLink = (noteId) =>
  request(`/kb/notes/${noteId}/auto-link`, { method: 'POST', timeout: 120000 })

export const kbRebuild = () =>
  request('/kb/rebuild', { method: 'POST', timeout: 300000 })

export const kbImportFromReport = (items, reportId) =>
  request('/kb/notes/from-report', { method: 'POST', body: { items, report_id: reportId } })

// 报告管理 (阶段2)
export const getReports = () => request('/reports')
export const getReport = (reportId) => request(`/reports/${reportId}`)
export const getReportRadar = (reportId) => request(`/reports/${reportId}/radar`)
export const getGrowth = () => request('/reports/growth')

// 账号与管理员 (v1.3)
export const getAccountMe = () => request('/account/me')
export const getQbankSummary = () => request('/qbank/summary')
export const changePassword = (oldPassword, newPassword) =>
  request('/account/password', { method: 'POST', body: { old_password: oldPassword, new_password: newPassword } })
export const listUsers = () => request('/admin/users')
export const adminResetPassword = (username, newPassword) =>
  request(`/admin/users/${username}/password`, { method: 'POST', body: { new_password: newPassword } })
export const adminSetEnabled = (username, enabled) =>
  request(`/admin/users/${username}/enabled`, { method: 'POST', body: { enabled } })
export const adminSetRole = (username, role) =>
  request(`/admin/users/${username}/role`, { method: 'POST', body: { role } })
export const getQbankStats = () => request('/admin/qbank/stats')
export const getQbankTemplate = () => request('/admin/qbank/template')
export const listQbankQuestions = (category = '', q = '', limit = 200, offset = 0) =>
  request(`/admin/qbank/list?category=${encodeURIComponent(category)}&q=${encodeURIComponent(q)}&limit=${limit}&offset=${offset}`)
export const importQbankQuestions = (questions, dryRun = false) =>
  request('/admin/qbank/import', { method: 'POST', body: { questions, dry_run: dryRun } })
export const deleteQbankQuestion = (questionId) =>
  request(`/admin/qbank/question/${encodeURIComponent(questionId)}`, { method: 'DELETE' })
export const rebuildQbankIndex = () =>
  request('/admin/qbank/rebuild', { method: 'POST', timeout: 180000 })

// 投递档案与面试复盘
export const listApplications = () => request('/applications')
export const getApplication = (id) => request(`/applications/${id}`)
export const createApplication = (body) =>
  request('/applications', { method: 'POST', body })
export const updateApplication = (id, body) =>
  request(`/applications/${id}`, { method: 'PUT', body })
export const addApplicationEvent = (id, note) =>
  request(`/applications/${id}/events`, { method: 'POST', body: { note } })
export const saveApplicationOutcome = (id, body) =>
  request(`/applications/${id}/outcome`, { method: 'PUT', body })
export const archiveApplication = (id) =>
  request(`/applications/${id}`, { method: 'DELETE' })
export const listJdVersions = (id) => request(`/applications/${id}/jd/versions`)
export const getJdVersion = (id, versionId) => request(`/applications/${id}/jd/versions/${versionId}`)
export const saveJdVersion = (id, body) => request(`/applications/${id}/jd`, { method: 'PUT', body })
export const restoreJdVersion = (id, versionId, expectedVersion) =>
  request(`/applications/${id}/jd/versions/${versionId}/restore`, { method: 'POST', body: { expected_version: expectedVersion } })

// 逐题面试记录 (v0.9 右侧边栏)
export const listInterviewRecords = () => request('/interview-records')
export const getInterviewRecord = (filename) => request(`/interview-records/${encodeURIComponent(filename)}`)
export const deleteInterviewRecord = (filename) =>
  request(`/interview-records/${encodeURIComponent(filename)}`, { method: 'DELETE' })

// 知识库原始文件: 走鉴权下载接口 (<a>/<img> 无法带自定义头, 用 ?token= 传递)
export function kbFileUrl(path) {
  if (!path) return '#'
  const name = encodeURIComponent(String(path).split('/').pop() || '')
  const token = encodeURIComponent(getToken() || '')
  return `/api/kb/files/${name}?token=${token}`
}

// 本地语音识别 (v1.1): WAV → 后端 SenseVoice 离线转写; 抽屉语音输入复用
export const transcribeAudio = (blob) => {
  const fd = new FormData()
  fd.append('file', blob, 'voice.wav')
  return request('/asr', { method: 'POST', body: fd, timeout: 30000 })
}

// 统筹智能体 (v2.0): 会话/设置/记忆走 REST, 对话流走 /ws/assistant
export const listAssistantSessions = () => request('/assistant/sessions')
export const createAssistantSession = () => request('/assistant/sessions', { method: 'POST' })
export const getAssistantSession = (id) => request(`/assistant/sessions/${id}`)
export const renameAssistantSession = (id, title) =>
  request(`/assistant/sessions/${id}`, { method: 'PATCH', body: { title } })
export const deleteAssistantSession = (id) =>
  request(`/assistant/sessions/${id}`, { method: 'DELETE' })
export const getAssistantSettings = () => request('/assistant/settings')
export const putAssistantSettings = (body) => request('/assistant/settings', { method: 'PUT', body })
export const listAssistantMemories = (kind = '') =>
  request(`/assistant/memories?kind=${encodeURIComponent(kind)}`)
export const deleteAssistantMemory = (id) =>
  request(`/assistant/memories/${id}`, { method: 'DELETE' })
export const clearAssistantMemories = () => request('/assistant/memories', { method: 'DELETE' })
