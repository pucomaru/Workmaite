const MAX_CHUNK_MS   = 12000  // 최대 청크 길이 (말이 계속 이어져도 여기서 끊음)
const MIN_CHUNK_MS   = 1500   // 이 시간 이전에는 무음이어도 끊지 않음
const SILENCE_MS     = 900    // 이 시간 이상 무음이면 청크 종료
const SILENCE_RMS    = 0.015  // RMS 이 값 이하면 무음으로 판단
const POLL_INTERVAL  = 80     // 오디오 레벨 폴링 간격 (ms)

function getRMS(analyser) {
  const buf = new Float32Array(analyser.fftSize)
  analyser.getFloatTimeDomainData(buf)
  let sum = 0
  for (const v of buf) sum += v * v
  return Math.sqrt(sum / buf.length)
}

export function useSTT({ onResult, onSegments = null, getLang = null, getSessionId = null, getSttMode = null }) {
  let stream = null
  let active = false
  let currentRecorder = null
  let generation = 0

  async function runLoop(gen) {
    let audioCtx = null
    let analyser = null

    try {
      audioCtx = new AudioContext()
      analyser = audioCtx.createAnalyser()
      analyser.fftSize = 2048
      const source = audioCtx.createMediaStreamSource(stream)
      source.connect(analyser)
    } catch {
      // VAD 초기화 실패 시 폴백: 고정 타이머로 동작
      analyser = null
    }

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

        const startedAt = Date.now()
        let silenceSince = null
        let pollTimer = null

        function checkSilence() {
          if (recorder.state !== 'recording') return
          const elapsed = Date.now() - startedAt

          // 최대 청크 길이 초과 시 강제 종료
          if (elapsed >= MAX_CHUNK_MS) {
            clearInterval(pollTimer)
            recorder.stop()
            return
          }

          if (!analyser) return

          const rms = getRMS(analyser)
          if (rms < SILENCE_RMS) {
            if (!silenceSince) silenceSince = Date.now()
            // 최소 녹음 시간 이후 무음 지속 시 종료
            if (elapsed >= MIN_CHUNK_MS && Date.now() - silenceSince >= SILENCE_MS) {
              clearInterval(pollTimer)
              recorder.stop()
            }
          } else {
            silenceSince = null
          }
        }

        pollTimer = setInterval(checkSilence, POLL_INTERVAL)

        // analyser 없을 때 폴백: 고정 타이머
        if (!analyser) {
          setTimeout(() => { if (recorder.state === 'recording') recorder.stop() }, MAX_CHUNK_MS)
        }
      })

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

        if (!active || generation !== gen) break

        if (data.segments?.length && typeof onSegments === 'function') {
          onSegments(data.segments)
        } else if (data.text?.trim()) {
          onResult(data.text.trim(), data.text_id ?? null)
        }
      } catch (e) {
        console.warn('[STT] 전송 실패', e)
      }
    }

    if (audioCtx) audioCtx.close().catch(() => {})
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
    generation++
    if (currentRecorder?.state === 'recording') currentRecorder.stop()
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null }
    currentRecorder = null
  }

  return { start, stop, supported: !!navigator.mediaDevices?.getUserMedia }
}
