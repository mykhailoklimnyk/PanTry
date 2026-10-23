<script lang="ts">
  interface Props {
    size?: number
  }

  const { size = 22 }: Props = $props()
</script>

<img class="mark" src="/logo-mark.png" width={size} height={size} alt="" aria-hidden="true" />

<style>
  .mark {
    display: block;
    object-fit: contain;
  }
</style>
