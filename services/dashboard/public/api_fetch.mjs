/**
 * Allowlisted operator API fetch helper.
 */

import { withCredentialedPolicy } from "./http.mjs";

export function createApiFetch(endpoints) {
  const allowed = Object.freeze([
    endpoints.login,
    endpoints.me,
    endpoints.logout,
    endpoints.stream,
  ]);

  function resolve(name) {
    if (name === "login") return endpoints.login;
    if (name === "me") return endpoints.me;
    if (name === "logout") return endpoints.logout;
    if (name === "stream") return endpoints.stream;
    return null;
  }

  return function apiFetch(name, init = {}) {
    const url = resolve(name);
    if (url != null && allowed.includes(url)) {
      return fetch(url, withCredentialedPolicy(init));
    }
    throw new Error("API endpoint is not on the allowlist");
  };
}
