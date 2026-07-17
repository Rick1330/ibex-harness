/** Inline script applied before paint to avoid theme flash on reload. */
export function ThemeNoFlashScript() {
  const script = `(function(){try{var t=localStorage.getItem("theme");var d=window.matchMedia("(prefers-color-scheme: dark)").matches;var dark=t==="dark"||(t!=="light"&&d);document.documentElement.classList.toggle("dark",dark);}catch(e){}})();`;

  return (
    <script
      id="theme-no-flash"
      dangerouslySetInnerHTML={{ __html: script }}
    />
  );
}
