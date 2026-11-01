<script setup>
import { computed, onMounted, ref } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { getApplication, getJdVersion, listJdVersions, restoreJdVersion, saveJdVersion } from '../api'
import Icon from './Icon.vue'

const props = defineProps({ application: { type: Object, required: true }, modelValue: { type: String, default: '' } })
const emit = defineEmits(['update:modelValue', 'saved'])
const text = computed({ get: () => props.modelValue, set: (value) => emit('update:modelValue', value) })
const sourceUrl = ref(props.application.job_url || '')
const versions = ref([])
const selectedId = ref('')
const historical = ref(null)
const busy = ref(false)
const historyLoading = ref(false)
const error = ref('')
const notice = ref('')
const currentVersion = computed(() => props.application.jd_version?.version || 0)
const dirty = computed(() => text.value.trim() !== props.application.jd_text || sourceUrl.value.trim() !== props.application.job_url)
let selectionRequest = 0

function formatDate(value) {
  return new Date(value).toLocaleString('zh-CN')
}

async function loadHistory() {
  historyLoading.value = true
  const result = await listJdVersions(props.application.id)
  historyLoading.value = false
  if (!result.success) { error.value = result.message || '版本目录加载失败'; return }
  versions.value = result.versions || []
}

async function selectVersion() {
  const requestId = ++selectionRequest
  historical.value = null
  if (!selectedId.value) { historyLoading.value = false; return }
  historyLoading.value = true
  const result = await getJdVersion(props.application.id, Number(selectedId.value))
  if (requestId !== selectionRequest) return
  historyLoading.value = false
  if (!result.success) { error.value = result.message || '历史版本加载失败'; return }
  historical.value = result.version
}

async function acceptSaved(result, message) {
  if (!result.success) { error.value = result.message || 'JD 保存失败'; return }
  emit('saved', result.application)
  text.value = result.application.jd_text
  sourceUrl.value = result.application.job_url
  notice.value = message
  await loadHistory()
}

async function save() {
  if (busy.value || !dirty.value) return
  busy.value = true
  error.value = notice.value = ''
  try {
    const result = await saveJdVersion(props.application.id, {
      jd_text: text.value.trim(), source_url: sourceUrl.value.trim(), expected_version: currentVersion.value,
    })
    await acceptSaved(result, 'JD 版本已保存')
  } finally { busy.value = false }
}

async function restore() {
  if (busy.value || !historical.value || !confirm(`将 v${historical.value.version} 恢复为当前 JD？${dirty.value ? '未保存的草稿将被替换。' : ''}`)) return
  busy.value = true
  error.value = notice.value = ''
  try {
    await acceptSaved(await restoreJdVersion(props.application.id, historical.value.id, currentVersion.value), '已恢复为新版本')
  } finally { busy.value = false }
}

async function reloadCurrent() {
  if (busy.value || (dirty.value && !confirm('重新载入当前 JD？未保存的草稿将被替换。'))) return
  busy.value = true
  error.value = notice.value = ''
  try { await acceptSaved(await getApplication(props.application.id), '已载入最新 JD') }
  finally { busy.value = false }
}

onMounted(loadHistory)
function canLeave() {
  return !busy.value && (!dirty.value || confirm('离开此页？未保存的 JD 草稿将被丢弃。'))
}
onBeforeRouteLeave(canLeave)
onBeforeRouteUpdate((to, from) => to.query.application_id === from.query.application_id || canLeave())
</script>

<template>
  <section class="jd-versions" aria-label="JD 来源与版本">
    <header class="versions-head">
      <h2>JD 来源与版本</h2>
      <span class="version-label">当前 v{{ currentVersion }}<span v-if="dirty"> · 未保存</span></span>
      <button class="icon-btn" :disabled="busy" title="重新载入当前 JD" aria-label="重新载入当前 JD" @click="reloadCurrent"><Icon name="refresh" :size="16" /></button>
    </header>
    <div class="versions-grid">
      <div class="jd-draft">
        <label class="field-label" for="jd-source-url">来源链接</label>
        <input id="jd-source-url" v-model="sourceUrl" type="url" class="input-box" maxlength="2000" :disabled="busy" placeholder="https://…">
        <label class="field-label" for="jd-version-text">当前 JD</label>
        <textarea id="jd-version-text" v-model="text" class="input-box" rows="10" maxlength="20000" :disabled="busy" placeholder="岗位职责、任职要求和加分项"></textarea>
        <div class="version-actions">
          <button class="btn btn-sm" :disabled="busy || !dirty" @click="save"><Icon name="save" :size="14" />{{ busy ? '处理中…' : '保存版本' }}</button>
          <span class="version-label">{{ text.length }} 字</span>
        </div>
      </div>
      <div class="jd-history">
        <label class="field-label" for="jd-history-select">历史版本</label>
        <select id="jd-history-select" v-model="selectedId" class="input-box" :disabled="busy || historyLoading" @change="selectVersion">
          <option value="">选择版本</option>
          <option v-for="item in versions" :key="item.id" :value="item.id">v{{ item.version }} · {{ formatDate(item.created_at) }}{{ item.version === currentVersion ? ' · 当前' : '' }}</option>
        </select>
        <p v-if="historyLoading" class="version-label" role="status">正在读取…</p>
        <template v-else-if="historical">
          <dl class="version-meta">
            <dt>来源</dt><dd>{{ historical.source_url || '未填写' }}</dd>
            <dt>记录时间</dt><dd>{{ formatDate(historical.created_at) }}</dd>
            <dt>记录方式</dt><dd>{{ historical.source === 'restore' ? `恢复历史 #${historical.restored_from}` : historical.source === 'migration' ? '既有档案补录' : '手动保存' }}</dd>
            <dt>SHA-256</dt><dd class="hash">{{ historical.content_hash }}</dd>
          </dl>
          <pre class="historical-text" aria-label="历史 JD 正文">{{ historical.jd_text || '（空正文）' }}</pre>
          <div class="version-actions">
            <button class="btn btn-ghost btn-sm" :disabled="busy || historical.version === currentVersion" @click="restore"><Icon name="undo" :size="14" />恢复此版本</button>
            <span class="version-label">{{ historical.jd_text.length }} 字 · {{ historical.jd_text === text.trim() && historical.source_url === sourceUrl.trim() ? '与当前内容一致' : '与当前内容不同' }}</span>
          </div>
        </template>
        <p v-else class="version-label">{{ versions.length }} 个已保存版本</p>
      </div>
    </div>
    <p v-if="error" class="version-error" role="alert">{{ error }}</p>
    <p v-if="notice" class="version-notice" role="status">{{ notice }}</p>
  </section>
</template>

<style scoped>
.jd-versions { margin-top: 24px; padding: 22px 0; border-block: 1px solid var(--line); min-width: 0; }
.versions-head { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-bottom: 18px; }
.versions-head h2 { font-size: 18px; }
.versions-head .icon-btn { margin-left: auto; }
.versions-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 24px; }
.jd-draft, .jd-history { display: grid; align-content: start; gap: 10px; min-width: 0; }
.input-box { width: 100%; min-width: 0; }
textarea { resize: vertical; line-height: 1.7; }
.version-label { font-size: 11px; color: var(--ink-3); overflow-wrap: anywhere; }
.version-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.version-meta { display: grid; grid-template-columns: 64px minmax(0, 1fr); gap: 8px; font-size: 11px; color: var(--ink-3); }
.version-meta dd { margin: 0; overflow-wrap: anywhere; }
.hash { font-family: var(--f-mono); }
.historical-text { margin: 0; max-height: 340px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font: 13px/1.7 var(--f-body); color: var(--ink-2); }
.version-error, .version-notice { margin: 14px 0 0; font-size: 12px; overflow-wrap: anywhere; }
.version-error { color: var(--vermilion); }.version-notice { color: var(--pine); }
@media (max-width: 800px) { .versions-grid { grid-template-columns: minmax(0, 1fr); }.jd-history { border-top: 1px solid var(--line); padding-top: 18px; } }
</style>
