<script lang="ts">
  interface Props {
    onKey: (key: string) => Promise<string | null>
  }

  const { onKey }: Props = $props()

  let draft = $state('')
  let fail = $state<string | null>(null)
  let busy = $state(false)

  async function save() {
    if (busy || !draft.trim()) return
    busy = true
    fail = await onKey(draft.trim())
    busy = false
    if (fail === null) draft = ''
  }
</script>

<div class="keyrow">
  <input
    type="password"
    autocomplete="off"
    placeholder="sk-..."
    bind:value={draft}
    aria-label="Ключ OpenAI"
    onkeydown={(event) => {
      if (event.key === 'Enter') void save()
    }}
  />
  <button type="button" disabled={busy} onclick={() => void save()}>
    {busy ? '…' : 'Зберегти'}
  </button>
</div>
{#if fail}
  <p class="keyfail">{fail}</p>
{/if}
<p class="keynote">
  Ключ лишається в цьому браузері — у нас його немає ні в базі, ні в логах.
  Прогін на ньому платиш ти.
</p>

<style>
  .keyrow {
    display: flex;
    gap: 6px;
    padding: 4px 8px 6px;
  }
  .keyrow input {
    flex: 1;
    min-width: 0;
    padding: 6px 8px;
    border: 1px solid var(--hair-strong);
    border-radius: 8px;
    background: var(--chip-bg);
    color: var(--ink);
    font: inherit;
    font-size: 12px;
  }
  .keyrow button {
    padding: 6px 10px;
    border: 0;
    border-radius: 8px;
    background: var(--pri-bg);
    color: var(--pri-ink);
    font: inherit;
    font-size: 12px;
    cursor: pointer;
  }
  .keyrow button:disabled {
    opacity: 0.6;
    cursor: default;
  }
  .keyfail {
    margin: 0 8px 4px;
    font-size: 11px;
    color: var(--warn);
  }
  .keynote {
    margin: 0 8px 6px;
    font-size: 11px;
    line-height: 1.35;
    color: var(--muted);
  }
</style>
