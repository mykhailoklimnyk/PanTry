<script lang="ts">
  import { PANTRY_PHASES } from './ui'

  interface Props {
    since: number
  }

  const { since }: Props = $props()

  let clock = $state(Date.now())

  $effect(() => {
    const tick = setInterval(() => (clock = Date.now()), 300)
    return () => clearInterval(tick)
  })

  const elapsed = $derived(clock - since)
  const step = $derived(
    [...PANTRY_PHASES].reverse().find((phase) => elapsed >= phase.after) ?? PANTRY_PHASES[0],
  )
  const last = $derived(step === PANTRY_PHASES[PANTRY_PHASES.length - 1])
</script>

<p class="phase" aria-live="polite" data-wait="pantry" data-step={step.id}>{step.label}</p>
<p class="call mono">{step.call}</p>
{#if last}
  <p class="note">перший раз довше — назви видів рахує модель, далі вони вже відомі</p>
{/if}

<style>
  .phase {
    margin-top: 9px;
    font-size: 12.5px;
    font-weight: 600;
    color: var(--muted);
    line-height: 1.45;
  }

  .call {
    margin-top: 2px;
    font-size: 11px;
    color: var(--faint);
  }

  .note {
    margin-top: 4px;
    font-size: 11.5px;
    color: var(--faint);
    line-height: 1.45;
  }
</style>
