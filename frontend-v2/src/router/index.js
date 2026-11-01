import { createRouter, createWebHistory } from 'vue-router'
import { isAuthenticated } from '../auth'

const routes = [
  { path: '/login', name: 'Login', component: () => import('../views/LoginView.vue'), meta: { layout: 'bare' } },
  { path: '/', name: 'Home', component: () => import('../views/HomeView.vue'), meta: { layout: 'bare' } },
  { path: '/resume-upload', name: 'ResumeUpload', component: () => import('../views/ResumeUploadView.vue'), meta: { layout: 'app', page: 'resume' } },
  { path: '/job-matching', name: 'JobMatching', component: () => import('../views/JobMatchingView.vue'), meta: { layout: 'app', page: 'resume' } },
  { path: '/choose-job', name: 'ChooseJob', component: () => import('../views/ChooseJobView.vue'), meta: { layout: 'app', page: 'choose' } },
  { path: '/interview', name: 'Interview', component: () => import('../views/InterviewView.vue'), meta: { layout: 'bare' } },
  { path: '/interview-records', name: 'InterviewRecords', component: () => import('../views/InterviewRecordsView.vue'), meta: { layout: 'app', page: 'records' } },
  { path: '/growth', name: 'Growth', component: () => import('../views/GrowthView.vue'), meta: { layout: 'app', page: 'growth' } },
  { path: '/settings', name: 'Settings', component: () => import('../views/SettingsView.vue'), meta: { layout: 'app', page: 'settings' } },
  { path: '/applications', name: 'Applications', component: () => import('../views/ApplicationBoardView.vue'), meta: { layout: 'app', page: 'applications' } },
  { path: '/summary/:reportId', name: 'Summary', component: () => import('../views/SummaryView.vue'), meta: { layout: 'app', page: 'records' } },
  // 个人知识库
  { path: '/knowledge', name: 'Knowledge', component: () => import('../views/knowledge/KnowledgeView.vue'), meta: { layout: 'app', page: 'workspace' } },
  { path: '/knowledge/graph', name: 'KnowledgeGraph', component: () => import('../views/knowledge/GraphView.vue'), meta: { layout: 'app', page: 'graph' } },
  { path: '/knowledge/chat', name: 'KbChat', component: () => import('../views/knowledge/KbChatView.vue'), meta: { layout: 'app', page: 'chat' } },
  { path: '/knowledge/note/:id', name: 'NoteEditor', component: () => import('../views/knowledge/NoteEditorView.vue'), meta: { layout: 'app', page: 'workspace' } },
  { path: '/knowledge/new', name: 'NoteNew', component: () => import('../views/knowledge/NoteEditorView.vue'), meta: { layout: 'app', page: 'workspace' } },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to) => {
  const authenticated = isAuthenticated()
  if (to.name !== 'Login' && !authenticated) {
    return { name: 'Login', query: { redirect: to.fullPath } }
  }
  if (to.name === 'Login' && authenticated) {
    return { name: 'Home' }
  }
  return true
})

export default router
