<script lang="ts">
  import { brandHtml } from '../ui'
  import Back from '../Back.svelte'
  import type { DocId } from '../navigation'
  import { PAGES, type ItemState } from '../pages'

  interface Props {
    id: DocId
    /** Куди веде «назад» — підпис із самого шляху, а не «Назад» узагалі. */
    label: string
    onBack: () => void
  }

  const { id, label, onBack }: Props = $props()

  const page = $derived(PAGES[id])

  const LABELS: Record<Exclude<ItemState, null>, string> = {
    done: 'працює',
    now: 'зараз',
    next: 'далі',
    no: 'не робимо',
  }
</script>

<div class="doc">
  <div class="top">
    <Back {label} onClick={onBack} />
    <h1>{page.title}</h1>
  </div>

  <p class="lede">{page.lede}</p>

  {#each page.sections as section (section.title)}
    <section>
      <h2>{section.title}</h2>
      <ul>
        {#each section.items as item (item.label)}
          <li>
            <div class="head">
              <span class="label">{item.label}</span>
              {#if item.state}
                <span class="state {item.state}">{LABELS[item.state]}</span>
              {/if}
            </div>
            {#if item.note}
              <p class="note">{@html brandHtml(item.note)}</p>
            {/if}
            {#if item.link}
              <a
                class="out"
                href={item.link.href}
                target="_blank"
                rel="noopener noreferrer"
              >
                {item.link.label} <span aria-hidden="true">↗</span>
              </a>
            {/if}
          </li>
        {/each}
      </ul>
    </section>
  {/each}

  <p class="made">створено для хакатону «Сільпо» AI Factory</p>
</div>

<style>
  .doc {
    padding: 16px 16px 40px;
  }

  .out {
    display: inline-block;
    margin-top: 7px;
    font-size: 12.5px;
    font-weight: 700;
    color: var(--accent);
    text-decoration: underline;
    text-underline-offset: 3px;
  }

  .top {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  h1 {
    font-size: 23px;
    font-weight: 800;
    letter-spacing: -0.7px;
    line-height: 1.2;
  }

  .lede {
    font-size: 14px;
    color: var(--muted);
    margin-top: 9px;
    line-height: 1.55;
  }

  section {
    margin-top: 22px;
  }

  h2 {
    font-size: 12px;
    font-weight: 700;
    color: var(--muted);
  }

  ul {
    margin-top: 9px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  li {
    padding: 12px 13px;
    border-radius: 14px;
    border: 1px solid var(--hair);
    background: var(--list-bg);
  }

  .head {
    display: flex;
    align-items: baseline;
    gap: 9px;
  }

  .label {
    flex: 1;
    font-size: 13.5px;
    font-weight: 700;
    line-height: 1.35;
  }

  .state {
    flex: none;
    padding: 2px 7px;
    border-radius: 999px;
    font-size: 10.5px;
    font-weight: 700;
    white-space: nowrap;
    color: var(--faint);
    border: 1px solid var(--hair-strong);
  }

  .state.done {
    color: var(--good);
    border-color: color-mix(in srgb, var(--good) 45%, transparent);
  }

  .state.now {
    color: var(--badge);
    border-color: var(--acc-edge);
  }

  .state.no {
    color: var(--warn);
    border-color: color-mix(in srgb, var(--warn) 45%, transparent);
  }

  .note {
    font-size: 12px;
    color: var(--muted);
    margin-top: 5px;
    line-height: 1.5;
  }

  .made {
    margin-top: 24px;
    font-size: 11.5px;
    color: var(--faint);
    text-align: center;
  }

  @media (width <= 380px) {
    .doc {
      padding-inline: 12px;
    }

    h1 {
      font-size: 21px;
    }
  }
</style>
