<template>
  <div class="room">

    <!-- ══ 顶栏 ══ -->
    <header class="room-top">
      <div class="room-left">
        <button class="room-exit" @click="handleExit"><Icon name="arrowLeft" :size="14" />退出</button>
        <div class="room-role">
          {{ roleTitle || '模拟面试' }}
          <small>Mock session · Intermediate</small>
        </div>
      </div>

      <div class="room-progress">
        <span class="label">第 <b>{{ questionNum }}</b> / {{ totalCount }} 题 · {{ ended ? 'Ended' : 'In progress' }}</span>
        <div class="ticks-line">
          <i v-for="i in totalCount" :key="i" :class="{ done: i < questionNum, now: i === questionNum }"></i>
        </div>
      </div>

      <div class="room-right">
        <button v-if="ttsSpeaking" class="tts-icon-btn" :title="ttsPaused ? '继续朗读' : '暂停朗读'" @click="toggleTtsPause">
          <Icon :name="ttsPaused ? 'play' : 'pause'" :size="14" />
        </button>
        <button v-if="ttsSpeaking" class="tts-icon-btn" title="跳过本段朗读" @click="skipTts">
          <Icon name="skipForward" :size="14" />
        </button>
        <button class="tts-btn" :class="{ 'is-on': ttsEnabled }" :title="ttsEnabled ? '关闭语音朗读' : '开启语音朗读'" @click="toggleTts">
          <Icon :name="ttsEnabled ? 'volume' : 'volumeX'" :size="14" />{{ ttsEnabled ? '语音' : '静音' }}
        </button>
        <span class="timer">{{ timerDisplay }}</span>
      </div>
    </header>

    <!-- ══ 作答中 ══ -->
    <div v-if="!ended && !isGeneratingReport" class="room-body">
      <main ref="chatRef" class="transcript">
        <div class="transcript-inner">
          <div v-if="connectionError" class="msg msg-status is-error"><span>{{ connectionError }}</span></div>

          <template v-for="(msg, i) in displayMessages" :key="i">
            <!-- 系统状态行 -->
            <div v-if="msg.side === 'system'" class="msg msg-status" :class="{ 'is-error': msg.isError }">
              <span>{{ msg.isError ? msg.displayText : `— ${msg.displayText} —` }}</span>
            </div>

            <!-- 提示便签 -->
            <article v-else-if="msg.msgType === 'hint'" class="msg msg-hint">
              <div class="msg-head"><span class="msg-who" style="color:var(--ink-3)">提示</span></div>
              <div class="hint-card">
                <Icon name="bulb" :size="17" />
                <div class="txt"><b>HINT {{ msg.hintLevel || 1 }}/2</b><br />{{ msg.content }}</div>
              </div>
            </article>

            <!-- 反馈 / 追问 -->
            <article v-else-if="msg.msgType === 'reaction'" class="msg msg-comment">
              <div class="msg-head"><span class="msg-who" style="color:var(--ink-3)">面试官 · 反馈</span></div>
              <div class="msg-text">{{ msg.displayText }}</div>
            </article>

            <!-- 我的作答 -->
            <article v-else-if="msg.side === 'user'" class="msg msg-user">
              <div class="msg-head">
                <span class="msg-who">我</span><span class="msg-time">{{ msg.time }}</span>
              </div>
              <div class="msg-text">{{ msg.displayText }}</div>
            </article>

            <!-- 面试官：开场 / 出题 / 追问 / 收尾 -->
            <article v-else class="msg msg-ai">
              <div class="msg-head">
                <span class="msg-who">面试官</span><span class="msg-time">{{ msg.time }}</span>
                <span v-if="msg.qIndex" class="msg-qid">Q{{ msg.qIndex }}</span>
              </div>
              <div class="msg-text">{{ msg.displayText }}<span v-if="msg.streaming" class="caret"></span><span
                v-if="ttsSpeaking && !msg.streaming && i === lastAiIndex" class="tts-indicator" title="AI 正在朗读"><Icon name="volume" :size="13" /></span></div>
            </article>
          </template>

          <!-- 思考中 -->
          <div v-if="showThinking" class="msg msg-status">
            <span class="thinking"><i></i><i></i><i></i></span>
          </div>
        </div>
      </main>

      <!-- 右侧控制台 -->
      <aside class="console">
        <div class="panel">
          <div class="panel-head">面试信息 <Icon name="target" :size="15" /></div>
          <div class="panel-body">
            <div class="kv"><span class="k">岗位</span><span class="v">{{ roleTitle || '-' }}</span></div>
            <div class="kv"><span class="k">题量</span><span class="v">{{ totalCount }} 题</span></div>
            <div class="kv"><span class="k">已答</span><span class="v">{{ answeredCount }} 题</span></div>
            <div class="kv"><span class="k">用时</span><span class="v">{{ timerDisplay }}</span></div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">题目状态 <Icon name="layers" :size="15" /></div>
          <div class="panel-body">
            <ul class="q-list">
              <li v-for="i in totalCount" :key="i" :class="{ done: i < questionNum, now: i === questionNum }">
                <span class="qn">{{ pad2(i) }}</span>
                <span>第 {{ i }} 题</span>
                <span class="state">{{ i < questionNum ? '已评分' : (i === questionNum ? '作答中' : '待出题') }}</span>
              </li>
            </ul>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">面试记录
            <button class="del" style="opacity:1" title="刷新" @click="refreshRecords"><Icon name="refresh" :size="13" /></button>
          </div>
          <div class="panel-body" style="padding-top:6px">
            <div v-if="recordsLoading" class="rec-empty">加载中…</div>
            <div v-else-if="!records.length" class="rec-empty">暂无历史记录</div>
            <template v-else>
              <div v-for="r in records" :key="r.filename" class="rec-item">
                <div style="min-width:0;flex:1;cursor:pointer" @click="openRecord(r.filename)">
                  <div class="t">{{ r.role_title || '未知岗位' }}</div>
                  <div class="d">{{ formatRecDate(r) }}</div>
                </div>
                <button class="del" title="删除" @click.stop="deleteRecord(r.filename)"><Icon name="trash" :size="13" /></button>
              </div>
            </template>
          </div>
        </div>

        <button class="end-btn" @click="endInterview">提前结束面试</button>
      </aside>
    </div>

    <!-- ══ 生成报告中 ══ -->
    <div v-if="isGeneratingReport" class="room-body">
      <div class="finish">
        <div class="gen-card">
          <div class="stamp stamp-sm" style="--sz:66px;font-size:15px">归档中</div>
          <h2>正在生成面试报告</h2>
          <p>汇总逐题评分、四维雷达与学习建议，通常需要 10–20 秒</p>
          <div class="progress" style="margin-top:24px"><div class="progress-fill" style="width:64%"></div></div>
          <div class="gen-log">
            <div>› 汇总 {{ answeredCount }} / {{ totalCount }} 题评分记录 …… <b>完成</b></div>
            <div>› 计算四维雷达与分类得分 …… <b>完成</b></div>
            <div>› 生成好答案 / 差答案对比 …… <b>进行中</b></div>
            <div>› 写入报告档案 …… 等待</div>
          </div>
        </div>
      </div>
    </div>

    <!-- ══ 面试已完成 ══ -->
    <div v-if="ended && !isGeneratingReport" class="room-body">
      <div class="finish">
        <div class="finish-card">
          <div class="stamp stamp-lg">已完成</div>
          <h2>面试已完成</h2>
          <p style="color:var(--ink-3); font-size:14px">本场共 {{ totalCount }} 题，你的作答记录已全部留档</p>
          <div class="stats">
            <div><div class="n">{{ answeredCount }}</div><div class="l">回答题数</div></div>
            <div><div class="n">{{ timerDisplay }}</div><div class="l">用时</div></div>
            <div><div class="n">{{ completionPercent }}%</div><div class="l">完成度</div></div>
          </div>
          <button class="btn btn-lg" style="--btn-bg:var(--vermilion); border-color:var(--vermilion)" @click="generateReport">
            生成面试报告<Icon name="arrowRight" class="ar" :size="18" />
          </button>
          <p class="mono" style="margin-top:18px">或稍后在「面试记录」中随时生成</p>
        </div>
      </div>
    </div>

    <!-- ══ 作答台 ══ -->
    <footer v-if="!ended && !isGeneratingReport" class="desk">
      <div class="desk-inner">
        <div class="desk-box">
          <textarea ref="inputRef" v-model="userInput" rows="1"
                    :placeholder="inputBusy ? 'AI 正在处理…' : (listening ? '正在聆听，请说话…' : voiceProcessing ? '正在本地转写…' : '输入你的回答，Enter 发送 / Shift + Enter 换行…')"
                    spellcheck="false" autocomplete="off" autocorrect="off" autocapitalize="off"
                    :disabled="inputBusy" @keydown="handleInputKeydown"></textarea>
          <div class="desk-tools">
            <button v-if="voiceSupported" class="dbtn" :class="{ 'is-live': listening }" :disabled="inputBusy || voiceProcessing"
                    :title="listening ? '停止语音输入' : '本地语音输入'" @click="toggleVoice">
              <Icon :name="listening ? 'square' : 'mic'" :size="15" />
            </button>
            <button class="dbtn" :disabled="inputBusy || hintCount >= 2" :title="hintCount >= 2 ? '每题最多2次提示' : '获取提示（每题 2 次）'" @click="sendHint">
              <Icon name="bulb" :size="15" />提示
            </button>
            <button class="send-btn" :disabled="!userInput.trim() || inputBusy" @click="sendAnswer">
              发送<Icon name="send" :size="15" />
            </button>
          </div>
        </div>
        <div class="desk-meta">
          <span>Enter 发送 · Shift+Enter 换行</span>
          <span v-if="voiceReviewCountdown">转写已填入，请核对后发送 · {{ voiceReviewCountdown }}s</span>
          <span v-else-if="voice.error">{{ voice.error }}</span>
          <span>提示 {{ hintCount }} / 2 已使用</span>
        </div>
      </div>
    </footer>

    <!-- ══ 面试记录抽屉 ══ -->
    <div class="mask room-mask" :class="{ 'is-open': recordDrawerOpen }" @click="closeRecordDrawer"></div>
    <aside class="drawer room-drawer" :class="{ 'is-open': recordDrawerOpen }">
      <div class="room-drawer-head">
        <div style="min-width:0">
          <div class="room-drawer-title">面试记录</div>
          <div class="room-drawer-sub">{{ recordDrawerTitle }}</div>
        </div>
        <button class="room-drawer-close" @click="closeRecordDrawer"><Icon name="x" :size="18" /></button>
      </div>
      <div class="room-drawer-body">
        <pre class="room-md">{{ recordDrawerContent }}</pre>
      </div>
    </aside>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useWebSocket } from '../composables/useWebSocket'
import { useVoiceInput } from '../composables/useVoiceInput'
import { listInterviewRecords, getInterviewRecord, deleteInterviewRecord } from '../api'
import Icon from '../components/Icon.vue'
import { toast } from '../composables/useToast'

const router = useRouter()
const {
  messages,
  connectionError,
  isStreaming: streaming,
  ttsEnabled,
  ttsSpeaking,
  ttsPaused,
  connect,
  sendConfig,
  send,
  sendAnswer: wsSendAnswer,
  requestHint,
  sendEnd,
  requestReport,
  toggleTts,
  toggleTtsPause,
  skipTts,
  stopTts,
  close,
} = useWebSocket()

const chatRef = ref(null)
const inputRef = ref(null)
const userInput = ref('')

// ---- 状态 ----
const roleTitle = ref('')
const totalCount = ref(5)
const questionNum = ref(1)
const ended = ref(false)
const isGeneratingReport = ref(false)
const awaitingResponse = ref(false)
const hintCount = ref(0)
const answeredCount = ref(0)
const startTime = ref(Date.now())
const elapsed = ref(0)
let timerInterval = null

onMounted(() => {
  timerInterval = setInterval(() => {
    if (!ended.value) elapsed.value = Math.floor((Date.now() - startTime.value) / 1000)
  }, 1000)
})
onUnmounted(() => { if (timerInterval) clearInterval(timerInterval) })

const timerDisplay = computed(() => {
  const m = String(Math.floor(elapsed.value / 60)).padStart(2, '0')
  const s = String(elapsed.value % 60).padStart(2, '0')
  return m + ':' + s
})
const completionPercent = computed(() =>
  totalCount.value ? Math.min(Math.round((answeredCount.value / totalCount.value) * 100), 100) : 0)

// ---- 输入框自适应高度 ----
function autoResizeInput() {
  const el = inputRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 150) + 'px'
}
watch(userInput, () => nextTick(autoResizeInput))

// Enter 发送, Shift+Enter 换行; 中文输入法组词中(isComposing)不触发发送
function handleInputKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    sendAnswer()
  }
}

// ---- 本地语音输入: 麦克风 PCM -> 后端 SenseVoice, 转写只填入输入框 ----
const voiceBaseText = ref('')
const voice = useVoiceInput({ onResult(text) {
  const separator = voiceBaseText.value && !voiceBaseText.value.endsWith('\n') ? '\n' : ''
  userInput.value = `${voiceBaseText.value}${separator}${text}`
} })
const voiceSupported = voice.supported
const listening = voice.recording
const voiceProcessing = voice.processing
const voiceReviewCountdown = voice.reviewCountdown

async function toggleVoice() {
  if (!voiceSupported || voiceProcessing.value) return
  if (listening.value) {
    await voice.stop()
    return
  }
  stopTts()
  voiceBaseText.value = userInput.value
  if (await voice.start()) toast('正在聆听，请说话…', 'mic')
}

// ---- 流式/思考态 ----
const liveStreamHasText = computed(() =>
  messages.value.some(m => m.type === 'stream_start' && (m.content || '').trim()))
const showThinking = computed(() =>
  (streaming.value || awaitingResponse.value)
  && !isGeneratingReport.value
  && !liveStreamHasText.value)
const inputBusy = computed(() =>
  (streaming.value || awaitingResponse.value) && !isGeneratingReport.value)

// ---- 消息过滤与映射 (报告流不显示) ----
const displayMessages = computed(() => messages.value.filter(m => {
  if (m.type === 'report') return false
  if (m.type === 'stream_start' && m.streamType === 'report') return false
  // 空的流式起始帧不显示气泡, 等第一个 chunk 到达再出现
  if (m.type === 'stream_start' && !(m.content || '').trim()) return false
  return ['opening', 'question', 'reaction', 'followup', 'closing', 'stream_start', 'user_answer', 'status', 'error', 'hint'].includes(m.type)
}).map(m => {
  const base = { msgType: m.type, streaming: m.type === 'stream_start', time: m._ts || '' }
  if (m.type === 'user_answer') return { ...base, side: 'user', displayText: m.content }
  if (m.type === 'status') return { ...base, side: 'system', displayText: m.content }
  if (m.type === 'error') return { ...base, side: 'system', displayText: `错误：${m.content}`, isError: true }
  if (m.type === 'hint') return { ...base, side: 'ai', hintLevel: m.hintLevel, content: m.content }
  return { ...base, side: 'ai', displayText: m.content || m.full || '', qIndex: m.questionIndex || 0, questionId: m.questionId || '' }
}))

// 最后一条 AI 消息的索引（用于 TTS 朗读指示器定位）
const lastAiIndex = computed(() => {
  const msgs = displayMessages.value
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i].side === 'ai') return i
  }
  return -1
})

function clockNow() {
  const d = new Date()
  return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0')
}
function pad2(n) { return String(n).padStart(2, '0') }

// 消息到达打时间戳 + 滚动到底 + 驱动状态机 (题号/结束/报告)
watch(messages, async () => {
  for (const m of messages.value) {
    if (!m._ts) m._ts = clockNow()
  }
  await nextTick()
  if (chatRef.value) chatRef.value.scrollTop = chatRef.value.scrollHeight

  for (let i = 0; i < messages.value.length; i++) {
    const m = messages.value[i]
    if (m.type === 'stream_start' && ['question', 'followup', 'closing'].includes(m.streamType)) {
      awaitingResponse.value = false
      if (m.streamType === 'question' && m.questionIndex) {
        questionNum.value = m.questionIndex
        if (m.totalCount) totalCount.value = m.totalCount
        hintCount.value = 0
      }
    }
    if (m.type === 'question' && m.questionIndex && !m._questionHandled) {
      m._questionHandled = true
      questionNum.value = m.questionIndex
      hintCount.value = 0
    }
    if (m.type === 'interview_ended' && !m._endHandled) {
      m._endHandled = true
      ended.value = true
      awaitingResponse.value = false
      answeredCount.value = Number(m.answeredCount || 0)
      if (m.totalCount) totalCount.value = Number(m.totalCount)
    }
    if (m.type === 'report_ready' && m.reportId && !m._reportHandled) {
      m._reportHandled = true
      isGeneratingReport.value = false
      sessionStorage.setItem('reportData', m.content || '')
      sessionStorage.setItem('reportId', m.reportId)
      sessionStorage.setItem('roleTitle', roleTitle.value)
      sessionStorage.setItem('answeredCount', String(answeredCount.value))
      sessionStorage.setItem('totalCount', String(totalCount.value))
      sessionStorage.setItem('elapsedTime', timerDisplay.value)
      router.push({ name: 'Summary', params: { reportId: m.reportId } })
      return
    }
    if (m.type === 'error' && !m._errorHandled) {
      m._errorHandled = true
      awaitingResponse.value = false
      isGeneratingReport.value = false
    }
  }
}, { deep: true })

// ---- 进入页面: 读取配置并连接 ----
onMounted(async () => {
  // v2.0: 统筹智能体交接的预填配置优先级最高 (AGENT_PLAN §7.3)
  const pendingRaw = sessionStorage.getItem('assistant_pending')
  if (pendingRaw) {
    sessionStorage.removeItem('assistant_pending')
    try {
      const p = JSON.parse(pendingRaw)
      roleTitle.value = p.role === 'llm_app' ? '大模型应用开发工程师' : (p.role || '模拟面试')
      totalCount.value = p.question_count || 5
      try {
        await connect(10000)
        awaitingResponse.value = true
        // 直接发原始 config 以携带 mode (sendConfig 不含 mode 参数)
        send({
          type: 'config',
          role: p.role || 'llm_app',
          question_count: p.question_count || 5,
          difficulty: p.difficulty || 2,
          mode: p.mode || 'standard',
          warmup_count: p.warmup_count || 0,
          jd_text: p.jd_text || '',
          resume_context: '',
          resume_skills: [],
        })
      } catch (_) {
        awaitingResponse.value = false
      }
      return
    } catch (_) { /* 预填损坏则回落到原有流程 */ }
  }
  // 优先本次会话选择(可能带简历上下文); 刷新/重进时回退到本地保存的上次配置
  let d = null
  const s = sessionStorage.getItem('selectedRole')
  if (s) { try { d = JSON.parse(s) } catch (_) { d = null } }
  if (!d) {
    const saved = localStorage.getItem('interviewConfig')
    if (saved) { try { d = JSON.parse(saved) } catch (_) { d = null } }
  }
  if (!d || !d.key) { router.push('/choose-job'); return }
  roleTitle.value = d.title || '模拟面试'
  totalCount.value = d.questionCount || 5
  try {
    await connect(10000)
    awaitingResponse.value = true
    sendConfig(d.key, d.questionCount || 5, 2, d.resumeContext || '', d.resumeSkills || [], d.applicationId || null, {
      mode: d.mode || 'standard',
      warmupCount: d.warmupCount || 0,
      jdText: d.jdText || '',
    })
  } catch (_) {
    awaitingResponse.value = false
  }
})
onUnmounted(() => close())

// ---- 作答台行为 ----
function sendAnswer() {
  if (!userInput.value.trim() || inputBusy.value) return
  const t = userInput.value.trim()
  userInput.value = ''
  messages.value.push({ type: 'user_answer', content: t })
  nextTick(autoResizeInput)
  if (wsSendAnswer(t)) awaitingResponse.value = true
}

function sendHint() {
  if (inputBusy.value || hintCount.value >= 2) return
  if (requestHint()) hintCount.value++
}

function endInterview() {
  if (confirm('确定要提前结束面试吗？')) {
    userInput.value = ''
    if (sendEnd()) {
      awaitingResponse.value = true
      toast('面试已结束，可以生成报告了')
    }
  }
}

function generateReport() {
  if (isGeneratingReport.value) return
  if (requestReport()) {
    isGeneratingReport.value = true
    toast('正在生成面试报告，请稍候…')
  }
}

function handleExit() {
  if (confirm('确定要退出面试吗？')) {
    close()
    router.push('/')
  }
}

// ---- 右侧控制台: 历史面试记录 ----
const records = ref([])
const recordsLoading = ref(false)
const recordDrawerOpen = ref(false)
const recordDrawerContent = ref('')
const recordDrawerTitle = ref('')

function formatRecDate(r) {
  const ts = r.timestamp
  const date = ts && ts.length >= 8
    ? `${ts.slice(0, 4)}-${ts.slice(4, 6)}-${ts.slice(6, 8)}`
    : ''
  const count = r.total_count ? `${r.total_count} 题` : '-'
  return date ? `${date} · ${count}` : count
}

async function refreshRecords() {
  recordsLoading.value = true
  try {
    const r = await listInterviewRecords()
    if (r.success) records.value = r.records || []
  } finally {
    recordsLoading.value = false
  }
}

async function openRecord(fn) {
  recordDrawerTitle.value = fn
  recordDrawerContent.value = '加载中…'
  recordDrawerOpen.value = true
  const r = await getInterviewRecord(fn)
  if (r.success) recordDrawerContent.value = r.content
  else recordDrawerContent.value = `加载失败: ${r.message}`
}

function closeRecordDrawer() {
  recordDrawerOpen.value = false
  recordDrawerContent.value = ''
  recordDrawerTitle.value = ''
}

async function deleteRecord(fn) {
  if (!confirm('确定删除这条记录吗？')) return
  const r = await deleteInterviewRecord(fn)
  if (r.success) {
    if (recordDrawerTitle.value === fn) closeRecordDrawer()
    toast('记录已删除')
    await refreshRecords()
  } else {
    toast(`删除失败: ${r.message}`, 'alert')
  }
}

onMounted(() => { refreshRecords() })
</script>

<style scoped>
/* ============ 暗房：局部令牌覆写 ============ */
.room {
  --paper: #191712;
  --ink: #EFE9DA;
  --ink-2: #C7C0B0;
  --ink-3: #A79F8B;
  --ink-4: #6F6857;
  --line: rgba(240, 234, 216, 0.13);
  --line-soft: rgba(240, 234, 216, 0.07);
  --line-strong: rgba(240, 234, 216, 0.34);
  --sheet: #211E17;
  --sheet-2: #26221A;
  --verm-wash: rgba(217, 58, 31, 0.14);
  --verm-line: rgba(217, 58, 31, 0.5);
  background: var(--room);
  color: var(--room-ink);
  min-height: 100vh;
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}
.room::before {
  content: '';
  position: absolute; inset: 0; pointer-events: none;
  background:
    radial-gradient(900px 460px at 50% -12%, rgba(240, 234, 216, 0.055), transparent 62%),
    radial-gradient(520px 380px at 104% 104%, rgba(217, 58, 31, 0.07), transparent 60%);
}

/* ── 顶栏 ── */
.room-top {
  position: relative;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 20px;
  padding: 14px clamp(16px, 3vw, 30px);
  border-bottom: 1px solid var(--line);
  background: rgba(25, 23, 18, 0.86);
  backdrop-filter: blur(8px);
  z-index: 20;
  flex-shrink: 0;
}
.room-left { display: flex; align-items: center; gap: 16px; min-width: 0; }
.room-exit {
  display: inline-flex; align-items: center; gap: 7px;
  font-size: 13px; color: var(--ink-3);
  padding: 7px 11px; border: 1px solid transparent;
  white-space: nowrap;
  transition: all var(--dur-1) ease;
}
.room-exit:hover { color: var(--room-ink); border-color: var(--line); }
.room-role { font-family: var(--f-display); font-weight: 900; font-size: 15px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.room-role small { font-family: var(--f-mono); font-size: 10px; letter-spacing: 0.16em; color: var(--ink-4); display: block; font-weight: 500; }

.room-progress { display: flex; flex-direction: column; align-items: center; gap: 9px; min-width: min(360px, 34vw); }
.room-progress .label { font-family: var(--f-mono); font-size: 10.5px; letter-spacing: 0.2em; text-transform: uppercase; color: var(--ink-3); }
.room-progress .label b { color: var(--room-ink); }
.ticks-line { width: 100%; }
.ticks-line i { background: rgba(240, 234, 216, 0.14); }
.ticks-line i.done { background: rgba(240, 234, 216, 0.62); }
.ticks-line i.now { background: var(--vermilion); }

.room-right { display: flex; align-items: center; justify-content: flex-end; gap: 12px; }
.tts-btn {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 7px 12px; font-size: 12px;
  border: 1px solid var(--line); color: var(--ink-3);
  transition: all var(--dur-1) ease;
}
.tts-icon-btn {
  width: 32px; height: 32px;
  display: inline-flex; align-items: center; justify-content: center;
  border: 1px solid var(--line); color: var(--ink-3);
  transition: all var(--dur-1) ease;
}
.tts-icon-btn:hover { color: var(--room-ink); border-color: var(--line-strong); }
.tts-btn:hover { color: var(--room-ink); border-color: var(--line-strong); }
.tts-btn.is-on { color: var(--vermilion); border-color: var(--verm-line); background: var(--verm-wash); }
.timer { font-family: var(--f-mono); font-weight: 700; font-size: 15px; letter-spacing: 0.04em; }

/* ── 主体 ── */
.room-body { position: relative; flex: 1; display: flex; min-height: 0; }

.transcript { flex: 1; overflow-y: auto; padding: clamp(24px, 4vh, 52px) clamp(20px, 4vw, 60px) 40px; scroll-behavior: smooth; }
.transcript-inner { max-width: 760px; margin: 0 auto; }

/* 消息 */
.msg { padding: 20px 0; border-bottom: 1px solid var(--line-soft); animation: msg-in 0.6s var(--ease) both; }
@keyframes msg-in { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: none; } }
.msg:last-child { border-bottom: 0; }
.msg-head { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.msg-who {
  font-family: var(--f-mono); font-size: 10px; font-weight: 700;
  letter-spacing: 0.2em; text-transform: uppercase; color: var(--vermilion);
  display: inline-flex; align-items: center; gap: 8px;
}
.msg-who::after { content: ''; width: 26px; height: 1px; background: var(--verm-line); }
.msg-time { font-family: var(--f-mono); font-size: 10px; color: var(--ink-4); letter-spacing: 0.1em; }
.msg-qid { font-family: var(--f-mono); font-size: 10px; color: var(--ink-4); margin-left: auto; letter-spacing: 0.08em; }

.msg-ai .msg-text { font-family: var(--f-display); font-weight: 700; font-size: 17.5px; line-height: 2; color: var(--room-ink); }
.msg-user .msg-head .msg-who { color: var(--indigo-ink); }
.msg-user .msg-head .msg-who::after { background: rgba(35, 64, 92, 0.6); }
.msg-user .msg-text {
  font-size: 15px; line-height: 2; color: var(--ink-2);
  padding-left: 18px; border-left: 2px solid var(--line-strong);
}

/* 反馈 / 追问 */
.msg-comment .msg-text {
  font-size: 14px; line-height: 1.95; color: var(--ink-3); font-style: italic;
  padding: 12px 18px; border-left: 2px solid var(--verm-line); background: rgba(240,234,216,.03);
}

/* 提示便签 */
.msg-hint .hint-card {
  border: 1px dashed var(--verm-line);
  background: rgba(217, 58, 31, 0.07);
  padding: 14px 18px;
  display: flex; gap: 12px; align-items: flex-start;
}
.msg-hint .ic { color: var(--vermilion); flex-shrink: 0; margin-top: 3px; }
.msg-hint .txt { font-size: 13.5px; line-height: 1.9; color: var(--ink-2); }
.msg-hint .txt b { color: var(--vermilion); font-family: var(--f-mono); font-size: 11px; letter-spacing: 0.1em; }

/* 系统状态 */
.msg-status { text-align: center; padding: 14px 0; }
.msg-status span { font-family: var(--f-mono); font-size: 11px; letter-spacing: 0.18em; text-transform: uppercase; color: var(--ink-4); }
.msg-status.is-error span { color: var(--vermilion); text-transform: none; letter-spacing: 0.06em; }

/* TTS 朗读指示器 */
.tts-indicator { display: inline-flex; align-items: center; margin-left: 6px; color: var(--vermilion); vertical-align: middle; animation: tts-pulse 1.2s ease-in-out infinite; }
@keyframes tts-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.35; } }

/* 思考中 */
.thinking { display: inline-flex; gap: 5px; align-items: center; padding: 6px 0; }
.thinking i { width: 6px; height: 6px; border-radius: 50%; background: var(--ink-3); animation: pulse 1.2s ease-in-out infinite; }
.thinking i:nth-child(2) { animation-delay: 0.18s; }
.thinking i:nth-child(3) { animation-delay: 0.36s; }

/* ── 右侧控制台 ── */
.console {
  width: 306px; flex-shrink: 0;
  border-left: 1px solid var(--line);
  background: rgba(33, 30, 23, 0.55);
  overflow-y: auto;
  padding: 22px;
  display: flex; flex-direction: column; gap: 18px;
}
.console .panel { border: 1px solid var(--line); background: rgba(240,234,216,.025); }
.console .panel-head {
  padding: 13px 16px; border-bottom: 1px solid var(--line);
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  font-family: var(--f-mono); font-size: 10px; letter-spacing: 0.2em; text-transform: uppercase; color: var(--ink-3);
}
.console .panel-body { padding: 14px 16px; }
.kv { display: flex; justify-content: space-between; gap: 12px; padding: 6px 0; font-size: 13px; }
.kv .k { color: var(--ink-4); }
.kv .v { color: var(--ink-2); font-family: var(--f-mono); font-size: 12.5px; }

.q-list li {
  display: flex; align-items: center; gap: 10px;
  padding: 7px 0; font-size: 13px; color: var(--ink-4);
  border-bottom: 1px dashed var(--line-soft);
}
.q-list li:last-child { border-bottom: 0; }
.q-list .qn { font-family: var(--f-mono); font-size: 11px; width: 30px; }
.q-list li.done { color: var(--ink-3); }
.q-list li.done .qn { color: var(--pine); }
.q-list li.now { color: var(--room-ink); font-weight: 600; }
.q-list li.now .qn { color: var(--vermilion); }
.q-list .state { margin-left: auto; font-family: var(--f-mono); font-size: 9.5px; letter-spacing: 0.12em; }

.rec-empty { font-size: 12px; color: var(--ink-4); padding: 6px 0; }
.rec-item { display: flex; align-items: center; gap: 8px; padding: 8px 0; border-bottom: 1px dashed var(--line-soft); }
.rec-item:last-child { border-bottom: 0; }
.rec-item .t { font-size: 12.5px; color: var(--ink-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rec-item .d { font-family: var(--f-mono); font-size: 10px; color: var(--ink-4); }
.rec-item .del { opacity: 0; color: var(--ink-4); transition: all var(--dur-1) ease; flex-shrink: 0; }
.rec-item:hover .del { opacity: 1; }
.rec-item .del:hover { color: var(--vermilion); }

.end-btn {
  width: 100%; padding: 11px; font-size: 13px;
  border: 1px solid rgba(217, 58, 31, 0.4); color: var(--vermilion);
  transition: all var(--dur-1) ease;
}
.end-btn:hover { background: var(--verm-wash); border-color: var(--vermilion); }

/* ── 作答台 ── */
.desk {
  position: relative;
  border-top: 1px solid var(--line);
  background: rgba(25, 23, 18, 0.92);
  backdrop-filter: blur(8px);
  padding: 16px clamp(16px, 3vw, 30px) 18px;
  flex-shrink: 0;
}
.desk-inner { max-width: 860px; margin: 0 auto; }
.desk-box {
  display: flex; gap: 12px; align-items: flex-end;
  border: 1px solid var(--line-strong);
  background: rgba(240, 234, 216, 0.035);
  padding: 12px 12px 12px 16px;
  transition: border-color var(--dur-2) ease, box-shadow var(--dur-2) ease;
}
.desk-box:focus-within { border-color: var(--vermilion); box-shadow: 0 0 0 3px rgba(217, 58, 31, 0.12); }
.desk textarea {
  flex: 1; resize: none; background: none; border: 0; outline: none;
  font-size: 14.5px; line-height: 1.85; color: var(--room-ink);
  min-height: 52px; max-height: 150px;
}
.desk textarea::placeholder { color: var(--ink-4); }
.desk-tools { display: flex; gap: 8px; align-items: center; }
.dbtn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 9px 11px; font-size: 12.5px;
  border: 1px solid var(--line); color: var(--ink-3);
  transition: all var(--dur-1) ease;
}
.dbtn:hover { color: var(--room-ink); border-color: var(--line-strong); }
.dbtn.is-live { color: var(--vermilion); border-color: var(--verm-line); background: var(--verm-wash); animation: pulse 1.4s ease-in-out infinite; }
.dbtn[disabled] { opacity: 0.4; pointer-events: none; }
.send-btn {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 10px 20px; font-size: 13.5px; font-weight: 600;
  background: var(--vermilion); color: #FFF6EE;
  transition: all var(--dur-2) var(--ease);
}
.send-btn:hover { background: #EF4B2C; transform: translateY(-1px); }
.send-btn[disabled] { opacity: 0.4; pointer-events: none; }
.desk-meta { display: flex; justify-content: space-between; gap: 12px; margin-top: 10px; }
.desk-meta span { font-family: var(--f-mono); font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink-4); }

/* ── 结束 / 生成报告 ── */
.finish { display: flex; align-items: center; justify-content: center; flex: 1; padding: 40px; }
.finish-card {
  max-width: 520px; width: 100%; text-align: center;
  border: 1px solid var(--line-strong);
  background: var(--sheet);
  padding: clamp(30px, 5vw, 52px);
  position: relative;
}
.finish-card .stamp { margin: 0 auto 22px; }
.finish-card h2 { font-size: 28px; margin-bottom: 12px; }
.finish-card .stats { display: flex; justify-content: center; gap: 34px; margin: 26px 0 30px; padding: 20px 0; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
.finish-card .stats .n { font-family: var(--f-mono); font-weight: 700; font-size: 26px; }
.finish-card .stats .l { font-size: 12px; color: var(--ink-3); margin-top: 4px; }

.gen-card { max-width: 520px; width: 100%; text-align: center; border: 1px solid var(--line-strong); background: var(--sheet); padding: clamp(30px, 5vw, 52px); }
.gen-card h2 { font-size: 24px; margin: 18px 0 10px; }
.gen-card p { color: var(--ink-3); font-size: 13.5px; }
.gen-log { margin-top: 24px; text-align: left; font-family: var(--f-mono); font-size: 11.5px; line-height: 2.1; color: var(--ink-4); }
.gen-log b { color: var(--vermilion); font-weight: 500; }

/* ── 面试记录抽屉（暗房风格，复用全局 .drawer/.mask） ── */
.room-drawer-head {
  padding: 20px 24px;
  border-bottom: 1px solid var(--line);
  display: flex; justify-content: space-between; align-items: flex-start; gap: 12px;
  flex-shrink: 0;
}
.room-drawer-title { font-family: var(--f-display); font-weight: 900; font-size: 18px; }
.room-drawer-sub {
  font-family: var(--f-mono); font-size: 11px; letter-spacing: 0.1em; color: var(--ink-3);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 44ch;
}
.room-drawer-close { color: var(--ink-3); transition: color var(--dur-1) ease; }
.room-drawer-close:hover { color: var(--room-ink); }
.room-drawer-body { flex: 1; overflow-y: auto; padding: 22px 26px; }
.room-md {
  margin: 0; font-family: var(--f-mono); font-size: 12.5px; line-height: 1.9;
  color: var(--ink-2); white-space: pre-wrap; word-break: break-word;
}

@media (max-width: 1080px) { .console { width: 252px; padding: 16px; } }
@media (max-width: 900px) { .console { display: none; } }
@media (max-width: 720px) {
  .room-top {
    grid-template-columns: 1fr auto;
    grid-template-areas: "left right" "prog prog";
    row-gap: 12px;
  }
  .room-left { grid-area: left; }
  .room-right { grid-area: right; }
  .room-progress { grid-area: prog; min-width: 0; width: 100%; }
  .transcript { padding: 20px 18px 30px; }
  .msg-ai .msg-text { font-size: 16px; }
  .desk-box { flex-wrap: wrap; }
  .desk textarea { min-height: 44px; width: 100%; flex: 1 1 100%; }
  .desk-tools { width: 100%; justify-content: flex-end; }
}
</style>
