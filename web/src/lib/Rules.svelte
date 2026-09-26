<script lang="ts">
  import BudgetPanel from './BudgetPanel.svelte'
  import DeliveryPicker from './DeliveryPicker.svelte'
  import Dictaphone from './Dictaphone.svelte'
  import MicButton from './MicButton.svelte'
  import { dragScroll } from './dragscroll'
  import { RULE_SUGGESTIONS, targetChip } from './ui'
  import { popover, togglePopover } from './popover.svelte'
  import { voiceAvailable } from './speech'
  import type { Loaded } from './data'
  import type { DeliveryOption, Exclusion, Pantry, SpendTarget } from './types'

  interface Props {
    rules: Exclusion[]
    note?: string | null
    deliveryOptions?: DeliveryOption[]
    deliveryLoaded?: Loaded<DeliveryOption[]> | null
    onDeliveryRetry?: () => void
    delivery?: string
    budget: number
    spend: SpendTarget | null
    pantrySource?: Omit<Pantry, 'items'> | null
    draft: string
    strip?: boolean
    modeLabel?: string | null
    stale?: boolean
    staleLabel?: string
    onToggleRule: (id: string) => void
    onRemoveRule: (id: string) => void
    onDraft: (value: string) => void
    onAddRule: () => void
    onBudget: (value: number) => void
    onSave: () => void
    onDelivery?: (id: string) => void
    onStale?: () => void
  }

  const {
    rules,
    note = null,
    deliveryOptions = [],
    deliveryLoaded = null,
    onDeliveryRetry,
    delivery = '',
    budget,
    spend,
    pantrySource = null,
    draft,
    strip = false,
    modeLabel = null,
    stale = false,
    staleLabel = '',
    onToggleRule,
    onRemoveRule,
    onDraft,
    onAddRule,
    onBudget,
    onSave,
    onDelivery,
    onStale,
  }: Props = $props()

  const inputId = $derived(strip ? 'rule-cart' : 'rule-start')

  const budgetId = $derived(strip ? 'budget-cart' : 'budget-start')
  const budgetOpen = $derived(popover.id === budgetId)
  const composerId = $derived(strip ? 'composer-cart' : 'composer-start')
  const composerOpen = $derived(popover.id === composerId)
  const deliveryOpen = $derived(popover.id === 'delivery')

  let dictOpen = $state(false)
  let voiceNote = $state<string | null>(null)
  const deliveryLabel = $derived(
    deliveryOptions.find((o) => o.id === delivery)?.label ??
      (deliveryLoaded === null || deliveryLoaded.ok === false ? 'спосіб не прочитався' : ''),
  )

  function onKey(event: KeyboardEvent) {
    if (event.key === 'Enter') {
      event.preventDefault()
      onAddRule()
    }
  }
</script>

<div class="rules" class:strip>
  <div class="row" class:hscroll={strip} use:dragScroll>
    {#if stale && onStale}
      <button class="chip solo rebuild" type="button" onclick={onStale}>
        {staleLabel}
      </button>
    {/if}

    <button
      class="chip solo"
      class:on={budgetOpen}
      type="button"
      data-popover
      aria-expanded={budgetOpen}
      onclick={() => togglePopover(budgetId, true)}
    >
      {targetChip(budget, pantrySource)}
    </button>

    {#each rules as rule (rule.id)}
      {#if rule.permanent}
        <span class="chip on locked" title="з профілю «Сільпо» — міняється там">
          <span class="label">{rule.label}</span>
          <span class="from">◆</span>
        </span>
      {:else}
        <div class="chip" class:on={rule.active}>
          <button
            class="label"
            type="button"
            aria-pressed={rule.active}
            onclick={() => onToggleRule(rule.id)}
          >
            {rule.label}
          </button>
          <button
            class="drop"
            type="button"
            aria-label="Видалити правило «{rule.label}»"
            onclick={() => onRemoveRule(rule.id)}
          >
            ×
          </button>
        </div>
      {/if}
    {/each}

    {#if deliveryLabel && onDelivery}
      <button
        class="chip solo"
        class:on={deliveryOpen}
        type="button"
        data-popover
        aria-expanded={deliveryOpen}
        onclick={() => togglePopover('delivery', true)}
      >
        {deliveryLabel}
      </button>
    {/if}

    {#if modeLabel}
      <span class="chip solo accent">режим: {modeLabel}</span>
    {/if}

    <button
      class="chip solo add"
      class:on={composerOpen}
      type="button"
      data-popover
      aria-expanded={composerOpen}
      onclick={() => togglePopover(composerId, true)}
    >
      + правило
    </button>

  </div>

  {#if note}
    <p class="note-row">{note}</p>
  {/if}

  {#if composerOpen}
    <div class="scrim" aria-hidden="true"></div>
    <div class="sheet" data-popover role="dialog" aria-modal="true" aria-label="Своє правило">
      <div class="composer">
        <label class="caption" for={inputId}>
          своє правило — його читає агент, а не фільтр
        </label>
        <div class="field">
          <span class="voice-wrap">
            <input
              id={inputId}
              type="text"
              value={draft}
              placeholder="напр. без свинини, але індичку можна"
              autocomplete="off"
              oninput={(event) => onDraft(event.currentTarget.value)}
              onkeydown={onKey}
            />
            {#if voiceAvailable()}
              <span class="mic-slot"><MicButton
                active={dictOpen}
                label="надиктувати правило"
                onClick={() => {
                  voiceNote = null
                  dictOpen = true
                }}
              /></span>
            {/if}
          </span>
        </div>
        {#if voiceNote}
          <p class="voice-error" role="alert">{voiceNote}</p>
        {/if}
        <Dictaphone
          open={dictOpen}
          onPhrase={(text) => onDraft(draft.trim() ? `${draft.trim()} ${text}` : text)}
          onClose={() => (dictOpen = false)}
          onError={(message) => (voiceNote = message)}
        />

        <div class="suggest">
          {#each RULE_SUGGESTIONS as hint (hint)}
            <button class="hint" type="button" onclick={() => onDraft(hint)}>{hint}</button>
          {/each}
        </div>

        <p class="note">
          Діє на цей тиждень. Агент не просто викине позиції — він перебалансує
          кошик і скаже в трейсі, чим саме замінив.
        </p>

        <div class="actions">
          <button class="secondary" type="button" onclick={() => togglePopover(composerId, true)}>
            Закрити
          </button>
          <button class="primary" type="button" disabled={!draft.trim()} onclick={onAddRule}>
            Додати правило
          </button>
        </div>
      </div>
    </div>
  {/if}

  {#if deliveryOpen && onDelivery}
    <div class="scrim" aria-hidden="true"></div>
    <div class="sheet" data-popover role="dialog" aria-modal="true" aria-label="Як забирати">
      <div class="composer">
        <div class="caption">як забирати</div>
        <div class="picker">
          <DeliveryPicker
            options={deliveryOptions}
            loaded={deliveryLoaded}
            onRetry={onDeliveryRetry}
            selected={delivery}
            onSelect={(id) => {
              onDelivery(id)
              togglePopover('delivery', true)
            }}
          />
        </div>
      </div>
    </div>
  {/if}

  {#if budgetOpen}
    <div class="scrim" aria-hidden="true"></div>
    <div class="sheet" data-popover role="dialog" aria-modal="true" aria-label="Межа на цей кошик">
      <BudgetPanel
        {budget}
        {spend}
        full
        {onBudget}
        {onSave}
        onClose={() => togglePopover(budgetId, true)}
      />
    </div>
  {/if}
</div>

<style>
  .rules {
    position: relative;
  }

  .row {
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
  }

  .rules.strip .row {
    flex-wrap: nowrap;
    gap: 8px;
    padding: 13px 16px 12px;
    overflow-x: auto;
    scrollbar-width: none;
    cursor: grab;
  }

  .rules.strip .row:active {
    cursor: grabbing;
  }

  .rules.strip .row::-webkit-scrollbar {
    display: none;
  }

  .chip {
    display: flex;
    align-items: center;
    flex: none;
    border-radius: 11px;
    font-size: 13px;
    font-weight: 600;
    white-space: nowrap;
    color: var(--ink);
    border: 1px solid var(--hair);
    background: var(--chip-bg);
  }

  .chip.on {
    color: var(--badge);
    border-color: var(--acc-edge);
    background: var(--acc-soft);
  }

  .label,
  .chip.solo {
    padding: 0 12px;
    min-height: 44px;
    color: inherit;
    display: flex;
    align-items: center;
  }

  .label {
    font: inherit;
  }

  .rules.strip .label,
  .rules.strip .chip.solo {
    min-height: 38px;
    padding: 0 12px;
  }

  .locked .label {
    padding: 0 4px 0 12px;
    min-height: 44px;
    display: flex;
    align-items: center;
    font: inherit;
  }

  .rules.strip .locked .label {
    min-height: 38px;
  }

  .from {
    padding-inline-end: 10px;
    font-size: 8px;
    line-height: 1;
    opacity: 0.55;
  }

  .drop {
    align-self: stretch;
    padding: 0 10px 0 2px;
    font-size: 16px;
    line-height: 1;
    color: var(--muted);
  }

  .chip.on .drop {
    color: var(--badge);
  }

  .chip.add {
    color: var(--muted);
    border-style: dashed;
    border-color: var(--hair-strong);
    background: transparent;
  }

  .chip.add.on {
    color: var(--badge);
    border-style: solid;
    border-color: var(--acc-edge);
    background: var(--acc-soft);
  }

  .chip.accent {
    padding: 0 12px;
    min-height: 38px;
    display: flex;
    align-items: center;
    color: var(--badge);
    border-color: var(--acc-edge);
    background: var(--acc-soft);
  }

  .chip.rebuild {
    color: var(--warn);
    border-color: rgb(232 147 90 / 0.55);
    background: transparent;
    font-weight: 700;
  }

  .scrim {
    position: fixed;
    inset: 0;
    z-index: 70;
    background: rgb(0 0 0 / 0.5);
    touch-action: none;
  }

  .sheet {
    position: fixed;
    z-index: 71;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: min(360px, calc(100vw - 32px));
    border-radius: 14px;
    box-shadow: 0 24px 60px rgb(0 0 0 / 0.5);
  }

  .sheet :global(> *) {
    background: var(--menu-bg);
    backdrop-filter: blur(22px) saturate(160%);
  }

  .picker {
    margin-top: 10px;
  }

  .composer {
    padding: 12px 13px;
    border-radius: 14px;
    border: 1px solid var(--hair-strong);
  }

  .caption {
    display: block;
    font-size: 12px;
    color: var(--muted);
  }

  .field {
    display: flex;
    align-items: stretch;
    gap: 8px;
    margin-top: 9px;
  }

  input {
    flex: 1;
    min-width: 0;
    width: 100%;
    padding: 11px 12px;
    min-height: 44px;
    border-radius: 11px;
    font-size: 14px;
    color: var(--ink);
    border: 1px solid var(--hair-strong);
    background: transparent;
    outline: none;
  }

  input::placeholder {
    color: var(--faint);
  }

  .suggest {
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
    margin-top: 9px;
  }

  .hint {
    padding: 8px 11px;
    min-height: 40px;
    border-radius: 10px;
    font-size: 12.5px;
    font-weight: 600;
    white-space: nowrap;
    color: var(--muted);
    border: 1px solid var(--hair-strong);
    background: transparent;
  }

  .note-row {
    margin: 8px 0 0;
    font-size: 11.5px;
    line-height: 1.45;
    color: var(--warn);
  }

  .rules.strip .note-row {
    margin: 0 0 10px;
    padding-inline: 16px;
  }

  .voice-error {
    margin-top: 8px;
    font-size: 11.5px;
    color: var(--warn);
    line-height: 1.4;
  }

  .note {
    font-size: 11.5px;
    color: var(--faint);
    margin-top: 10px;
    line-height: 1.45;
  }

  .actions {
    display: flex;
    gap: 8px;
    margin-top: 11px;
  }

  .secondary {
    flex: 1;
    min-height: 44px;
    border-radius: 11px;
    font-size: 13px;
    font-weight: 700;
    color: var(--ink);
    border: 1px solid var(--hair-strong);
    background: transparent;
  }

  .primary {
    flex: 1.3;
    min-height: 44px;
    padding: 0 10px;
    border-radius: 11px;
    font-size: 13px;
    font-weight: 800;
    white-space: nowrap;
    color: var(--pri-ink);
    background: var(--pri-bg);
  }

  .primary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  @media (width <= 380px) {
    .rules.strip .row {
      padding-inline: 12px;
    }

    .sheet {
      width: calc(100vw - 24px);
    }

    .actions {
      flex-direction: column;
    }
  }
  .voice-wrap {
    position: relative;
    display: flex;
    flex: 1;
    min-width: 0;
  }
  .voice-wrap > input {
    flex: 1;
    min-width: 0;
    padding-right: 48px;
  }
  .mic-slot {
    position: absolute;
    right: 6px;
    top: 50%;
    translate: 0 -50%;
  }
</style>
