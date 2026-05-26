import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api'

function safeParseUser() {
  try { return JSON.parse(localStorage.getItem('user') || 'null') }
  catch { return null }
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref(safeParseUser())
  const token = ref(localStorage.getItem('token') || '')

  async function login(email, password) {
    const { data } = await api.post('/api/v1/auth/login', { email, password })
    token.value = data.accessToken
    user.value = data.user
    localStorage.setItem('token', data.accessToken)
    localStorage.setItem('user', JSON.stringify(data.user))
  }

  async function loginWithEmail(email, password) {
    return login(email, password)
  }

  async function register(form) {
    await api.post('/api/v1/auth/signup', form)
  }

  async function updateProfile(data) {
    const { data: updated } = await api.patch('/api/v1/users/me', data)
    user.value = updated
    localStorage.setItem('user', JSON.stringify(updated))
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  return { user, token, login, loginWithEmail, register, updateProfile, logout }
})
