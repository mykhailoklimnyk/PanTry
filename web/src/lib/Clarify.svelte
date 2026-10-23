<script lang="ts">
  import { uah } from './format'
  import type { Clarification, ClarifyAnswer, ClarifyOption, ClarifyPick } from './types'

  interface Props {
    question: Clarification
    onAnswer: (answer: ClarifyAnswer) => void
    onPick: (pick: ClarifyPick) => void
    busy?: boolean
    chosen?: string | null
    reasked?: boolean
  }

  const {
    question,
    onAnswer,
    onPick,
    busy = false,
    chosen = null,
    reasked = false,
  }: Props = $props()

  let other = $state('')
  let writing = $state(false)

  function priceNote(price: number | null, byWeight: boolean): string {
    if (price === null) return ''
    return byWeight ? `від ${uah(price)}/кг` : `від ${uah(price)}`
  }

  function exactPrice(pick: ClarifyPick): string {
    return pick.byWeight ? `${uah(pick.price)}/кг` : uah(pick.price)
  }

  function sendOther() {
    const text = other.trim()
    if (!text || busy) return
    onAnswer({ intent: question.intent, slug: null, query: null, text, skip: false })
  }

  function key(option: ClarifyOption): string {
    return option.slug || (option.query ?? '')
  }
</script>

<div class="ask glass" data-tour="ask">
  <p class="head">
    <span class="mark" aria-hidden="true">?</span>
    <strong>{question.intent}</strong>
  </p>
  {#if reasked}
    <p class="reasked">Відповідь дійшла, але агент перепитав:</p>
  {/if}
  <p class="text">{question.question}</p>

  <ul class="options">
    {#each question.options as option (key(option))}
      <li>
        <button
          type="button"
          class="option"
          class:waiting={busy && chosen === key(option)}
          disabled={busy}
          onclick={() =>
            onAnswer({
              intent: question.intent,
              slug: option.slug || null,
              query: option.query,
              text: null,
              skip: false,
            })}
        >
          <span class="title">{option.title}</span>
          {#if busy && chosen === key(option)}
            <span class="wait">шукаю…</span>
          {:else if option.priceFrom !== null}
            <span class="price">{priceNote(option.priceFrom, option.byWeight)}</span>
          {/if}
        </button>
      </li>
    {/each}
  </ul>

  {#if question.picks.length > 0}
    <ul class="options picks">
      {#each question.picks as pick (pick.externalProductId)}
        <li>
          <button
            type="button"
            class="option"
            disabled={busy}
            onclick={() => onPick(pick)}
          >
            <span class="title">
              {pick.name}
              {#if pick.ratio}<span class="ratio">{pick.ratio}</span>{/if}
            </span>
            <span class="price exact">{exactPrice(pick)}</span>
          </button>
        </li>
      {/each}
    </ul>
    <p class="note picked-note">
      Дотик додає цей товар у кошик — перезбирати нічого не треба
    </p>
  {/if}

  <div class="aside">
    {#if busy && chosen !== null && !question.options.some((option) => key(option) === chosen)}
      <span class="wait">«{chosen}» — шукаю…</span>
    {:else if writing}
      <form
        class="other"
        onsubmit={(event) => {
          event.preventDefault()
          sendOther()
        }}
      >
        <!-- svelte-ignore a11y_autofocus -->
        <input
          type="text"
          autofocus
          bind:value={other}
          placeholder="напиши, що саме"
          aria-label="Інший варіант"
        />
        <button type="submit" class="chip send" disabled={busy || !other.trim()}>Ок</button>
      </form>
    {:else}
      <button type="button" class="chip" disabled={busy} onclick={() => (writing = true)}>
        інше
      </button>
    {/if}
    <button
      type="button"
      class="chip"
      disabled={busy}
      onclick={() =>
        onAnswer({ intent: question.intent, slug: null, query: null, text: null, skip: true })}
    >
      не треба
    </button>
  </div>

  <p class="note">
    {busy
      ? 'Шукаю під твою відповідь — це секунди, не перезбірка'
      : 'Поки не відповіси — позиція в кошик не їде і в суму не входить'}
  </p>
</div>

<style>
  .ask {
    margin: 14px 16px 0;
    padding: 14px;
    border-radius: 18px;
    border: 1px solid rgb(122 162 247 / 0.5);
  }

  .head {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 0 0 4px;
    font-size: 14px;
  }

  .mark {
    display: grid;
    place-items: center;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: rgb(122 162 247 / 0.22);
    color: var(--accent);
    font-size: 12px;
    font-weight: 700;
  }

  .text {
    margin: 0 0 10px;
    font-size: 13px;
    line-height: 1.45;
    color: var(--muted);
  }

  .options {
    display: grid;
    gap: 6px;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .option {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 10px;
    width: 100%;
    min-height: 44px;
    padding: 9px 12px;
    border-radius: 12px;
    text-align: left;
    border: 1px solid var(--hair-strong);
    background: var(--chip-bg);
    color: var(--ink);
    font: inherit;
    font-size: 13px;
    cursor: pointer;
  }

  .option:hover {
    border-color: var(--accent);
  }

  .title {
    min-width: 0;
  }

  .price {
    flex: none;
    font-size: 11.5px;
    white-space: nowrap;
    color: var(--muted);
  }

  .price.exact {
    color: var(--ink);
    font-weight: 600;
  }

  .ratio {
    margin-left: 6px;
    font-size: 11.5px;
    color: var(--muted);
  }

  .picks {
    margin-top: 8px;
  }

  .picked-note {
    margin-top: 6px;
  }

  .aside {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    margin-top: 10px;
    padding-top: 10px;
    border-top: 1px solid var(--hair);
  }

  .chip {
    min-height: 40px;
    padding: 7px 14px;
    border-radius: 999px;
    border: 1px solid var(--hair-strong);
    background: transparent;
    color: var(--muted);
    font: inherit;
    font-size: 13px;
    cursor: pointer;
  }

  .chip:hover {
    border-color: var(--accent);
  }

  .other {
    flex: 1;
    display: flex;
    gap: 6px;
    min-width: 0;
  }

  .other input {
    flex: 1;
    min-width: 0;
    min-height: 40px;
    padding: 7px 12px;
    border-radius: 999px;
    border: 1px solid var(--accent);
    background: var(--chip-bg);
    color: var(--ink);
    font: inherit;
    font-size: 13px;
  }

  .send {
    flex: none;
  }

  .chip:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .option:disabled {
    opacity: 0.55;
    cursor: default;
  }

  .option.waiting {
    opacity: 1;
    border-color: var(--accent);
  }

  .wait {
    flex: none;
    font-size: 11.5px;
    white-space: nowrap;
    color: var(--accent);
  }

  .reasked {
    margin: 0 0 4px;
    font-size: 12px;
    color: var(--accent);
  }

  .note {
    margin: 10px 0 0;
    font-size: 11.5px;
    color: var(--faint);
  }
</style>
