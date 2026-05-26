import axios from 'axios'

export const BASE_URL = import.meta.env.VITE_API_URL ?? ''

/** HTTP BASE_URL을 WebSocket URL로 변환합니다. */
export function toWsUrl(path) {
  const base = BASE_URL.replace(/^http/, 'ws')
  return `${base}${path}`
}

const api = axios.create({ baseURL: BASE_URL })

api.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  res => res,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default api

export async function streamPost(path, body, onChunk, onDone) {
  const token = localStorage.getItem('token')
  const response = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  })

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop()
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6)
        if (data === '[DONE]') { onDone?.(); return }
        onChunk(data.replace(/\\n/g, '\n'))
      }
    }
  }
  onDone?.()
}

