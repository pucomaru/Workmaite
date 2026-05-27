import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../api'

function safeParseUser() {
  try { return JSON.parse(localStorage.getItem('user') || 'null') }
  catch { return null }
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref(safeParseUser())
  const token = ref(localStorage.getItem('token') || '')

  async function login(employee_id, password) {
    const { data } = await api.post('/api/v1/auth/login', { email: employee_id, password })
    token.value = data.accessToken
    user.value = data.user
    localStorage.setItem('token', data.accessToken)
    localStorage.setItem('user', JSON.stringify(data.user))
  }

  async function loginWithEmail(email, password) {
    const { data } = await api.post('/api/v1/auth/login', { email, password })
    token.value = data.accessToken
    user.value = data.user
    localStorage.setItem('token', data.accessToken)
    localStorage.setItem('user', JSON.stringify(data.user))
  }

  async function register(form) {
    await api.post('/api/v1/auth/signup', form)
  }

  async function updateProfile(payload) {
    const { data } = await api.patch('/api/v1/users/me', payload)
    user.value = data
    localStorage.setItem('user', JSON.stringify(data))
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  const isStrategicTeam = computed(() => (user.value?.department || '').trim() === '전략기획팀')

  return { user, token, isStrategicTeam, login, loginWithEmail, register, updateProfile, logout }
})
