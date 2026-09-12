<script lang="ts">
  import PlacePicker from './PlacePicker.svelte'
  import type { Place, PlaceOption } from './types'

  interface Props {
    /** `null` — ще вантажиться: замість рядка стоїть скелет тих самих розмірів. */
    place: Place | null
    /** Відмова читання — приміткою в секції, а не банером на весь екран. */
    note: string | null
    /** Варіанти пошуку. `null` — ще не шукали. */
    results: PlaceOption[] | null
    searching: boolean
    searchNote: string | null
    onSearch: (text: string) => void
    onChoose: (option: PlaceOption) => void
  }

  const { place, note, results, searching, searchNote, onSearch, onChoose }: Props = $props()

  let open = $state(false)

  let asked = $state(false)
  const unknown = $derived(place !== null && place.address === null)
  const editing = $derived(open || (unknown && !asked))

  function choose(option: PlaceOption) {
    open = false
    asked = true
    onChoose(option)
  }
</script>

<section class="block" data-tour="place">
  <div class="caption">куди веземо</div>

  {#if place === null && note !== null}
    <div class="row warn">
      <span class="pin" aria-hidden="true">📍</span>
      <span class="body">
        <span class="label">Куди веземо — не знаю</span>
        <span class="state">{note}</span>
      </span>
    </div>
  {:else if place === null}
    <div class="row" aria-hidden="true">
      <span class="pin sk"></span>
      <span class="body">
        <span class="sk-line" style:width="58%"></span>
        <span class="sk-line" style:width="40%"></span>
      </span>
    </div>
  {:else}
    <button
      class="row"
      class:warn={place.source !== 'address'}
      type="button"
      aria-expanded={editing}
      onclick={() => (open = !open)}
    >
      <span class="pin" aria-hidden="true">📍</span>
      <span class="body">
        <span class="label">{place.address ?? 'Адресу ще не знаю'}</span>
        <span class="state">
          {place.branch ? `збирає ${place.branch}` : place.note}
        </span>
      </span>
      <span class="change"
        >{editing ? 'згорнути' : place.address ? 'змінити' : 'назвати адресу'}</span
      >
    </button>

    {#if place.branch}
      <p class="note" class:warn-note={place.source !== 'address'}>{place.note}</p>
    {/if}
  {/if}

  {#if note && place !== null}
    <p class="note">{note}</p>
  {/if}

  {#if editing && place !== null}
    <PlacePicker
      {place}
      {results}
      {searching}
      {searchNote}
      {onSearch}
      onChoose={choose}
      onClose={() => {
        open = false
        asked = true
      }}
    />
  {/if}
</section>

<style>
  .block {
    margin-top: 16px;
  }

  .caption {
    font-size: 12px;
    color: var(--muted);
    margin-bottom: 7px;
  }

  .row {
    display: flex;
    align-items: center;
    gap: 11px;
    width: 100%;
    padding: 10px 12px;
    text-align: left;
    border: 1px solid var(--hair);
    border-radius: 16px;
    background: var(--list-bg);
    color: var(--ink);
  }

  .row.warn {
    border-color: var(--warn);
  }

  .pin {
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

  .body {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-width: 0;
  }

  .label {
    font-size: 13px;
    font-weight: 700;
    line-height: 1.25;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .state {
    margin-top: 2px;
    font-size: 11.5px;
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .change {
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

  .warn-note {
    color: var(--warn);
  }

  .pin.sk,
  .sk-line {
    animation: sk-pulse 1.2s ease-in-out infinite;
  }

  .sk-line {
    height: 12px;
    border-radius: 6px;
    background: var(--chip-bg);
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
</style>
