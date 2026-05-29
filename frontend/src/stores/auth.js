import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../api'

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
    sessionStorage.setItem('user', JSON.stringify(data.user))
  }

  async function loginWithEmail(email, password) {
    const { data } = await api.post('/api/v1/auth/login', { email, password })
    token.value = data.accessToken
    user.value = data.user
    sessionStorage.setItem('token', data.accessToken)
    sessionStorage.setItem('refreshToken', data.refreshToken)
    sessionStorage.setItem('user', JSON.stringify(data.user))
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
    token.value = ''
    user.value = null
    sessionStorage.removeItem('token')
    sessionStorage.removeItem('refreshToken')
    sessionStorage.removeItem('user')
  }

  const isStrategicTeam = computed(() => (user.value?.department || '').trim() === '전략기획팀')

  return { user, token, isStrategicTeam, login, loginWithEmail, register, updateProfile, logout }
})
