<script lang="ts">
  import type { Loaded } from './data'
  import { priceOf } from './delivery'
  import { kg, uahRound } from './format'
  import type { DeliveryOption } from './types'

  interface Props {
    options: DeliveryOption[]
    loaded?: Loaded<DeliveryOption[]> | null
    selected: string
    onSelect: (id: string) => void
    onRetry?: () => void
  }

  const { options, loaded = null, selected, onSelect, onRetry }: Props = $props()

  const waiting = $derived(loaded === null)

  const live = $derived(options.filter((option) => option.available).length)

  function limits(option: DeliveryOption): string {
    const parts: string[] = []
    if (option.minOrder) parts.push(`від ${uahRound(option.minOrder)}`)
    if (option.maxWeightKg) parts.push(`до ${kg(option.maxWeightKg)}`)
    return parts.join(' · ')
  }
</script>

{#if options.length === 0}
  <p class="only">
    {waiting
      ? 'Умови доставки ще читаються'
      : 'Умов доставки я не прочитав — способів тут не покажу'}
    {#if !waiting && onRetry}
      <button class="again" type="button" onclick={onRetry}>Прочитати ще раз</button>
    {/if}
  </p>
{:else if live <= 1}
  <p class="only">
    {live === 0
      ? 'За цією адресою «Сільпо» зараз не пропонує жодного способу'
      : 'За цією адресою «Сільпо» пропонує один спосіб'} — решта нижче каже, чому ні
  </p>
{/if}

<ul class="options">
  {#each options as option (option.id)}
    <li>
      <button
        class="option"
        class:on={option.id === selected}
        type="button"
        aria-pressed={option.id === selected}
        disabled={!option.available}
        onclick={() => onSelect(option.id)}
      >
        <span class="dot" aria-hidden="true"></span>

        <span class="text">
          <span class="label">{option.label}</span>
          <span class="note">
            {option.available ? option.note : option.unavailableReason}
          </span>
        </span>

        <span class="facts num">
          <span class="cost">{priceOf(option)}</span>
          {#if limits(option)}
            <span class="limit">{limits(option)}</span>
          {/if}
        </span>
      </button>
    </li>
  {/each}
</ul>

<style>
  .again {
    margin-left: 6px;
    padding: 0;
    border: 0;
    background: none;
    color: inherit;
    font: inherit;
    text-decoration: underline;
    cursor: pointer;
  }

  .only {
    margin: 0 0 8px;
    font-size: 12px;
    line-height: 1.4;
    color: var(--muted);
  }

  .options {
    display: flex;
    flex-direction: column;
    gap: 7px;
  }

  .option {
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    text-align: left;
    padding: 10px 12px;
    min-height: 56px;
    border-radius: 12px;
    color: var(--ink);
    border: 1px solid var(--hair-strong);
    background: transparent;
  }

  .option.on {
    border-color: var(--acc-edge);
    background: var(--acc-soft);
  }

  .option:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  .dot {
    width: 14px;
    height: 14px;
    border-radius: 50%;
    flex: none;
    border: 2px solid var(--hair-strong);
  }

  .option.on .dot {
    border-color: var(--badge);
    background: var(--badge);
  }

  .text {
    flex: 1;
    min-width: 0;
  }

  .label {
    display: block;
    font-size: 13.5px;
    font-weight: 700;
    line-height: 1.25;
  }

  .note {
    display: block;
    font-size: 11.5px;
    color: var(--muted);
    margin-top: 2px;
    line-height: 1.3;
  }

  .facts {
    flex: none;
    text-align: right;
    white-space: nowrap;
  }

  .cost {
    display: block;
    font-size: 12.5px;
    font-weight: 700;
  }

  .option.on .cost {
    color: var(--badge);
  }

  .limit {
    display: block;
    font-size: 11px;
    color: var(--faint);
    margin-top: 2px;
  }
</style>
