<template>
  <div v-if="authed">
    <button class="ad-fab" title="统筹助手" @click="open = !open">
      <Icon name="chat" />
    </button>

    <transition name="ad-slide">
      <aside v-if="open" class="ad-drawer">
        <header class="ad-head">
          <span class="ad-title">统筹助手</span>
          <span class="ad-state">{{ sock.streaming.value ? '思考中…' : (sock.connected.value ? '就绪' : '未连接') }}</span>
          <button class="ad-x" title="收起" @click="open = false"><Icon name="x" /></button>
        </header>

        <nav class="ad-tabs">
          <button v-for="t in tabs" :key="t.key" :class="{ on: tab === t.key }" @click="tab = t.key">{{ t.label }}</button>
        </nav>

        <MessageStream v-if="tab === 'chat'" :sock="sock" :send="onSend" />
        <MemoryPanel v-else-if="tab === 'memory'" :hist="hist" />
        <SessionList v-else-if="tab === 'sessions'" :hist="hist" :busy="busy" @pick="onPickSession" @removed="onRemoved" @error="sock.lastError.value = $event" />
        <AssistantSettings v-else :hist="hist" />

        <ProposalCard v-if="sock.pendingProposal.value" :pending="sock.pendingProposal.value" :busy="busy" @decide="onDecide" />
      </aside>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { getToken, getUsername } from '../../auth'
import Icon from '../Icon.vue'
import MessageStream from './MessageStream.vue'
import MemoryPanel from './MemoryPanel.vue'
import SessionList from './SessionList.vue'
import AssistantSettings from './AssistantSettings.vue'
import ProposalCard from './ProposalCard.vue'
import { useAssistantSocket } from '../../composables/useAssistantSocket'
import { useAssistantHistory } from '../../composables/useAssistantHistory'

const router = useRouter()
const route = useRoute()
// 鉴权门: 未登录时整个抽屉不渲染——登录页挂载抽屉会无条件拉需鉴权的 REST,
// 401 会让 api 层清登录态跳回 /login, 形成重定向死循环 (页面持续闪烁)
const authed = ref(!!getToken())
watch(() => route.fullPath, () => { authed.value = !!getToken() })
const open = ref(false)
const tab = ref('chat')
const tabs = [
  { key: 'chat', label: '对话' },
  { key: 'memory', label: '记忆' },
  { key: 'sessions', label: '会话' },
  { key: 'settings', label: '设置' },
]

const sock = useAssistantSocket()
const hist = useAssistantHistory()
const busy = computed(() => sock.streaming.value || sock.sending.value)
let owner = getUsername()
let restoreVersion = 0
let restoreTimer = null
const selectionKey = (username) => `assistant_session:${username}`

// Register independently of initial authentication: App survives login.
sock.onHandoff.value = (target, cfg) => {
    if (target === 'interview') {
      sessionStorage.setItem('assistant_pending', JSON.stringify(cfg))
      router.push('/interview')
    } else if (target === 'kb_session') {
      sessionStorage.setItem('assistant_kb_question', cfg.question || '')
      router.push('/knowledge/chat')
    }
  open.value = false
}

watch(sock.sessionId, (id) => {
  if (!owner) return
  if (id) localStorage.setItem(selectionKey(owner), String(id))
  else localStorage.removeItem(selectionKey(owner))
})

async function restoreSession(id = sock.sessionId.value) {
  clearTimeout(restoreTimer)
  const version = ++restoreVersion
  if (!id) { sock.restore({}); return }
  const detail = await hist.loadSession(id)
  if (version !== restoreVersion || !authed.value) return
  if (!detail.success) {
    if (detail.status === 404) {
      sock.sessionId.value = null
      sock.restore({})
      return
    }
    throw new Error(detail.message || '会话恢复失败')
  }
  sock.restore(detail)
  if (detail.phase === 'thinking') {
    restoreTimer = setTimeout(() => restoreSession(id).catch((error) => {
      sock.lastError.value = error.message
    }), 500)
  }
}

sock.onRestore.value = async () => {
  await restoreSession()
  await hist.loadSessions()
}

async function activate() {
  owner = getUsername()
  const saved = Number(localStorage.getItem(selectionKey(owner)))
  sock.sessionId.value = Number.isInteger(saved) && saved > 0 ? saved : null
  await sock.connect()
  hist.loadSettings()
}

onMounted(() => { if (authed.value) activate() })

// 抽屉每次打开都补一次连接: 解决"登录页首次连接被 403 后再不重连"
watch(open, async (isOpen) => {
  if (isOpen && authed.value) {
    await sock.ensureConnected()
    hist.loadSessions()
  }
})

// 登录后首次进入应用页时补一次连接与数据 (App 不重挂, onMounted 不会再跑)
watch(authed, async (ok) => {
  if (ok) {
    await activate()
  } else {
    clearTimeout(restoreTimer)
    ++restoreVersion
    if (owner) localStorage.removeItem(selectionKey(owner))
    open.value = false
    sock.reset()
    hist.sessions.value = []
    hist.memories.value = []
    hist.settings.value = { auto_accept_level: 'read_auto', memory_enabled: true }
    sessionStorage.removeItem('assistant_pending')
    sessionStorage.removeItem('assistant_kb_question')
    owner = ''
  }
})

function onSend(text) { return sock.send(text) }

async function onPickSession(id) {
  if (busy.value) return
  sock.sessionId.value = id
  sock.restore({})
  try {
    await restoreSession(id)
    tab.value = 'chat'
  } catch (error) { sock.lastError.value = error.message }
}

function onRemoved(id) {
  if (sock.sessionId.value !== id) return
  ++restoreVersion
  clearTimeout(restoreTimer)
  sock.sessionId.value = null
  sock.restore({})
}

function onDecide({ action, args, reason }) {
  const pending = sock.pendingProposal.value
  if (!pending) return
  sock.sendDecision(pending.operation_id, action, args, reason)
}

onUnmounted(() => { ++restoreVersion; clearTimeout(restoreTimer) })
</script>

<style scoped>
.ad-fab {
  position: fixed; right: 22px; bottom: 22px; z-index: 60;
  width: 46px; height: 46px; border-radius: var(--r-pill);
  border: 1px solid var(--line-strong); background: var(--ink); color: var(--paper);
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  box-shadow: var(--sh-lift);
}
.ad-fab :deep(svg) { width: 19px; height: 19px; }
.ad-drawer {
  position: fixed; right: 0; top: 0; bottom: 0; z-index: 70;
  width: 420px; max-width: 92vw; display: flex; flex-direction: column;
  background: var(--sheet); border-left: 1px solid var(--line);
  box-shadow: var(--sh-lift);
}
.ad-head { display: flex; align-items: center; gap: 8px; padding: 12px 14px; border-bottom: 1px solid var(--line); }
.ad-title { font-family: var(--f-display); font-weight: 700; font-size: 15px; color: var(--ink); }
.ad-state { font-size: 11px; color: var(--ink-3); flex: 1; }
.ad-x { border: none; background: transparent; color: var(--ink-3); cursor: pointer; padding: 4px; display: flex; }
.ad-x :deep(svg) { width: 15px; height: 15px; }
.ad-tabs { display: flex; gap: 4px; padding: 8px 10px; border-bottom: 1px solid var(--line-soft); }
.ad-tabs button {
  border: none; background: transparent; color: var(--ink-2);
  font-size: 12px; padding: 5px 10px; border-radius: var(--r-1); cursor: pointer;
}
.ad-tabs button.on { background: var(--verm-wash); color: var(--vermilion-deep); font-weight: 600; }
.ad-slide-enter-active, .ad-slide-leave-active { transition: transform var(--dur-2) var(--ease); }
.ad-slide-enter-from, .ad-slide-leave-to { transform: translateX(100%); }
</style>
