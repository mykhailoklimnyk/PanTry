<script lang="ts">
  import CloseDock from '../CloseDock.svelte'
  import Dictaphone from '../Dictaphone.svelte'
  import MicButton from '../MicButton.svelte'
  import Modal from '../Modal.svelte'
  import {
    boughtChoices,
    cycleAsk,
    cycleChoicesFor,
    ASK_AT_ONCE,
    CYCLE_CHOICES,
    FILTER_FROM,
    NO_PHOTO,
    PANTRY_PHASES,
    addHints,
    pantryEmptyNote,
    pantryStep,
    plainKind,
    sourcesPhrase,
    stockDays,
    tollNote,
  } from '../ui'
  import { aisleIcon } from '../aisles'
  import { amount, plural, seconds, usd } from '../format'
  import { splitSpoken } from '../list'
  import { shelves } from '../pantry'
  import { voiceAvailable } from '../speech'
  import { homeThoughts } from '../thoughts'
  import Running from './Running.svelte'
  import type { Pantry, PantryAsk, PantryItem, Toll, TraceStep } from '../types'

  interface Props {
    items: PantryItem[]
    toll?: Toll | null
    loaded: boolean
    pending?: number | null
    failed: string | null
    onRetry: () => void
    source: Omit<Pantry, 'items'> | null
    addOpen: boolean
    query: string
    onQuery: (value: string) => void
    busy: ReadonlySet<string>
    onBought: (id: string, qty: number | null) => void
    onAddToggle: () => void
    onAddNamed: (label: string) => void
    onAdd: () => void
    onForget: (id: string) => void
    onHide: (id: string) => void
    onUnhide: (label: string) => void
    onSplit: (intent: string) => void
    onUnsplit: (intent: string) => void
    onMandate: (id: string, chain: string[]) => void
    onToList: (label: string) => void
    onAdjust: (id: string, delta: number) => void
    onCycle: (id: string, days: number | null) => void
    onSource: (mode: 'receipts' | 'manual') => void
    onGenerate: () => void
    onNextList: () => void
    onWipe: () => void
    deed: string | null
    composing: boolean
    sourceBusy: boolean
    debug?: boolean
    steps?: TraceStep[]
    looping?: boolean
    asked?: PantryAsk[]
    answering?: boolean
    answeringMore?: boolean
    door?: PantryAsk[]
    onDoor?: () => void
    onAnswer?: (answers: Record<string, number>, more?: boolean) => void
    since?: number | null
    backLabel: string
    onBack: () => void
  }

  const {
    items,
    loaded,
    toll = null,
    pending = null,
    failed,
    onRetry,
    source,
    addOpen,
    busy,
    onBought,
    query,
    onQuery,
    onAddToggle,
    onAddNamed,
    onAdd,
    onForget,
    onHide,
    onUnhide,
    onSplit,
    onUnsplit,
    onMandate,
    onToList,
    onAdjust,
    onCycle,
    onSource,
    onGenerate,
    onNextList,
    onWipe,
    deed,
    composing,
    sourceBusy,
    debug = false,
    steps = [],
    looping = false,
    asked = [],
    answering = false,
    answeringMore = false,
    door = [],
    onDoor = () => {},
    onAnswer = () => {},
    since = null,
    backLabel,
    onBack,
  }: Props = $props()

  const filling = $derived(
    (!loaded && (pending !== null || failed === null)) ||
      (looping && items.length > 0 && items.every((item) => !item.named)),
  )

  const hasUnder = (item: PantryItem): boolean =>
    item.usual !== null ||
    item.promo !== null ||
    item.parts.length > 1 ||
    item.mandate !== null

  let answers = $state<Record<string, number>>({})

  const answered = $derived(Object.keys(answers).length)

  const allAnswered = $derived(asked.length > 0 && answered === asked.length)

  const send = (more: boolean) => {
    const said = { ...answers }
    answers = {}
    onAnswer(said, more)
  }

  const probing = $derived(asked.length > 0)
  const HIDE_KEY = 'komora:asks-hidden'
  const today = () => new Date().toISOString().slice(0, 10)
  const hiddenToday = () => {
    try {
      return localStorage.getItem(HIDE_KEY) === today()
    } catch {
      return false
    }
  }
  let qHidden = $state(hiddenToday())
  const covering = $derived(failed === null && (filling || (probing && !qHidden) || answering))
  const spent = $derived(source?.spent ?? null)
  const tollLine = $derived(tollNote(toll))
  const homeFacts = $derived(homeThoughts(items, source?.source ?? 'receipts', !looping))

  let clock = $state(Date.now())
  $effect(() => {
    if (!filling && !answering) return
    const tick = setInterval(() => (clock = Date.now()), 300)
    return () => clearInterval(tick)
  })
  const waited = $derived(since === null ? 0 : clock - since)

  const bySelf = $derived(source?.source === 'manual')
  let wipeAsked = $state(false)
  let settingsOpen = $state(false)

  const hidden = $derived(source?.hidden ?? [])
  const atBar = $derived(source?.atBar ?? [])

  const apart = $derived(source?.apart ?? [])

  const ownKinds = $derived([
    ...new Set([...items.map((one) => one.label), ...(source?.outside ?? [])]),
  ])

  const hints = $derived(addHints(ownKinds, source?.outside ?? [], query))

  const outsideNote = $derived(
    `У покупках є ще ${source?.unlisted ?? 0} ${
      (source?.unlisted ?? 0) === 1 ? 'вид' : 'видів'
    }, яких немає у твоєму списку.`,
  )

  let dictOpen = $state(false)

  const workingNow = $derived(steps.at(-1)?.resultSummary ?? 'заповнюю комору')


  let asking = $state<PantryItem | null>(null)

  let ownQty = $state<string | number | undefined>('')
  const ownQtyValid = $derived(typed(ownQty) !== null && typed(ownQty)! >= 0)

  function typed(value: string | number | undefined): number | null {
    const text = String(value ?? '').trim()
    if (text === '') return null
    const parsed = Number(text)
    return Number.isFinite(parsed) ? parsed : null
  }

  let timing = $state<PantryItem | null>(null)
  let ownDays = $state<string | number | undefined>('')

  function tellCycle(id: string, days: number | null) {
    timing = null
    ownDays = ''
    onCycle(id, days)
  }

  const ownCycle = $derived(Math.floor(typed(ownDays) ?? 0))
  const ownValid = $derived(ownCycle >= 1)

  function timingLabel(item: PantryItem): string {
    if (item.cycleSaid) return 'виправити, на скільки вистачає'
    return 'сказати, на скільки вистачає'
  }

  function wroteLine(words: string[]): string {
    return `ти написав ${words.map((word) => `«${word}»`).join(', ')} -- веду цим рядком`
  }

  const questions = $derived(items.filter((item) => item.ask))
  let qIndex = $state(0)
  let qOpen = $state(false)
  let qDone = $state(new Set<string>())
  const qAll = $derived(questions.filter((item) => !qDone.has(item.id)))
  const qLeft = $derived(qAll.slice(0, ASK_AT_ONCE))
  const qAt = $derived(Math.min(qIndex, Math.max(0, qLeft.length - 1)))
  const qRest = $derived(qAll.length - qLeft.length)

  function qDrop(item: PantryItem): void {
    const done = new Set(qDone)
    done.add(item.id)
    qDone = done
    qIndex = 0
    onHide(item.id)
  }

  function qBack(): void {
    qIndex = Math.max(0, qAt - 1)
  }

  function qAnswer(item: PantryItem, days: number | null): void {
    const done = new Set(qDone)
    done.add(item.id)
    qDone = done
    qIndex = 0
    tellCycle(item.id, days)
  }

  function choicesFor(item: PantryItem): number[] {
    if (item.usualQty === null) return []
    return boughtChoices(item.usualQty, pantryStep(item.unit))
  }

  function tellBought(id: string, qty: number | null) {
    asking = null
    ownQty = ''
    onBought(id, qty)
  }

  let filter = $state('')

  const NAMES = { one: 'назва', few: 'назви', many: 'назв' }
  const KINDS = { one: 'вид', few: 'види', many: 'видів' }

  let opened = $state(new Set<string>())

  function togglePartsOf(id: string) {
    const next = new Set(opened)
    if (!next.delete(id)) next.add(id)
    opened = next
  }

  const plain = plainKind

  const needle = $derived(plain(filter))

  const qCurrent = $derived(
    qHidden ? null : (qLeft.at(qAt) ?? null),
  )
  let picked = $state<string | null>(null)
  const rail = $derived(source?.aisles ?? [])
  const active = $derived(rail.some((one) => one.title === picked) ? picked : null)

  let railEl = $state<HTMLElement | null>(null)
  let railLeft = $state(0)
  let railRoom = $state(0)

  function railMeasure(): void {
    const el = railEl
    if (el === null) return
    railLeft = el.scrollLeft
    railRoom = el.scrollWidth - el.clientWidth
  }

  function railStep(way: number): void {
    const el = railEl
    if (el === null) return
    el.scrollBy({ left: way * Math.round(el.clientWidth * 0.8), behavior: 'smooth' })
  }

  function railWheel(event: WheelEvent): void {
    const el = railEl
    if (el === null || event.deltaY === 0) return
    const room = el.scrollWidth - el.clientWidth
    if (room <= 0) return
    const edge = event.deltaY < 0 ? el.scrollLeft <= 0 : el.scrollLeft >= room - 1
    if (edge) return
    event.preventDefault()
    el.scrollLeft += event.deltaY
  }

  $effect(() => {
    const el = railEl
    if (el === null) return
    el.addEventListener('wheel', railWheel, { passive: false })
    const eye = new ResizeObserver(railMeasure)
    eye.observe(el)
    railMeasure()
    return () => {
      el.removeEventListener('wheel', railWheel)
      eye.disconnect()
    }
  })

  let pantryEl = $state<HTMLDivElement | null>(null)
  let dockHeight = $state(0)

  $effect(() => {
    const root = pantryEl
    if (root === null) return
    const dock = root.querySelector<HTMLElement>(':scope > .dock')
    if (dock === null) return
    const eye = new ResizeObserver(() => {
      dockHeight = dock.getBoundingClientRect().height
    })
    eye.observe(dock)
    dockHeight = dock.getBoundingClientRect().height
    return () => eye.disconnect()
  })

  const shown = $derived(
    (needle === ''
      ? items
      : items.filter(
          (item) =>
            plain(item.label).includes(needle) ||
            plain(item.usual?.name ?? '').includes(needle),
        )
    ).filter((item) => active === null || item.aisle === active),
  )

  const rows = $derived(shelves(shown))

  let spoken: string[] = []

  function flushSpoken() {
    dictOpen = false
    if (spoken.length === 0) return
    const head = query.trim().replace(/[,;\s]+$/, '')
    const heard = spoken.join(', ')
    spoken = []
    onQuery(head ? `${head}, ${heard}` : heard)
  }
  let voiceNote = $state<string | null>(null)
  let failedImages = $state(new Set<string>())

  function leftText(item: PantryItem): string | null {
    if (item.runningOut) return 'закінчилось'
    if (item.daysLeft === null) return null
    return `ще ~${item.daysLeft} дн`
  }

  function fill(ratio: number): number {
    return ratio <= 0 ? 0 : Math.max(4, Math.min(100, Math.round(ratio * 100)))
  }
</script>

{#if covering}
  <div class="cover" data-testid="pantry-screen">
    {#if probing}
      <section class="asked" data-testid="pantry-asked" data-tour="pantry-asked">
        <h2>Кілька слів про твій дім</h2>
        <p class="why">
          Чеки показують покупки, а не те, як швидко воно вдома закінчується.
          Відповідь на {plural(asked.length, {
            one: 'питання',
            few: 'питання',
            many: 'питань',
          })} поставить числа й сусіднім видам.
        </p>
        {#each asked as probe (probe.label)}
          <article class="ask">
            <p class="ask-name">{probe.label}</p>
            <p class="ask-q">{probe.ask}</p>
            {#if probe.usual}
              <p class="ask-usual">{probe.usual}</p>
            {/if}
            {#if probe.covers.length > 0}
              <p class="covers">Та сама відповідь пояснить: {probe.covers.join(', ')}</p>
            {/if}
            <div class="suggest">
              {#each CYCLE_CHOICES as choice (choice.days)}
                <button
                  type="button"
                  class="hint"
                  class:on={answers[probe.label] === choice.days}
                  onclick={() => (answers = { ...answers, [probe.label]: choice.days })}
                >
                  {choice.label}
                </button>
              {/each}
            </div>
          </article>
        {/each}
        <div class="asked-dock">
          {#if allAnswered}
            <button class="primary" type="button" onclick={() => send(true)}>
              Ще питання
            </button>
          {/if}
          <button
            class="link"
            type="button"
            data-testid="pantry-asked-done"
            onclick={() => send(false)}
          >
            {answered === 0
              ? 'Пропустити — питання чекатимуть у коморі'
              : `Готово · ${answered} з ${asked.length} — решта чекатиме в коморі`}
          </button>
        </div>
      </section>
    {:else}
    <Running
      elapsed={waited}
      thoughts={homeFacts}
      {steps}
      journal
      phases={PANTRY_PHASES}
      title={answering
        ? answeringMore
          ? 'Шукаю, що ще спитати'
          : 'Записую твою відповідь'
        : 'Заповнюю комору'}
      promise={answering
        ? answeringMore
          ? 'агент дивиться на комору після твоїх відповідей і сам вирішує, чого ще бракує'
          : 'ставлю число цьому виду і сусіднім, про які я питав'
        : 'перший раз довше — назви видів рахує модель, далі вони вже відомі'}
    />
    {/if}
    {#if !probing}
      <div class="cover-dock">
        <CloseDock label={backLabel} onClick={onBack} />
      </div>
    {/if}
  </div>
{:else}
  <div class="pantry" data-testid="pantry-screen" bind:this={pantryEl}>
    <div class="intro">
      <p>
        {#if bySelf}
          Цей список ведеш ти. Нове з покупок сюди не додається, але терміни й
          цикли рахуються з них далі.
        {:else if loaded && items.length === 0}
          Тут буде видно, що в тебе вдома і коли воно закінчується.
        {:else}
          Смуга — скільки лишилось до кінця циклу; кількість можна виправити.
        {/if}
      </p>
      <button class="primary" type="button" aria-expanded={addOpen} onclick={onAddToggle}>
        + Додати
      </button>
    </div>

    {#if loaded && source && source.trace.length > 0}
      <details class="why" data-tour="pantry-why">
        <summary>звідки це: {sourcesPhrase(source)}</summary>
        <ol>
          {#each source.trace as step}
            <li>
              <p class="said">{step.resultSummary}</p>
              {#if step.decision}<p class="because">{step.decision}</p>{/if}
              {#if debug && Object.keys(step.args).length > 0}
                <pre class="mono step-args">{JSON.stringify(step.args, null, 2)}</pre>
              {/if}
            </li>
          {/each}
        </ol>
        {#if spent !== null && spent.calls > 0}
          <p class="cost mono">
            цей оберт: {spent.costUsd === null ? 'модель без прайсу' : usd(spent.costUsd)} ·
            {spent.calls}
            {plural(spent.calls, { one: 'виклик', few: 'виклики', many: 'викликів' })} ·
            {spent.tokensIn} → {spent.tokensOut} ток. · {seconds(spent.durationMs)}
          </p>
        {/if}
        {#if tollLine !== null}
          <p class="cost mono">{tollLine}</p>
        {/if}
      </details>
    {/if}

    {#if loaded}
      <div class="source" data-tour="pantry-source">
        <div class="deeds">
          <button type="button" class="deed lead" disabled={sourceBusy} onclick={onNextList}>
            {composing ? 'Складаю список...' : 'На наступну покупку'}
          </button>
        </div>
        <button
          type="button"
          class="deed gear"
          aria-haspopup="dialog"
          aria-expanded={settingsOpen}
          onclick={() => (settingsOpen = true)}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path
              d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z M12 2v3 M12 19v3 M2 12h3 M19 12h3 M5 5l2 2 M17 17l2 2 M19 5l-2 2 M7 17l-2 2"
            />
          </svg>
          {bySelf ? 'веду сам' : 'з покупок'}
        </button>
        {#if deed}
          <p class="deed-said" role="status">{deed}</p>
        {/if}
        {#if looping && debug}
          <p class="working" data-testid="pantry-working" role="status">
            <span class="dot" aria-hidden="true"></span>{workingNow}
          </p>
        {:else if looping}
          <p class="working" data-testid="pantry-working" role="status">
            <span class="dot" aria-hidden="true"></span>дивлюсь, що вдома
          </p>
        {/if}
        {#if source?.refined}
          <p class="refined" data-testid="pantry-refined" role="status">{source.refined}</p>
        {/if}
        {#if bySelf && (source?.unlisted ?? 0) > 0}
          <p class="outside">
            {outsideNote}
            <button type="button" class="link" disabled={sourceBusy} onclick={onGenerate}>
              Додати їх
            </button>
          </p>
        {/if}
      </div>
    {/if}

    {#if loaded && door.length > 0 && needle === ''}
      <button class="ask-door" type="button" onclick={onDoor}>
        <span class="ask-door-text">питання про твій дім</span>
        <span class="ask-badge num">{door.length}</span>
      </button>
    {:else if loaded && qAll.length > 0 && !qHidden && needle === ''}
      <button class="ask-door" type="button" onclick={() => (qOpen = true)}>
        <span class="ask-door-text">просять твого слова</span>
        <span class="ask-badge num">{qAll.length}</span>
      </button>
    {/if}

    {#if qOpen}
      <Modal label="Питання про твій дім">
        <div class="ask-card">
          <button
            type="button"
            class="ask-close"
            aria-label="Закрити"
            onclick={() => (qOpen = false)}
          >
            ✕
          </button>
        {#if qCurrent === null}
          <p class="ask-count">більше питань немає</p>
        {:else}
          {@const q = qCurrent}
          <p class="ask-count">
            залишилось {plural(qAll.length, KINDS)}
          </p>
        <p class="ask-name">{q.label}</p>
        <p class="ask-q">{cycleAsk(q.usualQty, q.unit)}</p>
        {#if q.parts.length > 0}
          <p class="ask-seen">з чеків: {q.parts[0]!.label}</p>
        {/if}
        <p class="ask-sense">{q.sanity}</p>
        {#if qRest > 0}
          <p class="ask-rest">
            ще {qRest} підсвічені в самому списку
          </p>
        {/if}
        <div class="suggest">
          {#each cycleChoicesFor(q.keeps) as choice (choice.days)}
            <button
              class="hint"
              class:on={q.cycleSaid && q.cycleDays === choice.days}
              type="button"
              onclick={() => qAnswer(q, choice.days)}
            >
              {choice.label}
            </button>
          {/each}
          <button
            type="button"
            class="hint more"
            onclick={() => {
              ownDays = q.cycleSaid ? (q.cycleDays ?? '') : ''
              timing = q
            }}
          >
            інше…
          </button>
        </div>
        <div class="ask-row">
          <button type="button" class="ask-link" onclick={qBack}>← назад</button>
          <button type="button" class="ask-link" onclick={() => qDrop(q)}>не веду цей вид</button>
          <button
            type="button"
            class="ask-link"
            onclick={() => {
              qHidden = true
              qOpen = false
              try {
                localStorage.setItem(HIDE_KEY, today())
              } catch {
              }
            }}
          >
            відкласти всі
          </button>
        </div>
        {/if}
        </div>
      </Modal>
    {/if}

    {#if items.length >= FILTER_FROM}
      <div class="search">
        <input
          type="search"
          value={filter}
          placeholder="знайти у коморі"
          aria-label="знайти у коморі"
          oninput={(event) => (filter = event.currentTarget.value)}
        />
        {#if needle !== ''}
          <span class="found">{shown.length} з {items.length}</span>
        {/if}
      </div>
    {/if}

    {#if rail.length > 1}
      <div class="rail-wrap" data-tour="pantry-rail">
        {#if railLeft > 1}
          <button
            type="button"
            class="rail-step back"
            aria-label="Попередні відділи"
            onclick={() => railStep(-1)}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M15 5l-7 7 7 7" />
            </svg>
          </button>
        {/if}
        {#if railLeft < railRoom - 1}
          <button
            type="button"
            class="rail-step ahead"
            aria-label="Наступні відділи"
            onclick={() => railStep(1)}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M9 5l7 7-7 7" />
            </svg>
          </button>
        {/if}
        <nav
          class="rail"
          aria-label="Відділи комори"
          bind:this={railEl}
          onscroll={railMeasure}
        >
          {#each rail as one (one.title)}
            <button
              type="button"
              class="aisle"
              class:on={active === one.title}
              aria-pressed={active === one.title}
              onclick={() => (picked = active === one.title ? null : one.title)}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d={aisleIcon(one.title)} />
              </svg>
              <span class="aisle-name">{one.title}</span>
              <span class="aisle-rows">{one.rows}</span>
            </button>
          {/each}
        </nav>
      </div>
    {/if}

    {#if active !== null}
      <p class="picked" role="status">
        Відділ «{active}»
        <button type="button" class="link" onclick={() => (picked = null)}>показати все</button>
      </p>
    {/if}

    {#if addOpen}
      <Modal label="Додати в комору">
        <label class="caption" for="pantry-add">
          що вже стоїть у коморі, але агент про це не знає
        </label>
        <div class="field">
          <span class="voice-wrap">
            <input
              id="pantry-add"
              type="text"
              value={query}
              placeholder="вид, а не марка: гречка, олія"
              data-tour="pantry-add"
              oninput={(event) => onQuery(event.currentTarget.value)}
            />
            {#if voiceAvailable()}
              <span class="mic-slot"><MicButton
                active={dictOpen}
                label="надиктувати назву"
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

        <p class="suggest-note">{hints.note}</p>
        <div class="suggest">
          {#each hints.chips as item}
            <button class="hint" type="button" onclick={() => onQuery(item)}>{item}</button>
          {/each}
        </div>

        {#if voiceAvailable()}
          <p class="voice-note">надиктоване лягає в поле — перевір і додай</p>
        {/if}

        <div class="add-actions">
          <button class="secondary" type="button" onclick={onAddToggle}>Закрити</button>
          <button class="primary wide" type="button" disabled={!query.trim()} onclick={onAdd}>
            Додати в комору
          </button>
        </div>
      </Modal>
    {/if}

    {#if asking !== null}
      {@const item = asking}
      <Modal label="Скільки взяв">
        <p class="ask">Скільки взяв?</p>
        <p class="caption">
          {item.label}{item.usualQty === null
            ? ' · звичного ще не видно з чеків — скажи число сам'
            : ` · звично береш ${amount(item.usualQty, item.unit)}`}
        </p>

        <div class="suggest">
          {#each choicesFor(item) as value}
            {@const days = stockDays(value, item.usualQty ?? 0, item.cycleDays, item.cycleSaid)}
            <button class="hint" type="button" onclick={() => tellBought(item.id, value)}>
              {amount(value, item.unit)}
              {#if days !== null}<span class="for">на ~{days} дн</span>{/if}
            </button>
          {/each}
        </div>

        <label class="own-label" for="pantry-qty">або скільки саме</label>
        <div class="own">
          <input
            id="pantry-qty"
            type="number"
            min="0"
            step={pantryStep(item.unit)}
            inputmode="decimal"
            placeholder={item.unit || 'скільки'}
            bind:value={ownQty}
          />
          <button
            class="secondary"
            type="button"
            disabled={!ownQtyValid}
            onclick={() => tellBought(item.id, typed(ownQty) ?? 0)}
          >
            Записати
          </button>
        </div>

        {#if !item.cycleSaid}
          <button
            class="timing"
            type="button"
            onclick={() => {
              asking = null
              ownDays = ''
              timing = item
            }}
          >
            а на скільки тобі цього вистачає?
          </button>
        {/if}

        <div class="add-actions">
          <button class="secondary" type="button" onclick={() => (asking = null)}>
            Скасувати
          </button>
          <button class="primary wide" type="button" onclick={() => tellBought(item.id, null)}>
            просто купив
          </button>
        </div>
      </Modal>
    {/if}

    {#if timing !== null}
      {@const item = timing}
      <Modal label="На скільки вистачає">
        <p class="ask">{cycleAsk(item.usualQty, item.unit)}</p>
        <p class="caption">
          {item.label}{#if item.cycleDays !== null && !item.cycleSaid}&nbsp;· з чеків я рахую ~{item.cycleDays}
            дн{/if}
        </p>

        <div class="suggest">
          {#each CYCLE_CHOICES as choice (choice.days)}
            <button
              class="hint"
              class:on={item.cycleSaid && item.cycleDays === choice.days}
              type="button"
              onclick={() => tellCycle(item.id, choice.days)}
            >
              {choice.label}
            </button>
          {/each}
        </div>

        <label class="own-label" for="pantry-days">або своє число, у днях</label>
        <div class="own">
          <input
            id="pantry-days"
            type="number"
            min="1"
            step="1"
            inputmode="numeric"
            placeholder="днів"
            bind:value={ownDays}
          />
          <button
            class="secondary"
            type="button"
            disabled={!ownValid}
            onclick={() => tellCycle(item.id, ownCycle)}
          >
            Записати
          </button>
        </div>

        <p class="voice-note">
          я бачу лише чеки «Сільпо» — те, що ти береш в іншому магазині, звідти не видно
        </p>

        <div class="add-actions">
          <button class="secondary" type="button" onclick={() => (timing = null)}>
            Скасувати
          </button>
          {#if item.cycleSaid}
            <button class="primary wide" type="button" onclick={() => tellCycle(item.id, null)}>
              рахуй з чеків
            </button>
          {/if}
        </div>
      </Modal>
    {/if}

    <Dictaphone
      open={dictOpen}
      onPhrase={(text) => spoken.push(text)}
      refine={splitSpoken}
      onClose={flushSpoken}
      onError={(message) => (voiceNote = message)}
    />

    {#if failed !== null}
      <p class="nothing">
        {failed}
        <button class="link" type="button" onclick={onRetry}>Спробувати ще раз</button>
      </p>
    {:else if loaded && items.length === 0}
      {#if !bySelf}
        <p class="nothing">
          {source !== null ? pantryEmptyNote(source) : 'Коморі поки нема з чого рахуватись.'}
          Вид можна додати й руками, але цикл і залишок дадуть тільки чеки.
        </p>
      {:else if (source?.unlisted ?? 0) === 0}
        <p class="nothing">
          {source !== null ? pantryEmptyNote(source) : 'Список поки нема з чого звіряти.'}
        </p>
      {/if}
    {/if}

    {#if needle !== '' && shown.length === 0}
      <p class="nothing">
        «{filter.trim()}» у коморі немає.
        <button class="link" type="button" onclick={() => onAddNamed(filter.trim())}>
          Додати цей вид
        </button>
      </p>
    {/if}


    <ul class="list" data-tour="pantry-list">
      {#each rows as shelf (shelf.item.id)}
        {@const item = shelf.item}
        {@const leftLabel = leftText(item)}
        {#if shelf.head !== null}
          <li class="band">
            <span class="band-name">{shelf.head}</span>
            <span class="band-count">
              {plural(shelf.size, NAMES)} з чеків{shelf.out > 0
                ? `, ${shelf.out} закінчується`
                : ''}
            </span>
            <button
              class="band-split"
              type="button"
              aria-label="Розділити «{shelf.head}»: це різні види"
              onclick={() => onSplit(shelf.head ?? '')}
            >
              розділити
            </button>
          </li>
        {/if}
        <li class="row" class:grouped={item.group !== null}>
          <div class="thumb" aria-hidden="true">
            {#if item.imageUrl && !failedImages.has(item.id)}
              <img
                src={item.imageUrl}
                alt=""
                loading="lazy"
                onerror={() => (failedImages = new Set(failedImages).add(item.id))}
              />
            {:else}
              {NO_PHOTO.pantry}
            {/if}
          </div>

          <div class="body">
            <div class="name">{item.label}</div>
            {#if item.writtenAs.length > 0}
              <div class="wrote">{wroteLine(item.writtenAs)}</div>
            {/if}
            {#if item.source === 'receipts'}
              <button
                class="state say"
                class:empty={item.runningOut}
                class:said={item.cycleSaid}
                class:stale={busy.has(item.id)}
                type="button"
                aria-label="{timingLabel(item)}: {item.label}"
                onclick={() => {
                  ownDays = item.cycleSaid ? (item.cycleDays ?? '') : ''
                  timing = item
                }}
              >
                {item.state}
              </button>
            {:else}
              <div class="state" class:empty={item.runningOut} class:stale={busy.has(item.id)}>
                {item.state}
              </div>
            {/if}
            {#if item.arrived}
              <div class="arrived">{item.arrived}</div>
            {/if}
            {#if item.sanity}
              <div class="sense-line" class:asking={item.ask}>{item.sanity}</div>
            {/if}
            {#if hasUnder(item)}
              <button
                class="more"
                type="button"
                aria-expanded={opened.has(item.id)}
                onclick={() => togglePartsOf(item.id)}
              >
                докладніше
                {#if item.mandate?.agreed}<span class="more-mark">заміна</span>{/if}
                <span class="parts-arrow" aria-hidden="true">
                  {opened.has(item.id) ? '↑' : '↓'}
                </span>
              </button>
            {/if}
          </div>

          <div class="gauge">
            {#if item.qty !== null}
              <div class="stepper">
                <button
                  class="step"
                  type="button"
                  aria-label="Менше: {item.label}"
                  onclick={() => onAdjust(item.id, -1)}
                >
                  -
                </button>
                <div class="qty num">{amount(item.qty, item.unit)}</div>
                <button
                  class="step"
                  type="button"
                  aria-label="Більше: {item.label}"
                  onclick={() => onAdjust(item.id, 1)}
                >
                  +
                </button>
              </div>
            {/if}

            {#if item.leftRatio !== null}
              {@const percent = fill(item.leftRatio)}
              <div
                class="bar"
                class:stale={busy.has(item.id)}
                role="progressbar"
                aria-label="залишок: {item.label}"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={percent}
              >
                <span style:width="{percent}%"></span>
              </div>
            {/if}
            {#if leftLabel !== null}
              <div class="left num" class:out={item.runningOut} class:stale={busy.has(item.id)}>
                {leftLabel}
              </div>
            {/if}

            {#if item.runningOut && item.source === 'receipts'}
              {@const choices = choicesFor(item)}
              <button
                class="already"
                type="button"
                onclick={() =>
                  choices.length === 0 ? tellBought(item.id, null) : (asking = item)}
              >
                {busy.has(item.id) ? '…' : 'вже купив'}
              </button>
            {/if}

            {#if item.wanted}
              <span class="in-list">у списку на покупку</span>
            {:else}
              <button
                class="to-list"
                type="button"
                aria-label="У список на покупку: {item.label}"
                onclick={() => onToList(item.label)}
              >
                + у список
              </button>
            {/if}

            {#if item.source === 'receipts'}
              <button
                class="forget"
                type="button"
                aria-label="Не показувати «{item.label}»"
                title="не показувати цей вид у коморі"
                onclick={() => onHide(item.id)}
              >
                ×
              </button>
            {/if}

            {#if item.source === 'manual'}
              <button
                class="forget"
                type="button"
                aria-label="Прибрати «{item.label}»"
                title="прибрати — цей вид додав ти"
                onclick={() => onForget(item.id)}
              >
                ×
              </button>
            {/if}
          </div>
          {#if opened.has(item.id)}
            <div class="under">
            {#if item.usual}
              <div class="pick">купує {item.usual.name} · {item.usual.share}</div>
            {/if}
            {#if item.promo}
              <div class="pick">{item.promo}</div>
            {/if}
            {#if item.parts.length > 1}
              {#if opened.has(item.id)}
                <ul class="parts">
                  {#each item.parts as part}
                    <li class:fresh={part.fresh}>
                      <span class="parts-name">{part.label}</span>
                      <span class="parts-when">
                        {part.daysSince === null
                          ? 'коли -- невідомо'
                          : `${part.daysSince} дн тому`} · {part.receipts}
                        {part.receipts === 1 ? 'раз' : 'рази'}
                      </span>
                    </li>
                  {/each}
                </ul>
                {#if item.mandate && !item.mandate.agreed}
                  <div class="offer">
                    <p class="offer-head">якщо цього не буде — везти по черзі:</p>
                    <ol class="offer-chain">
                      {#each item.mandate.links as link}
                        <li>{link.name}</li>
                      {/each}
                    </ol>
                    <button
                      class="offer-yes"
                      type="button"
                      disabled={busy.has(item.id)}
                      onclick={() =>
                        onMandate(
                          item.id,
                          item.mandate ? item.mandate.links.map((l) => l.article) : [],
                        )}
                    >
                      погодити заміну
                    </button>
                  </div>
                {/if}
              {/if}
            {/if}

            {#if item.mandate && item.mandate.agreed}
              <div class="hand">
                <span class="hand-text">
                  <span class="hand-head">погоджена заміна — збирач читатиме це:</span>
                  <span class="hand-chain">
                    якщо немає — {item.mandate.links.map((l) => l.name).join(', потім ')}, інакше
                    не брати
                  </span>
                </span>
                <button
                  class="hand-off"
                  type="button"
                  disabled={busy.has(item.id)}
                  onclick={() => onMandate(item.id, [])}
                >
                  зняти
                </button>
              </div>
            {/if}
            </div>
          {/if}
        </li>
      {/each}
    </ul>


  {#if apart.length > 0}
      <div class="hidden-note">
        <span>не зводжу в один рядок {apart.length}:</span>
        {#each apart as intent}
          <button
            class="hint"
            type="button"
            aria-label="Звести «{intent}» назад в один рядок"
            onclick={() => onUnsplit(intent)}
          >
            {intent} ‹
          </button>
        {/each}
      </div>
    {/if}

    {#if hidden.length > 0}
      <div class="hidden-note">
        <span>ти прибрав з обліку {hidden.length} -- дотик повертає:</span>
        {#each hidden as label}
          <button
            class="hint"
            type="button"
            aria-label="Повернути «{label}» у комору"
            onclick={() => onUnhide(label)}
          >
            {label} ‹
          </button>
        {/each}
      </div>
    {/if}

    {#if atBar.length > 0}
      <p class="bar-note">
        алкоголь веде бар, не комора -- {atBar.length}
        {atBar.length === 1 ? 'вид' : 'види'}: {atBar.join(' · ')}
      </p>
    {/if}

    <div class="dock-spacer" style:height="{dockHeight}px" aria-hidden="true"></div>
    <CloseDock label={backLabel} onClick={onBack} />
  </div>
{/if}

<style>
  .dock-spacer {
    flex: none;
  }

  .why {
    margin: 0 0 12px;
  }

  .step-args {
    margin-top: 4px;
    font-size: 11px;
    line-height: 1.5;
    color: var(--muted);
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }

  .cost {
    margin: 6px 0 0;
    padding: 0 12px;
    font-size: 11px;
    color: var(--faint);
  }

  .why > summary {
    padding: 9px 12px;
    border-radius: 12px;
    font-size: 12.5px;
    color: var(--muted);
    border: 1px solid var(--hair);
    background: transparent;
    cursor: pointer;
    list-style: none;
  }

  .why > summary::-webkit-details-marker {
    display: none;
  }

  .why ol {
    margin: 8px 0 0;
    padding: 0 0 0 18px;
    display: grid;
    gap: 8px;
  }

  .why li {
    color: var(--ink);
    font-size: 12.5px;
  }

  .why .said {
    margin: 0;
  }

  .why .because {
    margin: 2px 0 0;
    color: var(--muted);
    font-size: 12px;
  }

  .source {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--gap-2, 8px);
    margin: var(--gap-2, 8px) 0 var(--gap-3, 12px);
  }

  .source > .deeds {
    flex: 0 0 auto;
  }

  .gear {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    color: var(--muted);
  }

  .gear svg {
    width: 13px;
    height: 13px;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.8;
    stroke-linecap: round;
  }

  .modes {
    display: inline-flex;
    align-self: flex-start;
    border: 1px solid var(--hair-strong);
    border-radius: var(--radius-pill, 999px);
    overflow: hidden;
  }

  .mode {
    border: 0;
    background: transparent;
    color: var(--muted);
    padding: 6px 14px;
    font: inherit;
    font-size: 0.85rem;
    cursor: pointer;
  }

  .mode[aria-pressed='true'] {
    background: var(--acc-soft);
    color: var(--ink);
    font-weight: 600;
  }

  .mode:disabled,
  .deed:disabled,
  .link:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .deeds {
    display: flex;
    flex-wrap: wrap;
    gap: var(--gap-2, 8px);
  }

  .deed {
    border: 1px solid var(--hair-strong);
    border-radius: var(--radius-pill, 999px);
    background: transparent;
    color: var(--muted);
    padding: 6px 14px;
    font: inherit;
    font-size: 0.85rem;
    cursor: pointer;
  }

  .deed.lead {
    border-color: var(--badge-edge);
    background: var(--badge-fill);
    color: var(--ink);
    font-weight: 700;
  }

  .deed.danger {
    border-color: var(--danger, var(--hair-strong));
    color: var(--warn);
  }

  .deed-said {
    margin: 6px 0 0;
    font-size: 12px;
    line-height: 1.4;
    color: var(--good);
  }

  .working {
    display: flex;
    align-items: center;
    gap: 7px;
    margin: 6px 0 0;
    font-size: 12px;
    line-height: 1.4;
    color: var(--muted);
  }

  .working .dot {
    width: 6px;
    height: 6px;
    flex: none;
    border-radius: 50%;
    background: var(--accent);
    animation: komora-pulse 1.2s ease-in-out infinite;
  }

  @keyframes komora-pulse {
    0%,
    100% {
      opacity: 0.35;
    }
    50% {
      opacity: 1;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .working .dot {
      animation: none;
    }
  }


  .refined {
    margin: 6px 0 0;
    font-size: 12px;
    line-height: 1.4;
    color: var(--muted);
  }

  .outside {
    margin: 0;
    color: var(--muted);
    font-size: 0.85rem;
  }

  .cover {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
  }
  .cover-dock {
    margin-top: auto;
    padding: 0 16px;
  }

  .ask-door {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    width: 100%;
    padding: 10px 14px;
    margin-bottom: 12px;
    border-radius: 16px;
    border: 1px solid var(--hair-strong);
    background: var(--acc-soft);
    text-align: left;
  }

  .ask-door-text {
    font-size: 13px;
    font-weight: 700;
  }

  .ask-badge {
    min-width: 22px;
    padding: 2px 7px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 800;
    text-align: center;
    color: var(--pri-ink);
    background: var(--accent);
  }


  .ask-count {
    margin: 0;
    font-size: 11.5px;
    font-weight: 700;
    color: var(--muted);
  }

  .ask-name {
    margin: 0;
    font-size: 14px;
    font-weight: 700;
    color: var(--ink);
  }

  .ask-q {
    margin: 0;
    font-size: 13px;
    font-weight: 600;
    line-height: 1.4;
    color: var(--ink);
  }

  .ask-seen {
    margin: 0;
    font-size: 11.5px;
    line-height: 1.4;
    color: var(--muted);
  }

  .ask-sense {
    margin: 0 0 2px;
    font-size: 13px;
    line-height: 1.4;
    color: var(--ink);
  }

  .ask-rest {
    margin: 0 0 2px;
    font-size: 11.5px;
    line-height: 1.4;
    color: var(--muted);
  }

  .asked {
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding: 8px 16px 24px;
  }

  .asked h2 {
    margin: 0;
    font-size: 17px;
    font-weight: 800;
    line-height: 1.25;
    color: var(--ink);
  }

  .asked .why {
    margin: -8px 0 2px;
    font-size: 12.5px;
    line-height: 1.45;
    color: var(--muted);
  }

  .ask {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 14px 16px;
    border-radius: 16px;
    border: 1px solid var(--hair-strong);
    background: var(--acc-soft);
  }

  .ask .ask-q {
    margin-top: 2px;
  }

  .ask .suggest {
    margin-top: 12px;
  }

  .ask-usual {
    margin: 3px 0 0;
    font-size: 12px;
    line-height: 1.4;
    color: var(--muted);
  }

  .asked .covers {
    margin: 8px 0 0;
    font-size: 11.5px;
    line-height: 1.4;
    color: var(--muted);
  }

  .asked-dock {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
    margin-top: 2px;
  }

  .asked-dock .link {
    padding: 4px 0;
    border: 0;
    background: transparent;
    color: var(--muted);
    font-size: 12px;
    font-weight: 600;
    text-decoration: underline;
    cursor: pointer;
  }

  .link {
    border: 0;
    background: transparent;
    color: var(--accent, var(--ink));
    padding: 0;
    font: inherit;
    font-size: inherit;
    text-decoration: underline;
    cursor: pointer;
  }

  .pantry {
    padding: 16px 16px 0;
    flex: 1;
    display: flex;
    flex-direction: column;
  }

  .nothing {
    font-size: 13px;
    color: var(--muted);
    line-height: 1.55;
    padding: 10px 0;
  }

  .link {
    color: var(--accent);
    font: inherit;
    font-weight: 700;
    text-decoration: underline;
    text-underline-offset: 3px;
  }

  .already {
    padding: 5px 9px;
    border-radius: 9px;
    font-size: 11.5px;
    font-weight: 700;
    white-space: nowrap;
    color: var(--muted);
    border: 1px solid var(--hair-strong);
    background: var(--chip-bg);
  }

  .already:disabled {
    opacity: 0.55;
  }

  .forget {
    position: absolute;
    top: 10px;
    right: 10px;
    width: 26px;
    height: 26px;
    flex: none;
    border-radius: 8px;
    font-size: 14px;
    line-height: 1;
    color: var(--muted);
    border: 1px solid transparent;
    background: transparent;
  }

  .forget:hover {
    color: var(--ink);
    border-color: var(--hair-strong);
  }

  .search {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 10px;
  }

  .search input {
    flex: 1;
    min-width: 0;
    min-height: 42px;
    padding: 0 12px;
    border-radius: 12px;
    border: 1px solid var(--hair);
    background: var(--chip-bg);
    color: var(--ink);
    font: inherit;
    font-size: 14px;
  }

  .found {
    flex: none;
    font-size: 12.5px;
    color: var(--muted);
    white-space: nowrap;
  }

  .intro {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 12px;
  }

  .intro p {
    flex: 1;
    font-size: 13px;
    color: var(--muted);
    line-height: 1.5;
  }

  .primary {
    flex: none;
    padding: 0 12px;
    min-height: 44px;
    border-radius: 11px;
    font-size: 12.5px;
    font-weight: 700;
    white-space: nowrap;
    color: var(--pri-ink);
    background: var(--pri-bg);
  }

  .primary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .ask {
    font-size: 14px;
    font-weight: 700;
    color: var(--ink);
    margin-bottom: 4px;
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

  .suggest-note {
    margin: 10px 0 0;
    font-size: 12px;
    line-height: 1.35;
    color: var(--faint);
  }

  .settings {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .bar-note {
    margin: 10px 0 0;
    font-size: 12px;
    line-height: 1.35;
    color: var(--faint);
  }

  .hidden-note {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px 6px;
    margin: 14px 0 0;
    color: var(--muted);
    font-size: 12px;
  }

  .hint {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
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

  .hint .for {
    font-size: 10.5px;
    font-weight: 600;
    color: var(--faint);
  }

  .hint.on {
    color: var(--ink);
    border-color: var(--accent);
    background: var(--chip-bg);
  }

  .own-label {
    display: block;
    margin-top: 11px;
    font-size: 11.5px;
    color: var(--faint);
  }

  .own {
    display: flex;
    gap: 8px;
    margin-top: 6px;
  }

  .own input {
    flex: 1;
    min-width: 0;
  }

  .voice-note {
    margin-top: 8px;
    font-size: 11.5px;
    color: var(--faint);
    line-height: 1.4;
  }

  .voice-error {
    margin-top: 8px;
    font-size: 11.5px;
    color: var(--warn);
    line-height: 1.4;
  }

  .add-actions {
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

  .wide {
    flex: 1.3;
  }

  .rail {
    display: flex;
    flex-direction: row;
    gap: 4px;
    overflow-x: auto;
    padding: 4px;
    border-radius: 999px;
    border: 1px solid var(--hair);
    background: var(--list-bg);
    scrollbar-width: none;
  }

  .rail::-webkit-scrollbar {
    display: none;
  }

  .rail-wrap {
    position: sticky;
    top: var(--chrome-h, 96px);
    z-index: 10;
    margin-bottom: 10px;
    background: var(--app-bg);
  }

  .rail-step {
    position: absolute;
    top: 1px;
    bottom: 1px;
    z-index: 1;
    display: flex;
    align-items: center;
    width: 42px;
    padding: 0;
    border: none;
    color: var(--ink);
    cursor: pointer;
  }

  .rail-step.back {
    left: 1px;
    justify-content: flex-start;
    padding-left: 4px;
    border-radius: 999px 0 0 999px;
    background: linear-gradient(to right, var(--list-bg) 86%, transparent);
  }

  .rail-step.ahead {
    right: 1px;
    justify-content: flex-end;
    padding-right: 4px;
    border-radius: 0 999px 999px 0;
    background: linear-gradient(to left, var(--list-bg) 86%, transparent);
  }

  .rail-step svg {
    width: 16px;
    height: 16px;
    fill: none;
    stroke: currentColor;
    stroke-width: 2;
    stroke-linecap: round;
    stroke-linejoin: round;
  }

  .aisle {
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 6px;
    flex: 0 0 auto;
    max-width: 45%;
    padding: 6px 12px;
    border: none;
    border-radius: 999px;
    background: transparent;
    color: var(--muted);
    cursor: pointer;
  }

  .aisle svg {
    width: 15px;
    height: 15px;
    flex: 0 0 auto;
    fill: none;
    stroke: currentColor;
    stroke-width: 1.6;
    stroke-linecap: round;
    stroke-linejoin: round;
  }

  .aisle-name {
    font-size: 12px;
    line-height: 1.2;
    min-width: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .aisle-rows {
    font-size: 11px;
    font-weight: 700;
    opacity: 0.65;
    flex: 0 0 auto;
  }

  .aisle.on {
    background: var(--acc-soft);
    color: var(--ink);
    font-weight: 600;
  }

  .picked {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 6px;
    margin: 0 0 8px;
    color: var(--muted);
    font-size: 12px;
  }

  .list {
    border-radius: 18px;
    overflow: hidden;
    border: 1px solid var(--hair);
    background: var(--list-bg);
    margin-bottom: 16px;
  }

  .row {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: start;
    gap: 8px 12px;
    padding: 12px 14px;
    border-bottom: 1px solid var(--hair);
    position: relative;
  }

  .row > .body {
    grid-column: 2;
  }

  .row > .gauge {
    grid-column: 2;
  }

  .row > .under {
    grid-column: 1 / -1;
  }

  .row:last-child {
    border-bottom: none;
  }

  .band {
    display: flex;
    align-items: baseline;
    gap: 8px;
    padding: 10px 14px 4px;
    color: var(--muted);
    font-size: 12px;
  }

  .band-name {
    flex: 0 1 auto;
    min-width: 0;
    overflow-wrap: anywhere;
    font-weight: 700;
    font-size: 13px;
    color: var(--ink);
  }

  .band-count {
    flex: 1;
    min-width: 0;
  }

  .band-split {
    flex: none;
    padding: 6px 8px;
    min-height: 32px;
    border: none;
    background: transparent;
    color: var(--muted);
    font-size: 12px;
    font-weight: 600;
    text-decoration: underline dotted;
    text-underline-offset: 3px;
  }

  .row.grouped .thumb {
    margin-left: 10px;
  }

  .to-list {
    padding: 6px 9px;
    min-height: 32px;
    border-radius: 9px;
    font-size: 11.5px;
    font-weight: 600;
    white-space: nowrap;
    color: var(--muted);
    border: 1px solid var(--hair-strong);
    background: transparent;
  }

  .in-list {
    padding: 6px 0;
    font-size: 11.5px;
    font-weight: 600;
    white-space: nowrap;
    color: var(--muted);
  }

  .parts-arrow {
    display: inline-block;
    width: 1em;
    text-align: center;
  }

  .more {
    align-self: flex-start;
    display: inline-flex;
    align-items: center;
    gap: 5px;
    margin-top: 6px;
    padding: 0;
    border: 0;
    background: transparent;
    font-size: 11.5px;
    font-weight: 600;
    color: var(--faint);
    cursor: pointer;
  }

  .more-mark {
    padding: 1px 6px;
    border-radius: 999px;
    border: 1px solid var(--hair-strong);
    color: var(--muted);
    font-size: 10.5px;
  }

  .under {
    display: flex;
    flex-direction: column;
    gap: 4px;
    margin-top: 8px;
    padding-top: 10px;
    border-top: 1px solid var(--hair);
  }


  .parts {
    list-style: none;
    margin: 2px 0 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }

  .parts li {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 6px;
    font-size: 11.5px;
    color: var(--muted);
  }

  .parts li.fresh .parts-name {
    font-weight: 700;
    color: var(--ink);
  }

  .parts-name {
    min-width: 0;
  }

  .row:has(.parts) {
    align-items: flex-start;
  }

  .hand,
  .offer {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 6px;
    font-size: 11.5px;
  }

  .offer {
    flex-direction: column;
    align-items: stretch;
    gap: 4px;
    margin-top: 6px;
    padding-left: 9px;
    border-left: 2px solid var(--acc-half);
  }

  .offer-head {
    margin: 0;
    color: var(--muted);
    font-weight: 700;
  }

  .offer-chain {
    margin: 0;
    padding-left: 16px;
    color: var(--muted);
    list-style: decimal;
  }

  .offer-chain li {
    padding: 1px 0;
  }

  .offer-yes {
    align-self: flex-start;
  }

  .hand {
    flex-direction: column;
    align-items: flex-start;
    gap: 3px;
  }

  .hand-text {
    color: var(--ink);
    min-width: 0;
  }

  .hand-head {
    display: block;
    color: var(--muted);
    font-weight: 700;
  }

  .hand-chain {
    display: block;
  }

  .hand-off,
  .offer-yes {
    border: 0;
    background: none;
    padding: 0;
    font: inherit;
    color: var(--accent);
    text-decoration: underline;
    cursor: pointer;
  }

  .hand-off:disabled,
  .offer-yes:disabled {
    color: var(--muted);
    cursor: default;
  }

  .thumb {
    width: 44px;
    height: 44px;
    border-radius: 12px;
    flex: none;
    display: grid;
    place-items: center;
    font-size: 18px;
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

  .state {
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 3;
    line-clamp: 3;
    overflow: hidden;
  }

  .pick {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .arrived {
    margin-top: 2px;
    font-size: 12px;
    font-weight: 700;
    color: var(--good);
  }

  .wrote {
    font-size: 12px;
    margin-top: 3px;
    color: var(--muted);
    white-space: normal;
    overflow-wrap: anywhere;
  }

  .sense-line {
    font-size: 12px;
    margin-top: 4px;
    color: var(--muted);
    font-style: italic;
    white-space: normal;
    overflow-wrap: anywhere;
  }

  .sense-line.asking {
    color: var(--ink);
    font-style: normal;
  }

  .name {
    font-size: 14px;
    font-weight: 700;
    line-height: 1.25;
    white-space: normal;
    overflow-wrap: anywhere;
  }

  .state {
    font-size: 12px;
    margin-top: 3px;
    color: var(--muted);
  }

  .stale {
    opacity: 0.4;
    transition: opacity 120ms ease-out;
  }

  .state.empty {
    color: var(--warn);
  }

  .state.say {
    display: block;
    width: 100%;
    text-align: left;
    background: none;
    border: 0;
    padding: 0;
    text-decoration: underline dotted var(--hair-strong);
    text-underline-offset: 3px;
  }

  .state.say.said {
    text-decoration: underline solid var(--accent);
  }

  .timing {
    display: block;
    margin-top: 10px;
    padding: 2px 0;
    font-size: 12px;
    text-align: left;
    color: var(--accent);
    background: none;
    border: 0;
    border-bottom: 1px dashed var(--accent);
    line-height: 1.35;
  }

  .pick {
    font-size: 11px;
    color: var(--badge);
    margin-top: 2px;
  }

  .gauge {
    display: flex;
    flex-flow: row wrap;
    align-items: center;
    gap: 6px 8px;
  }

  .gauge .bar {
    flex: 1 1 100%;
  }

  .gauge .already,
  .gauge .to-list {
    flex: 1 1 auto;
  }

  .stepper {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: none;
  }

  .bar {
    height: 6px;
    border-radius: 3px;
    overflow: hidden;
    background: var(--chip-bg);
    border: 1px solid var(--hair-strong);
  }

  .bar span {
    display: block;
    height: 100%;
    background: var(--pri-bg);
  }

  .left {
    font-size: 11.5px;
    font-weight: 700;
    text-align: center;
    color: var(--muted);
  }

  .left.out {
    color: var(--warn);
  }

  .step {
    width: 34px;
    min-height: 36px;
    display: grid;
    place-items: center;
    border-radius: 10px;
    font-size: 16px;
    font-weight: 700;
    line-height: 1;
    color: var(--ink);
    border: 1px solid var(--hair-strong);
    background: var(--chip-bg);
  }

  .qty {
    font-size: 13.5px;
    font-weight: 700;
    min-width: 52px;
    text-align: center;
  }

  @media (width <= 380px) {
    .pantry {
      padding-inline: 12px;
    }

    .row {
      gap: 8px;
      padding: 12px 10px;
    }

    .step {
      width: 34px;
    }

    .stepper {
      gap: 5px;
    }

    .qty {
      min-width: 44px;
      font-size: 12.5px;
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
  .ask-card {
    position: relative;
    padding-top: 2px;
  }
  .ask-close {
    position: absolute;
    top: -6px;
    right: -6px;
    width: 34px;
    height: 34px;
    margin: 0;
    padding: 0;
    border: 0;
    border-radius: 999px;
    display: grid;
    place-items: center;
    font-size: 15px;
    line-height: 1;
    color: var(--muted);
    background: transparent;
    cursor: pointer;
  }
  .ask-row {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 16px;
    margin-top: 6px;
  }
  .ask-link {
    border: 0;
    background: transparent;
    padding: 4px 0;
    font: inherit;
    font-size: 12.5px;
    color: var(--muted);
    text-decoration: underline;
    cursor: pointer;
  }
</style>

{#if settingsOpen}
  <Modal label="Як вести комору">
    <div class="settings">
      <div class="modes" role="group" aria-label="чим наповнювати список">
        <button
          type="button"
          class="mode"
          aria-pressed={!bySelf}
          disabled={sourceBusy}
          onclick={() => {
            settingsOpen = false
            onSource('receipts')
          }}
        >
          з покупок
        </button>
        <button
          type="button"
          class="mode"
          aria-pressed={bySelf}
          disabled={sourceBusy}
          onclick={() => {
            settingsOpen = false
            onSource('manual')
          }}
        >
          веду сам
        </button>
      </div>
      <div class="deeds">
        <button
          type="button"
          class="deed"
          disabled={sourceBusy}
          onclick={() => {
            settingsOpen = false
            onGenerate()
          }}
        >
          Скласти з покупок
        </button>
        {#if wipeAsked}
          <button
            type="button"
            class="deed danger"
            disabled={sourceBusy}
            onclick={() => {
              wipeAsked = false
              settingsOpen = false
              onWipe()
            }}
          >
            Точно стерти
          </button>
          <button type="button" class="deed" onclick={() => (wipeAsked = false)}>
            Ні
          </button>
        {:else}
          <button type="button" class="deed" onclick={() => (wipeAsked = true)}>
            Стерти список
          </button>
        {/if}
      </div>
      <div class="add-actions">
        <button class="secondary" type="button" onclick={() => (settingsOpen = false)}>
          Закрити
        </button>
      </div>
    </div>
  </Modal>
{/if}
