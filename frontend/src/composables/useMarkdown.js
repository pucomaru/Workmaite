import { marked } from 'marked'
import DOMPurify from 'dompurify'

/**
 * AI 에이전트 출력을 안전하게 Markdown → HTML 변환합니다.
 * DOMPurify로 XSS를 방지합니다.
 */
export function renderMd(text) {
  if (!text) return ''
  const normalized = text.replace(/\r\n/g, '\n').replace(/([^\n])\n(#{1,6} )/g, '$1\n\n$2')
  const raw = marked.parse(normalized, { breaks: true })
  return DOMPurify.sanitize(raw)
}
