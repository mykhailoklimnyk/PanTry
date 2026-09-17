<script lang="ts">
  import Back from '../Back.svelte'
  import CloseDock from '../CloseDock.svelte'
  import { BAR_GROUPS, BUILD_MODES, NO_PHOTO, barDroppedNote, barEmptyNote } from '../ui'
  import { amount, plural, uahRound } from '../format'
  import type {
    Bar,
    BarItem,
    BuildRequest,
    CartLine,
    DrinkKind,
    ProductPick,
  } from '../types'

  interface Props {
    /** Бар І те, з чого він порахований. `null` — ще не питали. */
    bar: Bar | null
    /** Що вже додано до кошика під привід. */
    added: Set<string>
    /** Кількість доданого. Той самий запис правок, що й у кошику. */
    qty: Record<string, number>
    /** Бар відкрито зі старту: вихід нагорі, бо внизу таби не поможуть. */
    showBack?: boolean
    /** Куди веде вихід — словами. Рахує App: екран не знає, звідки прийшли. */
    backLabel: string
    /** Режим збірки зі старту: саме він робить пораду доречною або зайвою. */
    mode: BuildRequest['mode']
    onAdd: (line: CartLine) => void
    onRemove: (id: string) => void
    onQty: (id: string, next: number) => void
    onMode: (id: BuildRequest['mode']) => void
    /**
     * Чим наповнюється бар: покупками чи самим гостем (#146).
     *
     * Прапорець СВІЙ, не спільний з коморою: алкоголь беруть нерівно і не
     * тільки в «Сільпо», тож вести бар руками і лишити комору на покупках --
     * нормальний стан, а спільний прапорець його забороняв би.
     */
    onSource: (mode: 'receipts' | 'manual') => void
    /** Скласти бар з покупок — явною дією з видимим результатом. */
    onGenerate: () => void
    /** Стерти ВЕСЬ список бару. Комори це не чіпає: області різні. */
    onWipe: () => void
    /** Що зробила остання дія — словами (#245). `null` — дії не було. */
    deed: string | null
    /** Дописати вид руками: «віскі раз на квартал» чеки не бачать. */
    onAddKind: (label: string) => void
    /** Прибрати дописаний рядок. Рядок з покупок так прибрати не можна. */
    onForget: (id: string) => void
    /**
     * Переставити вид на іншу полицю: «це не лікер, це ром» (#261).
     *
     * Групу вгадує модель, і відповідь її лягає у ВІЧНИЙ спільний кеш назв,
     * тож перший здогад замерзає як факт. Слово гостя лежить ПОВЕРХ кешу і
     * важить більше за нього; `null` -- зняти своє слово.
     */
    onGroup: (label: string, kind: DrinkKind | null) => void
    /** Котрась із дій зараз їде на сервер: вони довгі (перерахунок). */
    sourceBusy: boolean
    onBack?: () => void
  }

  const {
    bar,
    added,
    qty,
    showBack = false,
    backLabel,
    mode,
    onAdd,
    onRemove,
    onQty,
    onMode,
    onSource,
    onGenerate,
    onWipe,
    deed,
    onAddKind,
    onForget,
    onGroup,
    sourceBusy,
    onBack,
  }: Props = $props()

  const hasOccasion = $derived(mode === 'event')
  const occasionLabel = $derived(BUILD_MODES.find((m) => m.id === mode)?.label ?? '')

  const KNOWN = BAR_GROUPS.map((group) => group.kind)
  const groups = $derived(
    [
      ...BAR_GROUPS.map((group) => ({
        ...group,
        items: (bar?.items ?? []).filter((item) => item.kind === group.kind),
      })),
      {
        kind: 'said' as const,
        label: 'решта',
        note: 'ти дописав це сам',
        items: (bar?.items ?? []).filter(
          (item) => item.kind === null || !KNOWN.includes(item.kind),
        ),
      },
    ].filter((group) => group.items.length > 0),
  )

  const bySelf = $derived(bar?.source === 'manual')

  let wipeAsked = $state(false)
  let draft = $state('')

  let moving = $state<string | null>(null)

  function moveTo(item: BarItem, kind: DrinkKind | null): void {
    moving = null
    onGroup(item.label, kind)
  }

  const outsideNote = $derived(
    `У покупках є ще ${bar?.unlisted ?? 0} ${
      (bar?.unlisted ?? 0) === 1 ? 'вид' : 'видів'
    }, яких немає у твоєму списку.`,
  )

  function addDraft(): void {
    const label = draft.trim()
    if (!label || sourceBusy) return
    draft = ''
    onAddKind(label)
  }

  const emptyNote = $derived(
    bar && bar.items.length === 0 ? barEmptyNote(bar) : null,
  )

  const droppedNote = $derived(
    bar && bar.items.length > 0 ? barDroppedNote(bar) : null,
  )

  function history(item: BarItem): string {
    if (item.daysSince === null) {
      return 'ти дописав це сам · покупок ще не видно'
    }
    const last =
      item.daysSince === 0
        ? 'сьогодні'
        : item.daysSince === 1
          ? 'учора'
          : `${plural(item.daysSince, { one: 'день', few: 'дні', many: 'днів' })} тому`
    const times = plural(item.times, { one: 'покупка', few: 'покупки', many: 'покупок' })
    return `востаннє ${last} · ${times}`
  }

  function toLine(item: BarItem, usual: ProductPick): CartLine {
    const fork =
      item.priceFrom !== null && item.priceTo !== null
        ? `${amount(item.priceFrom, '')}–${amount(item.priceTo, '₴')}`
        : null
    return {
      externalProductId: usual.externalProductId,
      name: usual.name,
      qty: 1,
      unit: usual.unit,
      step: null,
      price: usual.price,
      basePrice: null,
      saleNote: null,
      weightKg: null,
      imageUrl: null,
      cardUrl: null,
      reason: 'occasion',
      explanation: `${item.label.toLowerCase()} до приводу · ${occasionLabel}`,
      explanationDetail: `Ти обрав вид, бренд підібрав агент: береш саме цю в ${usual.share} випадків. Не буде — візьме той самий вид${fork ? ` за ${fork} (${item.forkNote})` : ''}.`,
      confidence: 1,
      atRisk: false,
      needsApproval: false,
      chain: [],
      mandate: `${item.label}: якщо ${usual.name} немає — той самий вид${fork ? ` за ${fork}` : ''}. Не дзвонити.`,
      mandateAhead: false,
      decided: false,
      swapFork: null,
      considered: [],
      consideredTotal: 0,
      sliced: false,
      slicingNote: null,
    cheaper: null,
    }
  }
</script>

<div class="bar">
  {#if showBack && onBack}
    <div class="top">
      <Back label={backLabel} onClick={onBack} />
      <h1>Бар</h1>
    </div>
  {/if}

  <p class="intro">
    Обираєш вид — пляшку добере агент за твоєю історією. Нового не радить і сам
    у тижневий кошик нічого звідси не кладе.
  </p>

  <div class="occasion">
    <div class="caption">привід</div>
    <div class="chips">
      {#each BUILD_MODES.filter((m) => m.id === 'event') as option (option.id)}
        <button
          class="chip"
          class:on={mode === option.id}
          type="button"
          aria-pressed={mode === option.id}
          onclick={() => onMode(mode === option.id ? 'list' : option.id)}
        >
          {option.label}
        </button>
      {/each}
    </div>
    <p class="note">
      {hasOccasion
        ? `Кількість під ${occasionLabel} підбере агент при збиранні — тут ти обираєш що саме.`
        : 'Без приводу це просто довідка: агент нічого не пропонує.'}
    </p>
  </div>

  {#if bar}
    <div class="source" data-tour="bar-source">
      <div class="modes" role="group" aria-label="чим наповнювати бар">
        <button
          type="button"
          class="mode"
          aria-pressed={!bySelf}
          disabled={sourceBusy}
          onclick={() => onSource('receipts')}
        >
          з покупок
        </button>
        <button
          type="button"
          class="mode"
          aria-pressed={bySelf}
          disabled={sourceBusy}
          onclick={() => onSource('manual')}
        >
          веду сам
        </button>
      </div>

      <div class="deeds">
        <button type="button" class="deed" disabled={sourceBusy} onclick={onGenerate}>
          Скласти з покупок
        </button>
        {#if wipeAsked}
          <button
            type="button"
            class="deed danger"
            disabled={sourceBusy}
            onclick={() => {
              wipeAsked = false
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

      {#if deed}
        <p class="deed-said" role="status">{deed}</p>
      {/if}

      <form
        class="add"
        onsubmit={(event) => {
          event.preventDefault()
          addDraft()
        }}
      >
        <input
          class="field"
          type="text"
          placeholder="віскі, сидр, просекко"
          aria-label="дописати вид у бар"
          bind:value={draft}
          disabled={sourceBusy}
        />
        <button class="deed" type="submit" disabled={sourceBusy || !draft.trim()}>
          + Додати
        </button>
      </form>

      {#if bySelf && (bar.unlisted ?? 0) > 0}
        <p class="outside">
          {outsideNote}
          <button type="button" class="link" disabled={sourceBusy} onclick={onGenerate}>
            Додати їх
          </button>
        </p>
      {/if}
    </div>
  {/if}

  {#if emptyNote}
    <p class="empty">{emptyNote}</p>
  {/if}

  {#if droppedNote}
    <p class="empty">{droppedNote}</p>
  {/if}

  {#each groups as group (group.kind)}
    <section>
      <div class="group-head">
        <h2>{group.label}</h2>
        <span class="group-note">{group.note}</span>
      </div>

      <ul class="list">
        {#each group.items as item (item.id)}
          {@const usual = item.usual}
          {@const inCart = usual ? added.has(usual.externalProductId) : false}
          <li class="row">
            <div class="thumb" aria-hidden="true">
              {NO_PHOTO.drink}
            </div>

            <div class="body">
              <div class="name ellipsis">{item.label}</div>
              <div class="meta ellipsis">{history(item)}</div>
              {#if usual && item.priceFrom !== null && item.priceTo !== null}
                <div class="pick ellipsis">
                  візьме {usual.name}{usual.pack ? ` · ${usual.pack}` : ''} · {usual.share}
                </div>
                <div class="fallback ellipsis" title={item.forkNote}>
                  немає — {item.label.toLowerCase()} за {amount(item.priceFrom, '')}–{amount(
                    item.priceTo,
                    '₴',
                  )} · {item.forkNote}
                </div>
              {:else}
                <div class="fallback ellipsis">
                  покупок цього виду ще не видно — марку і ціну візьму з першої
                </div>
              {/if}

              <button
                class="shelf"
                class:said={item.kindSaid}
                type="button"
                disabled={sourceBusy}
                aria-expanded={moving === item.id}
                aria-label="Змінити полицю для «{item.label}»"
                onclick={() => (moving = moving === item.id ? null : item.id)}
              >
                {item.kindSaid ? 'полицю обрав ти' : 'не та полиця?'}
              </button>

              {#if moving === item.id}
                <div class="shelves" role="group" aria-label="полиця для «{item.label}»">
                  {#each BAR_GROUPS as option (option.kind)}
                    <button
                      class="shelf-chip"
                      class:on={item.kind === option.kind}
                      type="button"
                      disabled={sourceBusy}
                      aria-pressed={item.kind === option.kind}
                      onclick={() => moveTo(item, option.kind)}
                    >
                      {option.label}
                    </button>
                  {/each}
                  {#if item.kindSaid}
                    <button
                      class="shelf-chip"
                      type="button"
                      disabled={sourceBusy}
                      onclick={() => moveTo(item, null)}
                    >
                      здогад агента
                    </button>
                  {/if}
                </div>
              {/if}
            </div>

            {#if usual}
              <div class="right num">{uahRound(usual.price)}</div>
            {/if}

            {#if !usual}
              <button
                class="act"
                type="button"
                disabled={sourceBusy}
                aria-label="Прибрати: {item.label}"
                onclick={() => onForget(item.id)}
              >
                ✕
              </button>
            {:else if inCart}
              {@const count = qty[usual.externalProductId] ?? 1}
              <div class="count">
                <button
                  class="bump"
                  type="button"
                  aria-label="Менше: {item.label}"
                  onclick={() =>
                    count <= 1
                      ? onRemove(usual.externalProductId)
                      : onQty(usual.externalProductId, count - 1)}
                >
                  {count <= 1 ? '×' : '-'}
                </button>
                <span class="count-value num">{amount(count, usual.unit)}</span>
                <button
                  class="bump"
                  type="button"
                  aria-label="Більше: {item.label}"
                  onclick={() => onQty(usual.externalProductId, count + 1)}
                >
                  +
                </button>
              </div>
            {:else}
              <button
                class="act"
                type="button"
                disabled={!hasOccasion}
                title={hasOccasion ? '' : 'спершу вкажи привід'}
                onclick={() => onAdd(toLine(item, usual))}
              >
                Додати
              </button>
            {/if}
          </li>
        {/each}
      </ul>
    </section>
  {/each}

  <p class="outro">
    Вік підтверджено профілем «Сільпо». Історія покупок нікуди не надсилається —
    цикли рахуються там само, де решта чеків.
  </p>

  {#if onBack}
    <CloseDock label={backLabel} onClick={onBack} />
  {/if}
</div>

<style>
  .source {
    display: flex;
    flex-direction: column;
    gap: var(--gap-2, 8px);
    margin: var(--gap-3, 12px) 0 var(--gap-2, 8px);
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
  .link:disabled,
  .field:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .deed-said {
    margin: 6px 0 0;
    font-size: 12px;
    line-height: 1.4;
    color: var(--good);
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

  .deed.danger {
    border-color: var(--danger, var(--hair-strong));
    color: var(--warn);
  }

  .shelf {
    margin-top: 2px;
    padding: 0;
    border: 0;
    background: transparent;
    color: var(--muted);
    font: inherit;
    font-size: 11px;
    text-decoration: underline dotted;
    text-underline-offset: 3px;
    cursor: pointer;
  }

  .shelf.said {
    color: var(--good);
    text-decoration: none;
  }

  .shelves {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 6px;
  }

  .shelf-chip {
    border: 1px solid var(--hair-strong);
    border-radius: var(--radius-pill, 999px);
    background: transparent;
    color: var(--muted);
    padding: 3px 10px;
    font: inherit;
    font-size: 11px;
    cursor: pointer;
  }

  .shelf-chip.on {
    background: var(--acc-soft);
    color: var(--ink);
    font-weight: 600;
  }

  .shelf:disabled,
  .shelf-chip:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .add {
    display: flex;
    gap: var(--gap-2, 8px);
  }

  .field {
    flex: 1;
    min-width: 0;
    border: 1px solid var(--hair-strong);
    border-radius: var(--radius-pill, 999px);
    background: transparent;
    color: var(--ink);
    padding: 6px 14px;
    font: inherit;
    font-size: 0.85rem;
  }

  .outside {
    margin: 0;
    color: var(--muted);
    font-size: 0.85rem;
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

  .bar {
    padding: 16px 16px 0;
    flex: 1;
    display: flex;
    flex-direction: column;
  }

  .intro {
    font-size: 13px;
    color: var(--muted);
    line-height: 1.5;
  }

  .empty {
    margin-top: 14px;
    padding: 12px 13px;
    border: 1px solid var(--hair);
    border-radius: 12px;
    font-size: 13px;
    line-height: 1.5;
    color: var(--muted);
  }

  .occasion {
    margin-top: 14px;
    padding: 12px 13px;
    border-radius: 14px;
    border: 1px solid var(--hair-strong);
    background: var(--chip-bg);
  }

  .caption {
    font-size: 12px;
    color: var(--muted);
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
    margin-top: 9px;
  }

  .chip {
    padding: 0 12px;
    min-height: 44px;
    display: flex;
    align-items: center;
    border-radius: 11px;
    font-size: 13px;
    font-weight: 600;
    white-space: nowrap;
    color: var(--muted);
    border: 1px solid var(--hair-strong);
    background: transparent;
  }

  .chip.on {
    color: var(--badge);
    border-color: var(--acc-edge);
    background: var(--acc-soft);
  }

  .note {
    font-size: 11.5px;
    color: var(--faint);
    margin-top: 9px;
    line-height: 1.45;
  }

  section {
    margin-top: 18px;
  }

  .group-head {
    display: flex;
    align-items: baseline;
    gap: 8px;
    margin-bottom: 9px;
  }

  h2 {
    font-size: 13px;
    font-weight: 800;
    letter-spacing: -0.2px;
  }

  .group-note {
    flex: 1;
    font-size: 11.5px;
    color: var(--faint);
    text-align: right;
  }

  .list {
    border-radius: 18px;
    border: 1px solid var(--hair);
    background: var(--list-bg);
  }

  .row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    border-bottom: 1px solid var(--hair);
  }

  .row:last-child {
    border-bottom: none;
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

  .body {
    flex: 1;
    min-width: 0;
  }

  .name {
    font-size: 14px;
    font-weight: 700;
    letter-spacing: -0.15px;
    line-height: 1.25;
  }

  .meta {
    font-size: 11.5px;
    color: var(--muted);
    margin-top: 2px;
    line-height: 1.3;
  }

  .pick {
    font-size: 11px;
    color: var(--badge);
    margin-top: 2px;
    line-height: 1.3;
  }

  .fallback {
    font-size: 10.5px;
    color: var(--faint);
    margin-top: 1px;
    line-height: 1.3;
  }

  .right {
    flex: none;
    font-size: 12.5px;
    font-weight: 700;
    white-space: nowrap;
  }

  .act {
    flex: none;
    min-height: 40px;
    padding: 0 11px;
    border-radius: 10px;
    font-size: 12.5px;
    font-weight: 700;
    white-space: nowrap;
    color: var(--ink);
    border: 1px solid var(--hair-strong);
    background: var(--chip-bg);
  }

  .act:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .count {
    display: flex;
    align-items: center;
    gap: 4px;
    flex: none;
    padding: 0 4px;
    border-radius: 10px;
    border: 1px solid var(--acc-edge);
    background: var(--acc-soft);
  }

  .bump {
    width: 28px;
    min-height: 38px;
    display: grid;
    place-items: center;
    font-size: 15px;
    font-weight: 700;
    line-height: 1;
    color: var(--badge);
  }

  .count-value {
    min-width: 42px;
    text-align: center;
    font-size: 12.5px;
    font-weight: 700;
    color: var(--badge);
  }

  .top {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 14px;
  }

  h1 {
    font-size: 23px;
    font-weight: 800;
    letter-spacing: -0.7px;
    line-height: 1.2;
  }

  .outro {
    font-size: 11.5px;
    color: var(--faint);
    margin-top: 16px;
    line-height: 1.5;
  }

  @media (width <= 380px) {
    .bar {
      padding-inline: 12px;
    }

    .row {
      gap: 8px;
      padding: 8px 10px;
    }

    .right {
      font-size: 12px;
    }

    .act {
      padding: 0 9px;
      font-size: 12px;
    }
  }
</style>
