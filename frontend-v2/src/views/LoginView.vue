<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { login, register } from '../api'
import { saveAuth } from '../auth'
import Icon from '../components/Icon.vue'
import { toast } from '../composables/useToast'

const route = useRoute()
const router = useRouter()

const mode = ref('login')
const username = ref('')
const password = ref('')
const password2 = ref('')
const loading = ref(false)
const errorMsg = ref('')
const noticeMsg = ref('')

function switchMode(key) {
  mode.value = key
  errorMsg.value = ''
  noticeMsg.value = ''
  password.value = ''
  password2.value = ''
}

function goHome() {
  const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
  router.replace(redirect.startsWith('/') ? redirect : '/')
}

async function submit() {
  if (loading.value) return
  errorMsg.value = ''
  noticeMsg.value = ''
  if (mode.value === 'register' && password.value !== password2.value) {
    errorMsg.value = '两次输入的密码不一致'
    return
  }
  loading.value = true
  try {
    const action = mode.value === 'login' ? login : register
    const result = await action(username.value.trim(), password.value)
    if (!result.success) {
      errorMsg.value = result.message || (mode.value === 'login' ? '登录失败' : '注册失败')
      return
    }
    saveAuth(result.token, result.username)
    toast(mode.value === 'login' ? '登录成功，正在进入训练场' : '注册成功，已自动登录')
    goHome()
  } finally {
    loading.value = false
  }
}

function quickDemo() {
  username.value = 'admin'
  password.value = '123123'
  toast('已填入演示账号，点击登录即可', 'bulb')
}
</script>

<template>
  <div class="auth">
    <!-- 左：品牌宣言 -->
    <aside class="auth-brand">
      <div class="brand-watermark">面试</div>

      <div class="brand-top">
        <div class="brandmark">
          <span class="seal">面</span>
          <span>
            <span class="name">AI 模拟面试官</span>
            <span class="sub" style="display:block">Interview Studio</span>
          </span>
        </div>
        <span class="mono" style="color:rgba(240,234,216,.42)">EST. 2026 · 本地运行</span>
      </div>

      <div class="brand-mid">
        <span class="eyebrow" style="color:rgba(240,234,216,.7)">Mock Interview · 训练场</span>
        <h2>练到临场不慌，<br />答到<em>点子</em>上。</h2>
        <p>上传简历智能匹配岗位，LangGraph 人在回路真实追问，面试结束生成四维评估报告，薄弱点一键沉淀进个人知识库。</p>
      </div>

      <div>
        <ul class="brand-list">
          <li><span class="no">01</span><span>简历解析与岗位匹配，按技能画像出题</span><span class="meta">Resume → Role</span></li>
          <li><span class="no">02</span><span>混合检索题库 + 低分追问，还原真实面试节奏</span><span class="meta">Hybrid RAG</span></li>
          <li><span class="no">03</span><span>四维评估与好差答案对比，反馈可执行</span><span class="meta">Report</span></li>
          <li><span class="no">04</span><span>双链笔记构建知识体系，薄弱点自动入库</span><span class="meta">Knowledge</span></li>
        </ul>

        <div class="brand-foot" style="margin-top:36px">
          <div class="stats">
            <div class="stat"><div class="n">133</div><div class="l">精选题库</div></div>
            <div class="stat"><div class="n">4</div><div class="l">评估维度</div></div>
            <div class="stat"><div class="n">2</div><div class="l">练习路径</div></div>
          </div>
          <div class="seal-ring" aria-hidden="true">
            <svg class="ring" viewBox="0 0 118 118">
              <defs><path id="circ" d="M59,59 m-46,0 a46,46 0 1,1 92,0 a46,46 0 1,1 -92,0" /></defs>
              <text><textPath href="#circ">AI INTERVIEW STUDIO · 模拟面试 · 四维评估 · 知识沉淀 · </textPath></text>
            </svg>
            <span class="core">面</span>
          </div>
        </div>
      </div>
    </aside>

    <!-- 右：登录 / 注册 -->
    <main class="auth-form-side">
      <span class="reg tl"></span><span class="reg tr"></span><span class="reg bl"></span><span class="reg br"></span>

      <div class="auth-card rv is-in">
        <div class="folio">
          <span>档案入口 · Dossier Access</span>
          <span>№ 0001</span>
        </div>

        <div class="tabs">
          <button class="tab" :class="{ 'is-on': mode === 'login' }" @click="switchMode('login')">登录</button>
          <button class="tab" :class="{ 'is-on': mode === 'register' }" @click="switchMode('register')">注册</button>
        </div>

        <form @submit.prevent="submit">
          <div class="field">
            <label class="field-label" for="u1">用户名 / Username</label>
            <input id="u1" v-model="username" class="input" autocomplete="username"
                   placeholder="3–20 位字母、数字或下划线" :disabled="loading" />
          </div>

          <div class="field">
            <label class="field-label" for="p1">密码 / Password</label>
            <input id="p1" v-model="password" class="input" type="password" :disabled="loading"
                   :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" placeholder="至少 6 位" />
          </div>

          <div v-if="mode === 'register'" class="field">
            <label class="field-label" for="p2">确认密码 / Confirm</label>
            <input id="p2" v-model="password2" class="input" type="password" autocomplete="new-password"
                   :disabled="loading" placeholder="再输入一次密码" />
          </div>

          <div v-if="errorMsg" class="form-msg err">
            <Icon name="alert" /><span>{{ errorMsg }}</span>
          </div>
          <div v-else-if="noticeMsg" class="form-msg ok">
            <Icon name="checkCircle" /><span>{{ noticeMsg }}</span>
          </div>
          <div v-else-if="mode === 'register' && password2 && password === password2" class="form-msg ok">
            <Icon name="checkCircle" /><span>两次密码一致，可以创建账号。</span>
          </div>

          <div v-if="mode === 'login'" class="form-note">
            <Icon name="bulb" />
            <span>演示账号 <b style="font-family:var(--f-mono)">admin / 123123</b>，
              <a href="javascript:void(0)" style="color:var(--vermilion); border-bottom:1px solid var(--verm-line)" @click="quickDemo">一键填入</a>
            </span>
          </div>

          <button class="btn btn-lg btn-block" type="submit" :disabled="loading || !username.trim() || !password">
            <span v-if="loading">{{ mode === 'login' ? '登录中…' : '注册中…' }}</span>
            <template v-else>
              {{ mode === 'login' ? '进入训练场' : '注册并进入' }}<Icon name="arrowRight" class="ar" />
            </template>
          </button>

          <p class="auth-alt">
            {{ mode === 'login' ? '还没有账号？' : '已有账号？' }}
            <a href="javascript:void(0)" @click="switchMode(mode === 'login' ? 'register' : 'login')">
              {{ mode === 'login' ? '注册新用户' : '返回登录' }}
            </a>
          </p>
        </form>

        <div class="privacy-foot">
          <span>JWT 鉴权 · 数据按用户隔离</span>
          <span>Local First · 不出本机</span>
        </div>
      </div>
    </main>
  </div>
</template>

<style scoped>
.auth { display: grid; grid-template-columns: 1fr 1.06fr; min-height: 100vh; }

/* ── 左：宣言面板（暗面） ── */
.auth-brand {
  position: relative;
  background: var(--ink);
  color: var(--room-ink);
  padding: clamp(32px, 4vw, 60px);
  display: flex; flex-direction: column; justify-content: space-between;
  overflow: hidden; isolation: isolate;
}
.auth-brand::before {
  content: ''; position: absolute; inset: 0; z-index: -1;
  background:
    radial-gradient(720px 420px at 12% 4%, rgba(217,58,31,.16), transparent 62%),
    radial-gradient(560px 520px at 96% 96%, rgba(35,64,92,.34), transparent 60%);
}
.brand-watermark {
  position: absolute; right: -30px; top: 50%; transform: translateY(-50%);
  writing-mode: vertical-rl;
  font-family: var(--f-display); font-weight: 900;
  font-size: clamp(120px, 16vw, 230px); line-height: 1; letter-spacing: 0.1em;
  color: rgba(240, 234, 216, 0.045);
  user-select: none; z-index: -1;
}
.brand-top { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.brand-top .brandmark .sub { color: rgba(240,234,216,.5); }
.brand-top .brandmark .name { color: var(--room-ink); }
.brand-top .brandmark .seal { background: var(--room-ink); color: var(--ink); }

.brand-mid { max-width: 460px; margin: clamp(40px, 7vh, 84px) 0; }
.brand-mid h2 {
  font-size: clamp(34px, 3.6vw, 56px); line-height: 1.22;
  margin: 22px 0 20px; color: var(--room-ink); letter-spacing: 0.02em;
}
.brand-mid h2 em { font-style: normal; color: var(--vermilion); }
.brand-mid p { color: rgba(240,234,216,.66); font-size: 15px; line-height: 2; max-width: 38ch; }

.brand-list { display: flex; flex-direction: column; gap: 0; border-top: 1px solid var(--room-line); }
.brand-list li {
  display: grid; grid-template-columns: 44px 1fr auto; align-items: center; gap: 14px;
  padding: 15px 2px; border-bottom: 1px solid var(--room-line);
  font-size: 14px; color: rgba(240,234,216,.86);
}
.brand-list .no { font-family: var(--f-mono); font-size: 11px; color: var(--vermilion); letter-spacing: 0.1em; }
.brand-list .meta { font-family: var(--f-mono); font-size: 10.5px; color: rgba(240,234,216,.4); letter-spacing: 0.12em; text-transform: uppercase; }

.brand-foot { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; }
.brand-foot .stats { display: flex; gap: 30px; }
.brand-foot .stat .n { font-family: var(--f-mono); font-weight: 700; font-size: 22px; color: var(--room-ink); letter-spacing: -0.02em; }
.brand-foot .stat .l { font-size: 11.5px; color: rgba(240,234,216,.5); margin-top: 2px; }

.seal-ring { position: relative; width: 118px; height: 118px; flex-shrink: 0; }
.seal-ring .ring { position: absolute; inset: 0; animation: spin 26s linear infinite; }
.seal-ring .core {
  position: absolute; inset: 30px;
  display: flex; align-items: center; justify-content: center;
  border: 1.5px solid var(--vermilion); color: var(--vermilion);
  font-family: var(--f-display); font-weight: 900; font-size: 26px;
  background: rgba(217,58,31,.06); border-radius: 2px; transform: rotate(-8deg);
}
.seal-ring text { font-family: var(--f-mono); font-size: 9.4px; letter-spacing: 3px; fill: rgba(240,234,216,.5); }

/* ── 右：表单面板 ── */
.auth-form-side {
  display: flex; align-items: center; justify-content: center;
  padding: clamp(32px, 5vw, 72px) var(--gutter);
  position: relative;
  background: linear-gradient(var(--line-soft) 1px, transparent 1px) 0 0 / 100% 96px, var(--paper);
}
.reg { position: absolute; width: 14px; height: 14px; border-color: var(--line-strong); border-style: solid; }
.reg.tl { top: 26px; left: 26px; border-width: 1px 0 0 1px; }
.reg.tr { top: 26px; right: 26px; border-width: 1px 1px 0 0; }
.reg.bl { bottom: 26px; left: 26px; border-width: 0 0 1px 1px; }
.reg.br { bottom: 26px; right: 26px; border-width: 0 1px 1px 0; }

.auth-card { width: 100%; max-width: 420px; position: relative; }
.auth-card .folio {
  display: flex; align-items: center; justify-content: space-between;
  font-family: var(--f-mono); font-size: 10.5px; letter-spacing: 0.2em; text-transform: uppercase;
  color: var(--ink-4); margin-bottom: 30px;
}

.tabs { display: flex; gap: 30px; border-bottom: 1px solid var(--line); margin-bottom: 34px; }
.tab {
  position: relative; padding: 0 0 13px;
  font-family: var(--f-display); font-weight: 900; font-size: 25px;
  color: var(--ink-4); transition: color var(--dur-2) ease;
}
.tab::after {
  content: ''; position: absolute; left: 0; bottom: -1px; width: 100%; height: 2px;
  background: var(--ink); transform: scaleX(0); transform-origin: left;
  transition: transform var(--dur-2) var(--ease);
}
.tab:hover { color: var(--ink-2); }
.tab.is-on { color: var(--ink); }
.tab.is-on::after { transform: scaleX(1); background: var(--vermilion); }

.form-note {
  display: flex; gap: 9px; align-items: flex-start;
  margin: 6px 0 26px; padding: 12px 14px;
  border: 1px dashed var(--line-strong); background: var(--sheet-2);
  font-size: 12.5px; color: var(--ink-2); line-height: 1.7;
}
.form-note .ic { color: var(--vermilion); flex-shrink: 0; margin-top: 2px; }

.form-msg { display: flex; gap: 9px; align-items: center; margin: 14px 0 18px; padding: 11px 14px; font-size: 13px; border: 1px solid; }
.form-msg.err { color: var(--vermilion-deep); border-color: var(--verm-line); background: var(--verm-wash); }
.form-msg.ok { color: var(--pine); border-color: rgba(46,107,80,.3); background: var(--pine-wash); }

.auth-alt { margin-top: 26px; font-size: 13px; color: var(--ink-3); display: flex; align-items: center; gap: 8px; }
.auth-alt a { color: var(--ink); font-weight: 600; border-bottom: 1px solid var(--line-strong); transition: color var(--dur-1) ease, border-color var(--dur-1) ease; }
.auth-alt a:hover { color: var(--vermilion); border-color: var(--vermilion); }

.privacy-foot {
  margin-top: 42px; padding-top: 18px; border-top: 1px solid var(--line);
  display: flex; justify-content: space-between; gap: 14px;
  font-family: var(--f-mono); font-size: 10.5px; letter-spacing: 0.14em;
  text-transform: uppercase; color: var(--ink-4);
}

@media (max-width: 920px) {
  .auth { grid-template-columns: 1fr; }
  .auth-brand { min-height: auto; padding: 30px var(--gutter) 36px; }
  .brand-mid { margin: 30px 0; }
  .brand-foot .seal-ring { display: none; }
  .brand-watermark { font-size: 150px; right: -30px; }
  .auth-form-side { padding: 46px var(--gutter) 60px; min-height: 60vh; }
  .reg { display: none; }
}
</style>