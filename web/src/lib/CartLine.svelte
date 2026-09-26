<script lang="ts">
  import { shortWhy, uah, uahRound } from './format'
  import { pickLabel } from './picks'
  import { NO_PHOTO } from './ui'
  import { popover, togglePopover } from './popover.svelte'
  import type { CartLine } from './types'

  interface Props {
    line: CartLine
    once: boolean
    onToggleOnce: () => void
    onAction: () => void
    onQty: (next: number) => void
    onWhy: (() => void) | null
    kin?: number
    onCheaper?: (() => void) | null
  }

  const {
    line,
    once,
    onToggleOnce,
    onAction,
    onQty,
    onWhy,
    kin = 0,
    onCheaper = null,
  }: Props = $props()

  const weighed = $derived(line.unit !== 'шт' && line.unit !== 'уп')
  const step = $derived(line.step ?? (weighed ? 0.1 : 1))

  function bump(direction: 1 | -1) {
    const next = line.qty + direction * step
    onQty(Math.max(step, Math.round(next * 100) / 100))
  }

  let draft = $state('')

  $effect(() => {
    draft = String(line.qty).replace('.', ',')
  })

  function commit() {
    const parsed = Number(draft.replace(',', '.').replace(/[^\d.]/g, ''))
    if (Number.isFinite(parsed) && parsed > 0) {
      onQty(Math.max(step, Math.round(parsed * 100) / 100))
    } else {
      draft = String(line.qty).replace('.', ',')
    }
  }

  const atHome = $derived(line.reason === 'at_home')
  const substituted = $derived(line.reason === 'substituted')
  const whyId = $derived(`why:${line.externalProductId}`)
  const whyOpen = $derived(popover.id === whyId)
  const emoji = NO_PHOTO.line

  const why = $derived(
    once ? 'разова покупка · не для комори, прогноз не зміниться' : line.explanation,
  )
  const whyDetail = $derived(
    once
      ? 'Прогноз не зміниться: цю покупку агент не врахує в циклах.'
      : line.explanationDetail,
  )
</script>

<li
  class="row"
  class:risk={line.atRisk || line.needsApproval}
  class:home={atHome}
  class:swapped={substituted}
>
  <div class="thumb" aria-hidden="true">
    {#if line.imageUrl}
      <img src={line.imageUrl} alt="" loading="lazy" />
    {:else}
      {emoji}
    {/if}
  </div>

  <div class="body">
    <div class="name-row">
      {#if onWhy}
        <button class="name jump ellipsis" type="button" title="Чому саме цей" onclick={onWhy}>
          {line.name}
        </button>
      {:else}
        <span class="name ellipsis">{line.name}</span>
      {/if}
      {#if kin > 1}
        <span class="kin" title="кілька видів під одним словом: різний ритм і фасовка">1 з {kin}</span>
      {/if}
      {#if line.sliced}
        <span class="form" title="нарізаний">нарізаний</span>
      {/if}
    </div>

    <div class="sub">
      <div class="why ellipsis" class:once>{shortWhy(why)}</div>

      <button
        class="once-toggle"
        class:on={once}
        type="button"
        aria-pressed={once}
        title="разова покупка — не потрапить у залишки"
        onclick={onToggleOnce}
      >
        разово
      </button>

      <button
        class="i"
        class:on={whyOpen}
        type="button"
        data-popover
        aria-expanded={whyOpen}
        aria-label="Чому ця позиція тут"
        onclick={() => togglePopover(whyId)}
      >
        i
      </button>
    </div>

    {#if line.cheaper && onCheaper}
      <button class="cheaper" type="button" onclick={onCheaper}>
        <span class="cheaper-what ellipsis">{line.cheaper.name}</span>
        <span class="cheaper-gain">-{uahRound(line.cheaper.saving * line.qty)}</span>
      </button>
    {/if}
  </div>

  <div class="right num">
    {#if !atHome}
      <div class="qty">
        <button
          class="bump"
          type="button"
          aria-label="Менше: {line.name}"
          disabled={line.qty <= step}
          onclick={() => bump(-1)}
        >
          -
        </button>
        <input
          class="qty-input num"
          type="text"
          inputmode={step < 1 ? 'decimal' : 'numeric'}
          aria-label="Кількість: {line.name}"
          value={draft}
          oninput={(event) => (draft = event.currentTarget.value)}
          onfocus={(event) => event.currentTarget.select()}
          onblur={commit}
          onkeydown={(event) => {
            if (event.key === 'Enter') event.currentTarget.blur()
          }}
        />
        <span class="qty-unit">{line.unit}</span>
        <button class="bump" type="button" aria-label="Більше: {line.name}" onclick={() => bump(1)}>
          +
        </button>
      </div>
      <div class="price">{uah(line.qty * line.price)}</div>
      {#if weighed}
        <div class="per">{uah(line.price)}/{line.unit}</div>
      {/if}
      {#if line.saleNote}
        <div class="sale">{line.saleNote}</div>
      {/if}
    {/if}
  </div>

  <button
    class="act"
    class:add={atHome}
    type="button"
    title={atHome ? 'додати в замовлення' : 'прибрати'}
    aria-label={atHome ? `Додати ${line.name}` : `Прибрати ${line.name}`}
    onclick={onAction}
  >
    {atHome ? 'Додати' : '✕'}
  </button>

  {#if whyOpen}
    <div class="pop" data-popover role="note">
      <p class="pop-why">{why}</p>
      {#if whyDetail}
        <p class="pop-detail">{whyDetail}</p>
      {/if}
      {#if line.slicingNote}
        <p class="pop-detail">{line.slicingNote}</p>
      {/if}
      {#if onWhy}
        <button class="pop-jump" type="button" onclick={onWhy}>{pickLabel(line)} →</button>
      {/if}
    </div>
  {/if}
</li>

<style>
  .row {
    position: relative;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    border-bottom: 1px solid var(--hair);
    color: var(--ink);
  }

  .row.risk {
    background: var(--row-risk);
  }

  .row.home {
    background: var(--row-dim);
  }
  .row.swapped {
    background: var(--row-risk);
    box-shadow: inset 3px 0 0 var(--acc-edge);
  }

  .thumb {
    width: 36px;
    height: 36px;
    border-radius: 10px;
    flex: none;
    display: grid;
    place-items: center;
    font-size: 17px;
    overflow: hidden;
    background: var(--thumb-bg);
    border: 1px solid var(--hair);
  }

  .thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .body {
    flex: 1;
    min-width: 0;
  }

  .name-row {
    display: flex;
    align-items: baseline;
    gap: 6px;
    min-width: 0;
  }

  .form {
    flex: none;
    font-size: 10px;
    font-weight: 700;
    line-height: 1.6;
    padding: 0 6px;
    border-radius: 6px;
    color: var(--muted);
    background: var(--chip-bg);
    border: 1px solid var(--hair);
  }

  .name {
    font-size: 14px;
    font-weight: 700;
    letter-spacing: -0.15px;
    line-height: 1.25;
  }

  .name.jump {
    min-width: 0;
    padding: 0;
    text-align: left;
    color: inherit;
    background: transparent;
    border: 0;
    border-bottom: 1px dashed var(--hair-strong);
  }

  .row.risk .name {
    color: var(--risk-ink);
  }

  .row.home .name {
    color: var(--muted);
  }

  .sub {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 2px;
  }

  .why {
    flex: 1;
    min-width: 0;
    font-size: 11.5px;
    line-height: 1.3;
    color: var(--muted);
  }

  .row.risk .why {
    color: var(--warn);
  }

  .why.once {
    color: var(--badge);
  }

  .once-toggle,
  .i {
    position: relative;
    flex: none;
  }

  .once-toggle::after,
  .i::after {
    content: '';
    position: absolute;
    inset: -2px -3px -10px;
  }

  .cheaper {
    display: flex;
    align-items: baseline;
    gap: 6px;
    width: 100%;
    margin-top: 3px;
    padding: 3px 7px;
    border-radius: 6px;
    font-size: 11px;
    text-align: left;
    color: var(--faint);
    border: 1px dashed var(--hair-strong);
    background: transparent;
  }

  .cheaper-what {
    flex: 1;
    min-width: 0;
  }

  .cheaper-gain {
    font-weight: 700;
    font-variant-numeric: tabular-nums;
    color: var(--badge);
  }

  .once-toggle {
    font-size: 10.5px;
    font-weight: 700;
    padding: 3px 7px;
    border-radius: 6px;
    white-space: nowrap;
    color: var(--faint);
    border: 1px solid var(--hair-strong);
    background: transparent;
  }

  .once-toggle.on {
    color: var(--badge);
    border-color: var(--acc-edge);
    background: var(--acc-soft);
  }

  .i {
    width: 22px;
    height: 22px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    font-size: 11px;
    font-weight: 800;
    color: var(--faint);
    border: 1px solid var(--hair-strong);
    background: transparent;
  }

  .i.on {
    color: var(--badge);
    border-color: var(--acc-edge);
    background: var(--acc-soft);
  }

  .pop {
    position: absolute;
    top: calc(100% - 4px);
    right: 12px;
    width: min(250px, calc(100% - 24px));
    z-index: 50;
    padding: 11px 12px;
    border-radius: 14px;
    text-align: left;
    border: 1px solid var(--hair-strong);
    background: var(--menu-bg);
    backdrop-filter: blur(22px);
    box-shadow: 0 16px 38px rgb(0 0 0 / 0.4);
  }

  .pop-why {
    font-size: 12.5px;
    line-height: 1.45;
    color: var(--ink);
  }

  .pop-detail {
    font-size: 11.5px;
    line-height: 1.4;
    color: var(--muted);
    margin-top: 6px;
  }

  .pop-jump {
    margin-top: 9px;
    padding: 8px 11px;
    min-height: 40px;
    width: 100%;
    border-radius: 11px;
    font-size: 12px;
    font-weight: 700;
    text-align: left;
    color: var(--ink);
    border: 1px solid var(--hair-strong);
    background: var(--chip-bg);
  }

  .right {
    flex: none;
    min-width: 96px;
    text-align: right;
    white-space: nowrap;
  }

  .qty {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 2px;
    font-size: 12.5px;
    font-weight: 700;
  }

  .qty-input {
    width: 3.2ch;
    padding: 2px 0;
    font: inherit;
    text-align: right;
    color: var(--ink);
    border: none;
    border-bottom: 1px dashed var(--hair-strong);
    background: transparent;
    outline: none;
  }

  .qty-input:focus {
    border-bottom-color: var(--acc-edge);
  }

  .qty-unit {
    color: var(--muted);
    font-weight: 500;
  }

  .bump {
    position: relative;
    width: 20px;
    height: 20px;
    flex: none;
    display: grid;
    place-items: center;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 700;
    line-height: 1;
    color: var(--muted);
    border: 1px solid var(--hair-strong);
    background: transparent;
  }

  .bump::after {
    content: '';
    position: absolute;
    inset: -12px -2px;
  }

  .bump:disabled {
    opacity: 0.35;
    cursor: not-allowed;
  }

  .row.risk .bump {
    color: var(--warn);
  }

  .price {
    font-size: 12px;
    margin-top: 1px;
    color: var(--good);
  }

  .row.risk .price {
    color: var(--warn);
  }

  .per {
    font-size: 10.5px;
    margin-top: 1px;
    color: var(--muted);
  }

  .sale {
    font-size: 10.5px;
    font-weight: 700;
    margin-top: 2px;
    color: var(--good);
  }

  .act {
    flex: none;
    min-width: 34px;
    min-height: 44px;
    display: grid;
    place-items: center;
    border-radius: 9px;
    font-size: 14px;
    font-weight: 600;
    color: var(--faint);
    border: 1px solid transparent;
    background: transparent;
  }

  .act.add {
    font-size: 12px;
    padding: 0 10px;
    color: var(--ink);
    border-color: var(--hair-strong);
    background: var(--chip-bg);
  }

  @media (width <= 380px) {
    .row {
      gap: 8px;
      padding: 8px 10px;
    }

    .right {
      min-width: 86px;
    }

    .qty-input {
      width: 2.8ch;
    }

    .act {
      min-width: 30px;
    }

    .pop {
      right: 10px;
      width: calc(100% - 20px);
    }
  }
  .kin {
    flex: none;
    font-size: 11px;
    line-height: 1;
    padding: 3px 6px;
    border-radius: 999px;
    color: var(--muted);
    border: 1px solid currentColor;
    opacity: 0.7;
  }
</style>
