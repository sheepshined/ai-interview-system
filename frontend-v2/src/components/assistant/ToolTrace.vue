<template>
  <details class="tt">
    <summary>工具轨迹 · {{ trace.length }}</summary>
    <ul>
      <li v-for="(t, i) in trace" :key="i" :class="{ 'is-skill': isSkill(t) }">
        <span :class="['tt-dot', t.ok === false ? 'bad' : (t.ok === true ? 'good' : 'wait')]"></span>
        <code>{{ t.name }}</code>
        <span v-if="t.skill" class="tt-skill"><Icon name="sparkle" :size="11" />{{ t.skill }}</span>
        <span class="tt-ms">{{ t.ms ? t.ms + 'ms' : '' }}</span>
      </li>
    </ul>
  </details>
</template>

<script setup>
import Icon from '../Icon.vue'

defineProps({ trace: { type: Array, required: true } })

const SKILL_TOOLS = new Set(['activate_skill', 'deactivate_skill'])
function isSkill(t) {
  return SKILL_TOOLS.has(t.name) || !!t.skill
}
</script>

<style scoped>
.tt { font-size: 11px; color: var(--ink-3); margin-left: 6px; }
.tt summary { cursor: pointer; user-select: none; }
.tt ul { list-style: none; margin: 4px 0 0; padding: 0 0 0 4px; display: flex; flex-direction: column; gap: 3px; }
.tt code { color: var(--ink-2); font-family: var(--f-mono); }
.tt-ms { margin-left: 6px; opacity: .7; }
.tt-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 6px; background: var(--ink-4); }
.tt-dot.good { background: var(--pine); }
.tt-dot.bad { background: var(--vermilion); }
.tt-dot.wait { background: var(--ochre); }
.tt li.is-skill code { color: var(--indigo-ink); }
.tt-skill {
  display: inline-flex; align-items: center; gap: 3px; margin-left: 6px;
  padding: 0 7px; border-radius: 999px; font-size: 10px; line-height: 17px;
  color: var(--indigo-ink); background: var(--indigo-wash);
  border: 1px solid rgba(35, 64, 92, 0.25);
}
</style>
