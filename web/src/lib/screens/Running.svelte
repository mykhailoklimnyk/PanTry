<script lang="ts">
  import { copyJson } from '../clipboard'
  import { plural } from '../format'
  import { BUILD_PHASES, type Phase } from '../ui'
  import type { Thought } from '../thoughts'
  import type { TraceOption, TraceStep } from '../types'

  interface Props {
    /** Скільки мілісекунд триває ЦЯ збірка. Справжні, від кліку. */
    elapsed: number
    /** Що агент знає про цей дім — з комори, прочитаної на старті. */
    thoughts: Thought[]
    /**
     * Справжні кроки конвеєра, прочитані з сервера ПОКИ він працює (02.09).
     * Поки їх немає (перші сотні мілісекунд), екран іде фазами за таймером;
     * з першим кроком таймерна вигадка поступається правді.
     */
    steps?: TraceStep[]
    /**
     * Чи показувати ТЕХНІЧНУ частину кроків: імена інструментів і кнопку
     * «копіювати кроки». Самі кроки -- словами, з рішенням агента під
     * кожним -- гість бачить завжди (рішення власника 10.09: журі судить
     * агента, а ззовні workflow і агент виглядають однаково, поки не
     * видно, як він вирішує). До того перелік у збірці жив лише під
     * панеллю дебагу (#288): гість не читає імен інструментів -- це
     * лишається правдою, тому імена й досі під прапорцем. Гейт на
     * ПРАПОРЦІ, а не на видимості панелі: вона ховається на вузькому
     * екрані, і тоді імена зникали б там, де їх свідомо ввімкнули.
     */
    journal?: boolean
    /** Фази за ТАЙМЕРОМ, поки справжніх кроків ще немає. У комори й кошика
     *  вони різні і обидві виміряні (`ui.BUILD_PHASES`, `ui.PANTRY_PHASES`);
     *  спільна таблиця брехала б про одну з двох робіт. */
    phases?: readonly [Phase, ...Phase[]]
    /**
     * Хто прийме відповідь на питання агента (#285). Без нього картка не
     * малюється взагалі: питання, на яке немає як відповісти, -- це глухий
     * кут, а не діалог (#190).
     */
    onAnswer?: (questionId: string, option: TraceOption) => void
    /** Що саме зараз робиться. Проп, бо екран той самий на дві роботи:
     *  збірку кошика і заповнення комори (прохання власника 07.09: «такий
     *  подібний екран хочу на комору»). Другий екран з тією ж розкладкою
     *  розійшовся б з цим мовчки (#158). */
    title?: string
    /** Останній рядок екрана. Обіцянка теж належить РОБОТІ: «кошик покажу
     *  перед оплатою» на екрані комори було б відповіддю на питання, якого
     *  гість не ставив. */
    promise?: string
    /** Вікно ВБУДОВАНЕ, а не екран. У збірці воно займає всю висоту і
     *  притискає обіцянку донизу; у коморі стоїть над списком, і та сама
     *  розпірка відсунула б за екран рядки, по які прийшли (#125). */
    inline?: boolean
  }

  const {
    elapsed,
    thoughts,
    steps = [],
    journal = false,
    phases = BUILD_PHASES,
    onAnswer,
    title = 'Збираю кошик',
    promise = 'кошик покажу перед оплатою — нічого не спишеться',
    inline = false,
  }: Props = $props()

  let answered = $state<Record<string, string>>({})

  let copied = $state<'ok' | 'fail' | null>(null)
  async function copyAll() {
    copied = (await copyJson(steps)) ? 'ok' : 'fail'
    setTimeout(() => (copied = null), 1600)
  }
  const allLabel = $derived(
    copied === 'ok'
      ? `скопійовано ${steps.length}`
      : copied === 'fail'
        ? 'не вдалося'
        : `копіювати кроки (${steps.length})`,
  )
  const asking = $derived(
    steps
      .map((step) => step.question)
      .filter((question) => question !== null)
      .filter((question) => !(question.id in answered)),
  )


  const step = $derived(
    Math.max(0, phases.filter((phase) => elapsed >= phase.after).length - 1),
  )
  const timedDone = $derived(phases.slice(0, step))
  const timedNow = $derived(phases[step] ?? phases[0])
  const done = $derived(
    steps.length > 0
      ? steps
          .slice(0, -1)
          .map((s) => ({ id: s.id, label: s.resultSummary, call: s.tool, why: s.decision ?? '' }))
      : timedDone.map((phase) => ({ ...phase, why: '' })),
  )
  const now = $derived(
    steps.length > 0
      ? {
          id: steps[steps.length - 1]!.id,
          label: steps[steps.length - 1]!.resultSummary,
          call: steps[steps.length - 1]!.tool,
          why: steps[steps.length - 1]!.decision ?? '',
        }
      : { ...timedNow, why: '' },
  )

  const STEPS_SHOWN = 5
  const doneHidden = $derived(Math.max(0, done.length - STEPS_SHOWN))
  const doneShown = $derived(done.slice(-STEPS_SHOWN))

  const THOUGHT_EVERY_MS = 2800
  const THOUGHTS_FROM_MS = 3500
  const said = $derived(
    elapsed < THOUGHTS_FROM_MS
      ? []
      : thoughts.slice(0, Math.min(thoughts.length, Math.floor((elapsed - THOUGHTS_FROM_MS) / THOUGHT_EVERY_MS) + 1)),
  )

  const seconds = $derived(Math.floor(elapsed / 1000))
</script>

<div class="running" class:inline>
  <header>
    <div class="title">
      <h1>{title}</h1>
      <p class="clock num" aria-live="off">{seconds} с</p>
    </div>
  </header>

    <ol class="steps">
      {#if doneHidden > 0}
        <li class="steps-more">
          ще {plural(doneHidden, { one: 'крок', few: 'кроки', many: 'кроків' })} вище
        </li>
      {/if}
      {#each doneShown as phase, index (phase.id + index)}
        <li class="step done" data-step={phase.id}>
          <span class="dot" aria-hidden="true">✓</span>
          <span class="label">{phase.label}</span>
        </li>
      {/each}
      <li class="step live" data-step={now.id} aria-live="polite">
        <span class="dot pulse" aria-hidden="true"></span>
        <span class="label">{now.label}</span>
        {#if now.why}
          <span class="why">{now.why}</span>
        {/if}
        {#if journal}
          <span class="call mono">{now.call}<span class="ellipsis" aria-hidden="true">…</span></span>
        {/if}
      </li>
    </ol>
    {#if journal && steps.length > 0}
      <button class="copy-all" type="button" onclick={copyAll}>{allLabel}</button>
    {/if}

  {#if onAnswer}
    {#each asking as question (question.id)}
      <section class="ask" aria-live="polite">
        <h2>{question.ask}</h2>
        {#if question.why}
          <p class="why">{question.why}</p>
        {/if}
        <div class="options">
          {#each question.options as option (option.id)}
            <button
              type="button"
              onclick={() => {
                answered = { ...answered, [question.id]: option.id }
                onAnswer(question.id, option)
              }}
            >
              {option.label}
            </button>
          {/each}
        </div>
        <p class="wait">не відповіси за {question.waitS} с — зберу без цього</p>
      </section>
    {/each}
  {/if}

  {#if said.length > 0}
    <section class="knows">
      <h2>поки шукаю — ось що я знаю про твій дім</h2>
      <ul class="thoughts">
        {#each [...said].reverse() as thought (thought.id)}
          <li class="thought">
            <p>{thought.text}</p>
            {#if thought.detail}
              <p class="detail">{thought.detail}</p>
            {/if}
          </li>
        {/each}
      </ul>
    </section>
  {/if}

  {#if !inline}
    <div class="spacer"></div>
  {/if}
  <p class="promise">{promise}</p>
</div>

<style>
  .running {
    padding: 22px 20px 36px;
    flex: 1;
    display: flex;
    flex-direction: column;
  }

  .running.inline {
    flex: none;
    padding: 14px 0 10px;
  }

  header {
    display: flex;
    align-items: center;
    gap: 13px;
  }

  h1 {
    font-size: 20px;
    font-weight: 800;
    letter-spacing: -0.6px;
  }

  .clock {
    font-size: 12px;
    color: var(--faint);
    margin-top: 3px;
  }

  .steps {
    list-style: none;
    margin-top: 18px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .step {
    display: grid;
    grid-template-columns: 16px 1fr;
    align-items: baseline;
    gap: 3px 9px;
    font-size: 13px;
    line-height: 1.3;
  }
  .step.done .label {
    min-width: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .step.done {
    color: var(--faint);
    font-size: 12.5px;
  }

  .steps-more {
    font-size: 11px;
    color: var(--faint);
    font-style: italic;
  }

  .copy-all {
    align-self: flex-start;
    margin-top: 8px;
    padding: 4px 9px;
    font-size: 11px;
    color: var(--faint);
    border: 1px solid var(--hair);
    border-radius: 999px;
    background: none;
  }

  .step.live {
    font-size: 15px;
    margin-top: 3px;
  }

  .step.live .label {
    font-weight: 700;
  }

  .ellipsis {
    display: inline-block;
    width: 1.1em;
    overflow: hidden;
    vertical-align: bottom;
    animation: komora-ellipsis 1.4s steps(4) infinite;
  }

  .dot {
    grid-row: 1;
    font-size: 11px;
    color: var(--good);
    text-align: center;
  }

  .dot.pulse {
    width: 8px;
    height: 8px;
    margin: 0 auto;
    border-radius: 50%;
    background: var(--acc-bar);
    animation: komora-breathe 1.1s ease-in-out infinite;
  }

  .call {
    grid-column: 2;
    font-size: 10.5px;
    color: var(--faint);
  }

  .why {
    grid-column: 2;
    font-size: 11.5px;
    line-height: 1.35;
    color: var(--muted);
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .ask {
    margin-top: 18px;
    padding: 14px 15px 12px;
    border-radius: 16px;
    border: 1px solid var(--hair);
    background: var(--list-bg);
    animation: komora-rise 0.45s ease-out both;
  }

  .ask h2 {
    font-size: 15px;
    font-weight: 700;
    line-height: 1.35;
  }

  .ask .why {
    font-size: 12px;
    color: var(--faint);
    margin-top: 4px;
  }

  .options {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 11px;
  }

  .options button {
    padding: 8px 13px;
    border-radius: 999px;
    border: 1px solid var(--hair);
    background: var(--chip-bg);
    font: inherit;
    font-size: 13.5px;
    font-weight: 600;
    cursor: pointer;
  }

  .options button:hover {
    border-color: var(--acc-edge);
  }

  .wait {
    font-size: 11.5px;
    color: var(--faint);
    margin-top: 9px;
  }

  .knows {
    margin-top: 20px;
    padding-top: 15px;
    border-top: 1px solid var(--hair);
  }

  .knows h2 {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.3px;
    text-transform: uppercase;
    color: var(--faint);
  }

  .thoughts {
    list-style: none;
    margin-top: 12px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .thought {
    font-size: 14.5px;
    line-height: 1.4;
    animation: komora-rise 0.45s ease-out both;
  }

  .thought .detail {
    font-size: 11.5px;
    color: var(--faint);
    margin-top: 2px;
  }

  .spacer {
    flex: 1;
    min-height: 16px;
  }

  .promise {
    font-size: 12.5px;
    color: var(--faint);
    text-align: center;
  }

  @media (prefers-reduced-motion: reduce) {
    .dot.pulse,
    .ellipsis,
    .ask,
    .thought {
      animation: none;
    }
  }
</style>
