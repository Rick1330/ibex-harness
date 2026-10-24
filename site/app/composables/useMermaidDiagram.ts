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
  if (!mermaidPromise) {
    mermaidPromise = import('mermaid').then(module => module.default)
  }
  return mermaidPromise
}

function readToken(name: string, fallback: string) {
  if (typeof document === 'undefined') return fallback
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

function buildConfig(isDark: boolean, htmlLabels: boolean): MermaidConfig {
  const ink = readToken('--site-ink', isDark ? '#f2f2ed' : '#0a0b0c')
  const muted = readToken('--site-muted', isDark ? '#9a9d98' : '#5c605d')
  const line = readToken('--site-line', isDark ? '#262a2d' : '#d8d8d0')
  const lineStrong = readToken('--site-line-strong', isDark ? '#3a3f42' : '#b9bab2')
  const surface = readToken('--site-surface', isDark ? '#101214' : '#f8f8f4')
  const surfaceStrong = readToken('--site-surface-strong', isDark ? '#15181b' : '#ffffff')
  const background = readToken('--site-bg', isDark ? '#090a0b' : '#f1f1ec')
  const codeBackground = readToken('--site-code-bg', isDark ? '#141719' : '#e8e8e1')
  const signal = readToken('--site-signal', isDark ? '#d8ff4f' : '#5f8f00')
  const fontFamily = typeof document === 'undefined'
    ? 'ui-sans-serif, system-ui, sans-serif'
    : getComputedStyle(document.body).fontFamily

  return {
    startOnLoad: false,
    securityLevel: 'strict',
    theme: 'base',
    darkMode: isDark,
    fontFamily,
    htmlLabels,
    themeCSS: `
      .node rect, .node polygon, .node circle, .node ellipse, .node path { stroke-width: 1.2px; filter: drop-shadow(0 1px 1.5px ${isDark ? 'rgba(0, 0, 0, 0.45)' : 'rgba(10, 11, 12, 0.08)'}); }
      .nodeLabel { font-weight: 500; }
      .cluster rect { stroke-width: 1.1px; }
      .cluster-label .nodeLabel { color: ${signal}; fill: ${signal}; font-weight: 600; letter-spacing: 0.01em; }
      .flowchart-link, .edgePath .path { stroke-width: 1.2px; }
      .edgeLabel, .edgeLabel p { font-size: 12.5px; }
    `,
    themeVariables: {
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
    },
    flowchart: {
      useMaxWidth: true,
      wrappingWidth: 260,
      curve: 'basis',
      nodeSpacing: 40,
      rankSpacing: 48,
      padding: 14,
    },
    sequence: {
      useMaxWidth: true,
      wrap: true,
      mirrorActors: false,
      actorMargin: 48,
      messageMargin: 36,
      noteMargin: 12,
      boxMargin: 10,
    },
    gantt: {
      useMaxWidth: true,
      leftPadding: 96,
      gridLineStartPadding: 40,
      barHeight: 22,
      barGap: 6,
      topPadding: 56,
      sectionFontSize: 12,
    },
    journey: { useMaxWidth: true },
    timeline: { useMaxWidth: true },
    class: { useMaxWidth: true },
    state: { useMaxWidth: true },
    er: { useMaxWidth: true },
  }
}

function nextDiagramId(prefix: string) {
  diagramSequence += 1
  return `${prefix}-${diagramSequence}`
}

function measure(svg: string) {
  const viewBox = svg.match(/<svg\b[^>]*\bviewBox="([^"]+)"/i)?.[1]
  if (viewBox) {
    const parts = viewBox.split(/[\s,]+/).map(Number)
    if (parts.length === 4 && parts.every(Number.isFinite)) {
      return { width: parts[2]!, height: parts[3]! }
    }
  }
  return {
    width: Number(svg.match(/<svg\b[^>]*\bwidth="([\d.]+)"/i)?.[1]) || 800,
    height: Number(svg.match(/<svg\b[^>]*\bheight="([\d.]+)"/i)?.[1]) || 600,
  }
}

function enqueue<T>(work: () => Promise<T>) {
  const run = renderQueue.then(work, work)
  renderQueue = run.then(() => undefined, () => undefined)
  return run
}

export function useMermaidDiagram() {
  const colorMode = useColorMode()
  const isDark = computed(() => colorMode.value === 'dark')

  async function render(code: string, prefix = 'ibex-mermaid', options: { htmlLabels?: boolean } = {}): Promise<RenderedDiagram> {
    const mermaid = await loadMermaid()
    const dark = isDark.value
    const htmlLabels = options.htmlLabels ?? true
    return enqueue(async () => {
      mermaid.initialize(buildConfig(dark, htmlLabels))
      const id = nextDiagramId(prefix)
      const result = await mermaid.render(id, code)
      return {
        ...measure(result.svg),
        svg: result.svg,
        bindFunctions: result.bindFunctions,
      }
    })
  }

  return { isDark, render }
}
