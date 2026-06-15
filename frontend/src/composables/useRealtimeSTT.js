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
}) {
  // ── 세션 수명(일시정지/재개에도 유지) 자원 ──────────────────────────────────
  // 마이크 스트림은 녹음 세션 동안 유지한다(일시정지에서 끊지 않아 재개 시 빠르게 이어감).
  let stream = null

  // ── 구간 수명(일시정지마다 해제·재개마다 재생성) 자원 ──────────────────────
  let audioCtx = null
  let node = null
  let sink = null
  let highpass = null
  let compressor = null
  let analyser = null // 실시간 오디오 스펙트럼(rec-wave 시각화)용
  let freqData = null
  let ws = null
  let active = false
  let partial = '' // 부분 전사 누적 (OpenAI delta는 증분)

  // 실시간 경로(오디오 그래프 + WS)만 해제한다. 마이크 스트림은 건드리지 않아 일시정지 후
  // 재개 시 같은 마이크를 그대로 이어 쓸 수 있게 한다.
  function cleanupSegment() {
    for (const n of [node, sink, highpass, compressor, analyser]) {
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
    node = sink = highpass = compressor = analyser = freqData = audioCtx = null
  }

  // 마이크 스트림 트랙을 정지(마이크 표시등 해제).
  function releaseStream() {
    if (stream) {
      stream.getTracks().forEach(t => t.stop())
      stream = null
    }
  }

  // 기록 종료/언마운트 시 모든 자원(오디오 그래프·WS·마이크)을 즉시 해제한다.
  function release() {
    active = false
    try {
      if (ws && ws.readyState === WebSocket.OPEN) ws.close()
    } catch {
      /* noop */
    }
    ws = null
    cleanupSegment()
    releaseStream()
  }

  // 실시간 오디오 스펙트럼 — n개 막대의 정규화 크기(0~1) 배열. 녹음 중이 아니면 null.
  function getWaveLevels(n) {
    if (!analyser || !freqData) return null
    analyser.getByteFrequencyData(freqData)
    // 음성 에너지가 몰린 하위 ~70% 대역만 사용(초고역 잡음 제외)
    const usable = Math.max(n, Math.floor(freqData.length * 0.7))
    const per = Math.max(1, Math.floor(usable / n))
    const out = new Array(n)
    for (let i = 0; i < n; i++) {
      let sum = 0
      const start = i * per
      for (let j = 0; j < per; j++) sum += freqData[start + j] || 0
      out[i] = Math.min(1, (sum / per / 255) * 1.4) // 정규화 + 약간 부스트
    }
    return out
  }

  async function start() {
    if (active) return
    const sessionId = typeof getSessionId === 'function' ? getSessionId() : null
    if (!sessionId) throw new Error('세션이 필요합니다.')

    // 마이크 스트림은 세션 동안 유지(일시정지에도 끊지 않음) — 재개 시 재요청하지 않는다.
    if (!stream) {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
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
        // 문장 단위 확정 — partial은 후속 partial 메시지(남은 꼬리)가 갱신한다.
        // corrected: 전문용어 교정 에이전트가 이 문장을 바꿨는지 여부(UI 글로우용)
        if (data.text?.trim())
          onResult(data.text.trim(), data.text_id ?? null, {
            corrected: !!data.corrected,
          })
      } else if (data.type === 'error') {
        onError?.(data.message || '실시간 전사 오류')
      }
    }
    ws.onclose = () => {
      // 예기치 않은 WS 종료: 실시간 경로(오디오 그래프)만 정리하고 마이크 스트림은 유지한다.
      if (active) {
        active = false
        cleanupSegment()
      }
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

    // 실시간 스펙트럼 분석용 — compressor 출력에서 분기(전사 경로와 독립). destination 연결 불필요.
    analyser = audioCtx.createAnalyser()
    analyser.fftSize = 256
    analyser.smoothingTimeConstant = 0.7
    freqData = new Uint8Array(analyser.frequencyBinCount)
    compressor.connect(analyser)

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

  // finalize=false(일시정지): 실시간 경로(오디오 그래프+WS)만 해제하고 마이크는 유지 → 재개
  // 시 빠르게 이어간다. finalize=true(기록 종료): 마이크까지 완전히 해제한다.
  function stop({ finalize = false } = {}) {
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

    cleanupSegment()
    if (finalize) releaseStream() // 기록 종료 시 마이크 표시등 해제
  }

  return {
    start,
    stop,
    release,
    getWaveLevels,
    supported: !!(navigator.mediaDevices?.getUserMedia && window.AudioContext),
  }
}
