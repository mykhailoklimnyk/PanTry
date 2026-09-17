<script lang="ts">
  import { BUDGET_PRESETS } from './ui'
  import { loadWeekSpend } from './data'
  import type { Loaded } from './data'
  import type { SpendTarget, WeekSpend } from './types'
  import { plural, uahRound } from './format'

  interface Props {
    budget: number
    /**
     * Ціль і пресети з ОНЛАЙН-замовлень гостя (#212). `null` — історію
     * прочитати не вдалось, і тоді працюють наші числа.
     */
    spend: SpendTarget | null
    /** У кошику панель повна: з підказкою і кнопкою «зберегти як постійний». */
    full?: boolean
    onBudget: (value: number) => void
    /** «Зберегти як постійний»: число лягає в браузер і живе між збірками. */
    onSave: () => void
    onClose: () => void
  }

  const { budget, spend, full = false, onBudget, onSave, onClose }: Props = $props()

  const presets = $derived(spend?.presets.length ? spend.presets : BUDGET_PRESETS)

  const NUMBER = new Intl.NumberFormat('uk-UA')

  const STEP = 100
  const MIN = 300

  let draft = $state('')

  $effect(() => {
    draft = String(budget)
  })

  let week = $state<Loaded<WeekSpend> | null>(null)

  $effect(() => {
    void loadWeekSpend().then((loaded) => (week = loaded))
  })

  function commit() {
    const parsed = Number.parseInt(draft.replace(/\D/g, ''), 10)
    if (Number.isFinite(parsed) && parsed >= MIN) onBudget(parsed)
    else onBudget(MIN)
  }
</script>

<div class="budget">
  <div class="head">
    <span class="label">зібрати приблизно на</span>
    <span class="hint">агент ріже добране з циклів</span>
  </div>

  {#if full}
    <p class="note">
      Межа на один кошик, не на тиждень. Назване тобою лишається завжди — навіть якщо
      кошик через це вище межі; зняте видно поіменно в кошику.
    </p>
  {/if}

  <p class="week" data-tour="week-spend">
    {#if week === null}
      рахую витрати тижня…
    {:else if week.ok && week.data.receipts === 0}
      цього тижня покупок ще не було
    {:else if week.ok}
      цього тижня вже витрачено <strong>{uahRound(week.data.spent)}</strong> ·
      {plural(week.data.receipts, { one: 'чек', few: 'чеки', many: 'чеків' })} з понеділка
    {:else}
      витрати тижня не порахувались
    {/if}
  </p>

  <div class="stepper">
    <button
      class="step"
      type="button"
      aria-label="Менше на {STEP} ₴"
      onclick={() => onBudget(Math.max(MIN, budget - STEP))}
    >
      -
    </button>
    <div class="value">
      <input
        class="num"
        type="text"
        inputmode="numeric"
        aria-label="Межа на цей кошик, гривень"
        value={draft}
        oninput={(event) => (draft = event.currentTarget.value.replace(/\D/g, ''))}
        onfocus={(event) => event.currentTarget.select()}
        onblur={commit}
        onkeydown={(event) => {
          if (event.key === 'Enter') event.currentTarget.blur()
        }}
      />
      <span class="unit">₴</span>
    </div>
    <button
      class="step"
      type="button"
      aria-label="Більше на {STEP} ₴"
      onclick={() => onBudget(budget + STEP)}
    >
      +
    </button>
  </div>

  {#if spend !== null}
    <p class="from">{spend.note}</p>
  {/if}

  <div class="presets">
    {#each presets as preset (preset)}
      <button
        class="preset num"
        class:on={budget === preset}
        type="button"
        aria-pressed={budget === preset}
        onclick={() => onBudget(preset)}
      >
        {NUMBER.format(preset)}
      </button>
    {/each}
  </div>

  {#if full}
    <div class="actions">
      <button class="secondary" type="button" onclick={onClose}>На цей раз</button>
      <button class="primary" type="button" onclick={() => (onSave(), onClose())}>
        Зберегти як постійний
      </button>
    </div>
  {/if}
</div>

<style>
  .budget {
    padding: 13px 14px;
    border-radius: 14px;
    border: 1px solid var(--hair-strong);
    background: var(--chip-bg);
  }

  .head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px;
  }

  .label {
    font-size: 12px;
    color: var(--muted);
  }

  .hint {
    font-size: 11.5px;
    color: var(--faint);
  }

  .note {
    margin: 9px 0 0;
    font-size: 11.5px;
    line-height: 1.45;
    color: var(--faint);
  }

  .week {
    margin: 10px 0 0;
    padding-top: 9px;
    border-top: 1px solid var(--hair);
    font-size: 12px;
    line-height: 1.45;
    color: var(--muted);
  }

  .week strong {
    color: var(--ink);
    font-weight: 800;
  }

  .stepper {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 10px;
  }

  .step {
    width: 40px;
    min-height: 44px;
    display: grid;
    place-items: center;
    border-radius: 10px;
    font-size: 17px;
    font-weight: 700;
    line-height: 1;
    color: var(--ink);
    border: 1px solid var(--hair-strong);
    background: transparent;
  }

  .value {
    flex: 1;
    display: flex;
    align-items: baseline;
    justify-content: center;
    gap: 4px;
    font-size: 22px;
    font-weight: 800;
    letter-spacing: -0.6px;
  }

  .value input {
    width: 5ch;
    padding: 4px 2px;
    font: inherit;
    text-align: right;
    color: var(--ink);
    border: none;
    border-bottom: 1px dashed var(--hair-strong);
    background: transparent;
    outline: none;
  }

  .value input:focus {
    border-bottom-color: var(--acc-edge);
  }

  .unit {
    color: var(--muted);
  }

  .from {
    margin: 8px 0 0;
    color: var(--muted);
    font-size: 12px;
  }

  .presets {
    display: flex;
    gap: 7px;
    margin-top: 11px;
  }

  .preset {
    flex: 1;
    min-height: 44px;
    padding: 0 4px;
    border-radius: 10px;
    font-size: 12.5px;
    font-weight: 700;
    color: var(--muted);
    border: 1px solid var(--hair-strong);
    background: transparent;
  }

  .preset.on {
    color: var(--badge);
    border-color: var(--acc-edge);
    background: var(--acc-soft);
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
    flex: 1.4;
    min-height: 44px;
    padding: 0 8px;
    border-radius: 11px;
    font-size: 12.5px;
    font-weight: 800;
    white-space: nowrap;
    color: var(--pri-ink);
    background: var(--pri-bg);
  }

  @media (width <= 380px) {
    .actions {
      flex-direction: column;
    }

    .presets {
      gap: 5px;
    }

    .preset {
      font-size: 11.5px;
    }

    .value {
      font-size: 20px;
    }
  }
</style>
