<script lang="ts">
  interface Props {
    label: string
    onClick: () => void
  }

  const { label, onClick }: Props = $props()
</script>

<button class="back" type="button" title={label} aria-label={label} onclick={onClick}>
  <svg
    width="18"
    height="18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path d="M15 5 8 12l7 7" />
  </svg>
</button>

<style>
  .back {
    width: 38px;
    height: 38px;
    flex: none;
    display: grid;
    place-items: center;
    border-radius: 12px;
    color: var(--ink);
    border: 1px solid var(--hair-strong);
    background: var(--chip-bg);
    transition: background-color 120ms ease, border-color 120ms ease;
  }

  .back:hover {
    border-color: var(--acc-edge);
    background: var(--acc-soft);
  }
</style>
