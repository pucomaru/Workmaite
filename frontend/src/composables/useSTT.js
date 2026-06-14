// ── HTTP 청크 방식 상수 (OpenAI 전사) ──────────────────
const MAX_CHUNK_MS = 12000
const MIN_CHUNK_MS = 1500
const SILENCE_MS = 900
const SILENCE_RMS = 0.015
const POLL_INTERVAL = 80

function getRMS(analyser) {
  const buf = new Float32Array(analyser.fftSize)
  analyser.getFloatTimeDomainData(buf)
  let sum = 0
  for (const v of buf) sum += v * v
  return Math.sqrt(sum / buf.length)
}

function authHeaders() {
  const token = sessionStorage.getItem('token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export function useSTT({ onResult, onError = null, getLang = null, getSessionId = null }) {
  let stream = null
  let active = false
  let currentRecorder = null
  let generation = 0

  // ── HTTP 청크 방식 (OpenAI 전사) ───────────────────
  async function runLoop(gen) {
    let audioCtx = null
    let analyser = null
    try {
      audioCtx = new AudioContext()
      analyser = audioCtx.createAnalyser()
      analyser.fftSize = 2048
      audioCtx.createMediaStreamSource(stream).connect(analyser)
    } catch {
      analyser = null
    }

    while (active && stream && generation === gen) {
      const chunks = []
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm'
      const recorder = new MediaRecorder(stream, { mimeType })
      currentRecorder = recorder
      recorder.ondataavailable = e => {
        if (e.data.size > 0) chunks.push(e.data)
      }

      const recStartedAt = Date.now() // 청크 길이 측정 → STT 비용 산정 (P4)
      await new Promise(resolve => {
        recorder.onstop = resolve
        recorder.start()
        const startedAt = Date.now()
        let silenceSince = null
        const pollTimer = setInterval(() => {
          if (recorder.state !== 'recording') {
            clearInterval(pollTimer)
            return
          }
          const elapsed = Date.now() - startedAt
          if (elapsed >= MAX_CHUNK_MS) {
            clearInterval(pollTimer)
            recorder.stop()
            return
          }
          if (!analyser) return
          const rms = getRMS(analyser)
          if (rms < SILENCE_RMS) {
            if (!silenceSince) silenceSince = Date.now()
            if (elapsed >= MIN_CHUNK_MS && Date.now() - silenceSince >= SILENCE_MS) {
              clearInterval(pollTimer)
              recorder.stop()
            }
          } else {
            silenceSince = null
          }
        }, POLL_INTERVAL)
        if (!analyser)
          setTimeout(() => {
            if (recorder.state === 'recording') recorder.stop()
          }, MAX_CHUNK_MS)
      })

      if (!active || generation !== gen) break
      const blob = new Blob(chunks, { type: mimeType })
      if (blob.size < 500) continue

      const rawLang = typeof getLang === 'function' ? getLang() : 'ko'
      const lang = rawLang.split('-')[0].toLowerCase()
      const sessionId = typeof getSessionId === 'function' ? getSessionId() : null

      const durationSec = Math.max(0, (Date.now() - recStartedAt) / 1000)
      const formData = new FormData()
      formData.append('audio', blob, 'audio.webm')
      formData.append('lang', lang)
      formData.append('duration_sec', durationSec.toFixed(2)) // STT 비용 산정 (P4)
      if (sessionId) formData.append('session_id', String(sessionId))

      try {
        const res = await fetch('/api/stt/transcribe', {
          method: 'POST',
          headers: authHeaders(),
          body: formData,
        })
        if (!res.ok) {
          // STT 5xx (전 provider 실패, P4-3) — 청크 1회 재시도 후에도 실패면 사용자 알림
          const retry = await fetch('/api/stt/transcribe', {
            method: 'POST',
            headers: authHeaders(),
            body: formData,
          })
          if (!retry.ok) {
            if (typeof onError === 'function')
              onError('음성 인식에 일시적으로 실패했습니다. 녹음은 계속됩니다.')
            continue
          }
          const data = await retry.json()
          if (!active || generation !== gen) break
          if (data.text?.trim()) onResult(data.text.trim(), data.text_id ?? null)
          continue
        }
        const data = await res.json()
        if (!active || generation !== gen) break
        if (data.text?.trim()) onResult(data.text.trim(), data.text_id ?? null)
      } catch (e) {
        console.warn('[STT] 전송 실패', e)
      }
    }

    if (audioCtx) audioCtx.close().catch(() => {})
  }

  // ── 공통 start / stop ─────────────────────────────────────────
  async function start() {
    if (active) return
    active = true
    generation++
    const myGen = generation
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      runLoop(myGen) // 12초 청크 → /api/stt/transcribe (OpenAI 단순 전사)
    } catch (e) {
      active = false
      console.warn('[STT] 마이크 권한 없음', e)
      throw e
    }
  }

  function stop() {
    active = false
    generation++
    if (currentRecorder?.state === 'recording') currentRecorder.stop()
    if (stream) {
      stream.getTracks().forEach(t => t.stop())
      stream = null
    }
    currentRecorder = null
  }

  return { start, stop, supported: !!navigator.mediaDevices?.getUserMedia }
}
