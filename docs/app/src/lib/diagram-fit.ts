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

type FitBox = Readonly<{
  svgWidth: number;
  svgHeight: number;
  containerWidth: number;
  containerHeight: number;
  padding?: number;
}>;

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

function isAllowedSvgUnit(unit: string | undefined): boolean {
  return !unit || unit.toLowerCase() === "px";
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

function parseExplicitSvgSize(svg: string): SvgDimensions | null {
  const widthMatch = /\bwidth=["']([\d.]+)(%|px)?/i.exec(svg);
  const heightMatch = /\bheight=["']([\d.]+)(%|px)?/i.exec(svg);
  if (!widthMatch || !heightMatch) return null;
  if (!isAllowedSvgUnit(widthMatch[2]) || !isAllowedSvgUnit(heightMatch[2])) {
    return null;
  }

  const width = Number.parseFloat(widthMatch[1]);
  const height = Number.parseFloat(heightMatch[1]);
  if (width <= 0 || height <= 0) return null;
  return { width, height };
}

export function parseSvgDimensionsFromString(svg: string): SvgDimensions | null {
  const viewBoxMatch = /viewBox=["']([^"']+)["']/i.exec(svg);
  if (viewBoxMatch?.[1]) {
    const parsed = parseViewBoxAttribute(viewBoxMatch[1]);
    if (parsed) return parsed;
  }

  return parseExplicitSvgSize(svg);
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

function isValidFitBox(box: FitBox): boolean {
  return (
    box.svgWidth > 0 &&
    box.svgHeight > 0 &&
    box.containerWidth > 0 &&
    box.containerHeight > 0
  );
}

export function computeFitTransform(box: FitBox): DiagramTransform {
  if (!isValidFitBox(box)) {
    return { scale: 1, position: { x: 0, y: 0 } };
  }

  const padding = box.padding ?? DIAGRAM_FIT_PADDING;
  const innerWidth = Math.max(box.containerWidth - padding * 2, 1);
  const innerHeight = Math.max(box.containerHeight - padding * 2, 1);
  const scale = clampFitScale(
    Math.min(innerWidth / box.svgWidth, innerHeight / box.svgHeight),
  );
  const x = (box.containerWidth - box.svgWidth * scale) / 2;
  const y = (box.containerHeight - box.svgHeight * scale) / 2;

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
  return computeFitTransform({
    svgWidth: dimensions.width,
    svgHeight: dimensions.height,
    containerWidth,
    containerHeight,
  });
}
