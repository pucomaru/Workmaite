const CHUNK_MS = 4000

export function useSTT({ onResult, onSegments = null, getLang = null, getSessionId = null, getSttMode = null }) {
  let stream = null
  let active = false
  let currentRecorder = null
  let generation = 0   // 루프 세대 — stop/start 시 증가시켜 이전 루프 결과를 폐기

  async function runLoop(gen) {
    while (active && stream && generation === gen) {
      const chunks = []
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm'

      const recorder = new MediaRecorder(stream, { mimeType })
      currentRecorder = recorder

      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data) }

      await new Promise(resolve => {
        recorder.onstop = resolve
        recorder.start()
        setTimeout(() => { if (recorder.state === 'recording') recorder.stop() }, CHUNK_MS)
      })

      // stop()이 이미 호출됐거나 새 세대가 시작됐으면 결과 버림
      if (!active || generation !== gen) break

      const blob = new Blob(chunks, { type: mimeType })
      if (blob.size < 500) continue

      const rawLang = typeof getLang === 'function' ? getLang() : 'ko'
      const lang = rawLang.split('-')[0].toLowerCase()
      const sttMode = typeof getSttMode === 'function' ? getSttMode() : 'localwhisper'

      const formData = new FormData()
      formData.append('audio', blob, 'audio.webm')
      formData.append('lang', lang)
      formData.append('stt_mode', sttMode)

      const sessionId = typeof getSessionId === 'function' ? getSessionId() : null
      if (sessionId) formData.append('session_id', String(sessionId))

      try {
        const res = await fetch('/api/stt/transcribe', { method: 'POST', body: formData })
        const data = await res.json()

        // fetch 완료 후 다시 세대 체크
        if (!active || generation !== gen) break

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
    generation++
    const myGen = generation
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      runLoop(myGen)
    } catch (e) {
      active = false
      console.warn('[STT] 마이크 권한 없음', e)
      throw e
    }
  }

  function stop() {
    active = false
    generation++   // 진행 중인 루프가 결과를 처리하지 못하도록 세대 교체
    if (currentRecorder?.state === 'recording') currentRecorder.stop()
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null }
    currentRecorder = null
  }

  return { start, stop, supported: !!navigator.mediaDevices?.getUserMedia }
}
