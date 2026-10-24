export type CodeLanguage = 'shell' | 'ts' | 'python'

export type CodeTokenKind =
  | 'plain'
  | 'comment'
  | 'string'
  | 'variable'
  | 'number'
  | 'keyword'
  | 'function'
  | 'property'
  | 'type'
  | 'operator'
  | 'punctuation'
  | 'command'
  | 'flag'

export interface CodeToken {
  text: string
  kind: CodeTokenKind
}

const TOKEN_PATTERN = /"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|\$[A-Za-z_][A-Za-z0-9_]*|\b\d+(?:\.\d+)?\b/g

const TS_KEYWORDS = new Set([
  'as', 'async', 'await', 'break', 'case', 'catch', 'class', 'const', 'continue',
  'default', 'delete', 'do', 'else', 'export', 'extends', 'false', 'finally', 'for',
  'from', 'function', 'if', 'implements', 'import', 'in', 'instanceof', 'interface',
  'let', 'new', 'null', 'of', 'return', 'static', 'super', 'switch', 'this', 'throw',
  'true', 'try', 'type', 'typeof', 'undefined', 'var', 'void', 'while',
])

const PY_KEYWORDS = new Set([
  'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue', 'def', 'del',
  'elif', 'else', 'except', 'False', 'finally', 'for', 'from', 'global', 'if', 'import',
  'in', 'is', 'lambda', 'None', 'nonlocal', 'not', 'or', 'pass', 'raise', 'return',
  'True', 'try', 'while', 'with', 'yield',
])

const STRUCTURED_PATTERN = /[{}()[\],;:.]|\b[A-Za-z_$][\w$]*(?=\s*\()|\b[A-Za-z_$][\w$]*(?=\s*:)|[=+\-*/%<>!&|?]+|\b[A-Za-z_$][\w$]*\b/g
const SHELL_REST_PATTERN = /(?<![\w-])--?[A-Za-z][\w-]*|\b(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b|https?:\/\/[^\s"'`]+/g

function tokenizeStructuredPlain(text: string, language: 'ts' | 'python'): CodeToken[] {
  const keywords = language === 'ts' ? TS_KEYWORDS : PY_KEYWORDS
  const tokens: CodeToken[] = []
  let cursor = 0

  for (const match of text.matchAll(STRUCTURED_PATTERN)) {
    const index = match.index ?? 0
    if (index > cursor) {
      tokens.push({ text: text.slice(cursor, index), kind: 'plain' })
    }

    const value = match[0]
    const rest = text.slice(index + value.length)
    let kind: CodeTokenKind = 'plain'

    if (/^[{}()[\],;:.]$/.test(value)) {
      kind = 'punctuation'
    } else if (/^[=+\-*/%<>!&|?]+$/.test(value)) {
      kind = 'operator'
    } else if (keywords.has(value)) {
      kind = 'keyword'
    } else if (/^[A-Za-z_$][\w$]*$/.test(value)) {
      if (/^\s*\(/.test(rest)) {
        kind = 'function'
      } else if (/^\s*:/.test(rest)) {
        kind = 'property'
      }
    }

    tokens.push({ text: value, kind })
    cursor = index + value.length
  }

  if (cursor < text.length) {
    tokens.push({ text: text.slice(cursor), kind: 'plain' })
  }

  return tokens
}

function tokenizeShellPlain(text: string, atLineStart: boolean): CodeToken[] {
  const tokens: CodeToken[] = []
  let rest = text

  if (atLineStart) {
    const command = rest.match(/^(\s*)([A-Za-z][\w.-]*)/)
    if (command) {
      if (command[1]) tokens.push({ text: command[1], kind: 'plain' })
      tokens.push({ text: command[2]!, kind: 'command' })
      rest = rest.slice(command[0].length)
    }
  }

  return [...tokens, ...tokenizeShellRest(rest)]
}

function tokenizeShellRest(rest: string): CodeToken[] {
  const tokens: CodeToken[] = []
  let cursor = 0
  for (const match of rest.matchAll(SHELL_REST_PATTERN)) {
    const index = match.index ?? 0
    if (index > cursor) {
      tokens.push({ text: rest.slice(cursor, index), kind: 'plain' })
    }
    tokens.push({ text: match[0], kind: shellRestKind(match[0]) })
    cursor = index + match[0].length
  }
  if (cursor < rest.length) {
    tokens.push({ text: rest.slice(cursor), kind: 'plain' })
  }
  return tokens
}

function shellRestKind(value: string): CodeTokenKind {
  if (value.startsWith('http')) return 'string'
  if (value.startsWith('-')) return 'flag'
  return 'keyword'
}

function tokenizePlain(text: string, language: CodeLanguage, atLineStart: boolean): CodeToken[] {
  if (!text) return []
  return language === 'shell'
    ? tokenizeShellPlain(text, atLineStart)
    : tokenizeStructuredPlain(text, language)
}

export function isCommentLine(line: string, language: CodeLanguage) {
  const trimmed = line.trimStart()
  return language === 'ts' ? trimmed.startsWith('//') : trimmed.startsWith('#')
}

export function tokenizeCodeLine(line: string, language: CodeLanguage): CodeToken[] {
  if (!line) return []
  return isCommentLine(line, language)
    ? tokenizeCommentLine(line)
    : tokenizeCodeSegments(line, language)
}

function tokenizeCommentLine(line: string): CodeToken[] {
  const trimmed = line.trimStart()
  const indent = line.slice(0, line.length - trimmed.length)
  return [
    ...(indent ? [{ text: indent, kind: 'plain' as const }] : []),
    { text: trimmed, kind: 'comment' },
  ]
}

function segmentKind(text: string): CodeTokenKind {
  if (text.startsWith('"') || text.startsWith("'") || text.startsWith('`')) return 'string'
  if (text.startsWith('$')) return 'variable'
  return 'number'
}

function tokenizeCodeSegments(line: string, language: CodeLanguage): CodeToken[] {
  const tokens: CodeToken[] = []
  let cursor = 0

  for (const match of line.matchAll(TOKEN_PATTERN)) {
    const index = match.index ?? 0

    if (index > cursor) {
      tokens.push(...tokenizePlain(line.slice(cursor, index), language, cursor === 0))
    }

    tokens.push({ text: match[0], kind: segmentKind(match[0]) })
    cursor = index + match[0].length
  }

  if (cursor < line.length) {
    tokens.push(...tokenizePlain(line.slice(cursor), language, cursor === 0))
  }

  return tokens
}
