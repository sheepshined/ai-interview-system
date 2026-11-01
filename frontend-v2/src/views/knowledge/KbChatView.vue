<template>
  <div>
    <TopBar crumb="AI 对话" folio="卷·07">
      <template #actions>
        <span class="mono">基于你的知识库回答 · 附来源</span>
      </template>
    </TopBar>

    <div class="page-body">
      <div class="chat-layout">
        <!-- 会话列表 -->
        <aside class="sessions" v-reveal>
          <div class="sessions-head">
            <span class="t">Conversations · {{ sessions.length }}</span>
            <button class="btn btn-sm btn-block" @click="createAndSwitch">
              <Icon name="plus" :size="14" />新对话
            </button>
          </div>
          <div class="sess-list">
            <button
              v-for="s in sessions"
              :key="s.id"
              class="sess"
              :class="{ 'is-on': currentId === s.id }"
              @click="switchTo(s.id)"
            >
              <span class="body">
                <span class="t" @dblclick.stop="renameSess(s)">{{ s.title || '新对话' }}</span>
                <span class="d">{{ fmtTime(s.updated_at) }}{{ s.message_count ? ` · ${s.message_count} 条消息` : '' }}</span>
              </span>
              <span class="del" title="重命名" @click.stop="renameSess(s)"><Icon name="edit" :size="13" /></span>
              <span class="del" title="删除" @click.stop="deleteSess(s.id)"><Icon name="trash" :size="13" /></span>
            </button>
            <div v-if="loadingSessions" class="sess-empty">正在读取会话…</div>
            <div v-else-if="sessionsError" class="sess-empty sess-err">
              <span><Icon name="alert" :size="13" />{{ sessionsError }}</span>
              <button class="sess-retry" @click="loadSessions">重试</button>
            </div>
            <div v-else-if="!sessions.length" class="sess-empty">还没有对话</div>
          </div>
        </aside>

        <!-- 聊天区 -->
        <section class="chat" v-reveal="0.06">
          <template v-if="currentId">
            <div class="chat-head">
              <div>
                <div class="title" title="双击可重命名" @dblclick="renameCurrent">{{ currentSession?.title || '新对话' }}</div>
                <div class="sub">{{ headSub }}</div>
              </div>
              <button class="icon-btn" title="重命名" @click="renameCurrent"><Icon name="edit" /></button>
            </div>

            <div ref="chatBody" class="chat-body">
              <!-- 会话历史加载中 -->
              <div v-if="loadingHistory" class="chat-state">
                <span class="spin" style="display:inline-block;width:18px;height:18px;border:2px solid var(--line-strong);border-top-color:var(--vermilion);border-radius:50%"></span>
                正在调取对话记录…
              </div>

              <!-- 会话历史加载失败 -->
              <div v-else-if="historyError" class="chat-state chat-err">
                <span><Icon name="alert" :size="15" />{{ historyError }}</span>
                <button class="btn btn-ghost btn-sm" @click="loadHistory(currentId)"><Icon name="refresh" :size="14" />重新加载</button>
              </div>

              <!-- 空会话 -->
              <div v-else-if="!messages.length && !loading" class="chat-empty">
                <div class="empty-ic" style="margin-bottom:6px"><Icon name="book" :size="30" /></div>
                <div class="empty-title">开始向你的知识库提问吧</div>
                <div class="suggests">
                  <button v-for="s in suggestions" :key="s" class="suggest" @click="send(s)">{{ s }}</button>
                </div>
              </div>

              <template v-else>
                <div v-for="(msg, i) in messages" :key="i">
                  <!-- 用户 -->
                  <div v-if="msg.role === 'user'" class="turn turn-user">
                    <div class="bubble">
                      <div class="who">我</div>
                      {{ msg.content }}
                    </div>
                  </div>

                  <!-- 助手 -->
                  <div v-else class="turn turn-ai">
                    <div class="who-row">
                      <span class="who">知识库助手</span>
                      <span class="time">{{ msg.created_at ? fmtTime(msg.created_at) : '刚刚' }}</span>
                    </div>
                    <div class="answer">
                      <div class="md" v-html="renderMarkdown(msg.content)"></div>

                      <div v-if="msg.sources && msg.sources.length" class="sources">
                        <div class="st"><Icon name="book" :size="12" />参考来源 · {{ msg.sources.length }}</div>
                        <a
                          v-for="(src, si) in msg.sources"
                          :key="si"
                          class="source-row"
                          href="#"
                          @click.prevent="goNote(src.note_id)"
                        >
                          <span class="no">{{ si + 1 }}</span>
                          <span class="name">{{ src.title }}</span>
                          <span class="bar"><i :style="{ width: srcPct(src) + '%' }"></i></span>
                          <span class="pct">{{ srcPct(src) }}%</span>
                        </a>
                      </div>

                      <div v-if="msg.sparse" class="sparse">
                        <Icon name="alert" :size="13" />
                        <span>相关度不高，可能需要补充更多资料</span>
                        <RouterLink to="/knowledge" class="sparse-link">去导入 →</RouterLink>
                      </div>
                    </div>
                  </div>
                </div>

                <!-- 思考中 -->
                <div v-if="loading" class="turn turn-ai">
                  <div class="who-row"><span class="who">知识库助手</span><span class="time">刚刚</span></div>
                  <div class="thinking"><i></i><i></i><i></i></div>
                </div>
              </template>
            </div>

            <!-- 输入台 -->
            <div class="composer">
              <div class="box">
                <textarea
                  ref="taEl"
                  v-model="input"
                  rows="1"
                  placeholder="输入你的问题，比如：注意力机制和 self-attention 有什么区别？"
                  @input="autoGrow"
                  @keydown.enter.exact.prevent="send()"
                ></textarea>
                <button class="send" :disabled="loading || !input.trim()" title="发送" @click="send()">
                  <Icon name="arrowRight" :size="18" />
                </button>
              </div>
              <div class="foot">
                <span>Enter 发送 · 回答仅基于你的知识库</span>
                <span>检索知识库 · Top 5</span>
              </div>
            </div>
          </template>

          <!-- 未选中会话 -->
          <div v-else class="unselected">
            <div class="empty-ic" style="margin-bottom:4px"><Icon name="chat" :size="34" /></div>
            <div class="empty-title">欢迎使用知识库 AI 对话</div>
            <div class="empty-sub">基于你的笔记和资料提问，AI 会检索知识库内容回答并标注来源。</div>
            <div class="suggests">
              <button v-for="s in suggestions" :key="s" class="suggest" @click="startWith(s)">{{ s }}</button>
            </div>
            <button class="btn" style="margin-top:10px" @click="createAndSwitch">
              <Icon name="plus" :size="16" />开始新对话
            </button>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import TopBar from '../../components/TopBar.vue'
import Icon from '../../components/Icon.vue'
import { renderMarkdown } from '../../utils/markdown'
import 'katex/dist/katex.min.css'   // markdown.js 渲染 $/$$ 公式所需的样式
import {
  kbQa, kbChatListSessions, kbChatCreateSession,
  kbChatGetSession, kbChatDeleteSession, kbChatRenameSession,
} from '../../api'
import { toast } from '../../composables/useToast'

const router = useRouter()

const sessions = ref([])
const currentId = ref(null)
const messages = ref([])
const input = ref('')
const loading = ref(false)
const loadingSessions = ref(false)
const loadingHistory = ref(false)
const sessionsError = ref('')
const historyError = ref('')
const chatBody = ref(null)
const taEl = ref(null)

const suggestions = [
  '注意力机制和 self-attention 有什么区别？',
  'Transformer 的核心架构是什么？',
  'RAG 的检索增强生成流程是怎样的？',
]

const currentSession = computed(() => sessions.value.find(s => s.id === currentId.value) || null)

const headSub = computed(() => {
  const withSources = [...messages.value].reverse()
    .find(m => m.role === 'assistant' && m.sources && m.sources.length)
  return withSources
    ? `检索知识库 · 命中 ${withSources.sources.length} 条来源`
    : '检索知识库 · Top 5'
})

function fmtTime(iso) {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    const diff = (Date.now() - d.getTime()) / 1000
    if (diff < 60) return '刚刚'
    if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
    if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
    if (diff < 86400 * 2) return '昨天'
    if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} 天前`
    return d.toLocaleDateString()
  } catch (_) { return iso }
}

function srcPct(src) {
  return Math.round((Number(src?.score) || 0) * 100)
}

function goNote(id) {
  if (id) router.push(`/knowledge/note/${id}`)
  else toast('该来源没有关联笔记', 'alert')
}

async function scrollBottom() {
  await nextTick()
  if (chatBody.value) chatBody.value.scrollTop = chatBody.value.scrollHeight
}

function autoGrow() {
  const el = taEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 140) + 'px'
}

async function loadSessions() {
  loadingSessions.value = true
  sessionsError.value = ''
  try {
    const r = await kbChatListSessions()
    if (r.success) sessions.value = r.sessions || []
    else sessionsError.value = r.message || '会话列表加载失败'
  } catch (_) {
    sessionsError.value = '无法连接后端服务'
  } finally {
    loadingSessions.value = false
  }
}

async function loadHistory(id) {
  messages.value = []
  loadingHistory.value = true
  historyError.value = ''
  try {
    const r = await kbChatGetSession(id)
    if (r.success) messages.value = r.messages || []
    else historyError.value = r.error || r.message || '会话加载失败'
  } catch (_) {
    historyError.value = '会话加载失败'
  } finally {
    loadingHistory.value = false
    await scrollBottom()
  }
}

async function switchTo(id) {
  if (currentId.value === id) return
  currentId.value = id
  await loadHistory(id)
}

async function createAndSwitch() {
  const r = await kbChatCreateSession()
  if (r.success) {
    sessions.value.unshift(r.session)
    await switchTo(r.session.id)
  } else {
    toast(r.message || '新建对话失败', 'alert')
  }
}

async function startWith(q) {
  await createAndSwitch()
  if (currentId.value) await send(q)
}

async function deleteSess(id) {
  if (!confirm('确定删除这个对话吗？')) return
  const r = await kbChatDeleteSession(id)
  if (r.success) {
    sessions.value = sessions.value.filter(s => s.id !== id)
    if (currentId.value === id) {
      currentId.value = null
      messages.value = []
    }
    toast('已删除该对话', 'trash')
  } else {
    toast(r.error || r.message || '删除失败', 'alert')
  }
}

async function renameSess(s) {
  const title = prompt('重命名对话', s.title || '新对话')
  if (title == null) return
  const t = title.trim()
  if (!t) { toast('标题不能为空', 'alert'); return }
  const r = await kbChatRenameSession(s.id, t)
  if (r.success) { s.title = t; toast('已重命名', 'edit') }
  else toast(r.error || r.message || '重命名失败', 'alert')
}

function renameCurrent() {
  if (currentSession.value) renameSess(currentSession.value)
}

async function send(question) {
  const q = ((typeof question === 'string' ? question : input.value) || '').trim()
  if (!q || loading.value) return
  if (!currentId.value) await createAndSwitch()
  if (!currentId.value) return

  input.value = ''
  await nextTick()
  autoGrow()
  messages.value.push({ role: 'user', content: q })
  loading.value = true
  await scrollBottom()

  try {
    const r = await kbQa(q, 5, currentId.value)
    if (r.success) {
      if (r.session_id && !currentId.value) {
        currentId.value = r.session_id
        await loadSessions()
      }
      messages.value.push({
        role: 'assistant',
        content: r.answer,
        sources: r.sources || [],
        sparse: r.sparse,
        created_at: new Date().toISOString(),
      })
      // 标题可能被后端自动生成，刷新会话列表
      await loadSessions()
    } else {
      const msg = r.error || r.message || '请求失败'
      messages.value.push({ role: 'assistant', content: msg })
      toast(msg, 'alert')
    }
  } catch (_) {
    messages.value.push({ role: 'assistant', content: '网络错误，请稍后重试' })
    toast('网络错误，请稍后重试', 'alert')
  } finally {
    loading.value = false
    await scrollBottom()
  }
}

onMounted(async () => {
  await loadSessions()
  if (sessions.value.length) await switchTo(sessions.value[0].id)
  // v2.0: 统筹智能体交接预填 (AGENT_PLAN §7.3) — 只填输入框, 不自动发送
  const pendingQ = sessionStorage.getItem('assistant_kb_question')
  if (pendingQ) {
    sessionStorage.removeItem('assistant_kb_question')
    input.value = pendingQ
    await nextTick()
  }
})
</script>

<style scoped>
  .chat-layout { display: grid; grid-template-columns: 286px 1fr; gap: 24px; align-items: stretch; height: calc(100vh - 150px); min-height: 540px; }

  /* ── 会话列表 ── */
  .sessions { border: 1px solid var(--line); background: var(--sheet); display: flex; flex-direction: column; min-height: 0; }
  .sessions-head { padding: 16px; border-bottom: 1px solid var(--line-strong); }
  .sessions-head .t { font-family: var(--f-mono); font-size: 10.5px; letter-spacing: 0.2em; text-transform: uppercase; color: var(--ink-3); margin-bottom: 12px; display: block; }
  .sess-list { flex: 1; overflow-y: auto; }
  .sess {
    position: relative; width: 100%; text-align: left; cursor: pointer;
    padding: 14px 16px; border-bottom: 1px solid var(--line);
    display: flex; align-items: center; gap: 10px;
    transition: background var(--dur-1) ease, padding-left var(--dur-2) var(--ease);
  }
  .sess:hover { background: var(--sheet-2); padding-left: 20px; }
  .sess.is-on { background: var(--sheet-2); }
  .sess.is-on::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--vermilion); }
  .sess .body { min-width: 0; flex: 1; }
  .sess .t { font-size: 13.5px; font-weight: 600; color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: block; }
  .sess .d { font-family: var(--f-mono); font-size: 10px; color: var(--ink-4); margin-top: 3px; letter-spacing: 0.06em; display: block; }
  .sess .del { opacity: 0; color: var(--ink-4); transition: all var(--dur-1) ease; flex-shrink: 0; display: inline-flex; }
  .sess:hover .del { opacity: 1; }
  .sess .del:hover { color: var(--vermilion); }
  .sess-empty { text-align: center; color: var(--ink-4); font-size: 12px; padding: 26px 12px; }
  .sess-err { display: flex; flex-direction: column; align-items: center; gap: 10px; color: var(--vermilion-deep); }
  .sess-err > span { display: inline-flex; align-items: center; gap: 6px; }
  .sess-retry { font-family: var(--f-mono); font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--ink-2); border-bottom: 1px solid var(--line-strong); }
  .sess-retry:hover { color: var(--vermilion); border-color: var(--vermilion); }

  /* ── 聊天区 ── */
  .chat { border: 1px solid var(--line); background: var(--sheet); display: flex; flex-direction: column; min-width: 0; min-height: 0; }
  .chat-head {
    display: flex; align-items: center; justify-content: space-between; gap: 14px;
    padding: 16px 26px; border-bottom: 1px solid var(--line-strong);
  }
  .chat-head .title { font-family: var(--f-display); font-weight: 900; font-size: 16px; cursor: text; }
  .chat-head .sub { font-family: var(--f-mono); font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink-4); margin-top: 3px; }
  .chat-body { flex: 1; min-height: 0; overflow-y: auto; padding: 30px clamp(20px, 3vw, 44px); display: flex; flex-direction: column; }

  .chat-state { flex: 1; display: flex; align-items: center; justify-content: center; gap: 10px; color: var(--ink-3); font-size: 13.5px; }
  .chat-err { flex-direction: column; color: var(--vermilion-deep); }
  .chat-err > span { display: inline-flex; align-items: center; gap: 9px; }

  .turn { margin-bottom: 34px; }
  .turn-user { display: flex; justify-content: flex-end; }
  .turn-user .bubble {
    max-width: 76%; padding: 14px 18px;
    background: var(--ink); color: var(--paper);
    font-size: 14px; line-height: 1.85;
    white-space: pre-wrap; overflow-wrap: anywhere;
  }
  .turn-user .who { font-family: var(--f-mono); font-size: 9.5px; letter-spacing: 0.2em; text-transform: uppercase; color: rgba(240,234,216,.5); margin-bottom: 6px; }

  .turn-ai .who-row { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
  .turn-ai .who { font-family: var(--f-mono); font-size: 10px; font-weight: 700; letter-spacing: 0.2em; text-transform: uppercase; color: var(--vermilion); }
  .turn-ai .who::after { content: ''; display: inline-block; width: 22px; height: 1px; background: var(--verm-line); margin-left: 10px; vertical-align: middle; }
  .turn-ai .time { font-family: var(--f-mono); font-size: 10px; color: var(--ink-4); }
  .turn-ai .answer { padding-left: 18px; border-left: 2px solid var(--line-strong); }

  /* 档案式回答（markdown 安全渲染） */
  .answer :deep(.md-p) { font-size: 14.5px; line-height: 2.05; color: var(--ink-2); margin-bottom: 10px; }
  .answer :deep(.md-p:last-child) { margin-bottom: 0; }
  .answer :deep(strong) { color: var(--ink); font-weight: 700; }
  .answer :deep(em) { font-style: italic; }
  .answer :deep(.md-h) { font-family: var(--f-display); margin: 14px 0 8px; line-height: 1.4; font-weight: 700; color: var(--ink); }
  .answer :deep(.md-h1) { font-size: 18px; }
  .answer :deep(.md-h2) { font-size: 16px; padding-bottom: 4px; border-bottom: 1px solid var(--line); }
  .answer :deep(.md-h3) { font-size: 15px; }
  .answer :deep(.md-h4) { font-size: 14px; }
  .answer :deep(.md-hr) { border: none; border-top: 1px solid var(--line-strong); margin: 14px 0; }
  .answer :deep(.md-ul) { margin: 8px 0 12px; }
  .answer :deep(.md-ul li) { font-size: 14px; line-height: 1.95; color: var(--ink-2); padding-left: 18px; position: relative; list-style: none; }
  .answer :deep(.md-ul li)::before { content: '·'; position: absolute; left: 5px; color: var(--vermilion); }
  .answer :deep(.md-ol) { margin: 8px 0 12px; padding-left: 22px; }
  .answer :deep(.md-ol li) { font-size: 14px; line-height: 1.95; color: var(--ink-2); list-style: decimal; }
  .answer :deep(.md-quote) { margin: 8px 0; padding: 6px 12px; border-left: 2px solid var(--verm-line); background: var(--verm-wash); color: var(--ink-2); }
  .answer :deep(.md-pre) { margin: 8px 0; padding: 12px 14px; background: var(--ink); color: var(--paper); overflow-x: auto; font-size: 12.5px; line-height: 1.6; }
  .answer :deep(.md-code-block) { font-family: var(--f-mono); }
  .answer :deep(.md-code-inline) { background: var(--line-soft); padding: 1px 5px; font-size: 12.5px; font-family: var(--f-mono); }
  .answer :deep(.md-link) { color: var(--vermilion-deep); border-bottom: 1px solid var(--verm-line); }
  .answer :deep(.md-link:hover) { color: var(--vermilion); }
  .answer :deep(.md-table) { border-collapse: collapse; margin: 8px 0; font-size: 13px; display: block; overflow-x: auto; max-width: 100%; }
  .answer :deep(.md-table th),
  .answer :deep(.md-table td) { border: 1px solid var(--line-strong); padding: 6px 10px; text-align: left; }
  .answer :deep(.md-table th) { background: var(--sheet-2); font-weight: 600; }
  .answer :deep(.md-math-block) { margin: 10px 0; padding: 4px 0; text-align: center; overflow-x: auto; }
  .answer :deep(.katex-display) { margin: 0; }
  .answer :deep(.md-math-raw) { background: var(--line-soft); padding: 2px 6px; font-size: 12.5px; font-family: var(--f-mono); }

  .sources { margin-top: 16px; padding-top: 14px; border-top: 1px dashed var(--line); }
  .sources .st { font-family: var(--f-mono); font-size: 10px; letter-spacing: 0.18em; text-transform: uppercase; color: var(--ink-4); margin-bottom: 10px; display: flex; align-items: center; gap: 8px; }
  .source-row { display: flex; align-items: center; gap: 10px; padding: 7px 0; }
  .source-row .no { font-family: var(--f-mono); font-size: 10.5px; font-weight: 700; color: var(--vermilion); width: 18px; }
  .source-row .name { font-size: 13px; color: var(--ink); border-bottom: 1px solid var(--line-strong); transition: all var(--dur-1) ease; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .source-row .name:hover { color: var(--vermilion); border-color: var(--vermilion); }
  .source-row .bar { flex: 1; height: 3px; background: var(--line-soft); position: relative; min-width: 40px; }
  .source-row .bar i { position: absolute; inset: 0 auto 0 0; background: var(--ink); }
  .source-row .pct { font-family: var(--f-mono); font-size: 10.5px; font-weight: 700; color: var(--ink-2); width: 36px; text-align: right; }

  .sparse {
    margin-top: 14px; display: flex; align-items: center; gap: 9px;
    padding: 10px 14px; border: 1px dashed var(--ochre); background: var(--ochre-wash);
    font-size: 12.5px; color: #7A5410;
  }
  .sparse-link { font-weight: 600; color: var(--ochre); border-bottom: 1px solid currentColor; margin-left: auto; white-space: nowrap; }

  .thinking { display: inline-flex; gap: 5px; align-items: center; padding-left: 18px; }
  .thinking i { width: 6px; height: 6px; border-radius: 50%; background: var(--ink-3); animation: pulse 1.2s ease-in-out infinite; }
  .thinking i:nth-child(2) { animation-delay: .18s; }
  .thinking i:nth-child(3) { animation-delay: .36s; }

  /* 空态建议 */
  .chat-empty { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; text-align: center; }
  .suggests { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; margin-top: 18px; }
  .suggest {
    text-align: left; padding: 12px 16px; max-width: 280px;
    border: 1px solid var(--line); background: var(--sheet-2);
    font-size: 13px; color: var(--ink-2); line-height: 1.7;
    transition: all var(--dur-2) var(--ease);
  }
  .suggest:hover { border-color: var(--ink); transform: translateY(-2px); }

  /* 未选中会话（融合旧视图空态文案） */
  .unselected { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; padding: 40px; text-align: center; }
  .unselected .empty-sub { max-width: 420px; }

  /* 输入台 */
  .composer { flex-shrink: 0; border-top: 1px solid var(--line-strong); padding: 16px clamp(20px, 3vw, 44px) 18px; background: var(--sheet-2); }
  .composer .box {
    display: flex; align-items: flex-end; gap: 12px;
    border: 1px solid var(--line-strong); background: var(--sheet); padding: 12px 14px;
    transition: border-color var(--dur-2) ease, box-shadow var(--dur-2) ease;
  }
  .composer .box:focus-within { border-color: var(--ink); box-shadow: 0 0 0 3px var(--line-soft); }
  .composer textarea { flex: 1; border: 0; outline: none; background: none; resize: none; font-size: 14.5px; line-height: 1.8; min-height: 46px; max-height: 140px; }
  .composer textarea::placeholder { color: var(--ink-4); }
  .send {
    width: 42px; height: 42px; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    background: var(--ink); color: var(--paper);
    transition: all var(--dur-2) var(--ease);
  }
  .send:hover:not(:disabled) { background: var(--vermilion); transform: translateY(-2px); }
  .send:disabled { opacity: .4; pointer-events: none; }
  .composer .foot { display: flex; justify-content: space-between; gap: 12px; margin-top: 10px; }
  .composer .foot span { font-family: var(--f-mono); font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink-4); }

  @media (max-width: 1080px) {
    .chat-layout { grid-template-columns: 1fr; height: auto; min-height: 0; }
    .sessions { max-height: 260px; }
    .chat { height: 72vh; }
  }
</style>