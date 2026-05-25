/**
 * useSTT — Web Speech API 기반 한국어 실시간 STT
 * - 최종 확정된 문장(isFinal)만 onResult 콜백으로 반환
 * - 마이크 off 시 중단, on 시 재시작
 */
export function useSTT({ onResult, getLang = null }) {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
  if (!SpeechRecognition) return { start: () => {}, stop: () => {}, supported: false }

  let recognition = null
  let active = false

  function build() {
    const r = new SpeechRecognition()
    r.lang = typeof getLang === 'function' ? getLang() : 'ko-KR'
    r.continuous = true
    r.interimResults = false  // 최종 결과만

    r.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) {
          const text = e.results[i][0].transcript.trim()
          if (text) onResult(text)
        }
      }
    }

    r.onend = () => {
      // 활성 상태면 자동 재시작 — 새 인스턴스 생성으로 중복 결과 방지
      if (active) {
        recognition = build()
        try { recognition.start() } catch (_) {}
      }
    }

    r.onerror = (e) => {
      if (e.error === 'no-speech' || e.error === 'audio-capture') return
      if (e.error === 'not-allowed') {
        active = false
        console.warn('[STT] 마이크 권한 없음')
      }
    }

    return r
  }

  function start() {
    if (active) return
    active = true
    recognition = build()
    try { recognition.start() } catch (_) {}
  }

  function stop() {
    active = false
    if (recognition) {
      try { recognition.stop() } catch (_) {}
      recognition = null
    }
  }

  return { start, stop, supported: true }
}
