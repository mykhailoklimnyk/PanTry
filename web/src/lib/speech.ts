

interface PhraseAlternative {
  transcript: string
}

interface PhraseResult {
  isFinal: boolean
  0: PhraseAlternative
}

interface PhraseEvent {
  resultIndex: number
  results: ArrayLike<PhraseResult>
}

interface FailureEvent {
  error: string
}

interface SpeechEngine {
  lang: string
  continuous: boolean
  interimResults: boolean
  onresult: ((event: PhraseEvent) => void) | null
  onerror: ((event: FailureEvent) => void) | null
  onend: (() => void) | null
  onstart?: (() => void) | null
  onaudiostart?: (() => void) | null
  onaudioend?: (() => void) | null
  onsoundstart?: (() => void) | null
  onsoundend?: (() => void) | null
  onspeechstart?: (() => void) | null
  onspeechend?: (() => void) | null
  onnomatch?: (() => void) | null
  start(): void
  stop(): void
}

type SpeechCtor = new () => SpeechEngine

let ctorName = ''

function engineCtor(): SpeechCtor | null {
  const w = window as unknown as Record<string, unknown>
  const plain = w.SpeechRecognition as SpeechCtor | undefined
  if (plain) {
    ctorName = 'SpeechRecognition'
    return plain
  }
  const prefixed = w.webkitSpeechRecognition as SpeechCtor | undefined
  if (prefixed) {
    ctorName = 'webkitSpeechRecognition'
    return prefixed
  }
  ctorName = ''
  return null
}

export function voiceAvailable(): boolean {
  return typeof window !== 'undefined' && engineCtor() !== null
}

export type SpeechLang = 'uk-UA' | 'ru-RU'

export const SPEECH_LANGS: { id: SpeechLang; label: string }[] = [
  { id: 'uk-UA', label: 'укр' },
  { id: 'ru-RU', label: 'рус' },
]

const LANG_KEY = 'komora:speech-lang'

export function savedLang(): SpeechLang {
  try {
    const saved = localStorage.getItem(LANG_KEY)
    return saved === 'ru-RU' ? 'ru-RU' : 'uk-UA'
  } catch {
    return 'uk-UA'
  }
}

export function rememberLang(lang: SpeechLang): void {
  try {
    localStorage.setItem(LANG_KEY, lang)
  } catch {
  }
}

export interface SpeechTweaks {
  singleShot: boolean
  finalOnly: boolean
  noMeter: boolean
}

const TWEAK_KEY = 'komora:speech-tweaks'

export const NO_TWEAKS: SpeechTweaks = {
  singleShot: false,
  finalOnly: false,
  noMeter: false,
}

export function defaultTweaks(): SpeechTweaks {
  return { ...NO_TWEAKS, noMeter: coarsePointer() }
}

export function savedTweaks(): SpeechTweaks {
  try {
    const raw = localStorage.getItem(TWEAK_KEY)
    if (!raw) return defaultTweaks()
    const parsed = JSON.parse(raw) as Partial<SpeechTweaks>
    return {
      singleShot: parsed.singleShot === true,
      finalOnly: parsed.finalOnly === true,
      noMeter: parsed.noMeter === true,
    }
  } catch {
    return defaultTweaks()
  }
}

export function rememberTweaks(tweaks: SpeechTweaks): void {
  try {
    localStorage.setItem(TWEAK_KEY, JSON.stringify(tweaks))
  } catch {
  }
}

export interface SpeechNote {
  at: number
  name: string
  detail?: string
  level: number
}

const NOTES_MAX = 60

let notes: SpeechNote[] = []
let began = 0
let peak = 0
let sawEvent = false
let muteFor = ''
let lastCode = ''

function note(name: string, detail?: string): void {
  const entry: SpeechNote = {
    at: Math.round(performance.now() - began),
    name,
    level: Math.round(peak * 100) / 100,
    ...(detail ? { detail } : {}),
  }
  peak = 0
  notes = [...notes, entry].slice(-NOTES_MAX)
}

export function noteLevel(level: number): void {
  if (level > peak) peak = level
}

export function speechNotes(): SpeechNote[] {
  return notes
}

export function sawAnyEvent(): boolean {
  return sawEvent
}

export function tweakSignature(tweaks: SpeechTweaks): string {
  return `${tweaks.singleShot ? 1 : 0}${tweaks.finalOnly ? 1 : 0}${tweaks.noMeter ? 1 : 0}`
}

export function knownMute(signature: string): boolean {
  return muteFor !== '' && muteFor === signature
}

export function markMute(signature: string): void {
  muteFor = signature
  note('німий', 'жодної події від двигуна')
}

export function lastFailure(): string {
  return lastCode
}

export type MicPermission = 'granted' | 'denied' | 'prompt' | 'unknown'

export async function micPermission(): Promise<MicPermission> {
  try {
    const api = navigator.permissions as
      | { query(descriptor: { name: string }): Promise<{ state: string }> }
      | undefined
    if (!api?.query) return 'unknown'
    const status = await api.query({ name: 'microphone' })
    if (status.state === 'granted' || status.state === 'denied' || status.state === 'prompt') {
      return status.state
    }
    return 'unknown'
  } catch {
    return 'unknown'
  }
}

const FAILURES: Record<string, string> = {
  'not-allowed': 'мікрофон заборонено — дозволь його для цього сайту в браузері',
  'service-not-allowed': 'браузер не пускає до сервісу розпізнавання',
  'audio-capture': 'мікрофон не знайдено',
  network: 'розпізнаванню потрібна мережа — браузер не зміг достукатись',
  'no-speech': 'жодного слова не почулось',
  aborted: 'розпізнавання перервано',
  'language-not-supported': 'браузер не знає цієї мови розпізнавання',
  'bad-grammar': 'браузер не прийняв налаштування розпізнавання',
}

export function failureText(code: string): string {
  return FAILURES[code] ?? `розпізнавання не вдалось (${code})`
}

export function coarsePointer(): boolean {
  return typeof matchMedia === 'function' && matchMedia('(pointer: coarse)').matches
}

export function fallbackHint(): string {
  return coarsePointer() ? 'скажи через мікрофон на клавіатурі' : 'набери словами'
}

export interface Dictation {
  stop(): void
}

export interface VoiceMeter {
  stop(): void
}

export async function meterMicrophone(
  onLevel: (level: number) => void,
): Promise<VoiceMeter | null> {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    note('хвиля', 'потік відкрито')
    const context = new AudioContext()
    const source = context.createMediaStreamSource(stream)
    const analyser = context.createAnalyser()
    analyser.fftSize = 512
    source.connect(analyser)

    const data = new Uint8Array(analyser.fftSize)
    let raf = 0
    const tick = () => {
      analyser.getByteTimeDomainData(data)
      let sum = 0
      for (let i = 0; i < data.length; i += 1) {
        const v = ((data[i] ?? 128) - 128) / 128
        sum += v * v
      }
      onLevel(Math.min(1, Math.sqrt(sum / data.length) * 4))
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)

    return {
      stop() {
        cancelAnimationFrame(raf)
        source.disconnect()
        void context.close()
        for (const track of stream.getTracks()) track.stop()
      },
    }
  } catch (failure) {
    const name = failure instanceof Error ? failure.name : 'невідомо'
    note('хвиля', `потоку немає: ${name}`)
    return null
  }
}

export function dictate(handlers: {
  onPhrase: (text: string) => void
  lang?: SpeechLang
  tweaks?: SpeechTweaks
  fresh?: boolean
  onInterim?: (text: string) => void
  onEnd: () => void
  onError: (message: string) => void
}): Dictation | null {
  const Ctor = engineCtor()
  const tweaks = handlers.tweaks ?? NO_TWEAKS
  if (handlers.fresh) {
    notes = []
    began = performance.now()
    peak = 0
    sawEvent = false
    lastCode = ''
  }
  if (!Ctor) {
    note('двигуна немає', 'ні SpeechRecognition, ні webkitSpeechRecognition')
    return null
  }

  const engine = new Ctor()
  engine.lang = handlers.lang ?? 'uk-UA'
  engine.continuous = !tweaks.singleShot
  engine.interimResults = !tweaks.finalOnly

  const heard = (name: string, detail?: string) => {
    sawEvent = true
    note(name, detail)
  }

  let taken = 0
  let lastFinal = ''
  const words = (s: string): string[] =>
    s
      .toLowerCase()
      .replace(/[^\p{L}\p{N}\s'\u2019-]/gu, '')
      .split(/\s+/)
      .filter(Boolean)
  const startsLike = (longer: string[], shorter: string[]): boolean =>
    shorter.length > 0 && shorter.every((word, at) => longer[at] === word)

  engine.onresult = (event) => {
    let interim = ''
    let finals = 0
    for (let i = Math.max(event.resultIndex, taken); i < event.results.length; i += 1) {
      const result = event.results[i]
      if (!result) continue
      const text = result[0].transcript.trim()
      if (result.isFinal) {
        finals += 1
        taken = i + 1
        const now = words(text)
        const seen = words(lastFinal)
        const grown = now.length > seen.length && startsLike(now, seen)
        const repeated = now.length <= seen.length && startsLike(seen, now)
        const fresh = grown ? text.trim().split(/\s+/).slice(seen.length).join(' ') : repeated ? '' : text
        if (!repeated) lastFinal = text
        if (fresh) handlers.onPhrase(fresh)
      } else if (text) {
        interim += (interim ? ' ' : '') + text
      }
    }
    heard('result', `${event.results.length} шт, фінальних ${finals}`)
    handlers.onInterim?.(interim)
  }

  engine.onerror = (event) => {
    lastCode = event.error
    heard('error', event.error)
    if (event.error === 'no-speech' || event.error === 'aborted') return
    handlers.onError(failureText(event.error))
  }

  engine.onend = () => {
    heard('end')
    handlers.onEnd()
  }

  engine.onstart = () => heard('start')
  engine.onaudiostart = () => heard('audiostart')
  engine.onsoundstart = () => heard('soundstart')
  engine.onspeechstart = () => heard('speechstart')
  engine.onspeechend = () => heard('speechend')
  engine.onsoundend = () => heard('soundend')
  engine.onaudioend = () => heard('audioend')
  engine.onnomatch = () => heard('nomatch')

  note(
    'двигун',
    `${ctorName} ${engine.lang} continuous=${engine.continuous} interim=${engine.interimResults}`,
  )
  try {
    engine.start()
  } catch (failure) {
    note('start кинув', failure instanceof Error ? failure.name : 'невідомо')
    handlers.onError(`браузер не пустив розпізнавання — ${fallbackHint()}`)
    return null
  }
  note('start викликано')
  return { stop: () => engine.stop() }
}
