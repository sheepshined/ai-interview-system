<script setup>
import { computed, onMounted, ref } from 'vue'
import { listInterviewRecords, getInterviewRecord, deleteInterviewRecord } from '../api'
import Icon from '../components/Icon.vue'
import TopBar from '../components/TopBar.vue'
import { toast } from '../composables/useToast'

const records = ref([])
const loading = ref(false)
const loadError = ref('')

const selected = ref('')
const content = ref('')
const contentLoading = ref(false)
const contentError = ref('')

/* ── 记录 Markdown 解析：## 第N题 → 题号块，其余行 → md-h/sub/li/p ── */
const FIELD_MAP = {
  '题目 ID': 'id',
  '题目': 'question',
  '你的回答': 'answer',
  '追问': 'followup',
  '补充回答': 'followAnswer',
  '标准答案': 'standard',
  '最终得分': 'score',
  '评分维度': 'dims',
  '初始得分': 'initialScore',
}

function parseInterviewMarkdown(md) {
  const lines = String(md || '').replace(/\r\n?/g, '\n').split('\n')
  const blocks = []
  let meta = []
  let qa = null
  let cur = null

  const flushMeta = () => {
    if (!meta.length) return
    blocks.push({ kind: 'sub', text: meta.map(([k, v]) => `${k}: ${v}`).join(' · ') })
    meta = []
  }
  const addText = (kind, t) => {
    const s = String(t || '').trim()
    if (!s) return
    const last = blocks[blocks.length - 1]
    if (last && last.kind === kind && kind === 'p') { last.text += ' ' + s; return }
    blocks.push({ kind, text: s })
  }
  const finishQa = () => {
    if (qa) {
      const m = String(qa.score || '').match(/(\d+(?:\.\d+)?)/)
      if (m) {
        qa.scoreNum = Number(m[1])
        qa.scoreCls = qa.scoreNum >= 7.5 ? 'hi' : (qa.scoreNum < 6.5 ? 'lo' : '')
      }
      blocks.push(qa)
      qa = null
    }
    cur = null
  }
  const startQa = (title) => {
    finishQa()
    const m = title.match(/^第\s*(\d+)\s*题\s*(.*)$/)
    qa = {
      kind: 'qa',
      n: m ? m[1] : '',
      label: m ? m[2].trim() : String(title || '').trim(),
      id: '', question: '', answer: '', followup: '', followAnswer: '',
      standard: '', dims: '', score: '', scoreNum: null, scoreCls: '',
    }
  }
  const appendField = (key, v) => {
    if (!qa) return
    const s = String(v || '').trim()
    if (!s) return
    qa[key] = qa[key] ? qa[key] + ' ' + s : s
  }

  for (const rawLine of lines) {
    const line = rawLine.trim()
    if (!line) continue
    if (/^[-*_]{3,}$/.test(line)) { finishQa(); continue }

    let m
    if ((m = line.match(/^#\s+(.+)$/))) { finishQa(); flushMeta(); addText('h', m[1]); continue }
    if ((m = line.match(/^#{3,}\s+(.+)$/))) { finishQa(); flushMeta(); addText('sub', m[1]); continue }
    if ((m = line.match(/^##\s+(.+)$/))) {
      flushMeta()
      if (/第\s*\d+\s*题/.test(m[1])) startQa(m[1])
      else { finishQa(); addText('h', m[1]) }
      continue
    }
    // 列表行：头部元信息（- **用户**: x）或普通列表
    if ((m = line.match(/^[-*]\s+\*\*(.+?)\*\*[:：]\s*(.*)$/))) {
      if (qa) { addText('li', `${m[1].trim()}: ${m[2].trim()}`); cur = null }
      else meta.push([m[1].trim(), m[2].trim()])
      continue
    }
    if ((m = line.match(/^[-*]\s+(.+)$/))) { addText('li', m[1]); cur = null; continue }
    // 粗体字段行（题目 / 你的回答 / 最终得分 …）
    if ((m = line.match(/^\*\*(.+?)\*\*[:：]\s*(.*)$/))) {
      const key = m[1].trim()
      const val = m[2].trim()
      if (qa && FIELD_MAP[key]) {
        appendField(FIELD_MAP[key], val)
        cur = { key: FIELD_MAP[key] }
      } else {
        cur = null
      }
      continue
    }
    // 多行字段的续行
    if (qa && cur) { appendField(cur.key, line); continue }
    addText('p', line)
  }
  finishQa()
  flushMeta()
  return blocks
}

const docBlocks = computed(() => parseInterviewMarkdown(content.value))
const qaCount = computed(() => docBlocks.value.filter((b) => b.kind === 'qa').length)

const selectedMeta = computed(
  () => records.value.find((r) => r.filename === selected.value) || null
)
const docQuestionCount = computed(
  () => selectedMeta.value?.total_count || (qaCount.value || '-')
)
const docClock = computed(() => clockTs(selectedMeta.value?.timestamp || ''))

/* ── 工具 ── */
function pad(n) {
  return String(n).padStart(2, '0')
}
function formatTs(ts) {
  if (!ts || ts.length < 13) return ts || ''
  return `${ts.slice(4, 6)}-${ts.slice(6, 8)} ${ts.slice(9, 11)}:${ts.slice(11, 13)}`
}
function clockTs(ts) {
  if (!ts || ts.length < 13) return ''
  return `${ts.slice(9, 11)}:${ts.slice(11, 13)}`
}
function sizeKb(size) {
  if (!size) return ''
  return `${(size / 1024).toFixed(1)} KB`
}

/* ── 数据加载 ── */
async function loadRecords(autoSelect = true) {
  loading.value = true
  loadError.value = ''
  try {
    const r = await listInterviewRecords()
    if (!r.success) {
      loadError.value = r.message || '记录加载失败'
      records.value = []
      return
    }
    records.value = r.records || []
    if (autoSelect) {
      const stillThere = selected.value && records.value.some((x) => x.filename === selected.value)
      if (!stillThere) selected.value = records.value[0]?.filename || ''
      if (selected.value) await selectRecord(selected.value)
      else { content.value = ''; contentError.value = '' }
    }
  } finally {
    loading.value = false
  }
}

async function selectRecord(fn) {
  selected.value = fn
  content.value = ''
  contentError.value = ''
  contentLoading.value = true
  try {
    const r = await getInterviewRecord(fn)
    if (r.success) content.value = r.content || ''
    else contentError.value = r.message || '加载失败'
  } finally {
    contentLoading.value = false
  }
}

async function refresh() {
  await loadRecords(true)
  toast('已刷新记录列表', 'refresh')
}

async function copyContent() {
  const text = content.value
  if (!text) return
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    toast('已复制到剪贴板')
  } catch (_) {
    toast('复制失败', 'warn')
  }
}

async function deleteRecord(fn) {
  if (!confirm(`确定删除这条记录吗？\n${fn}`)) return
  const r = await deleteInterviewRecord(fn)
  if (r.success) {
    selected.value = ''
    content.value = ''
    contentError.value = ''
    await loadRecords(false)
    toast('已删除该记录')
  } else {
    toast(`删除失败: ${r.message}`, 'warn')
  }
}

onMounted(() => loadRecords(true))
</script>

<template>
  <div>
    <TopBar crumb="面试记录" folio="卷·04">
      <template #actions>
        <button class="tlink" :disabled="loading" @click="refresh">
          <Icon name="refresh" :size="15" />{{ loading ? '刷新中' : '刷新' }}
        </button>
      </template>
    </TopBar>

    <div class="page-body">
      <div class="page-head" v-reveal>
        <span class="sec-index">ARCHIVE</span>
        <h1 class="page-title" style="margin-top:14px">每场面试，都留了底稿</h1>
        <p class="page-sub">逐题问答自动保存为 Markdown 档案，按用户隔离；可随时回看、复制与删除。</p>
      </div>

      <div class="rec-layout">
        <!-- 左：档案清单 -->
        <div class="rec-list" v-reveal="0.05">
          <div class="rec-list-head">
            <span class="t">Records · {{ records.length }} 份</span>
            <span class="mono">按时间倒序</span>
          </div>

          <div v-if="loading" class="rec-state">
            <span class="spin"></span>加载中…
          </div>

          <div v-else-if="loadError" class="rec-state rec-state-col">
            <span>{{ loadError }}</span>
            <button class="btn btn-ghost btn-sm" @click="loadRecords(true)">
              <Icon name="refresh" :size="14" />重新加载
            </button>
          </div>

          <div v-else-if="!records.length" class="empty rec-empty">
            <div class="empty-ic"><Icon name="records" :size="28" /></div>
            <div class="empty-title">暂无面试记录</div>
            <div class="empty-sub">完成一场面试后，答题过程会自动保存到这里</div>
          </div>

          <button
            v-else
            v-for="(r, idx) in records"
            :key="r.filename"
            class="rec-item"
            :class="{ 'is-on': selected === r.filename }"
            @click="selectRecord(r.filename)"
          >
            <span class="idx">{{ pad(idx + 1) }}</span>
            <span class="body">
              <span class="role">{{ r.role_title || '未知岗位' }}</span>
              <span class="meta">
                <span>{{ r.difficulty_label || '-' }}</span>
                <span>·</span>
                <span>{{ r.total_count || '-' }} 题</span>
                <template v-if="r.size">
                  <span>·</span>
                  <span>{{ sizeKb(r.size) }}</span>
                </template>
                <template v-if="r.timestamp">
                  <span>·</span>
                  <span>{{ formatTs(r.timestamp) }}</span>
                </template>
              </span>
            </span>
            <span
              class="del"
              role="button"
              tabindex="0"
              title="删除"
              @click.stop="deleteRecord(r.filename)"
              @mousedown.stop
              @keydown.enter.stop="deleteRecord(r.filename)"
            >
              <Icon name="trash" :size="15" />
            </span>
          </button>
        </div>

        <!-- 右：档案视图 -->
        <div class="rec-doc" v-reveal="0.12">
          <template v-if="selected">
            <div class="rec-doc-head">
              <div style="min-width:0">
                <div class="fname">{{ selected }}</div>
                <div class="sub">Record · {{ docQuestionCount }} questions · {{ docClock }}</div>
              </div>
              <div style="display:flex; gap:10px">
                <button class="btn btn-sm btn-ghost" :disabled="!content" @click="copyContent">
                  <Icon name="copy" :size="14" />复制
                </button>
              </div>
            </div>

            <div class="rec-doc-body">
              <div v-if="contentLoading" class="rec-state">
                <span class="spin"></span>加载中…
              </div>

              <div v-else-if="contentError" class="empty">
                <div class="empty-ic"><Icon name="alert" :size="28" /></div>
                <div class="empty-title">加载失败</div>
                <div class="empty-sub">{{ contentError }}</div>
                <div style="margin-top:22px">
                  <button class="btn btn-ghost btn-sm" @click="selectRecord(selected)">
                    <Icon name="refresh" :size="14" />重新加载
                  </button>
                </div>
              </div>

              <template v-else-if="docBlocks.length">
                <template v-for="(b, i) in docBlocks" :key="i">
                  <h2 v-if="b.kind === 'h'" class="md-h">{{ b.text }}</h2>
                  <div v-else-if="b.kind === 'sub'" class="md-sub">{{ b.text }}</div>
                  <div v-else-if="b.kind === 'li'" class="md-li">{{ b.text }}</div>
                  <div v-else-if="b.kind === 'p'" class="md-p">{{ b.text }}</div>
                  <div v-else-if="b.kind === 'qa'" class="qa">
                    <div class="who">
                      Q{{ b.n }}<template v-if="b.label"> · {{ b.label }}</template>
                      <span v-if="b.followup" class="flag">· 已追问</span>
                    </div>
                    <div v-if="b.question" class="q-text">{{ b.question }}</div>
                    <div v-if="b.answer" class="a-text">{{ b.answer }}</div>

                    <div v-if="b.followup" class="qa-part">
                      <div class="who">追问</div>
                      <div class="q-text">{{ b.followup }}</div>
                      <div v-if="b.followAnswer" class="a-text">{{ b.followAnswer }}</div>
                    </div>

                    <div v-if="b.standard" class="qa-part">
                      <div class="who">标准答案</div>
                      <div class="a-text">{{ b.standard }}</div>
                    </div>

                    <div v-if="b.scoreNum != null" class="score" :class="b.scoreCls">
                      评分 {{ b.scoreNum }}/10
                    </div>
                    <div v-if="b.dims" class="dims">{{ b.dims }}</div>
                  </div>
                </template>
              </template>

              <div v-else class="rec-state">档案内容为空</div>
            </div>
          </template>

          <template v-else>
            <div class="rec-doc-head">
              <div>
                <div class="fname" style="color:var(--ink-4)">尚未选择档案</div>
                <div class="sub">Select a record</div>
              </div>
            </div>
            <div class="rec-doc-body">
              <div class="empty">
                <div class="empty-ic"><Icon name="target" :size="30" /></div>
                <div class="empty-title">点击左侧记录查看内容</div>
                <div class="empty-sub">逐题问答会以档案形式呈现在这里。</div>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
  .rec-layout { display: grid; grid-template-columns: 372px 1fr; gap: 26px; align-items: start; }

  /* ── 左：档案清单 ── */
  .rec-list { border: 1px solid var(--line); background: var(--sheet); }
  .rec-list-head {
    display: flex; align-items: center; justify-content: space-between; gap: 12px;
    padding: 16px 18px; border-bottom: 1px solid var(--line-strong);
  }
  .rec-list-head .t { font-family: var(--f-mono); font-size: 10.5px; letter-spacing: 0.2em; text-transform: uppercase; color: var(--ink-3); }
  .rec-item {
    position: relative; width: 100%; text-align: left;
    display: flex; align-items: center; gap: 14px;
    padding: 16px 18px; border-bottom: 1px solid var(--line);
    transition: background var(--dur-1) ease, padding-left var(--dur-2) var(--ease);
    cursor: pointer;
  }
  .rec-item:last-child { border-bottom: 0; }
  .rec-item:hover { background: var(--sheet-2); padding-left: 22px; }
  .rec-item.is-on { background: var(--sheet-2); }
  .rec-item.is-on::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--vermilion); }
  .rec-item .idx { font-family: var(--f-mono); font-size: 11px; color: var(--ink-4); }
  .rec-item .body { min-width: 0; flex: 1; }
  .rec-item .role { display: block; font-family: var(--f-display); font-weight: 900; font-size: 15px; }
  .rec-item .meta { display: flex; align-items: center; gap: 8px; margin-top: 5px; font-family: var(--f-mono); font-size: 10.5px; color: var(--ink-4); letter-spacing: 0.06em; }
  .rec-item .del { opacity: 0; color: var(--ink-4); transition: all var(--dur-1) ease; flex-shrink: 0; }
  .rec-item:hover .del { opacity: 1; }
  .rec-item .del:hover { color: var(--vermilion); }

  /* ── 右：文档视图 ── */
  .rec-doc { border: 1px solid var(--line); background: var(--sheet); display: flex; flex-direction: column; min-height: 620px; }
  .rec-doc-head {
    display: flex; align-items: center; justify-content: space-between; gap: 16px;
    padding: 18px 26px; border-bottom: 1px solid var(--line-strong);
  }
  .rec-doc-head .fname { font-family: var(--f-mono); font-size: 12px; color: var(--ink-2); letter-spacing: 0.04em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .rec-doc-head .sub { font-family: var(--f-mono); font-size: 10px; letter-spacing: 0.16em; text-transform: uppercase; color: var(--ink-4); margin-top: 4px; }
  .rec-doc-body { padding: 26px clamp(22px, 3vw, 40px); overflow-y: auto; max-height: 720px; }

  .md-h { font-family: var(--f-display); font-weight: 900; font-size: 17px; margin: 24px 0 10px; }
  .md-h:first-child { margin-top: 0; }
  .md-sub { font-family: var(--f-mono); font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--vermilion); margin: 20px 0 8px; }
  .md-p { font-size: 14px; line-height: 2; color: var(--ink-2); }
  .md-li { font-size: 14px; line-height: 2; color: var(--ink-2); padding-left: 16px; position: relative; }
  .md-li::before { content: '·'; position: absolute; left: 4px; color: var(--vermilion); }

  /* 逐题块 */
  .qa { border-left: 2px solid var(--line); padding: 4px 0 4px 18px; margin: 18px 0; }
  .qa .who { font-family: var(--f-mono); font-size: 10px; letter-spacing: 0.18em; text-transform: uppercase; color: var(--ink-4); margin-bottom: 6px; }
  .qa .who .flag { color: var(--vermilion); }
  .qa .q-text { font-family: var(--f-display); font-weight: 700; font-size: 15.5px; line-height: 1.9; margin-bottom: 12px; }
  .qa .a-text { font-size: 13.5px; line-height: 1.95; color: var(--ink-2); }
  .qa .qa-part { margin-top: 14px; }
  .qa .dims { margin-top: 8px; font-family: var(--f-mono); font-size: 10.5px; letter-spacing: 0.08em; color: var(--ink-4); }
  .qa .score {
    display: inline-flex; align-items: center; gap: 6px;
    margin-top: 10px; padding: 3px 10px;
    font-family: var(--f-mono); font-size: 11px; font-weight: 700;
    border: 1px solid var(--line-strong);
  }
  .qa .score.hi { border-color: rgba(46,107,80,.4); color: var(--pine); background: var(--pine-wash); }
  .qa .score.lo { border-color: var(--verm-line); color: var(--vermilion); background: var(--verm-wash); }

  /* 状态 */
  .rec-state {
    padding: 44px 24px; display: flex; align-items: center; justify-content: center; gap: 10px;
    color: var(--ink-3); font-size: 13.5px; text-align: center;
  }
  .rec-state-col { flex-direction: column; }
  .rec-state .spin {
    display: inline-block; width: 17px; height: 17px;
    border: 2px solid var(--line-strong); border-top-color: var(--vermilion); border-radius: 50%;
  }
  .rec-empty { border: 0; background: transparent; padding: 56px 24px; }

  @media (max-width: 1080px) { .rec-layout { grid-template-columns: 1fr; } .rec-doc { min-height: auto; } }
</style>