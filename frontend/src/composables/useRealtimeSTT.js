// 실시간 전사 (P5) — Web Audio PCM16(24kHz mono) → WS /ws/sessions/{id}/transcribe
// → FastAPI 프록시 → OpenAI Realtime. useSTT와 동일한 { start, stop, supported } 인터페이스에
// onPartial(부분 전사) 콜백을 추가한 드롭인 교체용 컴포저블.
import { toWsUrl } from '../api'

const SAMPLE_RATE = 24000

// ── 노이즈 게이트(VAD) ─────────────────────────────────────────────────────────
// 무음 프레임을 서버로 보내지 않아 (1) Whisper 계열의 무음 환각 전사를 줄이고 (2) STT 비용을
// 절감한다. 음성이 끝난 직후 HANGOVER_MS 동안은 계속 전송해 말끝 절단과 server_vad의 발화
// 종료 감지(silence_duration 700ms)를 보존한다.
const VAD_RMS = 0.012 // 이 RMS 미만이면 무음으로 간주
const VAD_HANGOVER_MS = 800 // 마지막 음성 이후 이 시간까지는 계속 전송

function floatTo16(float32) {
  const out = new Int16Array(float32.length)
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]))
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff
  }
  return out
}

function rms(float32) {
  let sum = 0
  for (let i = 0; i < float32.length; i++) sum += float32[i] * float32[i]
  return Math.sqrt(sum / float32.length)
}

// ── AudioWorklet 프로세서 ───────────────────────────────────────────────────────
// PCM16 변환 + VAD(노이즈 게이트)를 오디오 스레드에서 수행한다(ScriptProcessor 대체 — 메인
// 스레드 부하·프레임 드롭 감소). 전송할 프레임만 PCM16 ArrayBuffer로 port.postMessage 한다.
// 메인스레드 VAD 로직과 동일: RMS 임계 + hangover + 게이트 open 시 직전 프레임 프리롤.
const PCM_WORKLET_CODE = `
class PcmWorklet extends AudioWorkletProcessor {
  constructor(opts) {
    super()
    const o = (opts && opts.processorOptions) || {}
    this.frameSize = o.frameSize || 2048
    this.vadRms = o.vadRms || 0.012
    this.hangoverSamples = Math.round(((o.hangoverMs || 800) / 1000) * sampleRate)
    this.buf = new Float32Array(this.frameSize)
    this.fill = 0
    this.gateOpen = false
    this.lastVoiceSample = -1e15
    this.clock = 0
    this.prevPcm = null
  }
  _rms(a) { let s = 0; for (let i = 0; i < a.length; i++) s += a[i] * a[i]; return Math.sqrt(s / a.length) }
  _toPcm(f) {
    const out = new Int16Array(f.length)
    for (let i = 0; i < f.length; i++) { const s = Math.max(-1, Math.min(1, f[i])); out[i] = s < 0 ? s * 0x8000 : s * 0x7fff }
    return out
  }
  _flush() {
    const level = this._rms(this.buf)
    const pcm = this._toPcm(this.buf)
    this.clock += this.frameSize
    if (level >= this.vadRms) {
      if (!this.gateOpen && this.prevPcm) this.port.postMessage(this.prevPcm.buffer)
      this.gateOpen = true
      this.lastVoiceSample = this.clock
      this.port.postMessage(pcm.buffer)
    } else if (this.gateOpen && this.clock - this.lastVoiceSample < this.hangoverSamples) {
      this.port.postMessage(pcm.buffer)
    } else {
      this.gateOpen = false
    }
    this.prevPcm = pcm
  }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0]
    if (!ch) return true
    let i = 0
    while (i < ch.length) {
      const n = Math.min(this.frameSize - this.fill, ch.length - i)
      this.buf.set(ch.subarray(i, i + n), this.fill)
      this.fill += n
      i += n
      if (this.fill >= this.frameSize) { this._flush(); this.fill = 0 }
    }
    return true
  }
}
registerProcessor('pcm-worklet', PcmWorklet)
`
let _workletUrl = null
function workletUrl() {
  if (!_workletUrl && typeof Blob !== 'undefined' && typeof URL !== 'undefined') {
    _workletUrl = URL.createObjectURL(new Blob([PCM_WORKLET_CODE], { type: 'application/javascript' }))
  }
  return _workletUrl
}

export function useRealtimeSTT({
  onResult,
  onPartial = null,
  onError = null,
  getLang = null,
  getSessionId = null,
  getModel = null,
  // 종료 시 임시 수집한 전체 녹음(Blob)을 전달 — 화자분리(diarization)용. 없으면 녹음 안 함.
  onAudioComplete = null,
}) {
  let stream = null
  let audioCtx = null
  let node = null
  let sink = null
  let highpass = null
  let compressor = null
  let ws = null
  let active = false
  let partial = '' // 부분 전사 누적 (OpenAI delta는 증분)
  let recorder = null // MediaRecorder — 전체 오디오 임시 수집(화자분리 입력)
  let chunks = []
  let recMime = ''

  function cleanupAudio() {
    // recorder가 정상 종료 경로(finalizeRecorder)를 못 거친 비정상 종료 대비 — blob 미전달
    try {
      if (recorder && recorder.state !== 'inactive') recorder.stop()
    } catch {
      /* noop */
    }
    recorder = null
    chunks = []
    for (const n of [node, sink, highpass, compressor]) {
      try {
        if (n) n.disconnect()
      } catch {
        /* noop */
      }
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
    node = sink = highpass = compressor = audioCtx = null
  }

  // MediaRecorder를 멈추고 마지막 청크까지 모아 Blob을 전달한 뒤 오디오를 정리한다.
  // 트랙을 먼저 끊으면 마지막 청크가 잘리므로, onstop(=flush 완료) 이후에 cleanupAudio한다.
  function finalizeRecorder() {
    if (!recorder) {
      cleanupAudio()
      onAudioComplete?.(null)
      return
    }
    const rec = recorder
    recorder = null
    rec.onstop = () => {
      const blob = chunks.length ? new Blob(chunks, { type: recMime || 'audio/webm' }) : null
      chunks = []
      cleanupAudio()
      onAudioComplete?.(blob)
    }
    try {
      rec.stop()
    } catch {
      cleanupAudio()
      onAudioComplete?.(null)
    }
  }

  async function start() {
    if (active) return
    const sessionId = typeof getSessionId === 'function' ? getSessionId() : null
    if (!sessionId) throw new Error('세션이 필요합니다.')

    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    })
    // 전체 오디오를 임시 수집(연속 원음 — VAD/필터 전 단계)해 종료 시 화자분리에 사용한다.
    if (typeof onAudioComplete === 'function' && window.MediaRecorder) {
      chunks = []
      recMime = ['audio/webm;codecs=opus', 'audio/webm'].find(
        m => MediaRecorder.isTypeSupported?.(m),
      )
      try {
        recorder = recMime
          ? new MediaRecorder(stream, { mimeType: recMime })
          : new MediaRecorder(stream)
        recorder.ondataavailable = e => {
          if (e.data && e.data.size) chunks.push(e.data)
        }
        recorder.start(5000) // 5초 단위 청크 — 종료 시 마지막 청크까지 안전 수집
      } catch {
        recorder = null
      }
    }

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

    // 마이크 → [전처리 체인] → (워크릿/스크립트프로세서) → PCM16 프레임 WS 전송.
    const source = audioCtx.createMediaStreamSource(stream)

    // 전처리: highpass(85Hz, HVAC/저주파 럼블 제거) → compressor(마이크 레벨 편차 완화)
    highpass = audioCtx.createBiquadFilter()
    highpass.type = 'highpass'
    highpass.frequency.value = 85

    compressor = audioCtx.createDynamicsCompressor()
    compressor.threshold.value = -28
    compressor.knee.value = 24
    compressor.ratio.value = 3
    compressor.attack.value = 0.003
    compressor.release.value = 0.25

    // destination까지 그래프가 연결돼야 노드가 렌더링되므로 gain=0 sink로 무음 출력(피드백 방지).
    sink = audioCtx.createGain()
    sink.gain.value = 0
    sink.connect(audioCtx.destination)

    // 1순위: AudioWorklet (오디오 스레드에서 VAD+PCM16 변환, ScriptProcessor 비권장 경고 제거)
    let usedWorklet = false
    const url = workletUrl()
    if (audioCtx.audioWorklet && url) {
      try {
        await audioCtx.audioWorklet.addModule(url)
        node = new AudioWorkletNode(audioCtx, 'pcm-worklet', {
          numberOfInputs: 1,
          numberOfOutputs: 1,
          processorOptions: {
            frameSize: 2048,
            vadRms: VAD_RMS,
            hangoverMs: VAD_HANGOVER_MS,
          },
        })
        node.port.onmessage = ev => {
          if (!active || !ws || ws.readyState !== WebSocket.OPEN) return
          ws.send(ev.data) // PCM16 ArrayBuffer (전송 대상 프레임만 도착)
        }
        usedWorklet = true
      } catch {
        node = null
      }
    }

    // 폴백: AudioWorklet 미지원 환경 → 기존 ScriptProcessor + 메인스레드 VAD
    if (!usedWorklet) {
      node = audioCtx.createScriptProcessor(4096, 1, 1)
      let lastVoiceMs = 0
      let gateOpen = false
      let prevFrame = null
      node.onaudioprocess = e => {
        if (!active || !ws || ws.readyState !== WebSocket.OPEN) return
        const input = e.inputBuffer.getChannelData(0)
        const level = rms(input)
        const nowMs = audioCtx.currentTime * 1000
        const pcm = floatTo16(input)
        if (level >= VAD_RMS) {
          if (!gateOpen && prevFrame) ws.send(prevFrame.buffer)
          gateOpen = true
          lastVoiceMs = nowMs
          ws.send(pcm.buffer)
        } else if (gateOpen && nowMs - lastVoiceMs < VAD_HANGOVER_MS) {
          ws.send(pcm.buffer)
        } else {
          gateOpen = false
        }
        prevFrame = pcm
      }
    }

    source.connect(highpass)
    highpass.connect(compressor)
    compressor.connect(node)
    node.connect(sink)
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
    // recorder를 flush한 뒤 Blob 전달 + 오디오 정리 (cleanupAudio를 내부에서 호출)
    finalizeRecorder()
  }

  return {
    start,
    stop,
    supported: !!(navigator.mediaDevices?.getUserMedia && window.AudioContext),
  }
}
