<script lang="ts">

  interface Props {
    active?: boolean
    label?: string
    onClick: () => void
  }

  const { active = false, label = 'надиктувати', onClick }: Props = $props()
</script>

<button
  class="mic"
  class:live={active}
  type="button"
  aria-pressed={active}
  aria-label={label}
  title={label}
  onclick={onClick}
>
  <svg
    width="15"
    height="15"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <rect x="9" y="2" width="6" height="12" rx="3" />
    <path d="M5 10v1a7 7 0 0 0 14 0v-1" />
    <line x1="12" y1="18" x2="12" y2="22" />
  </svg>
</button>

<style>
  .mic {
    width: 36px;
    min-height: 36px;
    flex: none;
    display: grid;
    place-items: center;
    border-radius: 10px;
    color: var(--muted);
    border: 1px solid var(--hair-strong);
    background: var(--chip-bg);
  }

  .mic.live {
    color: var(--badge);
    border-color: var(--acc-edge);
    background: var(--acc-soft);
    animation: mic-pulse 1.6s ease-in-out infinite;
  }

  @keyframes mic-pulse {
    0%,
    100% {
      box-shadow: 0 0 0 0 var(--acc-half);
    }
    50% {
      box-shadow: 0 0 0 6px rgb(240 169 59 / 0);
    }
  }
</style>
