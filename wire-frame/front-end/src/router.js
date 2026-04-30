import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/login', component: () => import('./pages/LoginPage.vue') },
  { path: '/register', component: () => import('./pages/RegisterPage.vue') },
  // 회의실: 새 탭 전체화면 (헤더/사이드바 없음)
  {
    path: '/meetings/:meetingId/sessions/:sessionId/room',
    component: () => import('./pages/MeetingRoomPage.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/',
    component: () => import('./layouts/MainLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', component: () => import('./pages/HomePage.vue') },
      { path: 'minutes', component: () => import('./pages/AllMinutesPage.vue') },
      { path: 'past-meetings', component: () => import('./pages/PastMeetingsPage.vue') },
      { path: 'reports', component: () => import('./pages/AllReportsPage.vue') },
      { path: 'meetings/:meetingId/agenda', component: () => import('./pages/AgendaPage.vue') },
      { path: 'meetings/:meetingId/todo', component: () => import('./pages/TodoPage.vue') },
      { path: 'meetings/:meetingId/prepare', component: () => import('./pages/PreparePage.vue') },
      { path: 'meetings/:meetingId/sessions', component: () => import('./pages/SessionsPage.vue') },
      { path: 'meetings/:meetingId/card-news', component: () => import('./pages/CardNewsPage.vue') },
      { path: 'meetings/:meetingId/memory', component: () => import('./pages/TacitKnowledgePage.vue') },
      { path: 'profile', component: () => import('./pages/ProfilePage.vue') },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const token = localStorage.getItem('token')
  if (to.meta.requiresAuth && !token) return '/login'
  if ((to.path === '/login' || to.path === '/register') && token) return '/'
})

export default router
