/**
 * useAssistantHistory — 会话/设置/记忆的 REST 访问 (AGENT_PLAN §5.13)。v2 版。
 */
import { ref } from 'vue'
import {
  listAssistantSessions, getAssistantSession, createAssistantSession,
  renameAssistantSession, deleteAssistantSession,
  getAssistantSettings, putAssistantSettings,
  listAssistantMemories, deleteAssistantMemory, clearAssistantMemories,
} from '../api'

export function useAssistantHistory() {
  const sessions = ref([])
  const settings = ref({ auto_accept_level: 'read_auto', memory_enabled: true })
  const memories = ref([])

  async function loadSessions() {
    const res = await listAssistantSessions()
    if (res.success) sessions.value = res.sessions || []
    return res
  }

  async function loadMessages(sessionId) {
    const res = await getAssistantSession(sessionId)
    return res.success ? res.messages || [] : []
  }

  async function loadSession(sessionId) { return getAssistantSession(sessionId) }

  async function newSession() {
    const res = await createAssistantSession()
    if (res.success) await loadSessions()
    return res.session || null
  }

  async function removeSession(sessionId) {
    const res = await deleteAssistantSession(sessionId)
    if (res.success) await loadSessions()
    return res
  }

  async function rename(sessionId, title) {
    const res = await renameAssistantSession(sessionId, title)
    if (res.success) await loadSessions()
    return res
  }

  async function loadSettings() {
    const res = await getAssistantSettings()
    if (res.success) settings.value = res.settings
    return res
  }

  async function saveSettings(patch) {
    const res = await putAssistantSettings(patch)
    if (res.success) settings.value = res.settings
    return res
  }

  async function loadMemories(kind = '') {
    const res = await listAssistantMemories(kind)
    if (res.success) memories.value = res.memories || []
    return res
  }

  async function removeMemory(id) {
    const res = await deleteAssistantMemory(id)
    if (res.success) await loadMemories()
    return res
  }

  async function clearMemories() {
    const res = await clearAssistantMemories()
    if (res.success) memories.value = []
    return res
  }

  return {
    sessions, settings, memories,
    loadSessions, loadMessages, loadSession, newSession, removeSession, rename,
    loadSettings, saveSettings, loadMemories, removeMemory, clearMemories,
  }
}
