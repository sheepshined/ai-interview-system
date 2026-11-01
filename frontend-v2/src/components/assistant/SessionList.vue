<template>
  <div class="sl">
    <header class="sl-head">
      <span>会话历史</span>
      <button :disabled="busy" @click="create"><Icon name="plus" /> 新会话</button>
    </header>
    <ul>
      <li v-for="s in hist.sessions.value" :key="s.id">
        <button class="sl-title" :disabled="busy" :title="'打开会话 #' + s.id" @click="$emit('pick', s.id)">{{ s.title }}</button>
        <small>{{ s.updated_at }}</small>
        <span class="sl-ops">
          <button title="重命名" @click="rename(s)"><Icon name="pen" /></button>
          <button :disabled="busy" title="删除会话（消息与断点一并清除）" @click="remove(s)"><Icon name="trash" /></button>
        </span>
      </li>
      <li v-if="!hist.sessions.value.length" class="sl-empty">还没有会话。</li>
    </ul>
  </div>
</template>

<script setup>
import Icon from '../Icon.vue'

const props = defineProps({ hist: { type: Object, required: true }, busy: Boolean })
const emit = defineEmits(['pick', 'removed', 'error'])

async function create() {
  const session = await props.hist.newSession()
  if (session) emit('pick', session.id)
}

async function rename(session) {
  const title = window.prompt('新标题', session.title)
  if (title && title.trim()) await props.hist.rename(session.id, title.trim())
}

async function remove(session) {
  if (window.confirm(`删除会话「${session.title}」？消息与断点一并清除。`)) {
    const res = await props.hist.removeSession(session.id)
    if (res.success) emit('removed', session.id)
    else emit('error', res.message)
  }
}
</script>

<style scoped>
.sl { flex: 1; overflow-y: auto; padding: 12px; }
.sl-head { display: flex; justify-content: space-between; align-items: center; font-size: 12px; font-weight: 700; color: var(--ink); margin-bottom: 8px; }
.sl-head button {
  display: flex; align-items: center; gap: 4px; border: 1px solid var(--line);
  background: var(--sheet-2); color: var(--ink-2); border-radius: var(--r-1);
  padding: 4px 8px; font-size: 11px; cursor: pointer;
}
.sl-head button :deep(svg) { width: 12px; height: 12px; }
.sl ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.sl li { display: flex; align-items: center; gap: 6px; border: 1px solid var(--line-soft); border-radius: var(--r-1); padding: 7px 8px; background: var(--sheet-2); }
.sl-title {
  flex: 1; min-width: 0; border: none; background: transparent; text-align: left;
  font-size: 12px; color: var(--ink); cursor: pointer;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.sl small { font-size: 10px; color: var(--ink-3); flex-shrink: 0; max-width: 95px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sl-ops { display: flex; gap: 2px; }
.sl-ops button { border: none; background: transparent; color: var(--ink-3); cursor: pointer; display: flex; padding: 2px; }
.sl-ops button :deep(svg) { width: 12px; height: 12px; }
.sl-empty { border: none !important; background: transparent !important; color: var(--ink-3); font-size: 12px; }
</style>
