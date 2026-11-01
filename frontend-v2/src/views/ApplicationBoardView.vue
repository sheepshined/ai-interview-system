<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  addApplicationEvent,
  archiveApplication,
  createApplication,
  listApplications,
  listResumes,
  saveApplicationOutcome,
  updateApplication,
} from '../api'
import Icon from '../components/Icon.vue'
import TopBar from '../components/TopBar.vue'
import { toast } from '../composables/useToast'

const STAGES = [
  { key: 'saved', label: '待投递', tone: 'ink' },
  { key: 'applied', label: '已投递', tone: 'ochre' },
  { key: 'screening', label: '筛选 / 笔试', tone: 'ochre' },
  { key: 'interview', label: '面试中', tone: 'verm' },
  { key: 'offer', label: 'Offer', tone: 'pine' },
  { key: 'rejected', label: '已拒绝', tone: 'muted' },
  { key: 'withdrawn', label: '已撤回', tone: 'muted' },
]

const applications = ref([])
const route = useRoute()
const resumes = ref([])
const selectedId = ref(Number(route.query.application_id) || null)
const editingId = ref(null)
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const modal = ref('')
const eventNote = ref('')
const editForm = ref(emptyForm())
const outcomeForm = ref(emptyOutcome())

function emptyForm() {
  return { company: '', role_title: '', job_url: '', jd_text: '', stage: 'saved', resume_id: null }
}
function emptyOutcome() {
  return { result: '', feedback: '', reflection: '', next_steps: '', tags: '' }
}

const selected = computed(() => applications.value.find((item) => item.id === selectedId.value) || null)
const columns = computed(() => STAGES.map((stage) => ({
  ...stage,
  items: applications.value.filter((item) => item.stage === stage.key),
})))

function stageLabel(key) { return STAGES.find((stage) => stage.key === key)?.label || key }
function formatDate(value) {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value.replace('T', ' ') : date.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
function resumeTitle(id) {
  return resumes.value.find((resume) => resume.resume_id === id)?.title || (id ? `简历 #${id}` : '未关联简历')
}

async function load() {
  loading.value = true
  error.value = ''
  const [apps, resumeResult] = await Promise.all([listApplications(), listResumes()])
  if (apps.success) {
    applications.value = apps.applications || []
    if (!selectedId.value || !applications.value.some((item) => item.id === selectedId.value)) selectedId.value = applications.value[0]?.id || null
  } else {
    error.value = apps.message || '投递记录加载失败'
  }
  if (resumeResult.success) resumes.value = resumeResult.resumes || []
  loading.value = false
}

function openCreate() {
  editingId.value = null
  editForm.value = emptyForm()
  modal.value = 'edit'
}
function openEdit() {
  if (!selected.value) return
  editingId.value = selected.value.id
  editForm.value = {
    company: selected.value.company,
    role_title: selected.value.role_title,
    job_url: selected.value.job_url || '',
    jd_text: selected.value.jd_text || '',
    stage: selected.value.stage,
    resume_id: selected.value.resume_id || null,
    expected_jd_version: selected.value.jd_version?.version || 0,
  }
  modal.value = 'edit'
}
function openOutcome() {
  const outcome = selected.value?.outcome || {}
  outcomeForm.value = { ...emptyOutcome(), ...outcome, tags: (outcome.tags || []).join(', ') }
  modal.value = 'outcome'
}

async function submitEdit() {
  if (!editForm.value.company.trim() || !editForm.value.role_title.trim()) {
    toast('公司和岗位不能为空', 'warn')
    return
  }
  saving.value = true
  const isEditing = editingId.value !== null
  const result = isEditing
    ? await updateApplication(editingId.value, editForm.value)
    : await createApplication(editForm.value)
  saving.value = false
  if (!result.success) { toast(result.message || '保存失败', 'warn'); return }
  selectedId.value = result.application.id
  modal.value = ''
  await load()
  toast(isEditing ? '投递档案已保存' : '投递档案已创建')
}

async function changeStage(stage) {
  if (!selected.value || selected.value.stage === stage || saving.value) return
  saving.value = true
  const result = await updateApplication(selected.value.id, {
    company: selected.value.company,
    role_title: selected.value.role_title,
    job_url: selected.value.job_url || '',
    jd_text: selected.value.jd_text || '',
    stage,
    resume_id: selected.value.resume_id || null,
    expected_jd_version: selected.value.jd_version?.version || 0,
  })
  saving.value = false
  if (!result.success) { toast(result.message || '阶段更新失败', 'warn'); return }
  await load()
  toast(`已更新为「${stageLabel(stage)}」`)
}

async function submitEvent() {
  if (!selected.value || !eventNote.value.trim()) return
  saving.value = true
  const result = await addApplicationEvent(selected.value.id, eventNote.value.trim())
  saving.value = false
  if (!result.success) { toast(result.message || '备注保存失败', 'warn'); return }
  eventNote.value = ''
  applications.value = applications.value.map((item) => item.id === result.application.id ? result.application : item)
  toast('时间线已更新')
}

async function submitOutcome() {
  if (!selected.value) return
  saving.value = true
  const result = await saveApplicationOutcome(selected.value.id, {
    ...outcomeForm.value,
    tags: outcomeForm.value.tags.split(/[,，]/).map((tag) => tag.trim()).filter(Boolean),
  })
  saving.value = false
  if (!result.success) { toast(result.message || '复盘保存失败', 'warn'); return }
  applications.value = applications.value.map((item) => item.id === result.application.id ? result.application : item)
  modal.value = ''
  toast('复盘已保存')
}

async function archiveSelected() {
  if (!selected.value || !confirm(`归档「${selected.value.company} · ${selected.value.role_title}」？`)) return
  const result = await archiveApplication(selected.value.id)
  if (!result.success) { toast(result.message || '归档失败', 'warn'); return }
  selectedId.value = null
  await load()
  toast('投递档案已归档')
}

onMounted(load)
watch(() => route.query.application_id, (id) => { selectedId.value = Number(id) || null })
</script>

<template>
  <div>
    <TopBar crumb="投递记录" folio="卷·04">
      <template #actions>
        <button class="tlink" :disabled="loading" @click="load"><Icon name="refresh" :size="15" />{{ loading ? '刷新中' : '刷新' }}</button>
        <button class="btn btn-dark btn-sm" @click="openCreate"><Icon name="plus" :size="14" />新建档案</button>
      </template>
    </TopBar>

    <div class="page-body application-page">
      <div class="page-head" v-reveal>
        <span class="sec-index">APPLICATIONS</span>
        <h1 class="page-title">投递记录</h1>
      </div>

      <div v-if="error" class="inline-error"><Icon name="alert" :size="16" />{{ error }}<button class="btn btn-ghost btn-sm" @click="load">重新加载</button></div>
      <div v-else-if="loading && !applications.length" class="board-state"><span class="spin"></span>正在加载投递记录…</div>
      <div v-else class="application-layout">
        <section class="application-board" aria-label="投递阶段看板">
          <div class="board-toolbar">
            <span class="mono">{{ applications.length }} 份档案 · 按阶段整理</span>
          </div>
          <div class="stage-grid">
            <div v-for="column in columns" :key="column.key" class="stage-column">
              <div class="stage-head">
                <span class="stage-title"><i class="dot" :class="column.tone"></i>{{ column.label }}</span>
                <span class="stage-count">{{ column.items.length }}</span>
              </div>
              <button v-for="item in column.items" :key="item.id" class="application-card" :class="{ 'is-selected': selectedId === item.id }" @click="selectedId = item.id">
                <span class="card-company">{{ item.company }}</span>
                <strong>{{ item.role_title }}</strong>
                <span class="card-meta">{{ formatDate(item.updated_at) }}</span>
                <span v-if="item.resume_id" class="card-tag"><Icon name="file" :size="12" />{{ resumeTitle(item.resume_id) }}</span>
              </button>
              <div v-if="!column.items.length" class="stage-empty">暂无记录</div>
            </div>
          </div>
        </section>

        <aside class="application-detail" :class="{ 'is-empty': !selected }">
          <template v-if="selected">
            <div class="detail-head">
              <div class="detail-kicker">档案 #{{ selected.id }} · {{ stageLabel(selected.stage) }}</div>
              <div class="detail-title-row"><div><h2>{{ selected.company }}</h2><p>{{ selected.role_title }}</p></div><button class="icon-btn" title="编辑档案" aria-label="编辑档案" @click="openEdit"><Icon name="edit" :size="16" /></button></div>
              <div class="stage-select"><button v-for="stage in STAGES" :key="stage.key" class="stage-chip" :class="{ active: selected.stage === stage.key }" @click="changeStage(stage.key)">{{ stage.label }}</button></div>
            </div>
            <div class="detail-scroll">
              <div class="detail-links">
                <RouterLink class="btn btn-dark btn-sm" :to="{ path: '/choose-job', query: { application_id: selected.id } }"><Icon name="mic" :size="14" />模拟面试</RouterLink>
                <RouterLink class="btn btn-ghost btn-sm" :to="{ path: '/job-matching', query: { application_id: selected.id } }"><Icon name="file" :size="14" />岗位准备</RouterLink>
              </div>
              <div class="detail-links" v-if="selected.job_url || selected.resume_id">
                <a v-if="selected.job_url" :href="selected.job_url" target="_blank" rel="noreferrer"><Icon name="external" :size="14" />打开 JD</a>
                <span v-if="selected.resume_id"><Icon name="file" :size="14" />{{ resumeTitle(selected.resume_id) }}</span>
              </div>
              <section v-if="selected.jd_text" class="detail-section"><div class="section-label">JOB DESCRIPTION</div><p class="jd-preview">{{ selected.jd_text }}</p></section>

              <section class="detail-section">
                <div class="section-row"><div class="section-label">TIMELINE</div><span class="mono">{{ selected.events?.length || 0 }} 条记录</span></div>
                <div class="timeline"><div v-for="event in (selected.events || []).slice().reverse()" :key="event.id" class="timeline-item"><span class="timeline-dot"></span><div><div class="timeline-note">{{ event.note }}</div><div class="mono">{{ formatDate(event.created_at) }}</div></div></div></div>
                <div class="event-compose"><input v-model="eventNote" class="input-box" placeholder="记录一个进展或提醒…" @keyup.enter="submitEvent"><button class="icon-btn" title="添加记录" aria-label="添加记录" :disabled="saving || !eventNote.trim()" @click="submitEvent"><Icon name="send" :size="15" /></button></div>
              </section>

              <section class="detail-section outcome-section">
                <div class="section-row"><div class="section-label">OUTCOME & REFLECTION</div><button class="btn btn-ghost btn-sm" @click="openOutcome"><Icon name="edit" :size="13" />{{ selected.outcome ? '编辑复盘' : '写复盘' }}</button></div>
                <div v-if="selected.outcome" class="outcome-copy"><div v-if="selected.outcome.result"><b>结果</b><span>{{ selected.outcome.result }}</span></div><div v-if="selected.outcome.feedback"><b>反馈</b><span>{{ selected.outcome.feedback }}</span></div><div v-if="selected.outcome.reflection"><b>反思</b><span>{{ selected.outcome.reflection }}</span></div><div v-if="selected.outcome.next_steps"><b>下一步</b><span>{{ selected.outcome.next_steps }}</span></div><div v-if="selected.outcome.tags?.length" class="tags"><span v-for="tag in selected.outcome.tags" :key="tag" class="tag">{{ tag }}</span></div></div>
                <div v-else class="detail-empty">还没有结果复盘，面试结束后把反馈和下一步写下来。</div>
              </section>

              <section v-if="selected.interviews?.length" class="detail-section"><div class="section-label">INTERVIEW REPORTS</div><RouterLink v-for="report in selected.interviews" :key="report.report_id" class="report-link" :to="`/summary/${report.report_id}`"><Icon name="records" :size="14" />{{ report.report_id }}<Icon name="arrowRight" :size="13" /></RouterLink></section>
            </div>
            <div class="detail-foot"><button class="btn btn-ghost btn-sm danger-action" @click="archiveSelected"><Icon name="trash" :size="14" />归档</button></div>
          </template>
          <div v-else class="empty detail-empty-state"><div class="empty-ic"><Icon name="route" :size="30" /></div><div class="empty-title">还没有投递档案</div><div class="empty-sub">新建一份档案，开始记录岗位、面试和复盘。</div><button class="btn btn-dark btn-sm" @click="openCreate"><Icon name="plus" :size="14" />新建档案</button></div>
        </aside>
      </div>
    </div>

    <div v-if="modal" class="mask is-open" @click.self="modal = ''">
      <div class="dialog application-dialog">
        <div class="dialog-head"><div class="dialog-title">{{ modal === 'edit' ? (editingId !== null ? '编辑投递档案' : '新建投递档案') : '面试结果与复盘' }}</div><button class="icon-btn" aria-label="关闭" @click="modal = ''"><Icon name="x" /></button></div>
        <form v-if="modal === 'edit'" class="dialog-body" @submit.prevent="submitEdit">
          <div class="form-grid">
            <label class="field"><span class="field-label">公司</span><input v-model="editForm.company" class="input-box" required maxlength="160" placeholder="例如：星河科技"></label>
            <label class="field"><span class="field-label">岗位</span><input v-model="editForm.role_title" class="input-box" required maxlength="160" placeholder="例如：后端开发工程师"></label>
          </div>
          <div class="form-grid">
            <label class="field"><span class="field-label">阶段</span><select v-model="editForm.stage" class="input-box"><option v-for="stage in STAGES" :key="stage.key" :value="stage.key">{{ stage.label }}</option></select></label>
            <label class="field"><span class="field-label">关联简历</span><select v-model="editForm.resume_id" class="input-box"><option :value="null">不关联</option><option v-for="resume in resumes" :key="resume.resume_id" :value="resume.resume_id">{{ resume.title || `简历 #${resume.resume_id}` }}</option></select></label>
          </div>
          <label class="field"><span class="field-label">JD 链接</span><input v-model="editForm.job_url" class="input-box" type="url" placeholder="https://…"></label>
          <label class="field"><span class="field-label">JD 内容</span><textarea v-model="editForm.jd_text" class="input-box textarea" rows="5" maxlength="20000" placeholder="岗位描述"></textarea></label>
          <div class="dialog-foot"><button type="button" class="btn btn-ghost" @click="modal = ''">取消</button><button class="btn btn-dark" :disabled="saving"><Icon name="save" :size="14" />{{ saving ? '保存中' : '保存档案' }}</button></div>
        </form>
        <form v-else class="dialog-body" @submit.prevent="submitOutcome"><label class="field"><span class="field-label">结果</span><input v-model="outcomeForm.result" class="input-box" maxlength="80" placeholder="例如：进入终面 / 暂未通过 / 等待反馈"></label><label class="field"><span class="field-label">面试官反馈</span><textarea v-model="outcomeForm.feedback" class="input-box textarea" rows="3" maxlength="10000"></textarea></label><label class="field"><span class="field-label">自我反思</span><textarea v-model="outcomeForm.reflection" class="input-box textarea" rows="3" maxlength="10000"></textarea></label><label class="field"><span class="field-label">下一步行动</span><textarea v-model="outcomeForm.next_steps" class="input-box textarea" rows="3" maxlength="10000"></textarea></label><label class="field"><span class="field-label">标签</span><input v-model="outcomeForm.tags" class="input-box" placeholder="例如：系统设计, 表达, STAR"></label><div class="dialog-foot"><button type="button" class="btn btn-ghost" @click="modal = ''">取消</button><button class="btn btn-dark" :disabled="saving"><Icon name="save" :size="14" />{{ saving ? '保存中' : '保存复盘' }}</button></div></form>
      </div>
    </div>
  </div>
</template>

<style scoped>
.application-page { min-width: 0; }
.application-layout { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(330px, .85fr); gap: 24px; align-items: start; }
.application-board, .application-detail { min-width: 0; background: var(--sheet); }
.application-page .page-title { font-size: 28px; letter-spacing: 0; }
.application-detail { border-left: 1px solid var(--line); }
.application-detail :is(h2, p, .timeline-note, .outcome-copy span, .report-link) { overflow-wrap: anywhere; min-width: 0; }
.detail-title-row > div, .timeline-item > div, .event-compose .input-box { min-width: 0; }
.application-page :is(.section-label, .detail-kicker) { letter-spacing: 0; }
.board-toolbar { display:flex; justify-content:space-between; gap:12px; padding:15px 18px; border-bottom:1px solid var(--line-strong); color:var(--ink-3); }
.stage-grid { display:grid; grid-template-columns:repeat(4, minmax(145px, 1fr)); gap:1px; background:var(--line); overflow:hidden; }
.stage-column { min-width:0; min-height:190px; padding:14px 12px; background:var(--paper-deep); }
.stage-head, .section-row, .detail-title-row { display:flex; align-items:center; justify-content:space-between; gap:10px; }
.stage-title { display:flex; align-items:center; gap:8px; font-size:12px; font-weight:700; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.stage-count { font: 11px var(--f-mono); color:var(--ink-4); }
.dot { width:7px; height:7px; border-radius:50%; background:var(--ink-4); flex:none; }.dot.verm{background:var(--vermilion)}.dot.ochre{background:var(--ochre)}.dot.pine{background:var(--pine)}
.application-card { display:block; width:100%; margin-top:10px; padding:12px; text-align:left; border:1px solid var(--line); background:var(--sheet); border-radius:var(--r-1); cursor:pointer; transition: border-color .15s, transform .15s, box-shadow .15s; }
.application-card:hover, .application-card.is-selected { border-color:var(--ink); transform:translateY(-1px); box-shadow:var(--sh-sheet); }.application-card strong,.card-company,.card-meta,.card-tag{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.card-company{font:11px var(--f-mono);color:var(--ink-3);margin-bottom:6px}.application-card strong{font-size:13.5px}.card-meta{font:10px var(--f-mono);color:var(--ink-4);margin-top:10px}.card-tag{font-size:11px;color:var(--ink-3);margin-top:9px;display:flex;align-items:center;gap:5px}.stage-empty{padding:22px 4px;color:var(--ink-4);font:10px var(--f-mono);text-align:center}
.application-detail { position:sticky; top:72px; min-height:650px; display:flex; flex-direction:column; }.detail-head{padding:20px;border-bottom:1px solid var(--line-strong)}.detail-kicker,.section-label{font:10px var(--f-mono);letter-spacing:.16em;color:var(--ink-4);text-transform:uppercase}.detail-title-row{margin-top:12px}.detail-title-row h2{font:900 24px var(--f-display);line-height:1.2}.detail-title-row p{margin-top:5px;color:var(--ink-3);font-size:14px}.stage-select{display:flex;flex-wrap:wrap;gap:6px;margin-top:18px}.stage-chip{padding:6px 9px;border:1px solid var(--line);background:transparent;border-radius:var(--r-1);font-size:11px;color:var(--ink-3);cursor:pointer}.stage-chip.active{border-color:var(--ink);background:var(--ink);color:var(--paper)}.detail-scroll{overflow:auto;min-height:0;flex:1;padding:20px}.detail-links{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:20px}.detail-links a,.detail-links span,.report-link{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--ink-2)}.detail-links a{text-decoration:underline;text-underline-offset:3px}.detail-section{padding:18px 0;border-top:1px solid var(--line)}.detail-section:first-child{border-top:0;padding-top:0}.mono{font:10px var(--f-mono);color:var(--ink-4)}.jd-preview{margin-top:10px;white-space:pre-wrap;max-height:170px;overflow:auto;font-size:13px;line-height:1.8;color:var(--ink-2)}.timeline{margin:14px 0}.timeline-item{display:grid;grid-template-columns:12px 1fr;gap:10px;padding-bottom:15px}.timeline-dot{width:7px;height:7px;margin-top:5px;border-radius:50%;background:var(--vermilion);box-shadow:0 0 0 3px var(--verm-wash)}.timeline-note{font-size:13px;line-height:1.6}.event-compose{display:flex;gap:8px}.event-compose .input-box{padding:9px 11px}.event-compose .icon-btn{flex:none}.outcome-copy>div{display:grid;grid-template-columns:54px 1fr;gap:8px;margin-top:12px;font-size:13px;line-height:1.7}.outcome-copy b{color:var(--ink-3);font-size:11px}.tags{display:flex!important;flex-wrap:wrap;grid-template-columns:none!important}.detail-empty{font-size:13px;line-height:1.7;color:var(--ink-3);margin-top:12px}.report-link{justify-content:space-between;width:100%;padding:10px 0;border-bottom:1px solid var(--line)}.detail-foot{padding:14px 20px;border-top:1px solid var(--line)}.danger-action{color:var(--vermilion)}.detail-empty-state{margin:20px;flex:1;border:0}.board-state,.inline-error{display:flex;align-items:center;justify-content:center;gap:10px;padding:70px 20px;color:var(--ink-3)}.inline-error{justify-content:flex-start;border:1px solid var(--verm-line);background:var(--verm-wash);color:var(--vermilion)}.spin{width:16px;height:16px;border:2px solid var(--line-strong);border-top-color:var(--vermilion);border-radius:50%;display:inline-block}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.application-dialog{max-width:680px;max-height:calc(100vh - 48px);overflow:auto}.application-dialog .field{margin-bottom:16px}.application-dialog .dialog-foot{padding-inline:0;padding-bottom:0}.textarea{resize:vertical}
@media (max-width:1200px){.application-layout{grid-template-columns:1fr}.application-detail{position:static;min-height:520px}.stage-grid{grid-template-columns:repeat(3,minmax(150px,1fr))}}
@media (max-width:700px){.board-toolbar{align-items:flex-start;flex-direction:column}.stage-grid{grid-template-columns:repeat(2,minmax(140px,1fr))}.form-grid{grid-template-columns:1fr}.application-dialog{max-height:calc(100vh - 24px)}.application-page{padding-inline:16px}.detail-title-row h2{font-size:21px}}
@media (max-width:430px){.stage-grid{grid-template-columns:1fr}.topbar-actions .btn{padding-inline:9px}.topbar-actions .btn .ic{display:none}}
</style>
