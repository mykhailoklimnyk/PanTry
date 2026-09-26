<script lang="ts">

  interface Props {
    label: string
    onClick: () => void
  }

  const { label, onClick }: Props = $props()
</script>

<div class="dock">
  <button type="button" onclick={onClick}>{label}</button>
</div>

<style>
  .dock {
    position: sticky;
    bottom: 0;
    z-index: 2;
    margin: auto -16px 0;
    padding: 16px 16px calc(12px + env(safe-area-inset-bottom, 0px));
    border-top: 1px solid var(--hair);
    background: var(--glass-bg);
    backdrop-filter: blur(22px) saturate(160%);
  }

  button {
    width: 100%;
    min-height: 48px;
    border-radius: 14px;
    font-size: 14.5px;
    font-weight: 700;
    color: var(--ink);
    border: 1px solid var(--hair-strong);
    background: var(--chip-bg);
  }
</style>
