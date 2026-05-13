import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/landing', component: () => import('./pages/LandingPage.vue') },
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
      { path: 'archive', component: () => import('./pages/ArchivePage.vue') },
      { path: 'organization', component: () => import('./pages/OrganizationPage.vue') },
      { path: 'meeting-groups', component: () => import('./pages/MeetingGroupsPage.vue') },
      { path: 'session-record', component: () => import('./pages/SessionPage.vue') },
      { path: 'minutes', redirect: '/archive' },
      { path: 'reports', redirect: '/archive' },
      { path: 'past-meetings', component: () => import('./pages/PastMeetingsPage.vue') },
      { path: 'meetings/:meetingId', redirect: to => `/meetings/${to.params.meetingId}/home` },
      { path: 'meetings/:meetingId/home', component: () => import('./pages/MeetingHomePage.vue') },
      { path: 'meetings/:meetingId/agenda', component: () => import('./pages/AgendaPage.vue') },
      { path: 'meetings/:meetingId/prepare', component: () => import('./pages/PreparePage.vue') },
      { path: 'meetings/:meetingId/sessions', component: () => import('./pages/SessionsPage.vue') },
      { path: 'meetings/:meetingId/card-news', component: () => import('./pages/CardNewsPage.vue') },
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
  if (to.meta.requiresAuth && !token) return '/landing'
  if ((to.path === '/login' || to.path === '/register' || to.path === '/landing') && token) return '/'
})

export default router
