
import { forgetAutoSwap } from './consent'
import { forget as forgetRuleCache } from './rules'
import type { GuestLink } from './types'

export interface Link {
  ready: boolean
  backend: boolean
  connected: boolean
  expiresAt: string | null
  note: string | null
  greet: number | null
  llmKey: boolean
}

export const link: Link = $state({
  ready: false,
  backend: false,
  connected: false,
  expiresAt: null,
  note: null,
  greet: null,
  llmKey: false,
})

export async function refresh(): Promise<void> {
  try {
    const response = await fetch('/api/auth/session', {
      headers: { accept: 'application/json' },
    })
    if (!response.ok) throw new Error(String(response.status))
    const reply = (await response.json()) as GuestLink
    link.backend = true
    link.connected = reply.connected === true
    link.expiresAt = reply.expiresAt ?? null
    link.note = reply.reason ?? null
    link.greet = reply.greet ?? null
    link.llmKey = reply.llmKey === true
  } catch {
    link.backend = false
    link.connected = false
    link.expiresAt = null
    link.greet = null
    link.llmKey = false
  } finally {
    link.ready = true
  }
}

export function dropped(note: string): void {
  link.connected = false
  link.expiresAt = null
  link.note = note
}

export function greeted(): void {
  link.greet = null
}

export function connectUrl(): string {
  return `/api/auth/start?return_to=${encodeURIComponent(location.pathname)}`
}

export async function disconnect(): Promise<void> {
  forgetRuleCache()
  forgetAutoSwap()
  try {
    await fetch('/api/auth/logout', { method: 'POST' })
  } catch {
  }
  await refresh()
}


export async function saveLlmKey(key: string): Promise<string | null> {
  try {
    const response = await fetch('/api/auth/llm-key', {
      method: 'PUT',
      headers: { 'content-type': 'application/json', accept: 'application/json' },
      body: JSON.stringify({ key }),
    })
    if (!response.ok) {
      const reply = (await response.json().catch(() => null)) as { detail?: string } | null
      return reply?.detail ?? 'ключ не зберігся — спробуй ще раз'
    }
    link.llmKey = true
    return null
  } catch {
    return 'ключ не зберігся — мережа не відповіла'
  }
}

export async function forgetLlmKey(): Promise<void> {
  try {
    await fetch('/api/auth/llm-key', { method: 'DELETE' })
  } finally {
    link.llmKey = false
  }
}
