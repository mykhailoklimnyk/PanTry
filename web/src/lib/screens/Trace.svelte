<script lang="ts">
  import Back from '../Back.svelte'
  import { copyJson } from '../clipboard'
  import { plural, seconds, stepTime, uah, usd } from '../format'
  import { tollNote } from '../ui'
  import { hasPick, pickId, pickLabel } from '../picks'
  import type { Basket, CartLine, Toll } from '../types'

  interface Props {
    basket: Basket
    extras: CartLine[]
    focus: string | null
    logOpen: boolean
    debug?: boolean
    toll?: Toll | null
    onToggleLog: () => void
    onBack: () => void
  }

  const {
    basket,
    extras,
    focus,
    logOpen,
    debug = false,
    toll = null,
    onToggleLog,
    onBack,
  }: Props = $props()

  const decisions = $derived(basket.trace.filter((step) => step.decision))

  let clearedTo = $state<number | null>(null)
  const kept = $derived((step: { seq: number }) => clearedTo === null || step.seq > clearedTo)
  const shown = $derived(decisions.filter(kept))
  const journal = $derived(basket.trace.filter(kept))
  const hiddenSteps = $derived(basket.trace.length - journal.length)

  const picks = $derived([...basket.lines, ...extras].filter(hasPick))

  $effect(() => {
    if (focus === null) return
    document.getElementById(pickId(focus))?.scrollIntoView({ block: 'center' })
  })

  let copied = $state<string | null>(null)

  async function copyStep(id: string, step: unknown) {
    copied = (await copyJson(step)) ? id : `${id}:fail`
    setTimeout(() => (copied = null), 1600)
  }

  function copyLabel(id: string): string {
    if (copied === id) return 'скопійовано'
    if (copied === `${id}:fail`) return 'не вдалося'
    return 'копіювати крок'
  }

  async function copyAll() {
    copied = (await copyJson(journal)) ? 'all' : 'all:fail'
    setTimeout(() => (copied = null), 1600)
  }

  const allLabel = $derived(
    copied === 'all'
      ? `скопійовано ${journal.length}`
      : copied === 'all:fail'
        ? 'не вдалося'
        : `копіювати всі кроки (${journal.length})`,
  )

  function json(value: unknown): string {
    return JSON.stringify(value, null, 1)
  }

  const tollLine = $derived(tollNote(toll))

  const stats = $derived([
    basket.stats.orders > 0
      ? {
          n: `${basket.stats.receipts}+${basket.stats.orders}`,
          label: 'чеків і замовлень',
        }
      : { n: String(basket.stats.receipts), label: 'чеків прочитано' },
    { n: String(basket.stats.cycled), label: 'товари в циклі' },
    basket.stats.costUsd > 0
      ? { n: usd(basket.stats.costUsd), label: 'вартість прогону' }
      : { n: String(basket.stats.tokensIn + basket.stats.tokensOut), label: 'токенів моделі' },
  ])
</script>

<div class="trace">
  <div class="top">
    <Back label="До кошика" onClick={onBack} />
    <h1>Що зробив агент</h1>
  </div>

  {#if hiddenSteps > 0}
    <p class="lede">
      На екрані — {plural(shown.length, {
        one: 'рішення',
        few: 'рішення',
        many: 'рішень',
      })} після очищення. Решту сховано з показу: кошик і робота агента від цього не
      змінились.
    </p>
  {:else}
    <p class="lede">
      Агент ухвалив {plural(shown.length, {
        one: 'рішення',
        few: 'рішення',
        many: 'рішень',
      })}, збираючи твій кошик. Кожне видно цілком — з чим агент працював і чому вирішив
      саме так.
    </p>
  {/if}

  {#if debug}
    <p class="debug-strip" data-testid="trace-debug">
      режим дебагу: під кожним рішенням стоять аргументи кроку — те, що фраза
      віддала цифрам
    </p>
  {/if}

  <div class="stats">
    {#each stats as stat (stat.label)}
      <div class="stat">
        <div class="n num">{stat.n}</div>
        <div class="l">{stat.label}</div>
      </div>
    {/each}
  </div>

  <div class="clearing">
    {#if hiddenSteps > 0}
      <button class="clear" type="button" onclick={() => (clearedTo = null)}>
        Показати сховане: {plural(hiddenSteps, {
          one: 'крок',
          few: 'кроки',
          many: 'кроків',
        })}
      </button>
    {:else if basket.trace.length > 0}
      <button
        class="clear"
        type="button"
        onclick={() => (clearedTo = Math.max(...basket.trace.map((step) => step.seq)))}
      >
        Очистити показ
      </button>
    {/if}
    {#if journal.length > 0}
      <button class="clear" type="button" onclick={copyAll}>{allLabel}</button>
    {/if}
  </div>

  <div class="cards">
    {#each shown as step}
      <article class="card">
        <div class="card-head">
          <h2>{step.decision}</h2>
          {#if step.tag}
            <span class="tag" class:good={step.tagTone === 'good'} class:warn={step.tagTone === 'warn'}>
              {step.tag}
            </span>
          {/if}
        </div>
        <p class="body">{step.resultSummary}</p>
        {#if debug && Object.keys(step.args).length > 0}
          <pre class="mono step-args">{json(step.args)}</pre>
        {/if}
        <div class="card-foot">
          <button class="copy" type="button" onclick={() => copyStep(String(step.seq), step)}>
            {copyLabel(String(step.seq))}
          </button>
          <span class="mono call">{step.tool} · {stepTime(step.durationMs)}</span>
        </div>
      </article>
    {/each}
  </div>

  {#if picks.length > 0}
    <h2 class="section">Чому саме ці позиції</h2>
    <div class="cards">
      {#each picks as line (line.externalProductId)}
        <article
          class="card"
          class:focused={line.externalProductId === focus}
          id={pickId(line.externalProductId)}
          data-pick={line.externalProductId}
        >
          <div class="card-head">
            <h2>{line.name}</h2>
            <span class="tag">{pickLabel(line)}</span>
          </div>
          <p class="body">{line.explanationDetail ?? line.explanation}</p>
          {#if line.considered.length > 0}
            <ul class="rejected">
              {#each line.considered as other (other.externalProductId)}
                <li>
                  <span class="other-name">{other.name}</span>
                  <span class="mono other-price">
                    {uah(other.price)}{other.byWeight
                      ? '/кг'
                      : other.ratio
                        ? ` · ${other.ratio}`
                        : ''}{other.stock === 0 ? ' · немає' : ''}
                  </span>
                </li>
              {/each}
            </ul>
          {:else if line.consideredTotal === 1}
            <p class="body alone">
              Під цей намір на слот знайшовся рівно один товар — порівнювати не було з чим.
            </p>
          {/if}
        </article>
      {/each}
    </div>
  {/if}

  <div class="log glass">
    <p class="log-head">
      Технічний журнал прогону — {basket.stats.mcpCalls} викликів,
      {seconds(basket.stats.durationMs)}, {usd(basket.stats.costUsd)};
      з кешу шлюзу — {basket.stats.tokensCached} вхідних токенів з
      {basket.stats.tokensIn}.
    </p>
    {#if tollLine !== null}
      <p class="toll mono">{tollLine}</p>
    {/if}
    <button class="log-toggle" type="button" aria-expanded={logOpen} onclick={onToggleLog}>
      {logOpen ? 'Сховати журнал' : 'Показати журнал'}
    </button>
    {#if logOpen}
      <pre class="mono raw">{journal
          .map((step) => `${step.tool} → ${step.resultSummary}`)
          .join('\n')}</pre>
    {/if}
  </div>
</div>

<style>
  .trace {
    padding: 16px 16px 40px;
  }

  .top {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  h1 {
    font-size: 23px;
    font-weight: 800;
    letter-spacing: -0.7px;
    line-height: 1.2;
  }

  .lede {
    font-size: 14px;
    color: var(--muted);
    margin-top: 9px;
    line-height: 1.55;
  }

  .stats {
    display: flex;
    gap: 9px;
    margin-top: 18px;
  }

  .stat {
    flex: 1;
    padding: 12px 8px;
    border-radius: 14px;
    text-align: center;
    border: 1px solid var(--hair);
    background: var(--chip-bg);
  }

  .n {
    font-size: 18px;
    font-weight: 800;
    color: var(--badge);
    letter-spacing: -0.4px;
  }

  .l {
    font-size: 11.5px;
    color: var(--muted);
    margin-top: 3px;
    line-height: 1.3;
  }

  .cards {
    margin-top: 16px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .debug-strip {
    margin-top: 10px;
    padding: 7px 10px;
    border-radius: 10px;
    font-size: 11.5px;
    line-height: 1.4;
    color: var(--muted);
    border: 1px dashed var(--hair-strong);
    background: var(--chip-bg);
  }

  .clearing {
    margin-top: 14px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    align-items: flex-start;
  }

  .clear {
    padding: 9px 12px;
    min-height: 40px;
    border-radius: 11px;
    font-size: 12.5px;
    font-weight: 700;
    color: var(--muted);
    border: 1px solid var(--hair-strong);
    background: transparent;
  }

  .step-args {
    margin-top: 8px;
    font-size: 11px;
    line-height: 1.5;
    color: var(--trace-ink);
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  .section {
    font-size: 15px;
    font-weight: 800;
    letter-spacing: -0.3px;
    margin-top: 26px;
  }

  .rejected {
    margin-top: 9px;
    display: flex;
    flex-direction: column;
    gap: 5px;
    list-style: none;
  }

  .rejected li {
    display: flex;
    align-items: baseline;
    gap: 8px;
    font-size: 12.5px;
    color: var(--muted);
  }

  .other-name {
    flex: 1;
    line-height: 1.35;
  }

  .other-price {
    white-space: nowrap;
  }

  .alone {
    font-style: italic;
  }

  .card {
    padding: 14px;
    border-radius: 16px;
    border: 1px solid var(--hair);
    background: var(--list-bg);
  }

  .card.focused {
    border-color: var(--badge-edge);
    background: var(--badge-fill);
  }

  .card-head {
    display: flex;
    align-items: baseline;
    gap: 9px;
  }

  .card h2 {
    font-size: 14.5px;
    font-weight: 700;
    flex: 1;
    line-height: 1.3;
  }

  .tag {
    font-size: 12px;
    font-weight: 700;
    white-space: nowrap;
    color: var(--muted);
  }

  .tag.good {
    color: var(--good);
  }

  .tag.warn {
    color: var(--warn);
  }

  .body {
    font-size: 13px;
    color: var(--muted);
    margin-top: 6px;
    line-height: 1.5;
  }

  .card-foot {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 11px;
  }

  .copy {
    padding: 9px 12px;
    min-height: 40px;
    border-radius: 11px;
    font-size: 12.5px;
    font-weight: 700;
    color: var(--ink);
    border: 1px solid var(--hair-strong);
    background: var(--chip-bg);
  }

  .call {
    font-size: 11px;
    color: var(--faint);
    line-height: 1.4;
  }

  .log {
    margin-top: 16px;
    padding: 13px 14px;
    border-radius: 16px;
    border: 1px solid var(--hair);
    background: var(--trace-bg);
  }

  .log-head {
    font-size: 12.5px;
    color: var(--muted);
    line-height: 1.5;
  }

  .toll {
    margin-top: 6px;
    font-size: 12px;
    color: var(--muted);
  }

  .log-toggle {
    margin-top: 10px;
    padding: 9px 12px;
    min-height: 40px;
    border-radius: 11px;
    font-size: 12.5px;
    font-weight: 700;
    color: var(--muted);
    border: 1px solid var(--hair-strong);
    background: transparent;
  }

  .raw {
    font-size: 11.5px;
    line-height: 1.85;
    color: var(--trace-ink);
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    margin-top: 11px;
  }

  @media (width <= 380px) {
    .trace {
      padding-inline: 12px;
    }

    h1 {
      font-size: 21px;
    }

    .card-foot {
      flex-wrap: wrap;
    }
  }
</style>
