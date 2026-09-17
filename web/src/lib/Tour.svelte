<script lang="ts">
  import { brandHtml } from './ui'

  interface Props {
    open: boolean
    onClose: () => void
  }

  const { open, onClose }: Props = $props()

  interface Step {
    /** Значення `data-tour` на елементі. */
    id: string
    title: string
    text: string
  }

  const STEPS: Step[] = [
    {
      id: 'link',
      title: 'Твій акаунт «Сільпо»',
      text: 'ПанTry дивиться в нього, щоб знати, що ти зазвичай береш. Натисни — побачиш, що саме він там читає, і зможеш відключити будь-коли.',
    },
    {
      id: 'pantry-list',
      title: 'Що вдома і коли закінчиться',
      text: 'Кожен рядок — вид, який ти береш регулярно. Смуга показує, скільки ще лишилось, і день, коли воно закінчиться, порахований з твоїх чеків. Рядок без смуги береться нерівно, і ПанTry каже це словами замість вигаданого числа. Натисни рядок: «вже купив», «лишилось дві», «сховати».',
    },
    {
      id: 'pantry-asked',
      title: 'Коли ПанTry не знає',
      text: 'Про види, які беруть нерівно, агент питає тебе: як часто це потрібно. Одна відповідь пояснює й сусідні види, а рядок дістає смугу з твоїх слів.',
    },
    {
      id: 'pantry-rail',
      title: 'Відділи',
      text: 'Рейка ріже список за відділами «Сільпо», не міняючи порядку: те, що закінчується, лишається зверху.',
    },
    {
      id: 'pantry-add',
      title: 'Дописати руками',
      text: 'Вид, а не марку: «гречка», «олія». Або наговори. Дописане живе під твоїм акаунтом, а щойно чеки почнуть вести цей вид, за нього говоритиме цикл.',
    },
    {
      id: 'pantry',
      title: 'Що вдома зараз',
      text: "ПанTry пам'ятає, як часто ти щось купуєш, і рахує, коли воно закінчиться. Звідси й береться кошик — тому цей рядок стоїть першим.",
    },
    {
      id: 'week',
      title: 'Звідки брати кошик',
      text: '«На тиждень» — з того, що вдома закінчується, і до названої суми. «Подія» — стіл на гостей: тут Комора перебере список наново, бо чогось треба більше, а чогось цього разу не треба зовсім. «Зі списку» — тільки те, що ти записав сам.',
    },
    {
      id: 'place',
      title: 'Куди веземо',
      text: 'Від адреси залежить магазин, який збирає замовлення, — а від нього ціни, наявність і час доставки. ПанTry бере адресу з твого акаунта «Сільпо»; якщо там її ще немає, спитає один раз.',
    },
    {
      id: 'delivery',
      title: 'Як забиратимеш',
      text: 'Від цього залежить і ціна доставки, і скільки можна замовити, і навіть що покласти в кошик. Умови показані ті, що діють у «Сільпо» просто зараз.',
    },
    {
      id: 'rules',
      title: 'Твої правила і дозвіл на заміну',
      text: '«Без свинини», «менше цукру» — пиши так, як сказав би вголос: ПанTry не просто викине ці товари, а підбере, чим їх замінити. Тут же вирішуєш, чи можна міняти без питань, чи спершу спитати тебе.',
    },
    {
      id: 'list',
      title: 'Просто перелічи, що треба',
      text: '«Молоко, хліб» — цього досить. Яку саме марку і скільки, ПанTry знає з твоїх попередніх покупок. Можна не писати, а сказати вголос.',
    },
    {
      id: 'run',
      title: 'Одна кнопка — і кошик готовий',
      text: 'ПанTry перевірить, чи все є в наявності, домовиться про заміни на випадок, якщо чогось не стане, порахує суму і підбере час доставки. Чому взяв саме це — розкаже потім у кожному рядку.',
    },
    {
      id: 'from-cart',
      title: 'Уже маєш кошик?',
      text: 'Неважливо, хто його зібрав — ти, помічник «Сільпо» чи повтор минулого замовлення. ПанTry його перевірить і доведе до дверей.',
    },
    {
      id: 'pantry-why',
      title: 'Звідки ПанTry це взяв',
      text: 'Тут видно, як саме порахований твій дім: скільки чеків прочитано, які види він веде і чому. Числа ті самі, що в рядках поруч, — нічого «приблизно» тут немає.',
    },
    {
      id: 'pantry-source',
      title: 'Хто веде цей список',
      text: 'За замовчуванням список рахується з твоїх покупок сам. Можна взяти його на себе — тоді залишаться тільки ті рядки, які ти впишеш, а Комора й далі рахуватиме, коли вони закінчаться.',
    },
    {
      id: 'lines',
      title: 'Кожен рядок пояснює себе',
      text: 'Під назвою написано, чому воно тут: коли ця покупка була востаннє і як часто повторюється. Якщо це не так — скажи «ще є вдома» або «закінчилось раніше», і Комора перерахує кошик.',
    },
    {
      id: 'swaps',
      title: 'Якщо чогось не буде',
      text: 'Замість дзвінка від збирача — домовленість наперед: чим саме заміняти, а чим не треба. Збирач побачить це біля позиції, коли стоятиме перед полицею.',
    },
    {
      id: 'refill',
      title: 'Решта тижня',
      text: 'Те, що вже мало б закінчитись, але не влізло в звичний розмір кошика. Тут видно, скільки це приблизно коштує і скільки лишається до твоєї межі — і можна докинути одним дотиком.',
    },
    {
      id: 'checkout',
      title: 'Оплачуєш ти сам',
      text: 'ПанTry складе кошик у твоєму акаунті «Сільпо» і відкриє його оформлення. Замовлення підтверджуєш і оплачуєш ти — за тебе цього ніхто не зробить.',
    },
  ]

  let steps = $state<Step[]>([])
  let index = $state(0)

  interface Box {
    top: number
    left: number
    width: number
    height: number
  }

  let box = $state<Box | null>(null)

  const step = $derived(steps[index] ?? null)
  const last = $derived(index >= steps.length - 1)

  function target(id: string): HTMLElement | null {
    return document.querySelector<HTMLElement>(`[data-tour="${id}"]`)
  }

  function measure() {
    const id = steps[index]?.id
    const element = id ? target(id) : null
    if (!element) {
      box = null
      return
    }
    const rect = element.getBoundingClientRect()
    const pad = 6
    box = {
      top: rect.top - pad,
      left: rect.left - pad,
      width: rect.width + pad * 2,
      height: rect.height + pad * 2,
    }
  }

  function next() {
    if (last) {
      onClose()
      return
    }
    index += 1
  }

  $effect(() => {
    if (!open) return
    steps = STEPS.filter((item) => target(item.id) !== null)
    index = 0
  })

  $effect(() => {
    if (!open || steps.length === 0) return
    const id = steps[index]?.id
    const element = id ? target(id) : null
    element?.scrollIntoView({ block: 'center', behavior: 'instant' })
    measure()

    const again = () => measure()
    window.addEventListener('resize', again)
    window.addEventListener('scroll', again, true)
    return () => {
      window.removeEventListener('resize', again)
      window.removeEventListener('scroll', again, true)
    }
  })

  $effect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
      else if (event.key === 'ArrowRight' || event.key === 'Enter') next()
      else if (event.key === 'ArrowLeft' && index > 0) index -= 1
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const below = $derived(box !== null && box.top + box.height < window.innerHeight * 0.55)

  const place = $derived.by(() => {
    if (box === null || box.height > window.innerHeight * 0.6) {
      return { top: 'auto', bottom: '24px' }
    }
    return below
      ? { top: `${box.top + box.height + 12}px`, bottom: 'auto' }
      : { top: 'auto', bottom: `${window.innerHeight - box.top + 12}px` }
  })
</script>

{#if open && step}
  <div class="tour" role="dialog" aria-modal="true" aria-label="Підказки">
    <button class="veil" type="button" aria-label="Далі" onclick={next}></button>

    {#if box}
      <div
        class="hole"
        aria-hidden="true"
        style:top="{box.top}px"
        style:left="{box.left}px"
        style:width="{box.width}px"
        style:height="{box.height}px"
      ></div>
    {/if}

    <div class="card" class:below style:top={place.top} style:bottom={place.bottom}>
      <p class="count">{index + 1} / {steps.length}</p>
      <h2>{step.title}</h2>
      <p class="text">{@html brandHtml(step.text)}</p>
      <div class="actions">
        <button class="skip" type="button" onclick={onClose}>пропустити</button>
        <button class="next" type="button" onclick={next}>
          {last ? 'Зрозуміло' : 'Далі'}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .tour {
    position: fixed;
    inset: 0;
    z-index: 70;
  }

  .veil {
    position: absolute;
    inset: 0;
    width: 100%;
    background: transparent;
    cursor: default;
  }

  .hole {
    position: absolute;
    border-radius: 14px;
    pointer-events: none;
    border: 2px solid var(--pri-bg);
    box-shadow: 0 0 0 9999px rgb(0 0 0 / 0.62);
    transition: top 0.2s ease, left 0.2s ease, width 0.2s ease, height 0.2s ease;
  }

  @media (prefers-reduced-motion: reduce) {
    .hole {
      transition: none;
    }
  }

  .card {
    position: absolute;
    left: 50%;
    translate: -50% 0;
    width: min(var(--col), calc(100vw - 24px));
    padding: 14px 15px;
    border-radius: 16px;
    border: 1px solid var(--hair-strong);
    background: var(--menu-bg);
    backdrop-filter: blur(26px) saturate(160%);
    box-shadow: 0 18px 44px rgb(0 0 0 / 0.42);
  }

  .count {
    font-size: 10.5px;
    font-weight: 700;
    letter-spacing: 0.06em;
    color: var(--faint);
  }

  h2 {
    margin-top: 4px;
    font-size: 16px;
    font-weight: 800;
    letter-spacing: -0.3px;
    line-height: 1.25;
  }

  .text {
    margin-top: 6px;
    font-size: 13px;
    line-height: 1.5;
    color: var(--muted);
  }

  .actions {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 13px;
  }

  .skip {
    flex: none;
    padding: 8px 10px;
    min-height: 40px;
    font-size: 12px;
    font-weight: 700;
    color: var(--faint);
    background: transparent;
  }

  .next {
    flex: 1;
    min-height: 44px;
    border-radius: 12px;
    font-size: 14px;
    font-weight: 800;
    color: var(--pri-ink);
    background: var(--pri-bg);
  }
</style>
