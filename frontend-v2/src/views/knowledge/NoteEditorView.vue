<script setup>
import { ref, computed, nextTick, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Icon from '../../components/Icon.vue'
import TopBar from '../../components/TopBar.vue'
import { toast } from '../../composables/useToast'
import { renderMarkdown } from '../../utils/markdown'
import {
  kbGetNote, kbCreateNote, kbUpdateNote, kbDeleteNote, kbCategories,
  kbSearch, kbTidy, kbAutoCategory, kbAutoLink, kbFileUrl, kbInterpretNote,
} from '../../api'

const route = useRoute()
const router = useRouter()
const noteId = computed(() => (route.params.id ? Number(route.params.id) : null))
const isNew = computed(() => !noteId.value)
const note = ref(null)
const title = ref('')
const content = ref('')
const category = ref('')
const tagsInput = ref('')
const backlinks = ref([])
const related = ref([])
const categories = ref([])
const loading = ref(!isNew.value)
const error = ref('')
const saving = ref(false)
const aiBusy = ref(false)
const aiAction = ref('')
const mode = ref('edit')
const fullscreen = ref(false)
const activeSide = ref('info')
const linkedNote = ref(null)
const linkedLoading = ref(false)
const linkedError = ref('')
const interpretation = ref('')
const interpretationLoading = ref(false)
const interpretationError = ref('')
const editorArea = ref(null)

let linkedRequest = 0
let savedSnapshot = ''
let editHistory = ['']
const historyIndex = ref(0)
let historyTimer = null

const typeLabel = computed(() =>
  ({ note: '手写笔记', file: '文件导入', url: '网址收藏' }[note.value?.note_type] || '手写笔记'))
const typeIcon = computed(() =>
  ({ note: 'pen', file: 'file', url: 'link' }[note.value?.note_type] || 'pen'))
const wordCount = computed(() => (content.value || '').replace(/\s+/g, '').length)
const fileUrl = computed(() => (note.value?.file_path ? kbFileUrl(note.value.file_path) : ''))
const snapshotValue = () => JSON.stringify([title.value, content.value, category.value, tagsInput.value])
const isDirty = computed(() => snapshotValue() !== savedSnapshot)

function buildPreview(md) {
  const html = renderMarkdown(md || '')
  return html.replace(/\[\[([^\[\]<>\x0A\x0D]{1,120})\]\]/g, (match, raw) => {
    const name = raw.trim()
    if (!name) return match
    return `<button type="button" class="wikilink" data-wiki="${encodeURIComponent(name)}">${name}</button>`
  })
}

const previewHtml = computed(() => buildPreview(content.value))
const linkedPreviewHtml = computed(() => buildPreview(linkedNote.value?.content || ''))
const interpretationHtml = computed(() => renderMarkdown(interpretation.value || ''))
const fmtDate = (iso) => (iso || '').slice(0, 10)
const fmtDateTime = (iso) => (iso || '').slice(0, 16).replace('T', ' ')

function resetHistory(value) {
  clearTimeout(historyTimer)
  editHistory = [value || '']
  historyIndex.value = 0
}

function rememberContent(immediate = false) {
  clearTimeout(historyTimer)
  const commit = () => {
    const value = content.value || ''
    if (editHistory[historyIndex.value] === value) return
    editHistory = editHistory.slice(0, historyIndex.value + 1)
    editHistory.push(value)
    if (editHistory.length > 100) editHistory.shift()
    historyIndex.value = editHistory.length - 1
  }
  if (immediate) commit()
  else historyTimer = setTimeout(commit, 250)
}

function restoreHistory(offset) {
  clearTimeout(historyTimer)
  const next = historyIndex.value + offset
  if (next < 0 || next >= editHistory.length) return
  historyIndex.value = next
  content.value = editHistory[next]
  nextTick(() => editorArea.value?.focus())
}

async function load(silent = false) {
  if (isNew.value) {
    loading.value = false
    savedSnapshot = snapshotValue()
    resetHistory(content.value)
    return
  }
  if (!silent) loading.value = true
  error.value = ''
  try {
    const result = await kbGetNote(noteId.value)
    if (!result.success) { error.value = result.message || '笔记不存在'; return }
    note.value = result.note
    title.value = result.note.title || ''
    content.value = result.note.content || ''
    category.value = result.note.category || ''
    tagsInput.value = (result.note.tags || []).join(', ')
    backlinks.value = result.backlinks || []
    savedSnapshot = snapshotValue()
    resetHistory(content.value)
  } finally {
    if (!silent) loading.value = false
  }
}

async function loadCategories() {
  const result = await kbCategories()
  if (result.success) categories.value = result.categories || []
}

async function loadRelated() {
  const q = (title.value || content.value || '').trim()
  if (!q) { related.value = []; return }
  const result = await kbSearch(q.slice(0, 200), 6)
  if (result.success) {
    related.value = (result.results || [])
      .filter((item) => item.note_id !== noteId.value)
      .slice(0, 4)
  }
}

async function save() {
  if (saving.value) return false
  const cleanTitle = title.value.trim()
  if (!cleanTitle) { toast('请填写笔记标题', 'warn'); return false }
  saving.value = true
  try {
    const tags = tagsInput.value.split(/[,，]/).map((item) => item.trim()).filter(Boolean)
    const result = isNew.value
      ? await kbCreateNote(cleanTitle, content.value, tags, category.value.trim())
      : await kbUpdateNote(noteId.value, cleanTitle, content.value, tags, category.value.trim())
    if (!result.success) { toast(result.message || '保存失败', 'warn'); return false }
    if (isNew.value) {
      savedSnapshot = snapshotValue()
      toast('已创建笔记')
      await router.replace(`/knowledge/note/${result.id}`)
    } else {
      note.value = { ...note.value, title: cleanTitle, content: content.value, category: category.value.trim(), tags, updated_at: new Date().toISOString() }
      savedSnapshot = snapshotValue()
      await Promise.all([loadRelated(), loadCategories()])
      toast('已保存 · 已同步向量索引')
    }
    return true
  } finally {
    saving.value = false
  }
}

async function ensureSaved() {
  if (!isDirty.value) return true
  return save()
}

async function remove() {
  if (isNew.value || !confirm(`确定删除「${title.value}」？此操作不可恢复。`)) return
  const result = await kbDeleteNote(noteId.value)
  if (result.success) { toast('已删除该笔记'); router.push('/knowledge') }
  else toast(result.message || '删除失败', 'warn')
}

async function aiTidy() {
  if (aiBusy.value || isNew.value || !confirm('AI 将重新整理当前笔记内容（覆盖编辑区），确定继续？')) return
  if (!await ensureSaved()) return
  aiBusy.value = true; aiAction.value = 'tidy'
  try {
    const result = await kbTidy(noteId.value)
    if (result.success) {
      content.value = result.content || ''
      rememberContent(true)
      toast('AI 整理排版完成，请记得保存', 'sparkle')
    } else toast(result.message || 'AI 整理失败', 'warn')
  } finally { aiBusy.value = false; aiAction.value = '' }
}

async function aiCategory() {
  if (aiBusy.value || isNew.value || !await ensureSaved()) return
  aiBusy.value = true; aiAction.value = 'category'
  try {
    const result = await kbAutoCategory(noteId.value)
    if (result.success) {
      if (result.category) category.value = result.category
      if (result.tags?.length && !tagsInput.value.trim()) tagsInput.value = result.tags.join(', ')
      toast(`已自动归类到「${result.category || '未分类'}」`, 'folder')
    } else toast(result.message || '分类建议失败', 'warn')
  } finally { aiBusy.value = false; aiAction.value = '' }
}

async function smartLink() {
  if (aiBusy.value || isNew.value || !await ensureSaved()) return
  aiBusy.value = true; aiAction.value = 'link'
  try {
    const result = await kbAutoLink(noteId.value)
    if (result.success && result.linked?.length) {
      await load(true)
      await loadRelated()
      toast(`已智能关联 ${result.linked.length} 篇：${result.linked.join('、')}`, 'link')
    } else if (result.success) toast(result.message || '暂无足够相关的笔记可关联', 'warn')
    else toast(result.message || '智能关联失败', 'warn')
  } finally { aiBusy.value = false; aiAction.value = '' }
}

async function openLinkedById(id, fallbackTitle = '') {
  if (!id || Number(id) === noteId.value) { activeSide.value = 'info'; return }
  const requestId = ++linkedRequest
  linkedLoading.value = true
  linkedError.value = ''
  activeSide.value = 'linked'
  try {
    const result = await kbGetNote(id)
    if (requestId !== linkedRequest) return
    if (!result.success) throw new Error(result.message || '笔记加载失败')
    linkedNote.value = result.note
  } catch (err) {
    if (requestId === linkedRequest) {
      linkedNote.value = fallbackTitle ? { title: fallbackTitle, content: '' } : null
      linkedError.value = err.message || '笔记加载失败'
    }
  } finally {
    if (requestId === linkedRequest) linkedLoading.value = false
  }
}

async function openWiki(name) {
  if (!name) return
  const requestId = ++linkedRequest
  linkedLoading.value = true
  linkedError.value = ''
  activeSide.value = 'linked'
  try {
    const result = await kbSearch(name, 5)
    if (requestId !== linkedRequest) return
    const list = (result.success && result.results) || []
    const hit = list.find((item) => item.title === name) || list[0]
    if (!hit) {
      linkedNote.value = { title: name, content: '' }
      linkedError.value = `未找到「${name}」`
      return
    }
    const detail = await kbGetNote(hit.note_id)
    if (requestId !== linkedRequest) return
    if (!detail.success) throw new Error(detail.message || '笔记加载失败')
    linkedNote.value = detail.note
  } catch (err) {
    if (requestId === linkedRequest) linkedError.value = err.message || '笔记加载失败'
  } finally {
    if (requestId === linkedRequest) linkedLoading.value = false
  }
}

function onPreviewClick(event) {
  const link = event.target.closest?.('.wikilink')
  if (!link) return
  event.preventDefault()
  openWiki(decodeURIComponent(link.dataset.wiki || ''))
}

function insertRelated(item) {
  const current = content.value || ''
  content.value = current + (current && !current.endsWith('\n') ? '\n\n' : '') + `- [[${item.title}]]`
  mode.value = 'edit'
  rememberContent(true)
  toast(`已插入 [[${item.title}]]`)
}

async function selectSide(tab) {
  activeSide.value = tab
  if (tab !== 'ai' || interpretation.value || interpretationLoading.value) return
  interpretationLoading.value = true
  interpretationError.value = ''
  try {
    const result = await kbInterpretNote(noteId.value, title.value, content.value)
    if (result.success) interpretation.value = result.interpretation || ''
    else interpretationError.value = result.message || 'AI 解读失败'
  } catch (err) {
    interpretationError.value = err.message || 'AI 解读失败'
  } finally { interpretationLoading.value = false }
}

function updateSelection(before, after = before, placeholder = '文本') {
  mode.value = 'edit'
  nextTick(() => {
    const area = editorArea.value
    if (!area) return
    const start = area.selectionStart
    const end = area.selectionEnd
    const selected = content.value.slice(start, end) || placeholder
    content.value = content.value.slice(0, start) + before + selected + after + content.value.slice(end)
    rememberContent(true)
    nextTick(() => { area.focus(); area.setSelectionRange(start + before.length, start + before.length + selected.length) })
  })
}

function prefixLines(prefix) {
  mode.value = 'edit'
  nextTick(() => {
    const area = editorArea.value
    if (!area) return
    const start = content.value.lastIndexOf('\n', Math.max(0, area.selectionStart - 1)) + 1
    const tail = content.value.indexOf('\n', area.selectionEnd)
    const end = tail < 0 ? content.value.length : tail
    const block = content.value.slice(start, end)
    const changed = block.split('\n').map((line, index) => `${typeof prefix === 'function' ? prefix(index) : prefix}${line}`).join('\n')
    content.value = content.value.slice(0, start) + changed + content.value.slice(end)
    rememberContent(true)
    nextTick(() => { area.focus(); area.setSelectionRange(start, start + changed.length) })
  })
}

function insertBlock(text) {
  mode.value = 'edit'
  nextTick(() => {
    const area = editorArea.value
    if (!area) return
    const start = area.selectionStart
    content.value = content.value.slice(0, start) + text + content.value.slice(area.selectionEnd)
    rememberContent(true)
    nextTick(() => { area.focus(); area.setSelectionRange(start + text.length, start + text.length) })
  })
}

const editorTools = [
  { icon: 'bold', title: '粗体', run: () => updateSelection('**', '**') },
  { icon: 'italic', title: '斜体', run: () => updateSelection('*', '*') },
  { icon: 'strike', title: '删除线', run: () => updateSelection('~~', '~~') },
  { icon: 'quote', title: '引用', run: () => prefixLines('> ') },
  { icon: 'list', title: '无序列表', run: () => prefixLines('- ') },
  { icon: 'orderedList', title: '有序列表', run: () => prefixLines((index) => `${index + 1}. `) },
  { icon: 'link', title: '链接', run: () => updateSelection('[', '](https://)', '链接文字') },
  { icon: 'code', title: '代码', run: () => updateSelection('`', '`', 'code') },
  { icon: 'table', title: '表格', run: () => insertBlock('\n| 列 1 | 列 2 |\n| --- | --- |\n| 内容 | 内容 |\n') },
]

function toggleFullscreen() {
  fullscreen.value = !fullscreen.value
  document.body.classList.toggle('note-fullscreen-open', fullscreen.value)
}

function onKeydown(event) {
  if (event.key === 'Escape' && fullscreen.value) toggleFullscreen()
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
    event.preventDefault()
    save()
  }
}

onMounted(async () => {
  if (isNew.value && route.query.title) title.value = String(route.query.title).slice(0, 120)
  await load()
  await Promise.all([loadCategories(), loadRelated()])
  window.addEventListener('keydown', onKeydown)
})

watch(() => route.params.id, async (newId, oldId) => {
  if (!newId || newId === oldId) return
  error.value = ''
  linkedNote.value = null
  activeSide.value = 'info'
  interpretation.value = ''
  await load(true)
  await loadRelated()
})

watch([title, content], () => {
  interpretation.value = ''
  interpretationError.value = ''
})

onBeforeUnmount(() => {
  clearTimeout(historyTimer)
  document.body.classList.remove('note-fullscreen-open')
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div class="note-page" :class="{ 'is-fullscreen': fullscreen }">
    <TopBar crumb="笔记编辑" folio="卷·05">
      <template #actions>
        <button class="icon-btn" :title="fullscreen ? '退出全屏' : '全屏阅读'" @click="toggleFullscreen"><Icon :name="fullscreen ? 'fullscreenExit' : 'fullscreen'" :size="15" /></button>
        <button v-if="!isNew" class="icon-btn" title="删除笔记" @click="remove"><Icon name="trash" :size="15" /></button>
        <button class="btn btn-sm" :disabled="saving || !title.trim()" @click="save"><Icon name="save" :size="15" />{{ saving ? '保存中…' : (isNew ? '创建' : '保存') }}</button>
      </template>
    </TopBar>

    <div class="page-body note-body">
      <div v-if="loading" class="editor-status">加载中…</div>
      <div v-else-if="error" class="editor-status error-text">{{ error }}</div>
      <div v-else class="editor-layout">
        <div class="editor" v-reveal>
          <div class="editor-head">
            <div class="type-row">
              <span class="badge line"><Icon :name="typeIcon" :size="13" />{{ typeLabel }}</span>
              <span class="mono">{{ isNew ? 'NEW NOTE · 尚未保存' : `NOTE № ${noteId} · 创建于 ${fmtDate(note?.created_at)}` }}</span>
              <span v-if="isDirty" class="draft-mark">未保存</span>
            </div>
            <input v-model="title" class="title-input" placeholder="笔记标题" />
            <div class="editor-meta">
              <span class="mini-field"><Icon name="folder" :size="14" />分类<input v-model="category" list="kb-cat-list" placeholder="未分类" /></span>
              <span class="mini-field"><Icon name="hash" :size="14" />标签<input v-model="tagsInput" placeholder="逗号分隔" /></span>
              <datalist id="kb-cat-list"><option v-for="item in categories" :key="item.category" :value="item.category" /></datalist>
            </div>
          </div>

          <div class="editor-toolbar">
            <div class="format-tools" aria-label="Markdown 编辑工具">
              <button v-for="tool in editorTools" :key="tool.title" class="format-btn" :title="tool.title" :aria-label="tool.title" @click="tool.run"><Icon :name="tool.icon" :size="15" /></button>
              <span class="tool-divider"></span>
              <button class="format-btn" title="撤销" aria-label="撤销" :disabled="historyIndex <= 0" @click="restoreHistory(-1)"><Icon name="undo" :size="15" /></button>
              <button class="format-btn" title="重做" aria-label="重做" :disabled="historyIndex >= editHistory.length - 1" @click="restoreHistory(1)"><Icon name="redo" :size="15" /></button>
            </div>
            <div class="ai-tools">
              <button class="tool-btn" :disabled="isNew || aiBusy" @click="aiTidy"><Icon name="sparkle" :size="14" />{{ aiAction === 'tidy' ? '处理中…' : '整理排版' }}</button>
              <button class="tool-btn" :disabled="isNew || aiBusy" @click="aiCategory"><Icon name="folder" :size="14" />{{ aiAction === 'category' ? '处理中…' : '自动分类' }}</button>
              <button class="tool-btn" :disabled="isNew || aiBusy" @click="smartLink"><Icon name="link" :size="14" />{{ aiAction === 'link' ? '处理中…' : '智能关联' }}</button>
            </div>
            <div class="seg"><button :class="{ 'is-on': mode === 'edit' }" @click="mode = 'edit'">编辑</button><button :class="{ 'is-on': mode === 'preview' }" @click="mode = 'preview'">预览</button></div>
          </div>

          <div class="paper-area">
            <textarea v-show="mode === 'edit'" ref="editorArea" v-model="content" spellcheck="false" placeholder="用 Markdown 记录知识，输入 [[标题]] 链接其他笔记…" @input="rememberContent()"></textarea>
            <div v-show="mode === 'preview'" class="markdown-view preview" @click="onPreviewClick" v-html="previewHtml"></div>
          </div>
        </div>

        <aside class="side-stack">
          <section class="panel side-primary" v-reveal="0.06">
            <div class="side-tabs" role="tablist" aria-label="笔记辅助信息">
              <button :class="{ 'is-on': activeSide === 'info' }" @click="selectSide('info')">原信息</button>
              <button :class="{ 'is-on': activeSide === 'ai' }" @click="selectSide('ai')">AI解读</button>
              <button v-if="linkedNote || linkedLoading || linkedError" :class="{ 'is-on': activeSide === 'linked' }" @click="selectSide('linked')">插入笔记</button>
            </div>
            <div v-if="activeSide === 'info'" class="panel-body">
              <div class="kv"><span class="k">类型</span><span class="v">{{ typeLabel }}</span></div>
              <div class="kv"><span class="k">创建</span><span class="v">{{ isNew ? '—' : fmtDate(note?.created_at) }}</span></div>
              <div class="kv"><span class="k">更新</span><span class="v">{{ isNew ? '—' : fmtDateTime(note?.updated_at) }}</span></div>
              <div class="kv"><span class="k">字数</span><span class="v num">{{ wordCount }}</span></div>
              <div class="kv"><span class="k">被引用</span><span class="v num">{{ backlinks.length }}</span></div>
            </div>
            <div v-else-if="activeSide === 'ai'" class="panel-body side-reading">
              <div v-if="interpretationLoading" class="panel-empty">正在解读当前笔记…</div>
              <div v-else-if="interpretationError" class="panel-empty error-text">{{ interpretationError }}<button class="retry-link" @click="interpretation = ''; selectSide('ai')">重试</button></div>
              <div v-else class="markdown-view compact" v-html="interpretationHtml"></div>
            </div>
            <div v-else class="panel-body side-reading">
              <div v-if="linkedLoading" class="panel-empty">正在读取插入笔记…</div>
              <div v-else-if="linkedError && !linkedNote?.content" class="panel-empty error-text">{{ linkedError }}</div>
              <template v-else-if="linkedNote">
                <div class="linked-head"><span class="linked-title">{{ linkedNote.title }}</span><button v-if="linkedNote.id" class="open-note" title="在编辑页打开" @click="router.push(`/knowledge/note/${linkedNote.id}`)"><Icon name="external" :size="13" /></button></div>
                <div class="markdown-view compact" @click="onPreviewClick" v-html="linkedPreviewHtml"></div>
              </template>
            </div>
          </section>

          <section v-if="fileUrl" class="panel" v-reveal="0.1">
            <div class="panel-head">原始文件 <Icon name="file" :size="14" /></div>
            <div class="panel-body"><a class="file-link" :href="fileUrl" target="_blank" :title="note?.file_name || '原始文件'"><Icon name="file" :size="14" /><span class="fn">{{ note?.file_name || '原始文件' }}</span><span class="fo">打开 <Icon name="external" :size="12" /></span></a></div>
          </section>
          <section class="panel" v-reveal="0.12">
            <div class="panel-head">反向链接 · {{ backlinks.length }} <Icon name="link" :size="14" /></div>
            <div class="panel-body">
              <div v-if="!backlinks.length" class="panel-empty">还没有笔记链接到这里</div>
              <button v-for="item in backlinks" :key="item.id" class="backlink" @click="openLinkedById(item.id, item.title)"><span class="t"><Icon name="link" :size="14" />{{ item.title }}</span><span class="ctx">更新于 {{ fmtDateTime(item.updated_at) }}</span></button>
            </div>
          </section>
          <section class="panel" v-reveal="0.18">
            <div class="panel-head">相关笔记 · 语义 <Icon name="network" :size="14" /></div>
            <div class="panel-body">
              <div v-if="!related.length" class="panel-empty">暂无相关笔记</div>
              <div v-for="item in related" :key="item.note_id" class="related"><button class="t" @click="openLinkedById(item.note_id, item.title)">{{ item.title }}</button><span class="sim">{{ (item.score * 100).toFixed(0) }}%</span><button class="insert" @click="insertRelated(item)">插入</button></div>
            </div>
          </section>
        </aside>
      </div>
    </div>
  </div>
</template>

<style scoped>
.note-page, .note-body, .editor, .side-stack, .panel, .paper-area { min-width: 0; }
.note-body { max-width: 100%; }
.editor-layout { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(270px, 1fr); gap: 26px; align-items: start; max-width: 100%; }
.editor { border: 1px solid var(--line-strong); background: var(--sheet); overflow: hidden; }
.editor-head { padding: 24px 30px 0; }
.type-row { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
.draft-mark { font-family: var(--f-mono); font-size: 10px; color: var(--vermilion); }
.title-input { width: 100%; min-width: 0; border: 0; background: none; outline: none; font-family: var(--f-display); font-weight: 900; font-size: 30px; line-height: 1.35; color: var(--ink); }
.title-input::placeholder { color: var(--ink-4); }
.editor-meta { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin-top: 16px; }
.mini-field { display: flex; align-items: center; gap: 8px; min-width: 0; font-size: 13px; color: var(--ink-3); }
.mini-field input { min-width: 80px; max-width: 180px; border: 0; border-bottom: 1px dashed var(--line-strong); background: none; outline: none; font-size: 13px; padding: 3px 2px; color: var(--ink); }
.mini-field input:focus { border-bottom-color: var(--vermilion); }
.editor-toolbar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 12px 30px; margin-top: 20px; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); background: var(--sheet-2); }
.format-tools, .ai-tools { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.format-btn { width: 31px; height: 31px; display: inline-flex; align-items: center; justify-content: center; border: 1px solid transparent; color: var(--ink-2); }
.format-btn:hover { border-color: var(--line-strong); background: var(--sheet); color: var(--ink); }
.format-btn:disabled { opacity: .3; pointer-events: none; }
.tool-divider { width: 1px; height: 20px; background: var(--line); margin: 0 3px; }
.tool-btn { display: inline-flex; align-items: center; gap: 6px; padding: 7px 9px; font-size: 12px; border: 1px solid var(--line); background: var(--sheet); color: var(--ink-2); }
.tool-btn:hover { border-color: var(--ink); color: var(--ink); }
.tool-btn[disabled] { opacity: .38; pointer-events: none; }
.seg { display: flex; margin-left: auto; border: 1px solid var(--line); flex-shrink: 0; }
.seg button { padding: 7px 14px; font-size: 12.5px; color: var(--ink-3); }
.seg button.is-on { background: var(--ink); color: var(--paper); }
.paper-area textarea { display: block; width: 100%; min-width: 0; min-height: 520px; border: 0; outline: none; resize: vertical; padding: 26px 30px 34px; background-color: transparent; font-size: 14.5px; line-height: 2.05; color: var(--ink); overflow-wrap: anywhere; background-image: repeating-linear-gradient(transparent 0, transparent 39px, var(--line-soft) 39px, var(--line-soft) 40px); background-position: 0 26px; }
.paper-area textarea::placeholder { color: var(--ink-4); }
.preview { min-height: 520px; padding: 26px 30px 34px; }
.markdown-view { min-width: 0; max-width: 100%; overflow-wrap: anywhere; word-break: break-word; }
.markdown-view :deep(h1), .markdown-view :deep(h2) { font-size: 20px; margin: 26px 0 10px; }
.markdown-view :deep(h1:first-child), .markdown-view :deep(h2:first-child) { margin-top: 0; }
.markdown-view :deep(h3), .markdown-view :deep(h4) { font-size: 16px; margin: 20px 0 8px; color: var(--ink-2); }
.markdown-view :deep(p) { max-width: 100%; font-size: 14.5px; line-height: 2.05; color: var(--ink-2); margin-bottom: 12px; }
.markdown-view :deep(li) { font-size: 14.5px; line-height: 2; color: var(--ink-2); margin-left: 20px; }
.markdown-view :deep(ol) { list-style: decimal; }
.markdown-view :deep(ul) { list-style: disc; }
.markdown-view :deep(blockquote) { margin: 16px 0; padding: 12px 18px; border-left: 2px solid var(--verm-line); background: var(--verm-wash); font-size: 13.5px; color: var(--ink-2); font-style: italic; }
.markdown-view :deep(code) { font-family: var(--f-mono); font-size: 12.5px; background: var(--sheet-2); border: 1px solid var(--line); padding: 1px 6px; }
.markdown-view :deep(.md-pre) { max-width: 100%; overflow-x: auto; padding: 14px; background: var(--sheet-2); border: 1px solid var(--line); }
.markdown-view :deep(.md-code-block) { display: block; width: max-content; min-width: 100%; border: 0; padding: 0; white-space: pre; }
.markdown-view :deep(.md-table-wrap) { max-width: 100%; overflow-x: auto; margin: 14px 0; }
.markdown-view :deep(.md-table) { width: max-content; min-width: 100%; border-collapse: collapse; }
.markdown-view :deep(.md-table th), .markdown-view :deep(.md-table td) { padding: 7px 10px; border: 1px solid var(--line); text-align: left; }
.markdown-view :deep(.wikilink) { display: inline; padding: 0; color: var(--indigo-ink); font-weight: 600; border: 0; border-bottom: 1px dashed rgba(35,64,92,.5); background: none; cursor: pointer; }
.markdown-view :deep(.wikilink:hover) { color: var(--vermilion); border-color: var(--vermilion); }
.markdown-view.compact :deep(p), .markdown-view.compact :deep(li) { font-size: 13px; line-height: 1.8; }
.markdown-view.compact :deep(h1), .markdown-view.compact :deep(h2) { font-size: 17px; }
.markdown-view.compact :deep(h3), .markdown-view.compact :deep(h4) { font-size: 14px; }
.side-stack { display: flex; flex-direction: column; gap: 20px; }
.panel { border: 1px solid var(--line); background: var(--sheet); overflow: hidden; }
.side-primary { min-height: 220px; }
.side-tabs { display: flex; border-bottom: 1px solid var(--line); background: var(--sheet-2); }
.side-tabs button { flex: 1; min-width: 0; padding: 12px 8px; border-right: 1px solid var(--line); font-size: 12px; color: var(--ink-3); white-space: nowrap; }
.side-tabs button:last-child { border-right: 0; }
.side-tabs button.is-on { background: var(--ink); color: var(--paper); }
.panel-head { padding: 14px 18px; border-bottom: 1px solid var(--line); display: flex; align-items: center; justify-content: space-between; gap: 10px; font-family: var(--f-mono); font-size: 10.5px; letter-spacing: .18em; text-transform: uppercase; color: var(--ink-3); }
.panel-body { min-width: 0; padding: 14px 18px; }
.side-reading { max-height: min(64vh, 620px); overflow: auto; }
.kv { display: flex; justify-content: space-between; gap: 12px; padding: 7px 0; font-size: 13px; border-bottom: 1px dashed var(--line); }
.kv:last-child { border-bottom: 0; }
.kv .k { color: var(--ink-4); font-family: var(--f-mono); font-size: 10.5px; letter-spacing: .12em; text-transform: uppercase; padding-top: 2px; }
.kv .v { min-width: 0; color: var(--ink-2); text-align: right; overflow-wrap: anywhere; }
.kv .v.num { font-family: var(--f-mono); font-weight: 700; color: var(--ink); }
.linked-head { display: flex; align-items: flex-start; gap: 10px; padding-bottom: 12px; margin-bottom: 12px; border-bottom: 1px solid var(--line); }
.linked-title { min-width: 0; flex: 1; font-family: var(--f-display); font-size: 17px; font-weight: 900; overflow-wrap: anywhere; }
.open-note { width: 28px; height: 28px; display: inline-flex; align-items: center; justify-content: center; border: 1px solid var(--line); flex-shrink: 0; }
.retry-link { display: block; margin-top: 8px; color: var(--vermilion); text-decoration: underline; }
.backlink { display: block; width: 100%; padding: 11px 0; border-bottom: 1px dashed var(--line); text-align: left; }
.backlink:last-child { border-bottom: 0; }
.backlink .t { min-width: 0; font-size: 13.5px; font-weight: 600; color: var(--ink); display: flex; align-items: center; gap: 7px; overflow-wrap: anywhere; }
.backlink .ctx { font-size: 12px; color: var(--ink-3); line-height: 1.8; margin-top: 5px; display: block; }
.related { display: flex; min-width: 0; align-items: center; gap: 10px; padding: 11px 0; border-bottom: 1px dashed var(--line); }
.related:last-child { border-bottom: 0; }
.related .t { flex: 1; min-width: 0; font-size: 13.5px; color: var(--ink-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: left; }
.related .sim { font-family: var(--f-mono); font-size: 11px; font-weight: 700; color: var(--pine); flex-shrink: 0; }
.related .insert { font-family: var(--f-mono); font-size: 10px; color: var(--ink-3); border: 1px solid var(--line); padding: 3px 8px; flex-shrink: 0; }
.related .insert:hover { color: var(--vermilion); border-color: var(--verm-line); }
.file-link { display: flex; min-width: 0; align-items: center; gap: 10px; padding: 10px 12px; border: 1px solid var(--line); background: var(--sheet-2); }
.file-link .fn { flex: 1; min-width: 0; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-link .fo { display: inline-flex; align-items: center; gap: 4px; font-family: var(--f-mono); font-size: 10.5px; color: var(--ink-3); flex-shrink: 0; }
.panel-empty { font-size: 13px; color: var(--ink-4); }
.editor-status { text-align: center; color: var(--ink-3); padding: 60px 0; font-size: 14px; }
.error-text { color: var(--vermilion); }
.note-page.is-fullscreen { position: fixed; inset: 0; z-index: 130; overflow: auto; background: var(--paper); }
.note-page.is-fullscreen .topbar { position: sticky; }
.note-page.is-fullscreen .note-body { padding-top: 24px; }
:global(body.note-fullscreen-open) { overflow: hidden; }
@media (max-width: 1180px) { .editor-layout { grid-template-columns: minmax(0, 1fr); } .side-stack { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: start; } .side-primary { grid-column: 1 / -1; } }
@media (max-width: 760px) { .note-body { padding-inline: 14px; } .side-stack { display: flex; width: 100%; align-items: stretch; } .side-stack > .panel { width: 100%; } .editor-head { padding: 20px 18px 0; } .editor-toolbar { padding: 12px 18px; } .paper-area textarea, .preview { min-height: 58vh; padding: 20px 18px 28px; } .title-input { font-size: 25px; } .type-row .mono { display: none; } .mini-field { width: 100%; } .mini-field input { max-width: none; flex: 1; } .ai-tools { order: 3; width: 100%; } .seg { margin-left: auto; } }
@media (max-width: 430px) { .format-tools { width: 100%; } .seg { width: 100%; margin-left: 0; } .seg button { flex: 1; } .tool-btn { flex: 1; justify-content: center; } .side-tabs button { padding-inline: 5px; font-size: 11.5px; } }
</style>
