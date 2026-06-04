const CHUNK_MS = 4000

/**
 * @param {Object} opts
 * @param {(text: string) => void}              opts.onResult      - 발화자 구분 없을 때 호출 (fallback)
 * @param {(segments: Array) => void}           [opts.onSegments]  - 발화자 구분 세그먼트 배열 콜백
 * @param {() => string}                        [opts.getLang]     - 언어 코드 반환 함수 ('ko' | 'en')
 * @param {() => number|null}                   [opts.getSessionId]- 세션 ID 반환 함수 (DB 저장용)
 */
export function useSTT({ onResult, onSegments = null, getLang = null, getSessionId = null }) {
  let stream = null
  let active = false
  let currentRecorder = null

  async function runLoop() {
    while (active && stream) {
      const chunks = []
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm'

      const recorder = new MediaRecorder(stream, { mimeType })
      currentRecorder = recorder

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data)
      }

      await new Promise(resolve => {
        recorder.onstop = resolve
        recorder.start()
        setTimeout(() => {
          if (recorder.state === 'recording') recorder.stop()
        }, CHUNK_MS)
      })

      if (!active) break

      const blob = new Blob(chunks, { type: mimeType })
      if (blob.size < 500) continue

      // lang 정규화: ko-KR → ko, en-US → en
      const rawLang = typeof getLang === 'function' ? getLang() : 'ko'
      const lang = rawLang.split('-')[0].toLowerCase()

      const formData = new FormData()
      formData.append('audio', blob, 'audio.webm')
      formData.append('lang', lang)

      const sessionId = typeof getSessionId === 'function' ? getSessionId() : null
      if (sessionId) formData.append('session_id', String(sessionId))

      try {
        const res = await fetch('/api/stt/transcribe', { method: 'POST', body: formData })
        const data = await res.json()

        if (data.segments?.length && typeof onSegments === 'function') {
          onSegments(data.segments)
        } else if (data.text?.trim()) {
          onResult(data.text.trim())
        }
      } catch (e) {
        console.warn('[STT] 전송 실패', e)
      }
    }
  }

  async function start() {
    if (active) return
    active = true
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      runLoop()
    } catch (e) {
      active = false
      console.warn('[STT] 마이크 권한 없음', e)
      throw e  // 호출부에서 마이크 오류 감지 가능하도록
    }
  }

  function stop() {
    active = false
    if (currentRecorder?.state === 'recording') currentRecorder.stop()
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null }
    currentRecorder = null
  }

  return { start, stop, supported: !!navigator.mediaDevices?.getUserMedia }
}

