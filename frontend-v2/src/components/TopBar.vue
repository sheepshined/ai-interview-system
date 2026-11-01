<script setup>
import Icon from './Icon.vue'

defineProps({
  crumb: { type: String, default: '' },   // 当前页名，如「简历匹配」
  folio: { type: String, default: '' },   // 卷号，如「卷·02」
})

function toggleRail() {
  document.body.classList.toggle('rail-open')
}
</script>

<template>
  <div class="topbar">
    <div style="display:flex; align-items:center; gap:14px; min-width:0">
      <button class="icon-btn rail-toggle" aria-label="菜单" @click="toggleRail"><Icon name="menu" /></button>
      <div class="crumb">
        <span v-if="folio">{{ folio }}</span>
        <span v-if="folio" class="sep">/</span>
        <b>{{ crumb }}</b>
      </div>
    </div>
    <div class="topbar-actions">
      <slot name="actions" />
    </div>
  </div>
</template>