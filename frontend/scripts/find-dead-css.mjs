// 데드 CSS 스캐너 v2
// - .css 파일 정의: 전체 .vue/.js에서 사용 검색 (전역 클래스)
// - .vue <style> 정의: 해당 파일의 템플릿/스크립트에서만 검색 (scoped 가정)
// - Transition 파생(-enter-*/-leave-*), 동적 prefix 조립(`x-${...}`), 라이브러리 클래스 오탐 제외
import { readFileSync, readdirSync, statSync, writeFileSync } from 'fs'
import { join } from 'path'

const SRC = new URL('../src', import.meta.url).pathname.replace(/^\/([A-Z]:)/, '$1')

function walk(dir, exts, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) walk(p, exts, out)
    else if (exts.some(e => p.endsWith(e))) out.push(p)
  }
  return out
}

function classesOf(css) {
  const noComments = css.replace(/\/\*[\s\S]*?\*\//g, '')
  const selectors = noComments.split('}').map(b => b.split('{')[0]).join(',')
  return [...selectors.matchAll(/\.([a-zA-Z_][\w-]*)/g)].map(m => m[1])
}

const TRANSITION_SUFFIX = /-(enter|leave)(-(active|from|to))?$/
const LIB_CLASSES = new Set(['ProseMirror'])

function isDeadIn(cls, haystack) {
  if (haystack.includes(cls)) return false
  if (LIB_CLASSES.has(cls)) return false
  if (TRANSITION_SUFFIX.test(cls) && haystack.includes(cls.replace(TRANSITION_SUFFIX, ''))) return false
  const parts = cls.split('-')
  for (let i = 1; i < parts.length; i++) {
    if (haystack.includes(parts.slice(0, i).join('-') + '-')) return false // 동적 조립 가능성
  }
  return true
}

const vueFiles = walk(SRC, ['.vue'])
const globalHaystack = [
  ...vueFiles.map(f => readFileSync(f, 'utf8').replace(/<style[^>]*>[\s\S]*?<\/style>/g, '')),
  ...walk(SRC, ['.js']).map(f => readFileSync(f, 'utf8')),
].join('\n')

const dead = [] // { cls, file, scope }

// 1) 전역 .css 파일
for (const f of walk(SRC, ['.css'])) {
  for (const cls of new Set(classesOf(readFileSync(f, 'utf8')))) {
    if (isDeadIn(cls, globalHaystack)) dead.push({ cls, file: f, scope: 'global' })
  }
}

// 2) .vue scoped 스타일 — 해당 파일 안에서만 검색
for (const f of vueFiles) {
  const txt = readFileSync(f, 'utf8')
  const own = txt.replace(/<style[^>]*>[\s\S]*?<\/style>/g, '')
  const styles = [...txt.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map(m => m[1]).join('\n')
  for (const cls of new Set(classesOf(styles))) {
    // scoped여도 전역 클래스(style.css 정의)를 페이지에서 보강하는 경우가 있어 전역 사용도 인정
    if (isDeadIn(cls, own) && isDeadIn(cls, globalHaystack)) dead.push({ cls, file: f, scope: 'scoped' })
  }
}

dead.sort((a, b) => a.file.localeCompare(b.file) || a.cls.localeCompare(b.cls))
const lines = dead.map(d => `${d.scope}\t${d.cls}\t${d.file}`)
writeFileSync(join(SRC, '..', 'scripts', 'dead-css.tsv'), lines.join('\n'))
for (const l of lines) console.log(l.replace(SRC, 'src'))
console.log(`\n총 ${dead.length}개`)
