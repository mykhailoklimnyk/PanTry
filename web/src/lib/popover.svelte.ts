
export const popover = $state<{ id: string | null; modal: boolean }>({ id: null, modal: false })

/**
 * `modal` — для діалогів по центру екрана (бюджет, нове правило). Вони
 * закриваються по кліку поза, по Esc і по втраті фокуса, але НЕ по скролу:
 * діалог не прив'язаний до жодного рядка, тікати від прокрутки йому нікуди,
 * а в композері правила ще й лежить недописаний текст.
 */
export function togglePopover(id: string, modal = false): void {
  const closing = popover.id === id
  popover.id = closing ? null : id
  popover.modal = closing ? false : modal
}

export function closePopovers(): void {
  popover.id = null
  popover.modal = false
}

/**
 * Слухачі закриття. Повертає функцію відписки — викликати з `$effect`.
 */
export function watchDismiss(): () => void {
  const outside = (event: Event) => {
    const target = event.target
    if (target instanceof Element && target.closest('[data-popover]')) return
    closePopovers()
  }

  const onScroll = (event: Event) => {
    if (popover.modal) return
    outside(event)
  }

  const onKey = (event: KeyboardEvent) => {
    if (event.key === 'Escape') closePopovers()
  }

  document.addEventListener('click', outside)
  document.addEventListener('keydown', onKey)
  window.addEventListener('blur', closePopovers)
  window.addEventListener('scroll', onScroll, true)

  return () => {
    document.removeEventListener('click', outside)
    document.removeEventListener('keydown', onKey)
    window.removeEventListener('blur', closePopovers)
    window.removeEventListener('scroll', onScroll, true)
  }
}
