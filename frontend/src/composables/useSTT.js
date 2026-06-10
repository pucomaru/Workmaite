// ── HTTP 청크 방식 상수 (gcapi / whisperapi 모드) ──────────────────
const MAX_CHUNK_MS  = 12000
const MIN_CHUNK_MS  = 1500
const SILENCE_MS    = 900
const SILENCE_RMS   = 0.015
const POLL_INTERVAL = 80

function getRMS(analyser) {
  const buf = new Float32Array(analyser.fftSize)
  analyser.getFloatTimeDomainData(buf)
  let sum = 0
  for (const v of buf) sum += v * v
  return Math.sqrt(sum / buf.length)
}

function parseWLKTime(t) {
  if (t == null) return 0
  const parts = String(t).split(':').map(Number)
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2]
  if (parts.length === 2) return parts[0] * 60 + parts[1]
  return parts[0] || 0
}

async function saveToDB(sessionId, segments) {
  try {
    const res = await fetch('/api/stt/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, segments }),
    })
    const data = await res.json()
    return data.segments ?? segments
  } catch { return segments }
}

export function useSTT({ onResult, onSegments = null, getLang = null, getSessionId = null, getSttMode = null }) {
  let stream = null
  let active = false
  let currentRecorder = null
  let currentWS = null
  let generation = 0

  // ── WhisperLiveKit WebSocket 모드 ──────────────────────────────
  async function runWLKLoop(gen, lang) {
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${protocol}://${location.host}/wlk/asr?language=${lang}`)
    currentWS = ws
    ws.binaryType = 'arraybuffer'

    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus' : 'audio/webm'
    const recorder = new MediaRecorder(stream, { mimeType })
    currentRecorder = recorder

    // WLK는 누적 전체 lines를 매 메시지마다 보냄 → 신규 라인만 처리
    let processedCount = 0
    let lastData = null

    recorder.ondataavailable = async (e) => {
      if (e.data.size > 0 && ws.readyState === WebSocket.OPEN) {
        ws.send(await e.data.arrayBuffer())
      }
    }

    async function flushSegments(lines, bufferText = '') {
      const newLines = lines.slice(processedCount)
      processedCount = lines.length

      const toProcess = newLines.map(l => ({
        speaker: normalizeSpeaker(l.speaker),
        text:    (l.text ?? '').trim(),
        start:   parseWLKTime(l.beg ?? l.start),
        end:     parseWLKTime(l.end),
      })).filter(s => s.text)

      // 녹음 종료 시 buffer 잔여분을 마지막 세그먼트로 추가
      const trimmed = (bufferText ?? '').trim()
      if (trimmed) {
        toProcess.push({ speaker: normalizeSpeaker(null), text: trimmed, start: 0, end: 0 })
      }

      if (!toProcess.length) return

      const sessionId = typeof getSessionId === 'function' ? getSessionId() : null
      const saved = sessionId ? await saveToDB(sessionId, toProcess) : toProcess

      if (typeof onSegments === 'function') {
        onSegments(saved)
      } else if (saved[0]?.text) {
        onResult(saved.map(s => s.text).join(' '), saved[0]?.id ?? null)
      }
    }

    ws.onmessage = async (event) => {
      if (!active || generation !== gen) return
      let data
      try { data = JSON.parse(event.data) } catch { return }

      if (data.type === 'config' || data.type === 'ready_to_stop') return
      lastData = data

      await flushSegments(data.lines ?? [])
    }

    await new Promise(resolve => {
      ws.onopen  = () => { recorder.start(200) }
      ws.onerror = () => resolve()
      ws.onclose = async () => {
        // 종료 시점에 buffer에 남은 텍스트 저장
        if (lastData?.buffer?.trim()) {
          await flushSegments(lastData.lines ?? [], lastData.buffer)
        }
        resolve()
      }
    })
    currentWS = null
  }

  // "SPEAKER_00" → "1", "SPEAKER_01" → "2", null/"" → "1"
  function normalizeSpeaker(raw) {
    if (!raw) return '1'
    const m = String(raw).match(/(\d+)$/)
    return m ? String(parseInt(m[1], 10) + 1) : String(raw)
  }

  function stopWLK() {
    if (currentRecorder?.state === 'recording') currentRecorder.stop()
    if (currentWS && currentWS.readyState === WebSocket.OPEN) currentWS.close()
  }

  // ── HTTP 청크 방식 (gcapi / whisperapi 모드) ───────────────────
  async function runLoop(gen) {
    let audioCtx = null
    let analyser = null
    try {
      audioCtx = new AudioContext()
      analyser = audioCtx.createAnalyser()
      analyser.fftSize = 2048
      audioCtx.createMediaStreamSource(stream).connect(analyser)
    } catch { analyser = null }

    while (active && stream && generation === gen) {
      const chunks = []
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus' : 'audio/webm'
      const recorder = new MediaRecorder(stream, { mimeType })
      currentRecorder = recorder
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data) }

      await new Promise(resolve => {
        recorder.onstop = resolve
        recorder.start()
        const startedAt = Date.now()
        let silenceSince = null
        const pollTimer = setInterval(() => {
          if (recorder.state !== 'recording') { clearInterval(pollTimer); return }
          const elapsed = Date.now() - startedAt
          if (elapsed >= MAX_CHUNK_MS) { clearInterval(pollTimer); recorder.stop(); return }
          if (!analyser) return
          const rms = getRMS(analyser)
          if (rms < SILENCE_RMS) {
            if (!silenceSince) silenceSince = Date.now()
            if (elapsed >= MIN_CHUNK_MS && Date.now() - silenceSince >= SILENCE_MS) {
              clearInterval(pollTimer); recorder.stop()
            }
          } else { silenceSince = null }
        }, POLL_INTERVAL)
        if (!analyser) setTimeout(() => { if (recorder.state === 'recording') recorder.stop() }, MAX_CHUNK_MS)
      })

      if (!active || generation !== gen) break
      const blob = new Blob(chunks, { type: mimeType })
      if (blob.size < 500) continue

      const rawLang = typeof getLang === 'function' ? getLang() : 'ko'
      const lang = rawLang.split('-')[0].toLowerCase()
      const sttMode = typeof getSttMode === 'function' ? getSttMode() : 'localwhisper'
      const sessionId = typeof getSessionId === 'function' ? getSessionId() : null

      const formData = new FormData()
      formData.append('audio', blob, 'audio.webm')
      formData.append('lang', lang)
      formData.append('stt_mode', sttMode)
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
      } catch (e) { console.warn('[STT] 전송 실패', e) }
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
      const sttMode = typeof getSttMode === 'function' ? getSttMode() : 'localwhisper'
      if (sttMode === 'localwhisper') {
        const rawLang = typeof getLang === 'function' ? getLang() : 'ko'
        const lang = rawLang.split('-')[0].toLowerCase()
        runWLKLoop(myGen, lang)
      } else {
        runLoop(myGen)
      }
    } catch (e) {
      active = false
      console.warn('[STT] 마이크 권한 없음', e)
      throw e
    }
  }

  function stop() {
    active = false
    generation++
    stopWLK()
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null }
    currentRecorder = null
  }

  return { start, stop, supported: !!navigator.mediaDevices?.getUserMedia }
}
