// dead-css.tsv 목록의 클래스만 참조하는 CSS 규칙을 제거한다.
// 셀렉터 목록에 살아있는 셀렉터가 섞여 있으면 죽은 셀렉터만 떼어낸다.
import { readFileSync, writeFileSync } from 'fs'
import { join } from 'path'

const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Z]:)/, '$1')
const tsv = readFileSync(join(ROOT, 'scripts', 'dead-css.tsv'), 'utf8')
  .trim()
  .split('\n')

const deadByFile = new Map() // file -> Set(cls)
for (const line of tsv) {
  const [, cls, file] = line.split('\t')
  if (!deadByFile.has(file)) deadByFile.set(file, new Set())
  deadByFile.get(file).add(cls)
}

function selectorIsDead(sel, deadSet) {
  const classes = [...sel.matchAll(/\.([a-zA-Z_][\w-]*)/g)].map(m => m[1])
  return classes.some(c => deadSet.has(c))
}

// 중괄호 깊이를 추적하며 leaf 규칙(중첩 블록 없는 selector{...})을 찾아 제거
function removeDead(css, deadSet) {
  let out = ''
  let i = 0
  while (i < css.length) {
    // 주석 통과
    if (css.startsWith('/*', i)) {
      const end = css.indexOf('*/', i + 2)
      const j = end === -1 ? css.length : end + 2
      out += css.slice(i, j)
      i = j
      continue
    }
    const brace = css.indexOf('{', i)
    if (brace === -1) {
      out += css.slice(i)
      break
    }
    // 셀렉터 추출 (직전 '}' 또는 ';' 이후부터)
    let selStart = i
    const selector = css.slice(selStart, brace)
    if (selector.trimStart().startsWith('@')) {
      // @media 등 — 헤더만 쓰고 내부 재귀
      const inner = matchBlock(css, brace)
      out += css.slice(selStart, brace + 1) + removeDead(css.slice(brace + 1, inner), deadSet) + '}'
      i = inner + 1
      continue
    }
    const end = matchBlock(css, brace) // leaf 규칙 가정 (이 코드베이스는 중첩 없음)
    const body = css.slice(brace + 1, end)
    const parts = selector.split(',')
    const alive = parts.filter(p => !selectorIsDead(p, deadSet))
    if (alive.length === parts.length) {
      out += css.slice(selStart, end + 1)
    } else if (alive.length > 0) {
      out += alive.join(',') + '{' + body + '}'
    } // alive 0개 → 규칙 전체 삭제
    i = end + 1
  }
  return out
}

function matchBlock(css, openIdx) {
  let depth = 0
  for (let i = openIdx; i < css.length; i++) {
    if (css[i] === '{') depth++
    else if (css[i] === '}') {
      depth--
      if (depth === 0) return i
    }
  }
  return css.length - 1
}

function tidy(css) {
  return css.replace(/@[^{}]+\{\s*\}/g, '').replace(/\n{3,}/g, '\n\n')
}

let totalFiles = 0
for (const [file, deadSet] of deadByFile) {
  const txt = readFileSync(file, 'utf8')
  let next
  if (file.endsWith('.vue')) {
    next = txt.replace(
      /(<style[^>]*>)([\s\S]*?)(<\/style>)/g,
      (_, open, css, close) => open + tidy(removeDead(css, deadSet)) + close,
    )
  } else {
    next = tidy(removeDead(txt, deadSet))
  }
  if (next !== txt) {
    writeFileSync(file, next)
    totalFiles++
    console.log(`정리: ${file.replace(/.*src[\\/]/, 'src/')} (-${txt.length - next.length} chars)`)
  }
}
console.log(`\n${totalFiles}개 파일 수정 완료`)
