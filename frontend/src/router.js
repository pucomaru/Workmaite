import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/landing', component: () => import('./pages/LandingPage.vue') },
  { path: '/login', redirect: '/landing' },
  {
    path: '/',
    component: () => import('./layouts/MainLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', component: () => import('./pages/HomePage.vue') },
      { path: 'archive', component: () => import('./pages/ArchivePage.vue') },
      { path: 'company', component: () => import('./pages/CompanyPage.vue') },
      { path: 'meetings', component: () => import('./pages/MeetingsPage.vue') },
      { path: 'session-record', component: () => import('./pages/SessionPage.vue') },
      { path: 'minutes', redirect: '/archive' },
      { path: 'reports', redirect: '/archive' },
      { path: 'past-meetings', redirect: '/archive' },
      { path: 'meetings/:meetingId', redirect: '/meetings' },
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
  const token = sessionStorage.getItem('token')
  if (to.meta.requiresAuth && !token) return '/landing'
  if ((to.path === '/register' || to.path === '/landing') && token) return '/'
})

export default router
