export async function copyJson(value: unknown): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(JSON.stringify(value, null, 2))
    return true
  } catch {
    return false
  }
}
