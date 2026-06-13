export const GITHUB_OWNER = "Rick1330";
export const GITHUB_REPO = "ibex-harness";
export const GITHUB_BRANCH = "main";

/** Repo-relative path for Edit-on-GitHub links. */
export function getContentFilePath(relativePath: string): string {
  const normalized = relativePath.replace(/\\/g, "/");
  return `docs/app/content/docs/${normalized}`;
}

export function getEditOnGitHubUrl(relativePath: string): string {
  const path = getContentFilePath(relativePath);
  return `https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}/blob/${GITHUB_BRANCH}/${path}`;
}
