/**
 * Fail-closed guard for markup that reaches a `v-html` sink.
 *
 * Mermaid sanitises the SVG it generates with its own bundled DOMPurify and the
 * site runs it at `securityLevel: 'strict'`, so a rendered diagram is already
 * inert. This module is the second line of defence: if a mermaid upgrade or a
 * config change ever emits active content, the caller refuses to mount it and
 * shows the diagram's error state instead.
 *
 * `foreignObject` is deliberately allowed — mermaid uses it for its own HTML
 * labels, and strict mode encodes their content.
 */
const ACTIVE_SVG_CONTENT = /<\s*(script|iframe|object|embed)\b|\son[a-z]+\s*=|javascript:/i

export function containsActiveSvgContent(svg: string): boolean {
  return ACTIVE_SVG_CONTENT.test(svg)
}

export function assertInertSvg(svg: string): void {
  if (containsActiveSvgContent(svg)) {
    throw new Error('Mermaid rendered active content; refusing to mount the diagram')
  }
}
