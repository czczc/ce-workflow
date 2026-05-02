import { createRouter, createWebHistory } from 'vue-router'
import ChatPage from '../pages/ChatPage.vue'
import DocumentsPage from '../pages/DocumentsPage.vue'
import ReportsPage from '../pages/ReportsPage.vue'

const routes = [
  { path: '/', redirect: '/chat' },
  { path: '/chat', component: ChatPage },
  { path: '/documents', component: DocumentsPage },
  { path: '/reports', component: ReportsPage },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
