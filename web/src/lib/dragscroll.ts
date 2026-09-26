
export function dragScroll(node: HTMLElement) {
  let startX = 0
  let startLeft = 0
  let pressed = false
  let dragged = false

  const down = (event: PointerEvent) => {
    if (event.pointerType !== 'mouse' || event.button !== 0) return
    pressed = true
    dragged = false
    startX = event.clientX
    startLeft = node.scrollLeft
  }

  const move = (event: PointerEvent) => {
    if (!pressed) return
    const dx = event.clientX - startX
    if (!dragged && Math.abs(dx) > 4) {
      dragged = true
      node.setPointerCapture(event.pointerId)
    }
    if (dragged) node.scrollLeft = startLeft - dx
  }

  const up = (event: PointerEvent) => {
    pressed = false
    if (node.hasPointerCapture(event.pointerId)) {
      node.releasePointerCapture(event.pointerId)
    }
  }

  const click = (event: MouseEvent) => {
    if (!dragged) return
    dragged = false
    event.preventDefault()
    event.stopPropagation()
  }

  const wheel = (event: WheelEvent) => {
    if (event.deltaX !== 0 || event.deltaY === 0) return
    if (node.scrollWidth <= node.clientWidth) return
    node.scrollLeft += event.deltaY
    event.preventDefault()
  }

  node.addEventListener('pointerdown', down)
  node.addEventListener('pointermove', move)
  node.addEventListener('pointerup', up)
  node.addEventListener('pointercancel', up)
  node.addEventListener('click', click, true)
  node.addEventListener('wheel', wheel, { passive: false })

  return {
    destroy() {
      node.removeEventListener('pointerdown', down)
      node.removeEventListener('pointermove', move)
      node.removeEventListener('pointerup', up)
      node.removeEventListener('pointercancel', up)
      node.removeEventListener('click', click, true)
      node.removeEventListener('wheel', wheel)
    },
  }
}
