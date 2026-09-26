
declare const __BUILD_COMMIT__: string
declare const __BUILD_REPO__: string
declare const __BUILD_VERSION__: string

const COMMIT: string = __BUILD_COMMIT__

export const UI_VERSION: string = __BUILD_VERSION__

const REPO: string = __BUILD_REPO__

export const SHORT: string = COMMIT.slice(0, 9)

export function commitUrl(sha: string = COMMIT): string | null {
  if (!REPO || !sha) return null
  return `${REPO}/commit/${sha}`
}

export function matches(backend: string | null | undefined): boolean | null {
  if (!backend || !COMMIT) return null
  return backend === COMMIT
}
