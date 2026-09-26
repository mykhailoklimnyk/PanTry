<script lang="ts">
  import CartLineRow from '../CartLine.svelte'
  import Clarify from '../Clarify.svelte'
  import Dictaphone from '../Dictaphone.svelte'
  import MicButton from '../MicButton.svelte'
  import { asksWord } from '../attention'
  import Modal from '../Modal.svelte'
  import Rules from '../Rules.svelte'
  import { BAND_TOLERANCE, BUILD_MODES, isBuying } from '../ui'
  import { ASK_PHRASE } from '../facts'
  import { parseList, splitSpoken } from '../list'
  import type { Loaded } from '../data'
  import { voiceAvailable } from '../speech'
  import { collectorActs, heldByFork } from '../feedback'
  import { hasPick } from '../picks'
  import { amount, firstClause, kg, plural, slotLabel, uah, uahRound } from '../format'
  import { vendorReason } from '../vendor'
  import type {
    Basket,
    CarryOverState,
    CartCarryOver,
    CartLine,
    CheckoutResult,
    ClarifyAnswer,
    ClarifyPick,
    DeliveryOption,
    Exclusion,
    Pantry,
    Place as Where,
    SpendTarget,
  } from '../types'

  interface Props {
    basket: Basket
    once: Set<string>
    qty: Record<string, number>
    extras: CartLine[]
    mode: string
    rules: Exclusion[]
    rulesNote: string | null
    deliveryOptions: DeliveryOption[]
    deliveryLoaded: Loaded<DeliveryOption[]> | null
    onDeliveryRetry: () => void
    delivery: string
    place: Where | null
    budget: number
    spend: SpendTarget | null
    pantrySource: Omit<Pantry, 'items'> | null
    draft: string
    stale: boolean
    staleLabel: string
    touched: boolean
    checkout: CheckoutResult | null
    carryOver: CartCarryOver | null
    checkingOut: boolean
    confirmClear: boolean
    onToggleOnce: (id: string) => void
    onRemove: (id: string) => void
    onAdd: (id: string) => void
    onQty: (id: string, next: number) => void
    onExtra: (items: CartLine[]) => void
    onClearAll: () => void
    onRestore: () => void
    onToggleRule: (id: string) => void
    onRemoveRule: (id: string) => void
    onDraft: (value: string) => void
    onAddRule: () => void
    onBudget: (value: number) => void
    onSave: () => void
    onDelivery: (id: string) => void
    onStale: () => void
    onAnswer: (answer: ClarifyAnswer) => void
    onPick: (intent: string, pick: ClarifyPick) => void
    onCheckout: () => void
    onRebuild: () => void
    onKeepBudget: (named: number) => void
    onCarryOver: (existing: CarryOverState) => void
    onPlace: () => void
    onSwaps: (focus?: 'urgent' | 'all') => void
    onCheaper: (article: string, to: string) => void
    onTrace: () => void
    onWhy: (id: string) => void
    refilling: boolean
    answering?: Record<string, string>
    reasked?: string[]
    onRefill: (intents: string[]) => void
  }

  const {
    basket,
    once,
    qty,
    extras,
    mode,
    rules,
    rulesNote,
    deliveryOptions,
    deliveryLoaded,
    onDeliveryRetry,
    delivery,
    place,
    budget,
    spend,
    pantrySource,
    draft,
    stale,
    staleLabel,
    touched,
    checkout,
    carryOver,
    checkingOut,
    confirmClear,
    onToggleOnce,
    onRemove,
    onAdd,
    onQty,
    onExtra,
    onClearAll,
    onRestore,
    onToggleRule,
    onRemoveRule,
    onDraft,
    onAddRule,
    onBudget,
    onSave,
    onDelivery,
    onStale,
    onAnswer,
    onPick,
    onCheckout,
    onRebuild,
    onKeepBudget,
    onCarryOver,
    onPlace,
    onSwaps,
    onCheaper,
    onTrace,
    onWhy,
    refilling,
    answering = {},
    reasked = [],
    onRefill,
  }: Props = $props()

  const lines = $derived.by(() => {
    const byArticle = new Map<string, CartLine>()
    for (const l of [...basket.lines, ...extras]) {
      const corrected = { ...l, qty: qty[l.externalProductId] ?? l.qty }
      const seen = byArticle.get(corrected.externalProductId)
      if (seen) seen.qty = Math.max(seen.qty, corrected.qty)
      else byArticle.set(corrected.externalProductId, corrected)
    }
    return [...byArticle.values()]
  })
  const buying = $derived(lines.filter(isBuying))
  let shared = $state('')
  function shareText(): string {
    const head = `ПанTry, кошик на ${slot || 'найближчий слот'}, ~${uahRound(total)}`
    const rows = buying.map(
      (line) =>
        `${line.qty} ${line.unit || 'шт'}  ${line.name}${line.cardUrl ? `  ${line.cardUrl}` : ''}`,
    )
    return [head, ...rows, 'Зібрано ПанTry: https://pantry.klimnyk.dev'].join('\n')
  }
  async function share(): Promise<void> {
    const text = shareText()
    try {
      if (typeof navigator.share === 'function') {
        await navigator.share({ text })
        shared = 'надіслано'
        return
      }
      await navigator.clipboard.writeText(text)
      shared = 'скопійовано'
    } catch {
      shared = ''
    }
  }
  const headOf = (name: string): string => name.trim().split(/\s+/)[0]?.toLowerCase() ?? ''
  const kinOf = $derived.by(() => {
    const counts = new Map<string, number>()
    for (const line of buying) counts.set(headOf(line.name), (counts.get(headOf(line.name)) ?? 0) + 1)
    return counts
  })

  const ignoredNote = $derived((basket.textIgnored ?? []).join(", "))
  let ignoredSeen = $state("")

  const total = $derived(buying.reduce((sum, l) => sum + l.qty * l.price, 0))
  const baseTotal = $derived(
    buying.reduce((sum, l) => sum + l.qty * (l.basePrice ?? l.price), 0),
  )
  const savings = $derived(baseTotal - total)
  const paid = $derived(checkout?.totals ?? null)

  const blockerReasons = $derived.by(() => {
    if (!checkout) return []
    const c = checkout
    return c.blockers.map((code, i) => vendorReason(code, c.blockerNotes[i] ?? ''))
  })

  const skippedNote = $derived.by(() => {
    if (!checkout || checkout.skipped.length === 0) return ''
    const counts = new Map<string, number>()
    for (const item of checkout.skipped) counts.set(item.reason, (counts.get(item.reason) ?? 0) + 1)
    const parts = [...counts.entries()].map(([reason, n]) => (n > 1 ? `${reason} × ${n}` : reason))
    return `у кошик поїхало ${checkout.written} з ${buying.length} — ${shortList(parts)}`
  })
  const weight = $derived(buying.reduce((sum, l) => sum + l.qty * (l.weightKg ?? 0), 0))
  const unweighed = $derived(buying.filter((l) => l.weightKg === null).length)

  const refillable = $derived(basket.postponed.filter((item) => item.refillable))
  const held = $derived(basket.postponed.filter((item) => !item.refillable))

  const missedCount = $derived(
    basket.unresolved.length +
      basket.declined.length +
      basket.notCollected.length +
      held.length +
      basket.trimmed.length +
      basket.fillCut.length,
  )
  const missedGroups = $derived(
    [
      basket.unresolved.length,
      basket.declined.length,
      basket.notCollected.length,
      held.length,
      basket.trimmed.length,
      basket.fillCut.length,
    ].filter((n) => n > 0).length,
  )
  const grouped = $derived(
    [
      ...held
        .reduce((map, item) => {
          map.set(item.reason, [...(map.get(item.reason) ?? []), item.intent])
          return map
        }, new Map<string, string[]>())
        .entries(),
    ],
  )
  const refillCost = $derived(
    refillable.reduce((sum, item) => sum + (item.estimate ?? 0), 0),
  )
  const unpriced = $derived(refillable.filter((item) => item.estimate === null).length)

  const limit = $derived(basket.budget)
  const bandLow = $derived(limit === null ? null : round(limit * (1 - BAND_TOLERANCE)))
  const bandHigh = $derived(limit === null ? null : round(limit * (1 + BAND_TOLERANCE)))
  const overBudget = $derived(bandHigh === null ? 0 : round(total - bandHigh))
  const headroom = $derived(bandLow === null ? null : round(bandLow - total))

  const shortNote = $derived(
    headroom === null || headroom <= 0 || bandLow === null || limit === null
      ? ''
      : `бракує ${uahRound(headroom)} до нижньої межі ${uahRound(bandLow)}` +
        ` (ціль ${uahRound(limit)} ±10%)`,
  )

  const overNote = $derived(
    overBudget > 0 && bandHigh !== null
      ? `кошик уже вище верхньої межі ${uahRound(bandHigh)} на ${uahRound(overBudget)}`
      : '',
  )

  const gathers = $derived(mode === 'week')
  const weekNote = $derived(
    [
      basket.cyclesNote,
      shortNote === ''
        ? overNote
        : basket.fillNote
          ? `${shortNote} — решта пулу: ${basket.fillNote}`
          : gathers
            ? `${shortNote} — більше з твоїх покупок не назбирується`
            : shortNote,
    ]
      .filter(Boolean)
      .join(' · '),
  )

  const bandNote = $derived(
    limit === null
      ? ''
      : shortNote !== ''
        ? shortNote
        : overNote !== ''
          ? overNote
          : `кошик уже в межах цілі ${uahRound(limit)} ±10%`,
  )

  const gapWhy = $derived(
    headroom === null || headroom <= 0 ? '' : firstClause(basket.cyclesNote ?? ''),
  )

  const askAt = $derived(weekNote.indexOf(ASK_PHRASE))
  let extraField = $state<HTMLInputElement | null>(null)

  const slot = $derived(slotLabel(basket.slot))
  const modeLabel = $derived(BUILD_MODES.find((m) => m.id === mode)?.label ?? mode)

  const option = $derived(deliveryOptions.find((o) => o.id === delivery) ?? null)
  const termsUnknown = $derived(deliveryLoaded === null || !deliveryLoaded.ok)
  const missing = $derived(
    option?.minOrder ? round(option.minOrder - total) : 0,
  )
  const belowMin = $derived(missing > 0 && buying.length > 0)

  const overWeight = $derived(option?.maxWeightKg ? round(weight - option.maxWeightKg) : 0)

  const awaiting = $derived(buying.filter(asksWord))
  const approved = $derived(buying.filter((l) => l.mandate !== null))
  const byFork = $derived(heldByFork(approved))

  const collector = $derived(collectorActs(basket.feedback))

  const topUp = $derived(basket.topUp)
  const deliveryAfter = $derived(topUp ? basket.deliveryCost - topUp.saving : 0)
  const gap = $derived(topUp ? round(topUp.threshold - total) : 0)
  const net = $derived(topUp ? round(topUp.saving - gap) : 0)
  const inCart = $derived(new Set(lines.map((l) => l.externalProductId)))
  const suggestion = $derived(topUp?.items.filter((i) => !inCart.has(i.externalProductId)) ?? [])


  const WHAT_WIDTH = 38

  function shortList(names: string[]): string {
    const shown: string[] = []
    let width = 0
    for (const name of names) {
      if (shown.length > 0 && width + name.length > WHAT_WIDTH) break
      shown.push(name)
      width += name.length + 3
    }
    const rest = names.length - shown.length
    return shown.join(' · ') + (rest > 0 ? ` і ще ${rest}` : '')
  }

  let extra = $state('')
  let asking = $state<string[]>([])

  let dictOpen = $state(false)
  let voiceNote = $state<string | null>(null)
  let spoken: string[] = []

  function flushSpoken(): void {
    dictOpen = false
    if (spoken.length === 0) return
    const heard = spoken.join(', ')
    spoken = []
    extra = extra.trim() === '' ? heard : `${extra.trim()}, ${heard}`
  }

  function round(value: number): number {
    return Math.round(value * 100) / 100
  }

  let staleAccepted = $state(false)
  $effect(() => {
    if (!stale) staleAccepted = false
  })
  const checkoutBlockedBy = $derived(
    buying.length === 0
      ? 'у кошику порожньо'
      : belowMin
        ? 'сума менша за мінімум способу'
        : stale && !staleAccepted
          ? 'кошик зібрано за іншими налаштуваннями — перезбери або оформи як є'
          : null,
  )
  const canCheckout = $derived(checkoutBlockedBy === null && !checkingOut)

  function pickTopUp(): CartLine[] {
    const chosen: CartLine[] = []
    let need = gap
    for (const item of suggestion) {
      if (need <= 0) break
      chosen.push(item)
      need -= item.qty * item.price
    }
    return chosen
  }
</script>

<div class="cart">
  <Rules
    strip
    {rules}
    note={rulesNote}
    {deliveryOptions}
    {deliveryLoaded}
    {onDeliveryRetry}
    {delivery}
    {budget}
    {spend}
    {pantrySource}
    {draft}
    {modeLabel}
    {stale}
    {staleLabel}
    {onToggleRule}
    {onRemoveRule}
    {onDraft}
    {onAddRule}
    {onBudget}
    {onSave}
    {onDelivery}
    {onStale}
  />

  {#each basket.questions as question (question.intent)}
    <Clarify
      {question}
      {onAnswer}
      busy={refilling || question.intent in answering}
      chosen={answering[question.intent] ?? null}
      reasked={reasked.includes(question.intent)}
      onPick={(pick) => onPick(question.intent, pick)}
    />
  {/each}

  {#if missedCount > 0}
    <details class="missed-all" class:bare={missedGroups === 1} open={missedGroups === 1}>
      <summary>
        <strong>Не поїхало в кошик: {missedCount}</strong>
        <span class="missed-why">чому саме</span>
      </summary>

  {#if basket.unresolved.length > 0}
    <div class="missed glass">
      <p>
        <strong>Не знайшлось:</strong>
        {basket.unresolved.join(', ')} — скажи конкретніше і перезбери
      </p>
    </div>
  {/if}

  {#if basket.declined.length > 0}
    <div class="missed glass declined">
      <p><strong>Агент не взяв:</strong></p>
      <ul>
        {#each basket.declined as item}
          <li>{item.intent} — {item.why}</li>
        {/each}
      </ul>
      <p class="hint">
        Товар на полиці був — не підійшов під твоє правило або під сам вид. Зніми
        правило, назви іншу фасовку і перезбери.
      </p>
    </div>
  {/if}

  {#if basket.notCollected.length > 0}
    <div class="missed glass slot-empty">
      <p>
        <strong>На цей слот немає:</strong>
        {basket.notCollected.join(', ')} — спробуй інший слот, асортимент залежить від вікна
      </p>
    </div>
  {/if}

  {#if held.length > 0}
    <div class="missed glass trimmed" data-tour="postponed">
      <p><strong>Відкладено на наступний раз:</strong></p>
      <ul class="held">
        {#each grouped as [reason, intents] (reason)}
          {#if intents.length === 1}
            <li>{intents[0]} — {reason}</li>
          {:else}
            <li class="held-group">
              {reason} — {intents.length}
              <ul>
                {#each intents as intent}
                  <li>{intent}</li>
                {/each}
              </ul>
            </li>
          {/if}
        {/each}
      </ul>
    </div>
  {/if}

  {#if basket.trimmed.length > 0}
    <div class="missed glass trimmed" data-tour="trimmed">
      <p>
        <strong>Не влізло{limit === null ? '' : ` в ${uahRound(limit)}`}:</strong>
      </p>
      <ul>
        {#each basket.trimmed as item}
          <li>
            {item.name ?? item.intent}{item.price === null ? '' : ` · ${uah(item.price)}`} —
            {item.reason}
          </li>
        {/each}
      </ul>
    </div>
  {/if}

  {#if basket.fillCut.length > 0}
    <div class="missed glass trimmed" data-tour="fill-cut">
      <p><strong>Докинув під ціль і зняв сам:</strong></p>
      <p class="why">
        Це моя робота в обидва боки, а не твій тиждень: додав за оцінкою з чеків,
        на справжніх числах прибрав
      </p>
      <ul>
        {#each basket.fillCut as item}
          <li>
            {item.name ?? item.intent}{item.price === null ? '' : ` · ${uah(item.price)}`} —
            {item.reason}
          </li>
        {/each}
      </ul>
    </div>
  {/if}

    </details>
  {/if}

  {#if overBudget > 0}
    <div class="missed glass">
      <p><strong>Вище верхньої межі на {uah(overBudget)}</strong></p>
      <p class="why">
        {uah(total)} проти {uahRound(bandHigh ?? 0)} — це ціль {uahRound(limit ?? 0)} ±10%.
        Назване тобою агент не знімає: підійми ціль або прибери рядок сам
      </p>
    </div>
  {/if}

  {#if lines.length === 0}
    <div class="empty">
      <div class="mark" aria-hidden="true">∅</div>
      <h2>Збірка не дала жодного рядка</h2>
      <p>
        Ціль зараз {uahRound(budget)} — саме вона вирішує розмір кошика. Постав іншу
        вгорі і спробуй ще раз.
      </p>
      <div class="empty-actions">
        <button class="primary" type="button" onclick={onRestore}>Зібрати ще раз</button>
      </div>
    </div>
  {:else}
    <ul class="list" data-tour="lines">
      {#each lines as line (line.externalProductId)}
        <CartLineRow
          {line}
          kin={kinOf.get(headOf(line.name)) ?? 0}
          once={once.has(line.externalProductId)}
          onToggleOnce={() => onToggleOnce(line.externalProductId)}
          onQty={(next) => onQty(line.externalProductId, next)}
          onWhy={hasPick(line) ? () => onWhy(line.externalProductId) : null}
          onAction={() =>
            line.reason === 'at_home'
              ? onAdd(line.externalProductId)
              : onRemove(line.externalProductId)}
          onCheaper={line.cheaper
            ? () => onCheaper(line.externalProductId, line.cheaper!.externalProductId)
            : null}
        />
      {/each}
    </ul>

    {#if topUp && buying.length > 0}
      <div class="eco glass">
        {#if gap <= 0}
          <p>
            <strong>Поріг {uahRound(topUp.threshold)} пройдено</strong> — доставка
            {uahRound(deliveryAfter)} замість {uahRound(basket.deliveryCost)}. Плюс
            {uahRound(topUp.saving)}
          </p>
        {:else if net > 0 && suggestion.length > 0}
          <p>
            <strong>Докинути {uah(gap)}</strong> — доставка з {uahRound(basket.deliveryCost)}
            стане {uahRound(deliveryAfter)}. Чистий плюс {uah(net)}
          </p>
          <button class="eco-act" type="button" onclick={() => onExtra(pickTopUp())}>
            Докинути до порога
          </button>
        {:else if net > 0}
          <p>
            До порога {uahRound(topUp.threshold)} не вистачає {uah(gap)}, і це вигідно
            (доставка дешевшає на {uahRound(topUp.saving)}) — але зі звичного мені нема
            чого запропонувати: усе вже в кошику
          </p>
        {:else}
          <p>
            До порога {uahRound(topUp.threshold)} не вистачає {uah(gap)} — докидати
            невигідно: різниця більша за економію {uahRound(topUp.saving)} на доставці
          </p>
        {/if}
      </div>
    {/if}

    {#if awaiting.length > 0}
      <button
        class="swaps decide"
        type="button"
        data-tour="swaps"
        onclick={() => onSwaps('urgent')}
      >
        <span class="swaps-text">
          <span class="swaps-title">Чекає твого рішення</span>
          <span class="swaps-note">
            {plural(awaiting.length, {
              one: 'позиція просить',
              few: 'позиції просять',
              many: 'позицій просять',
            })}
            твого слова: малий залишок на полиці або заміна, якої ще не погоджено
          </span>
        </span>
        <span class="swaps-go" aria-hidden="true">›</span>
      </button>
    {/if}

    {#if approved.length > 0}
      {@const count = plural(approved.length, {
        one: 'позиція',
        few: 'позиції',
        many: 'позицій',
      })}
      {@const hands =
        byFork.length === 0
          ? count
          : byFork.length === approved.length
            ? `${count} — межа в грошах, товар не названий`
            : `${count}, з них ${byFork.length} — межа в грошах`}
      <button
        class="swaps"
        class:decide={collector === false}
        type="button"
        data-testid="swaps-approved"
        onclick={() => onSwaps('all')}
      >
        <span class="swaps-text">
          <span class="swaps-title">
            {#if collector === false}
              Заміни спрацюють до слота
            {:else if byFork.length > 0}
              Заміни сплановано наперед
            {:else}
              Заміни погоджено наперед
            {/if}
          </span>
          <span class="swaps-note">
            {#if collector === false}
              {hands} · біля полиці збирач міняти не буде: так стоїть у налаштуваннях
              замовлення
            {:else if collector === null}
              {hands} · чи прочитає мандат збирач -- не звіряв
            {:else}
              {hands} · збирач не дзвонитиме
            {/if}
          </span>
        </span>
        <span class="swaps-go" aria-hidden="true">›</span>
      </button>
    {/if}

    <div class="week glass" data-tour="refill">
      {#if refillable.length > 0}
        <button
          class="week-act"
          type="button"
          disabled={refilling}
          onclick={() => onRefill([])}
        >
          {refilling
            ? 'Добираю…'
            : `Закрити решту тижня — ще ${plural(refillable.length, {
                one: 'позиція',
                few: 'позиції',
                many: 'позицій',
              })}`}
        </button>
        <p class="week-note">
          {refillCost > 0 ? `~${uahRound(refillCost)}` : 'ціну підкаже полиця'}{unpriced > 0
            ? ` (без ${plural(unpriced, {
                one: 'виду',
                few: 'видів',
                many: 'видів',
              })} — ціни в чеках немає)`
            : ''}{bandNote === '' ? '' : ` · ${bandNote}`}
        </p>
        <p class="week-what">{shortList(refillable.map((item) => item.intent))}</p>
      {:else if weekNote}
        <p class="week-note">
          {#if askAt >= 0}
            {weekNote.slice(0, askAt)}<button
              class="week-ask"
              type="button"
              onclick={() => extraField?.focus()}>{ASK_PHRASE}</button
            >{weekNote.slice(askAt + ASK_PHRASE.length)}
          {:else}
            {weekNote}
          {/if}
        </p>
      {/if}

      <form
        class="week-add"
        onsubmit={(event) => {
          event.preventDefault()
          const asked = extra.trim()
          if (!asked || refilling) return
          extra = ''
          asking = parseList(asked)
          onRefill(asking)
        }}
      >
        <div class="field">
          <span class="voice-wrap">
            <input
              type="text"
              placeholder="Додати ще: сметана, хліб"
              bind:this={extraField}
              bind:value={extra}
              disabled={refilling}
            />
            {#if voiceAvailable()}
              <span class="mic-slot"><MicButton
                active={dictOpen}
                label="надиктувати, що додати"
                onClick={() => {
                  voiceNote = null
                  dictOpen = true
                }}
              /></span>
            {/if}
          </span>
        </div>
        <button class="secondary" type="submit" disabled={refilling || extra.trim() === ''}>
          {refilling ? 'Шукаю…' : 'Додати'}
        </button>
      </form>
      {#if refilling && asking.length > 0}
        <p class="week-asking" role="status">шукаю: {asking.join(', ')}</p>
      {/if}
      {#if voiceNote}
        <p class="voice-error" role="alert">{voiceNote}</p>
      {/if}
      <p class="week-note">додам окремо — кошик не перезбираю, вибір і заміни лишаються</p>
    </div>

    {#if true}
      <button
        class="place"
        class:warn={place === null || place.source !== 'address'}
        type="button"
        onclick={onPlace}
      >
        <span class="place-pin" aria-hidden="true">📍</span>
        <span class="place-body">
          <span class="place-label">{place?.address ?? 'Адресу ще не знаю'}</span>
          <span class="place-note">
            {place === null
              ? 'торкнись, щоб назвати — від адреси залежать ціни й наявність'
              : place.branch
                ? `збирає ${place.branch}`
                : place.note}
          </span>
        </span>
        <span class="place-change">змінити</span>
      </button>
    {/if}

    <div class="summary glass">
      <div class="summary-head">
        <div class="facts">
          {plural(buying.length, { one: 'позиція', few: 'позиції', many: 'позицій' })}{weight > 0
            ? ` · ${unweighed > 0 ? 'від ' : ''}${kg(weight)}`
            : ''}{slot ? ` · ${slot}` : ''}
        </div>
        <button class="clear" class:armed={confirmClear} type="button" onclick={onClearAll}>
          {confirmClear ? 'Точно, усе вдома?' : 'Усе вже вдома'}
        </button>
      </div>

      {#if basket.slot?.note}
        <p class="slot-why" data-testid="slot-why">чому цей слот: {basket.slot.note}</p>
      {/if}

      {#if basket.planNote}
        <p class="plan-note" role="status" data-testid="plan-note">
          зібрано аварійним планом: {basket.planNote} — без вибору агента,
          ланцюжків замін і питань
        </p>
      {/if}

      {#if basket.agentTarget}
        <p class="plan-note" role="status" data-testid="agent-target">
          {#if basket.agentTarget.refused !== null}
            агент пропонував межу {uahRound(Number(basket.agentTarget.proposed))}, але
            {basket.agentTarget.refused}
          {:else}
            межа {uahRound(Number(basket.agentTarget.named))} →
            {uahRound(Number(basket.agentTarget.target))}: {basket.agentTarget.why} —
            рішення агента під привід
            <button
              class="watch"
              type="button"
              onclick={() => onKeepBudget(Number(basket.agentTarget?.named ?? 0))}
            >
              лишити {uahRound(Number(basket.agentTarget.named))}
            </button>
          {/if}
        </p>
      {/if}

      {#if basket.shelfNote}
        <p class="plan-note" role="status" data-testid="shelf-note">
          {basket.shelfNote}
        </p>
      {/if}

      {#if basket.twinsDropped.length}
        <p class="plan-note" role="status" data-testid="twins-dropped">
          {#each basket.twinsDropped as twin (twin.name)}
            <span>«{twin.name}» звів з «{twin.keptName}»: {twin.why}</span>
          {/each}
        </p>
      {/if}

      {#if ignoredNote && ignoredNote !== ignoredSeen}
        <p class="text-ignored" role="status" data-testid="text-ignored">
          <span>з набраного не взяв: {ignoredNote} — це не схоже на товар</span>
          <button
            type="button"
            class="dismiss"
            aria-label="Сховати"
            onclick={() => (ignoredSeen = ignoredNote)}>✕</button
          >
        </p>
      {/if}

      {#if paid}
        <p class="estimate">суму порахувало «Сільпо» — вона у звіті нижче і в плашці</p>
      {:else}
        <div class="totals">
          <div class="sum num">{uahRound(total)}</div>
          {#if savings > 0.005}
            <div class="saved">
              <div class="was num">{uahRound(baseTotal)}</div>
              <div class="off num">знижки -{uahRound(savings)}</div>
            </div>
          {/if}
        </div>

        <p class="estimate">оцінка за цінами полиці — точну суму порахує «Сільпо» при записі</p>
      {/if}

      {#if unweighed > 0}
        <p class="estimate">
          {plural(unweighed, { one: 'позиція', few: 'позиції', many: 'позицій' })} без фасовки —
          ваги в картці немає, тож у вагу кошика вони не входять
        </p>
      {/if}

      <button class="secondary wide" type="button" onclick={onTrace}>Що зробив агент</button>
    </div>

    {#if checkout}
      <div class="handed glass" class:blocked={checkout.blockers.length > 0}>
        <p class="handed-sum">{checkout.summary}</p>
        {#if checkout.blockers.length > 0}
          <ul class="handed-list stop">
            {#each blockerReasons as reason (reason.code)}
              <li>
                {reason.text}{reason.action ? ` — ${reason.action}` : ''}
                </li>
            {/each}
          </ul>
        {/if}
        {#if checkout.stockCut.length > 0}
          <p class="handed-note calm">Кількість урізано під полицю:</p>
          <ul class="handed-list">
            {#each checkout.stockCut as note}
              <li>{note}</li>
            {/each}
          </ul>
        {/if}
        {#if checkout.warnings.length > 0}
          <p class="handed-note calm">«Сільпо» попереджає:</p>
          <ul class="handed-list">
            {#each checkout.warnings as note}
              <li>{note}</li>
            {/each}
          </ul>
        {/if}
        {#if checkout.totals}
          <dl class="paid">
            <div><dt>товари</dt><dd class="num">{uahRound(checkout.totals.products)}</dd></div>
            {#if checkout.totals.discount > 0.005}
              <div>
                <dt>знижка</dt>
                <dd class="num off">-{uahRound(checkout.totals.discount)}</dd>
              </div>
            {/if}
            <div><dt>доставка</dt><dd class="num">{uahRound(checkout.totals.delivery)}</dd></div>
            {#if checkout.totals.serviceFee !== null && checkout.totals.serviceFee > 0.005}
              <div>
                <dt>сервісний збір</dt>
                <dd class="num">{uahRound(checkout.totals.serviceFee)}</dd>
              </div>
            {/if}
            <div class="pay">
              <dt>до оплати</dt>
              <dd class="num">{uahRound(checkout.totals.toPay)}</dd>
            </div>
          </dl>
          {#if checkout.totals.estimate !== null}
            <p class="gap">
              моя оцінка була {uahRound(checkout.totals.estimate)} — «Сільпо» порахувало
              {checkout.totals.toPay < checkout.totals.estimate ? 'менше' : 'більше'}
              на {uahRound(Math.abs(checkout.totals.estimate - checkout.totals.toPay))}
            </p>
          {/if}
        {/if}
        {#if checkout.bonusAvailable !== null && checkout.bonusAvailable > 0}
          <p class="gap">
            у тебе {amount(checkout.bonusAvailable, '')} балабонусів на цей кошик —
            застосувати їх можна в «Сільпо» при оплаті
          </p>
        {/if}
        {#if checkout.carryOver}
          <p class="handed-note" class:calm={checkout.carryOver.state === 'removed'}>
            {checkout.carryOver.state === 'removed'
              ? 'Знято з кошика:'
              : 'Лишилось у кошику поза цим планом:'}
          </p>
          <ul class="handed-list">
            {#each checkout.carryOver.lines as row}
              <li><strong>{row.name}</strong> ×{row.qty} — {uahRound(row.total)}</li>
            {/each}
          </ul>
        {/if}
        {#if checkout.mandateLost.length > 0}
          <p class="handed-note">
            Коментар збирачу не зберігся на {checkout.mandateLost.length} поз. — перевір у застосунку «Сільпо»:
          </p>
          <ul class="handed-list">
            {#each checkout.mandateLost as label}
              <li><strong>{label}</strong></li>
            {/each}
          </ul>
        {/if}
        {#if checkout.unmandated.length > 0}
          <p class="handed-note">
            Без мандата поїхало {checkout.unmandated.length} поз. — заміну не погоджено, збирач вирішить сам:
          </p>
          <ul class="handed-list">
            {#each checkout.unmandated as label}
              <li><strong>{label}</strong></li>
            {/each}
          </ul>
        {/if}
        {#if checkout.wantedBurned.length > 0}
          <p class="handed-note calm">Зі списку на покупку згоріло — поїхало в кошик:</p>
          <ul class="handed-list">
            {#each checkout.wantedBurned as label}
              <li>
                <strong>{label}</strong>
                {checkout.wantedStocked.includes(label) ? '— у комору' : '— разова покупка'}
              </li>
            {/each}
          </ul>
        {/if}
        {#if checkout.promoGone.length > 0}
          <p class="handed-note">Акція зникла, поки писали — тепер за повну ціну:</p>
          <ul class="handed-list">
            {#each checkout.promoGone as name}
              <li><strong>{name}</strong> — прибери в кошику «Сільпо», якщо без акції не треба</li>
            {/each}
          </ul>
        {/if}
        {#if checkout.skipped.length > 0}
          <ul class="handed-list">
            {#each checkout.skipped as skip}
              <li><strong>{skip.name}</strong> — {skip.reason}</li>
            {/each}
          </ul>
        {/if}
      </div>
    {/if}

    <div class="dock glass" data-tour="checkout">
      {#if termsUnknown}
        <p class="blocker">
          Умов доставки я не прочитав — ні порогу, ні межі ваги тут не перевірю
          <button class="again" type="button" onclick={onDeliveryRetry}>
            Прочитати ще раз
          </button>
        </p>
      {/if}
      {#if belowMin && option}
        <p class="blocker">
          {option.label} возить від {uahRound(option.minOrder ?? 0)} — не вистачає
          {uah(missing)}
        </p>
      {/if}

      {#if overWeight > 0 && option?.maxWeightKg}
        <p class="blocker">
          {option.label} бере до {kg(option.maxWeightKg)}, а тут {unweighed > 0
            ? 'уже '
            : ''}{kg(weight)} — зніми щось або бери два вікна
        </p>
      {/if}

      {#if paid && touched}
        <p class="blocker">
          склад правлений після запису — у кошику «Сільпо» лишилось те, що у звіті вище
        </p>
      {/if}

      <div class="dock-sum">
        <span class="num">
          {uahRound(paid ? paid.toPay : total)}{#if !paid && limit !== null}<span class="of"
            >&nbsp;з {uahRound(limit)}{#if bandHigh !== null && total > limit && total <= bandHigh}
                · у коридорі до {uahRound(bandHigh)}{/if}</span
          >{/if}
        </span>
        <span class="dock-note">
          {paid ? 'до оплати' : 'оцінка'} · {plural(buying.length, {
            one: 'позиція',
            few: 'позиції',
            many: 'позицій',
          })}{slot ? ` · ${slot}` : ''}
        </span>
        {#if !paid && gapWhy}
          <span class="dock-why">{gapWhy}</span>
        {:else if paid && skippedNote}
          <span class="dock-why">{skippedNote}</span>
        {/if}
      </div>

      {#if checkout?.checkoutWebLink}
        <a class="primary" href={checkout.checkoutWebLink} target="_blank" rel="noopener">
          Підтвердити в «Сільпо»
        </a>
      {:else if checkout && (checkout.written > 0 || checkout.blockers.length > 0)}
        <div class="checkout done" role="status">
          <p class="done-lead">
            {#if checkout.written > 0}
              Записав {plural(checkout.written, {
                one: 'позицію',
                few: 'позиції',
                many: 'позицій',
              })} у кошик «Сільпо»{checkout.totals ? ` на ${uahRound(checkout.totals.toPay)}` : ''}
              — вони там лишились. Оформити зараз не можна:
            {:else}
              У кошик нічого не поїхало, і ось чому:
            {/if}
          </p>
          {#each blockerReasons as reason (reason.code)}
            <p class="why-blocked">
              {reason.text}{reason.action ? ` — ${reason.action}` : ''}
            </p>
          {/each}
          {#if checkout.retryHelps}
            <button class="watch" type="button" onclick={onRebuild}>
              Перезібрати під те, що є зараз
            </button>
          {:else if checkout.written > 0}
            <p class="why-blocked">
              перезбірка цього не виправить — те, що записано, лишилось у твоєму кошику
              «Сільпо», і причину можна зняти там
            </p>
          {/if}
          {#if checkout.cartWebLink}
            <a
              class="watch"
              href={checkout.cartWebLink}
              target="_blank"
              rel="noopener"
              data-testid="cart-link"
            >
              Відкрити кошик у «Сільпо»
            </a>
          {/if}
        </div>
      {:else}
        <div class="checkout">
          <button
            class="primary"
            type="button"
            disabled={!canCheckout}
            title={checkoutBlockedBy ?? undefined}
            onclick={onCheckout}
          >
            {checkingOut ? 'Записую в кошик…' : 'Оформити'}
          </button>
          <button
            class="share"
            type="button"
            title="текст із назвами, кількостями і картками silpo.ua"
            onclick={() => void share()}
          >
            {shared || 'Поділитись'}
          </button>
          {#if checkoutBlockedBy}
            <p class="why-blocked" role="status">{checkoutBlockedBy}</p>
            {#if stale && !staleAccepted}
              <button class="secondary" type="button" onclick={() => (staleAccepted = true)}>
                Оформити як є
              </button>
            {/if}
          {/if}
        </div>
      {/if}
    </div>
  {/if}
</div>

<Dictaphone
  open={dictOpen}
  onPhrase={(text) => spoken.push(text)}
  refine={splitSpoken}
  onClose={flushSpoken}
  onError={(message) => (voiceNote = message)}
/>

{#if carryOver}
  <Modal label="У кошику вже щось лежить">
    <p class="carry-lead">
      У кошику «Сільпо» вже лежить {plural(carryOver.lines.length, {
        one: 'позиція',
        few: 'позиції',
        many: 'позицій',
      })} на {uahRound(carryOver.total)}, яких немає в цьому плані. Хто їх поклав — я не знаю:
      це може бути минула збірка або ти сам у «Сільпо».
    </p>
    <ul class="carry-list">
      {#each carryOver.lines as row}
        <li><strong>{row.name}</strong> ×{row.qty} — {uahRound(row.total)}</li>
      {/each}
    </ul>
    <div class="carry-acts">
      <button
        class="secondary"
        type="button"
        disabled={checkingOut}
        onclick={() => onCarryOver('kept')}
      >
        Доповнити
      </button>
      <button
        class="secondary"
        type="button"
        disabled={checkingOut}
        onclick={() => onCarryOver('removed')}
      >
        Почати заново
      </button>
    </div>
  </Modal>
{/if}

<style>
  .watch {
    width: 100%;
    min-height: 44px;
    margin-top: 8px;
    border-radius: 12px;
    font-size: 13px;
    font-weight: 700;
    color: var(--ink);
    border: 1px solid var(--hair-strong);
    background: var(--chip-bg);
  }

  .checkout {
    display: flex;
    flex: 1 1 auto;
    flex-direction: column;
    align-items: stretch;
    gap: 6px;
    min-width: 0;
  }

  .done-lead {
    font-size: 12px;
    line-height: 1.4;
    text-align: center;
    text-wrap: balance;
  }

  .handed-list.stop {
    color: var(--warn);
  }

  .why-blocked {
    font-size: 11.5px;
    line-height: 1.35;
    color: var(--warn);
    text-align: center;
    text-wrap: balance;
  }


  .cart {
    padding: 0 0 16px;
  }

  .dock {
    position: sticky;
    bottom: 0;
    z-index: 15;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
    margin-top: 14px;
    padding: 12px 16px calc(12px + env(safe-area-inset-bottom, 0px));
    border-top: 1px solid var(--hair);
  }

  .dock-sum {
    flex: 1 1 auto;
    min-width: min-content;
  }

  .handed {
    margin-top: 12px;
    padding: 14px 16px;
    border-left: 3px solid var(--good);
  }

  .handed.blocked {
    border-left-color: var(--warn);
  }

  .estimate {
    margin-top: 6px;
    font-size: 11px;
    line-height: 1.35;
    color: var(--faint);
  }

  .paid {
    margin-top: 8px;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }

  .paid div {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    font-size: 12px;
  }

  .paid dt {
    color: var(--muted);
  }

  .paid dd {
    margin: 0;
  }

  .paid .off {
    color: var(--good);
  }

  .paid .pay {
    margin-top: 3px;
    padding-top: 5px;
    border-top: 1px solid var(--hair);
    font-size: 13.5px;
    font-weight: 800;
  }

  .gap {
    margin-top: 6px;
    font-size: 11px;
    line-height: 1.35;
    color: var(--faint);
  }

  .handed-sum {
    margin: 0;
    font-size: 13px;
    font-weight: 700;
    line-height: 1.45;
  }

  .handed-list {
    margin: 8px 0 0;
    padding-left: 18px;
    font-size: 12px;
    line-height: 1.5;
    color: var(--muted);
  }

  .handed-note {
    margin: 8px 0 0;
    font-size: 12px;
    line-height: 1.45;
    color: var(--warn);
  }

  .handed-note.calm {
    color: var(--muted);
  }

  .carry-lead {
    margin: 0;
    font-size: 13px;
    line-height: 1.5;
  }

  .carry-list {
    margin: 10px 0 0;
    padding-left: 18px;
    max-height: 40vh;
    overflow-y: auto;
    font-size: 12px;
    line-height: 1.6;
    color: var(--muted);
  }

  .carry-acts {
    display: flex;
    gap: 8px;
    margin-top: 14px;
  }

  .carry-acts button {
    flex: 1;
  }

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

  .blocker {
    flex-basis: 100%;
    font-size: 12px;
    font-weight: 700;
    line-height: 1.35;
    color: var(--warn);
  }

  .dock-sum .num {
    display: block;
    font-size: 20px;
    font-weight: 800;
    letter-spacing: -0.5px;
  }

  .of {
    font-size: 15px;
    font-weight: 700;
    color: var(--muted);
  }

  .dock-note {
    display: block;
    font-size: 11.5px;
    color: var(--muted);
    margin-top: 1px;
  }

  .dock-why {
    display: block;
    margin-top: 2px;
    font-size: 11px;
    line-height: 1.35;
    color: var(--muted);
  }


  .list {
    margin: 14px 16px 0;
    border-radius: 18px;
    border: 1px solid var(--hair);
    background: var(--list-bg);
  }

  .list :global(li:last-child) {
    border-bottom: none;
  }

  .empty {
    padding: 44px 24px 20px;
    text-align: center;
  }

  .mark {
    width: 60px;
    height: 60px;
    border-radius: 20px;
    margin: 0 auto;
    display: grid;
    place-items: center;
    font-size: 26px;
    color: var(--faint);
    border: 1px solid var(--hair-strong);
    background: var(--chip-bg);
  }

  .empty h2 {
    font-size: 21px;
    font-weight: 800;
    letter-spacing: -0.6px;
    margin-top: 18px;
  }

  .empty p {
    font-size: 14px;
    color: var(--muted);
    margin: 10px auto 0;
    line-height: 1.55;
    max-width: 300px;
  }

  .empty-actions {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-top: 20px;
  }

  .eco {
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 14px 16px 0;
    padding: 13px 14px;
    border-radius: 16px;
    border: 1px solid var(--eco-edge);
    background: var(--eco-bg);
  }

  .week {
    display: grid;
    gap: 8px;
    margin: 14px 16px 0;
    padding: 13px 14px;
    border-radius: 16px;
    border: 1px solid var(--hair-strong);
  }

  .week-act {
    width: 100%;
    padding: 11px 14px;
    border-radius: 12px;
    border: 1px solid var(--acc-edge);
    background: var(--acc-soft);
    color: var(--ink);
    font-size: 14px;
    font-weight: 700;
  }

  .week-act:disabled {
    opacity: 0.55;
  }

  .week-ask {
    font: inherit;
    color: var(--badge);
    text-decoration: underline;
    text-underline-offset: 2px;
  }

  .week-note,
  .week-what {
    margin: 0;
    font-size: 13px;
    line-height: 1.45;
    color: var(--muted);
  }

  .week-what {
    color: var(--faint);
  }

  .week-asking {
    margin: 6px 0 0;
    font-size: 12px;
    line-height: 1.4;
    color: var(--muted);
  }

  .week-add {
    display: flex;
    gap: 8px;
  }

  .week-add .field {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: stretch;
    gap: 8px;
  }

  .week-add input {
    flex: 1;
    min-width: 0;
    padding: 10px 12px;
    border-radius: 12px;
    border: 1px solid var(--hair);
    background: var(--chip-bg);
    color: var(--ink);
    font: inherit;
    font-size: 14px;
  }

  .week-add > button {
    flex: none;
  }

  .voice-error {
    margin: 8px 0 0;
    font-size: 11.5px;
    line-height: 1.4;
    color: var(--warn);
  }

  .missed-all > summary {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px;
    margin: 14px 16px 0;
    padding: 10px 14px;
    border-radius: 16px;
    border: 1px solid var(--hair-strong);
    cursor: pointer;
    list-style: none;
  }

  .missed-all > summary::-webkit-details-marker {
    display: none;
  }

  .missed-why {
    color: var(--muted);
    font-size: 0.82em;
    white-space: nowrap;
  }

  .missed-all[open] .missed-why {
    visibility: hidden;
  }

  .missed-all.bare > summary {
    display: none;
  }

  .missed {
    margin: 14px 16px 0;
    padding: 12px 14px;
    border-radius: 16px;
    border: 1px solid rgb(232 147 90 / 0.55);
  }

  .trimmed {
    border-color: var(--hair-strong);
  }

  .trimmed p,
  .trimmed li {
    color: var(--muted);
  }

  .trimmed ul {
    margin: 4px 0 0;
    padding-left: 18px;
    font-size: 13px;
    line-height: 1.45;
  }

  .held,
  .held ul {
    list-style: disc;
  }

  .held-group {
    list-style: none;
    margin-left: -18px;
  }

  .held-group ul {
    margin-top: 2px;
  }

  .held-group + li,
  li + .held-group {
    margin-top: 6px;
  }

  .missed p {
    margin: 0;
    font-size: 13px;
    line-height: 1.45;
    color: var(--warn);
  }

  .missed .why {
    margin-top: 5px;
    color: var(--muted);
  }

  .declined ul {
    margin: 4px 0 0;
    padding-left: 18px;
    font-size: 13px;
    line-height: 1.45;
    color: var(--warn);
  }

  .declined .hint {
    margin-top: 6px;
    color: var(--muted);
  }

  .eco p {
    flex: 1;
    font-size: 13.5px;
    line-height: 1.4;
    color: var(--eco-ink);
  }

  .eco-act {
    flex: none;
    padding: 9px 13px;
    border-radius: 11px;
    font-size: 13px;
    font-weight: 700;
    color: var(--eco-ink);
    border: 1px solid rgb(106 168 79 / 0.5);
    background: var(--chip-bg);
  }

  .swaps {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-block: 14px 0;
    padding: 12px 14px;
    text-align: left;
    color: var(--ink);
    border: 1px solid var(--hair);
    border-radius: 14px;
    background: var(--row-risk);
  }

  .swaps-text {
    flex: 1;
    min-width: 0;
  }

  .swaps-title {
    display: block;
    font-size: 13.5px;
    font-weight: 700;
    color: var(--risk-ink);
  }

  .swaps-note {
    display: block;
    font-size: 11.5px;
    color: var(--warn);
    margin-top: 2px;
    line-height: 1.3;
  }

  .swaps-go {
    flex: none;
    font-size: 20px;
    line-height: 1;
    color: var(--warn);
  }

  .swaps.decide {
    border-color: var(--warn);
    background: linear-gradient(var(--mark-warn), var(--mark-warn)), var(--row-risk);
  }

  .swaps.decide .swaps-title {
    color: var(--warn);
  }

  .place,
  .swaps {
    box-sizing: border-box;
    width: calc(100% - 32px);
    margin-inline: 16px;
  }

  .place {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-block: 14px 10px;
    padding: 9px 12px;
    text-align: left;
    border-radius: 14px;
    border: 1px solid var(--hair);
    background: var(--list-bg);
  }

  .place-change {
    flex: none;
    font-size: 12px;
    font-weight: 700;
    color: var(--accent);
  }

  .place.warn {
    border-color: var(--warn);
  }

  .place-pin {
    width: 26px;
    height: 26px;
    flex: none;
    display: grid;
    place-items: center;
    border-radius: 9px;
    font-size: 13px;
    background: var(--thumb-bg);
    border: 1px solid var(--hair);
  }

  .place-body {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-width: 0;
  }

  .place-label {
    font-size: 12.5px;
    font-weight: 700;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .place-note {
    margin-top: 1px;
    font-size: 11px;
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .summary {
    margin: 14px 16px 0;
    padding: 14px;
    border-radius: 16px;
    border: 1px solid var(--hair);
  }

  .summary-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }

  .facts {
    min-width: 0;
    font-size: 12.5px;
    line-height: 1.35;
    color: var(--muted);
  }

  .text-ignored {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    margin: 8px 0 0;
    padding: 8px 11px;
    border-radius: 10px;
    border-left: 3px solid var(--hair-strong);
    background: var(--row-dim);
    font-size: 12px;
    line-height: 1.4;
  }

  .text-ignored .dismiss {
    flex: none;
    margin-left: auto;
    width: 22px;
    height: 22px;
    padding: 0;
    border: 0;
    border-radius: 6px;
    background: transparent;
    color: var(--muted);
    font-size: 13px;
    line-height: 1;
    cursor: pointer;
  }

  .plan-note {
    margin: 8px 0 0;
    padding: 8px 11px;
    border-radius: 10px;
    border-left: 3px solid var(--warn);
    background: var(--row-risk);
    color: var(--risk-ink);
    font-size: 12px;
    line-height: 1.4;
  }

  .slot-why {
    margin-top: 6px;
    font-size: 11.5px;
    line-height: 1.4;
    color: var(--faint);
  }

  .clear {
    flex: none;
    padding: 8px 11px;
    min-height: 36px;
    border-radius: 10px;
    font-size: 12px;
    font-weight: 700;
    white-space: nowrap;
    color: var(--muted);
    border: 1px solid var(--hair-strong);
    background: transparent;
  }

  .clear.armed {
    color: var(--warn);
    border-color: rgb(232 147 90 / 0.55);
  }

  .totals {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-top: 6px;
  }

  .sum {
    font-size: 30px;
    font-weight: 800;
    letter-spacing: -1px;
  }

  .saved {
    text-align: right;
  }

  .was {
    font-size: 12.5px;
    color: var(--faint);
    text-decoration: line-through;
  }

  .off {
    font-size: 12px;
    font-weight: 700;
    color: var(--eco-ink);
    margin-top: 2px;
  }

  .wide {
    width: 100%;
    margin-top: 13px;
  }

  .secondary {
    flex: 1;
    padding: 13px;
    border-radius: 13px;
    font-size: 14px;
    font-weight: 700;
    color: var(--ink);
    border: 1px solid var(--hair-strong);
    background: var(--chip-bg);
  }

  .dock .primary {
    flex: 1 1 auto;
  }

  .primary {
    flex: none;
    padding: 13px 20px;
    border-radius: 13px;
    font-size: 14px;
    font-weight: 800;
    text-align: center;
    text-decoration: none;
    color: var(--pri-ink);
    background: var(--pri-bg);
  }

  .primary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  @media (width <= 380px) {
    .list,
    .eco,
    .summary {
      margin-inline: 12px;
    }

    .totals {
      flex-direction: column;
      align-items: flex-start;
      gap: 2px;
    }

    .saved {
      text-align: left;
    }

    .sum {
      font-size: 27px;
    }
  }
  .share {
    margin-top: 8px;
    width: 100%;
    background: none;
    border: 1px solid var(--muted);
    border-radius: 999px;
    padding: 9px 14px;
    color: var(--ink);
    font: inherit;
    cursor: pointer;
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
