import axios from 'axios'

// SpringBoot (8080) — 인증/CRUD 전담
// 로컬: VITE_API_URL=http://localhost:8080, k8s: 미설정(상대경로, Ingress가 /api 라우팅)
export const BASE_URL = import.meta.env.VITE_API_URL ?? ''

// FastAPI (8000) — AI 에이전트/알림/채팅 전담
// 로컬: VITE_AI_URL=http://localhost:8000, k8s: 미설정(상대경로, Ingress가 /ai 라우팅)
export const AI_BASE_URL = import.meta.env.VITE_AI_URL ?? ''

/** AI 서버 WebSocket URL 변환 */
export function toWsUrl(path) {
  const base = AI_BASE_URL.replace(/^http/, 'ws')
  return `${base}${path}`
}

// ── SpringBoot API ─────────────────────────────────────────────────────────
const api = axios.create({ baseURL: BASE_URL, timeout: 10000 })

api.interceptors.request.use(config => {
  const token = sessionStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  res => {
    // SpringBoot ApiResponse { success, message, data } 자동 언랩
    if (res.data && typeof res.data === 'object' && 'success' in res.data && 'data' in res.data) {
      res.data = res.data.data
    }
    return res
  },
  err => {
    if (err.code === 'ECONNABORTED' || err.code === 'ERR_NETWORK' || !err.response) {
      return Promise.reject(new Error('서버에 연결할 수 없습니다. 백엔드가 실행 중인지 확인하세요.'))
    }
    if (err.response?.status === 401) {
      sessionStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export default api

// ── FastAPI AI API ─────────────────────────────────────────────────────────
export const apiAI = axios.create({ baseURL: AI_BASE_URL, timeout: 30000 })

apiAI.interceptors.request.use(config => {
  const token = sessionStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

apiAI.interceptors.response.use(
  res => res,
  err => {
    if (err.code === 'ECONNABORTED' || err.code === 'ERR_NETWORK' || !err.response) {
      return Promise.reject(new Error('AI 서버에 연결할 수 없습니다.'))
    }
    return Promise.reject(err)
  }
)

// ── Streaming (FastAPI) ────────────────────────────────────────────────────
export async function streamPost(path, body, onChunk, onDone, onPlanning, onHighlight) {
  const token = sessionStorage.getItem('token')
  const response = await fetch(`${AI_BASE_URL}${path}`, {
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

