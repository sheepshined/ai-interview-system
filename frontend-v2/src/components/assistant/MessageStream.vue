<template>
  <div class="ms-wrap">
    <div ref="scroller" class="ms-list">
      <div v-if="!sock.messages.value.length" class="ms-empty">
        跟助手说句话试试：<br>「根据我最近三次面试报告，说我该补什么」
      </div>
      <div v-for="(m, i) in sock.messages.value" :key="i" :class="['ms-row', m.role]">
        <div class="ms-bubble" v-html="render(m.content)"></div>
        <ToolTrace v-if="m.trace && m.trace.length" :trace="m.trace" />
      </div>
    </div>
    <form class="ms-input" @submit.prevent="submit">
      <textarea v-model="text" rows="2" placeholder="问助手任何关于你面试 / 知识库的事…"
                @keydown.enter.exact.prevent="submit"></textarea>
      <button v-if="voiceSupported" type="button" :class="['ms-mic', { rec: listening }]"
              :title="listening ? '停止录音' : '语音输入（本地 SenseVoice）'" @click="toggleVoice">
        <Icon :name="listening ? 'square' : 'mic'" /><span v-if="listening">{{ elapsed }}s</span>
      </button>
      <button type="submit" title="发送" :disabled="sock.streaming.value || sock.sending.value || !!sock.pendingProposal.value || !text.trim()"><Icon name="send" /></button>
      <button v-if="sock.streaming.value" type="button" class="ms-stop" title="停止" @click="sock.interruptTurn()"><Icon name="square" /></button>
    </form>
    <p v-if="sock.lastError.value" class="ms-err">{{ sock.lastError.value }}</p>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import Icon from '../Icon.vue'
import ToolTrace from './ToolTrace.vue'
import { renderMarkdown } from '../../utils/markdown'
import { useVoiceInput } from '../../composables/useVoiceInput'

const props = defineProps({ sock: { type: Object, required: true }, send: { type: Function, required: true } })
const text = ref('')
const scroller = ref(null)

// 本地离线 ASR: 说完点停, 转写进输入框可改再发 (转写确认闸, RESUME_UPGRADE_PLAN V2)
const { supported: voiceSupported, recording: listening, elapsed, start, stop } =
  useVoiceInput({ onResult: (t) => { text.value = (text.value + ' ' + t).trim() } })

function toggleVoice() {
  if (listening.value) stop()
  else start()
}

function render(content) { return renderMarkdown(content || '') }

async function submit() {
  const value = text.value.trim()
  if (!value || props.sock.streaming.value || props.sock.sending.value || props.sock.pendingProposal.value) return
  if (await props.send(value) && text.value.trim() === value) text.value = ''
}

watch(() => props.sock.messages.value.map((m) => m.content).join(''), async () => {
  await nextTick()
  if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
})
</script>

<style scoped>
.ms-wrap { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.ms-list { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 10px; }
.ms-empty { color: var(--ink-3); font-size: 12px; line-height: 1.8; padding: 8px 4px; }
.ms-row { display: flex; flex-direction: column; gap: 4px; }
.ms-row.user { align-items: flex-end; }
.ms-bubble {
  overflow-wrap: anywhere; min-width: 0;
  max-width: 88%; padding: 8px 10px; border-radius: var(--r-1);
  font-size: 13px; line-height: 1.7; color: var(--ink);
  background: var(--sheet-2); border: 1px solid var(--line-soft);
}
.ms-row.user .ms-bubble { background: var(--verm-wash); border-color: var(--verm-line); }
.ms-bubble :deep(pre) { overflow-x: auto; font-family: var(--f-mono); font-size: 12px; }
.ms-input { display: flex; gap: 6px; align-items: flex-end; padding: 10px; border-top: 1px solid var(--line); }
.ms-input textarea {
  min-width: 0;
  flex: 1; resize: none; border: 1px solid var(--line); border-radius: var(--r-1);
  padding: 8px; font-size: 13px; font-family: var(--f-sans);
  background: var(--paper); color: var(--ink);
}
.ms-input button {
  border: 1px solid var(--line-strong); border-radius: var(--r-1);
  padding: 8px 12px; cursor: pointer; background: var(--ink); color: var(--paper); font-size: 12px;
}
.ms-input button:disabled { opacity: .45; cursor: not-allowed; }
.ms-input button { display: flex; align-items: center; justify-content: center; }
.ms-input button :deep(svg) { width: 16px; height: 16px; }
.ms-mic { display: flex; align-items: center; gap: 4px; background: var(--sheet) !important; color: var(--ink) !important; }
.ms-mic :deep(svg) { width: 14px; height: 14px; }
.ms-mic.rec { background: var(--vermilion) !important; color: #fff !important; }
.ms-stop { background: var(--vermilion) !important; border-color: var(--vermilion) !important; }
.ms-err { color: var(--vermilion-deep); font-size: 11px; padding: 0 12px 8px; margin: 0; }
</style>
