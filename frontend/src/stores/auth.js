import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../api'
import { toast } from '../composables/useToast'

function safeParseUser() {
  try { return JSON.parse(sessionStorage.getItem('user') || 'null') }
  catch { return null }
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref(safeParseUser())
  const token = ref(sessionStorage.getItem('token') || '')

  async function login(employee_id, password) {
    const { data } = await api.post('/api/v1/auth/login', { email: employee_id, password })
    token.value = data.accessToken
    user.value = data.user
    sessionStorage.setItem('token', data.accessToken)
    if (data.refreshToken) sessionStorage.setItem('refreshToken', data.refreshToken)
    sessionStorage.setItem('user', JSON.stringify(data.user))
  }

  async function loginWithEmail(email, password) {
    const { data } = await api.post('/api/v1/auth/login', { email, password })
    token.value = data.accessToken
    user.value = data.user
    sessionStorage.setItem('token', data.accessToken)
    sessionStorage.setItem('refreshToken', data.refreshToken)
    sessionStorage.setItem('user', JSON.stringify(data.user))
 
    if (data.user?.mustChangePassword) {
      // 임시 비밀번호 과도기 (P1-7②): 변경을 강하게 안내
      toast.info('임시 비밀번호로 로그인했습니다. 보안을 위해 프로필에서 비밀번호를 변경해주세요.', { duration: 6000 })
    }
  }

  async function register(form) {
    await api.post('/api/v1/auth/signup', form)
  }

  async function updateProfile(payload) {
    const { data } = await api.patch('/api/v1/users/me', payload)
    user.value = data
    sessionStorage.setItem('user', JSON.stringify(data))
  }

  function logout() {
    // 서버 측 refresh token 폐기 (실패해도 로컬 세션은 정리)
    const refreshToken = sessionStorage.getItem('refreshToken')
    if (refreshToken) {
      api.post('/api/v1/auth/logout', { refreshToken }).catch(() => {})
    }
    token.value = ''
    user.value = null
    sessionStorage.removeItem('token')
    sessionStorage.removeItem('refreshToken')
    sessionStorage.removeItem('user')
  }

  // 관리자 판별: 서버 role(RBAC) 기준. role 필드가 없는 구버전 세션만 부서명 폴백(재로그인 시 해소)
  const isStrategicTeam = computed(() =>
    user.value?.role === 'SYSTEM_ADMIN' ||
    (!user.value?.role && (user.value?.department || '').trim() === '전략기획팀')
  )

  return { user, token, isStrategicTeam, login, loginWithEmail, register, updateProfile, logout }
})
