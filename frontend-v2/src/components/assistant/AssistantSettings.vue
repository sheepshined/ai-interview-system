<template>
  <div class="st">
    <h4>工具确认档位</h4>
    <label v-for="o in levels" :key="o.value" class="st-row">
      <input type="radio" :value="o.value" v-model="level" @change="save" />
      <span><b>{{ o.label }}</b><br /><small>{{ o.desc }}</small></span>
    </label>

    <h4>长期记忆</h4>
    <label class="st-row">
      <input type="checkbox" v-model="memoryEnabled" @change="save" />
      <span><b>启用记忆注入与写入</b><br /><small>关闭后助手不再读取或写入长期记忆</small></span>
    </label>
    <p class="st-note">写入的记忆随时可在「记忆」页查看与删除。</p>
    <RouterLink class="st-more" to="/settings">改密码 / 用户管理 / 题库管理 → 完整设置页</RouterLink>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { RouterLink } from 'vue-router'

const props = defineProps({ hist: { type: Object, required: true } })
const level = ref('read_auto')
const memoryEnabled = ref(true)
const levels = [
  { value: 'all_confirm', label: '全部确认', desc: '每次工具调用都先问我' },
  { value: 'read_auto', label: '只读自动（默认）', desc: '读操作自动执行；写与执行要确认' },
  { value: 'exec_only', label: '仅执行确认', desc: '只有起面试这类执行动作要确认' },
]

onMounted(async () => {
  await props.hist.loadSettings()
  level.value = props.hist.settings.value.auto_accept_level
  memoryEnabled.value = props.hist.settings.value.memory_enabled
})

async function save() {
  await props.hist.saveSettings({
    auto_accept_level: level.value,
    memory_enabled: memoryEnabled.value,
  })
}
</script>

<style scoped>
.st { flex: 1; overflow-y: auto; padding: 14px; }
.st h4 { font-size: 12px; color: var(--ink); margin: 0 0 8px; }
.st-row { display: flex; gap: 8px; align-items: flex-start; margin-bottom: 8px; font-size: 12px; color: var(--ink-2); cursor: pointer; }
.st-row small { color: var(--ink-3); }
.st-note { font-size: 11px; color: var(--ink-3); }
.st-more { display: inline-block; margin-top: 10px; font-size: 11px; color: var(--indigo-ink); text-decoration: none; border-bottom: 1px dashed rgba(35, 64, 92, .4); }
</style>
