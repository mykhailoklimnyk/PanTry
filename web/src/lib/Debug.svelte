<script lang="ts">

  import { SHORT, UI_VERSION, commitUrl, matches } from './build'
  import { plural, stepTime } from './format'
  import { tollNote } from './ui'
  import { link } from './session.svelte'
  import type { Loaded } from './data'
  import type {
    BuildRun,
    CorrectionRun,
    DoneRun,
    FailedRun,
    RefillRun,
    Run,
    RunKind,
    SwapsRun,
  } from './runs'
  import type {
    Basket,
    Clarification,
    ClarifyAnswer,
    Health,
    ModelOption,
    Toll,
    TraceStep,
  } from './types'
  import type { Screen } from './navigation'

  interface Props {
    open: boolean
    screen: Screen
    model: string
    models: Loaded<ModelOption[]>
    signature: string
    builtWith: string
    stale: boolean
    basket: Basket | null
    live?: TraceStep[]
    pantry?: TraceStep[]
    spent?: Toll | null
    spentLogin?: Toll | null
    runs: Run[]
    hidden: number
    error: string | null
    health: Loaded<Health> | null
    onClose: () => void
  }

  const {
    open,
    screen,
    model,
    models,
    signature,
    builtWith,
    stale,
    basket,
    live = [],
    pantry = [],
    spent = null,
    spentLogin = null,
    runs,
    hidden,
    error,
    health,
    onClose,
  }: Props = $props()

  const runNote = $derived(tollNote(spent, 'цей забіг'))
  const sameSpend = $derived(
    spent !== null &&
      spentLogin !== null &&
      spent.runs === spentLogin.runs &&
      spent.tokensIn === spentLogin.tokensIn &&
      spent.tokensOut === spentLogin.tokensOut,
  )
  const loginNote = $derived(sameSpend ? null : tollNote(spentLogin, 'весь вхід'))

  const backendSha = $derived(health?.ok ? (health.data.version ?? null) : null)
  const backendShort = $derived(backendSha ? backendSha.slice(0, 9) : null)
  const sameCode = $derived(matches(backendSha))


  const runNow = $derived(live.length > 0)
  const cart = $derived(runNow ? live : (basket?.trace ?? []))
  const cartWhat = $derived(runNow ? 'збірка просто зараз' : 'останній зібраний кошик')
  const steps = $derived(cart)
  const stats = $derived(basket?.stats ?? null)

  const modelsSummary = $derived(
    models.ok
      ? `${models.data.filter((m) => m.available).length} з ${models.data.length} доступні`
      : models.message,
  )

  function json(value: unknown): string {
    return JSON.stringify(value, null, 1)
  }

  function rows(run: DoneRun): number {
    return run.basket.lines.filter((line) => line.reason !== 'at_home').length
  }

  function delta(value: number, forms: { one: string; few: string; many: string }): string {
    if (Math.round(value) === 0) return ''
    return `${value > 0 ? '+' : '-'}${plural(Math.abs(Math.round(value)), forms)}`
  }

  function diff(run: DoneRun, before: DoneRun | undefined): string {
    if (before === undefined) return ''
    const parts = [
      delta(rows(run) - rows(before), { one: 'рядок', few: 'рядки', many: 'рядків' }),
      delta(run.basket.questions.length - before.basket.questions.length, {
        one: 'питання',
        few: 'питання',
        many: 'питань',
      }),
      delta(run.basket.total - before.basket.total, { one: '₴', few: '₴', many: '₴' }),
    ].filter(Boolean)
    return parts.length > 0 ? parts.join(' · ') : 'склад не змінився'
  }

  function answered(answer: ClarifyAnswer, asked: Clarification[]): string {
    const question = asked.find((item) => item.intent === answer.intent)
    const chosen = question?.options.find(
      (option) =>
        (answer.slug !== null && option.slug === answer.slug) ||
        (answer.query !== null && option.query === answer.query),
    )
    return (
      chosen?.title ??
      answer.query ??
      answer.text ??
      (answer.skip ? 'не треба' : (answer.slug ?? 'без відповіді'))
    )
  }

  function why(run: Run, index: number): string {
    if (run.kind === 'failed') return `${ATTEMPT[run.what]} — не вдалась`
    const before = priorDone(index)
    if (run.kind === 'correction') return correction(run, before)
    if (run.kind === 'refill') return refilled(run, before)
    if (run.kind === 'swaps') return swapped(run)
    if (run.kind === 'pick') return `обрав сам: «${run.request.intent}»`
    if (run.kind === 'cheaper') return 'узяв дешевше того ж виду'
    const prior = priorBuild(index)
    const fresh = (run.request.answers ?? []).filter(
      (answer) =>
        !(prior?.request.answers ?? []).some((old) => old.intent === answer.intent),
    )
    if (fresh.length === 0) return before === undefined ? 'первинний збір' : 'перезбір'
    return fresh
      .map(
        (answer) =>
          `уточнення «${answer.intent}» → ${answered(answer, prior?.basket.questions ?? [])}`,
      )
      .join('; ')
  }

  function priorDone(index: number): DoneRun | undefined {
    for (let i = index - 1; i >= 0; i -= 1) {
      const earlier = runs[i]
      if (earlier !== undefined && earlier.kind !== 'failed') return earlier
    }
    return undefined
  }

  function priorBuild(index: number): BuildRun | undefined {
    for (let i = index - 1; i >= 0; i -= 1) {
      const earlier = runs[i]
      if (earlier?.kind === 'build') return earlier
    }
    return undefined
  }

  function correction(run: CorrectionRun, before: DoneRun | undefined): string {
    const article = run.request.externalProductId
    const line = run.basket.lines.find((item) => item.externalProductId === article)
    const gone = before?.basket.lines.find((item) => item.externalProductId === article)
    return `правка «${line?.name ?? gone?.name ?? article}» → ${
      line?.explanation ?? 'прибрано зі списку'
    }`
  }

  function refilled(run: RefillRun, before: DoneRun | undefined): string {
    const known = new Set((before?.basket.lines ?? []).map((line) => line.externalProductId))
    const added = run.basket.lines.filter((line) => !known.has(line.externalProductId))
    const said = run.request.answers ?? []
    if (said.length > 0) {
      const asked = before?.basket.questions ?? []
      return said
        .map((answer) => `уточнення «${answer.intent}» → ${answered(answer, asked)}`)
        .join('; ')
    }
    const what = run.request.intents.length > 0 ? 'добір словами' : 'добір: решта тижня'
    return added.length > 0 ? `${what} → ${added.map((line) => line.name).join(', ')}` : what
  }

  function swapped(run: SwapsRun): string {
    const withMandate = run.basket.lines.filter((line) => line.mandate).length
    return `погоджені заміни → мандат у ${plural(withMandate, {
      one: 'рядку',
      few: 'рядках',
      many: 'рядках',
    })}`
  }

  const ATTEMPT: Record<RunKind, string> = {
    build: 'збірка',
    correction: 'правка рядка',
    pick: 'обраний товар',
    refill: 'добір',
    cheaper: 'дешевше того ж виду',
    swaps: 'погоджені заміни',
  }

  function code(run: FailedRun): string {
    return run.status === null ? 'не доїхало' : String(run.status)
  }

  const CLOCK = new Intl.DateTimeFormat('uk-UA', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })

  function clock(at: number): string {
    return CLOCK.format(new Date(at))
  }

  let copied = $state<string | null>(null)

  async function copy(event: MouseEvent, what: string, value: unknown) {
    event.preventDefault()
    event.stopPropagation()
    try {
      await navigator.clipboard.writeText(json(value))
      copied = what
    } catch {
      copied = `${what}:fail`
    }
    setTimeout(() => (copied = null), 1600)
  }

  function copyLabel(what: string): string {
    if (copied === what) return 'скопійовано'
    if (copied === `${what}:fail`) return 'не вдалося'
    return 'копіювати'
  }
</script>

{#if open}
  <aside class="debug" aria-label="Панель дебагу">
    <header class="head">
      <span class="dot" class:live={link.connected} aria-hidden="true"></span>
      <span class="title">під капотом</span>
      <span class="mode">
        {link.connected ? 'акаунт «Сільпо»' : 'без акаунта'}
      </span>
      <button class="close" type="button" aria-label="Закрити панель" onclick={onClose}>
        ×
      </button>
    </header>

    <section class="block">
      <h3 class="label">стан</h3>
      <dl class="grid">
        <dt>екран</dt>
        <dd>{screen}</dd>
        <dt>модель</dt>
        <dd class="mono">{model || '— (серверний дефолт)'}</dd>
        <dt>кошик</dt>
        <dd>
          {#if basket === null}немає
          {:else if stale}<span class="warn">застарілий</span>
          {:else}свіжий{/if}
        </dd>
        <dt>моделі</dt>
        <dd class:warn={!models.ok}>{modelsSummary}</dd>
        {#if error}
          <dt>помилка</dt>
          <dd class="warn">{error}</dd>
        {/if}
      </dl>
    </section>

    {#if runNote !== null || loginNote !== null}
      <section class="block">
        <h3 class="label">витрати</h3>
        {#if runNote !== null}<p class="spend mono">{runNote}</p>{/if}
        {#if loginNote !== null}<p class="spend mono muted">{loginNote}</p>{/if}
      </section>
    {/if}

    <section class="block">
      <h3 class="label">версія</h3>
      <dl class="grid">
        <dt>UI</dt>
        <dd class="mono">{UI_VERSION || '— (збірка поза CI)'}</dd>
        <dt>фронт</dt>
        <dd class="mono">
          {#if commitUrl()}
            <a href={commitUrl()} target="_blank" rel="noreferrer">{SHORT}</a>
          {:else}
            {SHORT || 'невідомо'}
          {/if}
        </dd>
        <dt>бекенд</dt>
        <dd class="mono">
          {#if backendShort && commitUrl(backendSha ?? '')}
            <a href={commitUrl(backendSha ?? '')} target="_blank" rel="noreferrer">
              {backendShort}
            </a>
          {:else if health === null}
            питаємо…
          {:else if health.ok}
            не деплой
          {:else}
            {health.message}
          {/if}
        </dd>
        {#if sameCode === false}
          <dt>увага</dt>
          <dd class="warn">фронт і бекенд з різних комітів</dd>
        {/if}
      </dl>
    </section>

    <section class="block">
      <h3 class="label">підпис наміру · замовлення</h3>
      <p class="sig mono">{signature || '—'}</p>
      {#if basket !== null}
        <p class="sig mono" class:faded={!stale}>{builtWith || '—'}</p>
      {/if}
    </section>

    {#if stats}
      <section class="block">
        <h3 class="label">прогін</h3>
        <dl class="grid">
          <dt>модель</dt>
          <dd class="mono">{stats.model}</dd>
          <dt>тривалість</dt>
          <dd>{(stats.durationMs / 1000).toFixed(1)} с</dd>
          <dt>виклики MCP</dt>
          <dd>{stats.mcpCalls}</dd>
          <dt>вартість</dt>
          <dd>${stats.costUsd.toFixed(2)}</dd>
          <dt>чеків в основі</dt>
          <dd>{stats.receipts}</dd>
          <dt>позицій з циклом</dt>
          <dd>{stats.cycled}</dd>
        </dl>
      </section>
    {/if}

    <section class="block">
      <h3 class="label">прогони · {runs.length + hidden}</h3>
      {#if runs.length === 0}
        <p class="empty">прогону ще не було — зберіть кошик</p>
      {:else}
        {#if hidden > 0}
          <p class="capped">
            показані останні {runs.length} · ще {plural(hidden, {
              one: 'прогін витіснено',
              few: 'прогони витіснено',
              many: 'прогонів витіснено',
            })}
          </p>
        {/if}
        {#each runs.map((run, index) => ({ run, index })).reverse() as { run, index } (hidden + index)}
          {@const no = hidden + index + 1}
          <article class="run" class:broken={run.kind === 'failed'}>
            <div class="run-head">
              <span class="seq mono">#{no}</span>
              <span class="why">{why(run, index)}</span>
              {#if run.kind === 'failed'}
                <span class="bad mono">{code(run)}</span>
              {:else if basket !== null && run.basket.runId === basket.runId}
                <span class="now">на екрані</span>
              {/if}
            </div>
            {#if run.kind === 'failed'}
              <p class="facts">
                <span class="warn">{run.message}</span>
                <span class="delta">{clock(run.at)}</span>
              </p>
            {:else}
              {@const before = priorDone(index)}
              <p class="facts">
                {rows(run)} рядків · {Math.round(run.basket.total)} ₴ ·
                {run.basket.questions.length} питань
                {#if diff(run, before)}
                  <span class="delta">{diff(run, before)}</span>
                {/if}
              </p>
            {/if}
            <details class="args">
              <summary>
                <span>запит</span>
                <button class="copy" type="button" onclick={(e) => copy(e, `req${no}`, run.request)}>
                  {copyLabel(`req${no}`)}
                </button>
              </summary>
              <pre class="mono">{json(run.request)}</pre>
            </details>
            {#if run.kind !== 'failed'}
              <details class="args">
                <summary>
                  <span>відповідь — Basket цілком</span>
                  <button
                    class="copy"
                    type="button"
                    onclick={(e) => copy(e, `res${no}`, run.basket)}
                  >
                    {copyLabel(`res${no}`)}
                  </button>
                </summary>
                <pre class="mono">{json(run.basket)}</pre>
              </details>
            {/if}
          </article>
        {/each}
      {/if}
    </section>

    <section class="block">
      <h3 class="label">трейс · {cartWhat} · {steps.length} кроків</h3>
      {#if steps.length === 0}
        <p class="empty">прогону ще не було — зберіть кошик</p>
      {:else}
        {#each steps as step}
          <article class="step">
            <div class="step-head">
              <span class="seq mono">#{step.seq}</span>
              <span class="tool mono ellipsis">{step.tool}</span>
              <span class="ms">{stepTime(step.durationMs)}</span>
            </div>
            {#if step.calls !== null}
              <p class="spend mono muted">
                {#if step.calls === 0}модель не питали{:else}{plural(step.calls, {
                    one: 'виклик',
                    few: 'виклики',
                    many: 'викликів',
                  })}{/if}
              </p>
            {/if}
            <p class="summary">{step.resultSummary}</p>
            {#if step.decision}
              <p class="decision">{step.decision}</p>
            {/if}
            {#if step.prompt}
              <p class="prompt mono">промпт: {step.prompt}</p>
            {/if}
            {#if Object.keys(step.args).length > 0}
              <details class="args">
                <summary>
                  <span>аргументи (редаговані)</span>
                  <button
                    class="copy"
                    type="button"
                    onclick={(e) => copy(e, `step${step.seq}`, step.args)}
                  >
                    {copyLabel(`step${step.seq}`)}
                  </button>
                </summary>
                <pre class="mono">{json(step.args)}</pre>
              </details>
            {/if}
          </article>
        {/each}
      {/if}
    </section>

    {#if pantry.length > 0}
      <section class="block">
        <h3 class="label">трейс · петля комори · {pantry.length} кроків</h3>
        {#each pantry as step}
          <article class="step">
            <div class="step-head">
              <span class="seq mono">#{step.seq}</span>
              <span class="tool mono ellipsis">{step.tool}</span>
              <span class="ms">{stepTime(step.durationMs)}</span>
            </div>
            {#if step.calls !== null}
              <p class="spend mono muted">
                {#if step.calls === 0}модель не питали{:else}{plural(step.calls, {
                    one: 'виклик',
                    few: 'виклики',
                    many: 'викликів',
                  })}{/if}
              </p>
            {/if}
            <p class="summary">{step.resultSummary}</p>
            {#if step.decision}
              <p class="decision">{step.decision}</p>
            {/if}
            {#if step.prompt}
              <p class="prompt mono">промпт: {step.prompt}</p>
            {/if}
          </article>
        {/each}
      </section>
    {/if}

    <p class="foot">панель ховається клавішею ` або в меню — «панель дебагу»</p>
  </aside>
{/if}

<style>
  .debug {
    position: fixed;
    top: 12px;
    right: 12px;
    bottom: 12px;
    width: 360px;
    z-index: 55;
    overflow-y: auto;
    overscroll-behavior: contain;
    scrollbar-width: thin;
    scrollbar-color: var(--hair-strong) transparent;
    padding: 14px 14px 10px;
    border-radius: 16px;
    border: 1px solid var(--hair-strong);
    background: var(--menu-bg);
    backdrop-filter: blur(26px) saturate(160%);
    box-shadow: 0 18px 44px rgb(0 0 0 / 0.35);
    font-size: 12px;
    line-height: 1.45;
  }

  @media (max-width: 1239px) {
    .debug {
      display: none;
    }
  }

  .head {
    display: flex;
    align-items: center;
    gap: 7px;
  }

  .dot {
    flex: none;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--faint);
  }

  .dot.live {
    background: var(--warn);
  }

  .title {
    font-weight: 800;
    font-size: 13px;
  }

  .mode {
    margin-left: auto;
    font-size: 10.5px;
    color: var(--faint);
  }

  .close {
    flex: none;
    width: 22px;
    height: 22px;
    border-radius: 7px;
    font-size: 14px;
    line-height: 1;
    color: var(--muted);
    background: var(--chip-bg);
  }

  .block {
    margin-top: 12px;
    padding-top: 10px;
    border-top: 1px solid var(--hair-strong);
  }

  .label {
    margin: 0 0 6px;
    font-size: 10.5px;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--faint);
  }

  .grid {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 3px 10px;
    margin: 0;
  }

  .grid dt {
    color: var(--muted);
    white-space: nowrap;
  }

  .grid dd {
    margin: 0;
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .mono {
    font-family: var(--font-mono);
    font-size: 11px;
  }

  .grid a {
    color: var(--badge);
    text-decoration: underline;
  }

  .warn {
    color: var(--warn);
  }

  .sig {
    margin: 0 0 4px;
    padding: 6px 8px;
    border-radius: 8px;
    background: var(--chip-bg);
    overflow-wrap: anywhere;
  }

  .sig.faded {
    opacity: 0.55;
  }

  .empty {
    color: var(--faint);
    margin: 0;
  }

  .capped {
    margin: 0 0 6px;
    font-size: 11px;
    color: var(--faint);
  }

  .run {
    padding: 8px 0;
    border-bottom: 1px dashed var(--hair);
  }

  .run.broken .why {
    color: var(--warn);
  }

  .bad {
    flex: none;
    padding: 1px 6px;
    border-radius: 6px;
    font-size: 10px;
    font-weight: 700;
    color: var(--warn);
    background: var(--chip-bg);
  }

  .run:last-of-type {
    border-bottom: none;
  }

  .run-head {
    display: flex;
    align-items: baseline;
    gap: 7px;
  }

  .run .why {
    flex: 1;
    min-width: 0;
    font-size: 11px;
    font-weight: 700;
    line-height: 1.3;
  }

  .now {
    flex: none;
    padding: 1px 6px;
    border-radius: 6px;
    font-size: 10px;
    font-weight: 700;
    color: var(--badge);
    background: var(--chip-bg);
  }

  .facts {
    margin: 3px 0 5px;
    font-size: 11px;
    color: var(--trace-ink);
  }

  .delta {
    margin-left: 4px;
    font-weight: 700;
    color: var(--badge);
  }

  .step {
    padding: 7px 0;
    border-top: 1px dashed var(--hair-strong);
  }

  .step:first-of-type {
    border-top: none;
    padding-top: 0;
  }

  .step-head {
    display: flex;
    align-items: baseline;
    gap: 7px;
  }

  .seq {
    color: var(--faint);
  }

  .tool {
    min-width: 0;
    font-weight: 600;
  }

  .ms {
    margin-left: auto;
    flex: none;
    color: var(--muted);
    font-size: 10.5px;
  }

  .summary {
    margin: 2px 0 0;
    color: var(--muted);
  }

  .decision {
    margin: 3px 0 0;
    padding-left: 8px;
    border-left: 2px solid var(--badge);
  }

  .prompt {
    margin: 3px 0 0;
    color: var(--muted);
    font-size: 10.5px;
    overflow-wrap: anywhere;
  }

  .args {
    margin-top: 4px;
  }

  .args summary {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 10.5px;
    color: var(--faint);
    cursor: pointer;
  }

  .copy {
    margin-left: auto;
    flex: none;
    padding: 1px 6px;
    border-radius: 6px;
    font-size: 10px;
    color: var(--muted);
    background: var(--chip-bg);
  }

  .args pre {
    max-height: 320px;
    overflow: auto;
    overscroll-behavior: contain;
  }

  .args pre {
    margin: 4px 0 0;
    padding: 6px 8px;
    border-radius: 8px;
    background: var(--chip-bg);
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  .ellipsis {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .spend {
    font-size: 11.5px;
    line-height: 1.5;
    color: var(--ink);
    overflow-wrap: anywhere;
  }

  .spend.muted {
    color: var(--muted);
    margin-top: 4px;
  }

  .foot {
    margin: 12px 0 0;
    font-size: 10px;
    color: var(--faint);
  }
</style>
