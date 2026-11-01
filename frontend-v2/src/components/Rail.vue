<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Icon from './Icon.vue'
import { clearAuth, getUsername } from '../auth'

const route = useRoute()
const router = useRouter()
const username = getUsername()
const activePage = computed(() => route.meta.page || '')
const collapseKey = `ui:rail-collapsed:${username || 'anonymous'}`
const collapsed = ref(localStorage.getItem(collapseKey) === '1')

const GROUPS = [
  {
    title: 'Interview / 面试流程',
    links: [
      { page: 'home', href: '/', idx: '01', ic: 'house', label: '首页' },
      { page: 'resume', href: '/resume-upload', idx: '02', ic: 'file', label: '简历匹配' },
      { page: 'choose', href: '/choose-job', idx: '03', ic: 'pin', label: '选择岗位' },
      { page: 'applications', href: '/applications', idx: '04', ic: 'route', label: '投递记录' },
      { page: 'records', href: '/interview-records', idx: '05', ic: 'records', label: '面试记录' },
      { page: 'growth', href: '/growth', idx: '06', ic: 'growth', label: '成长档案' },
    ],
  },
  {
    title: 'Library / 个人知识库',
    links: [
      { page: 'workspace', href: '/knowledge', idx: '07', ic: 'pen', label: '我的笔记' },
      { page: 'graph', href: '/knowledge/graph', idx: '08', ic: 'graph', label: '知识图谱' },
      { page: 'chat', href: '/knowledge/chat', idx: '09', ic: 'chat', label: 'AI 对话' },
      { page: 'settings', href: '/settings', idx: '10', ic: 'sliders', label: '设置' },
    ],
  },
]

function logout() {
  clearAuth()
  router.push('/login')
}

function toggleCollapsed() {
  collapsed.value = !collapsed.value
  localStorage.setItem(collapseKey, collapsed.value ? '1' : '0')
}
</script>

<template>
  <aside class="rail" :class="{ 'is-collapsed': collapsed }">
    <div class="rail-head">
      <RouterLink class="brandmark" to="/">
        <span class="seal">面</span>
        <span>
          <span class="name">AI 模拟面试官</span>
          <span class="sub" style="display:block">Interview Studio</span>
        </span>
      </RouterLink>
      <button class="rail-collapse" :title="collapsed ? '展开侧栏' : '收起侧栏'"
              :aria-label="collapsed ? '展开侧栏' : '收起侧栏'" @click="toggleCollapsed">
        <Icon :name="collapsed ? 'chevronRight' : 'chevronLeft'" />
      </button>
    </div>

    <nav class="rail-groups">
      <div v-for="g in GROUPS" :key="g.title" class="rail-group">
        <div class="rail-group-title">{{ g.title }}</div>
        <RouterLink
          v-for="l in g.links" :key="l.page" :to="l.href"
          class="rail-link" :class="{ 'is-active': activePage === l.page }"
        >
          <span class="idx">{{ l.idx }}</span>
          <Icon :name="l.ic" /><span>{{ l.label }}</span>
        </RouterLink>
      </div>
    </nav>

    <div class="rail-foot">
      <span class="rail-avatar">{{ (username || 'U').charAt(0).toUpperCase() }}</span>
      <div class="rail-user">
        <div class="u-name">{{ username || '未登录' }}</div>
        <div class="u-role">Candidate</div>
      </div>
      <button class="rail-quit" title="退出登录" @click="logout"><Icon name="arrowLeft" /></button>
    </div>
  </aside>
</template>
