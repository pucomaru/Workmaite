// 색상 리터럴 → CSS 변수 치환.
// 대상: .css 파일 전체, .vue 파일의 <style> 블록만 (템플릿/SVG 속성은 var() 미지원이라 제외).
// CSS 변수 정의 라인(--x: ...)은 건드리지 않는다 (자기참조 방지).
import { readFileSync, writeFileSync, readdirSync, statSync } from 'fs'
import { join } from 'path'

const SRC = new URL('../src', import.meta.url).pathname.replace(/^\/([A-Z]:)/, '$1')

const MAP = {
  // 기존 :root 변수와 동일한 값
  '#3b82f6': 'var(--accent)',
  '#60a5fa': 'var(--accent-light)',
  '#ef4444': 'var(--danger)',
  '#f59e0b': 'var(--warning)',
  '#10b981': 'var(--success)',
  '#64748b': 'var(--text-muted)',
  '#94a3b8': 'var(--dark-muted)',
  '#0f172a': 'var(--dark-bg)',
  '#1e293b': 'var(--dark-card)',
  '#334155': 'var(--dark-border)',
  '#1e3a5f': 'var(--primary)',
  '#f8fafc': 'var(--surface)',
  '#f1f5f9': 'var(--surface-2)',
  '#1a202c': 'var(--text)',
  '#f0f4f8': 'var(--bg)',
  // 신규 보조 팔레트
  '#6366f1': 'var(--indigo)',
  '#93c5fd': 'var(--accent-soft)',
  '#1d4ed8': 'var(--accent-strong)',
  '#eff6ff': 'var(--accent-bg)',
  '#dbeafe': 'var(--accent-bg-2)',
  '#cbd5e1': 'var(--dark-text-2)',
  '#fef3c7': 'var(--warning-bg)',
  '#d97706': 'var(--warning-text)',
  '#a78bfa': 'var(--violet-soft)',
  '#f87171': 'var(--danger-soft)',
  // 화이트 오버레이 (긴 것부터 — .12가 .1에 잡아먹히지 않게)
  'rgba(255,255,255,.03)': 'var(--white-03)',
  'rgba(255,255,255,.04)': 'var(--white-04)',
  'rgba(255,255,255,.05)': 'var(--white-05)',
  'rgba(255,255,255,.06)': 'var(--white-06)',
  'rgba(255,255,255,.07)': 'var(--white-07)',
  'rgba(255,255,255,.08)': 'var(--white-08)',
  'rgba(255,255,255,.09)': 'var(--white-09)',
  'rgba(255,255,255,.12)': 'var(--white-12)',
  'rgba(255,255,255,.15)': 'var(--white-15)',
  'rgba(255,255,255,.18)': 'var(--white-18)',
  'rgba(255,255,255,.1)': 'var(--white-10)',
}
// #e2e8f0 — 값은 같지만 의미가 둘(라이트 보더 / 다크 텍스트): 파일 컨텍스트로 구분
const E2 = '#e2e8f0'

function walk(dir, exts, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p, exts, out)
    else if (exts.some(e => p.endsWith(e))) out.push(p)
  }
  return out
}

const counts = {}
function convert(css, e2var) {
  return css
    .split('\n')
    .map(line => {
      if (/^\s*--[\w-]+\s*:/.test(line)) return line // 변수 정의 라인 보호
      let l = line
      // hex는 뒤에 16진수가 더 붙지 않을 때만 (#3b82f6aa 같은 8자리 오인 방지)
      for (const [lit, v] of Object.entries(MAP)) {
        if (!l.includes(lit)) continue
        const re = lit.startsWith('#')
          ? new RegExp(lit + '(?![0-9a-fA-F])', 'g')
          : new RegExp(lit.replace(/[().]/g, '\\$&') + '(?!\\d)', 'g')
        l = l.replace(re, () => {
          counts[lit] = (counts[lit] || 0) + 1
          return v
        })
      }
      if (e2var && l.includes(E2)) {
        l = l.replace(new RegExp(E2 + '(?![0-9a-fA-F])', 'g'), () => {
          counts[E2] = (counts[E2] || 0) + 1
          return e2var
        })
      }
      return l
    })
    .join('\n')
}

let changed = 0
for (const f of walk(SRC, ['.css'])) {
  const e2var = f.includes('archive') ? 'var(--dark-text)' : 'var(--border)'
  const txt = readFileSync(f, 'utf8')
  const next = convert(txt, e2var)
  if (next !== txt) {
    writeFileSync(f, next)
    changed++
  }
}
for (const f of walk(SRC, ['.vue'])) {
  const txt = readFileSync(f, 'utf8')
  const next = txt.replace(
    /(<style[^>]*>)([\s\S]*?)(<\/style>)/g,
    (_, open, css, close) => open + convert(css, null) + close,
  )
  if (next !== txt) {
    writeFileSync(f, next)
    changed++
  }
}

const total = Object.values(counts).reduce((a, b) => a + b, 0)
for (const [k, v] of Object.entries(counts).sort((a, b) => b[1] - a[1]))
  console.log(`${k} → ${v}회`)
console.log(`\n${changed}개 파일, 총 ${total}회 치환`)
