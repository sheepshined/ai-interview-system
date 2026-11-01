<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { getGrowth } from '../api'
import Icon from '../components/Icon.vue'
import TopBar from '../components/TopBar.vue'
import { animateValue } from '../composables/useCountUp'

const isTouch = typeof matchMedia !== 'undefined' && matchMedia('(hover: none)').matches

const growth = ref(null)
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await getGrowth()
    if (res.success) growth.value = res.growth
    else error.value = res.message || '成长档案加载失败'
  } catch (e) {
    error.value = e?.message || '成长档案加载失败'
  }
  loading.value = false
}
onMounted(load)

const summary = computed(() => growth.value?.summary || {})
const timeline = computed(() => growth.value?.timeline || [])
const categories = computed(() => growth.value?.categories || [])
const difficulty = computed(() => growth.value?.difficulty_distribution || { 1: 0, 2: 0, 3: 0 })
const hasData = computed(() => timeline.value.length > 0)

// ── 总览数字滚动 (数据到位即触发; 该区块位于首屏, 加载完成必然可见) ──
const disp = ref({ reports: '0', questions: '0', avg: '0.0', trend: '—' })
watch(growth, (g) => {
  if (!g) return
  const s = g.summary || {}
  // 从当前显示值续滚, 避免点"刷新"时数字 28→0→28 跳水
  animateValue(s.total_reports || 0, (v) => (disp.value.reports = String(Math.round(v))),
               { from: Number(disp.value.reports) || 0 })
  animateValue(s.total_questions || 0, (v) => (disp.value.questions = String(Math.round(v))),
               { from: Number(disp.value.questions) || 0 })
  animateValue(s.overall_avg || 0, (v) => (disp.value.avg = v.toFixed(1)),
               { from: Number(disp.value.avg) || 0 })
  if (s.recent_delta !== null && s.recent_delta !== undefined) {
    const target = Number(s.recent_delta)
    const prevAbs = Math.abs(parseFloat(disp.value.trend)) || 0
    animateValue(Math.abs(target), (v) => {
      disp.value.trend = `${target > 0 ? '+' : target < 0 ? '-' : ''}${v.toFixed(1)}`
    }, { from: target === 0 ? 0 : prevAbs })
  } else {
    disp.value.trend = '—'
  }
}, { immediate: true })

const trendDelta = computed(() => summary.value.recent_delta)
const trendTone = computed(() => {
  if (trendDelta.value === null || trendDelta.value === undefined) return 'muted'
  return Number(trendDelta.value) > 0 ? 'pine' : (Number(trendDelta.value) < 0 ? 'verm' : 'ochre')
})

// ── 均分走势图 (SVG, viewBox 720x230, 描线入场) ──
const CHART_W = 720
const CHART_H = 230
const CHART_PAD = { l: 34, r: 16, t: 18, b: 30 }
const chartPoints = computed(() => {
  const items = timeline.value
  if (!items.length) return []
  const min = 0
  const max = 10
  const iw = CHART_W - CHART_PAD.l - CHART_PAD.r
  const ih = CHART_H - CHART_PAD.t - CHART_PAD.b
  const step = items.length > 1 ? iw / (items.length - 1) : 0
  return items.map((t, i) => {
    const v = Math.max(min, Math.min(max, Number(t.avg_score) || 0))
    const x = CHART_PAD.l + (items.length > 1 ? i * step : iw / 2)
    const y = CHART_PAD.t + ih - ((v - min) / (max - min || 1)) * ih
    return { x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10, v: t.avg_score, date: t.date, label: t.role_title }
  })
})
const linePath = computed(() =>
  chartPoints.value.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x} ${p.y}`).join(' '))
const chartFoot = computed(() => {
  const pts = chartPoints.value
  if (!pts.length) return null
  const maxP = pts.reduce((m, p) => (Number(p.v) > Number(m.v) ? p : m), pts[0])
  const last = pts[pts.length - 1]
  const avg = Math.round((pts.reduce((s2, p) => s2 + Number(p.v || 0), 0) / pts.length) * 10) / 10
  return { max: maxP.v, maxDate: maxP.date, last: last.v, lastDate: last.date, avg }
})

// 悬停十字线与单场浮层 (P1-5: 兑现"悬停数据点查看单场"的承诺)
const hoverIdx = ref(-1)
const hoverP = computed(() => (hoverIdx.value >= 0 ? chartPoints.value[hoverIdx.value] : null))
function onChartMove(e) {
  const pts = chartPoints.value
  if (pts.length < 2) return
  const rect = e.currentTarget.getBoundingClientRect()
  const x = ((e.clientX - rect.left) / rect.width) * CHART_W
  const step = (CHART_W - CHART_PAD.l - CHART_PAD.r) / (pts.length - 1)
  const idx = Math.round((x - CHART_PAD.l) / step)
  hoverIdx.value = Math.max(0, Math.min(pts.length - 1, idx))
}
const areaPath = computed(() => {
  if (!chartPoints.value.length) return ''
  const base = CHART_H - CHART_PAD.b
  const first = chartPoints.value[0]
  const last = chartPoints.value[chartPoints.value.length - 1]
  return `${linePath.value} L${last.x} ${base} L${first.x} ${base} Z`
})

// ── 四维雷达叠加: 最新一场 vs 个人均值 (从中心展开) ──
const DIM_DEFS = [
  { key: 'accuracy', label: '准确' },
  { key: 'completeness', label: '完整' },
  { key: 'depth', label: '深度' },
  { key: 'clarity', label: '条理' },
]
const CENTER = { x: 150, y: 128 }
const AXES = {
  top: { x: 150, y: 30 },
  right: { x: 258, y: 128 },
  bottom: { x: 150, y: 226 },
  left: { x: 42, y: 128 },
}
function axisPoint(axis, value) {
  const a = AXES[axis]
  const t = Math.max(0, Math.min(Number(value) || 0, 10)) / 10
  return {
    x: Math.round((CENTER.x + (a.x - CENTER.x) * t) * 10) / 10,
    y: Math.round((CENTER.y + (a.y - CENTER.y) * t) * 10) / 10,
  }
}
function polyFor(values) {
  const d = DIM_DEFS.reduce((acc, def, i) => ({ ...acc, [def.key]: values[i] }), {})
  const pts = [
    axisPoint('top', d.accuracy),
    axisPoint('right', d.completeness),
    axisPoint('bottom', d.depth),
    axisPoint('left', d.clarity),
  ]
  return pts.map((p) => `${p.x},${p.y}`).join(' ')
}
const latestDims = computed(() => {
  const last = timeline.value[timeline.value.length - 1]
  if (!last) return null
  return DIM_DEFS.map((def) => Number(last.dimensions?.[def.key]) || 0)
})
const averageDims = computed(() => {
  if (!timeline.value.length) return null
  return DIM_DEFS.map((def) => {
    const vals = timeline.value.map((t) => Number(t.dimensions?.[def.key]) || 0)
    return Math.round((vals.reduce((s, v) => s + v, 0) / vals.length) * 10) / 10
  })
})
const latestPoly = computed(() => (latestDims.value ? polyFor(latestDims.value) : ''))
const averagePoly = computed(() => (averageDims.value ? polyFor(averageDims.value) : ''))

// ── 分类掌握度 ──
function scoreTone(score) {
  if (score >= 7) return 'pine'
  if (score >= 5) return 'ochre'
  return 'verm'
}

// ── 场次明细 ──
const recentReports = computed(() => [...timeline.value].reverse().slice(0, 12))
const difficultyTotal = computed(() =>
  Object.values(difficulty.value).reduce((s, v) => s + Number(v || 0), 0))

function difficultyLabel(label) { return label || '—' }
</script>

<template>
  <div>
    <TopBar crumb="成长档案" folio="卷·05">
      <template #actions>
        <button class="tlink" :disabled="loading" @click="load">
          <Icon name="refresh" :size="15" />{{ loading ? '刷新中' : '刷新' }}
        </button>
      </template>
    </TopBar>

    <div class="page-body growth-page">
      <div class="page-head" v-reveal>
        <span class="sec-index">GROWTH DOSSIER</span>
        <h1 class="page-title">成长<em class="mark">档案</em></h1>
        <hr class="rv-hr head-rule" />
        <p class="page-sub">
          跨场次面试报告的确定性聚合 · 全部数字可在报告原文中复核
          <template v-if="summary.first_date"> · <span class="nowrap">{{ summary.first_date }} 至 {{ summary.last_date }}</span></template>
        </p>
      </div>

      <div v-if="error" class="inline-error"><Icon name="alert" :size="16" />{{ error }}<button class="btn btn-ghost btn-sm" @click="load">重新加载</button></div>
      <div v-else-if="loading && !growth" class="growth-state"><span class="spin"></span>正在汇总面试报告…</div>

      <div v-else-if="!hasData" class="empty growth-empty" v-reveal>
        <div class="empty-ic"><Icon name="growth" :size="30" /></div>
        <div class="empty-title">还没有可回顾的面试报告</div>
        <div class="empty-sub">完成第一场模拟面试后，这里会长出你的能力曲线。</div>
        <RouterLink class="btn btn-dark btn-sm" to="/choose-job"><Icon name="mic" :size="14" />去开一场面试</RouterLink>
      </div>

      <div v-else class="growth-layout">
        <!-- ── 总览数字带: 编辑部式大数字 + 滚动动画 ── -->
        <section class="stat-strip" v-reveal>
          <div class="stat-cell">
            <span class="stat-label">场次 <i class="mono">SESSIONS</i></span>
            <strong class="stat-num">{{ disp.reports }}</strong>
            <span class="stat-foot mono nowrap">{{ summary.first_date || '—' }} 起</span>
          </div>
          <div class="stat-cell">
            <span class="stat-label">累计题数 <i class="mono">QUESTIONS</i></span>
            <strong class="stat-num">{{ disp.questions }}</strong>
            <span class="stat-foot mono">追问率 {{ Math.round((summary.followup_rate || 0) * 100) }}%</span>
          </div>
          <div class="stat-cell is-accent">
            <span class="stat-label">总均分 <i class="mono">AVERAGE</i></span>
            <strong class="stat-num">{{ disp.avg }}<small>/10</small></strong>
            <span class="stat-foot mono">求助 {{ summary.hints_used_total || 0 }} 次</span>
          </div>
          <div class="stat-cell" :class="`tone-${trendTone}`">
            <span class="stat-label">近期趋势 <i class="mono">TREND</i></span>
            <strong class="stat-num">
              <Icon v-if="trendTone === 'pine'" name="arrowUpRight" :size="30" class="trend-ic" />
              <Icon v-else-if="trendTone === 'verm'" name="arrowRight" :size="30" class="trend-ic trend-down" />
              <template v-if="trendTone !== 'muted'">{{ disp.trend }}</template>
              <template v-else>—</template>
            </strong>
            <span class="stat-foot mono nowrap">最近 3 场 − 之前 3 场</span>
          </div>
        </section>

        <!-- ── 走势 + 雷达 ── -->
        <div class="chart-grid">
          <section class="panel chart-panel" v-reveal>
            <div class="panel-head">
              <span class="sec-index">01 · SCORE TIMELINE</span>
              <h2>场均分走势</h2>
              <span class="head-note mono">{{ isTouch ? "点按数据点查看单场" : "悬停数据点查看单场" }}</span>
            </div>
            <div class="chart-wrap">
            <svg class="line-chart" :viewBox="`0 0 ${CHART_W} ${CHART_H}`" role="img" aria-label="场均分走势图" @mousemove="onChartMove" @mouseleave="hoverIdx = -1">
              <defs>
                <linearGradient id="growthArea" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stop-color="var(--vermilion)" stop-opacity="0.16" />
                  <stop offset="100%" stop-color="var(--vermilion)" stop-opacity="0.01" />
                </linearGradient>
              </defs>
              <g v-for="gv in [0, 2.5, 5, 7.5, 10]" :key="gv"
                 :transform="`translate(0 ${CHART_PAD.t + (CHART_H - CHART_PAD.t - CHART_PAD.b) * (1 - gv / 10)})`">
                <line :x1="CHART_PAD.l" :x2="CHART_W - CHART_PAD.r" stroke="var(--line-soft)" stroke-width="1" />
                <text :x="CHART_PAD.l - 8" dy="4" text-anchor="end" class="axis-text">{{ gv }}</text>
              </g>
              <line v-if="hoverP" :x1="hoverP.x" :y1="CHART_PAD.t - 6" :x2="hoverP.x" :y2="CHART_H - CHART_PAD.b"
                    stroke="var(--line-strong)" stroke-dasharray="3 3" class="crosshair" />
              <path v-if="areaPath" :d="areaPath" fill="url(#growthArea)" class="area-fill" />
              <path :d="linePath" fill="none" stroke="var(--vermilion)" stroke-width="2.2"
                    stroke-linejoin="round" stroke-linecap="round" pathLength="1" class="line-draw" />
              <g v-for="(p, i) in chartPoints" :key="i">
                <circle :cx="p.x" :cy="p.y" r="4.5" class="chart-dot"
                        :style="{ '--d': `${0.9 + i * 0.045}s` }" />
                <circle :cx="p.x" :cy="p.y" r="13" fill="transparent" class="chart-hit">
                  <title>{{ p.date }} · {{ p.label }} · 均分 {{ p.v }}</title>
                </circle>
                <text v-if="i === 0 || i === chartPoints.length - 1 || chartPoints.length <= 8"
                      :x="p.x" :y="CHART_H - 10" text-anchor="middle" class="axis-text">{{ p.date.slice(5) || i + 1 }}</text>
              </g>
            </svg>
            <div v-if="hoverP" class="chart-tip" :style="{ '--tip-x': `${(hoverP.x / CHART_W) * 100}%` }">
              <span class="mono tip-date">{{ hoverP.date }}</span>
              <b class="fig tip-score">{{ hoverP.v }}</b>
              <span class="tip-role">{{ hoverP.label }}</span>
            </div>
            <div class="chart-foot mono" v-if="chartFoot">
              <span>峰值 <b class="fig">{{ chartFoot.max }}</b> ({{ chartFoot.maxDate }})</span>
              <span>最新 <b class="fig">{{ chartFoot.last }}</b> ({{ chartFoot.lastDate }})</span>
              <span>场均 <b class="fig">{{ chartFoot.avg }}</b></span>
            </div>
            </div>
          </section>

          <section class="panel radar-panel" v-reveal="0.08">
            <div class="panel-head">
              <span class="sec-index">02 · DIMENSIONS</span>
              <h2>四维雷达</h2>
            </div>
            <svg class="radar-chart" viewBox="0 0 300 256" role="img" aria-label="四维雷达对比图">
              <g v-for="ring in [0.25, 0.5, 0.75, 1]" :key="ring">
                <polygon :points="polyFor([10 * ring, 10 * ring, 10 * ring, 10 * ring])"
                         fill="none" stroke="var(--line-soft)" stroke-width="1" />
              </g>
              <line :x1="CENTER.x" :y1="CENTER.y" :x2="AXES.top.x" :y2="AXES.top.y" stroke="var(--line-soft)" />
              <line :x1="CENTER.x" :y1="CENTER.y" :x2="AXES.right.x" :y2="AXES.right.y" stroke="var(--line-soft)" />
              <line :x1="CENTER.x" :y1="CENTER.y" :x2="AXES.bottom.x" :y2="AXES.bottom.y" stroke="var(--line-soft)" />
              <line :x1="CENTER.x" :y1="CENTER.y" :x2="AXES.left.x" :y2="AXES.left.y" stroke="var(--line-soft)" />
              <text :x="AXES.top.x" :y="AXES.top.y - 10" text-anchor="middle" class="axis-text axis-dim">准确</text>
              <text :x="AXES.right.x + 8" :y="AXES.right.y + 4" text-anchor="start" class="axis-text axis-dim">完整</text>
              <text :x="AXES.bottom.x" :y="AXES.bottom.y + 16" text-anchor="middle" class="axis-text axis-dim">深度</text>
              <text :x="AXES.left.x - 8" :y="AXES.left.y + 4" text-anchor="end" class="axis-text axis-dim">条理</text>
              <polygon v-if="averagePoly" :points="averagePoly" class="radar-poly poly-avg"
                       :style="{ '--d': '0.35s' }" />
              <polygon v-if="latestPoly" :points="latestPoly" class="radar-poly poly-latest"
                       :style="{ '--d': '0.55s' }" />
            </svg>
            <div class="radar-legend">
              <span class="lg lg-latest"><i></i>最新一场 ({{ timeline[timeline.length - 1]?.date }})</span>
              <span class="lg lg-avg"><i></i>个人均值</span>
            </div>
          </section>
        </div>

        <!-- ── 分类掌握度 ── -->
        <section class="panel" v-reveal>
          <div class="panel-head">
            <span class="sec-index">03 · CATEGORY MASTERY</span>
            <h2>分类掌握度</h2>
            <span class="head-note mono">弱项置顶 · 跨场次题目级聚合</span>
          </div>
          <div class="cat-rows">
            <div v-for="(c, ci) in categories" :key="c.name" class="cat-row"
                 :style="{ '--d': `${ci * 0.05}s` }">
              <span class="cat-rank mono">{{ String(ci + 1).padStart(2, '0') }}</span>
              <span class="cat-name">{{ c.name }}</span>
              <div class="cat-bar-track">
                <div class="cat-bar" :class="`tone-${scoreTone(c.avg_score)}`"
                     :style="{ width: `${Math.max(4, (c.avg_score / 10) * 100)}%` }"></div>
              </div>
              <span class="cat-score fig" :class="`tone-${scoreTone(c.avg_score)}`">{{ c.avg_score }}</span>
              <span class="cat-delta mono" :class="c.delta > 0 ? 'up' : (c.delta < 0 ? 'down' : '')">
                {{ c.delta > 0 ? '↑' : (c.delta < 0 ? '↓' : '·') }}{{ Math.abs(c.delta) }}
              </span>
              <span class="cat-meta mono">{{ c.count }}题 · 低分{{ c.low_count }}</span>
            </div>
          </div>
          <div class="difficulty-row">
            <span class="section-label">DIFFICULTY</span>
            <span class="diff-chip" v-for="lvl in [1, 2, 3]" :key="lvl">
              L{{ lvl }} <b>{{ difficulty[lvl] || 0 }}</b>
              <small>{{ difficultyTotal ? Math.round(((difficulty[lvl] || 0) / difficultyTotal) * 100) : 0 }}%</small>
            </span>
          </div>
        </section>

        <!-- ── 场次明细 ── -->
        <section class="panel" v-reveal>
          <div class="panel-head">
            <span class="sec-index">04 · SESSIONS</span>
            <h2>场次明细</h2>
            <span class="head-note mono">最近 {{ recentReports.length }} 场 · 点击查看报告全文</span>
          </div>
          <div class="session-table">
            <RouterLink v-for="t in recentReports" :key="t.report_id" class="session-row"
                        :to="`/summary/${t.report_id}`">
              <span class="mono session-date">{{ t.date || '—' }}</span>
              <span class="session-role">{{ t.role_title || '未命名岗位' }}</span>
              <span class="session-diff">{{ difficultyLabel(t.difficulty_label) }}</span>
              <span class="session-count mono">{{ t.total_questions }} 题</span>
              <span class="session-score fig" :class="`tone-${scoreTone(Number(t.avg_score) || 0)}`">{{ t.avg_score }}</span>
              <Icon name="arrowRight" :size="14" class="session-arrow" />
            </RouterLink>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.growth-page { max-width: 1160px; }

.growth-state { display: flex; align-items: center; gap: 10px; padding: 60px 0; color: var(--ink-3); }

.page-head { margin-bottom: 10px; }
.nowrap { white-space: nowrap; }
.stat-foot.nowrap { white-space: nowrap; }
.head-rule { border: none; border-top: 1px solid var(--line-strong); margin: 14px 0 12px; max-width: 220px; }

.growth-empty {
  display: flex; flex-direction: column; align-items: center; gap: 10px;
  padding: 90px 0 70px; text-align: center;
}
.growth-empty .empty-ic { color: var(--ink-4); }

.growth-layout { display: flex; flex-direction: column; gap: 30px; }

/* ── 总览数字带: 编辑部式分栏细线 ── */
.stat-strip {
  display: grid; grid-template-columns: repeat(4, 1fr);
  border-block: 1px solid var(--line-strong);
  background: var(--sheet);
}
.stat-cell {
  padding: 20px 22px 18px; display: flex; flex-direction: column; gap: 6px;
  border-right: 1px solid var(--line-soft);
}
.stat-cell:last-child { border-right: none; }
.stat-label { font-size: 11px; letter-spacing: 0.1em; color: var(--ink-2); display: flex; justify-content: space-between; align-items: baseline; }
.stat-label i { font-style: normal; font-size: 9px; letter-spacing: 0.16em; color: var(--ink-4); }
.stat-num {
  font-variant-numeric: tabular-nums;
  font-size: 46px; font-weight: 800; line-height: 1.02; font-family: var(--f-display);
  letter-spacing: -0.01em; display: flex; align-items: baseline; gap: 4px;
}
.stat-num small { font-size: 16px; color: var(--ink-3); font-weight: 600; }
.stat-num .trend-ic { align-self: center; color: var(--pine); }
.stat-num .trend-down { color: var(--vermilion); transform: rotate(45deg); }
.stat-cell.is-accent .stat-num { color: var(--vermilion); }
.stat-cell.tone-pine .stat-num { color: var(--pine); }
.stat-cell.tone-verm .stat-num { color: var(--vermilion); }
.stat-cell.tone-ochre .stat-num { color: var(--ochre); }
.stat-foot { font-size: 11px; color: var(--ink-3); }

/* ── 图表面板 ── */
.chart-grid { display: grid; grid-template-columns: 1.7fr 1fr; gap: 16px; }
.panel {
  background: var(--sheet); border: 1px solid var(--line); border-radius: var(--r-1);
  padding: 22px 24px; box-shadow: var(--sh-sheet);
}
.panel-head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
.panel-head h2 { font-size: 18px; font-family: var(--f-display); margin: 0; }
.head-note { font-size: 11px; color: var(--ink-4); margin-left: auto; }

.line-chart { width: 100%; height: auto; display: block; }
.axis-text { font-size: 12px; fill: var(--ink-2); font-family: var(--f-mono); }
.axis-dim { font-size: 11px; fill: var(--ink-2); }

/* 描线入场: pathLength=1 归一化 */
.line-draw {
  stroke-dasharray: 1; stroke-dashoffset: 1;
}
.chart-wrap { position: relative; }
.chart-panel.is-in .line-draw {
  animation: drawLine 1.5s var(--ease) 0.35s forwards;
}
@keyframes drawLine { to { stroke-dashoffset: 0; } }
.area-fill { opacity: 0; }
.chart-panel.is-in .area-fill { animation: fadeIn 1s ease 1.2s forwards; }
@keyframes fadeIn { to { opacity: 1; } }

.chart-dot {
  fill: var(--sheet); stroke: var(--vermilion); stroke-width: 2;
  opacity: 0; transform-box: fill-box; transform-origin: center; transform: scale(0);
}
.chart-panel.is-in .chart-dot {
  animation: dotPop 0.45s var(--ease) forwards;
  animation-delay: var(--d, 1s);
}
@keyframes dotPop { to { opacity: 1; transform: scale(1); } }

.chart-foot {
  display: flex; gap: 22px; justify-content: center; margin-top: 10px;
  font-size: 11px; color: var(--ink-3); flex-wrap: wrap; row-gap: 4px;
}
.chart-foot b { color: var(--ink); font-weight: 700; }
.crosshair { pointer-events: none; }
.chart-tip {
  position: absolute; top: 46px; transform: translateX(-50%);
  left: clamp(96px, var(--tip-x, 50%), calc(100% - 96px));
  display: flex; flex-direction: column; gap: 1px; align-items: center;
  background: var(--sheet); border: 1px solid var(--line-strong); border-radius: var(--r-2);
  box-shadow: var(--sh-lift); padding: 7px 12px; pointer-events: none; z-index: 3;
  white-space: nowrap;
}
.tip-date { font-size: 10px; color: var(--ink-3); }
.tip-score { font-size: 17px; color: var(--vermilion); }
.tip-role { font-size: 10px; color: var(--ink-2); max-width: 180px; overflow: hidden; text-overflow: ellipsis; }

/* 雷达从中心展开 */
.radar-poly {
  transform-box: view-box; transform-origin: 50% 50%;
  opacity: 0; transform: scale(0.15);
}
.radar-panel.is-in .radar-poly {
  animation: radarIn 0.9s var(--ease) forwards;
  animation-delay: var(--d, 0.4s);
}
@keyframes radarIn { to { opacity: 1; transform: scale(1); } }
.poly-avg { fill: var(--indigo-wash); stroke: var(--indigo-ink); stroke-width: 1.6; stroke-dasharray: 4 3; }
.poly-latest { fill: var(--verm-wash); stroke: var(--vermilion); stroke-width: 2; stroke-linejoin: round; }

.radar-chart { width: 100%; max-width: 300px; display: block; margin: 0 auto; }
.radar-legend { display: flex; justify-content: center; gap: 18px; margin-top: 10px; font-size: 11px; color: var(--ink-2); }
.radar-legend .lg { display: inline-flex; align-items: center; gap: 6px; }
.radar-legend i { width: 14px; height: 3px; border-radius: 2px; display: inline-block; }
.lg-latest i { background: var(--vermilion); }
.lg-avg i { background: var(--indigo-ink); }

/* ── 分类掌握度 ── */
.cat-rows { display: flex; flex-direction: column; gap: 9px; }
.cat-row {
  display: grid; grid-template-columns: 26px 130px 1fr 44px 44px 120px;
  align-items: center; gap: 12px;
  opacity: 0; transform: translateY(8px);
}
.panel.is-in .cat-row {
  animation: rowIn 0.5s var(--ease) forwards;
  animation-delay: var(--d, 0s);
}
@keyframes rowIn { to { opacity: 1; transform: none; } }
.cat-rank { font-size: 10px; color: var(--ink-4); text-align: right; }
.cat-name { font-size: 13px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cat-bar-track { position: relative; height: 14px; background: var(--paper-deep); border-radius: var(--r-2); overflow: hidden; }
.cat-bar {
  position: absolute; inset: 0 auto 0 0; border-radius: var(--r-2);
  transform: scaleX(0); transform-origin: left;
}
.panel.is-in .cat-bar {
  animation: barIn 0.8s var(--ease) forwards;
  animation-delay: calc(var(--d, 0s) + 0.15s);
}
@keyframes barIn { to { transform: scaleX(1); } }
.cat-bar.tone-pine { background: var(--pine); }
.cat-bar.tone-ochre { background: var(--ochre); }
.cat-bar.tone-verm { background: var(--vermilion); }
.cat-score { font-size: 14px; font-weight: 700; text-align: right; }
.cat-score.tone-pine { color: var(--pine); }
.cat-score.tone-ochre { color: var(--ochre); }
.cat-score.tone-verm { color: var(--vermilion); }
.cat-delta { font-size: 11px; color: var(--ink-3); text-align: right; }
.cat-delta.up { color: var(--pine); }
.cat-delta.down { color: var(--vermilion); }
.cat-meta { font-size: 11px; color: var(--ink-3); text-align: right; }

.difficulty-row { display: flex; align-items: center; gap: 10px; margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--line-soft); flex-wrap: wrap; }
.diff-chip {
  font-size: 12px; color: var(--ink-2); background: var(--paper-deep);
  border-radius: var(--r-2); padding: 4px 12px; display: inline-flex; gap: 6px; align-items: baseline;
}
.diff-chip b { font-size: 13px; }
.diff-chip small { color: var(--ink-3); }

/* ── 场次明细 ── */
.session-table { display: flex; flex-direction: column; }
.session-row {
  display: grid; grid-template-columns: 92px 1fr 96px 60px 52px 20px;
  gap: 12px; align-items: center; padding: 11px 6px;
  border-bottom: 1px solid var(--line-soft); color: var(--ink);
  text-decoration: none; transition: background 0.15s ease, padding-left 0.2s ease;
}
.session-row:hover { background: var(--verm-wash); padding-left: 12px; }
.session-row:hover .session-arrow { transform: translateX(3px); color: var(--vermilion); }
.session-arrow { color: var(--ink-4); transition: transform 0.2s ease, color 0.2s ease; }
.session-date { font-size: 12px; color: var(--ink-3); }
.session-role { font-size: 14px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.session-diff { font-size: 12px; color: var(--ink-2); }
.session-count { font-size: 12px; color: var(--ink-3); text-align: right; }
.session-score { font-size: 15px; font-weight: 800; text-align: right; }
.session-score.tone-pine { color: var(--pine); }
.session-score.tone-ochre { color: var(--ochre); }
.session-score.tone-verm { color: var(--vermilion); }

@media (max-width: 980px) {
  .axis-text { font-size: 20px; }
  .stat-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .stat-foot { font-size: 10px; letter-spacing: 0; }
  .stat-cell:nth-child(2) { border-right: none; }
  .stat-cell:nth-child(-n+2) { border-bottom: 1px solid var(--line-soft); }
  .stat-num { font-size: 34px; }
  .chart-grid { grid-template-columns: 1fr; }
  .cat-row { grid-template-columns: 96px 1fr 40px 44px; }
  .cat-rank, .cat-meta, .cat-delta { display: none; }
  .session-row { grid-template-columns: 84px 1fr 48px 20px; }
  .session-diff, .session-count { display: none; }
}
</style>
