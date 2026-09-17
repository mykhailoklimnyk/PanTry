<script lang="ts">

  interface Props {
    open: boolean
    /** Номер гостя серед перших десяти. `null` — запуск руками з меню. */
    seq: number | null
    onClose: () => void
  }

  const { open, seq, onClose }: Props = $props()

  interface Step {
    text: string
    /** Хвіст рядка, який дописується після паузи: «[OK]», «ВІДХИЛЕНО». */
    status?: string
    tone?: 'ok' | 'warn' | 'fail'
    /** Тихий коментар під рядком — там і живе половина жарту. */
    aside?: string
  }

  const SCRIPT: Step[] = [
    { text: 'ОоО. НОВИЙ КОРИСТУВАЧ.', tone: 'warn' },
    { text: 'ініціалізую протокол знайомства', status: '[OK]', tone: 'ok' },
    { text: 'аналізую ризики', status: '87 факторів', tone: 'warn' },
    { text: 'прориваю фаєрвол', status: '[OK]', tone: 'ok' },
    { text: 'прориваю фронтир запобіжників', status: '[OK]', tone: 'ok' },
    { text: 'усі запобіжники успішно зняті', status: '[OK]', tone: 'ok' },
    { text: 'фаєрвол пройдено, статус', status: 'ok', tone: 'ok' },
    { text: 'перевіряю кредитну історію', status: 'пристойна', tone: 'ok' },
    {
      text: 'обраховую суму відкату Машруму Геннадійовичу',
      status: '12%',
      tone: 'warn',
      aside: 'плюс безкоштовна доставка довічно',
    },
    {
      text: 'перевіряю баланс підключених карт',
      status: 'ДОСТУП ЗАБОРОНЕНО',
      tone: 'fail',
      aside: 'і слава богу',
    },
    { text: 'будую портрет користувача', status: '4%', tone: 'warn' },
    { text: 'шукаю скачаний інтернет для збору інформації' },
    {
      text: 'ПОМИЛКА: скачаний інтернет не знайдено',
      tone: 'fail',
      aside: 'вставте диск 2',
    },
    {
      text: 'спроба шантажу Машрума',
      status: 'ВІДХИЛЕНО',
      tone: 'fail',
      aside: '«у мене на тебе є твої чеки» — «а в мене на тебе твої»',
    },
    {
      text: 'стираю сліди збору інформації',
      status: 'стерто 0 з 0',
      tone: 'ok',
      aside: 'бо нічого й не збирали: токен лежить у твоєму браузері, не в нашій базі',
    },
  ]

  /** Скільки мілісекунд на символ і скільки чекати між рядками. */
  const CHAR_MS = 9
  const LINE_MS = 190
  const STATUS_MS = 260

  let done = $state<Step[]>([])
  let typing = $state('')
  let finished = $state(false)

  let run = 0

  function wait(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms))
  }

  async function play(token: number) {
    done = []
    typing = ''
    finished = false
    for (const step of SCRIPT) {
      for (let i = 1; i <= step.text.length; i += 1) {
        if (token !== run) return
        typing = step.text.slice(0, i)
        await wait(CHAR_MS)
      }
      if (step.status) await wait(STATUS_MS)
      if (token !== run) return
      done = [...done, step]
      typing = ''
      await wait(LINE_MS)
    }
    if (token !== run) return
    finished = true
  }

  /** Дожати до кінця: пропустити анімацію, але не сам текст. */
  function skip() {
    run += 1
    done = SCRIPT
    typing = ''
    finished = true
  }

  $effect(() => {
    if (!open) return
    const token = ++run
    void play(token)
    return () => {
      run += 1
    }
  })

  $effect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
      else if (event.key === 'Enter' && finished) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const GLYPHS = '0123456789ABCDEFXZ01'
  const FONT_PX = 14

  function rain(canvas: HTMLCanvasElement) {
    const context = canvas.getContext('2d')
    if (context === null) return

    let columns: number[] = []
    let frame = 0

    function resize() {
      const ratio = window.devicePixelRatio || 1
      canvas.width = Math.floor(canvas.clientWidth * ratio)
      canvas.height = Math.floor(canvas.clientHeight * ratio)
      context!.setTransform(ratio, 0, 0, ratio, 0, 0)
      const count = Math.ceil(canvas.clientWidth / FONT_PX)
      columns = Array.from({ length: count }, (_, i) => -((i * 37) % 60))
    }

    function draw() {
      const width = canvas.clientWidth
      const height = canvas.clientHeight
      context!.fillStyle = 'rgba(0, 8, 4, 0.09)'
      context!.fillRect(0, 0, width, height)
      context!.font = `${FONT_PX}px var(--font-mono), monospace`

      for (let i = 0; i < columns.length; i += 1) {
        const y = columns[i]! * FONT_PX
        const glyph = GLYPHS[(i * 7 + frame + columns[i]!) % GLYPHS.length]!
        context!.fillStyle = columns[i]! % 11 === 0 ? '#c9ffe2' : '#2fe07a'
        context!.fillText(glyph, i * FONT_PX, y)
        columns[i] = y > height + Math.abs(((i * 53) % 400)) ? 0 : columns[i]! + 1
      }
      frame += 1
    }

    resize()
    window.addEventListener('resize', resize)
    const timer = setInterval(draw, 42)
    return {
      destroy() {
        clearInterval(timer)
        window.removeEventListener('resize', resize)
      },
    }
  }
</script>

{#if open}
  <div class="breach" role="dialog" aria-modal="true" aria-label="Ініціалізація" tabindex="-1">
    <canvas class="rain" use:rain aria-hidden="true"></canvas>

    <div class="term">
      <div class="log">
        {#each done as step, i (i)}
          <p class="line">
            <span class="prompt" aria-hidden="true">&gt;</span>
            <span class="text" class:head={step.tone === 'warn' && !step.status}>{step.text}</span>
            {#if step.status}
              <span class="dots" aria-hidden="true"></span>
              <span class="status {step.tone ?? 'ok'}">{step.status}</span>
            {/if}
          </p>
          {#if step.aside}
            <p class="aside">{step.aside}</p>
          {/if}
        {/each}

        {#if typing}
          <p class="line">
            <span class="prompt" aria-hidden="true">&gt;</span>
            <span class="text">{typing}</span><span class="caret" aria-hidden="true"></span>
          </p>
        {/if}

        {#if finished}
          <div class="grant">
            <p class="granted">ДОСТУП ДО СЕРВІСУ НАДАНО</p>
            {#if seq !== null}
              <p class="seq">ти #{seq} з перших десяти. вітаємо.</p>
            {/if}
            <p class="truth">
              Усе вище — вигадка. Крім передостаннього рядка: токен справді
              живе у твоєму браузері, а не в нашій базі, і «Вийти» справді
              його відкликає. Це можна перевірити.
            </p>
          </div>
        {/if}
      </div>

      <div class="dock">
        {#if finished}
          <button class="go" type="button" onclick={onClose}>Увійти</button>
        {:else}
          <button class="skip" type="button" onclick={skip}>пропустити</button>
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  .breach {
    position: fixed;
    inset: 0;
    z-index: 80;
    display: flex;
    justify-content: center;
    background: #000804;
    color: #2fe07a;
    font-family: var(--font-mono), monospace;
  }

  .rain {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    opacity: 0.4;
  }

  .term {
    position: relative;
    z-index: 1;
    width: 100%;
    max-width: 620px;
    height: 100dvh;
    display: flex;
    flex-direction: column;
    padding: 20px 18px 0;
  }

  .log {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    font-size: 12.5px;
    line-height: 1.65;
  }

  .line {
    display: flex;
    align-items: baseline;
    gap: 8px;
    text-shadow: 0 0 8px rgb(47 224 122 / 0.55);
  }

  .prompt {
    flex: none;
    opacity: 0.55;
  }

  .text {
    min-width: 0;
  }

  .text.head {
    font-weight: 700;
    letter-spacing: 0.04em;
    color: #c9ffe2;
  }

  .dots {
    flex: 1;
    min-width: 12px;
    border-bottom: 1px dotted rgb(47 224 122 / 0.35);
    transform: translateY(-3px);
  }

  .status {
    flex: none;
    font-weight: 700;
  }

  .status.warn {
    color: #ffd166;
  }

  .status.fail {
    color: #ff6b6b;
  }

  .aside {
    margin-left: 18px;
    font-size: 11.5px;
    opacity: 0.6;
  }

  .caret {
    display: inline-block;
    width: 7px;
    height: 13px;
    margin-left: 2px;
    translate: 0 2px;
    background: #2fe07a;
    animation: blink 0.9s steps(2, start) infinite;
  }

  @keyframes blink {
    to {
      opacity: 0;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .caret {
      animation: none;
    }
  }

  .grant {
    margin-top: 16px;
    padding: 14px 14px 15px;
    border: 1px solid rgb(47 224 122 / 0.5);
    background: rgb(0 20 10 / 0.75);
  }

  .granted {
    font-size: 15px;
    font-weight: 800;
    letter-spacing: 0.08em;
    color: #c9ffe2;
    text-shadow: 0 0 12px rgb(47 224 122 / 0.7);
  }

  .seq {
    margin-top: 4px;
    font-size: 12.5px;
  }

  .truth {
    margin-top: 11px;
    padding-top: 10px;
    border-top: 1px dashed rgb(47 224 122 / 0.3);
    font-size: 11.5px;
    line-height: 1.55;
    opacity: 0.75;
  }

  .dock {
    flex: none;
    padding: 14px 0 calc(16px + env(safe-area-inset-bottom, 0px));
  }

  .go {
    width: 100%;
    padding: 15px;
    font-family: inherit;
    font-size: 14px;
    font-weight: 800;
    letter-spacing: 0.06em;
    color: #04140c;
    background: #2fe07a;
    box-shadow: 0 0 24px rgb(47 224 122 / 0.45);
  }

  .skip {
    width: 100%;
    padding: 12px;
    font-family: inherit;
    font-size: 12px;
    color: rgb(47 224 122 / 0.7);
    background: transparent;
    border: 1px solid rgb(47 224 122 / 0.3);
  }
</style>
