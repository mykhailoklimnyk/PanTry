
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'
import { readFileSync, writeFileSync } from 'node:fs'

const require = createRequire(new URL('../web/package.json', import.meta.url))
const ts = require('typescript')
const esbuild = require('esbuild')
const compiler = await import(pathToFileURL(require.resolve('svelte/compiler')).href)
const svelte = compiler.parse ? compiler : compiler.default

const DIRECTIVE = /^(\/\/|\/\*)\s*(@ts-|ts-|eslint|prettier|biome|@vite-|@__PURE__|#__PURE__|svelte-ignore|@component|c8 |v8 |istanbul )/

const TYPED = /@(type|typedef|satisfies|param\s*\{|returns?\s*\{|template)/
const keep = (text) => text.startsWith('/*!') || DIRECTIVE.test(text) || TYPED.test(text)

function tsComments(text, kind) {
  const file = ts.createSourceFile(
    'x.' + kind,
    text,
    ts.ScriptTarget.Latest,
    true,
    kind === 'ts' ? ts.ScriptKind.TS : ts.ScriptKind.JS,
  )
  const found = new Map()
  const collect = (pos) => {
    for (const range of ts.getLeadingCommentRanges(text, pos) || []) {
      found.set(`${range.pos}:${range.end}`, range)
    }
  }
  const walk = (node) => {
    collect(node.pos)
    for (const child of node.getChildren(file)) walk(child)
  }
  walk(file)
  return [...found.values()]
    .map((range) => ({ start: range.pos, end: range.end }))
    .filter(({ start, end }) => !keep(text.slice(start, end)))
}

function cssComments(text) {
  const out = []
  let i = 0
  while (i < text.length) {
    const ch = text[i]
    if (ch === '"' || ch === "'") {
      i += 1
      while (i < text.length && text[i] !== ch) i += text[i] === '\\' ? 2 : 1
      i += 1
    } else if (ch === '/' && text[i + 1] === '*') {
      const end = text.indexOf('*/', i + 2)
      const stop = end === -1 ? text.length : end + 2
      if (!keep(text.slice(i, stop))) out.push({ start: i, end: stop })
      i = stop
    } else {
      i += 1
    }
  }
  return out
}

let removed = 0

function cut(text, ranges) {
  removed += ranges.length
  let out = text
  for (const { start, end } of [...ranges].sort((a, b) => b.start - a.start)) {
    let from = start
    let to = end
    const lineStart = out.lastIndexOf('\n', start - 1) + 1
    const lineEnd = out.indexOf('\n', end)
    const alone =
      !out.slice(lineStart, start).trim() &&
      !out.slice(end, lineEnd === -1 ? out.length : lineEnd).trim()
    if (alone) {
      from = lineStart
      to = lineEnd === -1 ? out.length : lineEnd + 1
    } else {
      while (from > lineStart && /[ \t]/.test(out[from - 1])) from -= 1
    }
    out = out.slice(0, from) + out.slice(to)
  }
  return out
}

function firstDiff(before, after) {
  let at = 0
  while (at < before.length && at < after.length && before[at] === after[at]) at += 1
  const around = (text) => text.slice(Math.max(0, at - 40), at + 60).replace(/\n/g, ' ')
  return `на символі ${at}: було «${around(before)}» | стало «${around(after)}»`
}

const tidy = (text) => text.replace(/\n{4,}/g, '\n\n\n')

const printed = (text, kind) =>
  ts
    .createPrinter({ removeComments: true })
    .printFile(
      ts.createSourceFile(
        'x.' + kind,
        text,
        ts.ScriptTarget.Latest,
        false,
        kind === 'ts' ? ts.ScriptKind.TS : ts.ScriptKind.JS,
      ),
    )

const minified = (text) => esbuild.transformSync(text, { loader: 'css', minify: true }).code

function nothingLeft(ranges, text, what) {
  if (!ranges.length) return
  const shown = ranges
    .slice(0, 3)
    .map(({ start, end }) => text.slice(start, end).slice(0, 60).replace(/\s+/g, ' '))
  throw new Error(`${what}: лишилось ${ranges.length} (${shown.join(' | ')})`)
}

function stripTs(text, kind) {
  const out = tidy(cut(text, tsComments(text, kind)))
  const [before, after] = [printed(text, kind), printed(out, kind)]
  if (before !== after) throw new Error('AST друкується інакше: ' + firstDiff(before, after))
  nothingLeft(tsComments(out, kind), out, 'коментарі коду')
  return out
}

function stripCss(text) {
  const out = tidy(cut(text, cssComments(text)))
  const [before, after] = [minified(text), minified(out)]
  if (before !== after) throw new Error('мініфікований CSS розійшовся: ' + firstDiff(before, after))
  nothingLeft(cssComments(out), out, 'коментарі стилів')
  return out
}

function markupComments(node, text, out = new Map(), inPre = false) {
  if (Array.isArray(node)) {
    for (const item of node) markupComments(item, text, out, inPre)
    return out
  }
  if (!node || typeof node !== 'object') return out
  const pre = inPre || (node.type === 'RegularElement' && node.name === 'pre')
  const at = `${node.start}:${node.end}`
  if (!pre && typeof node.start === 'number' && typeof node.end === 'number') {
    if (node.type === 'Comment' && !keep('// ' + node.data)) {
      out.set(at, { start: node.start, end: node.end })
    } else if (
      (node.type === 'Block' || node.type === 'Line') &&
      !keep(text.slice(node.start, node.end))
    ) {
      out.set(at, { start: node.start, end: node.end })
    }
  }
  for (const value of Object.values(node)) markupComments(value, text, out, pre)
  return out
}

function stripSvelte(text) {
  const ast = svelte.parse(text, { modern: true })
  const parts = []
  for (const block of [ast.instance, ast.module]) {
    if (!block) continue
    const { start, end } = block.content
    parts.push({ start, end, strip: (body) => cut(body, tsComments(body, 'ts')) })
  }
  if (ast.css) {
    const { start, end } = ast.css.content
    parts.push({ start, end, strip: (body) => cut(body, cssComments(body)) })
  }
  let out = text
  for (const part of parts.sort((a, b) => b.start - a.start)) {
    out = out.slice(0, part.start) + part.strip(out.slice(part.start, part.end)) + out.slice(part.end)
  }
  out = tidy(cut(out, [...markupComments(svelte.parse(out, { modern: true }).fragment, out).values()]))

  const compiled = (source) => {
    const result = svelte.compile(source, { generate: 'client', filename: 'x.svelte' })
    const code = printed(result.js.code, 'js') + '\n/*css*/\n' + (result.css ? minified(result.css.code) : '')
    return code.replace(/svelte-[a-z0-9]{5,}/g, 'svelte-HASH').replace(/\s+/g, ' ')
  }
  const [before, after] = [compiled(text), compiled(out)]
  if (before !== after) throw new Error('компілятор Svelte дав інший код: ' + firstDiff(before, after))

  const left = svelte.parse(out, { modern: true })
  for (const block of [left.instance, left.module]) {
    if (!block) continue
    const body = out.slice(block.content.start, block.content.end)
    nothingLeft(tsComments(body, 'ts'), body, 'коментарі скрипта')
  }
  if (left.css) {
    const body = out.slice(left.css.content.start, left.css.content.end)
    nothingLeft(cssComments(body), body, 'коментарі стилів')
  }
  nothingLeft([...markupComments(left.fragment, out).values()], out, 'коментарі розмітки')
  return out
}

const STRIP = {
  ts: (text) => stripTs(text, 'ts'),
  js: (text) => stripTs(text, 'js'),
  mjs: (text) => stripTs(text, 'js'),
  css: stripCss,
  svelte: stripSvelte,
}

const job = JSON.parse(readFileSync(0, 'utf8'))
const report = { changed: 0, removed: 0, errors: [] }
for (const file of job.files) {
  const kind = file.path.split('.').pop()
  const before = readFileSync(file.path, 'utf8')
  removed = 0
  try {
    const after = STRIP[kind](before)
    if (after !== before) {
      writeFileSync(file.path, after, 'utf8')
      report.changed += 1
      report.removed += removed
    }
  } catch (error) {
    report.errors.push(`${file.rel}: ${error.message}`)
  }
}
process.stdout.write(JSON.stringify(report))
process.exit(report.errors.length ? 1 : 0)
