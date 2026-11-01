<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { uploadResume, parseTextResume, updateResume, confirmResume, getLatestResume } from '../api'
import Icon from '../components/Icon.vue'
import TopBar from '../components/TopBar.vue'
import { toast } from '../composables/useToast'

const router = useRouter()
const fileInput = ref(null)
const isDragging = ref(false)
const textContent = ref('')
const parsing = ref(false)
const parsedData = ref(null)
const errorMsg = ref('')
const barWidth = ref(0)
const logLines = ref([])
const saving = ref(false)
const form = ref(emptyForm())

function emptyForm() {
  return { name: '', phone: '', email: '', location: '', summary: '', skills: [], experience: '', projects: '', education: '' }
}

function syncForm(data) {
  const source = data?.content || data || {}
  form.value = { ...emptyForm(), ...source, skills: [...(source.skills || [])] }
}

async function restoreResume() {
  const stored = sessionStorage.getItem('resumeData')
  if (stored) {
    try {
      const cached = JSON.parse(stored)
      if (cached?.resume_id) {
        parsedData.value = cached
        syncForm(cached)
        return
      }
    } catch (_) {
      sessionStorage.removeItem('resumeData')
    }
  }

  const latest = await getLatestResume()
  if (!latest?.success) return
  parsedData.value = latest
  syncForm(latest)
  sessionStorage.setItem('resumeData', JSON.stringify(latest))
}

onMounted(restoreResume)

const MAX_SIZE = 10 * 1024 * 1024 // 10MB,与后端一致

const skillCount = computed(() => (parsedData.value?.skills || []).length)
const roleLabel = computed(
  () => parsedData.value?.suggested_role_title || parsedData.value?.suggested_role || '未匹配到合适岗位'
)

// 后端未直接返回项目数/匹配方向数,缺失时合理降级
function countLines(text) {
  return text ? text.split('\n').filter((l) => l.trim()).length : 0
}
const projectCount = computed(() => {
  const p = parsedData.value
  if (!p) return null
  if (Array.isArray(p.projects)) return p.projects.length
  if (typeof p.project_count === 'number') return p.project_count
  if (typeof p.projects === 'string' && p.projects.trim()) return countLines(p.projects)
  const ctx = p.resume_context || ''
  const m = ctx.match(/项目经历[:：]\s*([\s\S]*?)(?:\n\n|工作经历[:：]|教育背景[:：]|$)/)
  if (m) {
    const n = countLines(m[1])
    if (n) return n
  }
  return null
})
const directionCount = computed(() => {
  const p = parsedData.value
  if (!p) return null
  if (Array.isArray(p.directions)) return p.directions.length
  if (Array.isArray(p.match_directions)) return p.match_directions.length
  return null
})

let logTimer = null
function stopLog() {
  if (logTimer) {
    clearInterval(logTimer)
    logTimer = null
  }
}
onBeforeUnmount(stopLog)

function startLog(firstLine) {
  logLines.value = []
  barWidth.value = 6
  const steps = [
    firstLine,
    '抽取文本层并清洗版式',
    '结构化字段：姓名 / 技能 / 项目',
    '技能命中题库标签',
    '分析完成，生成岗位匹配建议',
  ]
  let i = 0
  const tick = () => {
    if (i >= steps.length) return
    const pct = [14, 34, 62, 84, 96][i]
    logLines.value.push(steps[i])
    barWidth.value = pct
    i += 1
  }
  tick()
  logTimer = setInterval(tick, 620)
}

function triggerUpload() {
  if (parsing.value) return
  errorMsg.value = ''
  fileInput.value?.click()
}

function validateFile(file) {
  if (!file) return '请选择文件'
  const name = file.name.toLowerCase()
  const isPdf = name.endsWith('.pdf') || file.type === 'application/pdf'
  if (!isPdf) return '仅支持 PDF 文件'
  if (file.size === 0) return '文件为空，请重新选择'
  if (file.size > MAX_SIZE) return `文件过大 (${(file.size / 1024 / 1024).toFixed(1)}MB)，最大支持 10MB`
  return ''
}

async function runParse(fetcher, firstLine) {
  if (parsing.value) return
  errorMsg.value = ''
  parsedData.value = null
  parsing.value = true
  startLog(firstLine)
  try {
    const r = await fetcher()
    stopLog()
    if (r && r.success) {
      barWidth.value = 100
      parsedData.value = r
      syncForm(r)
      sessionStorage.setItem('resumeData', JSON.stringify(r))
      toast(`简历解析完成，已提取 ${(r.skills || []).length} 项技能`)
    } else {
      const msg = (r && r.message) || '简历解析失败'
      errorMsg.value = msg
      toast(msg, 'warn')
    }
  } catch (err) {
    stopLog()
    const msg = `解析失败: ${err.message || '未知错误'}`
    errorMsg.value = msg
    toast(msg, 'warn')
  } finally {
    parsing.value = false
  }
}

function handleFileSelect(e) {
  const file = e.target.files[0]
  if (file) doUpload(file)
  e.target.value = '' // 允许重复选择同一文件
}

function handleDrop(e) {
  isDragging.value = false
  if (parsing.value) return
  const file = e.dataTransfer.files[0]
  if (file) doUpload(file)
}

function doUpload(file) {
  const invalid = validateFile(file)
  if (invalid) {
    errorMsg.value = invalid
    toast(invalid, 'warn')
    return
  }
  runParse(() => uploadResume(file), `打开文件 ${file.name}`)
}

function parseText() {
  const content = textContent.value.trim()
  if (!content) return
  runParse(() => parseTextResume(content), `读取粘贴文本 · ${content.length} 字`)
}

function goToMatching() {
  sessionStorage.setItem('resumeData', JSON.stringify(parsedData.value))
  router.push('/job-matching')
}

async function saveReview(confirm = false) {
  if (!parsedData.value?.resume_id || saving.value) return
  saving.value = true
  errorMsg.value = ''
  try {
    let result = await updateResume(parsedData.value.resume_id, form.value, parsedData.value.title || form.value.name)
    if (result.success && confirm) result = await confirmResume(parsedData.value.resume_id)
    if (!result.success) throw new Error(result.message || '保存失败')
    parsedData.value = result
    syncForm(result)
    sessionStorage.setItem('resumeData', JSON.stringify(result))
    toast(confirm ? '简历已审核确认' : '简历修改已保存')
  } catch (err) {
    errorMsg.value = err.message || '保存失败'
    toast(errorMsg.value, 'warn')
  } finally {
    saving.value = false
  }
}

function reset() {
  parsedData.value = null
  errorMsg.value = ''
  document.querySelector('.dropzone')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}
</script>

<template>
  <div>
    <TopBar crumb="简历匹配" folio="卷·02">
      <template #actions>
        <RouterLink class="tlink" to="/choose-job">跳过，直接选岗<Icon name="arrowRight" /></RouterLink>
      </template>
    </TopBar>

    <div class="page-body">
      <div class="page-head" v-reveal>
        <span class="sec-index">STEP 02 / RESUME</span>
        <h1 class="page-title" style="margin-top:14px">上传简历，交给 AI 读一遍</h1>
        <p class="page-sub">支持 PDF 解析或直接粘贴文本。系统会提取姓名、技能与项目经历，并按技能画像推荐岗位。</p>
      </div>

      <div class="two-col">
        <!-- 左：上传主区 -->
        <div>
          <div
            class="dropzone"
            :class="{ 'is-drag': isDragging, 'is-parsing': parsing }"
            v-reveal="0.05"
            @click="triggerUpload"
            @dragover.prevent="isDragging = true"
            @dragenter.prevent="isDragging = true"
            @dragleave="isDragging = false"
            @drop.prevent="handleDrop"
          >
            <span class="dz-corner tl"></span><span class="dz-corner tr"></span>
            <span class="dz-corner bl"></span><span class="dz-corner br"></span>
            <input ref="fileInput" type="file" accept=".pdf,application/pdf" hidden @click.stop @change="handleFileSelect" />

            <div class="dz-idle">
              <div class="dz-icon"><Icon name="upload" :size="26" /></div>
              <div class="dz-title">拖拽 PDF 到此处，或点击上传</div>
              <div class="dz-hint">AI 解析通常需要 10–20 秒，扫描件将走视觉识别通道</div>
              <span class="btn btn-ghost btn-sm">浏览文件</span>
              <div class="dz-meta">
                <span><Icon name="file" :size="13" />PDF · 最大 10MB</span>
                <span><Icon name="target" :size="13" />自动提取技能</span>
                <span><Icon name="route" :size="13" />匹配岗位</span>
              </div>
            </div>

            <!-- 解析中状态 -->
            <div class="parsing">
              <div class="dz-icon">
                <span class="spin" style="display:block; width:22px; height:22px; border:2px solid var(--line-strong); border-top-color:var(--vermilion); border-radius:50%"></span>
              </div>
              <div class="dz-title">正在解析简历…</div>
              <div class="dz-hint">正在读取 PDF 文本层并抽取结构化信息</div>
              <div class="progress"><div class="progress-fill" :style="{ width: barWidth + '%' }"></div></div>
              <div class="parse-log">
                <div v-for="(line, i) in logLines" :key="i">› {{ line }}</div>
              </div>
            </div>
          </div>

          <div v-if="errorMsg" class="parse-error" v-reveal>
            <Icon name="alert" :size="15" /><span>{{ errorMsg }}</span>
          </div>

          <div class="divider-or"><span>或</span></div>

          <div class="field">
            <label class="field-label" for="paste">直接粘贴简历内容</label>
            <textarea
              id="paste"
              v-model="textContent"
              class="textarea"
              rows="6"
              placeholder="在此粘贴你的简历文本，例如：教育背景、项目经历、技术栈……"
            ></textarea>
          </div>
          <div style="display:flex; gap:14px; align-items:center; flex-wrap:wrap">
            <button class="btn btn-ghost" :disabled="parsing || !textContent.trim()" @click="parseText">
              解析文本<span class="ar"><Icon name="arrowRight" /></span>
            </button>
            <span class="mono">支持 Markdown / 纯文本</span>
          </div>

          <!-- 解析结果 -->
          <div v-if="parsedData" class="sheet sheet-pad result-sheet" v-reveal="0.05">
            <div class="result-head">
              <div>
                <div class="mono" style="margin-bottom:6px">解析完成 · Parsed</div>
                <div class="result-name">{{ parsedData.name || '未识别姓名' }}</div>
              </div>
              <span class="badge pine"><span class="dot pine"></span>已识别 {{ skillCount }} 项技能</span>
            </div>
            <div class="review-grid">
              <label><span>姓名</span><input v-model="form.name" class="input" /></label>
              <label><span>电话</span><input v-model="form.phone" class="input" /></label>
              <label><span>邮箱</span><input v-model="form.email" class="input" /></label>
              <label><span>所在地</span><input v-model="form.location" class="input" /></label>
              <label class="wide"><span>技能（用逗号分隔）</span><input class="input" :value="form.skills.join(', ')" @input="form.skills = $event.target.value.split(/[,，]/).map(s => s.trim()).filter(Boolean)" /></label>
              <label class="wide"><span>个人摘要</span><textarea v-model="form.summary" class="textarea" rows="3"></textarea></label>
              <label class="wide"><span>工作经历</span><textarea v-model="form.experience" class="textarea" rows="4"></textarea></label>
              <label class="wide"><span>项目经历</span><textarea v-model="form.projects" class="textarea" rows="4"></textarea></label>
              <label class="wide"><span>教育背景</span><textarea v-model="form.education" class="textarea" rows="3"></textarea></label>
            </div>
            <div class="audit-row">
              <span v-for="item in parsedData.audit" :key="item.field" class="audit" :class="item.status">
                {{ item.field }} · {{ item.status === 'present' ? '原文可核验' : item.status === 'review' ? '请人工核对' : '未识别' }}
              </span>
            </div>
            <div style="display:flex; gap:14px; margin-top:26px; flex-wrap:wrap">
              <button class="btn btn-ghost" :disabled="saving" @click="saveReview(false)">保存修改</button>
              <button v-if="parsedData.parse_status !== 'reviewed'" class="btn" :disabled="saving" @click="saveReview(true)">确认无误</button>
              <button v-else class="btn" @click="goToMatching">选择岗位与分析 JD<span class="ar"><Icon name="arrowRight" /></span></button>
              <button class="tlink" @click="reset">重新上传</button>
            </div>
          </div>
        </div>

        <!-- 右：建议 -->
        <aside v-reveal="0.14">
          <div class="sheet sheet-pad">
            <div class="mono" style="margin-bottom:8px">Upload Tips</div>
            <h3 class="d4" style="margin-bottom:16px">让解析更准的四个建议</h3>
            <ul class="tips">
              <li><span class="no">01</span><span>使用带文本层的 PDF；扫描图片型简历也可识别，但会稍慢。</span></li>
              <li><span class="no">02</span><span>简历里写清楚技术栈关键词，命中题库标签的概率更高。</span></li>
              <li><span class="no">03</span><span>项目经历建议保留量化结果，面试出题会围绕它展开。</span></li>
              <li><span class="no">04</span><span>确认前请核对结构化字段；低置信内容不会被当作已证实事实。</span></li>
            </ul>
          </div>
          <div class="privacy">
            <Icon name="target" class="ic" :size="16" />
            <span>简历仅用于岗位匹配与出题上下文，按用户隔离存储，不会泄露给第三方。</span>
          </div>
        </aside>
      </div>
    </div>
  </div>
</template>

<style scoped>
  .two-col { display: grid; grid-template-columns: 1.55fr 1fr; gap: clamp(28px, 4vw, 56px); align-items: start; }

  /* ── 上传区 ── */
  .dropzone {
    position: relative;
    border: 1px dashed var(--line-strong);
    border-radius: var(--r-1);
    background: var(--sheet);
    padding: clamp(38px, 6vw, 66px) 28px;
    text-align: center;
    cursor: pointer;
    transition: border-color var(--dur-2) ease, background var(--dur-2) ease, transform var(--dur-2) var(--ease);
  }
  .dropzone:hover { border-color: var(--ink); transform: translateY(-2px); }
  .dropzone.is-drag { border-color: var(--vermilion); background: var(--verm-wash); }
  .dropzone.is-drag .dz-icon { transform: scale(1.08) rotate(-4deg); }
  .dz-icon {
    width: 74px; height: 74px; margin: 0 auto 20px;
    border: 1px solid var(--line-strong);
    display: flex; align-items: center; justify-content: center;
    color: var(--vermilion);
    background: var(--paper);
    transition: transform var(--dur-2) var(--ease);
  }
  .dz-title { font-family: var(--f-display); font-weight: 900; font-size: 20px; margin-bottom: 8px; }
  .dz-hint { font-size: 13px; color: var(--ink-3); margin-bottom: 22px; }
  .dz-meta { display: flex; justify-content: center; gap: 18px; margin-top: 22px; }
  .dz-meta span { font-family: var(--f-mono); font-size: 10.5px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink-4); display: inline-flex; align-items: center; gap: 7px; }
  .dz-corner { position: absolute; width: 12px; height: 12px; border: solid var(--line-strong); }
  .dz-corner.tl { top: 10px; left: 10px; border-width: 1px 0 0 1px; }
  .dz-corner.tr { top: 10px; right: 10px; border-width: 1px 1px 0 0; }
  .dz-corner.bl { bottom: 10px; left: 10px; border-width: 0 0 1px 1px; }
  .dz-corner.br { bottom: 10px; right: 10px; border-width: 0 1px 1px 0; }

  /* 解析中 */
  .parsing { display: none; }
  .dropzone.is-parsing .dz-idle { display: none; }
  .dropzone.is-parsing .parsing { display: block; }
  .progress { margin-top: 18px; }
  .parse-log {
    margin-top: 16px; text-align: left;
    font-family: var(--f-mono); font-size: 11.5px; line-height: 2;
    color: var(--ink-3);
    border-top: 1px solid var(--line); padding-top: 14px;
  }
  .parse-log b { color: var(--vermilion); font-weight: 500; }

  /* 错误提示 */
  .parse-error {
    display: flex; align-items: center; gap: 10px;
    margin-top: 20px; padding: 12px 15px;
    border: 1px solid var(--verm-line); background: var(--verm-wash);
    color: var(--vermilion-deep); font-size: 13px;
  }
  .parse-error .ic { flex-shrink: 0; }

  /* 分隔 */
  .divider-or { display: flex; align-items: center; gap: 18px; margin: 30px 0 24px; }
  .divider-or::before, .divider-or::after { content: ''; flex: 1; height: 1px; background: var(--line); }
  .divider-or span { font-family: var(--f-mono); font-size: 10.5px; letter-spacing: 0.3em; text-transform: uppercase; color: var(--ink-4); }

  /* ── 解析结果 ── */
  .result-sheet { margin-top: 34px; }
  .result-head { display: flex; align-items: baseline; justify-content: space-between; gap: 14px; border-bottom: 1px solid var(--line); padding-bottom: 16px; margin-bottom: 20px; }
  .result-name { font-family: var(--f-display); font-weight: 900; font-size: 22px; }
  .skill-tags { display: flex; flex-wrap: wrap; gap: 8px; }
  .review-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
  .review-grid label { display: grid; gap: 7px; font-size: 12px; color: var(--ink-3); }
  .review-grid .wide { grid-column: 1 / -1; }
  .audit-row { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 18px; }
  .audit { padding: 5px 8px; border: 1px solid var(--line); font: 10px var(--f-mono); color: var(--ink-3); }
  .audit.present { border-color: var(--pine); color: var(--pine); }
  .audit.review { border-color: var(--ochre); color: var(--ochre); }
  .result-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0; border-top: 1px solid var(--line); margin-top: 22px; }
  .result-grid .cell { padding: 16px 18px; border-left: 1px solid var(--line); }
  .result-grid .cell:first-child { border-left: 0; }
  .result-grid .k { font-family: var(--f-mono); font-size: 10px; letter-spacing: 0.18em; text-transform: uppercase; color: var(--ink-4); margin-bottom: 6px; }
  .result-grid .v { font-size: 14px; color: var(--ink); }
  .result-grid .v.num { font-family: var(--f-mono); font-weight: 700; font-size: 20px; }

  /* 右侧栏 */
  .tips li { display: flex; gap: 12px; padding: 14px 0; border-bottom: 1px solid var(--line); font-size: 13.5px; color: var(--ink-2); line-height: 1.75; }
  .tips li:last-child { border-bottom: 0; }
  .tips .no { font-family: var(--f-mono); font-size: 11px; color: var(--vermilion); font-weight: 700; padding-top: 3px; }
  .privacy {
    margin-top: 20px; padding: 16px 18px;
    border: 1px dashed var(--line-strong); background: var(--sheet-2);
    font-size: 12.5px; color: var(--ink-3); line-height: 1.8;
    display: flex; gap: 10px;
  }
  .privacy .ic { color: var(--pine); flex-shrink: 0; margin-top: 2px; }

  @media (max-width: 1080px) { .two-col { grid-template-columns: 1fr; } }
  @media (max-width: 560px) { .review-grid { grid-template-columns: 1fr; } .review-grid .wide { grid-column: auto; } }
</style>
