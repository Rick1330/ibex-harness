import type { ShikiTransformer } from "shiki";

function shouldAttachLanguage(lang?: string): boolean {
  if (!lang) return false;
  return lang !== "plaintext" && lang !== "text";
}

/** Attach `data-language` to Shiki `<pre>` nodes for the Pre component tab label. */
export function attachCodeLanguageTransformer(): ShikiTransformer {
  return {
    name: "ibex:attach-code-language",
    pre(node) {
      const lang = this.options.lang;
      if (!shouldAttachLanguage(lang)) return;

      const element = node as {
        properties?: Record<string, string | number | boolean | (string | number | boolean)[]>;
      };
      element.properties ??= {};
      element.properties["data-language"] = lang;
    },
  };
}
