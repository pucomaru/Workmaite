// 실시간 전사 (P5) — Web Audio PCM16(24kHz mono) → WS /ws/sessions/{id}/transcribe
// → FastAPI 프록시 → OpenAI Realtime. useSTT와 동일한 { start, stop, supported } 인터페이스에
// onPartial(부분 전사) 콜백을 추가한 드롭인 교체용 컴포저블.
import { toWsUrl } from '../api'

const SAMPLE_RATE = 24000

function floatTo16(float32) {
  const out = new Int16Array(float32.length)
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]))
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff
  }
  return out
}

export function useRealtimeSTT({
  onResult,
  onPartial = null,
  onError = null,
  getLang = null,
  getSessionId = null,
  getModel = null,
}) {
  let stream = null
  let audioCtx = null
  let node = null
  let sink = null
  let ws = null
  let active = false
  let partial = '' // 부분 전사 누적 (OpenAI delta는 증분)

  function cleanupAudio() {
    try {
      if (node) node.disconnect()
    } catch {
      /* noop */
    }
    try {
      if (sink) sink.disconnect()
    } catch {
      /* noop */
    }
    try {
      if (audioCtx) audioCtx.close()
    } catch {
      /* noop */
    }
    if (stream) {
      stream.getTracks().forEach(t => t.stop())
      stream = null
    }
    node = sink = audioCtx = null
  }

  async function start() {
    if (active) return
    const sessionId = typeof getSessionId === 'function' ? getSessionId() : null
    if (!sessionId) throw new Error('세션이 필요합니다.')

    stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    })
    audioCtx = new AudioContext({ sampleRate: SAMPLE_RATE })
    // 사용자 제스처로 생성해도 suspended일 수 있다 — resume 안 하면 ScriptProcessor의
    // onaudioprocess가 돌지 않아 오디오가 전혀 전송되지 않는다(녹음 버튼만 바뀌고 전사 0).
    if (audioCtx.state === 'suspended') await audioCtx.resume()
    active = true
    partial = ''

    // WS 연결 (toWsUrl이 token 쿼리 자동 부착)
    ws = new WebSocket(toWsUrl(`/ws/sessions/${sessionId}/transcribe`))
    ws.binaryType = 'arraybuffer'

    await new Promise((resolve, reject) => {
      ws.onopen = () => {
        const lang = typeof getLang === 'function' ? getLang() : 'ko'
        const model = typeof getModel === 'function' ? getModel() : undefined
        ws.send(JSON.stringify({ type: 'start', lang, model }))
        resolve()
      }
      ws.onerror = () => reject(new Error('실시간 전사 서버에 연결하지 못했습니다.'))
    })

    ws.onmessage = ev => {
      let data
      try {
        data = JSON.parse(ev.data)
      } catch {
        return
      }
      if (data.type === 'partial') {
        // 백엔드가 전체 라이브 텍스트(확정전 버퍼+발화중)를 보낸다 → 교체(누적 아님)
        partial = data.text || ''
        onPartial?.(partial)
      } else if (data.type === 'final') {
        // 문장 단위 확정 — partial은 후속 partial 메시지(남은 꼬리)가 갱신한다
        if (data.text?.trim()) onResult(data.text.trim(), data.text_id ?? null)
      } else if (data.type === 'error') {
        onError?.(data.message || '실시간 전사 오류')
      }
    }
    ws.onclose = () => {
      if (active) cleanupAudio()
    }

    // 마이크 → PCM16 프레임 전송. ScriptProcessor는 destination 연결이 필요하므로
    // gain=0 sink로 무음 출력(피드백 방지)하면서 onaudioprocess를 살린다.
    const source = audioCtx.createMediaStreamSource(stream)
    node = audioCtx.createScriptProcessor(4096, 1, 1)
    node.onaudioprocess = e => {
      if (!active || !ws || ws.readyState !== WebSocket.OPEN) return
      const pcm = floatTo16(e.inputBuffer.getChannelData(0))
      ws.send(pcm.buffer)
    }
    sink = audioCtx.createGain()
    sink.gain.value = 0
    source.connect(node)
    node.connect(sink)
    sink.connect(audioCtx.destination)
  }

  function stop() {
    active = false
    try {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'stop' }))
        ws.close()
      }
    } catch {
      /* noop */
    }
    ws = null
    cleanupAudio()
  }

  return {
    start,
    stop,
    supported: !!(navigator.mediaDevices?.getUserMedia && window.AudioContext),
  }
}
