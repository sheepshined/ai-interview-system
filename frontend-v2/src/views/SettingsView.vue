<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  adminResetPassword,
  adminSetEnabled,
  adminSetRole,
  changePassword,
  deleteQbankQuestion,
  getAccountMe,
  getQbankStats,
  getQbankTemplate,
  importQbankQuestions,
  listQbankQuestions,
  listUsers,
  rebuildQbankIndex,
} from '../api'
import Icon from '../components/Icon.vue'
import TopBar from '../components/TopBar.vue'
import { useAssistantHistory } from '../composables/useAssistantHistory'
import { toast } from '../composables/useToast'
import { clearAuth } from '../auth'
import { animateValue } from '../composables/useCountUp'

const router = useRouter()

// ── 账号 ──
const me = ref({ username: '', role: 'user' })
const isAdmin = computed(() => me.value.role === 'admin')

// ── 锚点导航 ──
const sections = computed(() => {
  const base = [
    { id: 'account', no: '01', label: '账号安全', en: 'ACCOUNT', admin: false },
    { id: 'assistant', no: '02', label: '助手偏好', en: 'ASSISTANT', admin: false },
  ]
  if (isAdmin.value) {
    base.push({ id: 'users', no: '03', label: '用户管理', en: 'USERS', admin: true })
    base.push({ id: 'qbank', no: '04', label: '题库管理', en: 'QUESTION BANK', admin: true })
  }
  return base
})
const activeSection = ref('account')

let spyLock = false
function goToSection(id) {
  activeSection.value = id
  spyLock = true
  document.getElementById(`sec-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  setTimeout(() => { spyLock = false }, 700)
}
function onScrollSpy() {
  if (spyLock) return
  const ids = sections.value.map((s) => s.id)
  let current = ids[0]
  for (const id of ids) {
    const el = document.getElementById(`sec-${id}`)
    // 阈值高于 scroll-margin(76px): 区块标题落定到视口上部即高亮
    if (el && el.getBoundingClientRect().top < 170) current = id
  }
  // 末区块高度不足时强制点亮最后一项
  if (window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 4) {
    current = ids[ids.length - 1]
  }
  activeSection.value = current
}

// ── 改密码 ──
const pwdForm = reactive({ old: '', next: '', confirm: '' })
const pwdSaving = ref(false)

async function submitPassword() {
  if (!pwdForm.old || !pwdForm.next) { toast('请填写旧密码与新密码', 'warn'); return }
  if (pwdForm.next.length < 6) { toast('新密码至少 6 位', 'warn'); return }
  if (pwdForm.next !== pwdForm.confirm) { toast('两次输入的新密码不一致', 'warn'); return }
  pwdSaving.value = true
  const res = await changePassword(pwdForm.old, pwdForm.next)
  pwdSaving.value = false
  if (res.success) {
    toast('密码已更新, 请用新密码重新登录')
    // 改密码后旧 token 因 pw 指纹立即失效, 主动登出回到登录页, 避免突兀的 401 弹回
    setTimeout(() => {
      clearAuth()
      router.push('/login')
    }, 1200)
    pwdForm.old = pwdForm.next = pwdForm.confirm = ''
  } else {
    toast(res.message || res.detail || '修改失败', 'warn')
  }
}

// ── 用户管理 (admin) ──
const users = ref([])
const usersLoading = ref(false)
const resetTarget = ref(null)
const resetPwd = ref('')

async function loadUsers() {
  usersLoading.value = true
  const res = await listUsers()
  usersLoading.value = false
  if (res.success) users.value = res.users || []
}

async function doResetPassword() {
  if (!resetTarget.value || resetPwd.value.length < 6) { toast('新密码至少 6 位', 'warn'); return }
  const res = await adminResetPassword(resetTarget.value, resetPwd.value)
  if (res.success) {
    toast(res.message || '已重置')
    resetTarget.value = null
    resetPwd.value = ''
  } else toast(res.message || res.detail || '重置失败', 'warn')
}

async function toggleEnabled(user) {
  const res = await adminSetEnabled(user.username, !user.enabled)
  if (res.success) { toast(res.message || '已更新'); await loadUsers() }
  else toast(res.message || res.detail || '操作失败', 'warn')
}

async function changeRole(user, role) {
  const res = await adminSetRole(user.username, role)
  if (res.success) { toast(res.message || '已更新'); await loadUsers() }
  else toast(res.message || res.detail || '操作失败', 'warn')
}

// ── 题库管理 (admin) ──
const hist = useAssistantHistory()
const qstats = ref(null)
const qLoading = ref(false)
const importText = ref('')
const importReport = ref(null)
const importing = ref(false)
const rebuilding = ref(false)
const qList = ref([])
const qTotal = ref(0)
const qFilter = reactive({ category: '', q: '', offset: 0 })
const Q_PAGE = 200
const qDisp = reactive({ total: 0, cats: 0, index: 0 })
const qStatDone = ref(false)
const qTarget = ref({ total: 0, cats: 0, index: 0 })
const qStatRef = ref(null)

function runQCountUp() {
  if (qStatDone.value) return
  qStatDone.value = true
  animateValue(qTarget.value.total || 0, (v) => (qDisp.total = Math.round(v)))
  animateValue(qTarget.value.cats || 0, (v) => (qDisp.cats = Math.round(v)))
  animateValue(qTarget.value.index || 0, (v) => (qDisp.index = Math.round(v)))
}

async function loadQbank(append = false) {
  qLoading.value = true
  if (!append) qFilter.offset = 0
  const [statsRes, listRes] = await Promise.all([
    getQbankStats(),
    listQbankQuestions(qFilter.category, qFilter.q, Q_PAGE, qFilter.offset),
  ])
  qLoading.value = false
  if (statsRes.success) {
    qstats.value = statsRes.stats
    qTarget.value = {
      total: statsRes.stats.total || 0,
      cats: statsRes.stats.categories?.length || 0,
      index: statsRes.stats.index_count || 0,
    }
    runQCountUp()
  }
  if (listRes.success) {
    qList.value = append ? [...qList.value, ...(listRes.questions || [])] : (listRes.questions || [])
    qTotal.value = listRes.total || 0
  }
}

async function loadMoreQbank() {
  qFilter.offset += Q_PAGE
  await loadQbank(true)
}

async function runImport(dryRun) {
  let items = null
  try {
    items = JSON.parse(importText.value)
  } catch (e) {
    toast('JSON 解析失败: ' + e.message, 'warn')
    return
  }
  importing.value = true
  const res = await importQbankQuestions(items, dryRun)
  importing.value = false
  importReport.value = res
  if (res.success && res.written > 0) {
    toast(`已导入 ${res.written} 题, 重建索引后生效`)
    importText.value = ''
    await loadQbank()
  } else if (dryRun && res.validated > 0) {
    toast(`校验通过 ${res.validated} 条` + (res.errors?.length ? `,${res.errors.length} 条有问题` : ''))
  } else if (!res.success) {
    toast(res.message || '导入失败', 'warn')
  }
}

function onImportFile(event) {
  const file = event.target.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => { importText.value = String(reader.result || '') }
  reader.readAsText(file, 'utf-8')
  event.target.value = ''
}

async function downloadTemplate() {
  const data = await getQbankTemplate()
  if (!data?.success || !data.template) {
    toast(data?.message || '模板下载失败', 'warn')
    return
  }
  const blob = new Blob([JSON.stringify(data.template, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'qbank-import-template.json'
  a.click()
  URL.revokeObjectURL(url)
}

async function removeQuestion(item) {
  if (!confirm(`确认删除题目 ${item.id}? (需重建索引生效)`)) return
  const res = await deleteQbankQuestion(item.id)
  if (res.success) { toast(res.message || '已删除'); await loadQbank() }
  else toast(res.message || res.detail || '删除失败', 'warn')
}

async function rebuild() {
  if (!confirm('重建向量索引? 重建期间进行中的面试可能短暂受影响, 建议在无面试时操作。')) return
  rebuilding.value = true
  const res = await rebuildQbankIndex()
  rebuilding.value = false
  if (res.ok) { toast(res.message || '重建完成'); await loadQbank() }
  else toast(res.message || '重建失败', 'warn')
}

onMounted(async () => {
  const meRes = await getAccountMe()
  if (meRes.success) me.value = { username: meRes.username, role: meRes.role }
  await hist.loadSettings()
  // 管理区块仅在确认管理员身份后请求, 普通用户不产生 403 噪音
  if (me.value.role === 'admin') {
    await loadUsers()
    await loadQbank()
  }
  window.addEventListener('scroll', onScrollSpy, { passive: true })
  onScrollSpy()

  const statIo = new IntersectionObserver((entries) => {
    entries.forEach((en) => {
      if (en.isIntersecting) { runQCountUp(); statIo.disconnect() }
    })
  }, { threshold: 0.3 })
  if (qStatRef.value) statIo.observe(qStatRef.value)
})

onUnmounted(() => {
  window.removeEventListener('scroll', onScrollSpy)
})
</script>

<template>
  <div>
    <TopBar crumb="设置" folio="卷·06" />

    <div class="page-body settings-page">
      <div class="page-head" v-reveal>
        <span class="sec-index">SETTINGS</span>
        <h1 class="page-title">系统设<em class="mark">置</em></h1>
        <hr class="rv-hr head-rule" />
        <p class="page-sub">
          账号安全、助手偏好与系统管理
          <template v-if="isAdmin"> · 当前身份 <b class="role-chip"><Icon name="checkCircle" :size="12" />管理员</b></template>
        </p>
      </div>

      <div class="settings-grid">
        <!-- ── 左侧锚点导航 (桌面) ── -->
        <aside class="side-nav">
          <button v-for="s in sections" :key="s.id" class="side-link"
                  :class="{ 'is-active': activeSection === s.id }" @click="goToSection(s.id)">
            <span class="mono side-no">{{ s.no }}</span>
            <span class="side-label">{{ s.label }}<i v-if="s.admin" class="mono side-tag">ADMIN</i></span>
          </button>
          <div class="side-foot mono">Interview Studio · v1.3</div>
        </aside>

        <!-- ── 右侧内容 ── -->
        <div class="settings-flow">
          <!-- ── 01 账号安全 ── -->
          <section id="sec-account" class="panel" v-reveal>
            <div class="panel-head">
              <span class="sec-index">01 · ACCOUNT</span>
              <h2>账号安全</h2>
              <hr class="rv-hr panel-rule" />
            </div>
            <div class="account-row">
              <span class="seal acc-seal">{{ (me.username || 'U').charAt(0).toUpperCase() }}</span>
              <div class="acc-meta">
                <div class="acc-name">{{ me.username || '—' }}</div>
                <div class="acc-role mono">{{ me.role === 'admin' ? 'ADMINISTRATOR' : 'CANDIDATE' }}</div>
              </div>
              <span v-if="isAdmin" class="acc-stamp" v-reveal="0.3">管 理 员</span>
            </div>
            <div class="pwd-grid">
              <label>当前密码<input type="password" v-model="pwdForm.old" autocomplete="current-password" placeholder="验证身份" /></label>
              <label>新密码<input type="password" v-model="pwdForm.next" autocomplete="new-password" placeholder="至少 6 位" /></label>
              <label>确认新密码<input type="password" v-model="pwdForm.confirm" autocomplete="new-password" @keyup.enter="submitPassword" /></label>
              <button class="btn btn-dark btn-sm pwd-btn" :disabled="pwdSaving" @click="submitPassword">
                <Icon name="check" :size="14" />{{ pwdSaving ? '保存中' : '修改密码' }}
              </button>
            </div>
            <p class="panel-note">修改成功后当前会话将失效, 需用新密码重新登录。</p>
          </section>

          <!-- ── 02 助手偏好 ── -->
          <section id="sec-assistant" class="panel" v-reveal>
            <div class="panel-head">
              <span class="sec-index">02 · ASSISTANT</span>
              <h2>统筹助手偏好</h2>
              <hr class="rv-hr panel-rule" />
            </div>
            <div class="st-clone">
              <div class="pref-block">
                <h4>工具确认档位</h4>
                <div class="pref-opts">
                  <label v-for="(o, oi) in [
                    { value: 'all_confirm', label: '全部确认', desc: '每次工具调用都先问我' },
                    { value: 'read_auto', label: '只读自动（默认）', desc: '读操作自动执行；写与执行要确认' },
                    { value: 'exec_only', label: '仅执行确认', desc: '只有起面试这类执行动作要确认' },
                  ]" :key="o.value" class="pref-card"
                     :class="{ 'is-on': hist.settings.value.auto_accept_level === o.value }"
                     :style="{ '--d': `${oi * 0.06}s` }">
                    <input type="radio" :value="o.value" v-model="hist.settings.value.auto_accept_level"
                           @change="hist.saveSettings({ auto_accept_level: hist.settings.value.auto_accept_level, memory_enabled: hist.settings.value.memory_enabled })" />
                    <b>{{ o.label }}</b>
                    <small>{{ o.desc }}</small>
                  </label>
                </div>
              </div>
              <div class="pref-block">
                <h4>长期记忆</h4>
                <label class="pref-card pref-switch" :class="{ 'is-on': hist.settings.value.memory_enabled }">
                  <input type="checkbox" v-model="hist.settings.value.memory_enabled"
                         @change="hist.saveSettings({ auto_accept_level: hist.settings.value.auto_accept_level, memory_enabled: hist.settings.value.memory_enabled })" />
                  <div>
                    <b>启用记忆注入与写入</b>
                    <small>关闭后助手不再读取或写入长期记忆；已写入的记忆随时可在「记忆」面板查看与删除。</small>
                  </div>
                  <span class="switch-ui" aria-hidden="true"><i></i></span>
                </label>
              </div>
            </div>
          </section>

          <!-- ── 03 用户管理 (admin) ── -->
          <section id="sec-users" class="panel" v-if="isAdmin" v-reveal>
            <div class="panel-head">
              <span class="sec-index">03 · USERS</span>
              <h2>用户管理</h2>
              <span class="head-note mono">{{ users.length }} 个账号 · {{ users.filter(u => u.enabled).length }} 启用</span>
              <hr class="rv-hr panel-rule" />
              <button class="tlink head-action" :disabled="usersLoading" @click="loadUsers"><Icon name="refresh" :size="14" />刷新</button>
            </div>
            <div class="user-table">
              <div class="user-row user-head mono">
                <span>用户</span><span>角色</span><span>状态</span><span>创建</span><span></span>
              </div>
              <div v-for="u in users" :key="u.username" class="user-row"
                   :class="{ 'is-me': u.username === me.username, 'is-off': !u.enabled }">
                <span class="u-name">
                  <i class="u-dot" :class="u.enabled ? 'on' : 'off'"></i>
                  {{ u.username }}<em v-if="u.username === me.username" class="mono u-tag">当前</em>
                </span>
                <span class="u-role-wrap">
                  <select class="role-select" :value="u.role" :disabled="u.username === me.username"
                          @change="changeRole(u, $event.target.value)">
                    <option value="admin">管理员</option>
                    <option value="user">普通用户</option>
                  </select>
                </span>
                <span class="u-state" :class="u.enabled ? 'on' : 'off'">{{ u.enabled ? '启用' : '停用' }}</span>
                <span class="mono u-date">{{ (u.created_at || '').slice(0, 10) }}</span>
                <div class="u-actions">
                  <button class="btn btn-ghost btn-sm" @click="resetTarget = u; resetPwd = ''"><Icon name="refresh" :size="13" />重置密码</button>
                  <button class="btn btn-ghost btn-sm" :class="{ 'danger-action': u.enabled }" :disabled="u.username === me.username"
                          @click="toggleEnabled(u)">
                    {{ u.enabled ? '停用' : '启用' }}
                  </button>
                </div>
              </div>
            </div>
            <div v-if="resetTarget" class="reset-box" v-reveal>
              <span>重置 <b>{{ resetTarget.username }}</b> 的密码:</span>
              <input type="password" v-model="resetPwd" autocomplete="new-password" placeholder="新密码, 至少 6 位" @keyup.enter="doResetPassword" />
              <button class="btn btn-dark btn-sm" @click="doResetPassword">确认重置</button>
              <button class="btn btn-ghost btn-sm" @click="resetTarget = null">取消</button>
            </div>
            <p class="panel-note"><Icon name="alert" :size="12" /> 停用即时生效: 该账号已登录的会话也会被拒绝; 系统至少保留一个启用的管理员。</p>
          </section>

          <!-- ── 04 题库管理 (admin) ── -->
          <section id="sec-qbank" class="panel" v-if="isAdmin" v-reveal>
            <div class="panel-head">
              <span class="sec-index">04 · QUESTION BANK</span>
              <h2>题库管理</h2>
              <hr class="rv-hr panel-rule" />
              <button class="tlink head-action" :disabled="qLoading" @click="loadQbank()"><Icon name="refresh" :size="14" />刷新</button>
            </div>

            <div ref="qStatRef" class="q-stat-row">
              <div class="q-stat"><b class="fig">{{ qDisp.total }}</b><span>题库题目</span></div>
              <div class="q-stat"><b class="fig">{{ qDisp.cats }}</b><span>分类</span></div>
              <div class="q-stat"><b class="fig">{{ qDisp.index }}</b><span>向量索引</span></div>
              <div class="q-stat" v-if="qstats">
                <b class="mono">{{ qstats.difficulty?.['1'] || 0 }}/{{ qstats.difficulty?.['2'] || 0 }}/{{ qstats.difficulty?.['3'] || 0 }}</b>
                <span>初 / 中 / 高级</span>
              </div>
            </div>

            <div class="import-zone">
              <div class="section-row">
                <div class="section-label">导入题目 · JSON</div>
                <button class="tlink" @click="downloadTemplate"><Icon name="download" :size="13" />下载 JSON 模板</button>
              </div>
              <textarea v-model="importText" class="import-box" rows="7" spellcheck="false"
                        placeholder='粘贴 JSON 数组, 例如:&#10;[{ "category": "RAG", "difficulty": 2, "type": "scenario", "question": "题面", "answer": "标准答案", "scoring_points": ["要点1"] }]'></textarea>
              <div class="import-actions">
                <label class="btn btn-ghost btn-sm file-btn"><Icon name="upload" :size="13" />选择文件<input type="file" accept=".json,.txt" hidden @change="onImportFile" /></label>
                <button class="btn btn-ghost btn-sm" :disabled="importing || !importText.trim()" @click="runImport(true)">仅校验</button>
                <button class="btn btn-dark btn-sm" :disabled="importing || !importText.trim()" @click="runImport(false)"><Icon name="upload" :size="13" />{{ importing ? '导入中' : '导入题库' }}</button>
                <button class="btn btn-dark btn-sm rebuild-btn" :disabled="rebuilding" @click="rebuild"><Icon name="refresh" :size="13" :class="{ spinning: rebuilding }" />{{ rebuilding ? '重建中…' : '重建向量索引' }}</button>
              </div>
              <div v-if="importReport" class="import-report" :class="{ bad: importReport.errors?.length }" v-reveal>
                <template v-if="importReport.dry_run">校验结果:</template>
                <template v-else>导入结果:</template>
                通过 <b>{{ importReport.validated }}</b> · 写入 <b>{{ importReport.written }}</b>
                <template v-if="importReport.errors?.length">· 问题 {{ importReport.errors.length }} 条:</template>
                <ul v-if="importReport.errors?.length"><li v-for="(e, i) in importReport.errors" :key="i">{{ e }}</li></ul>
              </div>
              <p class="panel-note">导入写入题库 markdown (事实源); 点击"重建向量索引"后才会出现在面试出题中。重建期间进行中的面试可能短暂受影响, 建议在无面试时操作。</p>
            </div>

            <div class="q-list-zone">
              <div class="section-row">
                <div class="section-label">题目列表 <span class="mono">共 {{ qTotal }} 题</span></div>
                <div class="q-filters">
                  <input v-model="qFilter.q" class="input-box" placeholder="搜索题面或 id" @keyup.enter="loadQbank()" />
                  <button class="btn btn-ghost btn-sm" @click="loadQbank()"><Icon name="search" :size="13" />筛选</button>
                </div>
              </div>
              <div class="q-rows">
                <div v-for="item in qList" :key="item.id" class="q-row">
                  <div class="q-main">
                    <div class="q-text">{{ item.question }}</div>
                    <div class="q-meta mono">{{ item.id }} · {{ item.category }} · {{ item.difficulty_label }} · {{ item.type === 'scenario' ? '场景' : '知识' }}</div>
                  </div>
                  <button class="icon-btn" title="删除题目" @click="removeQuestion(item)"><Icon name="trash" :size="14" /></button>
                </div>
                <div v-if="!qList.length" class="q-empty">没有匹配的题目</div>
                <div v-if="qList.length < qTotal" class="q-more">
                  <button class="btn btn-ghost btn-sm" :disabled="qLoading" @click="loadMoreQbank">
                    加载更多 (已显示 {{ qList.length }} / {{ qTotal }})
                  </button>
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings-page { max-width: 1240px; }
.page-head { margin-bottom: 14px; }
.head-rule { border: none; border-top: 1px solid var(--line-strong); margin: 14px 0 12px; max-width: 180px; }
.role-chip {
  display: inline-flex; align-items: center; gap: 4px; color: var(--vermilion);
  border: 1px solid var(--verm-line); border-radius: 999px; padding: 1px 10px;
  font-size: 12px; background: var(--verm-wash);
}

/* ── 双栏骨架 ── */
.settings-grid { display: grid; grid-template-columns: 208px 1fr; gap: 28px; align-items: start; }
.side-nav { position: sticky; top: 76px; display: flex; flex-direction: column; gap: 2px; }
.side-link {
  display: flex; align-items: center; gap: 10px; padding: 10px 12px;
  background: none; border: none; border-left: 2px solid transparent;
  font-size: 13px; color: var(--ink-2); cursor: pointer; text-align: left;
  transition: color 0.2s ease, border-color 0.2s ease, background 0.2s ease;
}
.side-link:hover { color: var(--ink); background: var(--verm-wash); }
.side-link.is-active { color: var(--ink); border-left-color: var(--vermilion); background: var(--verm-wash); }
.side-no { font-size: 10px; color: var(--ink-4); }
.side-link.is-active .side-no { color: var(--vermilion); }
.side-label { display: inline-flex; align-items: center; gap: 6px; }
.side-tag { font-style: normal; font-size: 8px; letter-spacing: 0.12em; color: var(--ochre); border: 1px solid rgba(169, 116, 28, 0.4); border-radius: 3px; padding: 0 4px; }
.side-foot { margin-top: 18px; padding: 0 12px; font-size: 9px; color: var(--ink-4); letter-spacing: 0.1em; }

.settings-flow { display: flex; flex-direction: column; gap: 26px; min-width: 0; }
.panel {
  background: var(--sheet); border: 1px solid var(--line); border-radius: var(--r-1);
  padding: 24px 26px; box-shadow: var(--sh-sheet); scroll-margin-top: 76px;
}
.panel-head { position: relative; display: flex; align-items: baseline; gap: 12px; margin-bottom: 18px; flex-wrap: wrap; padding-bottom: 10px; }
.panel-head h2 { font-size: 19px; font-family: var(--f-display); margin: 0; letter-spacing: 0.01em; }
.panel-rule { border: none; border-top: 1px solid var(--line-soft); position: absolute; left: 0; right: 0; bottom: 0; margin: 0; }
.head-note { font-size: 11px; color: var(--ink-4); margin-left: auto; }
.head-action { margin-left: auto; }
.head-note + .head-action { margin-left: 0; }
.panel-note { font-size: 11px; color: var(--ink-3); margin: 14px 0 0; display: flex; align-items: center; gap: 4px; }

/* ── 01 账号 ── */
.account-row { display: flex; align-items: center; gap: 14px; margin-bottom: 20px; position: relative; }
.acc-seal {
  width: 46px; height: 46px; display: grid; place-items: center;
  background: var(--ink); color: var(--paper); font-family: var(--f-display);
  font-size: 20px; font-weight: 700; border-radius: var(--r-2);
  box-shadow: 2px 2px 0 var(--verm-line);
}
.acc-name { font-size: 17px; font-weight: 700; font-family: var(--f-display); }
.acc-role { font-size: 10px; color: var(--ink-3); letter-spacing: 0.18em; }
.acc-stamp {
  margin-left: auto; color: var(--vermilion); border: 2px solid var(--vermilion);
  border-radius: var(--r-2); padding: 6px 12px; font-size: 13px; font-weight: 700;
  font-family: var(--f-display); letter-spacing: 0.3em;
  box-shadow: inset 0 0 0 1px rgba(217, 58, 31, 0.25);
  transition: opacity 0.5s ease 0.35s, transform 0.7s var(--ease) 0.35s;
}
.acc-stamp.rv { opacity: 0; transform: rotate(-14deg) scale(1.35); }
.acc-stamp.rv.is-in { opacity: 0.85; transform: rotate(-6deg) scale(1); }
.pwd-grid { display: grid; grid-template-columns: repeat(3, 1fr) auto; gap: 12px; align-items: end; }
.pwd-grid label { display: flex; flex-direction: column; gap: 6px; font-size: 11px; letter-spacing: 0.06em; color: var(--ink-2); min-width: 0; }
.pwd-grid input {
  border: 1px solid var(--line); border-radius: var(--r-2); padding: 9px 11px; font-size: 13px;
  background: var(--sheet-2); transition: border-color 0.2s ease, box-shadow 0.2s ease;
  width: 100%; min-width: 0; box-sizing: border-box;
}
.pwd-grid input:focus {
  outline: none; border-color: var(--vermilion);
  box-shadow: 0 0 0 3px var(--verm-wash);
}
.pwd-btn { height: 37px; }

/* ── 02 助手偏好 ── */
.pref-block + .pref-block { margin-top: 20px; }
.pref-block h4 { font-size: 12px; letter-spacing: 0.08em; color: var(--ink-2); margin: 0 0 10px; }
.pref-opts { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.pref-card {
  position: relative; display: block; border: 1px solid var(--line);
  border-radius: var(--r-2); padding: 13px 14px; background: var(--sheet-2); cursor: pointer;
  transition: border-color 0.2s ease, background 0.2s ease, transform 0.2s ease;
}
.pref-card:hover { transform: translateY(-1px); border-color: var(--line-strong); }
.pref-card input { position: absolute; opacity: 0; pointer-events: none; }
.pref-card b { display: block; font-size: 13px; margin-bottom: 3px; }
.pref-card small { display: block; font-size: 11px; color: var(--ink-3); line-height: 1.5; }
.pref-card.is-on { border-color: var(--vermilion); background: var(--verm-wash); }
.pref-card.is-on::after {
  content: ''; position: absolute; top: 10px; right: 10px; width: 7px; height: 7px;
  border-radius: 50%; background: var(--vermilion);
}
.pref-card:focus-within { outline: none; border-color: var(--vermilion); box-shadow: 0 0 0 3px var(--verm-wash); }
.pref-switch { display: flex; gap: 14px; align-items: center; }
.pref-switch > div { flex: 1; }
.switch-ui {
  width: 38px; height: 22px; border-radius: 999px; background: var(--paper-deep);
  border: 1px solid var(--line); position: relative; transition: background 0.25s ease; flex-shrink: 0;
}
.switch-ui i {
  position: absolute; top: 2px; left: 2px; width: 16px; height: 16px; border-radius: 50%;
  background: var(--sheet); box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
  transition: left 0.25s var(--ease);
}
.pref-switch.is-on .switch-ui { background: var(--pine); border-color: var(--pine); }
.pref-switch.is-on .switch-ui i { left: 18px; }

/* ── 03 用户管理 ── */
.user-table { display: flex; flex-direction: column; }
.user-row {
  display: grid; grid-template-columns: 1.25fr 130px 76px 90px auto;
  gap: 12px; align-items: center; padding: 11px 8px;
  border-bottom: 1px solid var(--line-soft); transition: background 0.15s ease;
}
.user-row.is-me { background: var(--verm-wash); }
.user-row.is-off { opacity: 0.78; }
.user-row.is-off .u-name { color: var(--ink-3); text-decoration: line-through; text-decoration-color: var(--ink-4); }
.user-head { font-size: 10px; letter-spacing: 0.12em; color: var(--ink-4); padding: 4px 8px 8px; }
.u-name { font-size: 14px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
.u-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
.u-dot.on { background: var(--pine); box-shadow: 0 0 0 3px var(--pine-wash); }
.u-dot.off { background: var(--ink-4); }
.u-tag { font-style: normal; font-size: 10px; color: var(--vermilion); border: 1px solid var(--verm-line); border-radius: 3px; padding: 0 4px; }
.role-select {
  border: 1px solid var(--line); border-radius: var(--r-2); padding: 5px 8px; font-size: 12px;
  background: var(--sheet-2); transition: border-color 0.2s ease;
}
.role-select:hover:not(:disabled) { border-color: var(--line-strong); }
.u-state { font-size: 12px; display: flex; align-items: center; }
.u-state.on { color: var(--pine); }
.u-state.off { color: var(--ink-3); }
.u-date { font-size: 11px; color: var(--ink-3); }
.u-actions { display: flex; gap: 8px; justify-content: flex-end; }
.reset-box {
  display: flex; gap: 10px; align-items: center; margin-top: 14px; padding: 12px 14px;
  background: var(--paper-deep); border-left: 3px solid var(--vermilion); border-radius: 0 var(--r-2) var(--r-2) 0;
  font-size: 13px;
}
.reset-box input { flex: 1; border: 1px solid var(--line); border-radius: var(--r-2); padding: 7px 10px; font-size: 13px; }
.reset-box input:focus { outline: none; border-color: var(--vermilion); box-shadow: 0 0 0 3px var(--verm-wash); }

/* ── 04 题库 ── */
.q-stat-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 20px; }
.q-stat {
  background: var(--sheet-2); border: 1px solid var(--line-soft); border-radius: var(--r-2);
  padding: 13px 15px; display: flex; flex-direction: column; gap: 2px;
}
.q-stat b { font-size: 24px; font-weight: 700; font-variant-numeric: tabular-nums; }
.q-stat span { font-size: 11px; color: var(--ink-3); }
.section-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; flex-wrap: wrap; }
.section-label { font-size: 11px; letter-spacing: 0.14em; color: var(--ink-3); }
.import-zone { padding-top: 8px; border-top: 1px dashed var(--line); }
.import-box {
  width: 100%; box-sizing: border-box; border: 1px solid var(--line); border-radius: var(--r-2);
  padding: 12px 14px; font-size: 12px; line-height: 1.7; font-family: var(--f-mono);
  background: var(--sheet-2); resize: vertical; transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.import-box:focus { outline: none; border-color: var(--vermilion); box-shadow: 0 0 0 3px var(--verm-wash); }
.import-actions { display: flex; gap: 10px; margin-top: 10px; flex-wrap: wrap; align-items: center; }
.file-btn { position: relative; overflow: hidden; cursor: pointer; }
.rebuild-btn { margin-left: auto; }
.rebuild-btn:disabled { opacity: 0.7; }
.spinning { animation: spin 0.9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.import-report {
  margin-top: 12px; font-size: 12px; color: var(--ink-2);
  border-left: 3px solid var(--pine); padding: 8px 12px; background: var(--pine-wash); border-radius: 0 6px 6px 0;
}
.import-report.bad { border-left-color: var(--vermilion); background: var(--verm-wash); }
.import-report.bad b { color: var(--vermilion); }
.import-report ul { margin: 6px 0 0; padding-left: 18px; color: var(--vermilion); }
.q-list-zone { margin-top: 22px; padding-top: 8px; border-top: 1px dashed var(--line); }
.q-filters { display: flex; gap: 8px; }
.q-filters .input-box { min-width: 200px; border: 1px solid var(--line); border-radius: var(--r-2); padding: 7px 10px; font-size: 12px; background: var(--sheet-2); }
.q-filters .input-box:focus { outline: none; border-color: var(--vermilion); box-shadow: 0 0 0 3px var(--verm-wash); }
.q-rows { display: flex; flex-direction: column; }
.q-row { display: flex; align-items: center; gap: 12px; padding: 9px 6px; border-bottom: 1px solid var(--line-soft); transition: background 0.15s ease; }
.q-row:hover { background: var(--paper-deep); }
.q-main { flex: 1; min-width: 0; }
.q-text { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.q-meta { font-size: 11px; color: var(--ink-3); margin-top: 2px; }
.q-row .icon-btn { opacity: 0; transition: opacity 0.15s ease, color 0.15s ease; }
.q-row:hover .icon-btn, .q-row .icon-btn:focus-visible { opacity: 1; }
.q-row .icon-btn:hover { color: var(--vermilion); }
@media (hover: none) {
  .q-row .icon-btn { opacity: 1; }
}
.q-empty { padding: 24px 0; text-align: center; color: var(--ink-3); font-size: 12px; }
.q-more { display: flex; justify-content: center; padding: 12px 0 4px; }

@media (max-width: 1080px) {
  .settings-grid { grid-template-columns: 1fr; }
  .side-nav { position: static; flex-direction: row; flex-wrap: wrap; gap: 6px; border-bottom: 1px solid var(--line-soft); padding-bottom: 12px; }
  .side-link { border-left: none; border-bottom: 2px solid transparent; border-radius: var(--r-2) var(--r-2) 0 0; }
  .side-link.is-active { border-bottom-color: var(--vermilion); }
  .side-foot { display: none; }
  .pwd-grid { grid-template-columns: 1fr 1fr; }
  .pwd-grid label:last-of-type { grid-column: span 2; }
}
@media (max-width: 760px) {
  /* 纵向 flex 布局: 规避小屏下栅格轨道受输入框固有宽度挤压的问题 */
  .pwd-grid { display: flex; flex-direction: column; align-items: stretch; }
  .pref-opts { grid-template-columns: 1fr; }
  .user-row { grid-template-columns: 1fr auto; }
  .u-role-wrap, .u-state, .u-date { display: none; }
  .q-stat-row { grid-template-columns: repeat(2, 1fr); }
}
</style>
