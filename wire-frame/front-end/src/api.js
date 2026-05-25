import axios from 'axios'

export const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

/** HTTP BASE_URL을 WebSocket URL로 변환합니다. */
export function toWsUrl(path) {
  const base = BASE_URL.replace(/^http/, 'ws')
  return `${base}${path}`
}

const api = axios.create({ baseURL: BASE_URL, timeout: 10000 })

api.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  res => res,
  err => {
    if (err.code === 'ECONNABORTED' || err.code === 'ERR_NETWORK' || !err.response) {
      return Promise.reject(new Error('서버에 연결할 수 없습니다. 백엔드가 실행 중인지 확인하세요.'))
    }
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default api

export async function streamPost(path, body, onChunk, onDone, onPlanning, onHighlight) {
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
        if (data.startsWith('[PLANNING] ') && onPlanning) {
          onPlanning(data.slice(11))
        } else if (data.startsWith('[HIGHLIGHT] ') && onHighlight) {
          try { onHighlight(JSON.parse(data.slice(12))) } catch {}
        } else {
          onChunk(data.replace(/\\n/g, '\n'))
        }
      }
    }
  }
  onDone?.()
}

