import { ref, computed, onUnmounted, reactive } from 'vue'
import { getToken } from '../auth'

export function useWebSocket() {
  const ws = ref(null)
  const connected = ref(false)
  const messages = ref([])
  const connectionError = ref('')
  const streaming = ref(false)
  const threadId = ref('')
  let activeStream = null
  let revealTimer = null

  // 打字机逐字释放：chunk 先进 pending 缓冲区，定时器按节奏搬到 content。
  // 积压越多每次吐得越多，保证长文本不会明显拖慢。
  // ---- TTS 语音朗读 (浏览器原生 SpeechSynthesis, 零成本) ----
  // 朗读面试官的发言(opening/question/followup/closing), 在打字机吐完字后触发。
  // 用户可通过 ttsEnabled 开关控制; STT(语音输入)开始时自动停止朗读。
  const ttsEnabled = ref(true)   // 默认开启, 演示效果佳
  const ttsSpeaking = ref(false)
  const ttsPaused = ref(false)
  const _speakableTypes = new Set(['opening', 'question', 'followup', 'closing'])

  function _speakText(text) {
    if (!ttsEnabled.value) return
    if (typeof window === 'undefined' || !window.speechSynthesis) return
    if (!text || !text.trim()) return
    try {
      // 停止之前可能残留的朗读
      window.speechSynthesis.cancel()
      const utterance = new SpeechSynthesisUtterance(text)
      utterance.lang = 'zh-CN'
      utterance.rate = 0.92   // 稍慢, 更像真人面试官
      utterance.pitch = 1.0
      utterance.volume = 1.0
      utterance.onstart = () => { ttsSpeaking.value = true }
      utterance.onend = () => { ttsSpeaking.value = false; ttsPaused.value = false }
      utterance.onerror = () => { ttsSpeaking.value = false; ttsPaused.value = false }
      window.speechSynthesis.speak(utterance)
    } catch (_) {
      ttsSpeaking.value = false
    }
  }

  function stopTts() {
    if (typeof window !== 'undefined' && window.speechSynthesis) {
      window.speechSynthesis.cancel()
    }
    ttsSpeaking.value = false
    ttsPaused.value = false
  }

  function toggleTtsPause() {
    if (typeof window === 'undefined' || !window.speechSynthesis || !ttsSpeaking.value) return
    if (ttsPaused.value) {
      window.speechSynthesis.resume()
      ttsPaused.value = false
    } else {
      window.speechSynthesis.pause()
      ttsPaused.value = true
    }
  }

  function skipTts() {
    stopTts()
  }

  function toggleTts() {
    ttsEnabled.value = !ttsEnabled.value
    if (!ttsEnabled.value) stopTts()
  }

  const REVEAL_INTERVAL_MS = 24
  function _revealTick() {
    if (!activeStream) { _stopReveal(); return }
    const pending = activeStream.pending || ''
    if (!pending) {
      if (activeStream.ended) _finalizeStream()
      return
    }
    const n = pending.length > 80 ? 6 : pending.length > 30 ? 3 : 1
    activeStream.content += pending.slice(0, n)
    activeStream.pending = pending.slice(n)
  }
  function _startReveal() {
    if (revealTimer) return
    revealTimer = window.setInterval(_revealTick, REVEAL_INTERVAL_MS)
  }
  function _stopReveal() {
    if (revealTimer) { window.clearInterval(revealTimer); revealTimer = null }
  }
  // 流结束后等 pending 吐完才收尾：置最终文本、解除 streaming（输入解锁）
  // 收尾后若为面试官发言(opening/question/followup/closing), 触发 TTS 朗读
  function _finalizeStream() {
    if (!activeStream) return
    activeStream.type = activeStream.endType || activeStream.streamType
    activeStream.content = activeStream.full ?? activeStream.content
    if (activeStream.endReportId) activeStream.reportId = activeStream.endReportId
    // TTS: 捕获朗读内容后再清空 activeStream
    const _ttsType = activeStream.streamType
    const _ttsContent = activeStream.content || ''
    activeStream = null
    streaming.value = false
    _stopReveal()
    // 朗读面试官发言(打字机吐完后异步朗读, 不阻塞 UI)
    if (_speakableTypes.has(_ttsType) && _ttsContent) {
      _speakText(_ttsContent)
    }
  }
  // 新流到来时若上一段还没吐完，立即补全上一段，避免互相覆盖
  function _flushStream() {
    if (!activeStream) return
    _finalizeStream()
  }

  function connect(timeoutMs = 10000) {
    if (ws.value && ws.value.readyState === WebSocket.OPEN) {
      return Promise.resolve()
    }
    connectionError.value = ''
    return new Promise((resolve, reject) => {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      // 握手鉴权: 后端要求 ?token=<jwt>, 无效 token 会拒绝握手
      const token = getToken()
      const qs = token ? `?token=${encodeURIComponent(token)}` : ''
      const socket = new WebSocket(`${protocol}//${window.location.host}/ws/chat${qs}`)
      ws.value = socket
      let settled = false
      const timer = window.setTimeout(() => {
        if (settled) return
        settled = true
        connectionError.value = '连接面试服务超时，请确认后端已启动'
        socket.close()
        reject(new Error(connectionError.value))
      }, timeoutMs)

      socket.onopen = () => {
        window.clearTimeout(timer)
        connected.value = true
        if (!settled) {
          settled = true
          resolve()
        }
      }
      socket.onclose = () => {
        window.clearTimeout(timer)
        connected.value = false
        streaming.value = false
        stopTts()
        _stopReveal()
        activeStream = null
        if (!settled) {
          settled = true
          connectionError.value = '无法连接面试服务，请确认后端已启动'
          reject(new Error(connectionError.value))
        }
      }
      socket.onerror = () => {
        connectionError.value = '面试服务连接异常'
      }
      socket.onmessage = (event) => {
        let data
        try {
          data = JSON.parse(event.data)
        } catch (_) {
          messages.value.push({ type: 'error', content: '收到无法解析的服务端消息' })
          return
        }

        if (data.type === 'stream_start') {
          _flushStream()
          activeStream = reactive({
            type: 'stream_start',
            streamType: data.stream_type,
            content: '',
            full: '',
            pending: '',
            ended: false,
            questionId: data.question_id || '',
            questionIndex: data.question_index || 0,
            totalCount: data.total_count || 0,
          })
          messages.value.push(activeStream)
          streaming.value = true
          // 报告流不走打字机（不在聊天区展示），直接透传
          if (data.stream_type === 'report') activeStream.instant = true
          if (!activeStream.instant) _startReveal()
        } else if (data.type === 'stream_chunk') {
          if (activeStream) {
            if (activeStream.instant) {
              activeStream.content += data.content || ''
            } else {
              activeStream.pending += data.content || ''
            }
          }
        } else if (data.type === 'stream_end') {
          if (activeStream) {
            activeStream.endType = data.stream_type || activeStream.streamType
            activeStream.full = data.full_text ?? (activeStream.content + (activeStream.pending || ''))
            activeStream.endReportId = data.report_id || ''
            if (activeStream.instant || !(activeStream.pending || '')) {
              _finalizeStream()
            } else {
              // 还有未吐完的字，交给定时器收尾
              activeStream.ended = true
            }
          } else {
            streaming.value = false
          }
        } else if (data.type === 'config_ok') {
          threadId.value = data.thread_id || ''
          messages.value.push({ type: 'config_ok', data })
        } else if (data.type === 'decision') {
          messages.value.push({ type: 'decision', data })
        } else if (data.type === 'interview_ended') {
          messages.value.push({
            type: 'interview_ended',
            content: data.content,
            canReport: data.can_report,
            answeredCount: data.answered_count ?? 0,
            totalCount: data.total_count ?? 0,
          })
        } else if (data.type === 'report_ready') {
          messages.value.push({
            type: 'report_ready',
            reportId: data.report_id,
            content: data.content || '',
          })
        } else if (data.type === 'hint') {
          messages.value.push({
            type: 'hint',
            content: data.content || '',
            hintLevel: data.hint_level || 0,
            questionId: data.question_id || '',
          })
        } else if (data.type === 'status') {
          messages.value.push({ type: 'status', content: data.content })
        } else if (data.type === 'error') {
          streaming.value = false
          _stopReveal()
          activeStream = null
          messages.value.push({ type: 'error', content: data.content })
        }
      }
    })
  }

  function send(data) {
    if (!ws.value || ws.value.readyState !== WebSocket.OPEN) return false
    ws.value.send(JSON.stringify(data))
    return true
  }

  function sendConfig(role, questionCount, difficulty, resumeContext, resumeSkills, applicationId = null, options = {}) {
    return send({
      type: 'config',
      role,
      question_count: questionCount,
      difficulty,
      resume_context: resumeContext || '',
      resume_skills: resumeSkills || [],
      application_id: applicationId,
      mode: options.mode || 'standard',
      warmup_count: options.warmupCount || 0,
      jd_text: options.jdText || '',
    })
  }
  function sendAnswer(content) { return send({ type: 'answer', content }) }
  function sendEnd() { return send({ type: 'end' }) }
  function requestReport() { return send({ type: 'report' }) }
  function requestHint() { return send({ type: 'hint' }) }
  function close() {
    stopTts()
    if (ws.value) ws.value.close()
    ws.value = null
  }
  function clearMessages() { messages.value = [] }

  const isStreaming = computed(() => streaming.value)
  onUnmounted(close)
  return {
    ws,
    connected,
    connectionError,
    threadId,
    messages,
    isStreaming,
    ttsEnabled,
    ttsSpeaking,
    ttsPaused,
    connect,
    send,
    sendConfig,
    sendAnswer,
    sendEnd,
    requestReport,
    requestHint,
    close,
    clearMessages,
    toggleTts,
    toggleTtsPause,
    skipTts,
    stopTts,
  }
}
