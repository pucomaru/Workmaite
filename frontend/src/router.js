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
      { path: 'organization', component: () => import('./pages/OrganizationPage.vue') },
      { path: 'meeting-groups', component: () => import('./pages/MeetingGroupsPage.vue') },
      { path: 'session-record', component: () => import('./pages/SessionPage.vue') },
      { path: 'minutes', redirect: '/archive' },
      { path: 'reports', redirect: '/archive' },
      { path: 'past-meetings', component: () => import('./pages/PastMeetingsPage.vue') },
      { path: 'meetings/:meetingId', redirect: '/meeting-groups' },
      // { path: 'meetings/:meetingId/card-news', component: () => import('./pages/CardNewsPage.vue') },
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
