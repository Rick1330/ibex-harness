export const IBEX_VIDEO_POSTER = "/ibex-ascii-poster.webp";

export const IBEX_VIDEO_SOURCES = {
  light: {
    webm: "/ibex-ascii.webm",
    mp4: "/ibex-ascii.mp4",
  },
  dark: {
    webm: "/ibex-ascii-dark.webm",
    mp4: "/ibex-ascii-dark.mp4",
  },
} as const;

export type IbexVideoTheme = keyof typeof IBEX_VIDEO_SOURCES;
export type IbexVideoSources = (typeof IBEX_VIDEO_SOURCES)[IbexVideoTheme];

export function ibexVideoSourcesForTheme(theme: IbexVideoTheme) {
  return IBEX_VIDEO_SOURCES[theme];
}
