<script lang="ts">

  import {
    SPEECH_LANGS,
    dictate,
    failureText,
    fallbackHint,
    knownMute,
    lastFailure,
    markMute,
    meterMicrophone,
    micPermission,
    noteLevel,
    rememberLang,
    rememberTweaks,
    savedLang,
    savedTweaks,
    sawAnyEvent,
    speechNotes,
    tweakSignature,
    type Dictation,
    type MicPermission,
    type SpeechLang,
    type SpeechNote,
    type SpeechTweaks,
    type VoiceMeter,
  } from './speech'
  import { debugEnabled, speechDiagEnabled } from './ui'

  interface Props {
    open: boolean
    /** Одна зафіксована позиція — один виклик. Викликається на «Готово»,
     *  НЕ під час диктування: до того чипси можна прибрати хрестиком, і
     *  хибно розчуте не встигає нікуди записатись. */
    onPhrase: (text: string) => void
    /** Дорозбити фразу на позиції («воду зелень чай» → три). Поле списку
     *  передає splitSpoken; полю правила фраза потрібна цілою — воно не
     *  передає нічого. Чипси показують уже розбите: гість бачить рівно те,
     *  що ляже в поле. */
    refine?: (text: string) => string[]
    onClose: () => void
    onError?: (message: string) => void
  }

  const { open, onPhrase, refine = (text) => [text], onClose, onError }: Props = $props()

  const WAVE_BARS = 36

  const BEAT_RISE = 1
  const BEAT_FALL = 0.14
  let heat = 0
  let seenEvents = 0

  const QUIET_YIELD = 2
  const QUIET_QUIT = 4
  const RESTART_MS = 250
  const STALL_RESTART_MS = 1500
  const WATCH_MS = 4000
  const WATCH_AFTER_YIELD_MS = 3000
  const WATCH_KNOWN_MS = 1200
  const JOURNAL_MS = 300
  const VOICE_LEVEL = 0.15
  const VOICE_FRAMES = 20

  const HINT_LISTEN = 'пауза ~1 с розділяє · × прибирає хибне'
  const HINT_YIELD = 'хвиля вимкнена: вона забирала мікрофон у розпізнавання'
  const HINT_NO_METER = 'хвиля не відкривалась: дослід без другого потоку'
  const SILENT_VOICED = 'мікрофон чую, а слів не розбираю — схоже, браузер не пускає розпізнавання; '
  const SILENT_MUTE = 'не почув жодного слова — якщо ти говорив, браузер не пускає розпізнавання; '

  /** Що вже зафіксовано цим диктуванням — чипси в діалозі. */
  let phrases = $state<string[]>([])
  /** Що промовляється просто зараз — курсивний рядок. */
  let interim = $state('')
  /** Історія рівнів голосу. Нуль — тиша, одиниця — крик. */
  let wave = $state<number[]>(Array(WAVE_BARS).fill(0))
  /** Мова розпізнавання. Запам'ятовується один раз — це властивість гостя,
   *  а не цього диктування. */
  let lang = $state<SpeechLang>(savedLang())
  const langSwitch = $derived(open && debugEnabled())
  /** Рядок стану в шапці: він же називає зняту хвилю. */
  let hint = $state(HINT_LISTEN)
  /** Діагноз, коли слів довго немає: усередині діалога, не банером ззовні. */
  let warning = $state('')
  let session: Dictation | null = null
  let meter: VoiceMeter | null = null

  const diagnosing = $derived(open && speechDiagEnabled())
  const ENGINE_EVENTS = new Set([
    'start',
    'audiostart',
    'soundstart',
    'speechstart',
    'result',
    'speechend',
    'soundend',
    'audioend',
    'nomatch',
    'end',
    'error',
  ])
  let journal = $state<SpeechNote[]>([])
  const fromEngine = $derived(journal.filter((item) => ENGINE_EVENTS.has(item.name)).length)
  let permission = $state<MicPermission>('unknown')
  let tweaks = $state<SpeechTweaks>(savedTweaks())
  let copied = $state('')

  function switchLang(next: SpeechLang) {
    if (next === lang) return
    lang = next
    rememberLang(next)
    phrases = []
    interim = ''
    session?.stop()
  }

  function toggleTweak(key: keyof SpeechTweaks) {
    tweaks = { ...tweaks, [key]: !tweaks[key] }
    rememberTweaks(tweaks)
    phrases = []
    interim = ''
    session?.stop()
  }

  function journalText(): string {
    const head = `дозвіл мікрофона: ${permission} | прапорці: ${tweakSignature(tweaks)}`
    const lines = journal.map(
      (item) =>
        `+${item.at}мс ${item.name}${item.detail ? ` (${item.detail})` : ''} хвиля ${item.level}`,
    )
    return [head, ...lines].join('\n')
  }

  async function copyJournal() {
    try {
      await navigator.clipboard.writeText(journalText())
      copied = 'скопійовано'
    } catch {
      copied = 'буфер не дався — виділи текст руками'
    }
  }

  /** «Готово» (і фатальна відмова): усе, що лишилось у чипсах, їде власнику.

      Чернетка (interim) їде ТЕЖ: гість бачить свої слова курсивом і тисне
      «Готово», не чекаючи секунди фіксації, — викинути їх означає «сказав,
      бачив, а не додалось» (живий випадок у коморі 14.08). */
  function finish() {
    const tail = interim.trim()
    const pending = tail ? refine(tail).filter(Boolean) : []
    for (const phrase of [...phrases, ...pending]) onPhrase(phrase)
    onClose()
  }

  function drop(index: number) {
    phrases = phrases.filter((_, i) => i !== index)
  }

  $effect(() => {
    if (!open) return

    phrases = []
    interim = ''
    hint = HINT_LISTEN
    wave = Array(WAVE_BARS).fill(0)
    copied = ''
    const stored = savedTweaks()
    if (tweakSignature(stored) !== tweakSignature(tweaks)) tweaks = stored

    void micPermission().then((state) => {
      permission = state
    })

    let alive = true
    let fatal = false
    /** Чи прийшло хоч одне слово в ЦІЙ сесії. */
    let heard = false
    /** Сесій поспіль, які скінчились без жодного слова. */
    let quiet = 0
    /** Кадрів хвилі зі справжнім голосом: доказ, що мовчав не гість. */
    let voiced = 0
    let yielded = false
    let timer = 0
    let watch = 0
    /** Номер сесії: події від уже зупиненої нас не стосуються. */
    let gen = 0
    /** Перша сесія цього диктування чистить журнал, наступні дописуються. */
    let first = true
    const watchFor = (yieldedNow: boolean) => {
      if (knownMute(tweakSignature(tweaks))) return WATCH_KNOWN_MS
      return yieldedNow ? WATCH_AFTER_YIELD_MS : WATCH_MS
    }
    const journalTick = window.setInterval(() => {
      journal = speechNotes()
      if (!tweaks.noMeter) return
      const now = journal.filter((item) => ENGINE_EVENTS.has(item.name)).length
      if (now > seenEvents) heat = BEAT_RISE
      seenEvents = now
      wave = [...wave.slice(1), heat]
      heat = Math.max(0, heat - BEAT_FALL)
    }, JOURNAL_MS)

    const dropMeter = () => {
      meter?.stop()
      meter = null
    }

    const teardown = () => {
      alive = false
      window.clearInterval(journalTick)
      window.clearTimeout(timer)
      window.clearTimeout(watch)
      const active = session
      session = null
      dropMeter()
      active?.stop()
    }

    const yieldWave = () => {
      dropMeter()
      yielded = true
      hint = HINT_YIELD
      wave = Array(WAVE_BARS).fill(0)
      heat = 0
      seenEvents = 0
    }

    const armWatch = (ms: number) => {
      window.clearTimeout(watch)
      watch = window.setTimeout(() => {
        if (!alive) return
        if (!yielded) {
          yieldWave()
          begin()
          armWatch(watchFor(true))
          return
        }
        stall()
      }, ms)
    }

    const stall = () => {
      window.clearTimeout(timer)
      window.clearTimeout(watch)
      const active = session
      session = null
      dropMeter()
      active?.stop()
      if (!sawAnyEvent()) markMute(tweakSignature(tweaks))
      const code = lastFailure()
      const named = code ? `${failureText(code)}; ` : ''
      warning = named + (voiced >= VOICE_FRAMES ? SILENT_VOICED : SILENT_MUTE) + fallbackHint()
      timer = window.setTimeout(begin, STALL_RESTART_MS)
    }

    const begin = () => {
      interim = ''
      heard = false
      const mine = ++gen
      const previous = session
      session = null
      previous?.stop()
      const stale = () => mine !== gen
      const wasFirst = first
      first = false
      if (wasFirst) journal = speechNotes()
      session = dictate({
        lang,
        tweaks,
        fresh: first,
        onPhrase: (text) => {
          if (stale()) return
          heard = true
          warning = ''
          armWatch(watchFor(yielded))
          phrases = [...phrases, ...refine(text).filter(Boolean)]
        },
        onInterim: (text) => {
          if (stale()) return
          if (text) {
            heard = true
            armWatch(watchFor(yielded))
          }
          interim = text
        },
        onEnd: () => {
          if (!alive || stale()) return
          if (fatal) {
            session = null
            dropMeter()
            finish()
            return
          }
          if (heard) {
            quiet = 0
            begin()
            return
          }
          quiet += 1
          if (quiet >= QUIET_QUIT) {
            stall()
            return
          }
          if (quiet >= QUIET_YIELD && meter) {
            yieldWave()
          }
          timer = window.setTimeout(begin, RESTART_MS)
        },
        onError: (message) => {
          if (stale()) return
          fatal = true
          onError?.(message)
        },
      })

      if (!session) {
        alive = false
        window.clearInterval(journalTick)
        window.clearTimeout(watch)
        onClose()
        return
      }
      armWatch(watchFor(yielded))
    }

    if (tweaks.noMeter) {
      yielded = true
      hint = diagnosing ? HINT_NO_METER : ''
    }

    begin()

    if (!session) return

    if (!tweaks.noMeter) {
      void meterMicrophone((level) => {
        if (level > VOICE_LEVEL) voiced += 1
        noteLevel(level)
        wave = [...wave.slice(1), level]
      }).then((opened) => {
        if (!session || yielded) {
          opened?.stop()
          return
        }
        meter = opened
      })
    }

    return teardown
  })
</script>

{#if open}
  <div class="scrim" aria-hidden="true"></div>
  <div class="sheet" role="dialog" aria-modal="true" aria-label="Диктування">
    <div class="recorder">
      <div class="rec-head">
        <span class="rec-dot" aria-hidden="true"></span>
        <span class="rec-title">слухаю</span>
        <span class="rec-hint">{hint}</span>
        {#if langSwitch}
          <div class="rec-langs" role="group" aria-label="Мова розпізнавання">
            {#each SPEECH_LANGS as option (option.id)}
              <button
                type="button"
                class="rec-lang"
                class:on={lang === option.id}
                aria-pressed={lang === option.id}
                onclick={() => switchLang(option.id)}
              >
                {option.label}
              </button>
            {/each}
          </div>
        {/if}
      </div>

      <div class="wave" aria-hidden="true">
        {#each wave as level, index (index)}
          <span class="wave-bar" style:height="{6 + level * 52}px"></span>
        {/each}
      </div>

      <p class="rec-live" class:idle={!interim} aria-live="polite">
        {interim || 'кажи — я записую'}
      </p>

      {#if warning}
        <p class="rec-warn" role="alert">{warning}</p>
      {/if}

      {#if phrases.length > 0}
        <div class="rec-phrases">
          {#each phrases as phrase, index (index)}
            <span class="rec-chip">
              {phrase}
              <button
                class="rec-drop"
                type="button"
                aria-label="Прибрати «{phrase}»"
                onclick={() => drop(index)}
              >
                ×
              </button>
            </span>
          {/each}
        </div>
      {/if}

      <button class="rec-done" type="button" onclick={finish}>
        {phrases.length > 0 ? `Готово — додати (${phrases.length})` : 'Готово'}
      </button>

      {#if diagnosing}
        <div class="diag">
          <div class="diag-head">
            <span class="diag-count">подій від двигуна: {fromEngine}</span>
            <span class="diag-perm">дозвіл: {permission}</span>
            <button class="diag-copy" type="button" onclick={copyJournal}>копіювати</button>
          </div>
          {#if copied}
            <p class="diag-said" aria-live="polite">{copied}</p>
          {/if}

          <div class="diag-tweaks" role="group" aria-label="Досліди над розпізнаванням">
            <label class="diag-tweak">
              <input
                type="checkbox"
                checked={tweaks.singleShot}
                onchange={() => toggleTweak('singleShot')}
              />
              continuous=false
            </label>
            <label class="diag-tweak">
              <input
                type="checkbox"
                checked={tweaks.finalOnly}
                onchange={() => toggleTweak('finalOnly')}
              />
              interim=false
            </label>
            <label class="diag-tweak">
              <input
                type="checkbox"
                checked={tweaks.noMeter}
                onchange={() => toggleTweak('noMeter')}
              />
              без хвилі
            </label>
          </div>

          <ol class="diag-log mono">
            {#each journal as item, index (index)}
              <li>
                <b>+{item.at}</b>
                {item.name}{#if item.detail}
                  · {item.detail}{/if}
                · хвиля {item.level}
              </li>
            {/each}
          </ol>
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .diag {
    margin-top: 10px;
    padding-top: 10px;
    border-top: 1px solid var(--hair-strong);
    font-size: 11px;
    color: var(--muted);
  }

  .diag-head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
  }

  .diag-count {
    color: var(--ink);
    font-weight: 600;
  }

  .diag-perm {
    color: var(--faint);
  }

  .diag-copy {
    margin-left: auto;
    padding: 3px 8px;
    border-radius: 8px;
    color: var(--muted);
    border: 1px solid var(--hair-strong);
    background: var(--chip-bg);
    font-size: 11px;
  }

  .diag-said {
    margin: 6px 0 0;
    color: var(--faint);
  }

  .diag-tweaks {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 10px;
    margin-top: 8px;
  }

  .diag-tweak {
    display: flex;
    align-items: center;
    gap: 4px;
    min-height: 28px;
  }

  .diag-log {
    max-height: 30vh;
    overflow-y: auto;
    overscroll-behavior: contain;
    margin: 8px 0 0;
    padding: 0;
    list-style: none;
    font-size: 10px;
    line-height: 1.5;
    overflow-wrap: anywhere;
  }

  .diag-log b {
    color: var(--badge);
    font-weight: 600;
  }

  .scrim {
    position: fixed;
    inset: 0;
    z-index: 80;
    background: rgb(0 0 0 / 0.5);
    touch-action: none;
  }

  .sheet {
    position: fixed;
    z-index: 81;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: min(360px, calc(100vw - 32px));
    border-radius: 16px;
    box-shadow: 0 24px 60px rgb(0 0 0 / 0.5);
  }

  .recorder {
    padding: 16px 16px 14px;
    border-radius: 16px;
    border: 1px solid var(--hair-strong);
    background: var(--menu-bg);
  }

  .rec-head {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .rec-dot {
    flex: none;
    width: 9px;
    height: 9px;
    border-radius: 50%;
    background: var(--badge);
    animation: rec-pulse 1.6s ease-in-out infinite;
  }

  .rec-title {
    font-size: 14px;
    font-weight: 800;
  }

  .rec-hint {
    margin-left: auto;
    font-size: 11px;
    color: var(--faint);
  }

  .wave {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 3px;
    height: 72px;
    margin-top: 12px;
  }

  .wave-bar {
    flex: none;
    width: 4px;
    min-height: 6px;
    border-radius: 2px;
    background: var(--badge);
    opacity: 0.85;
    transition: height 90ms linear;
  }

  .rec-live {
    margin-top: 10px;
    min-height: 18px;
    font-size: 13px;
    line-height: 1.4;
    text-align: center;
    color: var(--muted);
    font-style: italic;
  }

  .rec-live.idle {
    color: var(--faint);
    font-style: normal;
  }

  .rec-warn {
    margin: 8px 0 0;
    font-size: 12px;
    line-height: 1.4;
    text-align: center;
    color: var(--warn-ink, var(--muted));
  }

  .rec-phrases {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 5px;
    margin-top: 10px;
  }

  .rec-chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 4px 3px 9px;
    border-radius: 8px;
    font-size: 12px;
    font-weight: 600;
    border: 1px solid var(--hair-strong);
    background: var(--chip-bg);
  }

  .rec-drop {
    padding: 0 5px;
    font-size: 14px;
    line-height: 1.2;
    color: var(--muted);
  }

  .rec-langs {
    display: flex;
    gap: 2px;
    margin-left: auto;
    padding: 2px;
    border-radius: 999px;
    background: rgb(255 255 255 / 0.07);
  }

  .rec-lang {
    padding: 3px 9px;
    border: 0;
    border-radius: 999px;
    background: transparent;
    color: var(--muted);
    font: inherit;
    font-size: 11px;
    cursor: pointer;
  }

  .rec-lang.on {
    background: var(--chip-bg);
    color: var(--ink);
  }

  .rec-done {
    width: 100%;
    margin-top: 14px;
    padding: 12px;
    border-radius: 12px;
    font-size: 15px;
    font-weight: 800;
    color: var(--pri-ink);
    background: var(--pri-bg);
  }

  @keyframes rec-pulse {
    0%,
    100% {
      box-shadow: 0 0 0 0 var(--acc-half);
    }
    50% {
      box-shadow: 0 0 0 6px rgb(240 169 59 / 0);
    }
  }
</style>
