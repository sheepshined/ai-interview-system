<template>
  <div class="pc">
    <div class="pc-head">待确认 · {{ kindLabel }}</div>
    <p class="pc-human">{{ pending.human }}</p>
    <p v-if="pending.risk_hint" class="pc-hint">{{ pending.risk_hint }}</p>

    <div v-for="f in pending.editable_fields || []" :key="f.field" class="pc-field">
      <label>{{ labels[f.field] || f.field }}</label>
      <select v-if="f.value_type === 'enum'" v-model="args[f.field]">
        <option v-for="o in f.options" :key="o.value" :value="o.value">{{ o.label }}</option>
      </select>
      <textarea v-else-if="f.value_type === 'long_text'" v-model="args[f.field]" rows="2"></textarea>
      <input v-else-if="f.value_type === 'number'" v-model.number="args[f.field]" type="number" />
      <input v-else v-model="args[f.field]" type="text" />
    </div>

    <div class="pc-actions">
      <button class="pc-ok" :disabled="busy" @click="decide('approve')">确认</button>
      <button v-if="pending.editable_fields?.length" class="pc-edit" :disabled="busy" @click="decide('edit')">按修改后确认</button>
      <button class="pc-no" :disabled="busy" @click="decide('reject')">取消</button>
    </div>
  </div>
</template>

<script setup>
import { reactive, watch, computed } from 'vue'

const props = defineProps({ pending: { type: Object, required: true }, busy: Boolean })
const emit = defineEmits(['decide'])
const args = reactive({})
const labels = { question_count: '题量', difficulty: '难度', mode: '模式', resume_ref: '简历', question: '问题' }
const kindLabel = computed(() =>
  props.pending.kind === 'interview' ? '开始面试'
    : props.pending.kind === 'kb_session' ? '知识库对话' : '工具执行')

watch(() => props.pending, (p) => {
  Object.keys(args).forEach((k) => delete args[k])
  Object.assign(args, JSON.parse(JSON.stringify(p.args || {})))
}, { immediate: true })

function decide(action) {
  const edited = Object.fromEntries((props.pending.editable_fields || []).map((f) => [f.field, args[f.field]]))
  emit('decide', { action, args: action === 'edit' ? edited : {}, reason: '' })
}
</script>

<style scoped>
.pc { border-top: 1px solid var(--line); padding: 12px; background: var(--sheet-2); max-height: 55%; overflow-y: auto; flex-shrink: 0; overflow-wrap: anywhere; }
.pc-head { font-size: 12px; font-weight: 700; color: var(--vermilion-deep); margin-bottom: 6px; }
.pc-human { font-size: 13px; color: var(--ink); margin: 0 0 4px; }
.pc-hint { font-size: 11px; color: var(--ink-3); margin: 0 0 8px; }
.pc-field { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.pc-field label { width: 52px; font-size: 12px; color: var(--ink-2); flex-shrink: 0; }
.pc-field select, .pc-field input, .pc-field textarea {
  min-width: 0;
  flex: 1; border: 1px solid var(--line); border-radius: var(--r-1);
  padding: 5px 7px; font-size: 12px; background: var(--paper); color: var(--ink);
}
.pc-actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.pc-actions button { border: 1px solid var(--line-strong); border-radius: var(--r-1); padding: 7px 12px; font-size: 12px; cursor: pointer; }
.pc-ok { background: var(--vermilion); border-color: var(--vermilion) !important; color: #fff; }
.pc-edit { background: var(--sheet); color: var(--ink); }
.pc-no { background: transparent; color: var(--ink-3); border-color: var(--line) !important; }
</style>
