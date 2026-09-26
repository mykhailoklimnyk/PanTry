
export const popover = $state<{ id: string | null; modal: boolean }>({ id: null, modal: false })

export function togglePopover(id: string, modal = false): void {
  const closing = popover.id === id
  popover.id = closing ? null : id
  popover.modal = closing ? false : modal
}

export function closePopovers(): void {
  popover.id = null
  popover.modal = false
}

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
