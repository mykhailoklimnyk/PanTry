<script lang="ts">
  import Back from '../Back.svelte'
  import { asksWord } from '../attention'
  import Dictaphone from '../Dictaphone.svelte'
  import MicButton from '../MicButton.svelte'
  import Modal from '../Modal.svelte'
  import { collectorActs } from '../feedback'
  import { voiceAvailable } from '../speech'
  import { forkBasis, forkNote, forkRange } from '../swap'
  import { NO_PHOTO } from '../ui'
  import { plural, uah } from '../format'
  import type { Loaded } from '../data'
  import type {
    CartLine,
    OrderFeedback,
    SavedSwap,
    Substitute,
    SwapOption,
  } from '../types'

  export type SwapPolicy = 'substitute' | 'skip' | 'call'

  interface Props {
    lines: CartLine[]
    policy: Record<string, SwapPolicy>
    chains: Record<string, Substitute[]>
    autoSwap: boolean
    onAutoSwap: () => void
    onPolicy: (id: string, value: SwapPolicy) => void
    onChain: (lineId: string, chain: Substitute[]) => void
    onOptions: (lineId: string, query: string) => Promise<Loaded<SwapOption[]>>
    feedback: OrderFeedback
    stale: boolean
    staleWhy: string[]
    onRebuild: () => void
    remember: boolean
    onRemember: () => void
    saved: SavedSwap[]
    onForget: (id: string) => void
    savedBusy: boolean
    confirming: boolean
    onConfirm: () => void
    onBack: () => void
    focus?: 'urgent' | 'all'
  }

  const {
    lines,
    policy,
    chains,
    autoSwap,
    onAutoSwap,
    onPolicy,
    onChain,
    onOptions,
    feedback,
    stale,
    staleWhy,
    onRebuild,
    remember,
    onRemember,
    saved,
    onForget,
    savedBusy,
    confirming,
    onConfirm,
    onBack,
    focus = 'all',
  }: Props = $props()

  const urgent = $derived(lines.filter(asksWord))
  const calm = $derived(lines.filter((line) => !urgent.includes(line)))
  const ready = $derived(
    calm.filter((line) => line.mandate !== null && line.swapFork === null).length,
  )
  const capped = $derived(calm.filter((line) => line.swapFork !== null).length)
  const hands = $derived(
    [
      ready > 0 ? `${ready} із заміною напоготові` : '',
      capped > 0 ? `${capped} з межею в грошах` : '',
    ]
      .filter(Boolean)
      .join(' і '),
  )
  let revealed = $state(false)
  const narrowed = $derived(focus === 'urgent' && urgent.length > 0 && !revealed)
  const shown = $derived(narrowed ? urgent : [...urgent, ...calm])
  const restTitle = $derived(urgent.length > 0 ? 'Решта кошика' : 'Кошик')

  let picking = $state<string | null>(null)
  let query = $state('')
  let options = $state<SwapOption[]>([])
  let loading = $state(false)
  let failed = $state<string | null>(null)
  let refused = $state<string | null>(null)
  let failedImages = $state(new Set<string>())
  let dictating = $state(false)
  let voiceNote = $state<string | null>(null)
  let dictated = false

  let consented = $state(false)

  async function openPicker(lineId: string, text = '') {
    picking = lineId
    query = text
    loading = true
    failed = null
    refused = null
    const result = await onOptions(lineId, text)
    if (picking !== lineId) return
    loading = false
    if (result.ok) {
      options = result.data
      return
    }
    options = []
    failed = result.message
  }

  function closePicker() {
    picking = null
    query = ''
    options = []
    failed = null
    refused = null
  }

  let scrolledToFocus = false
  $effect(() => {
    if (scrolledToFocus || focus !== 'urgent' || urgent.length === 0) return
    scrolledToFocus = true
    document.querySelector('[data-scroll="urgent"]')?.scrollIntoView({ block: 'start' })
  })

  const SOURCES: Record<string, string> = {
    history: 'з твоєї історії',
    replacements: 'пропонує «Сільпо»',
    similar: 'схожий товар',
    manual: 'додав ти',
  }

  const OPTIONS: { id: SwapPolicy; label: string; note: string }[] = [
    { id: 'substitute', label: 'Замінити за списком', note: 'збирач бере перше доступне' },
    { id: 'skip', label: 'Не привозити', note: 'краще нічого, ніж не те' },
    { id: 'call', label: 'Подзвонити мені', note: 'той самий дзвінок, від якого тікаємо' },
  ]

  function chainOf(line: CartLine): Substitute[] {
    return chains[line.externalProductId] ?? line.chain
  }

  const remembered = $derived(lines.filter((line) => chainOf(line).length > 0).length)

  function edit(line: CartLine, next: Substitute[]) {
    onChain(line.externalProductId, next)
  }

  function drop(line: CartLine, subId: string) {
    edit(
      line,
      chainOf(line).filter((s) => s.externalProductId !== subId),
    )
  }

  function move(line: CartLine, index: number, delta: number) {
    const chain = [...chainOf(line)]
    const to = index + delta
    if (to < 0 || to >= chain.length) return
    const [moved] = chain.splice(index, 1)
    chain.splice(to, 0, moved!)
    edit(line, chain)
  }

  function add(line: CartLine, option: SwapOption) {
    if (option.sameKind === false) {
      refused = option.externalProductId
      return
    }
    const chain = chainOf(line)
    if (chain.some((s) => s.externalProductId === option.externalProductId)) return
    edit(line, [
      ...chain,
      {
        externalProductId: option.externalProductId,
        name: option.name,
        source: 'manual',
        price: option.price,
        ratio: option.ratio,
        byWeight: option.byWeight,
      },
    ])
  }

  function policyOf(line: CartLine): SwapPolicy {
    return policy[line.externalProductId] ?? 'substitute'
  }

  const collector = $derived(collectorActs(feedback))

  function handOf(line: CartLine): string | null {
    if (policyOf(line) !== 'substitute') return null
    if (chainOf(line).length === 0 && line.mandate === null) return null
    const ours = 'до слота заміню я — це мій запис у твій кошик'
    if (collector === false) return `${ours}; біля полиці збирач міняти не буде`
    if (collector === null) return `${ours}; чи прочитає мандат збирач — не звіряв`
    return `${ours}; біля полиці — збирач за мандатом`
  }

  function mandateOf(line: CartLine): string | null {
    const kind = policyOf(line)
    if (kind === 'skip') return `${line.name}: якщо немає — не привозити. Не дзвонити.`
    if (kind === 'call') return `${line.name}: якщо немає — подзвонити.`

    const chain = chainOf(line)
    if (chain.length === 0) {
      return line.mandate ?? null
    }
    return `${line.name}: якщо немає — ${chain.map((s) => s.name).join(', потім ')}. Не дзвонити.`
  }

  function withoutMandate(): string {
    if (collector === false) return 'у замовленні стоїть «не збирайте те, що потребує уточнень» — не привезуть'
    if (collector === true) return 'у замовленні стоїть «замініть на схожі» — збирач підбере на свій розсуд'
    return 'що буде далі, вирішить галочка замін у замовленні «Сільпо» — ми її не звіряли'
  }
</script>

<div class="swaps">
  <div class="top">
    <Back label="До кошика" onClick={onBack} />
    <h1>Погодження замін</h1>
  </div>

  <p class="lede">
    У застосунку магазину це одна галочка на все замовлення. Тут — рішення на кожну
    позицію: чим саме заміняти, в якому порядку і що прочитає збирач.
  </p>

  {#if feedback.changes !== null}
    <div class="setting" class:blocked={collector === false} data-testid="feedback">
      {#if collector === false}
        <p class="setting-title">Біля полиці збирач міняти не буде</p>
        <p class="setting-note">
          У твоєму замовленні стоїть «не збирайте те, що потребує уточнень» -- одна
          галочка на все замовлення, і вона сильніша за будь-який мандат. Погоджене
          тут спрацює до слота: якщо позиція зникне з полиці раніше, рядок перепишу я.
        </p>
      {:else}
        <p class="setting-title">У замовленні дозволено заміни</p>
        <p class="setting-note">
          У «Сільпо» стоїть «замініть на схожі». Що саме схоже, вирішує цей екран:
          на кожну позицію свій список замін.
        </p>
      {/if}
      {#if feedback.contacts === 'call'}
        <p class="setting-note">
          Ще там стоїть «зателефонуйте для уточнень» -- дзвінок буде, навіть коли
          все погоджено тут.
        </p>
      {:else if feedback.contacts === 'doNotCall'}
        <p class="setting-note">
          Ще там стоїть «не телефонуйте». З мандатом це більше не означає «роби, що
          вважаєш за потрібне», а означає «роби, як домовились».
        </p>
      {/if}
      <p class="setting-where">
        Міняється це тільки в застосунку «Сільпо»: Доставка та оплата → Заміна
        товарів. Ми в чужі налаштування не пишемо.
      </p>
    </div>
  {/if}

  <button class="auto" class:on={autoSwap} type="button" onclick={onAutoSwap}>
    <span class="auto-text">
      <span class="auto-title">Авто-заміна без погодження</span>
      <span class="auto-note">
        якщо позиції немає, збирач бере такий самий вид іншої марки
      </span>
      <span class="auto-note">{forkNote()}</span>
    </span>
    <span class="auto-state">{autoSwap ? 'увімкнена' : 'вимкнена'}</span>
  </button>

  {#if lines.length === 0}
    <p class="empty">Кошик порожній -- погоджувати нічого.</p>
  {:else}
    {#if urgent.length === 0}
      <p class="empty">
        Термінового нічого: усе в кошику є на складі твоєї філії.
        {#if ready > 0}
          Наявність між збіркою і збиранням міняється, тож {plural(ready, {
            one: 'рядок їде',
            few: 'рядки їдуть',
            many: 'рядків їдуть',
          })} із заміною напоготові -- вони нижче.
        {:else}
          Але наявність між збіркою і збиранням міняється -- ланцюжок можна скласти
          наперед.
        {/if}
      </p>
    {/if}

    <div class="cards">
      {#each shown as line, index (line.externalProductId)}
        {#if index === 0 && urgent.length > 0}
          <p class="group" data-scroll="urgent">
            {plural(urgent.length, {
              one: 'позиція просить',
              few: 'позиції просять',
              many: 'позицій просять',
            })} рішення
          </p>
        {/if}
        {#if index === urgent.length && calm.length > 0}
          <p class="group" data-testid="rest">
            {restTitle} -- {calm.length}{hands ? `, з них ${hands}` : ''}
          </p>
        {/if}
        {@const chain = chainOf(line)}
        {@const kind = policyOf(line)}
        <article class="card" class:risk={line.atRisk}>
          <div class="head">
            <div class="thumb" aria-hidden="true">
              {NO_PHOTO.line}
            </div>
            <div class="head-text">
              <h2 class="ellipsis">{line.name}</h2>
              <p class="why">{line.explanation}</p>
            </div>
          </div>

          {#if kind === 'substitute'}
            {#if chain.length > 0}
              <p class="chain-cap">Не буде — візьму по черзі:</p>
            {:else if line.swapFork}
              <p class="chain-cap">Ланцюжка немає — лишається межа в грошах:</p>
            {/if}
            <ol class="chain">
              {#each chain as sub, index (sub.externalProductId)}
                <li>
                  <span class="order num">{index + 1}</span>
                  <span class="sub">
                    <span class="sub-name ellipsis">{sub.name}</span>
                    <span class="sub-source">
                      {SOURCES[sub.source] ?? sub.source}{sub.price != null
                        ? ` · ${uah(sub.price)}${sub.byWeight ? '/кг' : ''}${sub.ratio ? ` · ${sub.ratio}` : ''}`
                        : ''}
                    </span>
                  </span>
                  <span class="order-acts">
                    <button
                      class="move"
                      type="button"
                      disabled={index === 0}
                      aria-label="Вище: {sub.name}"
                      onclick={() => move(line, index, -1)}
                    >
                      ↑
                    </button>
                    <button
                      class="move"
                      type="button"
                      disabled={index === chain.length - 1}
                      aria-label="Нижче: {sub.name}"
                      onclick={() => move(line, index, 1)}
                    >
                      ↓
                    </button>
                  </span>
                  <button
                    class="drop"
                    type="button"
                    aria-label="Прибрати {sub.name} із ланцюжка"
                    onclick={() => drop(line, sub.externalProductId)}
                  >
                    ×
                  </button>
                </li>
              {/each}

              {#if chain.length === 0}
                {#if line.swapFork}
                  <li class="rule fork">
                    <span class="fork-range">Візьмуть {forkRange(line.swapFork)}</span>
                    <span class="fork-basis">
                      {forkBasis(line.price, line.swapFork)} · не знайдеться в цій вилці --
                      не привезуть
                    </span>
                  </li>
                {:else if line.mandate}
                  <li class="rule">{line.mandate}</li>
                {:else}
                  <li class="none">
                    {line.consideredTotal <= 1
                      ? 'Замінити нема чим: на цей слот під намір є лише цей товар.'
                      : 'Схожого того ж виду на цей слот не знайшлось.'}
                    {withoutMandate()}
                  </li>
                {/if}
              {/if}
            </ol>

            <button class="pick" type="button" onclick={() => openPicker(line.externalProductId)}>
              + Додати заміну
            </button>
          {/if}

          <div class="options">
            {#each OPTIONS as option (option.id)}
              <button
                class="option"
                class:on={kind === option.id}
                class:warn={option.id === 'call'}
                type="button"
                aria-pressed={kind === option.id}
                onclick={() => onPolicy(line.externalProductId, option.id)}
              >
                <span class="option-label">{option.label}</span>
                <span class="option-note">{option.note}</span>
              </button>
            {/each}
          </div>

          <div class="mandate">
            <div class="mandate-cap">
              поїде збирачу{line.mandateAhead ? ' -- готово наперед' : ''}
            </div>
            {#if mandateOf(line) !== null}
              <p class="mono mandate-text">{mandateOf(line)}</p>
            {:else}
              <p class="mandate-none">нічого: {withoutMandate()}</p>
            {/if}
            {#if handOf(line) !== null}
              <p class="hand" class:blocked={collector === false}>{handOf(line)}</p>
            {/if}
          </div>
        </article>
      {/each}
    </div>
    {#if narrowed}
      <button
        class="reveal"
        type="button"
        data-testid="reveal-rest"
        onclick={() => (revealed = true)}
      >
        Показати решту кошика — {calm.length}{hands ? ` · ${hands}` : ''}
      </button>
    {/if}

    {#if stale}
      <div class="changed">
        <div class="what">
          <p>
            Кошик зібрано за іншими налаштуваннями. Щоб зміни поїхали збирачу,
            його треба перезібрати.
          </p>
          <ul>
            {#each staleWhy as line (line)}
              <li>{line}</li>
            {/each}
          </ul>
        </div>
        <button class="rebuild" type="button" onclick={onRebuild}>Перезібрати</button>
      </div>
    {/if}

    {#if saved.length > 0}
      <section class="saved">
        <h3>Діє надалі</h3>
        <ul>
          {#each saved as row (row.id)}
            <li>
              <span><strong>{row.label}</strong> — {row.links.join(' → ')}</span>
              <button
                type="button"
                aria-label="Зняти погодження: {row.label}"
                disabled={savedBusy}
                onclick={() => onForget(row.id)}
              >
                ✕
              </button>
            </li>
          {/each}
        </ul>
      </section>
    {/if}

    <p class="outro">
      {#if collector === true}
        Погоджене наперед знімає дзвінок збирача.
      {:else}
        Погоджене наперед лишається в силі до слота: якщо позиція зникне з полиці
        раніше за збирання, рядок перепишу я.
      {/if}
    </p>

    <div class="bottom-dock glass">
      <label class="remember">
        <input type="checkbox" checked={remember} onchange={onRemember} />
        Запам'ятати ці заміни для цих видів надалі
      </label>
      {#if remember}
        <p class="remember-note">
          {#if remembered > 0}
            запам'ятаю: наступного разу не питатиму про ці
            {plural(remembered, { one: 'вид', few: 'види', many: 'видів' })}
          {:else}
            запам'ятовувати поки нічого: ланцюжок заміни не складений на жодному рядку
          {/if}
        </p>
      {/if}

      {#if !confirming}
        <button class="confirm dock-btn" type="button" onclick={onBack}>Підтвердити</button>
      {/if}
      {#if confirming && !stale}
        <label class="consent">
          <input
            type="checkbox"
            checked={consented}
            onchange={() => (consented = !consented)}
          />
          Згоден, щоб збирач замінив за цими правилами, якщо чогось не буде
        </label>
        <button class="confirm" type="button" disabled={!consented} onclick={onConfirm}>
          Погоджую -- оформити
        </button>
        {#if !consented}
          <p class="why-blocked" role="status">
            постав галочку вище — без неї не знаю, що ти прочитав ці правила
          </p>
        {/if}
      {/if}
    </div>
  {/if}

  {#if picking !== null}
    {@const line = lines.find((l) => l.externalProductId === picking)}
    <Modal label="Чим заміняти">
      <p class="pick-cap">{line ? line.name : ''}</p>
      <form
        class="pick-search"
        onsubmit={(event) => {
          event.preventDefault()
          if (picking !== null) void openPicker(picking, query)
        }}
      >
        <span class="voice-wrap">
          <input
            type="text"
            value={query}
            placeholder="назва товару"
            aria-label="Пошук заміни"
            oninput={(event) => (query = event.currentTarget.value)}
          />
          {#if voiceAvailable()}
            <span class="mic-slot"><MicButton
              active={dictating}
              label="надиктувати заміну"
              onClick={() => {
                voiceNote = null
                dictated = false
                dictating = true
              }}
            /></span>
          {/if}
        </span>
        <button class="secondary" type="submit">Знайти</button>
      </form>
      {#if voiceNote}
        <p class="pick-error" role="alert">{voiceNote}</p>
      {/if}
      <Dictaphone
        open={dictating}
        onPhrase={(text) => {
          query = query.trim() ? `${query.trim()} ${text}` : text
          dictated = true
        }}
        onClose={() => {
          dictating = false
          if (dictated && picking !== null) void openPicker(picking, query)
        }}
        onError={(message) => (voiceNote = message)}
      />

      {#if loading}
        <p class="pick-note">шукаю на цей слот...</p>
      {:else if failed}
        <p class="pick-error" role="alert">{failed}</p>
      {:else if options.length === 0}
        <p class="pick-note">
          На це вікно доставки тут порожньо. Асортимент прив'язаний до слота: спробуй
          інші слова або інший слот.
        </p>
      {:else}
        <ul class="pick-list">
          {#each options as option (option.externalProductId)}
            {@const already =
              line !== undefined &&
              chainOf(line).some((s) => s.externalProductId === option.externalProductId)}
            {@const other = option.sameKind === false}
            <li>
              <div class="pick-line">
                <button
                  class="pick-row"
                  class:other
                  type="button"
                  disabled={already}
                  onclick={() => {
                    if (line) add(line, option)
                  }}
                >
                  <span class="pick-thumb" aria-hidden="true">
                    {#if option.imageUrl && !failedImages.has(option.externalProductId)}
                      <img
                        src={option.imageUrl}
                        alt=""
                        loading="lazy"
                        onerror={() =>
                          (failedImages = new Set(failedImages).add(option.externalProductId))}
                      />
                    {:else}
                      {NO_PHOTO.line}
                    {/if}
                  </span>
                  <span class="pick-name">{option.name}</span>
                  <span class="pick-facts">
                    {uah(option.price)}{option.ratio ? ` · ${option.ratio}` : ''}{option.stock !==
                    null
                      ? ` · залишок ${option.stock}`
                      : ''}{option.sliced ? ' · нарізаний' : ''}
                  </span>
                  <span class="pick-add">
                    {already ? 'вже в списку' : other ? 'інший вид' : 'додати'}
                  </span>
                </button>
                {#if option.cardUrl}
                  <a
                    class="pick-open"
                    href={option.cardUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    title="відкрити картку в «Сільпо»"
                    aria-label="Відкрити «{option.name}» в «Сільпо»"
                  >
                    ↗
                  </a>
                {/if}
              </div>
              {#if refused === option.externalProductId}
                <p class="pick-why" role="status">
                  {option.kind
                    ? `Це інший вид — не з «${option.kind}».`
                    : 'Це інший вид.'} Заміна — обіцянка збирачу взяти те саме:
                  збирач прочитав би «якщо немає — {option.name}» і привіз би не те, по
                  що ти прийшов. Окрема позиція в кошик — так, заміна — ні.
                </p>
              {/if}
            </li>
          {/each}
        </ul>
      {/if}

      <div class="pick-actions">
        <button class="secondary" type="button" onclick={closePicker}>Готово</button>
      </div>
    </Modal>
  {/if}
</div>

<style>
  .dock-btn {
    width: 100%;
    margin-top: 10px;
  }
  .swaps {
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

  .setting {
    margin-top: 12px;
    padding: 12px 13px;
    border-radius: 13px;
    border: 1px solid var(--hair);
    background: var(--list-bg);
  }

  .setting.blocked {
    border-color: var(--warn);
    background: var(--row-risk);
  }

  .setting-title {
    font-size: 13.5px;
    font-weight: 700;
    color: var(--ink);
  }

  .setting.blocked .setting-title {
    color: var(--risk-ink);
  }

  .setting-note {
    margin-top: 5px;
    font-size: 12px;
    line-height: 1.5;
    color: var(--muted);
  }

  .setting-where {
    margin-top: 7px;
    font-size: 11.5px;
    line-height: 1.45;
    color: var(--faint);
  }

  .auto {
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    margin-top: 12px;
    padding: 12px 13px;
    text-align: left;
    border-radius: 13px;
    border: 1px dashed var(--hair-strong);
    background: transparent;
    color: var(--ink);
  }

  .auto.on {
    border-style: solid;
    border-color: var(--acc-edge);
    background: var(--acc-soft);
  }

  .auto-text {
    flex: 1;
    min-width: 0;
  }

  .auto-title {
    display: block;
    font-size: 13.5px;
    font-weight: 700;
  }

  .auto.on .auto-title {
    color: var(--badge);
  }

  .auto-note {
    display: block;
    margin-top: 2px;
    font-size: 12px;
    color: var(--muted);
    line-height: 1.4;
  }

  .auto-state {
    flex: none;
    font-size: 12px;
    font-weight: 700;
    color: var(--faint);
  }

  .auto.on .auto-state {
    color: var(--badge);
  }

  .empty {
    margin-top: 18px;
    padding: 16px;
    border-radius: 14px;
    font-size: 13px;
    color: var(--muted);
    border: 1px solid var(--hair);
    background: var(--list-bg);
  }

  .cards {
    margin-top: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .card {
    padding: 13px;
    border-radius: 16px;
    border: 1px solid var(--hair);
    background: var(--list-bg);
  }

  .card.risk {
    background: var(--row-risk);
  }

  .head {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .thumb {
    width: 36px;
    height: 36px;
    border-radius: 10px;
    flex: none;
    display: grid;
    place-items: center;
    font-size: 17px;
    background: var(--thumb-bg);
    border: 1px solid var(--hair);
  }

  .head-text {
    flex: 1;
    min-width: 0;
  }

  h2 {
    font-size: 14px;
    font-weight: 700;
    line-height: 1.25;
  }

  .why {
    font-size: 11.5px;
    color: var(--muted);
    margin-top: 2px;
    line-height: 1.3;
  }

  .card.risk .why {
    color: var(--warn);
  }

  .chain-cap {
    margin-top: 11px;
    font-size: 11.5px;
    color: var(--muted);
  }

  .chain-cap + .chain {
    margin-top: 5px;
  }

  .chain {
    margin-top: 11px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .chain li {
    display: flex;
    align-items: center;
    gap: 9px;
    padding: 7px 9px;
    border-radius: 10px;
    border: 1px solid var(--hair);
    background: var(--chip-bg);
  }

  .order {
    width: 18px;
    height: 18px;
    flex: none;
    display: grid;
    place-items: center;
    border-radius: 50%;
    font-size: 10.5px;
    font-weight: 800;
    color: var(--pri-ink);
    background: var(--badge);
  }

  .sub {
    flex: 1;
    min-width: 0;
  }

  .sub-name {
    display: block;
    font-size: 12.5px;
    font-weight: 700;
    line-height: 1.25;
  }

  .sub-source {
    display: block;
    font-size: 10.5px;
    color: var(--faint);
    margin-top: 1px;
  }

  .drop {
    flex: none;
    width: 26px;
    height: 26px;
    display: grid;
    place-items: center;
    border-radius: 8px;
    font-size: 15px;
    line-height: 1;
    color: var(--muted);
  }

  .none {
    font-size: 11.5px;
    color: var(--warn);
    justify-content: center;
  }

  .rule {
    font-size: 11.5px;
    line-height: 1.4;
    color: var(--muted);
  }

  .fork {
    display: block;
  }

  .fork-range {
    display: block;
    font-size: 12.5px;
    font-weight: 700;
    color: var(--ink);
  }

  .fork-basis {
    display: block;
    margin-top: 1px;
    font-size: 10.5px;
    color: var(--faint);
  }

  .order-acts {
    display: flex;
    flex: none;
    gap: 2px;
  }

  .move {
    width: 26px;
    min-height: 26px;
    display: grid;
    place-items: center;
    border-radius: 8px;
    font-size: 12px;
    line-height: 1;
    color: var(--muted);
    border: 1px solid var(--hair);
    background: transparent;
  }

  .move:disabled {
    opacity: 0.35;
  }

  .pick {
    width: 100%;
    margin-top: 8px;
    padding: 9px 12px;
    min-height: 40px;
    border-radius: 11px;
    font-size: 12.5px;
    font-weight: 700;
    color: var(--ink);
    border: 1px dashed var(--hair-strong);
    background: transparent;
  }

  .group {
    padding-top: 4px;
    font-size: 12.5px;
    font-weight: 700;
    color: var(--muted);
  }

  .group + .card {
    margin-top: -4px;
  }

  .pick-cap {
    font-size: 13px;
    font-weight: 700;
  }

  .pick-search {
    display: flex;
    gap: 8px;
    margin-top: 9px;
  }

  .pick-search input {
    flex: 1;
    min-width: 0;
    padding: 11px 12px;
    min-height: 44px;
    border-radius: 11px;
    font-size: 14px;
    color: var(--ink);
    border: 1px solid var(--hair-strong);
    background: transparent;
    outline: none;
  }

  .secondary {
    padding: 0 14px;
    min-height: 44px;
    border-radius: 11px;
    font-size: 13px;
    font-weight: 700;
    color: var(--ink);
    border: 1px solid var(--hair-strong);
    background: transparent;
  }

  .pick-note,
  .pick-error {
    margin-top: 10px;
    font-size: 12px;
    line-height: 1.4;
    color: var(--muted);
  }

  .pick-error {
    color: var(--warn);
  }

  .pick-list {
    margin-top: 10px;
    max-height: 46vh;
    overflow-y: auto;
    border-radius: 12px;
    border: 1px solid var(--hair);
  }

  .pick-list li + li {
    border-top: 1px solid var(--hair);
  }

  .pick-line {
    display: flex;
    align-items: stretch;
  }

  .pick-row {
    display: grid;
    grid-template-columns: auto 1fr auto;
    gap: 2px 10px;
    flex: 1;
    min-width: 0;
    padding: 10px 12px;
    text-align: left;
    color: var(--ink);
    background: transparent;
  }

  .pick-thumb {
    grid-row: 1 / span 2;
    grid-column: 1;
    align-self: center;
    width: 38px;
    height: 38px;
    display: grid;
    place-items: center;
    border-radius: 10px;
    overflow: hidden;
    font-size: 16px;
    background: var(--thumb-bg);
    border: 1px solid var(--hair);
  }

  .pick-thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .pick-open {
    flex: none;
    display: grid;
    place-items: center;
    width: 34px;
    font-size: 14px;
    text-decoration: none;
    color: var(--muted);
    border-left: 1px solid var(--hair);
  }

  .pick-row:disabled {
    opacity: 0.55;
  }

  .pick-name {
    grid-column: 2;
    font-size: 13px;
    font-weight: 700;
    line-height: 1.25;
  }

  .pick-facts {
    grid-column: 2;
    font-size: 11.5px;
    color: var(--muted);
  }

  .pick-add {
    grid-row: 1 / span 2;
    grid-column: 3;
    align-self: center;
    font-size: 11.5px;
    font-weight: 700;
    white-space: nowrap;
    color: var(--badge);
  }

  .pick-row.other .pick-name {
    color: var(--muted);
  }

  .pick-row.other .pick-add {
    color: var(--warn);
  }

  .pick-why {
    padding: 0 12px 10px;
    font-size: 11.5px;
    line-height: 1.45;
    color: var(--warn);
  }

  .pick-actions {
    display: flex;
    justify-content: flex-end;
    margin-top: 11px;
  }

  .changed {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 14px;
    padding: 11px 13px;
    border-radius: 13px;
    font-size: 12.5px;
    line-height: 1.4;
    color: var(--risk-ink);
    border: 1px solid var(--warn);
    background: var(--row-risk);
  }

  .what {
    flex: 1;
  }

  .changed ul {
    margin: 6px 0 0;
    list-style: disc;
    padding-inline-start: 17px;
  }

  .changed li {
    margin-top: 2px;
  }

  .rebuild {
    flex: none;
    padding: 0 12px;
    min-height: 40px;
    border-radius: 11px;
    font-size: 12.5px;
    font-weight: 700;
    white-space: nowrap;
    color: var(--pri-ink);
    background: var(--pri-bg);
  }

  .options {
    display: flex;
    gap: 6px;
    margin-top: 11px;
  }

  .option {
    flex: 1;
    min-width: 0;
    padding: 8px 7px;
    border-radius: 11px;
    text-align: left;
    color: var(--ink);
    border: 1px solid var(--hair-strong);
    background: transparent;
  }

  .option.on {
    border-color: var(--acc-edge);
    background: var(--acc-soft);
  }

  .option.warn.on {
    border-color: rgb(232 147 90 / 0.55);
    background: rgb(232 147 90 / 0.12);
  }

  .option-label {
    display: block;
    font-size: 11.5px;
    font-weight: 700;
    line-height: 1.25;
  }

  .option.on .option-label {
    color: var(--badge);
  }

  .option.warn.on .option-label {
    color: var(--warn);
  }

  .option-note {
    display: block;
    font-size: 10px;
    color: var(--faint);
    margin-top: 3px;
    line-height: 1.3;
  }

  .mandate {
    margin-top: 11px;
    padding: 9px 10px;
    border-radius: 11px;
    border: 1px solid var(--hair);
    background: var(--trace-bg);
  }

  .mandate-cap {
    font-size: 10.5px;
    color: var(--faint);
  }

  .mandate-none {
    margin: 0;
    color: var(--muted);
    font-size: 12.5px;
  }

  .mandate-text {
    font-size: 11.5px;
    line-height: 1.5;
    color: var(--trace-ink);
    margin-top: 4px;
  }

  .hand {
    margin-top: 6px;
    padding-top: 6px;
    border-top: 1px solid var(--hair);
    font-size: 11px;
    line-height: 1.45;
    color: var(--faint);
  }

  .hand.blocked {
    color: var(--risk-ink);
  }

  .confirm {
    width: 100%;
    margin-top: 12px;
    min-height: 52px;
    border-radius: 15px;
    font-size: 15px;
    font-weight: 800;
    color: var(--pri-ink);
    background: var(--pri-bg);
  }

  .confirm:disabled {
    opacity: 0.45;
  }

  .outro {
    font-size: 12px;
    color: var(--faint);
    margin-top: 16px;
    line-height: 1.5;
  }

  .bottom-dock {
    position: sticky;
    bottom: 0;
    z-index: 15;
    margin: 20px -16px -40px;
    padding: 14px 16px calc(14px + env(safe-area-inset-bottom, 0px));
    border-top: 1px solid var(--hair);
  }

  .remember {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    color: var(--ink);
    cursor: pointer;
  }

  .remember-note {
    margin: 5px 0 0 26px;
    font-size: 11.5px;
    color: var(--muted);
  }

  .consent {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-top: 13px;
    font-size: 12.5px;
    line-height: 1.35;
    color: var(--ink);
    cursor: pointer;
  }

  .why-blocked {
    margin-top: 6px;
    font-size: 11.5px;
    line-height: 1.35;
    text-align: center;
    color: var(--warn);
  }

  .saved {
    margin-top: 20px;
  }

  .saved h3 {
    margin: 0 0 8px;
    font-size: 13px;
    color: var(--muted);
    font-weight: 600;
  }

  .saved ul {
    margin: 0;
    padding: 0;
    list-style: none;
    display: grid;
    gap: 6px;
  }

  .saved li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    font-size: 12.5px;
    color: var(--muted);
    border: 1px solid var(--hair);
    border-radius: 10px;
    padding: 6px 10px;
  }

  .saved button {
    border: 0;
    background: transparent;
    color: var(--muted);
    font: inherit;
    cursor: pointer;
    padding: 0 2px;
  }

  .saved button:disabled {
    opacity: 0.5;
    cursor: default;
  }

  @media (width <= 380px) {
    .swaps {
      padding-inline: 12px;
    }

    h1 {
      font-size: 21px;
    }

    .options {
      flex-direction: column;
    }

    .option-note {
      display: inline;
      margin-inline-start: 6px;
    }
  }
  .reveal {
    width: 100%;
    margin: 4px 0 12px;
    padding: 12px 14px;
    border-radius: 14px;
    border: 1px dashed var(--hair-strong);
    background: transparent;
    font: inherit;
    font-weight: 700;
    color: inherit;
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
