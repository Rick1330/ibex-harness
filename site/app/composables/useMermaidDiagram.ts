import type { MermaidConfig } from 'mermaid'

type Mermaid = (typeof import('mermaid'))['default']

export interface RenderedDiagram {
  svg: string
  width: number
  height: number
  bindFunctions?: (element: Element) => void
}

let mermaidPromise: Promise<Mermaid> | null = null
let renderQueue: Promise<unknown> = Promise.resolve()
let diagramSequence = 0

function loadMermaid() {
  mermaidPromise ??= import('mermaid').then(module => module.default)
  return mermaidPromise
}

function readToken(name: string, fallback: string) {
  if (typeof document === 'undefined') return fallback
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

interface ThemeTokens {
  ink: string
  muted: string
  line: string
  lineStrong: string
  surface: string
  surfaceStrong: string
  background: string
  codeBackground: string
  signal: string
}

// cssVar name plus the dark and light fallbacks, in that order.
const THEME_TOKEN_FALLBACKS: Record<keyof ThemeTokens, [cssVar: string, dark: string, light: string]> = {
  ink: ['--site-ink', '#f2f2ed', '#0a0b0c'],
  muted: ['--site-muted', '#9a9d98', '#5c605d'],
  line: ['--site-line', '#262a2d', '#d8d8d0'],
  lineStrong: ['--site-line-strong', '#3a3f42', '#b9bab2'],
  surface: ['--site-surface', '#101214', '#f8f8f4'],
  surfaceStrong: ['--site-surface-strong', '#15181b', '#ffffff'],
  background: ['--site-bg', '#090a0b', '#f1f1ec'],
  codeBackground: ['--site-code-bg', '#141719', '#e8e8e1'],
  signal: ['--site-signal', '#d8ff4f', '#5f8f00'],
}

function readThemeTokens(isDark: boolean): ThemeTokens {
  const shade = isDark ? 1 : 2
  return Object.fromEntries(
    (Object.keys(THEME_TOKEN_FALLBACKS) as (keyof ThemeTokens)[])
      .map(key => [key, readToken(THEME_TOKEN_FALLBACKS[key][0], THEME_TOKEN_FALLBACKS[key][shade])]),
  ) as unknown as ThemeTokens
}

function readFontFamily() {
  return typeof document === 'undefined'
    ? 'ui-sans-serif, system-ui, sans-serif'
    : getComputedStyle(document.body).fontFamily
}

function buildThemeCSS(isDark: boolean, signal: string) {
  const shadow = isDark ? 'rgba(0, 0, 0, 0.45)' : 'rgba(10, 11, 12, 0.08)'
  return `
      .node rect, .node polygon, .node circle, .node ellipse, .node path { stroke-width: 1.2px; filter: drop-shadow(0 1px 1.5px ${shadow}); }
      .nodeLabel { font-weight: 500; }
      .cluster rect { stroke-width: 1.1px; }
      .cluster-label .nodeLabel { color: ${signal}; fill: ${signal}; font-weight: 600; letter-spacing: 0.01em; }
      .flowchart-link, .edgePath .path { stroke-width: 1.2px; }
      .edgeLabel, .edgeLabel p { font-size: 12.5px; }
    `
}

function buildThemeVariables(palette: ReturnType<typeof readThemeTokens>, fontFamily: string): MermaidConfig['themeVariables'] {
  const {
    ink, muted, line, lineStrong, surface, surfaceStrong,
    background, codeBackground, signal,
  } = palette
  return {
    fontFamily,
    fontSize: '15px',
    background,
    mainBkg: surfaceStrong,
    primaryColor: surfaceStrong,
    primaryTextColor: ink,
    primaryBorderColor: lineStrong,
    secondaryColor: codeBackground,
    tertiaryColor: surface,
    lineColor: muted,
    textColor: ink,
    nodeTextColor: ink,
    edgeLabelBackground: background,
    clusterBkg: surface,
    clusterBorder: line,
    titleColor: ink,
    nodeBorder: lineStrong,
    actorBkg: surfaceStrong,
    actorBorder: lineStrong,
    actorTextColor: ink,
    actorLineColor: lineStrong,
    signalColor: ink,
    signalTextColor: ink,
    labelBoxBkgColor: surface,
    labelBoxBorderColor: lineStrong,
    labelTextColor: ink,
    loopTextColor: ink,
    noteBkgColor: codeBackground,
    noteBorderColor: lineStrong,
    noteTextColor: ink,
    activationBkgColor: surface,
    activationBorderColor: signal,
    sectionBkgColor: surface,
    altSectionBkgColor: background,
    taskBkgColor: surfaceStrong,
    taskBorderColor: lineStrong,
    taskTextColor: ink,
    activeTaskBkgColor: codeBackground,
    activeTaskBorderColor: signal,
    gridColor: line,
    doneTaskBkgColor: codeBackground,
    doneTaskBorderColor: lineStrong,
    critBkgColor: codeBackground,
    critBorderColor: signal,
    todayLineColor: signal,
    attributeBackgroundColorOdd: surface,
    attributeBackgroundColorEven: codeBackground,
    attributeTextColor: ink,
    rowOdd: surface,
    rowEven: codeBackground,
  }
}

// Diagram-type options are theme-independent; the shared useMaxWidth keeps
// every diagram responsive inside its container.
const DIAGRAM_TYPE_OPTIONS = { useMaxWidth: true } as const

function buildConfig(isDark: boolean, htmlLabels: boolean): MermaidConfig {
  const palette = readThemeTokens(isDark)
  const fontFamily = readFontFamily()

  return {
    startOnLoad: false,
    securityLevel: 'strict',
    theme: 'base',
    darkMode: isDark,
    fontFamily,
    htmlLabels,
    themeCSS: buildThemeCSS(isDark, palette.signal),
    themeVariables: buildThemeVariables(palette, fontFamily),
    flowchart: { ...DIAGRAM_TYPE_OPTIONS, wrappingWidth: 260, curve: 'basis', nodeSpacing: 40, rankSpacing: 48, padding: 14 },
    sequence: { ...DIAGRAM_TYPE_OPTIONS, wrap: true, mirrorActors: false, actorMargin: 48, messageMargin: 36, noteMargin: 12, boxMargin: 10 },
    gantt: { ...DIAGRAM_TYPE_OPTIONS, leftPadding: 96, gridLineStartPadding: 40, barHeight: 22, barGap: 6, topPadding: 56, sectionFontSize: 12 },
    journey: DIAGRAM_TYPE_OPTIONS,
    timeline: DIAGRAM_TYPE_OPTIONS,
    class: DIAGRAM_TYPE_OPTIONS,
    state: DIAGRAM_TYPE_OPTIONS,
    er: DIAGRAM_TYPE_OPTIONS,
  }
}

function nextDiagramId(prefix: string) {
  diagramSequence += 1
  return `${prefix}-${diagramSequence}`
}

const SVG_VIEWBOX = /<svg\b[^>]*\bviewBox="([^"]+)"/i
const SVG_WIDTH = /<svg\b[^>]*\bwidth="([\d.]+)"/i
const SVG_HEIGHT = /<svg\b[^>]*\bheight="([\d.]+)"/i

function viewBoxSize(svg: string): { width: number, height: number } | null {
  const viewBox = SVG_VIEWBOX.exec(svg)?.[1]
  if (!viewBox) return null
  const parts = viewBox.split(/[\s,]+/).map(Number)
  if (parts.length !== 4 || !parts.every(Number.isFinite)) return null
  return { width: parts[2]!, height: parts[3]! }
}

function measure(svg: string) {
  const fromViewBox = viewBoxSize(svg)
  if (fromViewBox) return fromViewBox
  return {
    width: Number(SVG_WIDTH.exec(svg)?.[1]) || 800,
    height: Number(SVG_HEIGHT.exec(svg)?.[1]) || 600,
  }
}

function enqueue<T>(work: () => Promise<T>) {
  const run = renderQueue.then(work, work)
  renderQueue = run.then(() => undefined, () => undefined)
  return run
}

// A mermaid operation that never settles (a stalled library chunk, a hung
// renderer) must surface the diagram's visible error state instead of an
// indefinite spinner. The deadline cannot cancel the underlying work; it
// only stops the caller waiting on it.
const MERMAID_OPERATION_TIMEOUT_MS = 20_000

function withDeadline<T>(work: Promise<T>, failure: string): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined
  const deadline = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error(failure)), MERMAID_OPERATION_TIMEOUT_MS)
  })
  return Promise.race([work, deadline]).finally(() => {
    if (timer !== undefined) clearTimeout(timer)
  })
}

export function useMermaidDiagram() {
  const colorMode = useColorMode()
  const isDark = computed(() => colorMode.value === 'dark')

  async function render(code: string, prefix = 'ibex-mermaid', options: { htmlLabels?: boolean } = {}): Promise<RenderedDiagram> {
    const mermaid = await withDeadline(loadMermaid(), 'Mermaid library failed to load in time')
    const dark = isDark.value
    const htmlLabels = options.htmlLabels ?? true
    return enqueue(async () => {
      mermaid.initialize(buildConfig(dark, htmlLabels))
      const id = nextDiagramId(prefix)
      const result = await withDeadline(mermaid.render(id, code), 'Diagram rendering timed out')
      return {
        ...measure(result.svg),
        svg: result.svg,
        bindFunctions: result.bindFunctions,
      }
    })
  }

  return { isDark, render }
}
