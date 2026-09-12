<script lang="ts">

  import Modal from './Modal.svelte'
  import type { Place, PlaceOption } from './types'

  interface Props {
    /**
     * Поточна адреса. `null` — її ще не прочитали (#253), і саме тоді вікно
     * потрібне найбільше: гість, який не знає своєї адреси, хоче її
     * НАЗВАТИ. До 02.09 вікно на цьому стані просто не відкривалось --
     * тобто дороги не було рівно там, де вона потрібна.
     */
    place: Place | null
    /** Варіанти пошуку. `null` — ще не шукали. */
    results: PlaceOption[] | null
    searching: boolean
    searchNote: string | null
    onSearch: (text: string) => void
    onChoose: (option: PlaceOption) => void
    onClose: () => void
  }

  const { place, results, searching, searchNote, onSearch, onChoose, onClose }: Props = $props()

  let query = $state('')

  function submit(event: SubmitEvent) {
    event.preventDefault()
    onSearch(query)
  }
</script>

<Modal label="Куди веземо">
  {#if place && place.saved.length > 0}
    <div class="caption">адреси з твого акаунта</div>
    <ul class="saved">
      {#each place.saved as option (option.id ?? option.label)}
        <li>
          <button
            class="option"
            class:on={option.label === place?.address}
            type="button"
            onclick={() => onChoose(option)}
          >
            <span class="option-label">{option.label}</span>
            {#if option.tag}<span class="tag">{option.tag}</span>{/if}
          </button>
        </li>
      {/each}
    </ul>
  {/if}

  <form class="find" onsubmit={submit}>
    <input
      class="find-input"
      type="text"
      placeholder="місто, вулиця, будинок"
      bind:value={query}
      aria-label="Адреса доставки"
    />
    <button class="find-go" type="submit" disabled={searching || query.trim() === ''}>
      {searching ? '…' : 'Знайти'}
    </button>
  </form>

  {#if searchNote}
    <p class="note">{searchNote}</p>
  {:else if results !== null && results.length === 0}
    <p class="note">за цим запитом нічого не знайшлось — спробуй інакше</p>
  {:else if results !== null}
    <ul class="found">
      {#each results as option (option.label)}
        <li>
          <button class="option" type="button" onclick={() => onChoose(option)}>
            <span class="option-label">{option.label}</span>
          </button>
        </li>
      {/each}
    </ul>
  {/if}

  <div class="actions">
    <button class="secondary" type="button" onclick={onClose}>Закрити</button>
  </div>
</Modal>

<style>
  .caption {
    font-size: 12px;
    color: var(--muted);
    margin-bottom: 7px;
  }

  .saved,
  .found {
    list-style: none;
    margin: 0 0 10px;
    padding: 0;
    display: grid;
    gap: 6px;
    max-height: 42vh;
    overflow-y: auto;
  }

  .option {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 11px 12px;
    text-align: left;
    font-size: 13.5px;
    color: var(--ink);
    border: 1px solid var(--hair);
    border-radius: 12px;
    background: var(--chip-bg);
  }

  .option.on {
    border-color: var(--acc-edge);
    background: var(--acc-soft);
  }

  .option-label {
    flex: 1;
    min-width: 0;
  }

  .tag {
    flex: none;
    font-size: 11px;
    font-weight: 700;
    color: var(--muted);
  }

  .find {
    display: flex;
    gap: 8px;
    margin-bottom: 10px;
  }

  .find-input {
    flex: 1;
    min-width: 0;
    min-height: 44px;
    padding: 0 12px;
    border-radius: 12px;
    border: 1px solid var(--hair);
    background: var(--chip-bg);
    color: var(--ink);
    font: inherit;
    font-size: 14px;
  }

  .find-go {
    flex: none;
    padding: 0 14px;
    min-height: 44px;
    border-radius: 12px;
    font-size: 13px;
    font-weight: 700;
    color: var(--pri-ink);
    background: var(--pri-bg);
  }

  .find-go:disabled {
    opacity: 0.55;
  }

  .note {
    margin: 0 0 10px;
    font-size: 12.5px;
    line-height: 1.5;
    color: var(--muted);
  }

  .actions {
    display: flex;
    justify-content: flex-end;
  }

  .secondary {
    padding: 10px 14px;
    border-radius: 12px;
    font-size: 13px;
    font-weight: 700;
    color: var(--ink);
    border: 1px solid var(--hair-strong);
    background: var(--chip-bg);
  }
</style>
