import Script from "next/script";

const THEME_BOOTSTRAP = `(function(){try{var t=localStorage.getItem("ibex-theme")||localStorage.getItem("theme");var d=window.matchMedia("(prefers-color-scheme: dark)").matches;var dark=t==="dark"||((!t||t==="system")&&d);if(t==="light")dark=false;document.documentElement.classList.toggle("dark",dark);}catch(e){}})();`;

/** Inline script applied before paint to avoid theme flash on reload. */
export function ThemeNoFlashScript() {
  return (
    <Script id="theme-no-flash" strategy="beforeInteractive">
      {THEME_BOOTSTRAP}
    </Script>
  );
}
