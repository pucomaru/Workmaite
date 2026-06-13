import axios from 'axios'
import { markNetworkDown, markNetworkUp } from './stores/network'

// SpringBoot (8080) — 인증/CRUD 전담
// 로컬: VITE_API_URL=http://localhost:8080, k8s: 미설정(상대경로, Ingress가 /api 라우팅)
export const BASE_URL = import.meta.env.VITE_API_URL ?? ''

// FastAPI (8000) — AI 에이전트/알림/채팅 전담
// 로컬: VITE_AI_URL=http://localhost:8000, k8s: 미설정(상대경로, Ingress가 /ai 라우팅)
export const AI_BASE_URL = import.meta.env.VITE_AI_URL ?? ''

/** AI 서버 WebSocket URL 변환 (인증 토큰 자동 부착) */
export function toWsUrl(path) {
  const base = AI_BASE_URL.replace(/^http/, 'ws')
  const token = sessionStorage.getItem('token')
  const sep = path.includes('?') ? '&' : '?'
  return token ? `${base}${path}${sep}token=${encodeURIComponent(token)}` : `${base}${path}`
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
      .finally(() => {
        _refreshPromise = null
      })
  }
  return _refreshPromise
}

/**
 * 토큰이 곧 만료될 경우(5분 이내) 갱신합니다.
 * - streamPost / streamPostForm 진입 시 안전망으로 호출
 * - useActivityRefresh 컴포저블이 사용자 인터랙션 시에도 호출
 */
export async function ensureFreshToken() {
  const token = sessionStorage.getItem('token')
  if (!token) return
  try {
    const b64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    const payload = JSON.parse(atob(b64))
    const msLeft = payload.exp * 1000 - Date.now()
    if (msLeft < 5 * 60 * 1000) await _doRefresh()
  } catch {
    /* 파싱 실패 무시 — 요청 실패 시 인터셉터가 처리 */
  }
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
    markNetworkUp()
    // SpringBoot ApiResponse { success, message, data } 자동 언랩
    if (res.data && typeof res.data === 'object' && 'success' in res.data && 'data' in res.data) {
      res.data = res.data.data
    }
    return res
  },
  async err => {
    if (err.code === 'ECONNABORTED' || err.code === 'ERR_NETWORK' || !err.response) {
      markNetworkDown() // 전역 배너 표시 — 스토어 캐시가 최신 아님을 사용자에게 인지시킴
      return Promise.reject(new Error('서버에 연결할 수 없습니다.'))
    }
    const isAuthRequest =
      err.config.url?.includes('/auth/login') || err.config.url?.includes('/auth/signup')
    if (
      (err.response?.status === 401 || err.response?.status === 403) &&
      !err.config._retry &&
      !isAuthRequest
    ) {
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
  },
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
  res => {
    markNetworkUp()
    return res
  },
  async err => {
    if (err.code === 'ECONNABORTED' || err.code === 'ERR_NETWORK' || !err.response) {
      markNetworkDown()
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
  },
)

// ── Streaming (FastAPI) ────────────────────────────────────────────────────
// SSE v2(event: 필드 기반, P3A-6)와 v1([PLANNING] 등 data 프리픽스) 모두 파싱.
// v2는 LLM 출력에 'data:'/'[DONE]'이 섞여도 오동작하지 않는다 (FE-2).
async function _readSseStream(response, onChunk, onDone, onPlanning, onHighlight, onResult) {
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let eventType = null // 직전 'event:' 라인 (v2)
  const handleV2 = (type, data) => {
    switch (type) {
      case 'done':
        onDone?.()
        return true
      case 'planning': {
        try {
          onPlanning?.(JSON.parse(data).text ?? data)
        } catch {
          onPlanning?.(data)
        }
        break
      }
      case 'result': {
        try {
          onResult?.(JSON.parse(data))
        } catch {}
        break
      }
      case 'highlight': {
        try {
          onHighlight?.(JSON.parse(data))
        } catch {}
        break
      }
      case 'error': {
        try {
          onChunk(`[오류] ${JSON.parse(data).message ?? data}`)
        } catch {
          onChunk(`[오류] ${data}`)
        }
        break
      }
      case 'run':
        break // {run_id} — 중단/이어보기용 메타 (후속 UI에서 사용)
      case 'token':
      default: {
        try {
          onChunk(JSON.parse(data).text ?? '')
        } catch {
          onChunk(data.replace(/\\n/g, '\n'))
        }
      }
    }
    return false
  }
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop()
    for (const line of lines) {
      if (line.startsWith('event: ')) {
        eventType = line.slice(7).trim()
        continue
      }
      if (!line.startsWith('data: ')) continue
      const data = line.slice(6)
      if (eventType) {
        // v2
        const finished = handleV2(eventType, data)
        eventType = null
        if (finished) return
        continue
      }
      // v1 폴백
      if (data === '[DONE]') {
        onDone?.()
        return
      }
      if (data.startsWith('[PLANNING] ') && onPlanning) {
        onPlanning(data.slice(11))
      } else if (data.startsWith('[RESULT] ') && onResult) {
        try {
          onResult(JSON.parse(data.slice(9)))
        } catch {}
      } else if (data.startsWith('[HIGHLIGHT] ') && onHighlight) {
        try {
          onHighlight(JSON.parse(data.slice(12)))
        } catch {}
      } else {
        onChunk(data.replace(/\\n/g, '\n'))
      }
    }
  }
  onDone?.()
}

export async function streamPost(
  path,
  body,
  onChunk,
  onDone,
  onPlanning,
  onHighlight,
  onResult,
  options = {},
) {
  // 만료 임박 시 미리 갱신 (스트림 도중 토큰 만료 방지)
  await ensureFreshToken()

  const doFetch = tok =>
    fetch(`${AI_BASE_URL}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${tok}` },
      body: JSON.stringify(body),
      signal: options.signal, // 중단 버튼 (P3A-6) — abort 시 서버 generator도 취소됨
    })

  let token = sessionStorage.getItem('token')
  let response = await doFetch(token)

  if (response.status === 401) {
    try {
      token = await _doRefresh()
      response = await doFetch(token)
    } catch {
      _clearSession()
      onDone?.() // 세션 만료로 중단해도 호출자의 로딩 상태는 반드시 해제 (agentLoading 고착 방지)
      return
    }
  }

  if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)

  try {
    await _readSseStream(response, onChunk, onDone, onPlanning, onHighlight, onResult)
  } catch (e) {
    if (e.name === 'AbortError') {
      onDone?.()
      return
    } // 사용자 중단은 정상 종료로 처리
    throw e
  }
}

// ── Streaming with FormData (FastAPI SSE) ───────────────────────────────────
// 각 SSE 라인의 data를 JSON으로 파싱해 onEvent(event)로 전달. data가 '[DONE]'이면 종료.
export async function streamPostForm(path, formData, onEvent) {
  await ensureFreshToken()

  const doFetch = tok =>
    fetch(`${AI_BASE_URL}${path}`, {
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
      try {
        onEvent(JSON.parse(data))
      } catch {
        /* 부분 데이터 무시 */
      }
    }
  }
}
