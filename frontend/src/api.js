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

// ── 공유 토큰 갱신 헬퍼 ────────────────────────────────────────────────────
let _refreshPromise = null

function _clearSession() {
  sessionStorage.removeItem('token')
  sessionStorage.removeItem('refreshToken')
  sessionStorage.removeItem('user')
  window.location.href = '/landing'
}

/**
 * Refresh Token으로 Access Token을 갱신합니다.
 * 동시에 여러 401이 발생해도 단일 Promise를 공유해 중복 호출을 방지합니다.
 */
async function _doRefresh() {
  if (!_refreshPromise) {
    const refreshToken = sessionStorage.getItem('refreshToken')
    if (!refreshToken) throw new Error('no_refresh_token')
    _refreshPromise = axios
      .post(`${BASE_URL}/api/v1/auth/refresh`, { refreshToken })
      .then(({ data }) => {
        const newToken = data.data?.accessToken || data.accessToken
        const newRefresh = data.data?.refreshToken || data.refreshToken
        if (!newToken) throw new Error('empty_token_response')
        sessionStorage.setItem('token', newToken)
        if (newRefresh) sessionStorage.setItem('refreshToken', newRefresh)
        return newToken
      })
      .finally(() => { _refreshPromise = null })
  }
  return _refreshPromise
}

/**
 * 토큰 만료 5분 전에 미리 갱신합니다.
 * streamPost / streamPostForm 진입 시 호출해 스트림 도중 토큰 만료를 예방합니다.
 */
async function ensureFreshToken() {
  const token = sessionStorage.getItem('token')
  if (!token) return
  try {
    const b64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    const payload = JSON.parse(atob(b64))
    const msLeft = payload.exp * 1000 - Date.now()
    if (msLeft < 5 * 60 * 1000) await _doRefresh()
  } catch { /* 파싱 실패 무시 — 요청 실패 시 인터셉터가 처리 */ }
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
  async err => {
    if (err.code === 'ECONNABORTED' || err.code === 'ERR_NETWORK' || !err.response) {
      return Promise.reject(new Error('서버에 연결할 수 없습니다. 백엔드가 실행 중인지 확인하세요.'))
    }
    const isAuthRequest = err.config.url?.includes('/auth/login') || err.config.url?.includes('/auth/signup')
    if ((err.response?.status === 401 || err.response?.status === 403) && !err.config._retry && !isAuthRequest) {
      err.config._retry = true
      try {
        const newToken = await _doRefresh()
        err.config.headers.Authorization = `Bearer ${newToken}`
        return api(err.config)
      } catch {
        _clearSession()
      }
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
  async err => {
    if (err.code === 'ECONNABORTED' || err.code === 'ERR_NETWORK' || !err.response) {
      return Promise.reject(new Error('AI 서버에 연결할 수 없습니다.'))
    }
    if (err.response?.status === 401 && !err.config._retry) {
      err.config._retry = true
      try {
        const newToken = await _doRefresh()
        err.config.headers.Authorization = `Bearer ${newToken}`
        return apiAI(err.config)
      } catch {
        _clearSession()
      }
    }
    return Promise.reject(err)
  }
)

// ── Streaming (FastAPI) ────────────────────────────────────────────────────
async function _readSseStream(response, onChunk, onDone, onPlanning, onHighlight, onResult) {
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
        } else if (data.startsWith('[RESULT] ') && onResult) {
          try { onResult(JSON.parse(data.slice(9))) } catch {}
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

export async function streamPost(path, body, onChunk, onDone, onPlanning, onHighlight, onResult) {
  // 만료 임박 시 미리 갱신 (스트림 도중 토큰 만료 방지)
  await ensureFreshToken()

  const doFetch = (tok) => fetch(`${AI_BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tok}` },
    body: JSON.stringify(body),
  })

  let token = sessionStorage.getItem('token')
  let response = await doFetch(token)

  if (response.status === 401) {
    try {
      token = await _doRefresh()
      response = await doFetch(token)
    } catch {
      _clearSession()
      return
    }
  }

  if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)

  await _readSseStream(response, onChunk, onDone, onPlanning, onHighlight, onResult)
}

// ── Streaming with FormData (FastAPI SSE) ───────────────────────────────────
// 각 SSE 라인의 data를 JSON으로 파싱해 onEvent(event)로 전달. data가 '[DONE]'이면 종료.
export async function streamPostForm(path, formData, onEvent) {
  await ensureFreshToken()

  const doFetch = (tok) => fetch(`${AI_BASE_URL}${path}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${tok}` },
    body: formData,
  })

  let token = sessionStorage.getItem('token')
  let response = await doFetch(token)

  if (response.status === 401) {
    try {
      token = await _doRefresh()
      response = await doFetch(token)
    } catch {
      _clearSession()
      return
    }
  }

  if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)

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
      if (!line.startsWith('data: ')) continue
      const data = line.slice(6)
      if (data === '[DONE]') return
      try { onEvent(JSON.parse(data)) } catch { /* 부분 데이터 무시 */ }
    }
  }
}

