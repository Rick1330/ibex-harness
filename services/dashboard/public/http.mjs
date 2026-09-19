/**
 * Shared fetch policy for operator API calls that may carry cookies or a PAT body.
 * redirect:"error" prevents browsers from forwarding credentials to Location targets
 * on 301/302/303/307/308.
 */

export const CREDENTIALED_REDIRECT = "error";

/** Merge caller init with credentials + fail-closed redirect policy (policy wins). */
export function withCredentialedPolicy(init = {}) {
  return {
    ...init,
    credentials: "include",
    redirect: CREDENTIALED_REDIRECT,
  };
}
