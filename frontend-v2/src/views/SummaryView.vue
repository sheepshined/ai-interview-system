<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getReport, getReportRadar, kbImportFromReport } from '../api'
import Icon from '../components/Icon.vue'
import TopBar from '../components/TopBar.vue'
import { toast } from '../composables/useToast'

const route = useRoute()
const reportId = computed(() => String(route.params.reportId || ''))

// ── 缓存态（照旧视图：先读 sessionStorage，接口返回后覆盖并写回）──
const roleTitle = ref(sessionStorage.getItem('roleTitle') || '模拟面试')
const rawReport = ref('')
const answeredCount = ref(sessionStorage.getItem('answeredCount') || '0')
const totalCount = ref(sessionStorage.getItem('totalCount') || '0')
const elapsedTime = ref(sessionStorage.getItem('elapsedTime') || '00:00')
const radar = ref(null)

const loading = ref(true)
const loadError = ref('')

// ── 一键入库（v0.8 返回 created/skipped/coverage）──
const kbImporting = ref(false)
const kbImported = ref(false)
const kbImportedCount = ref(0)
const kbCoverage = ref(null)
const kbNotice = ref(null)

// ── 四维（radar.dimensions: accuracy/completeness/depth/clarity）──
const dims = computed(() => {
  const d = radar.value?.dimensions
  if (!d) return []
  return [
    { key: 'accuracy', label: '准确', en: 'Accuracy', value: Number(d.accuracy) || 0 },
    { key: 'completeness', label: '完整', en: 'Completeness', value: Number(d.completeness) || 0 },
    { key: 'depth', label: '深度', en: 'Depth', value: Number(d.depth) || 0 },
    { key: 'clarity', label: '条理', en: 'Clarity', value: Number(d.clarity) || 0 },
  ]
})

// 原型 viewBox 340×300，中心 (170,150)，四轴菱形网格顶点按真实分值等比缩放
const CENTER = { x: 170, y: 150 }
const AXES = {
  top: { x: 170, y: 40 },
  right: { x: 300, y: 150 },
  bottom: { x: 170, y: 260 },
  left: { x: 40, y: 150 },
}
function axisPoint(axis, value) {
  const a = AXES[axis]
  const t = Math.max(0, Math.min(Number(value) || 0, 10)) / 10
  return {
    x: Math.round((CENTER.x + (a.x - CENTER.x) * t) * 10) / 10,
    y: Math.round((CENTER.y + (a.y - CENTER.y) * t) * 10) / 10,
  }
}
const radarShape = computed(() => {
  const d = radar.value?.dimensions
  if (!d) return null
  const top = axisPoint('top', d.accuracy)
  const right = axisPoint('right', d.completeness)
  const bottom = axisPoint('bottom', d.depth)
  const left = axisPoint('left', d.clarity)
  return {
    top, right, bottom, left,
    poly: `${top.x},${top.y} ${right.x},${right.y} ${bottom.x},${bottom.y} ${left.x},${left.y}`,
  }
})

const avgScore = computed(() => {
  const v = radar.value?.avg_score
  return v === undefined || v === null || v === '' ? '—' : v
})
const showTotal = computed(() => radar.value?.total_questions ?? totalCount.value)

const reportNo = computed(() => reportId.value)
const reportDate = computed(() => {
  const ts = radar.value?.timestamp || ''
  const m = ts.match(/^(\d{4})(\d{2})(\d{2})/)
  if (m) return `${m[1]}-${m[2]}-${m[3]}`
  const m2 = reportId.value.match(/_(\d{4})(\d{2})(\d{2})_/)
  return m2 ? `${m2[1]}-${m2[2]}-${m2[3]}` : '—'
})

// ── 分类得分 ──
const categories = computed(() => radar.value?.categories || [])
const maxCatScore = computed(() =>
  categories.value.reduce((m, c) => Math.max(m, Number(c.avg_score) || 0), 0))

// ── 优势 / 待加强（真实字段为题目文本数组）──
const strengths = computed(() => radar.value?.strengths || [])
const weaknesses = computed(() => radar.value?.weaknesses || [])

// ── 学习建议 ──
const suggestions = computed(() => radar.value?.learning_suggestions || [])
const adviceCount = computed(() => suggestions.value.length)
const importStateText = computed(() => {
  if (!kbImported.value) return `尚未入库 · 共 ${adviceCount.value} 条建议`
  const coverage = kbCoverage.value || []
  const sparse = coverage.filter((c) => c.sparse).length
  const covered = coverage.length - sparse
  return `已存入知识库 ${kbImportedCount.value} 条 · ${covered} 项已覆盖${sparse ? ` · ${sparse} 项覆盖不足` : ''}`
})

// ── 好答案 vs 差答案 ──
const compareQuestions = computed(() =>
  (radar.value?.questions || []).filter(
    (q) => (q.good_points && q.good_points.length) || (q.bad_points && q.bad_points.length),
  ))

// ── 报告全文：按行解析（连续 - 行聚成列表）──
function cleanLine(text) {
  return text.replace(/\*\*/g, '').replace(/^>\s?/, '')
}
const reportBlocks = computed(() => {
  if (!rawReport.value) return []
  const blocks = []
  let listBuf = []
  const flush = () => {
    if (listBuf.length) {
      blocks.push({ tag: 'ul', items: listBuf })
      listBuf = []
    }
  }
  for (const raw of rawReport.value.split('\n')) {
    const t = raw.trim()
    if (!t) { flush(); blocks.push({ tag: 'br' }); continue }
    if (t.startsWith('- ') || t.startsWith('* ')) {
      listBuf.push(cleanLine(t.replace(/^[-*]\s+/, '')))
      continue
    }
    if (t.startsWith('### ')) { flush(); blocks.push({ tag: 'h3', text: cleanLine(t.slice(4)) }); continue }
    if (t.startsWith('## ')) { flush(); blocks.push({ tag: 'h2', text: cleanLine(t.slice(3)) }); continue }
    if (t.startsWith('# ')) { flush(); blocks.push({ tag: 'h2', text: cleanLine(t.slice(2)) }); continue }
    if (t.startsWith('---')) { flush(); blocks.push({ tag: 'hr' }); continue }
    flush()
    blocks.push({ tag: 'p', text: cleanLine(t) })
  }
  flush()
  return blocks
})

// ── 一键入库 ──
async function importToKnowledge() {
  if (kbImporting.value || kbImported.value || !suggestions.value.length) return
  kbImporting.value = true
  kbNotice.value = null
  try {
    const items = suggestions.value.map((s) => ({ topic: s.topic, suggestion: s.suggestion }))
    const result = await kbImportFromReport(items, reportId.value)
    if (result.success) {
      kbImportedCount.value = result.created.length
      kbCoverage.value = result.coverage || []
      kbImported.value = true
      const skippedTxt = result.skipped.length ? `，${result.skipped.length} 条同名已存在跳过` : ''
      const sparseCount = kbCoverage.value.filter((c) => c.sparse).length
      const sparseTxt = sparseCount ? `，${sparseCount} 项覆盖不足` : ''
      kbNotice.value = {
        type: 'ok',
        text: `已存入知识库 ${result.created.length} 条${skippedTxt}${sparseTxt}，详见下方「知识库覆盖情况」。`,
      }
      toast(`已存入知识库 ${result.created.length} 条，详见覆盖情况`)
    } else {
      kbNotice.value = { type: 'error', text: result.message || '入库失败，请重试' }
      toast(result.message || '入库失败，请重试', 'warn')
    }
  } catch (e) {
    kbNotice.value = { type: 'error', text: '网络错误，请稍后重试' }
    toast('网络错误，请稍后重试', 'warn')
  } finally {
    kbImporting.value = false
  }
}
function retryImport() {
  kbNotice.value = null
  importToKnowledge()
}

// ── 复制报告 ──
async function copyReport() {
  if (!rawReport.value) return
  try {
    await navigator.clipboard.writeText(rawReport.value)
    toast('报告已复制到剪贴板')
  } catch (e) {
    toast('复制失败，请手动选择报告内容', 'warn')
  }
}

function reload() {
  loading.value = true
  loadError.value = ''
  load()
}

async function load() {
  const cachedId = sessionStorage.getItem('reportId') || ''
  if (cachedId === reportId.value) rawReport.value = sessionStorage.getItem('reportData') || ''
  if (!reportId.value) {
    loading.value = false
    loadError.value = '缺少报告编号'
    return
  }
  try {
    const [reportResult, radarResult] = await Promise.all([
      getReport(reportId.value),
      getReportRadar(reportId.value),
    ])
    const reportOk = reportResult.success && !!reportResult.content
    const radarOk = radarResult.success && !!radarResult.radar
    if (reportOk) {
      rawReport.value = reportResult.content
      sessionStorage.setItem('reportData', reportResult.content)
      sessionStorage.setItem('reportId', reportId.value)
    }
    if (radarOk) {
      radar.value = radarResult.radar
      if (radarResult.radar.role_title) {
        roleTitle.value = radarResult.radar.role_title
        sessionStorage.setItem('roleTitle', radarResult.radar.role_title)
      }
      const total = radarResult.radar.total_questions
      if (total !== undefined && total !== null) {
        totalCount.value = String(total)
        answeredCount.value = String(total)
        sessionStorage.setItem('totalCount', String(total))
        sessionStorage.setItem('answeredCount', String(total))
      }
    }
    if (!reportOk && !radarOk && !rawReport.value) {
      loadError.value = reportResult.message || radarResult.message || '报告加载失败'
    }
  } catch (e) {
    console.warn(`加载报告 ${reportId.value} 失败`, e)
    if (!rawReport.value && !radar.value) loadError.value = '网络错误，报告加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div>
    <TopBar crumb="面试报告" folio="卷·04">
      <template #actions>
        <RouterLink v-if="radar?.application_id" class="tlink" :to="{ path: '/applications', query: { application_id: radar.application_id } }"><Icon name="arrowLeft" />返回投递档案</RouterLink>
        <button class="tlink" @click="copyReport"><Icon name="copy" :size="15" />复制报告</button>
        <RouterLink class="btn btn-sm" :to="{ path: '/choose-job', query: radar?.application_id ? { application_id: radar.application_id } : {} }">再来一次<span class="ar"><Icon name="arrowRight" /></span></RouterLink>
      </template>
    </TopBar>

    <div class="page-body narrow" style="max-width:1080px">
      <!-- 加载中 -->
      <div v-if="loading" class="page-state">
        <span class="spin" style="display:inline-block;width:18px;height:18px;border:2px solid var(--line-strong);border-top-color:var(--vermilion);border-radius:50%"></span>
        正在加载面试报告…
      </div>

      <!-- 接口失败 -->
      <div v-else-if="loadError" class="load-error" v-reveal>
        <span><Icon name="alert" :size="15" />{{ loadError }}</span>
        <button class="btn btn-ghost btn-sm" @click="reload"><Icon name="refresh" :size="14" />重新加载</button>
      </div>

      <!-- 空态 -->
      <div v-else-if="!rawReport && !radar" class="empty" v-reveal>
        <div class="empty-ic"><Icon name="records" :size="30" /></div>
        <div class="empty-title">暂无报告数据</div>
        <div class="empty-sub">未找到该场面试的报告，请返回重新进行一场面试。</div>
        <div style="margin-top:22px">
          <RouterLink class="btn" to="/choose-job">去面试<span class="ar"><Icon name="arrowRight" /></span></RouterLink>
        </div>
      </div>

      <template v-else>
        <!-- ══ 封面 ══ -->
        <div class="cover" v-reveal>
          <div class="cover-score">
            <span class="cap">Avg. Score</span>
            <span class="row">
              <span class="big">{{ avgScore }}</span>
              <span class="of">/ 10</span>
            </span>
          </div>
          <div class="cover-main">
            <h1>面试总结报告</h1>
            <div class="role">
              {{ roleTitle }}<template v-if="radar && radar.difficulty_label"> · {{ radar.difficulty_label }}</template>
            </div>
            <div class="cover-kv">
              <div><span class="k">Report №</span><span class="v report-no">{{ reportNo }}</span></div>
              <div><span class="k">日期</span><span class="v">{{ reportDate }}</span></div>
              <div><span class="k">题量</span><span class="v">{{ showTotal }}</span></div>
              <div><span class="k">用时</span><span class="v">{{ elapsedTime }}</span></div>
            </div>
          </div>
          <div class="cover-stamp"><span class="stamp stamp-lg">已评估</span></div>
        </div>

        <div class="kpi">
          <div class="cell"><div class="n">{{ answeredCount }}</div><div class="l">回答题数</div></div>
          <div class="cell"><div class="n">{{ showTotal }}</div><div class="l">总题数</div></div>
          <div class="cell"><div class="n">{{ avgScore }}</div><div class="l">平均分</div></div>
          <div class="cell"><div class="n">{{ elapsedTime }}</div><div class="l">用时</div></div>
        </div>

        <!-- ══ §1 能力雷达 ══ -->
        <section v-if="radar && radarShape" class="chapter">
          <div class="chapter-head" v-reveal>
            <span class="sec">§ 01</span><h2>四维能力雷达</h2>
            <span class="hint">Accuracy / Completeness / Depth / Clarity</span>
          </div>

          <div class="duo">
            <div class="sheet radar-box" v-reveal="0.05">
              <svg viewBox="0 0 340 300" aria-hidden="true">
                <!-- 网格 -->
                <g fill="none" stroke="rgba(23,21,15,.16)">
                  <path d="M170 40 L300 150 L170 260 L40 150 Z" />
                  <path d="M170 70 L270 150 L170 230 L70 150 Z" />
                  <path d="M170 100 L240 150 L170 200 L100 150 Z" />
                  <path d="M170 130 L210 150 L170 170 L130 150 Z" />
                </g>
                <g stroke="rgba(23,21,15,.14)"><path d="M170 40v220M40 150h260" /></g>
                <!-- 数据多边形（真实分值等比缩放） -->
                <polygon :points="radarShape.poly" fill="rgba(217,58,31,.13)" stroke="#D93A1F" stroke-width="1.6" />
                <g fill="#D93A1F">
                  <circle :cx="radarShape.top.x" :cy="radarShape.top.y" r="3.4" />
                  <circle :cx="radarShape.right.x" :cy="radarShape.right.y" r="3.4" />
                  <circle :cx="radarShape.bottom.x" :cy="radarShape.bottom.y" r="3.4" />
                  <circle :cx="radarShape.left.x" :cy="radarShape.left.y" r="3.4" />
                </g>
                <g class="radar-axis">
                  <text x="170" y="26" text-anchor="middle">准确 ACCURACY</text>
                  <text x="330" y="154" text-anchor="end">完整</text>
                  <text x="170" y="284" text-anchor="middle">深度 DEPTH</text>
                  <text x="10" y="154">条理</text>
                </g>
                <g class="radar-val">
                  <text x="170" y="60" text-anchor="middle">{{ dims[0]?.value }}</text>
                  <text x="308" y="164" text-anchor="end">{{ dims[1]?.value }}</text>
                  <text x="170" y="230" text-anchor="middle">{{ dims[2]?.value }}</text>
                  <text x="34" y="164">{{ dims[3]?.value }}</text>
                </g>
              </svg>
            </div>

            <div v-reveal="0.12">
              <div class="dims">
                <div v-for="d in dims" :key="d.key" class="dim-line">
                  <div class="top">
                    <span class="name">{{ d.label }}<small>{{ d.en }}</small></span>
                    <span class="val" :class="{ low: d.value < 7 }">{{ d.value }}</span>
                  </div>
                  <div class="progress">
                    <div class="progress-fill bar-anim" :style="{ '--w': d.value / 10 }"></div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- ══ §2 分类得分 ══ -->
        <section v-if="categories.length" class="chapter">
          <div class="chapter-head" v-reveal>
            <span class="sec">§ 02</span><h2>分类得分</h2>
            <span class="hint">按题目类别聚合</span>
          </div>
          <div v-reveal>
            <div v-for="cat in categories" :key="cat.category" class="cat-row">
              <span class="c">{{ cat.category }}</span>
              <span class="track">
                <i class="bar-anim" :class="{ top: Number(cat.avg_score) === maxCatScore }"
                   :style="{ '--w': (Number(cat.avg_score) || 0) / 10 }"></i>
              </span>
              <span class="v">{{ cat.avg_score }}</span>
              <span class="n">{{ cat.count }} 题</span>
            </div>
          </div>
        </section>

        <!-- ══ §3 强弱项 ══ -->
        <section v-if="strengths.length || weaknesses.length" class="chapter">
          <div class="chapter-head" v-reveal>
            <span class="sec">§ 03</span><h2>优势与待加强</h2>
          </div>
          <div class="sw" v-reveal>
            <div v-if="strengths.length" class="sw-col good">
              <div class="sw-title"><Icon name="thumbsUp" :size="15" />优势项</div>
              <ul>
                <li v-for="(s, i) in strengths" :key="i">{{ s }}</li>
              </ul>
            </div>
            <div v-if="weaknesses.length" class="sw-col bad">
              <div class="sw-title"><Icon name="thumbsDown" :size="15" />待加强</div>
              <ul>
                <li v-for="(w, i) in weaknesses" :key="i">{{ w }}</li>
              </ul>
            </div>
          </div>
        </section>

        <!-- ══ §4 学习建议 ══ -->
        <section v-if="suggestions.length" class="chapter">
          <div class="chapter-head" v-reveal>
            <span class="sec">§ 04</span><h2>学习建议</h2>
            <span class="hint">可一键存入知识库</span>
          </div>

          <div class="advice-toolbar" v-reveal>
            <button
              class="btn btn-sm"
              :class="{ 'btn-ghost': kbImported, 'is-disabled': kbImporting || kbImported }"
              :disabled="kbImporting || kbImported"
              @click="importToKnowledge"
            >
              <Icon :name="kbImported ? 'check' : (kbImporting ? 'refresh' : 'download')" :size="15" />
              {{ kbImported ? `已入库 ${kbImportedCount} 条` : (kbImporting ? '入库中…' : '一键存入知识库') }}
            </button>
            <span class="mono">{{ importStateText }}</span>
          </div>

          <!-- 入库结果提示条（可重试） -->
          <div v-if="kbNotice" class="kb-notice" :class="kbNotice.type">
            <Icon :name="kbNotice.type === 'ok' ? 'checkCircle' : 'alert'" :size="14" />
            <span>{{ kbNotice.text }}</span>
            <button v-if="kbNotice.type === 'error'" class="kb-notice-close" @click="retryImport">重试入库</button>
          </div>

          <!-- 覆盖情况 -->
          <div v-if="kbCoverage" class="coverage" v-reveal>
            <h5><Icon name="target" :size="14" />知识库覆盖情况</h5>
            <ul>
              <li v-for="c in kbCoverage" :key="c.topic">
                <template v-if="c.matched && c.matched.length">
                  <span class="ic ok"><Icon name="checkCircle" :size="14" /></span>
                  <span>
                    {{ c.topic }}：已有 {{ c.matched.length }} 条相关笔记
                    <RouterLink v-for="m in c.matched" :key="m.note_id" :to="`/knowledge/note/${m.note_id}`">「{{ m.title }}」</RouterLink>
                  </span>
                </template>
                <template v-else>
                  <span class="ic warn"><Icon name="alert" :size="14" /></span>
                  <span>{{ c.topic }}：知识库中无相关内容，<RouterLink to="/knowledge">建议导入对应资料 →</RouterLink></span>
                </template>
              </li>
            </ul>
          </div>

          <div class="advice" v-reveal>
            <div v-for="(item, idx) in suggestions" :key="idx" class="advice-item">
              <span class="no">{{ String(idx + 1).padStart(2, '0') }}</span>
              <div>
                <h4>{{ item.topic }}</h4>
                <p>{{ item.suggestion }}</p>
              </div>
              <div class="side">
                <div class="score">{{ item.score }}</div>
                <div class="cat">{{ item.category }}</div>
              </div>
            </div>
          </div>
        </section>

        <!-- ══ §5 好差答案 ══ -->
        <section v-if="compareQuestions.length" class="chapter">
          <div class="chapter-head" v-reveal>
            <span class="sec">§ 05</span><h2>好答案 vs 差答案</h2>
            <span class="hint">按题对照</span>
          </div>

          <div v-for="(q, idx) in compareQuestions" :key="idx" class="compare" v-reveal>
            <div class="q"><b>Q{{ q.round }}</b>{{ q.question }}</div>
            <div class="compare-grid">
              <div v-if="q.good_points && q.good_points.length" class="cmp good">
                <h5><Icon name="thumbsUp" :size="13" />高分答案特征</h5>
                <ul>
                  <li v-for="(p, i) in q.good_points" :key="i">{{ p }}</li>
                </ul>
              </div>
              <div v-if="q.bad_points && q.bad_points.length" class="cmp bad">
                <h5><Icon name="thumbsDown" :size="13" />低分踩坑特征</h5>
                <ul>
                  <li v-for="(p, i) in q.bad_points" :key="i">{{ p }}</li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        <!-- ══ §6 报告全文 ══ -->
        <section v-if="rawReport" class="chapter">
          <div class="chapter-head" v-reveal>
            <span class="sec">§ 06</span><h2>报告全文</h2>
            <span class="hint">Markdown · 可复制</span>
          </div>
          <div id="reportDoc" class="doc" v-reveal>
            <template v-for="(b, i) in reportBlocks" :key="i">
              <h2 v-if="b.tag === 'h2'">{{ b.text }}</h2>
              <h3 v-else-if="b.tag === 'h3'">{{ b.text }}</h3>
              <hr v-else-if="b.tag === 'hr'" />
              <ul v-else-if="b.tag === 'ul'">
                <li v-for="(it, j) in b.items" :key="j">{{ it }}</li>
              </ul>
              <p v-else-if="b.tag === 'br'"></p>
              <p v-else>{{ b.text }}</p>
            </template>
          </div>
        </section>

        <div class="actions">
          <RouterLink class="btn" to="/choose-job">再来一次面试<span class="ar"><Icon name="arrowRight" /></span></RouterLink>
          <button class="btn btn-ghost" @click="copyReport">复制报告全文</button>
          <RouterLink class="tlink" to="/interview-records" style="align-self:center">查看逐题记录<span><Icon name="arrowRight" :size="15" /></span></RouterLink>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
  /* ── 报告封面 ── */
  .cover {
    position: relative;
    border: 1px solid var(--line-strong);
    background: var(--sheet);
    padding: clamp(26px, 4vw, 46px);
    display: grid;
    grid-template-columns: auto 1fr auto;
    gap: clamp(24px, 4vw, 56px);
    align-items: center;
    overflow: hidden;
  }
  .cover::before {
    content: ''; position: absolute; inset: 0; pointer-events: none;
    background: radial-gradient(560px 260px at 100% 0%, var(--verm-wash), transparent 68%);
  }
  .cover-score { display: flex; flex-direction: column; gap: 10px; position: relative; }
  .cover-score .row { display: flex; align-items: flex-end; gap: 10px; }
  .cover-score .big { font-family: var(--f-mono); font-weight: 700; font-size: clamp(64px, 8vw, 108px); line-height: 0.86; letter-spacing: -0.05em; }
  .cover-score .of { font-family: var(--f-mono); font-size: 15px; color: var(--ink-3); padding-bottom: 8px; }
  .cover-score .cap { font-family: var(--f-mono); font-size: 10px; letter-spacing: 0.24em; text-transform: uppercase; color: var(--ink-4); }
  .cover-main { position: relative; }
  .cover-main h1 { font-size: clamp(24px, 2.6vw, 34px); }
  .cover-main .role { margin-top: 10px; font-size: 14.5px; color: var(--ink-2); }
  .cover-kv { display: flex; gap: 26px; margin-top: 18px; padding-top: 16px; border-top: 1px solid var(--line); flex-wrap: wrap; }
  .cover-kv .k { font-family: var(--f-mono); font-size: 10px; letter-spacing: 0.16em; text-transform: uppercase; color: var(--ink-4); display: block; margin-bottom: 4px; }
  .cover-kv .v { font-family: var(--f-mono); font-weight: 700; font-size: 17px; }
  .cover-kv .report-no { font-size: 13px; max-width: 300px; overflow-wrap: anywhere; }
  .cover-stamp { position: relative; }

  /* ── 指标格 ── */
  .kpi { display: grid; grid-template-columns: repeat(4, 1fr); border: 1px solid var(--line); border-top: 0; background: var(--sheet-2); }
  .kpi .cell { padding: 20px 24px; border-left: 1px solid var(--line); }
  .kpi .cell:first-child { border-left: 0; }
  .kpi .n { font-family: var(--f-mono); font-weight: 700; font-size: 26px; letter-spacing: -0.03em; }
  .kpi .l { font-size: 12.5px; color: var(--ink-3); margin-top: 4px; }

  /* ── 章节 ── */
  .chapter { margin-top: clamp(34px, 5vw, 62px); }
  .chapter-head {
    display: flex; align-items: baseline; gap: 14px;
    padding-bottom: 14px; margin-bottom: 22px;
    border-bottom: 1px solid var(--line-strong);
  }
  .chapter-head .sec { font-family: var(--f-mono); font-size: 11px; font-weight: 700; letter-spacing: 0.16em; color: var(--vermilion); }
  .chapter-head h2 { font-size: clamp(19px, 2vw, 24px); }
  .chapter-head .hint { margin-left: auto; font-family: var(--f-mono); font-size: 10px; letter-spacing: 0.16em; text-transform: uppercase; color: var(--ink-4); }

  .duo { display: grid; grid-template-columns: 0.9fr 1.1fr; gap: clamp(26px, 4vw, 54px); align-items: start; }

  /* 雷达大图 */
  .radar-box { padding: 26px; text-align: center; }
  .radar-box svg { width: 100%; max-width: 330px; margin: 0 auto; }
  .radar-axis { font-family: var(--f-mono); font-size: 10.5px; fill: var(--ink-3); letter-spacing: 0.08em; }
  .radar-val { font-family: var(--f-mono); font-size: 12px; font-weight: 700; fill: var(--ink); }

  .dims { display: flex; flex-direction: column; }
  .dim-line { padding: 18px 4px; border-bottom: 1px solid var(--line); }
  .dim-line:first-child { border-top: 1px solid var(--line); }
  .dim-line .top { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
  .dim-line .name { font-family: var(--f-display); font-weight: 900; font-size: 16px; }
  .dim-line .name small { font-family: var(--f-mono); font-size: 10px; letter-spacing: 0.16em; color: var(--ink-4); margin-left: 8px; font-weight: 500; text-transform: uppercase; }
  .dim-line .val { font-family: var(--f-mono); font-weight: 700; font-size: 18px; }
  .dim-line .val.low { color: var(--vermilion); }
  .dim-line .note { margin-top: 9px; font-size: 13px; color: var(--ink-3); line-height: 1.8; }

  /* 分类得分条 */
  .cat-row { display: grid; grid-template-columns: 150px 1fr 66px 52px; gap: 16px; align-items: center; padding: 13px 4px; border-bottom: 1px solid var(--line); }
  .cat-row .c { font-size: 13.5px; color: var(--ink-2); }
  .cat-row .track { height: 8px; background: var(--line-soft); position: relative; }
  .cat-row .track i { position: absolute; inset: 0 auto 0 0; background: var(--ink); }
  .cat-row .track i.bar-anim { width: 100%; }
  .cat-row .track i.top { background: var(--vermilion); }
  .cat-row .v { font-family: var(--f-mono); font-weight: 700; font-size: 14px; text-align: right; }
  .cat-row .n { font-family: var(--f-mono); font-size: 11px; color: var(--ink-4); text-align: right; }

  /* 强弱项 */
  .sw { display: grid; grid-template-columns: 1fr 1fr; gap: 0; border: 1px solid var(--line); background: var(--sheet); }
  .sw-col { padding: 24px 26px; }
  .sw-col + .sw-col { border-left: 1px solid var(--line); }
  .sw-title { display: flex; align-items: center; gap: 9px; font-family: var(--f-mono); font-size: 11px; font-weight: 700; letter-spacing: 0.16em; text-transform: uppercase; margin-bottom: 16px; }
  .sw-title.good { color: var(--pine); }
  .sw-title.bad { color: var(--vermilion); }
  .sw li { position: relative; padding: 9px 0 9px 20px; font-size: 13.5px; color: var(--ink-2); line-height: 1.75; border-bottom: 1px dashed var(--line); }
  .sw li:last-child { border-bottom: 0; }
  .sw li::before { content: ''; position: absolute; left: 0; top: 17px; width: 8px; height: 1px; background: var(--ink-4); }
  .sw-col.good li::before { background: var(--pine); }
  .sw-col.bad li::before { background: var(--vermilion); }

  /* 学习建议 */
  .advice-toolbar { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; margin-bottom: 18px; }
  .advice { border: 1px solid var(--line); background: var(--sheet); }
  .advice-item { display: grid; grid-template-columns: 46px 1fr auto; gap: 18px; padding: 20px 22px; border-bottom: 1px solid var(--line); align-items: start; }
  .advice-item:last-child { border-bottom: 0; }
  .advice-item .no { font-family: var(--f-mono); font-weight: 700; font-size: 15px; color: var(--vermilion); padding-top: 2px; }
  .advice-item h4 { font-size: 15.5px; margin-bottom: 6px; }
  .advice-item p { font-size: 13.5px; color: var(--ink-2); line-height: 1.85; }
  .advice-item .side { text-align: right; }
  .advice-item .score { font-family: var(--f-mono); font-weight: 700; font-size: 15px; }
  .advice-item .cat { font-family: var(--f-mono); font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink-4); margin-top: 4px; }

  /* 覆盖情况 */
  .coverage { border: 1px dashed var(--line-strong); background: var(--sheet-2); padding: 18px 22px; margin-bottom: 18px; }
  .coverage h5 { font-family: var(--f-mono); font-size: 10.5px; letter-spacing: 0.18em; text-transform: uppercase; color: var(--ink-3); margin-bottom: 12px; display: flex; align-items: center; gap: 8px; }
  .coverage li { display: flex; gap: 10px; font-size: 13px; padding: 6px 0; color: var(--ink-2); align-items: flex-start; }
  .coverage .ic.ok { color: var(--pine); }
  .coverage .ic.warn { color: var(--ochre); }
  .coverage a { color: var(--ink); border-bottom: 1px solid var(--line-strong); margin-right: 6px; }
  .coverage a:hover { color: var(--vermilion); border-color: var(--vermilion); }

  /* 入库提示条 */
  .kb-notice {
    display: flex; align-items: center; gap: 8px;
    margin-bottom: 18px; padding: 10px 14px;
    border-radius: var(--r-1); font-size: 13px; line-height: 1.5;
  }
  .kb-notice.ok { background: var(--pine-wash); border: 1px solid rgba(46,107,80,.3); color: var(--pine); }
  .kb-notice.error { background: var(--verm-wash); border: 1px solid var(--verm-line); color: var(--vermilion-deep); }
  .kb-notice-close {
    margin-left: auto; flex-shrink: 0; cursor: pointer;
    border: 1px solid currentColor; background: none; color: inherit;
    border-radius: var(--r-1); padding: 3px 10px; font-size: 12px;
  }

  /* 好差答案 */
  .compare { border: 1px solid var(--line); background: var(--sheet); padding: 22px 24px; margin-bottom: 18px; }
  .compare .q { font-size: 14px; color: var(--ink-2); margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--line); }
  .compare .q b { font-family: var(--f-mono); font-size: 11px; letter-spacing: 0.14em; color: var(--vermilion); margin-right: 8px; }
  .compare-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
  .cmp { padding: 16px 18px; border-left: 2px solid; }
  .cmp.good { border-color: var(--pine); background: var(--pine-wash); }
  .cmp.bad { border-color: var(--vermilion); background: var(--verm-wash); }
  .cmp h5 { display: flex; align-items: center; gap: 7px; font-family: var(--f-mono); font-size: 10.5px; letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 10px; }
  .cmp.good h5 { color: var(--pine); }
  .cmp.bad h5 { color: var(--vermilion); }
  .cmp li { font-size: 13px; color: var(--ink-2); line-height: 1.8; padding: 3px 0 3px 14px; position: relative; }
  .cmp li::before { content: '·'; position: absolute; left: 2px; color: var(--ink-4); }

  /* 报告全文 */
  .doc { border: 1px solid var(--line); background: var(--sheet); padding: clamp(24px, 3.4vw, 46px); }
  .doc h2 { font-size: 19px; margin: 30px 0 12px; padding-bottom: 8px; border-bottom: 1px solid var(--line); }
  .doc h2:first-child { margin-top: 0; }
  .doc h3 { font-size: 15.5px; margin: 20px 0 8px; color: var(--ink-2); }
  .doc p { font-size: 14px; line-height: 2; color: var(--ink-2); margin-bottom: 10px; }
  .doc li { font-size: 14px; line-height: 2; color: var(--ink-2); padding-left: 18px; position: relative; }
  .doc li::before { content: '◇'; position: absolute; left: 0; font-size: 10px; color: var(--vermilion); top: 4px; }

  .actions { display: flex; gap: 14px; justify-content: center; flex-wrap: wrap; margin-top: 46px; }

  /* 加载 / 失败 */
  .page-state {
    padding: 96px 24px;
    display: flex; align-items: center; justify-content: center; gap: 10px;
    color: var(--ink-3); font-size: 13.5px;
  }
  .load-error {
    padding: 16px 20px;
    display: flex; align-items: center; justify-content: space-between; gap: 14px; flex-wrap: wrap;
    border: 1px solid var(--verm-line); background: var(--verm-wash);
    color: var(--vermilion-deep); font-size: 13px;
  }
  .load-error > span { display: inline-flex; align-items: center; gap: 9px; }

  @media (max-width: 1080px) {
    .duo { grid-template-columns: 1fr; }
    .cover { grid-template-columns: auto 1fr auto; gap: clamp(18px, 3vw, 34px); }
    .cover-stamp .stamp { --sz: 84px; font-size: 19px; }
    .cover-score .big { font-size: clamp(52px, 7vw, 76px); }
  }
  @media (max-width: 860px) {
    .cover { grid-template-columns: 1fr; gap: 16px; }
    .cover-stamp { position: absolute; top: 20px; right: 20px; }
    .cover-stamp .stamp { --sz: 70px; font-size: 17px; }
  }
  @media (max-width: 720px) {
    .cover-main .role { font-size: 13.5px; line-height: 1.8; }
    .cover-kv { gap: 18px; }
    .kpi { grid-template-columns: 1fr 1fr; }
    .kpi .cell:nth-child(3) { border-left: 0; border-top: 1px solid var(--line); }
    .kpi .cell:nth-child(4) { border-top: 1px solid var(--line); }
    .sw { grid-template-columns: 1fr; }
    .sw-col + .sw-col { border-left: 0; border-top: 1px solid var(--line); }
    .compare-grid { grid-template-columns: 1fr; }
    .cat-row { grid-template-columns: 110px 1fr 60px; }
    .cat-row .n { display: none; }
    .advice-item { grid-template-columns: 32px 1fr; }
    .advice-item .side { grid-column: 2; text-align: left; }
  }
</style>
