const CHUNK_MS = 4000

export function useSTT({ onResult, getLang = null }) {
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

      const lang = typeof getLang === 'function' ? getLang() : 'ko'
      const formData = new FormData()
      formData.append('audio', blob, 'audio.webm')
      formData.append('lang', lang)

      try {
        const res = await fetch('/api/stt/transcribe', { method: 'POST', body: formData })
        const data = await res.json()
        if (data.text?.trim()) onResult(data.text.trim())
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
    }
  }

  function stop() {
    active = false
    if (currentRecorder?.state === 'recording') currentRecorder.stop()
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null }
    currentRecorder = null
  }

  return { start, stop, supported: true }
}
