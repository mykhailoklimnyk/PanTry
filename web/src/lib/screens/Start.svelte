<script lang="ts">
  import Dictaphone from '../Dictaphone.svelte'
  import MicButton from '../MicButton.svelte'
  import PantryWait from '../PantryWait.svelte'
  import Place from '../Place.svelte'
  import Rules from '../Rules.svelte'
  import { BUILD_MODES, DELIVERY_SKELETON, NO_PHOTO, pantryEmptyNote } from '../ui'
  import { kg, plural, uahRound } from '../format'
  import { parseList } from '../list'
  import { voiceAvailable } from '../speech'
  import type { Loaded } from '../data'
  import type {
    BuildRequest,
    CartState,
    DeliveryOption,
    Exclusion,
    Pantry,
    PantryItem,
    Place as Where,
    PlaceOption,
    Quota,
    SpendTarget,
    WantedRow,
  } from '../types'

  interface Props {
    mode: BuildRequest['mode']
    rules: Exclusion[]
    /** Що не вдалося з правилами — приміткою біля них, не банером. */
    rulesNote: string | null
    /**
     * Способи отримання. `null` — запит ще їде: у секції стоїть скелет БЕЗ
     * жодної умови (#164). Причина недоступності буває лише з відповіді:
     * написана наперед, вона переживає своє джерело і читається як факт про
     * продукт — рівно те, що сталось із «у хакатон-демо не передбачено».
     */
    deliveryLoaded: Loaded<DeliveryOption[]> | null
    delivery: string
    /** Прочитати умови ще раз: відмова без дії — глухий кут. */
    onDeliveryRetry: () => void
    /** Куди веземо і хто збирає. `null` — ще вантажиться. */
    place: Where | null
    /** Відмова читання адреси — приміткою в секції, не банером. */
    placeNote: string | null
    placeResults: PlaceOption[] | null
    placeSearching: boolean
    placeSearchNote: string | null
    onPlaceSearch: (text: string) => void
    onPlaceChoose: (option: PlaceOption) => void
    budget: number
    /** Ціль і пресети з ЙОГО замовлень (#212). `null` — історію не прочитали. */
    spend: SpendTarget | null
    draft: string
    /** Стан дому — акцент продукту. Кошик випливає з нього, тож він
     *  стоїть на старті вище за всі налаштування. */
    pantry: PantryItem[]
    /** false — комора ще вантажиться: стоїть скелет тих самих розмірів. */
    pantryLoaded: boolean
    /**
     * З чого комора порахувалась. `null` — ще не відповіла.
     *
     * Порожня комора без цього числа мовчить про причину, а причин три, і
     * дві з них не про поломку: покупок ще не було, покупок не видно, або
     * чеки є, але циклу з них ще не вийшло (#38).
     */
    pantrySource: Omit<Pantry, 'items'> | null
    /** Чому комора не прочиталась. `null` -- прочиталась (#166). */
    pantryFailed: string | null
    onPantryRetry: () => void
    /** Коли почався запит комори. Потрібно, щоб скелет не мовчав секунди. */
    pantryPending: number | null
    /** Сирий текст списку (вхід В). Розбирається тут лише для показу;
     *  для запиту його розбирає App — одна функція parseList на обох. */
    list: string
    /**
     * Список на наступну покупку (#110): те, що гість вирішив узяти
     * ОБОВ'ЯЗКОВО. Не комора: комора каже, коли вид закінчиться (прогноз з
     * циклів, який можна заперечити), а тут рішення, у якому нема в чому
     * помилятись, -- і саме тому його рядок після покупки ЗГОРАЄ.
     *
     * Живе поруч із полем списку, а не окремим екраном: гість згадує про
     * батарейки не тоді, коли сідає замовляти, і місце, по яке треба йти,
     * лишилось би порожнім.
     */
    wanted: WantedRow[]
    onWantedAdd: (label: string) => void
    onWantedDrop: (id: string) => void
    /** Перемкнути, чи ляже рядок у комору після покупки (#238). */
    onWantedHome: (row: WantedRow) => void
    /** Дія їде на сервер: список належить акаунту, а не вкладці (#45). */
    wantedBusy: boolean
    /** Скільки напоїв уже обрано до приводу. */
    barCount: number
    /** Скільки видів у барі. `null` -- ще не читали (#370).
     *
     * Нуля тут не малюємо здогадом: «0 видів» до відповіді сервера -- це та
     * сама неправда про дім, що й порожня комора замість непорахованої
     * (#76). Двері стоять одразу, число доїжджає, коли стає правдою (#341).
     */
    drinkKinds: number | null
    /** Скільки людей на привід — питається лише під «гості» і «вечірку». */
    people: number
    /** Стояче погодження заміни: рівноцінна заміна того самого виду в
     *  ціновій вилці навколо ціни позиції. */
    autoSwap: boolean
    barInWeek: boolean
    onBarInWeek: () => void
    onAutoSwap: () => void
    onPeople: (value: number) => void
    onMode: (id: BuildRequest['mode']) => void
    onDelivery: (id: string) => void
    onBar: () => void
    onPantry: () => void
    onList: (value: string) => void
    onToggleRule: (id: string) => void
    onRemoveRule: (id: string) => void
    onDraft: (value: string) => void
    onAddRule: () => void
    onBudget: (value: number) => void
    onSave: () => void
    /**
     * Що вже лежить у кошику акаунта. `null` — ще читаємо, `{ok:false}` —
     * не знаємо. Гасити кнопку можна ЛИШЕ на порожньому кошику: «не знаю»
     * і «порожньо» — різні відповіді, і перша не привід нічого забороняти.
     *
     * Але й обіцяти на «не знаю» не можна: обидві ці гілки означають, що
     * кошика ми не бачили, і кнопка в них не стверджує, а пропонує
     * перевірити (#89).
     */
    cartState: Loaded<CartState> | null
    /**
     * Стеля живого контуру (#34). `null` — ще не питали.
     *
     * Стоїть на екрані ЗАВЖДИ, а не лише коли спрацювала: стеля, про яку
     * дізнаються в мить відмови, — це та сама тиша, тільки з затримкою.
     */
    quota: Loaded<Quota> | null
    /**
     * Петля комори ЗАРАЗ крутиться. Прапорець не гасить нічого -- він лише
     * дає кнопці сказати ціну: збірка під час заповнення платить за частину
     * назв удруге, і мовчазна ціна від безкоштовної не відрізняється (#38).
     */
    looping?: boolean
    onRun: () => void
    /** Вхід Б: узяти кошик, наповнений кимось іншим, і довести до дверей. */
    onRunCart: () => void
  }

  const {
    mode,
    rules,
    rulesNote,
    deliveryLoaded,
    delivery,
    onDeliveryRetry,
    place,
    placeNote,
    placeResults,
    placeSearching,
    placeSearchNote,
    onPlaceSearch,
    onPlaceChoose,
    budget,
    spend,
    draft,
    pantry,
    pantryLoaded,
    pantrySource,
    pantryFailed,
    onPantryRetry,
    pantryPending,
    list,
    wanted,
    onWantedAdd,
    onWantedDrop,
    onWantedHome,
    wantedBusy,
    barCount,
    drinkKinds,
    people,
    autoSwap,
    barInWeek,
    onBarInWeek,
    onAutoSwap,
    onPeople,
    onMode,
    onDelivery,
    onBar,
    onPantry,
    onList,
    onToggleRule,
    onRemoveRule,
    onDraft,
    onAddRule,
    onBudget,
    onSave,
    cartState,
    quota,
    looping = false,
    onRun,
    onRunCart,
  }: Props = $props()

  const note = $derived(BUILD_MODES.find((m) => m.id === mode)?.note ?? '')
  const isOccasion = $derived(mode === 'event')

  const cartLines = $derived(cartState?.ok ? cartState.data.rows : 0)
  const cartEmpty = $derived(cartState?.ok === true && cartState.data.rows === 0)
  const cartSum = $derived(
    cartState?.ok && cartState.data.total > 0 ? ` · ${uahRound(cartState.data.total)}` : '',
  )
  /** «7 позицій · 1 253 ₴» — рівно те, що ми бачили в кошику акаунта. */
  const cartFacts = $derived(
    `${plural(cartLines, { one: 'позиція', few: 'позиції', many: 'позицій' })}${cartSum}`,
  )

  const runningOut = $derived(pantry.filter((item) => item.runningOut))
  const watched = $derived(pantry.filter((item) => item.cycleDays != null).length)
  const listLines = $derived(parseList(list))

  /** Відкритий діалог-диктофон. Саме слухання живе в Dictaphone.svelte. */
  let dictOpen = $state(false)
  let voiceNote = $state<string | null>(null)

  const OFFERED = new Set(['DeliveryHome', 'SelfPickup'])
  const deliveryOptions = $derived(
    deliveryLoaded?.ok ? deliveryLoaded.data.filter((option) => OFFERED.has(option.id)) : [],
  )
  const liveOptions = $derived(deliveryOptions.filter((option) => option.available).length)
  const refused = $derived([
    ...deliveryOptions
      .filter((option) => !option.available)
      .reduce((map, option) => {
        const reason = option.unavailableReason ?? 'причини не назвали'
        return map.set(reason, [...(map.get(reason) ?? []), option.label])
      }, new Map<string, string[]>())
      .entries(),
  ])

  const deliveryNote = $derived.by(() => {
    const option = deliveryOptions.find((o) => o.id === delivery)
    if (!option) return ''
    const parts = [option.note]
    if (option.cost > 0) parts.push(uahRound(option.cost))
    else if (option.minOrder !== null || option.threshold !== null) parts.push('безкоштовно')
    if (option.minOrder) parts.push(`від ${uahRound(option.minOrder)}`)
    if (option.maxWeightKg) parts.push(`до ${kg(option.maxWeightKg)}`)
    return parts.join(' · ')
  })


  const capped = $derived(quota?.ok === true && quota.data.blocked)
  const noNeeds = $derived(
    pantrySource !== null && pantry.every((item) => item.source !== 'receipts'),
  )
  const noHistory = $derived(
    pantrySource !== null && pantrySource.receipts === 0 && pantrySource.orders === 0,
  )
  const noPool = $derived(pantrySource !== null && pantrySource.targetPool === 0)
  const CAP_NEAR = 3

  const capNote = $derived(quota?.ok === true ? quota.data : null)

  const runLabel = $derived.by(() => {
    if (mode === 'list') {
      const count = listLines.length + wanted.length
      return count > 0 ? `Зібрати зі списку (${count})` : 'Зібрати зі списку'
    }
    if (mode === 'event') return 'Зібрати на подію'
    return noPool ? 'Зібрати на тиждень' : `Зібрати на тиждень на ${uahRound(budget)}`
  })

  const nothingToBuild = $derived(
    mode === 'list'
      ? listLines.length === 0 && wanted.length === 0
      : noNeeds && listLines.length === 0,
  )
</script>

<div class="start">

  <section class="block" data-tour="pantry">
    <div class="caption">у коморі зараз</div>
    {#if !pantryLoaded}
      <button
        class="stock"
        type="button"
        aria-label="Комора ще рахується — відкрити"
        onclick={onPantry}
      >
        <span class="stock-thumbs" aria-hidden="true">
          <span class="thumb sk"></span>
          <span class="thumb sk"></span>
          <span class="thumb sk"></span>
        </span>
        <span class="stock-body" aria-hidden="true">
          <span class="sk-line" style:width="62%"></span>
          <span class="sk-line" style:width="44%"></span>
        </span>
      </button>
      {#if pantryPending !== null}
        <PantryWait since={pantryPending} />
      {/if}
    {:else if pantry.length > 0}
      <button class="stock" type="button" onclick={onPantry}>
        <span class="stock-thumbs" aria-hidden="true">
          {#each runningOut.slice(0, 3) as item (item.id)}
            <span class="thumb">{NO_PHOTO.pantry}</span>
          {/each}
          {#if runningOut.length === 0}
            <span class="thumb">✓</span>
          {/if}
        </span>
        <span class="stock-body">
          <span class="stock-label">
            {runningOut.length > 0
              ? `Закінчується: ${runningOut
                  .slice(0, 3)
                  .map((item) => (item.label.split(' ')[0] ?? item.label).toLowerCase())
                  .join(', ')}${runningOut.length > 3 ? ` +${runningOut.length - 3}` : ''}`
              : 'Усе під наглядом, поповнювати нічого'}
          </span>
          <span class="stock-state">
            {watched === 0
              ? `${pantry.length} видів у списку`
              : watched === pantry.length
                ? `${pantry.length} видів під наглядом`
                : `${pantry.length} видів, ${watched} під наглядом`}{runningOut.length > 0
              ? ` · ${runningOut.length} треба поповнити`
              : ''}
          </span>
        </span>
        <span class="stock-go" aria-hidden="true">›</span>
      </button>
    {:else}
      <p class="note">
        {pantryFailed ??
          (pantrySource !== null
            ? pantryEmptyNote(pantrySource)
            : 'коморі поки нема з чого рахуватись')}
      </p>
      {#if pantryFailed !== null}
        <button class="write" type="button" onclick={onPantryRetry}>
          Спробувати ще раз ›
        </button>
      {:else}
        <button class="write" type="button" onclick={onPantry}>
          Записати, що вдома, самому ›
        </button>
      {/if}
    {/if}

    {#if !isOccasion}
      <button class="bar-door" type="button" onclick={onBar}>
        <span class="bar-door-text">
          що з напоїв удома
          {#if drinkKinds !== null && drinkKinds > 0}
            <span class="bar-door-count"
              >{plural(drinkKinds, { one: 'вид', few: 'види', many: 'видів' })}</span
            >
          {/if}
        </span>
        <span class="bar-go" aria-hidden="true">›</span>
      </button>
    {/if}
  </section>

  <section class="block" data-tour="week">
    <div class="caption">що збираємо</div>
    <div class="chips">
      {#each BUILD_MODES as option (option.id)}
        <button
          class="chip"
          class:on={mode === option.id}
          type="button"
          aria-pressed={mode === option.id}
          onclick={() => onMode(option.id)}
        >
          {option.label}
        </button>
      {/each}
    </div>
    <p class="note">{note}</p>

    {#if isOccasion}
      <div class="people">
        <span class="people-label">скільки вас буде</span>
        <div class="people-stepper">
          <button
            class="people-step"
            type="button"
            aria-label="Менше людей"
            disabled={people <= 1}
            onclick={() => onPeople(Math.max(1, people - 1))}
          >
            -
          </button>
          <span class="people-n num">{people}</span>
          <button
            class="people-step"
            type="button"
            aria-label="Більше людей"
            onclick={() => onPeople(Math.min(99, people + 1))}
          >
            +
          </button>
        </div>
      </div>

      <button class="bar-link" type="button" onclick={onBar}>
        <span class="bar-text">
          <span class="bar-title">Напої до приводу</span>
          <span class="bar-note">
            {barCount > 0 ? `обрано ${barCount}` : 'з того, що вже брав'}
          </span>
        </span>
        <span class="bar-go" aria-hidden="true">›</span>
      </button>
    {/if}
  </section>

  <Place
    {place}
    note={placeNote}
    results={placeResults}
    searching={placeSearching}
    searchNote={placeSearchNote}
    onSearch={onPlaceSearch}
    onChoose={onPlaceChoose}
  />

  <section class="block" data-tour="delivery">
    <div class="caption">як забирати</div>
    {#if deliveryLoaded === null}
      <div class="chips" aria-hidden="true">
        {#each DELIVERY_SKELETON as width, index (index)}
          <span class="chip sk" style:width="{width}px"></span>
        {/each}
      </div>
      <p class="note">Читаю умови доставки на твою адресу…</p>
    {:else if !deliveryLoaded.ok}
      <p class="note">Умови доставки не прочитались: {deliveryLoaded.message}</p>
      <button class="again" type="button" onclick={onDeliveryRetry}>
        Прочитати умови ще раз ›
      </button>
      <p class="note">
        Тому способів я звідси не назву — ні порогів, ні межі ваги. Кошик збереться, а
        доставку не перевірить.
      </p>
    {:else}
      <div class="chips">
        {#each deliveryOptions as option (option.id)}
          <button
            class="chip"
            class:on={option.id === delivery}
            type="button"
            aria-pressed={option.id === delivery}
            disabled={!option.available}
            title={option.available ? option.note : (option.unavailableReason ?? '')}
            onclick={() => onDelivery(option.id)}
          >
            {option.label}
          </button>
        {/each}
      </div>
      <p class="note">{deliveryNote}</p>
      {#if liveOptions <= 1}
        <p class="note">
          {liveOptions === 1
            ? 'Доступний один спосіб — решта нижче з причиною'
            : 'Жодного доступного способу за цією адресою'}
        </p>
      {/if}
      {#each refused as [reason, labels] (reason)}
        <p class="note">{labels.join(', ')} — {reason}</p>
      {/each}
    {/if}
  </section>

  <section class="block" data-tour="rules">
    <div class="caption">правила збору</div>
    <button
      class="auto"
      class:on={autoSwap}
      type="button"
      aria-pressed={autoSwap}
      onclick={onAutoSwap}
    >
      <span class="auto-text">
        <span class="auto-title">Дозволити заміну без питань</span>
        <span class="auto-note">
          {autoSwap
            ? 'не буде твого — візьмуть рівноцінне, заміни побачиш перед оформленням'
            : 'кожну заміну погоджуєш окремо'}
        </span>
      </span>
      <span class="auto-state">{autoSwap ? 'увімкнено' : 'вимкнено'}</span>
    </button>

    <button
      class="auto"
      class:on={barInWeek}
      type="button"
      aria-pressed={barInWeek}
      onclick={onBarInWeek}
    >
      <span class="auto-text">
        <span class="auto-title">Алкоголь із бару в тижневий кошик</span>
        <span class="auto-note">
          {barInWeek
            ? 'пиво й вино з твоїх чеків поїдуть за своїм ритмом'
            : 'напої живуть у барі й у тижневий кошик не їдуть'}
        </span>
      </span>
      <span class="auto-state">{barInWeek ? 'увімкнено' : 'вимкнено'}</span>
    </button>

    <Rules
      {rules}
      note={rulesNote}
      {budget}
      {spend}
      {pantrySource}
      {draft}
      {onToggleRule}
      {onRemoveRule}
      {onDraft}
      {onAddRule}
      {onBudget}
      {onSave}
    />
  </section>

  <div class="spacer"></div>

  <div class="dock">
    <div class="list-wrap" class:lead={noPool} data-tour="list">
      <textarea
        class="list-input"
        class:with-mic={voiceAvailable()}
        rows="2"
        placeholder="треба щось конкретне? молоко, хліб, туалетний папір…"
        value={list}
        oninput={(event) => onList(event.currentTarget.value)}
      ></textarea>
      {#if voiceAvailable()}
        <div class="mic-slot">
          <MicButton
            active={dictOpen}
            label="надиктувати список"
            onClick={() => {
              voiceNote = null
              dictOpen = true
            }}
          />
        </div>
      {/if}
    </div>

    {#if list.trim()}
      <button
        type="button"
        class="keep"
        disabled={wantedBusy}
        onclick={() => onWantedAdd(list)}
      >
        + у список на потім
      </button>
    {/if}
    {#if wanted.length > 0}
      <ul class="wanted">
        {#each wanted as row (row.id)}
          <li class="want">
            <span class="want-text">
              <span class="want-name">{row.label}</span>
              {#if row.why}
                <span class="why">{row.why}</span>
              {/if}
            </span>
            <button
              type="button"
              class="home"
              class:once={!row.atHome}
              aria-label={row.atHome
                ? `Не класти в комору після покупки: ${row.label}`
                : `Класти в комору після покупки: ${row.label}`}
              disabled={wantedBusy}
              onclick={() => onWantedHome(row)}
            >
              {row.atHome ? 'у комору' : 'разова'}
            </button>
            <button
              type="button"
              class="drop"
              aria-label="Прибрати зі списку: {row.label}"
              disabled={wantedBusy}
              onclick={() => onWantedDrop(row.id)}
            >
              ✕
            </button>
          </li>
        {/each}
      </ul>
        <p class="note">
          {wanted.length === 1 ? 'Рядок' : 'Рядки'} зі списку доїде в наступний кошик
        без нагадування і згорить, щойно поїде — куплене ляже в комору,
        крім позначеного «разова».
      </p>
    {/if}

    {#if voiceNote && !dictOpen}
      <p class="note">{voiceNote}</p>
    {:else if listLines.length > 0}
      <p class="note">
        {noHistory
          ? 'марку й кількість підберу з полиці: твоїх покупок я ще не бачу'
          : 'прочитаю текст сам — підберу звичні марки й кількість за твоїми покупками'}
      </p>
    {:else if noNeeds || noPool}
      <p class="note">Напиши, що потрібно, — марку й кількість підберу сам.</p>
    {/if}

    <button
      class="run"
      type="button"
      data-tour="run"
      disabled={capped || nothingToBuild}
      onclick={onRun}
    >
      {runLabel}
    </button>
    {#if looping && !capped && !nothingToBuild}
      <p class="note">Комора ще заповнюється — збірка назве частину видів сама, тому довше.</p>
    {/if}


    {#if capNote && (capNote.blocked || capNote.left <= CAP_NEAR)}
      <p class="cap" class:stop={capNote.blocked}>
        {capNote.headline}{#if capNote.action}. {capNote.action}{/if}{#if capNote.contact}:
          <a href={capNote.contact} target="_blank" rel="noopener">{capNote.contact}</a>
        {/if}
      </p>
    {:else if quota?.ok === false}
      <p class="cap">скільки прогонів лишилось — не знаю: {quota.message}</p>
    {/if}

    {#if listLines.length === 0 && cartEmpty}
    {:else if listLines.length === 0}
      <button
        class="from-cart"
        type="button"
        data-tour="from-cart"
        disabled={capped}
        onclick={onRunCart}
      >
        {#if cartLines > 0}
          У кошику {cartFacts} — перевір і доведи до дверей
        {:else}
          Перевірити кошик у «Сільпо» і довести до дверей
        {/if}
      </button>
    {:else if cartLines > 0}
      <button
        class="from-cart aside"
        type="button"
        data-tour="from-cart"
        disabled={capped}
        onclick={onRunCart}
      >
        У кошику {cartFacts} — окремий прогін, список не поїде
      </button>
    {/if}
  </div>

  <Dictaphone
    open={dictOpen}
    onPhrase={(text) =>
      onList(list.trim() ? `${list.trim().replace(/[,;\s]+$/, '')}, ${text}` : text)}
    onClose={() => (dictOpen = false)}
    onError={(message) => (voiceNote = message)}
  />
</div>

<style>
  .start {
    padding: 22px 20px 0;
    flex: 1;
    display: flex;
    flex-direction: column;
  }

  .block {
    margin-top: 16px;
  }

  .caption {
    font-size: 12px;
    color: var(--muted);
    margin-bottom: 7px;
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
  }

  .chip {
    display: flex;
    align-items: center;
    gap: 7px;
    padding: 0 12px;
    min-height: 40px;
    border-radius: 11px;
    font-size: 13px;
    font-weight: 600;
    white-space: nowrap;
    color: var(--muted);
    border: 1px solid var(--hair-strong);
    background: transparent;
  }

  .chip.sk {
    display: block;
    border-color: transparent;
    background: var(--chip-bg);
    animation: sk-pulse 1.2s ease-in-out infinite;
  }

  .chip:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .chip.on {
    color: var(--badge);
    border-color: var(--acc-edge);
    background: var(--acc-soft);
  }

  .people {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 9px;
    padding: 6px 12px;
    border-radius: 12px;
    border: 1px solid var(--hair);
    background: var(--chip-bg);
  }

  .people-label {
    flex: 1;
    font-size: 13px;
    color: var(--muted);
  }

  .people-stepper {
    display: flex;
    align-items: center;
    gap: 8px;
    flex: none;
  }

  .people-step {
    width: 36px;
    min-height: 36px;
    display: grid;
    place-items: center;
    border-radius: 10px;
    font-size: 15px;
    font-weight: 700;
    line-height: 1;
    color: var(--ink);
    border: 1px solid var(--hair-strong);
    background: transparent;
  }

  .people-step:disabled {
    opacity: 0.4;
  }

  .people-n {
    min-width: 26px;
    text-align: center;
    font-size: 14px;
    font-weight: 800;
  }

  .bar-door {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    width: 100%;
    margin-top: 10px;
    padding: 10px 12px;
    border: 1px solid var(--hair);
    border-radius: 12px;
    background: none;
    color: var(--ink);
    font: inherit;
    font-size: 14px;
    cursor: pointer;
  }

  .bar-door-text {
    display: flex;
    align-items: baseline;
    gap: 8px;
    text-align: left;
  }

  .bar-door-count {
    color: var(--muted);
    font-size: 13px;
  }

  .bar-link {
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    margin-top: 9px;
    padding: 10px 12px;
    border-radius: 12px;
    text-align: left;
    color: var(--ink);
    border: 1px solid var(--acc-edge);
    background: var(--acc-soft);
  }

  .bar-text {
    flex: 1;
    min-width: 0;
  }

  .bar-title {
    display: block;
    font-size: 13px;
    font-weight: 700;
  }

  .bar-note {
    display: block;
    font-size: 11px;
    color: var(--muted);
    margin-top: 1px;
  }

  .bar-go {
    flex: none;
    font-size: 18px;
    line-height: 1;
    color: var(--badge);
  }

  .auto {
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    margin-bottom: 9px;
    padding: 11px 12px;
    border-radius: 13px;
    text-align: left;
    color: var(--ink);
    border: 1px solid var(--hair-strong);
    background: transparent;
  }

  .auto.on {
    border-color: var(--acc-edge);
    background: var(--acc-soft);
  }

  .auto-text {
    flex: 1;
    min-width: 0;
  }

  .auto-title {
    display: block;
    font-size: 13px;
    font-weight: 700;
  }

  .auto-note {
    display: block;
    margin-top: 2px;
    font-size: 11.5px;
    line-height: 1.35;
    color: var(--muted);
  }

  .auto-state {
    flex: none;
    font-size: 11.5px;
    font-weight: 700;
    color: var(--badge);
  }

  .note {
    font-size: 11.5px;
    color: var(--faint);
    margin-top: 7px;
    line-height: 1.4;
  }

  .stock {
    display: flex;
    align-items: center;
    gap: 11px;
    width: 100%;
    padding: 10px 12px;
    text-align: left;
    border: 1px solid var(--hair);
    border-radius: 16px;
    background: var(--list-bg);
  }

  .stock-thumbs {
    display: flex;
    gap: 4px;
    flex: none;
  }

  .thumb {
    width: 28px;
    height: 28px;
    border-radius: 9px;
    flex: none;
    display: grid;
    place-items: center;
    font-size: 14px;
    background: var(--thumb-bg);
    border: 1px solid var(--hair);
  }

  .stock-body {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-width: 0;
  }

  .stock-label {
    font-size: 13px;
    font-weight: 700;
    line-height: 1.25;
    color: var(--warn);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .stock-state {
    margin-top: 2px;
    font-size: 11.5px;
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .write,
  .again {
    margin-top: 8px;
    padding: 0;
    align-self: flex-start;
    font-size: 13px;
    font-weight: 600;
    color: var(--accent);
    border: none;
    background: none;
  }

  .stock-go {
    flex: none;
    font-size: 16px;
    line-height: 1;
    color: var(--badge);
  }

  .thumb.sk {
    animation: sk-pulse 1.2s ease-in-out infinite;
  }

  .sk-line {
    height: 12px;
    border-radius: 6px;
    background: var(--chip-bg);
    animation: sk-pulse 1.2s ease-in-out infinite;
  }

  .sk-line + .sk-line {
    margin-top: 6px;
    height: 10px;
  }

  @keyframes sk-pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.45;
    }
  }

  .wanted {
    display: flex;
    flex-direction: column;
    margin-top: var(--gap-2, 8px);
    padding: 0;
    list-style: none;
  }

  .keep,
  .why {
    color: var(--muted);
    font-size: 0.82em;
  }

  .want {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 9px 2px;
    border-bottom: 1px solid var(--hair);
    color: var(--muted);
    font-size: 0.86rem;
  }

  .want:last-child {
    border-bottom: 0;
  }

  .want-text {
    display: flex;
    min-width: 0;
    flex: 1;
    flex-direction: column;
    gap: 1px;
  }

  .want-name {
    color: var(--ink);
    overflow-wrap: anywhere;
  }

  .keep {
    cursor: pointer;
    color: var(--ink);
  }

  .keep:disabled,
  .home:disabled,
  .drop:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .home {
    border: 0;
    border-radius: var(--radius-pill, 999px);
    background: var(--chip-bg);
    color: var(--muted);
    padding: 1px 8px;
    font: inherit;
    font-size: 0.7rem;
    cursor: pointer;
  }

  .home.once {
    text-decoration: line-through;
  }

  .drop {
    border: 0;
    background: transparent;
    color: var(--muted);
    padding: 0;
    font: inherit;
    cursor: pointer;
  }

  .list-wrap {
    position: relative;
    margin-bottom: 8px;
  }

  .list-input {
    width: 100%;
    padding: 10px 12px;
    border-radius: 12px;
    font: inherit;
    font-size: 13.5px;
    line-height: 1.45;
    color: var(--ink);
    border: 1px solid var(--hair-strong);
    background: var(--chip-bg);
    resize: none;
  }

  .list-input::placeholder {
    color: var(--faint);
  }

  .list-wrap.lead .list-input {
    border-color: var(--acc-edge);
    background: var(--acc-soft);
  }

  .list-input:focus {
    outline: none;
    border-color: var(--acc-edge);
    background: var(--acc-soft);
  }

  .list-input.with-mic {
    padding-right: 48px;
  }

  .mic-slot {
    position: absolute;
    right: 8px;
    top: 50%;
    translate: 0 -50%;
  }

  .spacer {
    flex: 1;
    min-height: 12px;
  }

  .dock .note {
    margin: 0 0 8px;
  }

  .dock {
    position: sticky;
    bottom: 0;
    margin: 16px -20px 0;
    padding: 10px 20px calc(12px + env(safe-area-inset-bottom, 0px));
    border-top: 1px solid var(--hair);
    background: var(--glass-bg);
    backdrop-filter: blur(22px) saturate(160%);
  }

  .run {
    width: 100%;
    padding: 16px;
    border-radius: 16px;
    font-size: clamp(16px, 4.4vw, 17.5px);
    font-weight: 800;
    letter-spacing: -0.2px;
    color: var(--pri-ink);
    background: var(--pri-bg);
    box-shadow: 0 10px 26px rgb(240 169 59 / 0.3);
  }

  .cap {
    margin-top: 6px;
    font-size: 12.5px;
    color: var(--faint);
    text-align: center;
    text-wrap: balance;
  }

  .cap.stop {
    margin-top: 12px;
    padding: 10px 12px;
    border: 1px solid var(--acc-edge);
    border-radius: 12px;
    background: var(--acc-soft);
    color: var(--ink);
    text-align: left;
  }

  .cap a {
    color: inherit;
  }

  .from-cart {
    width: 100%;
    margin-top: 10px;
    padding: 12px;
    border-radius: 14px;
    font-size: 13.5px;
    font-weight: 700;
    line-height: 1.35;
    color: var(--ink);
    border: 1px solid var(--acc-edge);
    background: var(--acc-soft);
  }

  .from-cart.aside {
    margin-top: 8px;
    padding: 8px 12px;
    font-size: 12.5px;
    font-weight: 600;
    color: var(--muted);
    border-color: var(--hair);
    background: transparent;
  }

  .run:disabled {
    padding: 12px;
    color: var(--muted);
    background: transparent;
    border: 1px solid var(--hair-strong);
    box-shadow: none;
  }

  .from-cart:disabled {
    color: var(--muted);
    border-color: var(--hair-strong);
    background: transparent;
  }
</style>
