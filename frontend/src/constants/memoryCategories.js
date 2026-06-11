/**
 * AI 운영 메모리 카테고리 공통 상수
 * MeetingHomePage.vue, HyeanAgent.vue, TacitKnowledgePage.vue 등에서 공유
 */
export const MEMORY_CATEGORIES = [
  { value: 'report_standard',  label: '📋 보고서 기준',  color: '#dbeafe', border: '#93c5fd', text: '#1d4ed8' },
  { value: 'agenda_standard',  label: '📌 아젠다 기준',  color: '#fef9c3', border: '#fde047', text: '#854d0e' },
  { value: 'todo_standard',    label: '✅ 아젠다 기준',  color: '#dcfce7', border: '#86efac', text: '#166534' },
  { value: 'meeting_standard', label: '🎙 회의 기준',    color: '#f3e8ff', border: '#d8b4fe', text: '#6b21a8' },
]
