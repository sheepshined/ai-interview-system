<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import Icon from '../components/Icon.vue'
import { getUsername, isAuthenticated } from '../auth'
import { getQbankSummary } from '../api'

/* 登录态：已登录时顶栏显示用户名与「继续练习」，未登录显示「登录」 */
const authed = isAuthenticated()
const username = getUsername()

/* ── 滚动进度条 ── */
const scrollProgress = ref(0)

function onScroll() {
  const h = document.documentElement.scrollHeight - window.innerHeight
  scrollProgress.value = h > 0 ? Math.min((window.scrollY / h) * 100, 100) : 0
}

/* ── 数据带数字滚动 ── */
const countQ = ref(0)
const countD = ref(0)
const realTotal = ref(0)
const statRef = ref(null)

// 数字滚动已提取至 composables/useCountUp.js (共享给成长档案与设置页)
function animateValue(target, setter, dur = 1100) {
  const t0 = performance.now()
  const tick = (t) => {
    const p = Math.min((t - t0) / dur, 1)
    const eased = 1 - Math.pow(1 - p, 3)
    setter(Math.round(target * eased))
    if (p < 1) requestAnimationFrame(tick)
  }
  requestAnimationFrame(tick)
}

/* ── 滚动字幕（内容翻倍以实现无缝） ── */
const tickerItems = [
  'RAG 检索增强', 'LangGraph 人在回路', 'Agent 工具调用', 'Transformer', '提示词工程',
  'MCP 协议', 'LoRA 微调', '向量检索', 'Memory 记忆', '模型部署',
]
const tickerDoubled = computed(() => [...tickerItems, ...tickerItems])

let io
onMounted(() => {
  onScroll()
  window.addEventListener('scroll', onScroll, { passive: true })

  // 题库数字取真实统计 (登录后可读); 未登录或接口失败回落 0, 不放假数字
  getQbankSummary().then((res) => {
    if (res?.success) realTotal.value = res.total
  }).catch(() => {})

  io = new IntersectionObserver((entries) => {
    entries.forEach((en) => {
      if (en.isIntersecting) {
        animateValue(realTotal.value, (v) => (countQ.value = v))
        animateValue(4, (v) => (countD.value = v))
        io.unobserve(en.target)
      }
    })
  }, { threshold: 0.16, rootMargin: '0px 0px -6% 0px' })
  if (statRef.value) io.observe(statRef.value)
})

onUnmounted(() => {
  window.removeEventListener('scroll', onScroll)
  io?.disconnect()
})
</script>

<template>
  <div class="home-page">
  <div class="scroll-line"><i :style="{ width: scrollProgress + '%' }"></i></div>

  <!-- ── 顶栏 ── -->
  <header class="pubnav">
    <RouterLink class="brandmark" to="/">
      <span class="seal">面</span>
      <span>
        <span class="name">AI 模拟面试官</span>
        <span class="sub" style="display:block">Interview Studio</span>
      </span>
    </RouterLink>
    <nav class="pubnav-links">
      <a href="#modes">训练路径</a>
      <a href="#flow">面试流程</a>
      <a href="#eval">评估体系</a>
      <a href="#kb">知识库</a>
    </nav>
    <div class="pubnav-cta">
      <RouterLink v-if="!authed" class="tlink" to="/login">登录</RouterLink>
      <span v-else class="tlink" style="cursor:default; color:var(--ink-3)">{{ username }}</span>
      <RouterLink class="btn btn-sm" :to="authed ? '/interview-records' : '/resume-upload'">
        {{ authed ? '继续练习' : '开始面试' }}<Icon name="arrowRight" class="ar" />
      </RouterLink>
    </div>
  </header>

  <!-- ── HERO ── -->
  <section class="hero">
    <div class="wrap hero-grid">
      <div>
        <span class="eyebrow" v-reveal>AI 面试教练 · 应届生求职陪练</span>
        <h1 class="d1 hero-title">
          <span class="rv-line" v-reveal="0.05"><span>把每一次练习，</span></span>
          <span class="rv-line" v-reveal="0.14"><span>都练成 <em class="mark">offer</em> 的底气</span></span>
        </h1>
        <p class="lead" v-reveal="0.24">
          上传简历智能匹配岗位，或自主选岗开启模拟面试。LangGraph 人在回路追问、四维评分、
          好差答案对照——面试结束，薄弱点一键沉淀进你的个人知识库。
        </p>
        <div class="hero-actions" v-reveal="0.32">
          <RouterLink class="btn btn-lg" to="/resume-upload">开始模拟面试<Icon name="arrowRight" class="ar" /></RouterLink>
          <RouterLink class="tlink" to="/choose-job">自主选岗练习<Icon name="arrowUpRight" /></RouterLink>
        </div>
        <div class="hero-meta" v-reveal="0.4">
          <span class="m"><Icon name="route" />简历匹配 · 智能出题</span>
          <span class="m"><Icon name="clock" />单场约 15 分钟</span>
          <span class="m"><Icon name="target" />四维能力雷达</span>
        </div>
      </div>

      <!-- 档案卡叠放 -->
      <div class="hero-stage" v-reveal="0.2">
        <div class="card-doc doc-score">
          <span class="tape"></span>
          <div class="doc-head">
            <span class="doc-title">本场评估 · 评分卡</span>
            <span class="mono">№ 2026-1004</span>
          </div>
          <div class="doc-body">
            <svg class="radar" viewBox="0 0 132 132" aria-hidden="true">
              <g stroke="rgba(23,21,15,.16)" fill="none">
                <path d="M66 18 L114 66 L66 114 L18 66 Z"/>
                <path d="M66 30 L102 66 L66 102 L30 66 Z"/>
                <path d="M66 42 L90 66 L66 90 L42 66 Z"/>
                <path d="M66 54 L78 66 L66 78 L54 66 Z"/>
              </g>
              <path d="M66 20 L112 66 L66 106 L20 66 Z" fill="none" stroke="rgba(23,21,15,.22)"/>
              <path d="M66 24.6 L108.6 66 L66 100.4 L23.4 66 Z" fill="rgba(217,58,31,.12)" stroke="var(--vermilion)" stroke-width="1.4"/>
              <g fill="var(--vermilion)">
                <circle cx="66" cy="24.6" r="2.2"/><circle cx="108.6" cy="66" r="2.2"/>
                <circle cx="66" cy="100.4" r="2.2"/><circle cx="23.4" cy="66" r="2.2"/>
              </g>
              <g class="mono" font-size="8.4" fill="var(--ink-2)" font-family="JetBrains Mono, monospace">
                <text x="66" y="12" text-anchor="middle">准确 8.6</text>
                <text x="126" y="69" text-anchor="end">完整 6.8</text>
                <text x="66" y="126" text-anchor="middle">深度 6.2</text>
                <text x="6" y="69">条理 9.1</text>
              </g>
            </svg>
            <div class="dim-list">
              <div class="dim"><span>准确</span><span class="track"><i class="v" style="width:86%"></i></span><span class="val">8.6</span></div>
              <div class="dim"><span>完整</span><span class="track"><i style="width:68%"></i></span><span class="val">6.8</span></div>
              <div class="dim"><span>深度</span><span class="track"><i style="width:62%"></i></span><span class="val">6.2</span></div>
              <div class="dim"><span>条理</span><span class="track"><i class="v" style="width:91%"></i></span><span class="val">9.1</span></div>
            </div>
          </div>
        </div>

        <div class="card-doc doc-transcript">
          <span class="tape dark"></span>
          <div class="line" style="margin-bottom:8px">
            <span class="who">面试官</span>
            <span class="txt">请说说 RAG 的检索增强流程，<span class="hi">为什么要做重排</span>？</span>
          </div>
          <div class="line">
            <span class="who me">我</span>
            <span class="txt">检索阶段先用 BM25 与向量双路召回，再用 RRF 融合……<span class="caret"></span></span>
          </div>
        </div>

        <div class="card-doc doc-graph">
          <svg viewBox="0 0 162 122" aria-hidden="true">
            <g class="gedge"><path d="M32 34 74 22"/><path d="M74 22 116 40"/><path d="M32 34 60 72"/><path d="M60 72 116 40"/><path d="M60 72 92 98"/><path d="M116 40 92 98"/></g>
            <g class="gedge sem"><path d="M32 34 92 98"/><path d="M74 22 60 72"/></g>
            <circle cx="32" cy="34" r="7" fill="var(--indigo-ink)" stroke="var(--paper)" stroke-width="1.5"/>
            <circle cx="74" cy="22" r="9" fill="var(--pine)" stroke="var(--paper)" stroke-width="1.5"/>
            <circle cx="116" cy="40" r="6" fill="var(--ochre)" stroke="var(--paper)" stroke-width="1.5"/>
            <circle cx="60" cy="72" r="10" fill="var(--indigo-ink)" stroke="var(--paper)" stroke-width="1.5"/>
            <circle cx="92" cy="98" r="6.5" fill="var(--ink-3)" stroke="var(--paper)" stroke-width="1.5"/>
            <g class="gpulse"><circle cx="60" cy="72" r="16" fill="none" stroke="rgba(35,64,92,.35)"/></g>
          </svg>
        </div>

        <div class="stamp stamp-sm stamp-float">已评估</div>
      </div>
    </div>
  </section>

  <!-- ── 滚动字幕 ── -->
  <div class="ticker" aria-hidden="true">
    <div class="ticker-track">
      <span v-for="(item, i) in tickerDoubled" :key="i" class="ticker-item">{{ item }}</span>
    </div>
  </div>

  <!-- ── 数据带 ── -->
  <section class="statband">
    <div class="wrap">
      <div ref="statRef" class="statband-grid" data-stagger>
        <div class="cell" v-reveal><span class="e">Question Bank</span><span class="n">{{ countQ }}</span><span class="l">精选题库 · 大模型应用专场</span></div>
        <div class="cell" v-reveal><span class="e">Retrieval</span><span class="n">双路<sup>RRF</sup></span><span class="l">BM25 + 向量混合检索出题</span></div>
        <div class="cell" v-reveal><span class="e">Evaluation</span><span class="n">{{ countD }}</span><span class="l">维度评分 · 准确 / 完整 / 深度 / 条理</span></div>
        <div class="cell" v-reveal><span class="e">Knowledge</span><span class="n">双链<sup>父文档</sup></span><span class="l">薄弱点入库 · 图谱 · RAG 问答</span></div>
      </div>
    </div>
  </section>

  <!-- ── 训练路径 ── -->
  <section class="modes" id="modes">
    <div class="wrap">
      <div class="sec-head" v-reveal>
        <span class="sec-index">01 / PATH</span>
        <h2 class="d2">选择你的练习方式</h2>
        <p class="lead">简历匹配省去选择困难，自主选岗灵活定制，两条路径都通向同一份可执行的评估报告。</p>
      </div>

      <div class="modes-grid" data-stagger>
        <RouterLink class="mode-row" to="/resume-upload" v-reveal>
          <span class="no">01</span>
          <h3>简历智能匹配</h3>
          <p>上传 PDF 简历或粘贴文本，AI 解析技能画像并匹配最合适的岗位，直接进入针对性模拟面试。</p>
          <div class="tags">
            <span class="tag">PDF 解析</span><span class="tag">技能提取</span><span class="tag">岗位推荐</span>
          </div>
          <span class="go">上传简历，开始匹配 <Icon name="arrowRight" /></span>
        </RouterLink>
        <RouterLink class="mode-row" to="/choose-job" v-reveal>
          <span class="no">02</span>
          <h3>自主选择岗位</h3>
          <p>自由选择目标岗位与题量，按自己的节奏练习；适合考前突击与专项突破。</p>
          <div class="tags">
            <span class="tag">岗位方向</span><span class="tag">题量自定</span><span class="tag">随时开始</span>
          </div>
          <span class="go">选择岗位，直接开练 <Icon name="arrowRight" /></span>
        </RouterLink>
      </div>
    </div>
  </section>

  <!-- ── 面试流程 ── -->
  <section class="flow" id="flow">
    <div class="wrap">
      <div class="sec-head" v-reveal>
        <span class="sec-index">02 / FLOW</span>
        <h2 class="d2">一场面试，四步走完</h2>
        <p class="lead">从简历到报告，每一步都留下可回看的档案。</p>
      </div>
      <div class="flow-grid" data-stagger>
        <div class="flow-step" v-reveal>
          <span class="n">01</span><span class="node"></span>
          <h4>简历解析</h4>
          <p>读取 PDF 或粘贴文本，提取姓名、技能与项目经历。</p>
        </div>
        <div class="flow-step" v-reveal>
          <span class="n">02</span><span class="node"></span>
          <h4>岗位匹配</h4>
          <p>按技能画像匹配岗位，也可自由选择方向与题量。</p>
        </div>
        <div class="flow-step" v-reveal>
          <span class="n">03</span><span class="node"></span>
          <h4>实战面试</h4>
          <p>逐题作答，支持语音输入、提示与低分追问，节奏接近真实面试。</p>
        </div>
        <div class="flow-step" v-reveal>
          <span class="n">04</span><span class="node"></span>
          <h4>报告复盘</h4>
          <p>四维雷达 + 好差答案对照，薄弱点一键存进知识库。</p>
        </div>
      </div>
    </div>
  </section>

  <!-- ── 评估体系 ── -->
  <section class="eval" id="eval">
    <div class="wrap eval-grid">
      <div class="eval-sticky" v-reveal>
        <span class="sec-index">03 / RUBRIC</span>
        <h2 class="d2" style="margin:18px 0 20px">评分标准，<br />写在明面上</h2>
        <p class="lead" style="margin-bottom:30px">每个回答都从四个维度打分，并给出高分特征与踩坑特征对照——你知道自己差在哪一层。</p>
        <div class="sheet ticks">
          <div class="mono" style="margin-bottom:12px">Rubric · 四维评分</div>
          <div class="dim" style="grid-template-columns:56px 1fr 40px"><span>准确</span><span class="track"><i class="v" style="width:86%"></i></span><span class="val">8.6</span></div>
          <div style="height:10px"></div>
          <div class="dim" style="grid-template-columns:56px 1fr 40px"><span>完整</span><span class="track"><i style="width:68%"></i></span><span class="val">6.8</span></div>
          <div style="height:10px"></div>
          <div class="dim" style="grid-template-columns:56px 1fr 40px"><span>深度</span><span class="track"><i style="width:62%"></i></span><span class="val">6.2</span></div>
          <div style="height:10px"></div>
          <div class="dim" style="grid-template-columns:56px 1fr 40px"><span>条理</span><span class="track"><i class="v" style="width:91%"></i></span><span class="val">9.1</span></div>
        </div>
      </div>

      <div class="dim-rows" data-stagger>
        <div class="dim-row" v-reveal>
          <span class="no">A</span>
          <div>
            <h4>准确 Accuracy</h4>
            <p>概念是否正确、有无幻觉。反幻觉数据契约要求答案必须落在题库知识范围内。</p>
          </div>
          <div class="score"><div class="v">40%</div><div class="k">权重</div></div>
        </div>
        <div class="dim-row" v-reveal>
          <span class="no">B</span>
          <div>
            <h4>完整 Completeness</h4>
            <p>是否覆盖了参考答案的关键要点，而不是只答了其中一半。</p>
          </div>
          <div class="score"><div class="v">25%</div><div class="k">权重</div></div>
        </div>
        <div class="dim-row" v-reveal>
          <span class="no">C</span>
          <div>
            <h4>深度 Depth</h4>
            <p>能否讲到实现细节、边界情况与取舍，这也是追问最容易暴露的地方。</p>
          </div>
          <div class="score"><div class="v">20%</div><div class="k">权重</div></div>
        </div>
        <div class="dim-row" v-reveal>
          <span class="no">D</span>
          <div>
            <h4>条理 Clarity</h4>
            <p>表达结构是否清晰，能否先给结论再展开论证——面试官听得到的那一半分数。</p>
          </div>
          <div class="score"><div class="v">15%</div><div class="k">权重</div></div>
        </div>
      </div>
    </div>
  </section>

  <!-- ── 知识库（暗带） ── -->
  <section class="kb-band" id="kb">
    <div class="wrap kb-grid">
      <div class="kb-copy">
        <span class="eyebrow" v-reveal>个人知识库 · Second Brain</span>
        <h2 class="d2" v-reveal="0.08">面试暴露的每一个漏洞，<br />都变成笔记里的一条链</h2>
        <p v-reveal="0.16">
          报告里的薄弱点可一键入库；[[双链语法]] 把零散笔记连成网，
          父文档检索让长文也能被精准召回，AI 对话只基于你的资料回答并标注来源。
        </p>
        <ul class="kb-feats" data-stagger>
          <li v-reveal><span><Icon name="hash" /></span><span>双链笔记 · [[标题]] 互相链接，反向链接自动汇总</span><span class="meta">Wiki Links</span></li>
          <li v-reveal><span><Icon name="layers" /></span><span>父文档检索 · 子块索引、父块返回，长文不失真</span><span class="meta">Parent Retrieval</span></li>
          <li v-reveal><span><Icon name="graph" /></span><span>知识图谱 · 显式双链 + 语义关联双色成图</span><span class="meta">Graph</span></li>
          <li v-reveal><span><Icon name="chat" /></span><span>RAG 问答 · 多轮对话，答案附带来源与相似度</span><span class="meta">Grounded QA</span></li>
        </ul>
        <div v-reveal style="margin-top:34px; display:flex; gap:16px; flex-wrap:wrap">
          <RouterLink class="btn btn-verm" to="/knowledge">进入知识库<Icon name="arrowRight" class="ar" /></RouterLink>
          <RouterLink class="btn btn-ghost" to="/knowledge/graph">看知识图谱</RouterLink>
        </div>
      </div>

      <div class="kb-visual" v-reveal="0.14">
        <div class="frame">
          <svg viewBox="0 0 460 330" aria-hidden="true">
            <g class="gedge">
              <path d="M96 92 190 56"/><path d="M190 56 300 96"/><path d="M96 92 168 178"/>
              <path d="M168 178 300 96"/><path d="M168 178 262 262"/><path d="M300 96 262 262"/>
              <path d="M300 96 392 170"/><path d="M262 262 392 170"/><path d="M96 92 62 210"/>
              <path d="M62 210 168 178"/>
            </g>
            <g class="gedge sem">
              <path d="M96 92 262 262"/><path d="M190 56 168 178"/><path d="M62 210 300 96"/>
            </g>
            <circle cx="96" cy="92" r="14" fill="var(--indigo-ink)" stroke="var(--paper)" stroke-width="2"/>
            <circle cx="190" cy="56" r="19" fill="var(--pine)" stroke="var(--paper)" stroke-width="2"/>
            <circle cx="300" cy="96" r="12" fill="var(--ochre)" stroke="var(--paper)" stroke-width="2"/>
            <circle cx="168" cy="178" r="23" fill="var(--indigo-ink)" stroke="var(--paper)" stroke-width="2"/>
            <circle cx="262" cy="262" r="11" fill="var(--ink-3)" stroke="var(--paper)" stroke-width="2"/>
            <circle cx="392" cy="170" r="15" fill="var(--pine)" stroke="var(--paper)" stroke-width="2"/>
            <circle cx="62" cy="210" r="9" fill="var(--ochre)" stroke="var(--paper)" stroke-width="2"/>
            <g class="gpulse"><circle cx="168" cy="178" r="36" fill="none" stroke="rgba(217,58,31,.5)"/></g>
            <g class="gpulse" style="animation-delay:1.2s"><circle cx="190" cy="56" r="30" fill="none" stroke="rgba(240,234,216,.25)"/></g>
            <g class="glabel">
              <text x="96" y="126" text-anchor="middle">RAG 流程</text>
              <text x="190" y="30" text-anchor="middle">Transformer</text>
              <text x="300" y="126" text-anchor="middle">Agent 工具</text>
              <text x="168" y="216" text-anchor="middle">向量检索</text>
              <text x="262" y="290" text-anchor="middle">部署</text>
              <text x="392" y="200" text-anchor="middle">微调</text>
              <text x="62" y="238" text-anchor="middle">Memory</text>
            </g>
          </svg>
        </div>
        <div class="caption">
          <span>12 notes · 34 links · 18 semantic</span>
          <span>实时构建于本地</span>
        </div>
      </div>
    </div>
  </section>

  <!-- ── 页脚 ── -->
  <footer>
    <div class="wrap">
      <div class="foot-top">
        <div>
          <div class="foot-word">练到临场不慌，<br />答到点子上。</div>
          <div style="display:flex; gap:14px; align-items:center; margin-top:26px">
            <span class="stamp stamp-sm" style="--sz:64px; font-size:16px">模拟面试</span>
            <span class="mono">Mock Interview · Since 2026</span>
          </div>
        </div>
        <div class="foot-cols">
          <div class="foot-col">
            <h5>Interview</h5>
            <RouterLink to="/resume-upload">简历匹配</RouterLink>
            <RouterLink to="/choose-job">选择岗位</RouterLink>
            <RouterLink to="/interview-records">面试记录</RouterLink>
            <RouterLink to="/summary/demo">评估报告</RouterLink>
          </div>
          <div class="foot-col">
            <h5>Knowledge</h5>
            <RouterLink to="/knowledge">我的笔记</RouterLink>
            <RouterLink to="/knowledge/graph">知识图谱</RouterLink>
            <RouterLink to="/knowledge/chat">AI 对话</RouterLink>
          </div>
          <div class="foot-col">
            <h5>System</h5>
            <RouterLink to="/login">登录 / 注册</RouterLink>
          </div>
        </div>
      </div>
      <div class="foot-bottom">
        <span>Local First · FastAPI + LangGraph + Vue · 数据不出本机</span>
        <span>© 2026 AI 模拟面试官 · 前端重构原型</span>
      </div>
    </div>
  </footer>
  </div>
</template>

<style scoped>
/* ── 滚动进度 ── */
.scroll-line { position: fixed; top: 0; left: 0; right: 0; height: 2px; z-index: 80; background: transparent; }
.scroll-line i { display: block; height: 100%; width: 0; background: var(--vermilion); }

/* ── 公共顶栏 ── */
.pubnav {
  position: sticky; top: 0; z-index: 60;
  display: flex; align-items: center; justify-content: space-between; gap: 22px;
  padding: 16px var(--gutter);
  background: color-mix(in srgb, var(--paper) 86%, transparent);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--line);
}
.pubnav .brandmark { flex-shrink: 0; }
.pubnav-links { display: flex; gap: 30px; }
.pubnav-links a {
  position: relative; font-size: 14px; color: var(--ink-2);
  padding-bottom: 3px; white-space: nowrap; transition: color var(--dur-1) ease;
}
.pubnav-links a::after {
  content: ''; position: absolute; left: 0; bottom: 0; width: 100%; height: 1px;
  background: var(--vermilion); transform: scaleX(0); transform-origin: left;
  transition: transform var(--dur-2) var(--ease);
}
.pubnav-links a:hover { color: var(--ink); }
.pubnav-links a:hover::after { transform: scaleX(1); }
.pubnav-cta { display: flex; align-items: center; gap: 14px; }

/* ── HERO ── */
.hero { position: relative; padding: clamp(46px, 7vw, 96px) 0 clamp(50px, 7vw, 96px); overflow: hidden; }
.hero::before {
  content: ''; position: absolute; inset: 0; z-index: -1;
  background:
    radial-gradient(880px 480px at 88% -12%, rgba(217,58,31,.10), transparent 62%),
    linear-gradient(var(--line-soft) 1px, transparent 1px) 0 0 / 100% 108px;
}
.hero-grid { display: grid; grid-template-columns: 1.02fr 0.98fr; gap: clamp(34px, 5vw, 76px); align-items: center; }
.hero-title { margin: 26px 0 24px; }
.hero-title .row { display: block; }
.hero-title .mark { padding-bottom: 4px; background-size: 100% 4px; }
.hero-actions { display: flex; align-items: center; gap: 22px; flex-wrap: wrap; margin-top: 34px; }
.hero-meta {
  display: flex; gap: 26px; margin-top: 40px; padding-top: 22px;
  border-top: 1px solid var(--line);
}
.hero-meta .m { display: flex; align-items: center; gap: 9px; font-family: var(--f-mono); font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--ink-3); white-space: nowrap; }
.hero-meta .m .ic { color: var(--vermilion); }

/* ── HERO 右侧：档案卡叠放 ── */
.hero-stage { position: relative; min-height: 480px; }
.card-doc {
  position: absolute;
  background: var(--sheet);
  border: 1px solid var(--line-strong);
  border-radius: var(--r-1);
  box-shadow: var(--sh-lift);
}
.tape {
  position: absolute; width: 92px; height: 26px;
  background: rgba(217, 58, 31, 0.14);
  border-left: 1px dashed rgba(217,58,31,.28);
  border-right: 1px dashed rgba(217,58,31,.28);
  top: -13px; left: 50%; transform: translateX(-50%) rotate(-1.5deg);
}
.tape.dark { background: rgba(35, 64, 92, 0.14); border-color: rgba(35,64,92,.3); }

.doc-score {
  top: 8px; left: 0; width: 74%;
  padding: 24px 24px 20px;
  animation: floaty 7s ease-in-out infinite;
}
.doc-score .doc-head { display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid var(--line); padding-bottom: 12px; margin-bottom: 14px; }
.doc-score .doc-title { font-family: var(--f-display); font-weight: 900; font-size: 16px; }
.doc-body { display: grid; grid-template-columns: 132px 1fr; gap: 18px; align-items: center; }
.radar { width: 132px; height: 132px; }
.dim-list { display: flex; flex-direction: column; gap: 10px; }
.dim { display: grid; grid-template-columns: 44px 1fr 34px; align-items: center; gap: 10px; font-size: 12px; color: var(--ink-2); }
.dim .track { height: 4px; background: var(--line-soft); position: relative; }
.dim .track i { position: absolute; inset: 0 auto 0 0; background: var(--ink); }
.dim .track i.v { background: var(--vermilion); }
.dim .val { font-family: var(--f-mono); font-size: 11.5px; text-align: right; color: var(--ink); }

.doc-transcript {
  bottom: 26px; right: 0; width: 76%;
  padding: 22px 24px;
  transform: rotate(1.6deg);
  animation: floaty 8s ease-in-out 0.8s infinite;
}
.doc-transcript .line { display: flex; gap: 10px; font-size: 13.5px; line-height: 1.85; }
.doc-transcript .who { font-family: var(--f-mono); font-size: 10px; letter-spacing: 0.14em; color: var(--vermilion); padding-top: 5px; flex-shrink: 0; width: 42px; }
.doc-transcript .who.me { color: var(--indigo-ink); }
.doc-transcript .txt { color: var(--ink-2); }
.doc-transcript .hi { color: var(--ink); font-weight: 500; background: var(--verm-wash); }

.doc-graph {
  bottom: -14px; left: 6%; width: 190px; height: 150px;
  padding: 14px;
  transform: rotate(-2.5deg);
  animation: floaty 6.4s ease-in-out 0.4s infinite;
}

.stamp-float {
  position: absolute; top: -8px; right: 4%;
  --sz: 84px; font-size: 15px; line-height: 1.2; text-align: center;
  animation: floaty 6s ease-in-out 1.4s infinite;
}

/* ── 数字带 ── */
.statband { border-bottom: 1px solid var(--line); background: var(--paper-deep); }
.statband-grid { display: grid; grid-template-columns: repeat(4, 1fr); }
.statband .cell {
  padding: 30px clamp(18px, 3vw, 38px);
  border-left: 1px solid var(--line);
  display: flex; flex-direction: column; gap: 6px;
}
.statband .cell:first-child { border-left: 0; }
.statband .n { font-family: var(--f-mono); font-weight: 700; font-size: clamp(30px, 3.4vw, 44px); letter-spacing: -0.03em; line-height: 1; }
.statband .n sup { font-size: 0.45em; color: var(--vermilion); margin-left: 4px; }
.statband .l { font-size: 13px; color: var(--ink-3); }
.statband .e { font-family: var(--f-mono); font-size: 10px; letter-spacing: 0.2em; text-transform: uppercase; color: var(--ink-4); }

/* ── 训练路径 ── */
.modes { padding: var(--section-y) 0; }
.modes-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0; border-top: 1px solid var(--line-strong); }
.mode-row {
  position: relative;
  padding: clamp(30px, 4vw, 54px) clamp(24px, 3vw, 46px) clamp(34px, 4vw, 54px);
  border-bottom: 1px solid var(--line);
  border-right: 1px solid var(--line);
  overflow: hidden;
  display: flex; flex-direction: column; gap: 18px;
  min-height: 340px;
  transition: color var(--dur-2) ease;
}
.mode-row:last-child { border-right: 0; }
.mode-row::before {
  content: ''; position: absolute; inset: 0;
  background: var(--ink);
  transform: translateY(101%);
  transition: transform 0.5s var(--ease);
  z-index: 0;
}
.mode-row:hover::before { transform: translateY(0); }
.mode-row > * { position: relative; z-index: 1; }
.mode-row .no { font-family: var(--f-mono); font-size: 12px; font-weight: 700; letter-spacing: 0.16em; color: var(--vermilion); }
.mode-row h3 { font-size: clamp(22px, 2.3vw, 30px); transition: color var(--dur-2) ease; }
.mode-row p { color: var(--ink-2); font-size: 14.5px; line-height: 1.9; max-width: 40ch; transition: color var(--dur-2) ease; }
.mode-row .tags { display: flex; gap: 8px; flex-wrap: wrap; }
.mode-row .tag { transition: all var(--dur-2) ease; }
.mode-row .go {
  margin-top: auto; display: inline-flex; align-items: center; gap: 9px;
  font-family: var(--f-mono); font-size: 11.5px; letter-spacing: 0.18em; text-transform: uppercase;
  color: var(--ink); transition: color var(--dur-2) ease;
}
.mode-row .go .ic { transition: transform var(--dur-2) var(--ease); }
.mode-row:hover h3, .mode-row:hover .go { color: var(--room-ink); }
.mode-row:hover p { color: rgba(240,234,216,.68); }
.mode-row:hover .tag { border-color: rgba(240,234,216,.3); color: rgba(240,234,216,.85); }
.mode-row:hover .go .ic { transform: translateX(6px); }
.mode-row:hover .no { color: var(--vermilion); }

/* ── 流程 ── */
.flow { padding: var(--section-y) 0; background: var(--sheet-2); border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
.flow-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 0; margin-top: 8px; }
.flow-step {
  position: relative;
  padding: 34px clamp(16px, 2vw, 30px) 30px;
  border-left: 1px solid var(--line);
  transition: background var(--dur-2) ease;
}
.flow-step:first-child { border-left: 0; }
.flow-step:hover { background: var(--sheet); }
.flow-step .n {
  font-family: var(--f-mono); font-weight: 700; font-size: 52px; line-height: 1;
  color: transparent; -webkit-text-stroke: 1px var(--ink-4);
  transition: -webkit-text-stroke-color var(--dur-2) ease, color var(--dur-2) ease;
}
.flow-step:hover .n { -webkit-text-stroke-color: var(--vermilion); }
.flow-step h4 { margin: 18px 0 8px; font-size: 17px; }
.flow-step p { font-size: 13px; color: var(--ink-3); line-height: 1.8; }
.flow-step .node {
  position: absolute; top: 39px; right: -4px;
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--paper); border: 1px solid var(--line-strong);
}
.flow-step:hover .node { background: var(--vermilion); border-color: var(--vermilion); box-shadow: 0 0 0 4px var(--verm-wash); }

/* ── 评估体系 ── */
.eval { padding: var(--section-y) 0; }
.eval-grid { display: grid; grid-template-columns: 0.9fr 1.1fr; gap: clamp(34px, 6vw, 96px); align-items: start; }
.eval-sticky { position: sticky; top: 104px; }
.eval-sticky .sheet { padding: 26px; display: inline-block; }
.dim-rows { border-top: 1px solid var(--line-strong); }
.dim-row {
  display: grid; grid-template-columns: 52px 1fr 96px;
  gap: 18px; align-items: baseline;
  padding: 26px 6px;
  border-bottom: 1px solid var(--line);
  transition: background var(--dur-2) ease, padding-left var(--dur-2) var(--ease);
}
.dim-row:hover { background: var(--sheet); padding-left: 16px; }
.dim-row .no { font-family: var(--f-mono); font-size: 12px; color: var(--vermilion); font-weight: 700; }
.dim-row h4 { font-size: 19px; margin-bottom: 6px; }
.dim-row p { font-size: 13.5px; color: var(--ink-3); line-height: 1.8; max-width: 44ch; }
.dim-row .score { text-align: right; }
.dim-row .score .v { font-family: var(--f-mono); font-weight: 700; font-size: 21px; }
.dim-row .score .k { font-family: var(--f-mono); font-size: 10px; letter-spacing: 0.18em; color: var(--ink-4); text-transform: uppercase; }

/* ── 知识库（暗带） ── */
.kb-band { position: relative; background: var(--ink); color: var(--room-ink); padding: var(--section-y) 0; overflow: hidden; }
.kb-band::before {
  content: ''; position: absolute; inset: 0;
  background: radial-gradient(760px 420px at 88% 10%, rgba(35,64,92,.5), transparent 60%),
              radial-gradient(620px 420px at 6% 96%, rgba(217,58,31,.2), transparent 60%);
}
.kb-grid { position: relative; display: grid; grid-template-columns: 1.05fr 0.95fr; gap: clamp(34px, 5vw, 80px); align-items: center; }
.kb-copy .eyebrow { color: rgba(240,234,216,.72); }
.kb-copy h2 { font-size: clamp(26px, 3.1vw, 44px); color: var(--room-ink); margin: 20px 0 20px; }
.kb-copy p { color: rgba(240,234,216,.66); font-size: 15px; line-height: 2; max-width: 46ch; }
.kb-feats { margin-top: 34px; border-top: 1px solid var(--room-line); }
.kb-feats li {
  display: grid; grid-template-columns: 30px 1fr auto; gap: 12px; align-items: center;
  padding: 15px 0; border-bottom: 1px solid var(--room-line);
  font-size: 14px; color: rgba(240,234,216,.88);
}
.kb-feats .ic { color: var(--vermilion); }
.kb-feats .meta { font-family: var(--f-mono); font-size: 10px; letter-spacing: 0.16em; text-transform: uppercase; color: rgba(240,234,216,.4); }
.kb-band .btn-ghost { color: var(--room-ink); border-color: var(--room-line); }
.kb-band .btn-ghost:hover { color: var(--sheet); }

.kb-visual { position: relative; }
.kb-visual .frame {
  border: 1px solid var(--room-line);
  background: rgba(240,234,216,.03);
  border-radius: var(--r-1);
  padding: 26px;
}
.kb-visual .caption { display: flex; justify-content: space-between; margin-top: 14px; font-family: var(--f-mono); font-size: 10.5px; letter-spacing: 0.16em; text-transform: uppercase; color: rgba(240,234,216,.45); }
.gnode { fill: none; stroke-width: 1.3; }
.gedge { stroke: rgba(240,234,216,.22); stroke-width: 1; }
.gedge.sem { stroke-dasharray: 3 5; }
.glabel { font-family: var(--f-mono); font-size: 8.6px; fill: rgba(240,234,216,.62); letter-spacing: 0.06em; }
.gpulse { animation: pulse 2.6s ease-in-out infinite; }
@keyframes dash { to { stroke-dashoffset: -60; } }
.gedge.sem { animation: dash 6s linear infinite; }

/* ── 页脚 ── */
footer { background: var(--paper); border-top: 1px solid var(--line); padding: clamp(46px, 6vw, 76px) 0 34px; }
.foot-top { display: flex; justify-content: space-between; gap: 40px; flex-wrap: wrap; }
.foot-word { font-family: var(--f-display); font-weight: 900; font-size: clamp(38px, 5vw, 64px); line-height: 1.1; }
.foot-cols { display: flex; gap: clamp(30px, 5vw, 78px); }
.foot-col h5 { font-family: var(--f-mono); font-size: 10.5px; letter-spacing: 0.22em; text-transform: uppercase; color: var(--ink-4); margin-bottom: 14px; }
.foot-col a { display: block; font-size: 14px; color: var(--ink-2); padding: 5px 0; transition: color var(--dur-1) ease, transform var(--dur-2) var(--ease); }
.foot-col a:hover { color: var(--vermilion); transform: translateX(3px); }
.foot-bottom {
  margin-top: 52px; padding-top: 20px; border-top: 1px solid var(--line);
  display: flex; justify-content: space-between; gap: 18px; flex-wrap: wrap;
  font-family: var(--f-mono); font-size: 10.5px; letter-spacing: 0.16em; text-transform: uppercase; color: var(--ink-4);
}

/* ── 响应式 ── */
@media (max-width: 1080px) {
  .hero-grid { grid-template-columns: 1fr; }
  .hero-stage { min-height: 430px; max-width: 560px; }
  .eval-grid { grid-template-columns: 1fr; }
  .eval-sticky { position: static; }
  .kb-grid { grid-template-columns: 1fr; }
}
@media (max-width: 820px) {
  .pubnav-links { display: none; }
  .modes-grid, .flow-grid, .statband-grid { grid-template-columns: 1fr 1fr; }
  .mode-row { min-height: auto; }
  .statband .cell:nth-child(3) { border-left: 0; }
  .flow-step:nth-child(3) { border-left: 0; }
  .hero-meta { flex-wrap: wrap; gap: 14px 22px; }
}
@media (max-width: 560px) {
  .pubnav { gap: 12px; }
  .pubnav-cta .tlink { display: none; }
  .pubnav .brandmark .sub { display: none; }
  .pubnav .brandmark .name { font-size: 15px; }
  .modes-grid, .flow-grid, .statband-grid { grid-template-columns: 1fr; }
  .statband .cell { border-left: 0; border-top: 1px solid var(--line); }
  .flow-step { border-left: 0; border-top: 1px solid var(--line); }
  .hero-stage { min-height: 420px; }
  .doc-score { width: 100%; }
  .doc-transcript { width: 100%; right: auto; left: 0; bottom: 0; }
  .doc-graph { display: none; }
}
</style>