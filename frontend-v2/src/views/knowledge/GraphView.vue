<template>
  <div>
    <TopBar crumb="知识图谱" folio="卷·06">
      <template #actions>
        <button class="tlink" :disabled="rebuilding" @click="rebuild">
          <Icon name="refresh" />{{ rebuilding ? '重建中…' : '重建索引' }}
        </button>
        <button class="tlink" @click="relayout"><Icon name="network" />重新布局</button>
        <button class="tlink" @click="load"><Icon name="refresh" />刷新</button>
      </template>
    </TopBar>

    <div class="page-body">
      <div class="page-head" v-reveal>
        <span class="sec-index">KNOWLEDGE GRAPH</span>
        <h1 class="page-title" style="margin-top:14px">知识图谱</h1>
        <p class="page-sub" style="margin-bottom:16px">
          节点大小 = 连接数；实线为 [[双链]]，虚线为语义关联；灰度虚线框表示尚未创建的笔记。
        </p>
        <div class="legend-row">
          <span class="legend"><span class="lg-dot note"></span>笔记</span>
          <span class="legend"><span class="lg-dot file"></span>文件</span>
          <span class="legend"><span class="lg-dot url"></span>网址</span>
          <span class="legend"><span class="lg-dot virtual"></span>未创建</span>
          <span class="legend"><span class="lg-line"></span>双链</span>
          <span class="legend"><span class="lg-line dash"></span>语义</span>
        </div>
      </div>

      <!-- 控制条 -->
      <div class="graph-controls" v-reveal="0.06">
        <label class="switch">
          <input type="checkbox" v-model="showSemantic" @change="load" />
          显示语义边
        </label>
        <label class="switch">
          <input type="checkbox" v-model="hideOrphans" @change="applyOrphanFilter" />
          隐藏孤立节点
        </label>
        <template v-if="categories.length">
          <span class="ctl-sep"></span>
          <span class="mono">分类筛选</span>
          <div class="chips">
            <button
              v-for="c in categories"
              :key="c.category"
              class="tag"
              :class="{ 'is-on': activeCategories.has(c.category) }"
              @click="toggleCategory(c.category)"
            >
              <Icon name="folder" :size="12" />{{ c.category }} ({{ c.count }})
            </button>
          </div>
        </template>
      </div>

      <!-- 画布 -->
      <div class="graph-wrap" v-reveal="0.12">
        <div v-if="loading" class="graph-state">
          <span class="spin" style="display:inline-block;width:18px;height:18px;border:2px solid var(--line-strong);border-top-color:var(--vermilion);border-radius:50%"></span>
          图谱加载中…
        </div>

        <div v-else-if="error" class="graph-state">
          <span class="graph-state-msg"><Icon name="alert" :size="15" />{{ error }}</span>
          <button class="btn btn-ghost btn-sm" @click="load"><Icon name="refresh" :size="14" />重新加载</button>
        </div>

        <div v-else-if="!nodeCount" class="graph-state graph-empty">
          <div class="empty-ic"><Icon name="network" :size="30" /></div>
          <div class="empty-title">图谱还是空的</div>
          <div class="empty-sub">先去写几篇笔记或导入文件，用 [[标题]] 互相链接起来吧。</div>
          <RouterLink class="btn btn-sm" to="/knowledge" style="margin-top:18px">
            去写笔记<span class="ar"><Icon name="arrowRight" /></span>
          </RouterLink>
        </div>

        <div ref="cyContainer" class="cy" v-show="nodeCount > 0"></div>

        <!-- 悬浮详情 -->
        <div class="node-card" :class="{ 'is-on': cardOn }">
          <div class="t">{{ card.title }}</div>
          <div class="row"><span>类型</span><b>{{ card.type }}</b></div>
          <div class="row"><span>连接数</span><b>{{ card.links }}</b></div>
          <div class="row"><span>备注</span><b>{{ card.note }}</b></div>
          <div class="hintx">{{ card.hint }}</div>
        </div>

        <!-- 状态条 -->
        <div v-if="nodeCount" class="graph-stats">
          <span><b>{{ nodeCount }}</b> 节点</span>
          <span><b>{{ virtualCount }}</b> 虚拟</span>
          <span><b>{{ wikiEdgeCount }}</b> 双链</span>
          <span><b>{{ semEdgeCount }}</b> 语义</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import cytoscape from 'cytoscape'
import fcose from 'cytoscape-fcose'
import layoutUtilities from 'cytoscape-layout-utilities'
import TopBar from '../../components/TopBar.vue'
import Icon from '../../components/Icon.vue'
import { kbGraph, kbCategories, kbCreateNote, kbRebuild } from '../../api'
import { toast } from '../../composables/useToast'

// fcose 力导布局 (Cytoscape 官方推荐) + layout-utilities (fcose packComponents 依赖)
cytoscape.use(layoutUtilities)
cytoscape.use(fcose)

const router = useRouter()
const cyContainer = ref(null)
const loading = ref(false)
const error = ref('')
const nodeCount = ref(0)
const virtualCount = ref(0)
const wikiEdgeCount = ref(0)
const semEdgeCount = ref(0)
const categories = ref([])
const activeCategories = ref(new Set())
const showSemantic = ref(true)
const hideOrphans = ref(false)
const rebuilding = ref(false)

// 节点悬浮详情卡
const cardOn = ref(false)
const card = reactive({
  title: '—',
  type: '—',
  links: 0,
  note: '—',
  hint: '悬停节点查看详情 · 点击进入笔记',
})

let cy = null
let lastGraph = null
const noteIdByTitle = new Map()

/* ── 设计令牌（与 tokens.css 对齐的 cytoscape 字面值） ──
   节点: note 靛蓝 / file 松绿 / url 赭黄 / virtual 灰；描边取米白纸色
   双链: 实线 (墨 28%)  ·  语义: 虚线 (墨 16%) + dash 流动 */
const TOK = {
  sheet: '#FBF9F3',
  paper: '#F4F1E8',
  ink2: '#4C4739',
  ink3: '#8B8474',
  ink4: '#B4AD9D',
  wiki: 'rgba(23,21,15,0.28)',
  sem: 'rgba(23,21,15,0.16)',
  vermilion: '#D93A1F',
}
const TYPE_COLORS = {
  note: '#23405C',   // --indigo-ink
  file: '#2E6B50',   // --pine
  url: '#A9741C',    // --ochre
  virtual: '#B4AD9D', // --ink-4
}
const TYPE_LABELS = { note: '笔记', file: '文件', url: '网址', virtual: '未创建' }

async function load() {
  loading.value = true
  error.value = ''
  try {
    const catParam = [...activeCategories.value].join(',')
    const result = await kbGraph(showSemantic.value, catParam)
    if (!result.success) {
      error.value = result.message || '加载失败'
      return
    }
    render(result.graph)
  } catch (_) {
    error.value = '无法连接后端服务'
  } finally {
    loading.value = false
  }
}

async function loadCategories() {
  try {
    const result = await kbCategories()
    if (result.success) categories.value = result.categories || []
  } catch (_) { /* 分类缺失不影响主图 */ }
}

function toggleCategory(c) {
  if (activeCategories.value.has(c)) activeCategories.value.delete(c)
  else activeCategories.value.add(c)
  activeCategories.value = new Set(activeCategories.value)
  load()
}

async function rebuild() {
  if (rebuilding.value) return
  rebuilding.value = true
  try {
    const result = await kbRebuild()
    if (result.success) {
      toast(`已重建：${result.notes} 篇笔记向量 · ${result.sem_links} 条语义关联`, 'refresh')
      await load()
    } else {
      toast(result.message || '重建失败', 'alert')
    }
  } catch (_) {
    toast('重建请求失败', 'alert')
  } finally {
    rebuilding.value = false
  }
}

/** 单行标签最多 9 字，超出省略；全名 hover 通过详情卡展示 */
function shortLabel(title) {
  const t = (title || '').trim()
  const MAX = 9
  return t.length > MAX ? t.slice(0, MAX) + '…' : t
}

/** 计算节点度并分配尺寸/颜色 */
function buildElements(graph) {
  const degreeMap = {}
  graph.nodes.forEach(n => { degreeMap[n.id] = 0 })
  graph.edges.forEach(e => {
    if (degreeMap[e.source] !== undefined) degreeMap[e.source]++
    if (degreeMap[e.target] !== undefined) degreeMap[e.target]++
  })
  const maxDeg = Math.max(1, ...Object.values(degreeMap))

  const visibleNodes = hideOrphans.value
    ? graph.nodes.filter(n => (degreeMap[n.id] ?? 0) > 0)
    : graph.nodes
  const visibleIds = new Set(visibleNodes.map(n => n.id))

  return {
    nodes: visibleNodes.map(n => {
      const deg = degreeMap[n.id] ?? 0
      const isVirtual = !!n.virtual
      const color = isVirtual ? TYPE_COLORS.virtual : (TYPE_COLORS[n.note_type] || TYPE_COLORS.note)
      const size = 10 + 12 * Math.sqrt(deg / maxDeg)
      return {
        data: {
          id: n.id,
          label: shortLabel(n.id),
          size,
          color,
          virtual: isVirtual ? 'yes' : 'no',
          category: n.category || '',
          noteType: n.note_type || 'note',
          tags: (n.tags || []).join(' · '),
          deg,
        },
      }
    }),
    edges: graph.edges
      .filter(e => visibleIds.has(e.source) && visibleIds.has(e.target))
      .map((e, i) => ({
        data: {
          id: `e${i}`,
          source: e.source,
          target: e.target,
          kind: e.kind,
          virtual: e.virtual ? 'yes' : 'no',
          score: e.score,
        },
      })),
  }
}

function applyOrphanFilter() {
  if (lastGraph) render(lastGraph)
}

/** 语义边 dash 流动动画（cytoscape line-dash-offset） */
let dashTimer = null
let dashOffset = 0
function startDash() {
  stopDash()
  if (!cy) return
  if (!cy.edges('[kind = "semantic"]').length) return
  dashTimer = setInterval(() => {
    if (!cy) return
    dashOffset = (dashOffset + 1) % 20
    cy.edges('[kind = "semantic"]').style('line-dash-offset', dashOffset)
  }, 90)
}
function stopDash() {
  if (dashTimer) { clearInterval(dashTimer); dashTimer = null }
}

function showCard(node) {
  const d = node.data()
  const isVirtual = d.virtual === 'yes'
  card.title = node.id()
  card.type = isVirtual
    ? '未创建 · 虚拟节点'
    : `${TYPE_LABELS[d.noteType] || '笔记'} · ${d.category || '未分类'}`
  card.links = d.deg
  card.note = isVirtual ? '可点击创建该笔记' : (d.tags || d.category || '—')
  card.hint = isVirtual ? '尚未创建的笔记 · 点击可创建' : '点击进入笔记'
  cardOn.value = true
}

function render(graph) {
  lastGraph = graph
  if (!graph || !graph.nodes.length) {
    stopDash()
    if (cy) { cy.destroy(); cy = null }
    nodeCount.value = 0
    virtualCount.value = 0
    wikiEdgeCount.value = 0
    semEdgeCount.value = 0
    cardOn.value = false
    return
  }

  noteIdByTitle.clear()
  for (const n of graph.nodes) noteIdByTitle.set(n.id, n.note_id)

  const { nodes, edges } = buildElements(graph)
  nodeCount.value = nodes.length
  virtualCount.value = nodes.filter(n => n.data.virtual === 'yes').length
  wikiEdgeCount.value = edges.filter(e => e.data.kind === 'wiki').length
  semEdgeCount.value = edges.filter(e => e.data.kind === 'semantic').length

  nextTick(() => {
    stopDash()
    if (cy) { cy.destroy(); cy = null }
    if (!cyContainer.value) return
    cy = cytoscape({
      container: cyContainer.value,
      elements: [...nodes, ...edges],
      style: [
        {
          selector: 'node',
          style: {
            'label': 'data(label)',
            'background-color': 'data(color)',
            'width': 'data(size)',
            'height': 'data(size)',
            'border-width': 2,
            'border-color': TOK.sheet,
            'color': TOK.ink2,
            'font-family': 'JetBrains Mono, monospace',
            'font-size': 10.5,
            'text-valign': 'bottom',
            'text-halign': 'center',
            'text-margin-y': 5,
            'text-wrap': 'none',
            'min-zoomed-font-size': 8,
          },
        },
        {
          selector: 'node[virtual = "yes"]',
          style: {
            'background-color': TYPE_COLORS.virtual,
            'border-color': TOK.ink4,
            'border-style': 'dashed',
            'border-width': 1.4,
            'color': TOK.ink3,
          },
        },
        {
          selector: 'node[deg < 2]',
          style: { 'font-size': 9.5, 'color': TOK.ink3 },
        },
        {
          selector: 'edge[kind = "wiki"]',
          style: {
            'width': 1.1,
            'line-color': TOK.wiki,
            'curve-style': 'bezier',
            'line-style': 'solid',
          },
        },
        {
          selector: 'edge[kind = "wiki"][virtual = "yes"]',
          style: { 'line-style': 'dashed', 'line-color': 'rgba(23,21,15,0.14)' },
        },
        {
          selector: 'edge[kind = "semantic"]',
          style: {
            'width': 1.1,
            'line-color': TOK.sem,
            'line-style': 'dashed',
            'line-dash-pattern': [4, 6],
            'curve-style': 'bezier',
          },
        },
        {
          selector: 'node:selected',
          style: { 'border-width': 4, 'border-color': TOK.vermilion, 'border-style': 'solid' },
        },
      ],
      layout: buildLayoutOptions(true),
      minZoom: 0.3,
      maxZoom: 3,
      wheelSensitivity: 0.3,
    })

    // hover: 聚焦当前节点及一跳邻居
    cy.on('mouseover', 'node', (event) => {
      const node = event.target
      const hood = node.closedNeighborhood()
      cy.elements().difference(hood).style({ opacity: 0.08 })
      hood.style({ opacity: 1 })
      node.style({
        'border-width': 4, 'border-color': TOK.vermilion, 'border-style': 'solid',
        'z-index': 999, 'font-size': 13, 'color': '#17150F',
      })
      node.neighborhood().nodes().style({
        'border-width': 3, 'border-color': TOK.vermilion, 'color': TOK.ink2,
      })
      node.connectedEdges().style({ opacity: 1, width: 2.5, 'line-color': TOK.vermilion })
      showCard(node)
    })
    cy.on('mouseout', 'node', () => {
      cy.elements().removeStyle()
      cardOn.value = false
    })

    // 语义边 hover 高亮
    cy.on('mouseover', 'edge[kind = "semantic"]', (event) => {
      const e = event.target
      e.style({ 'line-color': TOK.vermilion, width: 2.5, opacity: 1 })
      e.source().style({ 'border-width': 4, 'border-color': TOK.vermilion })
      e.target().style({ 'border-width': 4, 'border-color': TOK.vermilion })
    })
    cy.on('mouseout', 'edge[kind = "semantic"]', () => {
      cy.elements().removeStyle()
    })

    // 点击节点: 跳转笔记 / 虚节点创建
    cy.on('tap', 'node', async (event) => {
      const node = event.target
      const title = node.id()
      const noteId = noteIdByTitle.get(title)
      if (noteId) { router.push(`/knowledge/note/${noteId}`); return }
      if (node.data('virtual') !== 'yes') return
      const created = await kbCreateNote(title, `# ${title}\n\n（从图谱虚节点创建）\n\n`)
      if (created.success) {
        toast(`已创建笔记「${title}」`, 'plus')
        router.push(`/knowledge/note/${created.id}`)
      } else {
        toast(created.message || '创建失败', 'alert')
      }
    })

    startDash()
  })
}

/** fcose 布局参数（紧凑团簇 + 分量打包） */
function buildLayoutOptions(animate = true) {
  return {
    name: 'fcose',
    quality: 'proof',
    randomize: true,
    animate,
    animationDuration: 700,
    animationEasing: 'ease-out-cubic',
    fit: true,
    padding: 40,
    nodeDimensionsIncludeLabels: true,
    packComponents: true,
    componentSpacing: 20,
    nodeSeparation: 60,
    nodeRepulsion: () => 5500,
    idealEdgeLength: (edge) => (edge.data('kind') === 'semantic' ? 100 : 45),
    edgeElasticity: (edge) => (edge.data('kind') === 'semantic' ? 0.15 : 0.55),
    nestingFactor: 0.1,
    gravity: 0.4,
    gravityRange: 3.8,
    numIter: 4000,
    tile: true,
    tilingPaddingVertical: 14,
    tilingPaddingHorizontal: 14,
  }
}

function relayout() {
  if (!cy) return
  cy.layout(buildLayoutOptions(true)).run()
  startDash()
}

onMounted(() => { load(); loadCategories() })
onBeforeUnmount(() => {
  stopDash()
  if (cy) cy.destroy()
})
</script>

<style scoped>
  /* 图例 */
  .legend-row { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; }
  .legend { display: inline-flex; align-items: center; gap: 7px; font-size: 12.5px; color: var(--ink-3); }
  .legend + .legend { margin-left: 16px; }
  .lg-dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
  .lg-dot.note { background: var(--indigo-ink); }
  .lg-dot.file { background: var(--pine); }
  .lg-dot.url { background: var(--ochre); }
  .lg-dot.virtual { background: var(--ink-4); }
  .lg-line { display: inline-block; width: 22px; height: 0; border-top: 1px solid var(--ink-3); }
  .lg-line.dash { border-top-style: dashed; }

  /* 控制条 */
  .graph-controls {
    display: flex; align-items: center; gap: 18px; flex-wrap: wrap;
    padding: 14px 0; border-top: 1px solid var(--line-strong); border-bottom: 1px solid var(--line);
    margin-bottom: 20px;
  }
  .switch { display: inline-flex; align-items: center; gap: 9px; font-size: 13.5px; color: var(--ink-2); cursor: pointer; }
  .switch input { appearance: none; width: 34px; height: 18px; border: 1px solid var(--line-strong); position: relative; transition: all var(--dur-2) ease; cursor: pointer; }
  .switch input::after { content: ''; position: absolute; top: 2px; left: 2px; width: 12px; height: 12px; background: var(--ink-4); transition: all var(--dur-2) var(--ease); }
  .switch input:checked { border-color: var(--vermilion); background: var(--verm-wash); }
  .switch input:checked::after { left: 17px; background: var(--vermilion); }
  .ctl-sep { width: 1px; height: 20px; background: var(--line); }
  .chips { display: flex; gap: 8px; flex-wrap: wrap; }

  /* 画布 */
  .graph-wrap {
    position: relative; border: 1px solid var(--line-strong);
    background: var(--sheet); overflow: hidden;
    min-height: clamp(460px, 62vh, 660px);
  }
  .graph-wrap::before {
    content: ''; position: absolute; inset: 0;
    background-image: radial-gradient(var(--line) 1px, transparent 1px);
    background-size: 26px 26px;
    opacity: .55;
  }
  .cy { position: relative; width: 100%; height: clamp(460px, 62vh, 660px); }

  /* 三态 */
  .graph-state {
    position: absolute; inset: 0; z-index: 2; background: var(--sheet);
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 12px; padding: 24px; text-align: center;
    color: var(--ink-3); font-size: 13.5px;
  }
  .graph-state-msg { display: inline-flex; align-items: center; gap: 9px; color: var(--vermilion-deep); }
  .graph-empty .empty-ic { color: var(--ink-4); display: flex; justify-content: center; }
  .graph-empty .empty-title { font-family: var(--f-display); font-weight: 900; font-size: 18px; color: var(--ink); }
  .graph-empty .empty-sub { color: var(--ink-3); font-size: 13.5px; max-width: 46ch; }

  /* 悬浮详情 */
  .node-card {
    position: absolute; right: 20px; bottom: 20px; z-index: 3;
    width: 260px; padding: 16px 18px;
    border: 1px solid var(--line-strong); background: var(--sheet);
    box-shadow: var(--sh-sheet);
    opacity: 0; transform: translateY(8px); pointer-events: none;
    transition: opacity var(--dur-2) ease, transform var(--dur-2) var(--ease);
  }
  .node-card.is-on { opacity: 1; transform: none; }
  .node-card .t { font-family: var(--f-display); font-weight: 900; font-size: 15px; margin-bottom: 8px; }
  .node-card .row { display: flex; justify-content: space-between; gap: 12px; font-size: 12.5px; color: var(--ink-3); padding: 3px 0; }
  .node-card .row b { font-family: var(--f-mono); font-weight: 700; color: var(--ink); text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .node-card .hintx { margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--line); font-family: var(--f-mono); font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink-4); }

  /* 状态条 */
  .graph-stats {
    position: absolute; left: 20px; bottom: 20px; z-index: 3;
    display: flex; gap: 18px; padding: 10px 16px;
    border: 1px solid var(--line); background: color-mix(in srgb, var(--paper) 88%, transparent);
    backdrop-filter: blur(6px);
    font-family: var(--f-mono); font-size: 10.5px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink-3);
  }
  .graph-stats b { color: var(--ink); font-weight: 700; }
</style>