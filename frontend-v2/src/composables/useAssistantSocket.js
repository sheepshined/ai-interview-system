import { ref, reactive, onUnmounted } from 'vue'
import { getToken } from '../auth'

export function useAssistantSocket() {
  const connected = ref(false)
  const messages = ref([])
  const pendingProposal = ref(null)
  const streaming = ref(false)
  const sending = ref(false)
  const sessionId = ref(null)
  const lastError = ref('')
  const onHandoff = ref(null)
  const onRestore = ref(null)
  let socket = null
  let connecting = null
  let current = null
  let request = null
  let generation = 0
  let reconnectTimer = null
  let reconnectAttempt = 0
  let stopped = false
  const handedOff = new Set()

  function pushAssistant() {
    current = reactive({ role: 'assistant', content: '', trace: [] })
    messages.value.push(current)
    return current
  }

  function finishRequest(ok) {
    if (!request) return
    clearTimeout(request.timer)
    const resolve = request.resolve
    request = null
    sending.value = false
    resolve(ok)
  }

  function handle(data) {
    switch (data.type) {
      case 'turn_start':
        sessionId.value = data.session_id
        streaming.value = true
        if (request?.text) messages.value.push({ role: 'user', content: request.text, trace: [] })
        finishRequest(true)
        current = null
        break
      case 'assistant_delta':
        if (!current) pushAssistant()
        current.content += data.text || ''
        break
      case 'tool_call':
        if (!current) pushAssistant()
        current.trace.push({ name: data.name, callId: data.call_id, ok: null, ms: 0 })
        break
      case 'tool_result': {
        if (!current) pushAssistant()
        let entry = current.trace.find((t) => t.callId === data.call_id)
        if (!entry) {
          entry = reactive({ name: data.name, callId: data.call_id })
          current.trace.push(entry)
        }
        entry.ok = data.ok
        entry.ms = data.ms
        if (data.skill) entry.skill = data.skill
        break
      }
      case 'proposal_asked':
        if (pendingProposal.value?.operation_id !== data.pending?.operation_id) {
          pendingProposal.value = data.pending
        }
        break
      case 'proposal_decided':
        if (pendingProposal.value?.operation_id === data.operation_id) pendingProposal.value = null
        break
      case 'handoff':
        if (!handedOff.has(data.operation_id)) {
          handedOff.add(data.operation_id)
          onHandoff.value?.(data.target, data.config)
        }
        break
      case 'memory_written':
        if (!current) pushAssistant()
        current.trace.push({ name: `remember #${data.id}`, callId: `mem${data.id}`, ok: true, ms: 0 })
        break
      case 'budget_exceeded':
        lastError.value = '本轮预算已用尽，助手正在整理已有信息。'
        break
      case 'error':
        lastError.value = data.message || '助手出错'
        finishRequest(false)
        break
      case 'turn_end':
        streaming.value = false
        current = null
        if (!data.awaiting_confirm) pendingProposal.value = null
        break
      default:
        break
    }
  }

  function connect() {
    if (connecting) return connecting
    if (socket?.readyState === WebSocket.OPEN) return Promise.resolve(true)
    if (!getToken()) return Promise.resolve(false)
    stopped = false
    clearTimeout(reconnectTimer)
    const version = ++generation
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const next = new WebSocket(`${protocol}//${window.location.host}/ws/assistant?token=${encodeURIComponent(getToken())}`)
    socket = next
    connecting = new Promise((resolve) => {
      let settled = false
      const settle = (ok) => {
        if (settled) return
        settled = true
        clearTimeout(timer)
        if (version === generation) connecting = null
        resolve(ok)
      }
      const timer = setTimeout(() => {
        if (version !== generation) return settle(false)
        lastError.value = '助手连接超时，请重试'
        settle(false)
        next.close()
      }, 10000)
      next.onopen = async () => {
        if (version !== generation) return settle(false)
        connected.value = true
        lastError.value = ''
        reconnectAttempt = 0
        try {
          await onRestore.value?.()
          settle(version === generation)
        } catch (_) {
          lastError.value = '会话恢复失败，请重新连接'
          settle(false)
          next.close()
        }
      }
      next.onerror = () => {
        if (version !== generation) return
        lastError.value = '助手服务连接异常'
        settle(false)
      }
      next.onclose = (event) => {
        settle(false)
        if (version !== generation) return
        connected.value = false
        streaming.value = false
        current = null
        finishRequest(false)
        if (!stopped && getToken() && event.code !== 4401) {
          const delay = Math.min(1000 * 2 ** reconnectAttempt++, 10000)
          reconnectTimer = setTimeout(connect, delay)
        }
      }
      next.onmessage = (event) => {
        if (version !== generation) return
        try { handle(JSON.parse(event.data)) } catch (_) { /* Ignore malformed frames. */ }
      }
    })
    return connecting
  }

  async function transmit(payload, text = '') {
    if (sending.value || streaming.value) return false
    sending.value = true
    lastError.value = ''
    if (!await connect() || socket?.readyState !== WebSocket.OPEN) {
      sending.value = false
      lastError.value ||= '未连接助手服务，请确认后端已启动并已登录'
      return false
    }
    if (streaming.value || (payload.type === 'user_message' && pendingProposal.value)) {
      sending.value = false
      lastError.value = '请先等待当前执行结束或处理待确认操作'
      return false
    }
    payload.session_id = sessionId.value
    return new Promise((resolve) => {
      request = { resolve, text, timer: setTimeout(() => {
        lastError.value = '未收到服务端确认，正在恢复会话；请检查历史后再重试'
        finishRequest(false)
        socket?.close()
      }, 15000) }
      try { socket.send(JSON.stringify(payload)) } catch (_) { finishRequest(false) }
    })
  }

  function send(text) { return transmit({ type: 'user_message', text }, text) }
  function sendDecision(operationId, action, args, reason) {
    return transmit({ type: 'proposal_decision', operation_id: operationId,
      action, args: args || {}, reason: reason || '' })
  }
  function interruptTurn() {
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'interrupt_turn' }))
  }
  function restore(detail) {
    current = null
    messages.value = (detail.messages || []).map((m) => ({
      role: m.role, content: m.content, trace: m.tool_trace || [],
    }))
    pendingProposal.value = detail.pending_action || null
    streaming.value = detail.phase === 'thinking'
  }
  function close() {
    stopped = true
    clearTimeout(reconnectTimer)
    ++generation
    socket?.close()
    socket = null
    connecting = null
    connected.value = false
    streaming.value = false
    finishRequest(false)
    current = null
  }
  function reset() {
    close()
    sessionId.value = null
    messages.value = []
    pendingProposal.value = null
    lastError.value = ''
    handedOff.clear()
  }
  onUnmounted(close)
  return { connected, messages, pendingProposal, streaming, sending, sessionId,
    lastError, onHandoff, onRestore, connect, ensureConnected: connect,
    send, sendDecision, interruptTurn, restore, close, reset }
}
