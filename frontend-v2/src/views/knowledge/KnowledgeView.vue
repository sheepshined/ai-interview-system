<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import Icon from '../../components/Icon.vue'
import TopBar from '../../components/TopBar.vue'
import { toast } from '../../composables/useToast'
import {
  kbListNotes, kbCategories, kbUploadFiles, kbCreateUrlNote, kbRebuild,
} from '../../api'

const router = useRouter()

const notes = ref([])
const allTags = ref([])
const categories = ref([])
const allCount = ref(0)
const activeCategory = ref('')
const activeTag = ref('')
const search = ref('')
const loading = ref(true)
const error = ref('')
const tagsExpanded = ref(false)
const rebuilding = ref(false)

const visibleTags = computed(() =>
  tagsExpanded.value ? allTags.value : allTags.value.slice(0, 8)
)
const totalCount = computed(() => allCount.value)
const totalLinks = computed(() =>
  notes.value.reduce((sum, n) => sum + (n.link_count || 0), 0)
)

const fileInput = ref(null)
const uploading = ref(false)
const uploadResults = ref(null)
const uploadCount = ref(0)

const urlDialog = ref(false)
const urlSaving = ref(false)
const urlForm = ref({ url: '', title: '', description: '', category: '' })

let searchTimer = null

async function load() {
  loading.value = true
  error.value = ''
  try {
    const result = await kbListNotes(search.value, activeTag.value, activeCategory.value)
    if (!result.success) {
      error.value = result.message || '加载失败'
      notes.value = []
      return
    }
    notes.value = result.notes || []
    if (!search.value && !activeTag.value && !activeCategory.value) {
      allCount.value = notes.value.length
      const seen = new Set()
      const tags = []
      for (const n of notes.value) {
        for (const t of n.tags || []) {
          if (!seen.has(t)) { seen.add(t); tags.push(t) }
        }
      }
      allTags.value = tags
    }
  } finally {
    loading.value = false
  }
}

async function loadCategories() {
  const result = await kbCategories()
  if (result.success) categories.value = result.categories || []
}

function onSearchInput() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(load, 300)
}

function selectTag(t) {
  activeTag.value = activeTag.value === t ? '' : t
  load()
}

function selectCategory(c) {
  activeCategory.value = activeCategory.value === c && c !== '' ? '' : c
  load()
}

function openNote(id) {
  router.push(`/knowledge/note/${id}`)
}

// ---- 文件上传 ----
function pickFiles() { fileInput.value?.click() }

async function onFilesPicked(e) {
  const files = [...(e.target.files || [])]
  e.target.value = ''   // 允许重复选同一文件
  if (!files.length || uploading.value) return
  if (files.length > 10) { toast('单次最多上传 10 个文件', 'warn'); return }
  uploading.value = true
  uploadResults.value = null
  uploadCount.value = files.length
  try {
    const result = await kbUploadFiles(files)
    if (result.success) {
      uploadResults.value = result.results || []
      await Promise.all([load(), loadCategories()])
      toast(`已处理 ${files.length} 个文件`, 'checkCircle')
    } else {
      toast(result.message || '上传失败', 'warn')
    }
  } finally {
    uploading.value = false
  }
}

function statusLabel(s) {
  return { created: '成功', skipped: '跳过', failed: '失败' }[s] || s
}
function statusClass(s) {
  return { created: 'ok', skipped: 'skip', failed: 'fail' }[s] || ''
}
function uploadMeta(r) {
  if (r.pages) return `${r.pages} 页 · ${r.extract_mode || ''}${r.llm_used ? ' · AI 整理' : ''}`
  return r.message || ''
}

// ---- 网址收藏 ----
async function saveUrl() {
  if (urlSaving.value) return
  const url = urlForm.value.url.trim()
  const description = urlForm.value.description.trim()
  if (!url || !description) { toast('请填写网址与描述', 'warn'); return }
  if (!/^https?:\/\//i.test(url)) { toast('网址必须以 http(s):// 开头', 'warn'); return }
  urlSaving.value = true
  try {
    const result = await kbCreateUrlNote(
      url, urlForm.value.title.trim(), description, urlForm.value.category.trim(),
    )
    if (!result.success) {
      toast(result.message || '保存失败', 'warn')
      return
    }
    urlDialog.value = false
    urlForm.value = { url: '', title: '', description: '', category: '' }
    await Promise.all([load(), loadCategories()])
    toast('网址已收藏')
  } finally {
    urlSaving.value = false
  }
}

// ---- 重建索引 ----
async function rebuild() {
  if (rebuilding.value) return
  rebuilding.value = true
  try {
    const result = await kbRebuild()
    if (result.success) {
      toast(`已重建索引：${result.notes ?? 0} 篇笔记 · ${result.sem_links ?? 0} 条语义关联`, 'refresh')
    } else {
      toast(result.message || '重建失败', 'warn')
    }
  } finally {
    rebuilding.value = false
  }
}

function typeIconOf(t) { return { note: 'pen', file: 'file', url: 'link' }[t] || 'pen' }
function typeLabel(t) { return { note: '手写笔记', file: '文件导入', url: '网址收藏' }[t] || t }
function formatDate(iso) { return iso ? String(iso).slice(5, 10) : '' }

onMounted(() => { load(); loadCategories() })
</script>

<template>
  <div>
    <TopBar crumb="我的笔记" folio="卷·05">
      <template #actions>
        <button class="tlink" :disabled="rebuilding" @click="rebuild">
          <Icon name="refresh" :size="15" />{{ rebuilding ? '重建中…' : '重建索引' }}
        </button>
      </template>
    </TopBar>

    <div class="page-body">
      <div class="page-head" v-reveal style="display:flex; align-items:flex-end; justify-content:space-between; gap:20px; flex-wrap:wrap">
        <div>
          <span class="sec-index">SECOND BRAIN</span>
          <h1 class="page-title" style="margin-top:14px">我的笔记</h1>
          <p class="page-sub">上传文件 / 收藏网址 / 手写笔记，用 [[双链语法]] 把知识连成网。</p>
        </div>
        <div style="display:flex; gap:10px; flex-wrap:wrap">
          <button class="btn btn-ghost btn-sm" :disabled="uploading" @click="pickFiles">
            <Icon name="upload" :size="15" />{{ uploading ? `导入中 (${uploadCount})…` : '导入文件' }}
          </button>
          <button class="btn btn-ghost btn-sm" @click="urlDialog = true">
            <Icon name="link" :size="15" />添加网址
          </button>
          <router-link class="btn btn-sm" to="/knowledge/new">
            <Icon name="plus" :size="16" />新建笔记
          </router-link>
        </div>
        <input ref="fileInput" type="file" multiple hidden
               accept=".md,.markdown,.txt,.pptx,.docx,.pdf" @change="onFilesPicked" />
      </div>

      <!-- 工具条 -->
      <div class="toolbar" v-reveal="0.06">
        <label class="search-box">
          <Icon name="search" :size="16" />
          <input v-model="search" placeholder="搜索标题或内容…" @input="onSearchInput" />
        </label>
        <div class="chips">
          <button class="tag" :class="{ 'is-on': !activeCategory }" @click="selectCategory('')">
            <Icon name="folder" :size="13" />全部 ({{ totalCount }})
          </button>
          <button v-for="c in categories" :key="'c-' + c.category" class="tag"
                  :class="{ 'is-on': activeCategory === c.category }"
                  @click="selectCategory(c.category)">
            <Icon name="folder" :size="13" />{{ c.category }} ({{ c.count }})
          </button>
        </div>
        <div v-if="visibleTags.length" class="chips">
          <button v-for="t in visibleTags" :key="t" class="tag"
                  :class="{ 'is-on': activeTag === t }" @click="selectTag(t)">{{ t }}</button>
          <button v-if="allTags.length > 8" class="tag" @click="tagsExpanded = !tagsExpanded">
            <Icon name="chevronDown" :size="13" />{{ tagsExpanded ? '收起' : `+${allTags.length - 8}` }}
          </button>
        </div>
      </div>

      <!-- 导入结果 -->
      <div v-if="uploadResults" class="uploads">
        <div class="uploads-head">
          <span class="t">Import Result · {{ uploadResults.length }} 个文件</span>
          <button class="icon-btn" style="width:28px;height:28px" @click="uploadResults = null">
            <Icon name="x" :size="14" />
          </button>
        </div>
        <div v-for="(r, i) in uploadResults" :key="i" class="uploads-row">
          <span class="st" :class="statusClass(r.status)">{{ statusLabel(r.status) }}</span>
          <span class="tt">{{ r.title || r.file }}</span>
          <span v-if="uploadMeta(r)" class="meta">{{ uploadMeta(r) }}</span>
        </div>
      </div>

      <!-- 三态 -->
      <div v-if="loading" class="kb-empty">加载中…</div>
      <div v-else-if="error" class="kb-empty" style="color:var(--vermilion)">{{ error }}</div>
      <div v-else-if="!notes.length" class="kb-empty">
        还没有笔记。导入文件、收藏网址，或在面试报告页把薄弱点一键入库。
      </div>

      <!-- 笔记网格 -->
      <template v-else>
        <div class="notes-grid" data-stagger>
          <article v-for="(note, idx) in notes" :key="note.id"
                   class="note-card sheet sheet-hover" :class="{ tall: idx === 0 }"
                   v-reveal @click="openNote(note.id)">
            <div class="head">
              <span class="type-glyph" :class="note.note_type" :title="typeLabel(note.note_type)">
                <Icon :name="typeIconOf(note.note_type)" :size="14" />
              </span>
              <span class="title">{{ note.title }}</span>
              <span v-if="note.source === 'interview_report'" class="badge verm" style="font-size:9.5px">面试</span>
              <a v-if="note.note_type === 'url' && note.source_url" class="src"
                 :href="note.source_url" target="_blank" rel="noopener" title="打开网址"
                 @click.stop><Icon name="external" :size="15" /></a>
            </div>
            <p class="excerpt">{{ note.content || '（空笔记）' }}</p>
            <div class="meta">
              <span v-if="note.category" class="tag small" style="cursor:default">{{ note.category }}</span>
              <span v-for="t in (note.tags || []).slice(0, 3)" :key="t" class="tag small" style="cursor:default">{{ t }}</span>
              <span class="links"><Icon name="link" :size="12" />{{ note.link_count }}</span>
              <span class="date">{{ formatDate(note.updated_at) }}</span>
            </div>
          </article>
        </div>

        <div class="grid-foot">
          <span>共 {{ notes.length }} 篇 · {{ totalLinks }} 条双链</span>
          <span>父文档检索 · 子块索引 / 父块返回</span>
        </div>
      </template>
    </div>

    <!-- 添加网址弹窗 -->
    <div v-if="urlDialog" class="mask is-open" @click.self="urlDialog = false">
      <div class="dialog">
        <div class="dialog-head">
          <span class="dialog-title">添加网址收藏</span>
          <button class="icon-btn" style="width:30px;height:30px" @click="urlDialog = false">
            <Icon name="x" :size="15" />
          </button>
        </div>
        <div class="dialog-body">
          <div class="dlg-field">
            <label>网址 *</label>
            <input v-model="urlForm.url" class="input-box" placeholder="https://…" />
          </div>
          <div class="dlg-field">
            <label>标题（留空则用网址）</label>
            <input v-model="urlForm.title" class="input-box" placeholder="如：BGE 模型卡" />
          </div>
          <div class="dlg-field">
            <label>描述 * · 检索匹配的主体，请认真填写</label>
            <textarea v-model="urlForm.description" class="input-box" rows="3"
                      placeholder="这个网页讲了什么？为什么收藏它？" style="resize:vertical; line-height:1.8"></textarea>
          </div>
          <div class="dlg-field" style="margin-bottom:0">
            <label>分类（可选）</label>
            <input v-model="urlForm.category" class="input-box" placeholder="如：大模型" />
          </div>
        </div>
        <div class="dialog-foot">
          <button class="btn btn-ghost btn-sm" @click="urlDialog = false">取消</button>
          <button class="btn btn-sm"
                  :disabled="!urlForm.url.trim() || !urlForm.description.trim() || urlSaving"
                  @click="saveUrl">{{ urlSaving ? '保存中…' : '保存' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
  /* ── 工具条 ── */
  .toolbar {
    display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
    padding: 16px 0 18px; margin-bottom: 8px;
    border-bottom: 1px solid var(--line-strong);
  }
  .search-box {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 14px; min-width: 260px; flex: 1; max-width: 340px;
    border: 1px solid var(--line); background: var(--sheet);
    transition: border-color var(--dur-1) ease;
  }
  .search-box:focus-within { border-color: var(--ink); }
  .search-box input { flex: 1; border: 0; background: none; outline: none; font-size: 14px; }
  .search-box input::placeholder { color: var(--ink-4); }
  .search-box .ic { color: var(--ink-4); }
  .chips { display: flex; gap: 8px; flex-wrap: wrap; }

  /* 上传结果 */
  .uploads { border: 1px solid var(--line); background: var(--sheet); margin: 20px 0 8px; }
  .uploads-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 18px; border-bottom: 1px solid var(--line); }
  .uploads-head .t { font-family: var(--f-mono); font-size: 10.5px; letter-spacing: 0.18em; text-transform: uppercase; color: var(--ink-3); }
  .uploads-row { display: flex; align-items: center; gap: 12px; padding: 11px 18px; border-bottom: 1px solid var(--line); font-size: 13.5px; }
  .uploads-row:last-child { border-bottom: 0; }
  .uploads-row .st { font-family: var(--f-mono); font-size: 10.5px; font-weight: 700; letter-spacing: 0.12em; }
  .uploads-row .st.ok { color: var(--pine); }
  .uploads-row .st.skip { color: var(--ochre); }
  .uploads-row .st.fail { color: var(--vermilion); }
  .uploads-row .tt { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .uploads-row .meta { font-family: var(--f-mono); font-size: 10.5px; color: var(--ink-4); }

  /* ── 笔记网格 ── */
  .notes-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(292px, 1fr)); gap: 20px; margin-top: 26px; }
  .note-card { padding: 22px 22px 18px; display: flex; flex-direction: column; gap: 12px; cursor: pointer; }
  .note-card .head { display: flex; align-items: center; gap: 10px; }
  .type-glyph {
    width: 26px; height: 26px; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    border: 1px solid var(--line-strong);
  }
  .type-glyph.note { color: var(--indigo-ink); border-color: rgba(35,64,92,.35); background: var(--indigo-wash); }
  .type-glyph.file { color: var(--pine); border-color: rgba(46,107,80,.32); background: var(--pine-wash); }
  .type-glyph.url { color: var(--ochre); border-color: rgba(169,116,28,.32); background: var(--ochre-wash); }
  .note-card .title { font-family: var(--f-display); font-weight: 900; font-size: 16px; line-height: 1.45; flex: 1; min-width: 0; }
  .note-card .excerpt {
    font-size: 13px; color: var(--ink-3); line-height: 1.85;
    display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
    min-height: 72px;
  }
  .note-card .meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding-top: 12px; border-top: 1px solid var(--line); }
  .note-card .meta .links { display: inline-flex; align-items: center; gap: 5px; font-family: var(--f-mono); font-size: 10.5px; color: var(--ink-4); }
  .note-card .meta .date { margin-left: auto; font-family: var(--f-mono); font-size: 10.5px; color: var(--ink-4); }
  .note-card .src { color: var(--ink-4); flex-shrink: 0; transition: color var(--dur-1) ease; }
  .note-card .src:hover { color: var(--ochre); }

  /* 首批卡片：让网格有节奏 */
  .note-card.tall .excerpt { -webkit-line-clamp: 5; min-height: 118px; }

  .grid-foot {
    margin-top: 30px; padding-top: 16px; border-top: 1px solid var(--line);
    display: flex; justify-content: space-between; gap: 16px; flex-wrap: wrap;
    font-family: var(--f-mono); font-size: 10.5px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--ink-4);
  }

  /* URL 弹窗内表单 */
  .dlg-field { margin-bottom: 16px; }
  .dlg-field label { display: block; font-family: var(--f-mono); font-size: 10.5px; letter-spacing: 0.16em; text-transform: uppercase; color: var(--ink-3); margin-bottom: 7px; }

  /* 三态 */
  .kb-empty { text-align: center; color: var(--ink-3); padding: 72px 0; font-size: 14px; }
</style>