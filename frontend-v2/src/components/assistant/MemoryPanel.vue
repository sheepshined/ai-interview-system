<template>
  <div class="mp">
    <header class="mp-head">
      <span>长期记忆 · {{ hist.memories.value.length }}</span>
      <button class="mp-clear" @click="clearAll">清空</button>
    </header>
    <p class="mp-note">助手自主写入；删除立即生效，之后不再注入。</p>
    <ul>
      <li v-for="m in hist.memories.value" :key="m.id">
        <span class="mp-kind">{{ kindLabel[m.kind] || m.kind }}</span>
        <div class="mp-body">
          <p>{{ m.text }}</p>
          <small>{{ m.ts }}<template v-if="m.source_ref"> · 出处 {{ m.source_ref }}</template> · 召回 {{ m.recall_count }} 次</small>
        </div>
        <button title="删除这条记忆" @click="hist.removeMemory(m.id)"><Icon name="trash" /></button>
      </li>
      <li v-if="!hist.memories.value.length" class="mp-empty">还没有记忆。</li>
    </ul>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import Icon from '../Icon.vue'

const props = defineProps({ hist: { type: Object, required: true } })
const kindLabel = { fact: '事实', weakness_pattern: '弱项', preference: '偏好', project: '项目' }

onMounted(() => props.hist.loadMemories())

async function clearAll() {
  if (window.confirm('清空全部长期记忆？不可恢复。')) await props.hist.clearMemories()
}
</script>

<style scoped>
.mp { flex: 1; overflow-y: auto; padding: 12px; }
.mp-head { display: flex; justify-content: space-between; align-items: center; font-size: 12px; font-weight: 700; color: var(--ink); }
.mp-clear { border: none; background: transparent; color: var(--vermilion-deep); font-size: 11px; cursor: pointer; }
.mp-note { font-size: 11px; color: var(--ink-3); margin: 4px 0 10px; }
.mp ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.mp li { display: flex; gap: 8px; align-items: flex-start; border: 1px solid var(--line-soft); border-radius: var(--r-1); padding: 8px; background: var(--sheet-2); }
.mp-kind { font-size: 10px; padding: 2px 6px; border-radius: var(--r-1); background: var(--indigo-wash); color: var(--indigo-ink); flex-shrink: 0; }
.mp-body { flex: 1; min-width: 0; }
.mp-body p { margin: 0 0 3px; font-size: 12px; color: var(--ink); line-height: 1.65; }
.mp-body small { font-size: 10px; color: var(--ink-3); }
.mp li button { border: none; background: transparent; color: var(--ink-3); cursor: pointer; display: flex; padding: 2px; }
.mp li button :deep(svg) { width: 13px; height: 13px; }
.mp-empty { border: none !important; background: transparent !important; color: var(--ink-3); font-size: 12px; }
</style>
