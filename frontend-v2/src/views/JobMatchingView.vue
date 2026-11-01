<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { analyzeJd, getApplication, getResume, getLatestResume, getRoles } from '../api'
import Icon from '../components/Icon.vue'
import TopBar from '../components/TopBar.vue'
import JdVersionPanel from '../components/JdVersionPanel.vue'

const router = useRouter()
const route = useRoute()
const application = ref(null)
const roles = ref([])
const resumeData = ref(null)
const suggestedRole = ref('')
const loadingRoles = ref(false)
const roleError = ref('')
const jdText = ref('')
const jdLoading = ref(false)
const jdError = ref('')
const jdResult = ref(null)
const loadingContext = ref(false)
const contextError = ref('')
let contextRequest = 0
let roleRequest = 0
watch(jdText, () => { jdResult.value = null })

const skillCount = computed(() => (resumeData.value?.skills || []).length)
const initial = computed(() => (resumeData.value?.name || '简').trim().charAt(0) || '简')
const skillPreview = computed(() => (resumeData.value?.skills || []).slice(0, 4))
const skillRest = computed(() => Math.max(skillCount.value - skillPreview.value.length, 0))

function isSuggested(role) {
  return !!suggestedRole.value && role.key === suggestedRole.value
}

function pad(n) {
  return String(n).padStart(2, '0')
}

async function loadRoles() {
  const requestId = ++roleRequest
  const contextId = contextRequest
  loadingRoles.value = true
  roleError.value = ''
  roles.value = []
  try {
    const result = await getRoles()
    if (requestId !== roleRequest || contextId !== contextRequest) return
    if (!result.success) {
      roleError.value = result.message || '岗位加载失败'
      return
    }
    if (!Array.isArray(result.roles) || result.roles.length === 0) {
      roleError.value = '后端未返回可用岗位，请检查题库配置'
      return
    }
    roles.value = [...result.roles]
    suggestedRole.value = resumeData.value?.suggested_role || ''
    const idx = roles.value.findIndex((role) => role.key === suggestedRole.value)
    if (idx > 0) {
      const [suggested] = roles.value.splice(idx, 1)
      roles.value.unshift(suggested)
    }
  } finally {
    if (requestId === roleRequest && contextId === contextRequest) loadingRoles.value = false
  }
}

async function runJdAnalysis() {
  if (!resumeData.value?.resume_id || !jdText.value.trim() || jdLoading.value) return
  jdLoading.value = true
  jdError.value = ''
  jdResult.value = null
  const analyzedText = jdText.value.trim()
  const requestId = contextRequest
  const result = await analyzeJd(resumeData.value.resume_id, analyzedText)
  if (requestId !== contextRequest) return
  jdLoading.value = false
  if (!result.success) {
    jdError.value = result.message || 'JD 分析失败'
    return
  }
  if (jdText.value.trim() === analyzedText) jdResult.value = result.analysis
}

function selectRole(role) {
  const config = {
    key: role.key,
    title: role.title,
    questionCount: 5,
    resumeContext: resumeData.value?.resume_context || '',
    resumeSkills: resumeData.value?.skills || [],
    applicationId: application.value?.id || null,
  }
  sessionStorage.setItem('selectedRole', JSON.stringify(config))
  // 记住最近一次面试配置(含简历上下文),刷新面试页可直接续上
  localStorage.setItem('interviewConfig', JSON.stringify({ key: role.key, title: role.title, questionCount: 5 }))
  router.push('/interview')
}

watch(() => route.query.application_id, async (applicationId) => {
  const requestId = ++contextRequest
  ++roleRequest
  application.value = resumeData.value = jdResult.value = null
  roles.value = []
  jdText.value = jdError.value = contextError.value = roleError.value = ''
  jdLoading.value = false
  loadingRoles.value = false
  loadingContext.value = true
  if (applicationId) {
    const result = await getApplication(Number(applicationId))
    if (requestId !== contextRequest) return
    if (!result.success || result.application.archived) {
      contextError.value = result.message || '投递档案不可用'
      loadingContext.value = false
      return
    }
    application.value = result.application
    jdText.value = result.application.jd_text || ''
    if (result.application.resume_id) {
      const resume = await getResume(result.application.resume_id)
      if (requestId !== contextRequest) return
      if (resume.success) resumeData.value = resume
      else jdError.value = resume.message || '关联简历不可用'
    }
    await loadRoles()
    if (requestId === contextRequest) loadingContext.value = false
    return
  }
  const stored = sessionStorage.getItem('resumeData')
  if (stored) {
    try {
      resumeData.value = JSON.parse(stored)
    } catch (_) {
      resumeData.value = null
    }
  }
  if (!resumeData.value?.resume_id) {
    const latest = await getLatestResume()
    if (requestId !== contextRequest) return
    if (latest.success) {
      resumeData.value = latest
      sessionStorage.setItem('resumeData', JSON.stringify(latest))
    }
  }
  await loadRoles()
  if (requestId === contextRequest) loadingContext.value = false
}, { immediate: true })
</script>

<template>
  <div>
    <TopBar crumb="岗位匹配" folio="卷·03">
      <template #actions>
        <RouterLink class="tlink" to="/resume-upload"><Icon name="arrowLeft" />返回上传</RouterLink>
      </template>
    </TopBar>

    <div class="page-body">
      <RouterLink v-if="application" class="tlink" :to="{ path: '/applications', query: { application_id: application.id } }"><Icon name="arrowLeft" />{{ application.company }} · {{ application.role_title }}</RouterLink>
      <p v-if="contextError" role="alert">{{ contextError }}</p>
      <div class="page-head" v-reveal>
        <span class="sec-index">RESUME → ROLE</span>
        <h1 class="page-title" style="margin-top:14px">挑一个方向，开始练</h1>
        <p class="page-sub">按技能画像推荐的方向排在最前。你也可以粘贴目标 JD，逐条核对已满足、未满足和证据不足的要求。</p>
      </div>

      <JdVersionPanel v-if="application" :key="application.id" v-model="jdText" :application="application" @saved="application = $event" />

      <!-- 无简历数据：引导回上传 -->
      <p v-if="loadingContext" role="status">正在读取档案…</p>
      <div v-else-if="!resumeData && !contextError" class="empty" v-reveal>
        <div class="empty-ic"><Icon name="file" :size="30" /></div>
        <div class="empty-title">还没有简历解析结果</div>
        <div class="empty-sub">请先上传或粘贴简历，系统会按技能画像为你推荐岗位。</div>
        <div style="margin-top:22px">
          <RouterLink class="btn" to="/resume-upload">去上传简历<span class="ar"><Icon name="arrowRight" /></span></RouterLink>
        </div>
      </div>

      <template v-else-if="resumeData">
        <div class="resume-strip" v-reveal="0.06">
          <div class="who">
            <span class="stamp-mini">{{ initial }}</span>
            <span>
              <span class="name">{{ resumeData.name || '未识别姓名' }}</span>
              <span class="meta" style="display:block">已完成简历分析 · {{ skillCount }} 项技能</span>
            </span>
          </div>
          <div class="skills">
            <span v-for="s in skillPreview" :key="s" class="tag">{{ s }}</span>
            <span v-if="skillRest > 0" class="tag">+{{ skillRest }}</span>
          </div>
        </div>

        <section class="jd-panel" :class="{ 'application-analysis': application }" v-reveal="0.08">
          <div class="jd-input">
            <label v-if="!application" class="field-label" for="jd-text">目标岗位 JD</label>
            <textarea v-if="!application" id="jd-text" v-model="jdText" class="textarea" rows="7" maxlength="16000" placeholder="粘贴岗位职责、任职要求和加分项"></textarea>
            <button class="btn" :disabled="jdLoading || !jdText.trim() || resumeData.parse_status !== 'reviewed'" @click="runJdAnalysis">
              {{ jdLoading ? '正在对照…' : '分析岗位要求' }}
            </button>
            <p v-if="resumeData.parse_status !== 'reviewed'" class="jd-hint">请先返回简历页审核并确认结构化信息。</p>
            <p v-if="jdError" class="jd-error">{{ jdError }}</p>
          </div>
          <div v-if="jdResult" class="jd-results">
            <div>
              <h3>硬性要求</h3>
              <div v-for="item in jdResult.hard_constraints" :key="item.requirement" class="constraint">
                <span class="status" :class="item.status">{{ item.status === 'met' ? '已满足' : item.status === 'unmet' ? '未满足' : '证据不足' }}</span>
                <strong>{{ item.requirement }}</strong>
                <p>{{ item.explanation }}</p>
              </div>
              <p v-if="!jdResult.hard_constraints.length" class="mono">未提取到明确硬性要求</p>
            </div>
            <div>
              <h3>待补充与追问</h3>
              <ul class="jd-list"><li v-for="item in jdResult.gaps" :key="item.requirement">{{ item.requirement }} · {{ item.candidate_status === 'unknown' ? '需补证据' : '当前未体现' }}</li></ul>
              <ul class="jd-list"><li v-for="item in jdResult.next_questions" :key="item">{{ item }}</li></ul>
            </div>
            <div v-if="jdResult.suggestions.length" class="wide">
              <h3>表达建议</h3>
              <div v-for="item in jdResult.suggestions" :key="item.section + item.suggested" class="suggestion">
                <b>{{ item.section }}</b><span>{{ item.current || '原简历未体现' }}</span><span>{{ item.suggested }}</span>
              </div>
            </div>
          </div>
        </section>

        <div v-if="loadingRoles" class="role-state" v-reveal>
          <span class="spin" style="display:inline-block; width:18px; height:18px; border:2px solid var(--line-strong); border-top-color:var(--vermilion); border-radius:50%"></span>
          正在加载岗位…
        </div>

        <div v-else-if="roleError" class="load-error" v-reveal>
          <span><Icon name="alert" :size="15" />{{ roleError }}</span>
          <button class="btn btn-ghost btn-sm" @click="loadRoles"><Icon name="refresh" :size="14" />重新加载</button>
        </div>

        <div v-else-if="!roles.length" class="empty" v-reveal>
          <div class="empty-ic"><Icon name="pin" :size="28" /></div>
          <div class="empty-title">暂无可选岗位</div>
          <div class="empty-sub">后端未返回岗位，请检查题库配置后重试。</div>
        </div>

        <div v-else class="role-grid" data-stagger>
          <article
            v-for="(role, idx) in roles"
            :key="role.key"
            class="role-card sheet sheet-hover"
            :class="{ 'is-best': idx === 0 && isSuggested(role) }"
            v-reveal
            @click="selectRole(role)"
          >
            <span v-if="isSuggested(role)" class="corner-tag verm">推荐 · MATCH</span>
            <span class="no">№ {{ pad(idx + 1) }}</span>
            <h3>{{ role.title }}</h3>
            <div class="tags">
              <span v-for="tag in role.tags.slice(0, 5)" :key="tag" class="tag">{{ tag }}</span>
            </div>
            <div class="foot">
              <span class="role-note">{{ isSuggested(role) ? '基于技能画像优先展示' : '可直接选择此方向' }}</span>
              <button
                class="btn btn-sm"
                :class="{ 'btn-ghost': !(idx === 0 && isSuggested(role)) }"
                @click.stop="selectRole(role)"
              >
                开始面试<span class="ar"><Icon name="arrowRight" /></span>
              </button>
            </div>
          </article>
        </div>

      </template>
    </div>
  </div>
</template>

<style scoped>
  /* 简历摘要条 */
  .resume-strip {
    display: flex; align-items: center; gap: 22px; flex-wrap: wrap;
    padding: 18px 24px;
    border: 1px solid var(--line);
    background: var(--sheet-2);
    border-left: 3px solid var(--pine);
  }
  .resume-strip .who { display: flex; align-items: center; gap: 12px; }
  .resume-strip .stamp-mini {
    width: 42px; height: 42px; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    background: var(--ink); color: var(--paper);
    font-family: var(--f-display); font-weight: 900; font-size: 19px;
  }
  .resume-strip .name { font-family: var(--f-display); font-weight: 900; font-size: 17px; }
  .resume-strip .meta { font-family: var(--f-mono); font-size: 10.5px; letter-spacing: 0.16em; text-transform: uppercase; color: var(--ink-3); }
  .resume-strip .skills { display: flex; gap: 7px; flex-wrap: wrap; margin-left: auto; }
  .jd-panel { display: grid; grid-template-columns: minmax(280px, .8fr) minmax(0, 1.2fr); gap: 24px; margin-top: 26px; padding: 24px; border: 1px solid var(--line); background: var(--sheet); }
  .jd-input { display: grid; gap: 12px; align-content: start; }
  .jd-panel.application-analysis { grid-template-columns: minmax(0, 1fr); padding: 20px 0; border: 0; border-bottom: 1px solid var(--line); background: none; }
  .application-analysis .jd-input { justify-items: start; }
  .jd-hint, .jd-error { margin: 0; font-size: 12px; color: var(--ink-3); }
  .jd-error { color: var(--vermilion); }
  .jd-results { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; min-width: 0; }
  .jd-results .wide { grid-column: 1 / -1; }
  .jd-results h3 { font-size: 15px; margin-bottom: 12px; }
  .constraint { padding: 11px 0; border-top: 1px solid var(--line); }
  .constraint strong { font-size: 13px; }
  .constraint p { margin: 6px 0 0; color: var(--ink-3); font-size: 12px; line-height: 1.65; }
  .status { display: inline-block; margin-right: 8px; padding: 2px 5px; border: 1px solid var(--line); font: 10px var(--f-mono); }
  .status.met { color: var(--pine); border-color: var(--pine); }
  .status.unmet { color: var(--vermilion); border-color: var(--verm-line); }
  .jd-list { padding-left: 18px; color: var(--ink-2); font-size: 12px; line-height: 1.8; }
  .suggestion { display: grid; grid-template-columns: 100px 1fr 1fr; gap: 12px; padding: 10px 0; border-top: 1px solid var(--line); font-size: 12px; line-height: 1.6; }

  /* 加载 / 错误 */
  .role-state {
    margin-top: 34px; padding: 48px 24px;
    display: flex; align-items: center; justify-content: center; gap: 10px;
    color: var(--ink-3); font-size: 13.5px;
  }
  .load-error {
    margin-top: 34px; padding: 16px 20px;
    display: flex; align-items: center; justify-content: space-between; gap: 14px; flex-wrap: wrap;
    border: 1px solid var(--verm-line); background: var(--verm-wash);
    color: var(--vermilion-deep); font-size: 13px;
  }
  .load-error > span { display: inline-flex; align-items: center; gap: 9px; }

  /* 岗位卡片 */
  .role-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(310px, 1fr)); gap: 22px; margin-top: 34px; }
  .role-card { padding: 26px 26px 22px; display: flex; flex-direction: column; gap: 16px; position: relative; overflow: hidden; cursor: pointer; }
  .role-card .no { font-family: var(--f-mono); font-size: 11px; letter-spacing: 0.18em; color: var(--ink-4); }
  .role-card h3 { font-size: 20px; margin-top: -6px; }
  .role-card .tags { display: flex; gap: 7px; flex-wrap: wrap; }
  .role-card .foot { display: flex; align-items: flex-end; justify-content: space-between; gap: 14px; margin-top: auto; padding-top: 18px; border-top: 1px solid var(--line); }
  .role-note { color: var(--ink-3); font: 10px var(--f-mono); }
  .role-card.is-best { border-color: var(--line-strong); box-shadow: var(--sh-lift); }
  .role-card.is-best::after {
    content: ''; position: absolute; inset: 0; pointer-events: none;
    background: radial-gradient(320px 160px at 100% 0%, var(--verm-wash), transparent 70%);
  }

  .foot-note {
    margin-top: 40px; padding-top: 18px; border-top: 1px solid var(--line);
    display: flex; justify-content: space-between; gap: 16px; flex-wrap: wrap;
    font-family: var(--f-mono); font-size: 10.5px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink-4);
  }

  @media (max-width: 800px) { .jd-panel, .jd-results { grid-template-columns: 1fr; } .jd-results .wide { grid-column: auto; } }
  @media (max-width: 700px) { .resume-strip .skills { margin-left: 0; } .suggestion { grid-template-columns: 1fr; } }
</style>
