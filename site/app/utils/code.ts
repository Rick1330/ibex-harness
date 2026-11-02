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

export class CodeToken {
  readonly text: string
  readonly kind: CodeTokenKind

  constructor(text: string, kind: CodeTokenKind) {
    this.text = text
    this.kind = kind
  }

  static plain(text: string): CodeToken {
    return new CodeToken(text, 'plain')
  }
}

// A quoted string of any of the three quote flavors, a shell-style variable,
// or a decimal number.
const TOKEN_PATTERN = /(["'`])(?:\\.|(?!\1)[^\\])*\1|\$[A-Za-z_]\w*|\b\d+(?:\.\d+)?\b/g

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

const PUNCTUATION = /^[{}()[\],;:.]$/
const OPERATOR = /^[=+\-*/%<>!&|?]+$/
const IDENTIFIER = /^[A-Za-z_$][\w$]*$/
// Identifiers followed by ( classify as calls, by : as property keys.
const STRUCTURED_PATTERN = /[{}()[\],;:.]|[=+\-*/%<>!&|?]+|\b[A-Za-z_$][\w$]*(?=\s*[:(])|\b[A-Za-z_$][\w$]*\b/g
// Flags, URLs, and bare uppercase words (HTTP verbs are promoted to keywords
// in shellRestKind; other uppercase words stay plain).
const SHELL_REST_PATTERN = /(?<![\w-])--?[A-Za-z][\w-]*|https?:\/\/[^\s"'`]+|\b[A-Z]{3,8}\b/g

const SHELL_KEYWORDS = new Set(['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'])

// Accumulates tokens over one source string so each tokenizer stays linear:
// gaps before matches, matched segments, and the plain remainder all flow
// through one cursor.
function createTokenSink(source: string) {
  const tokens: CodeToken[] = []
  let cursor = 0
  return {
    tokens,
    consumed: () => cursor,
    textBefore(index: number) {
      return source.slice(cursor, index)
    },
    advanceTo(index: number) {
      cursor = index
    },
    push(token: CodeToken) {
      tokens.push(token)
      cursor += token.text.length
    },
    pushAll(newTokens: CodeToken[]) {
      tokens.push(...newTokens)
      cursor += newTokens.reduce((length, token) => length + token.text.length, 0)
    },
    pushPlain(text: string, kind: CodeTokenKind = 'plain') {
      tokens.push(new CodeToken(text, kind))
      cursor += text.length
    },
    pushRemainingPlain() {
      if (cursor < source.length) {
        tokens.push(CodeToken.plain(source.slice(cursor)))
      }
    },
  }
}

function structuredKind(value: string, keywords: Set<string>, rest: string): CodeTokenKind {
  if (PUNCTUATION.test(value)) return 'punctuation'
  if (OPERATOR.test(value)) return 'operator'
  if (keywords.has(value)) return 'keyword'
  if (!IDENTIFIER.test(value)) return 'plain'
  if (/^\s*\(/.test(rest)) return 'function'
  if (/^\s*:/.test(rest)) return 'property'
  return 'plain'
}

function tokenizeStructuredPlain(text: string, language: 'ts' | 'python'): CodeToken[] {
  const keywords = language === 'ts' ? TS_KEYWORDS : PY_KEYWORDS
  const sink = createTokenSink(text)

  for (const match of text.matchAll(STRUCTURED_PATTERN)) {
    const index = match.index ?? 0
    const gap = sink.textBefore(index)
    if (gap) sink.pushPlain(gap)
    sink.advanceTo(index)
    const rest = text.slice(index + match[0].length)
    sink.push(new CodeToken(match[0], structuredKind(match[0], keywords, rest)))
  }

  sink.pushRemainingPlain()
  return sink.tokens
}

function shellRestKind(value: string): CodeTokenKind {
  if (value.startsWith('http')) return 'string'
  if (value.startsWith('-')) return 'flag'
  if (SHELL_KEYWORDS.has(value)) return 'keyword'
  return 'plain'
}

function tokenizeShellPlain(text: string, atLineStart: boolean): CodeToken[] {
  const sink = createTokenSink(text)

  if (atLineStart) {
    const command = text.match(/^(\s*)([A-Za-z][\w.-]*)/)
    if (command) {
      if (command[1]) sink.pushPlain(command[1])
      sink.pushPlain(command[2]!, 'command')
    }
  }

  for (const match of text.matchAll(SHELL_REST_PATTERN)) {
    const index = match.index ?? 0
    const gap = sink.textBefore(index)
    if (gap) sink.pushPlain(gap)
    sink.advanceTo(index)
    sink.pushPlain(match[0], shellRestKind(match[0]))
  }

  sink.pushRemainingPlain()
  return sink.tokens
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
    ...(indent ? [CodeToken.plain(indent)] : []),
    new CodeToken(trimmed, 'comment'),
  ]
}

function segmentKind(text: string): CodeTokenKind {
  if (text.startsWith('"') || text.startsWith("'") || text.startsWith('`')) return 'string'
  if (text.startsWith('$')) return 'variable'
  return 'number'
}

function tokenizeCodeSegments(line: string, language: CodeLanguage): CodeToken[] {
  const sink = createTokenSink(line)

  for (const match of line.matchAll(TOKEN_PATTERN)) {
    const index = match.index ?? 0
    const gap = sink.textBefore(index)
    if (gap) sink.pushAll(tokenizePlain(gap, language, sink.consumed() === 0))
    sink.advanceTo(index)
    sink.push(new CodeToken(match[0], segmentKind(match[0])))
  }

  const remainder = sink.textBefore(line.length)
  if (remainder) sink.pushAll(tokenizePlain(remainder, language, sink.consumed() === 0))
  return sink.tokens
}
