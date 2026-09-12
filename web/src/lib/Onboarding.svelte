<script lang="ts">
  import { brandHtml } from './ui'


  interface Props {
    open: boolean
    /** Онбординг закінчився: далі гостя веде App — на екран згоди. */
    onDone: () => void
  }

  const { open, onDone }: Props = $props()

  interface Slide {
    /** Титульний слайд — з повним логотипом; решта — з маскотом. */
    mark?: boolean
    title: string
    text: string
  }

  const SLIDES: Slide[] = [
    {
      mark: true,
      title: 'Знає, що вдома.\nЗамовить, що треба.',
      text: 'Застосунок «Сільпо» бачить твої покупки. Він не бачить, що з них ще лишилось удома — а кошик випливає саме з цього.',
    },
    {
      title: 'Знає, як швидко що закінчується',
      text: "Дивиться на твої чеки — і з магазину, і з доставки. Молоко закінчується за три дні, сіль за пів року, і ПанTry це пам'ятає. Те, що ти брав недавно, важить більше за торішнє.",
    },
    {
      title: 'Домовляється про заміну заздалегідь',
      text: 'Не буде твого сиру — той, хто збирає замовлення, уже знатиме, чим його замінити: ти дозволив це наперед. Ніхто не дзвонитиме з магазину з питанням «брати інший?».',
    },
    {
      title: 'Далі — твій акаунт',
      text: 'Щоб знати саме твій дім, ПанTry потрібні твої покупки — а вони в акаунті «Сільпо». Вхід відбувається на їхньому боці, пароля ми не бачимо. На наступному екрані видно, що саме він читає.',
    },
  ]

  let index = $state(0)
  const last = $derived(index === SLIDES.length - 1)
  const slide = $derived(SLIDES[index]!)

  function next() {
    if (last) {
      onDone()
      return
    }
    index += 1
  }

  function prev() {
    if (index > 0) index -= 1
  }

  let touchX = 0
  let touchY = 0

  function onTouchStart(event: TouchEvent) {
    touchX = event.changedTouches[0]?.clientX ?? 0
    touchY = event.changedTouches[0]?.clientY ?? 0
  }

  function onTouchEnd(event: TouchEvent) {
    const dx = (event.changedTouches[0]?.clientX ?? 0) - touchX
    const dy = (event.changedTouches[0]?.clientY ?? 0) - touchY
    if (Math.abs(dx) < 40 || Math.abs(dx) < Math.abs(dy)) return
    if (dx < 0) next()
    else prev()
  }

  $effect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'ArrowRight') next()
      else if (event.key === 'ArrowLeft') prev()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })
</script>

{#if open}
  <div
    class="onboarding"
    role="dialog"
    aria-modal="true"
    aria-label="Про ПанTry"
    tabindex="-1"
    ontouchstart={onTouchStart}
    ontouchend={onTouchEnd}
  >
    <div class="col">
      <div class="top">
        <div class="dots" role="tablist" aria-label="Слайди">
          {#each SLIDES as item, i (item.title)}
            <button
              class="dot"
              class:on={i === index}
              type="button"
              role="tab"
              aria-selected={i === index}
              aria-label={`Слайд ${i + 1}: ${item.title.replace('\n', ' ')}`}
              onclick={() => (index = i)}
            ></button>
          {/each}
        </div>
        <button class="skip" type="button" onclick={onDone}>пропустити</button>
      </div>

      <div class="stage">
        {#key index}
          <article class="slide">
            {#if slide.mark}
              <img class="hero" src="/logo.png" alt="ПанTry" width="240" height="240" />
            {:else}
              <img class="mascot" src="/logo-mark.png" alt="" aria-hidden="true" width="108" height="108" />
            {/if}
            <h1>{slide.title}</h1>
            <p class="text">{@html brandHtml(slide.text)}</p>
          </article>
        {/key}
      </div>

      <div class="dock">
        <button class="go" type="button" onclick={next}>Далі</button>
        <p class="foot">створено для хакатону «Сільпо» AI Factory</p>
      </div>
    </div>
  </div>
{/if}

<style>
  .onboarding {
    position: fixed;
    inset: 0;
    z-index: 65;
    display: flex;
    justify-content: center;
    background: var(--app-bg);
  }

  .col {
    width: 100%;
    max-width: var(--col);
    height: 100dvh;
    display: flex;
    flex-direction: column;
    padding: 18px 22px 0;
  }

  .top {
    display: flex;
    align-items: center;
    gap: 12px;
    flex: none;
  }

  .dots {
    display: flex;
    gap: 6px;
    flex: 1;
  }

  .dot {
    width: 22px;
    height: 24px;
    display: grid;
    place-items: center;
    background: transparent;
  }

  .dot::after {
    content: '';
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--hair-strong);
    transition: width 0.2s ease, background 0.2s ease;
  }

  .dot.on::after {
    width: 20px;
    border-radius: 4px;
    background: var(--pri-bg);
  }

  .skip {
    flex: none;
    padding: 6px 8px;
    font-size: 12px;
    font-weight: 700;
    color: var(--faint);
    background: transparent;
  }

  .stage {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    overflow-x: clip;
    display: flex;
    flex-direction: column;
    padding: 18px 0;
  }

  .slide {
    margin-block: auto;
    animation: slide-in 0.26s ease;
  }

  @keyframes slide-in {
    from {
      opacity: 0;
      translate: 14px 0;
    }
    to {
      opacity: 1;
      translate: 0 0;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .slide {
      animation: none;
    }
  }

  .hero {
    width: min(260px, 64vw);
    height: auto;
    display: block;
    margin: 0 auto 6px;
  }

  .mascot {
    width: 108px;
    height: 108px;
    display: block;
  }

  h1 {
    margin-top: 20px;
    font-size: clamp(26px, 7.4vw, 33px);
    font-weight: 800;
    letter-spacing: -1.2px;
    line-height: 1.12;
    white-space: pre-line;
    text-wrap: balance;
  }

  .text {
    margin-top: 14px;
    font-size: 14.5px;
    line-height: 1.55;
    color: var(--muted);
  }

  .dock {
    flex: none;
    margin: 0 -22px;
    padding: 12px 22px calc(12px + env(safe-area-inset-bottom, 0px));
    border-top: 1px solid var(--hair);
    background: var(--glass-bg);
    backdrop-filter: blur(22px) saturate(160%);
  }

  .go {
    width: 100%;
    padding: 16px;
    border-radius: 16px;
    font-size: clamp(16px, 4.4vw, 17.5px);
    font-weight: 800;
    color: var(--pri-ink);
    background: var(--pri-bg);
    box-shadow: 0 10px 26px rgb(240 169 59 / 0.3);
  }

  .foot {
    margin: 10px 0 0;
    text-align: center;
    font-size: 11px;
    color: var(--faint);
  }

  @media (width <= 380px) {
    .col {
      padding-inline: 16px;
    }

    .dock {
      margin-inline: -16px;
      padding-inline: 16px;
    }
  }
</style>
