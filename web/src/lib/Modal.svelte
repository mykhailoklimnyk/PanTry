<script lang="ts">

  import type { Snippet } from 'svelte'

  interface Props {
    label: string
    children: Snippet
  }

  const { label, children }: Props = $props()
</script>

<div class="scrim" aria-hidden="true"></div>
<div class="sheet" role="dialog" aria-modal="true" aria-label={label}>
  <div class="box">
    {@render children()}
  </div>
</div>

<style>
  .scrim {
    position: fixed;
    inset: 0;
    z-index: 70;
    background: rgb(0 0 0 / 0.5);
    touch-action: none;
  }

  .sheet {
    position: fixed;
    z-index: 71;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: min(360px, calc(100vw - 32px));
    border-radius: 16px;
    box-shadow: 0 24px 60px rgb(0 0 0 / 0.5);
  }

  .box {
    padding: 14px;
    border-radius: 16px;
    border: 1px solid var(--hair-strong);
    background: var(--menu-bg);
  }

  @media (width <= 380px) {
    .sheet {
      width: calc(100vw - 24px);
    }
  }
</style>
