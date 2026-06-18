export type DiagramPosition = Readonly<{ x: number; y: number }>;

export type DiagramTransform = Readonly<{
  scale: number;
  position: DiagramPosition;
}>;

export const DIAGRAM_MIN_SCALE = 0.4;
export const DIAGRAM_MAX_SCALE = 3;
export const DIAGRAM_FIT_MIN_SCALE = 0.05;
export const DIAGRAM_FIT_PADDING = 32;

type SvgDimensions = Readonly<{ width: number; height: number }>;

function parseViewBoxAttribute(viewBox: string): SvgDimensions | null {
  const parts = viewBox.trim().split(/[\s,]+/).map(Number);
  if (parts.length !== 4 || parts.some((value) => Number.isNaN(value))) {
    return null;
  }
  const width = parts[2];
  const height = parts[3];
  if (width <= 0 || height <= 0) return null;
  return { width, height };
}

function parseSvgDimensionsFromElement(svg: SVGSVGElement): SvgDimensions | null {
  const viewBox = svg.getAttribute("viewBox");
  if (viewBox) {
    const parsed = parseViewBoxAttribute(viewBox);
    if (parsed) return parsed;
  }

  try {
    const box = svg.getBBox();
    if (box.width > 0 && box.height > 0) {
      return { width: box.width, height: box.height };
    }
  } catch {
    // getBBox may throw before layout
  }

  const width = Number.parseFloat(svg.getAttribute("width") ?? "");
  const height = Number.parseFloat(svg.getAttribute("height") ?? "");
  if (width > 0 && height > 0) return { width, height };

  return null;
}

export function parseSvgDimensionsFromString(svg: string): SvgDimensions | null {
  const match = /viewBox=["']([^"']+)["']/i.exec(svg);
  if (match?.[1]) {
    const parsed = parseViewBoxAttribute(match[1]);
    if (parsed) return parsed;
  }

  const widthMatch = /\bwidth=["']([\d.]+)(%|px)?/i.exec(svg);
  const heightMatch = /\bheight=["']([\d.]+)(%|px)?/i.exec(svg);
  if (widthMatch && heightMatch && !widthMatch[2] && !heightMatch[2]) {
    const width = Number.parseFloat(widthMatch[1]);
    const height = Number.parseFloat(heightMatch[1]);
    if (width > 0 && height > 0) return { width, height };
  }

  return null;
}

export function parseSvgDimensions(
  source: SVGSVGElement | string,
): SvgDimensions | null {
  if (typeof source === "string") return parseSvgDimensionsFromString(source);
  return parseSvgDimensionsFromElement(source);
}

function clampFitScale(value: number): number {
  return Math.min(DIAGRAM_MAX_SCALE, Math.max(DIAGRAM_FIT_MIN_SCALE, value));
}

function clampUserScale(value: number): number {
  return Math.min(DIAGRAM_MAX_SCALE, Math.max(DIAGRAM_MIN_SCALE, value));
}

export function computeFitTransform(
  svgWidth: number,
  svgHeight: number,
  containerWidth: number,
  containerHeight: number,
  padding = DIAGRAM_FIT_PADDING,
): DiagramTransform {
  if (
    svgWidth <= 0 ||
    svgHeight <= 0 ||
    containerWidth <= 0 ||
    containerHeight <= 0
  ) {
    return { scale: 1, position: { x: 0, y: 0 } };
  }

  const innerWidth = Math.max(containerWidth - padding * 2, 1);
  const innerHeight = Math.max(containerHeight - padding * 2, 1);
  const scale = clampFitScale(
    Math.min(innerWidth / svgWidth, innerHeight / svgHeight),
  );
  const x = (containerWidth - svgWidth * scale) / 2;
  const y = (containerHeight - svgHeight * scale) / 2;

  return { scale, position: { x, y } };
}

export function fitTransformForContainer(
  source: SVGSVGElement | string | null,
  containerWidth: number,
  containerHeight: number,
): DiagramTransform | null {
  if (!source) return null;
  const dimensions = parseSvgDimensions(source);
  if (!dimensions) return null;
  return computeFitTransform(
    dimensions.width,
    dimensions.height,
    containerWidth,
    containerHeight,
  );
}
