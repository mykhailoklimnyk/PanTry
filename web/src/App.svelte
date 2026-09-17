<script lang="ts">
  import Breach from './lib/Breach.svelte'
  import Chrome from './lib/Chrome.svelte'
  import { autoSwapGiven, rememberAutoSwap } from './lib/consent'
  import Debug from './lib/Debug.svelte'
  import Modal from './lib/Modal.svelte'
  import Onboarding from './lib/Onboarding.svelte'
  import PlacePicker from './lib/PlacePicker.svelte'
  import Tour from './lib/Tour.svelte'
  import {
    addBarKind,
    buildBarFromPurchases,
    clearBarList,
    dropBarKind,
    dropSavedSwap,
    dropWanted,
    keepWanted,
    loadBar,
    loadBasket,
    loadDeliveryOptions,
    loadHealth,
    loadCartState,
    loadModels,
    buildPantryFromPurchases,
    nextShoppingList,
    clearPantryList,
    dropPantryItem,
    loadPantry,
    loopPantry,
    loadSavedSwaps,
    loadWanted,
    loadSwapOptions,
    loadPlace,
    loadQuota,
    loadOwnRules,
    loadProfileRules,
    deleteRule,
    saveRule,
    toggleRule as saveRuleSwitch,
    resolvePantryUnit,
    searchPlace,
    sendCheckout,
    sendCheaper,
    sendCorrection,
    sendPantryMark,
    setBarGroup,
    setBarSource,
    setPantrySource,
    sendPlace,
    sendPick,
    sendRefill,
    sendSwaps,
    type Loaded,
  } from './lib/data'
  import { answerProgress, readProgress } from './lib/api'
  import { parseList } from './lib/list'
  import * as ruleCache from './lib/rules'
  import {
    type PantryEdit,
    SETTLE_MS,
    keepOrder,
    order as orderOf,
    stepped,
    withQty,
  } from './lib/pantry'
  import { swapsToReview } from './lib/feedback'
  import { changes, signature as signatureOf, staleLabel, type Settings } from './lib/stale'
  import { plural } from './lib/format'
  import type { DoneRun, FailedRun, Run, RunKind } from './lib/runs'
  import {
  disconnect,
  forgetLlmKey,
  greeted,
  link,
  refresh as refreshLink,
  saveLlmKey,
} from './lib/session.svelte'
  import {
    DEBUG_KEY,
    DEFAULT_DELIVERY,
    isBuying,
    pantryStep,
    tollSince,
  } from './lib/ui'
  import { thoughtsFor, type Thought } from './lib/thoughts'
  import { backLabel, inTabs, isDoc, popped, pushed, type Screen } from './lib/navigation'
  import Doc from './lib/screens/Doc.svelte'
  import KeyForm from './lib/KeyForm.svelte'
  import { closePopovers, watchDismiss } from './lib/popover.svelte'
  import Bar from './lib/screens/Bar.svelte'
  import Cart from './lib/screens/Cart.svelte'
  import Connect from './lib/screens/Connect.svelte'
  import Pantry from './lib/screens/Pantry.svelte'
  import Running from './lib/screens/Running.svelte'
  import Start from './lib/screens/Start.svelte'
  import Swaps, { type SwapPolicy } from './lib/screens/Swaps.svelte'
  import Trace from './lib/screens/Trace.svelte'
  import { theme } from './lib/theme.svelte'
  import type {
    Bar as BarState,
    Basket,
    CarryOverState,
    CartCarryOver,
    CartLine,
    CartState,
    CheckoutResult,
    BuildRequest,
    ClarifyAnswer,
    TraceOption,
    TraceStep,
    ClarifyPick,
    DeliveryOption,
    Exclusion,
    Health,
    ModelOption,
    Pantry as PantryState,
    SwapDecision,
    Substitute,
    PantryAsk,
    PantryItem,
    Place,
    PlaceOption,
    Quota as QuotaState,
    Toll,
    SavedSwap,
    WantedRow,
  } from './lib/types'

  const today = new Date()

  const PANTRY_SEEN = 'komora:pantry-seen'
  let screen = $state<Screen>(localStorage.getItem(PANTRY_SEEN) === '1' ? 'start' : 'pantry')
  $effect(() => {
    if (view !== 'pantry' || !pantryLoaded || pantryFailed !== null) return
    localStorage.setItem(PANTRY_SEEN, '1')
  })
  let elapsed = $state(0)
  let thoughts = $state<Thought[]>([])

  let model = $state('')
  let models = $state<Loaded<ModelOption[]>>({ ok: true, data: [] })
  const MODEL_KEY = 'komora:model'
  const storedModel = (): string => {
    try {
      return localStorage.getItem(MODEL_KEY) ?? ''
    } catch {
      return ''
    }
  }
  let modelsKnown = $state(false)
  function adoptModels(loaded: Loaded<ModelOption[]>): void {
    models = loaded
    modelsKnown = true
    if (!loaded.ok) return
    const kept = storedModel()
    const known = loaded.data.find((item) => item.id === kept && item.available)
    model = known?.id ?? loaded.data.find((item) => item.active)?.id ?? ''
  }
  void loadModels().then(adoptModels)

  let fast = $state<boolean | null>(null)

  let cartState = $state<Loaded<CartState> | null>(null)
  let quota = $state<Loaded<QuotaState> | null>(null)
  let error = $state<string | null>(null)
  let keyRefused = $state(false)
  const NO_PAYER = 402
  const NO_KEY_NOTE =
    'ця модель працює на твоєму ключі OpenAI: додай ключ у меню або перемкнись на іншу модель, і комора заповниться'
  const KEY_SAVED = 'ключ збережено в цьому браузері — тисни «Зібрати» ще раз'
  const modelWantsKey = $derived(
    models.ok &&
      (models.data.find((item) => item.id === model)?.needsKey ?? false) &&
      !link.llmKey,
  )
  $effect(() => {
    if (!modelWantsKey && pantryFailed === NO_KEY_NOTE) void refreshPantry(true)
    else if (modelWantsKey && pantryFailed === null && pantryLoaded) {
      pantry = []
      pantryFailed = NO_KEY_NOTE
    }
  })

  let debugOpen = $state(localStorage.getItem(DEBUG_KEY) === '1')

  const ONBOARD_KEY = 'komora:onboarded'
  let onboardingOpen = $state(localStorage.getItem(ONBOARD_KEY) !== '1')

  function closeOnboarding() {
    localStorage.setItem(ONBOARD_KEY, '1')
    onboardingOpen = false
  }

  const gated = $derived(link.ready && !link.connected)

  const view = $derived<Screen>(gated && !isDoc(screen) ? 'connect' : screen)

  const TOUR_KEY = 'komora:toured'
  const TOUR_KEYS: Partial<Record<Screen, string>> = {
    start: TOUR_KEY,
    pantry: 'komora:toured-pantry',
  }
  let tourSeen = $state<Record<string, boolean>>({
    [TOUR_KEY]: localStorage.getItem(TOUR_KEY) === '1',
    'komora:toured-pantry': localStorage.getItem('komora:toured-pantry') === '1',
  })
  let tourOpen = $state(false)
  let tourKey = $state(TOUR_KEY)

  function closeTour() {
    localStorage.setItem(tourKey, '1')
    tourSeen = { ...tourSeen, [tourKey]: true }
    tourOpen = false
  }

  $effect(() => {
    if (onboardingOpen || gated || !link.ready) return
    const key = TOUR_KEYS[view]
    if (key === undefined || tourSeen[key]) return
    if (view === 'pantry' && !pantryLoaded) return
    tourKey = key
    tourOpen = true
  })

  let breachOpen = $state(false)
  let breachSeq = $state<number | null>(null)

  $effect(() => {
    if (link.greet === null) return
    breachSeq = link.greet
    breachOpen = true
    greeted()
  })

  let health = $state<Loaded<Health> | null>(null)

  $effect(() => {
    if (!link.ready || !link.backend || health !== null) return
    void loadHealth().then((loaded) => (health = loaded))
  })

  $effect(() => {
    localStorage.setItem(DEBUG_KEY, debugOpen ? '1' : '0')
  })

  $effect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.code !== 'Backquote') return
      const target = event.target as HTMLElement | null
      const typing =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target?.isContentEditable === true
      if (typing) return
      event.preventDefault()
      debugOpen = !debugOpen
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  let mode = $state<BuildRequest['mode']>('week')

  let occasionPeople = $state(4)
  const isOccasion = $derived(mode === 'event')
  let eventStyle = $state<BuildRequest['eventStyle']>(null)

  let shoppingList = $state('')
  let source = $state<BuildRequest['source']>('list')
  let runs = $state<Run[]>([])
  const MAX_DEBUG_RUNS = 6
  let hiddenRuns = $state(0)

  function remember(run: Run) {
    const kept = [...runs, run]
    hiddenRuns += Math.max(0, kept.length - MAX_DEBUG_RUNS)
    runs = kept.slice(-MAX_DEBUG_RUNS)
  }

  function refused(
    what: RunKind,
    request: FailedRun['request'],
    failure: { message: string; status: number | null },
  ) {
    remember({
      kind: 'failed',
      what,
      request,
      status: failure.status,
      message: failure.message,
      at: Date.now(),
    })
  }

  let answers = $state<ClarifyAnswer[]>([])
  let answering = $state<Record<string, string>>({})
  let reasked = $state<string[]>([])
  let budget = $state(1700)
  let budgetSaid = $state(false)
  const BAR_KEY = 'komora:bar-in-week'
  let barInWeek = $state(false)
  try {
    barInWeek = localStorage.getItem(BAR_KEY) === '1'
  } catch {
  }
  function toggleBarInWeek(): void {
    barInWeek = !barInWeek
    try {
      localStorage.setItem(BAR_KEY, barInWeek ? '1' : '0')
    } catch {
    }
  }
  const BUDGET_KEY = 'komora:budget'
  try {
    const kept = Number(localStorage.getItem(BUDGET_KEY))
    if (kept > 0) {
      budget = kept
      budgetSaid = true
    }
  } catch {
  }
  function saveBudget(): void {
    budgetSaid = true
    try {
      localStorage.setItem(BUDGET_KEY, String(budget))
    } catch {
    }
  }
  function adoptTarget(data: Basket): void {
    const agent = data.agentTarget
    if (!agent || agent.refused !== null) return
    budget = Number(agent.target)
  }
  let rules = $state<Exclusion[]>([])
  let rulesNote = $state<string | null>(null)
  /** Окремо від `rulesNote`: це про ЧУЖЕ налаштування, не про свої правила. */
  let profileNote = $state<string | null>(null)
  let draft = $state('')

  /** Ширина цінової вилки авто-заміни. Одне число на весь фронт: воно їде
   *  і в запит, і в підпис ОБОХ тумблерів — на старті й на екрані замін.
   *  Другий тримав свою десятку літералом у розмітці, тобто «одне число»
   *  було двома (#90). Самі межі в гривнях рахує бекенд: гість мусить
   *  бачити ті самі, що прочитає збирач. */
  const AUTO_SWAP_PERCENT = 10

  let autoSwap = $state(autoSwapGiven())

  $effect(() => {
    rememberAutoSwap(autoSwap)
  })

  let delivery = $state(DEFAULT_DELIVERY)
  let deliveryLoaded = $state<Loaded<DeliveryOption[]> | null>(null)
  const deliveryOptions = $derived(deliveryLoaded?.ok ? deliveryLoaded.data : [])

  let place = $state<Place | null>(null)
  let placeNote = $state<string | null>(null)
  let placeResults = $state<PlaceOption[] | null>(null)
  let placeSearching = $state(false)
  let placeSearchNote = $state<string | null>(null)

  let placeOpen = $state(false)
  let placeAsk = $state<PlaceOption | null>(null)

  let basket = $state<Basket | null>(null)
  let cartReady = $state(false)
  let confirmClear = $state(false)
  let clearTimer: ReturnType<typeof setTimeout> | undefined

  let logOpen = $state(false)

  let pantry = $state<PantryItem[]>([])
  let pantrySource = $state<Omit<PantryState, 'items'> | null>(null)
  let pantryLoaded = $state(false)
  let pantryPending = $state<number | null>(null)
  let pantryAddOpen = $state(false)
  let pantryQuery = $state('')

  let bar = $state<BarState | null>(null)

  let once = $state(new Set<string>())

  /** Правки кількості: externalProductId → скільки брати насправді. */
  let qty = $state<Record<string, number>>({})

  let extras = $state<CartLine[]>([])

  let added = $state<string[]>([])

  let swapPolicy = $state<Record<string, SwapPolicy>>({})
  let swapChains = $state<Record<string, Substitute[]>>({})
  let swapsReviewed = $state(false)
  let swapsFromCheckout = $state(false)

  const activeRules = $derived(rules.filter((rule) => rule.active))

  const settings = $derived<Settings>({
    rules,
    budget,
    mode,
    people: isOccasion ? occasionPeople : null,
    delivery,
    list: shoppingList,
    model,
    autoSwap,
    source,
  })

  const naming = $derived({
    delivery: (id: string) =>
      deliveryOptions.find((option) => option.id === id)?.label ?? 'спосіб без назви',
    model: (id: string) =>
      (models.ok ? models.data.find((option) => option.id === id)?.label : null) ?? id,
  })

  let built = $state<Settings | null>(null)
  const signature = $derived(signatureOf(settings))
  const builtWith = $derived(built ? signatureOf(built) : '')
  const stale = $derived(basket !== null && built !== null && signature !== builtWith)
  const staleWhy = $derived(built && stale ? changes(built, settings, naming) : [])
  const staleChip = $derived(staleLabel(staleWhy))
  const touched = $derived(Object.keys(qty).length > 0 || extras.length > 0)

  function toggleRule(id: string) {
    const before = rules
    const target = rules.find((rule) => rule.id === id)
    if (!target || target.permanent) return
    rules = rules.map((rule) => (rule.id === id ? { ...rule, active: !rule.active } : rule))
    askRebuild()
    void keepRule(() => saveRuleSwitch(id, !target.active), before)
  }

  function removeRule(id: string) {
    const before = rules
    const target = rules.find((rule) => rule.id === id)
    if (!target || target.permanent) return
    rules = rules.filter((rule) => rule.id !== id)
    askRebuild()
    void keepRule(() => deleteRule(id), before)
  }

  /**
   * Донести правку до сервера. Вдалось — на екрані те саме, що в базі;
   * ні — екран повертається до стану, який у базі справді є, і каже це.
   */
  async function keepRule(
    work: () => Promise<Loaded<Exclusion[]>>,
    before: Exclusion[],
  ): Promise<void> {
    const loaded = await work()
    if (loaded.ok) {
      settleRules(loaded.data)
      return
    }
    rules = before
    rulesNote = `${loaded.message}. Правило лишилось таким, як було`
  }

  /**
   * Відповідь сервера і є станом — але не для того, що до нього ще не доїхало.
   *
   * Правило, записане поки база мовчала, у відповіді сервера й не з'явиться,
   * тож взяти її цілком означало б знищити його ЧУЖОЮ правкою: гість
   * видаляє одне правило, а зникають два. Тому непідтверджене лишається і
   * тут, і в кеші — до першої вдалої синхронізації.
   */
  function settleRules(own: Exclusion[], keep = rules.filter((rule) => rule.permanent)) {
    const waiting = ruleCache.missing(own, ruleCache.cached())
    rules = [...keep, ...own, ...waiting.map(asRule)]
    ruleCache.remember([...ruleCache.confirmed(own), ...waiting])
    rulesNote = profileNote
  }

  let rebuildAsk = $state(false)

  function askRebuild() {
    if (screen === 'cart' && basket !== null && stale) rebuildAsk = true
  }

  function revertSettings() {
    const snapshot = built
    if (!snapshot) return
    void revertRules(rules, snapshot.rules)
    rules = snapshot.rules
    budget = snapshot.budget
    mode = snapshot.mode
    if (snapshot.people !== null) occasionPeople = snapshot.people
    delivery = snapshot.delivery
    shoppingList = snapshot.list
    model = snapshot.model
    autoSwap = snapshot.autoSwap
    source = snapshot.source
  }

  /**
   * Повернути правила до знімка, за яким зібрано кошик, — і в базі теж.
   *
   * Порівняння за СЛОВАМИ: id доданого правила тимчасовий, поки сервер не
   * відповів, і зійтись зі знімком він не може.
   */
  async function revertRules(before: Exclusion[], after: Exclusion[]): Promise<void> {
    const mine = (list: Exclusion[]) => list.filter((rule) => !rule.permanent)
    const key = ruleCache.labelKey
    const was = mine(before)
    const wanted = mine(after)
    const ops: (() => Promise<Loaded<Exclusion[]>>)[] = []

    for (const rule of was) {
      const same = wanted.find((other) => key(other.label) === key(rule.label))
      if (!same) ops.push(() => deleteRule(rule.id))
      else if (same.active !== rule.active) ops.push(() => saveRuleSwitch(rule.id, same.active))
    }
    for (const rule of wanted) {
      if (!was.some((other) => key(other.label) === key(rule.label))) {
        ops.push(() => saveRule(rule.label, rule.active))
      }
    }

    for (const op of ops) {
      const done = await op()
      if (!done.ok) {
        rulesNote = `${done.message}. На сервері правила лишились як були`
        return
      }
      settleRules(done.data)
    }
  }

  function addRule() {
    const label = ruleCache.clean(draft)
    if (!label) return
    const exists = rules.some(
      (rule) => ruleCache.labelKey(rule.label) === ruleCache.labelKey(label),
    )
    if (!exists) {
      rules = [...rules, { id: ruleCache.localId(label), label, permanent: false, active: true }]
      askRebuild()
      void bringRule(label)
    }
    draft = ''
    closePopovers()
  }

  /**
   * Нове правило на сервер. Відмова НЕ прибирає його з екрана: воно існує
   * лише тут, і зникнути мусить хіба від явного «видалити». Але й мовчати
   * про це не можна — правило, яке гість вважає збереженим, зникне при
   * наступному вході з іншого пристрою.
   */
  async function bringRule(label: string): Promise<void> {
    const saved = await saveRule(label)
    if (saved.ok) {
      settleRules(saved.data)
      return
    }
    ruleCache.remember([
      ...ruleCache.cached().filter((row) => ruleCache.labelKey(row.label) !== ruleCache.labelKey(label)),
      { id: ruleCache.localId(label), label, active: true, pending: true },
    ])
    rulesNote = `${saved.message}. Правило поки лишилось у цьому браузері`
  }

  function withToggled(set: Set<string>, id: string): Set<string> {
    const next = new Set(set)
    if (!next.delete(id)) next.add(id)
    return next
  }

  $effect(() => {
    document.documentElement.dataset.theme = theme.value
  })

  $effect(() => watchDismiss())

  $effect(() => {
    const onPop = () => {
      closePopovers()
      goBack()
    }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  })

  $effect(() => {
    void view
    if (focusPick !== null) return
    window.scrollTo({ top: 0, behavior: 'instant' })
  })

  async function syncRules(): Promise<void> {
    const [profile, own] = await Promise.all([loadProfileRules(), loadOwnRules()])
    const permanent = profile.ok ? profile.data.filter((rule) => rule.permanent) : []
    profileNote = profile.ok ? null : `${profile.message} — обмеження профілю не показані`

    if (!own.ok) {
      const stored = ruleCache.cached()
      rules = [...permanent, ...stored.map(asRule)]
      rulesNote = `${own.message}. Показані правила з цього браузера`
      return
    }

    let server = own.data
    let stalled: string | null = null
    for (const row of ruleCache.missing(server, ruleCache.cached())) {
      const saved = await saveRule(row.label, row.active)
      if (!saved.ok) {
        stalled = saved.message
        break
      }
      server = saved.data
    }
    settleRules(server, permanent)
    if (stalled) rulesNote = `${stalled}. Решта правил поки лишилась у цьому браузері`
  }

  function asRule(row: ruleCache.Cached): Exclusion {
    return { id: row.id, label: row.label, permanent: false, active: row.active }
  }

  $effect(() => {
    void refreshLink()
  })

  const keyGate = $derived(link.ready && link.connected && modelsKnown && modelWantsKey)
  const freeModel = $derived(
    models.ok ? (models.data.find((item) => item.available && !item.needsKey) ?? null) : null,
  )
  function switchModel(id: string): void {
    model = id
    try {
      localStorage.setItem(MODEL_KEY, id)
    } catch {
    }
  }
  $effect(() => {
    if (!link.ready || !link.connected) return
    if (!modelsKnown || keyGate) return
    void syncRules()
    void loadPlace().then((loaded) => {
      if (loaded.ok) {
        place = loaded.data
        placeNote = null
      } else {
        placeNote = loaded.message
      }
    })
    readDeliveryOptions()
    void refreshPantry()
    refreshWanted()
    refreshSavedSwaps()
    refreshCartState()
    refreshQuota()
    void loadModels().then(adoptModels)
  })

  let cartInFlight = false

  let deliveryAsk = 0

  function readDeliveryOptions(): void {
    const ask = ++deliveryAsk
    deliveryLoaded = null
    void loadDeliveryOptions().then((loaded) => {
      if (ask !== deliveryAsk) return
      deliveryLoaded = loaded
      if (!loaded.ok) return
      if (!loaded.data.some((option) => option.id === delivery)) {
        delivery = loaded.data.find((option) => option.available)?.id ?? delivery
      }
    })
  }

  const toll = $derived(quota !== null && quota.ok ? quota.data.toll : null)
  let tollBase = $state<Toll | null>(null)
  let tollBaseSet = $state(false)
  $effect(() => {
    if (tollBaseSet || toll === null) return
    tollBaseSet = true
    tollBase = toll
  })
  const tollRun = $derived(tollSince(toll, tollBase))

  function refreshQuota(): void {
    if (!link.connected) return
    void loadQuota().then((loaded) => (quota = loaded))
  }

  function refreshCartState(): void {
    if (!link.connected || cartInFlight) return
    cartInFlight = true
    void loadCartState().then((loaded) => {
      cartState = loaded
      cartInFlight = false
    })
  }

  $effect(() => {
    const back = () => {
      if (document.visibilityState !== 'visible') return
      refreshCartState()
    }
    document.addEventListener('visibilitychange', back)
    return () => document.removeEventListener('visibilitychange', back)
  })

  async function findPlace(text: string) {
    placeSearching = true
    placeSearchNote = null
    const loaded = await searchPlace(text)
    placeSearching = false
    if (loaded.ok) placeResults = loaded.data
    else {
      placeResults = null
      placeSearchNote = loaded.message
    }
  }

  function askPlace(option: PlaceOption) {
    placeOpen = false
    if (basket === null) {
      void pickPlace(option)
      return
    }
    placeAsk = option
  }

  async function pickPlace(option: PlaceOption) {
    const loaded = await sendPlace(option)
    if (!loaded.ok) {
      placeSearchNote = loaded.message
      return
    }
    place = loaded.data
    placeNote = null
    placeResults = null
    placeSearchNote = null
    readDeliveryOptions()
    void refreshPantry(true)
  }

  function swapDecisions(): SwapDecision[] {
    return (basket?.lines ?? [])
      .filter(
        (line) =>
          line.atRisk ||
          line.chain.length > 0 ||
          line.externalProductId in swapChains ||
          line.externalProductId in swapPolicy,
      )
      .map((line) => ({
        externalProductId: line.externalProductId,
        policy: swapPolicy[line.externalProductId] ?? 'substitute',
        chain: (swapChains[line.externalProductId] ?? line.chain).map(
          (sub) => sub.externalProductId,
        ),
      }))
  }

  function buildRequest(): BuildRequest {
    return {
      source,
      delivery,
      mode,
      occasionPeople: isOccasion ? occasionPeople : null,
      eventStyle: isOccasion ? eventStyle : null,
      progressKey: null,
      budget,
      budgetSaid,
      barInWeek,
      shoppingList: [...parseList(shoppingList), ...added],
      listText: shoppingList,
      keep: extras.map((line) => line.externalProductId),
      swaps: swapDecisions(),
      exclusions: activeRules.filter((rule) => rule.permanent).map((rule) => rule.id),
      rules: activeRules.map((rule) => rule.label),
      model: model || null,
      fast,
      cold: coldRun,
      autoSwap,
      autoSwapPercent: AUTO_SWAP_PERCENT,
      answers,
    }
  }

  let liveSteps = $state<TraceStep[]>([])
  let pantrySteps = $state<TraceStep[]>([])
  let pantryLooping = $state(false)
  /** Петля пішла ПІСЛЯ відповіді гостя -- екран кроків мусить лишитись (#386). */
  let pantryAnswering = $state(false)
  let pantryAnsweringMore = $state(false)
  let pantryDoor = $state<PantryAsk[]>([])
  /** Гість натиснув «Пропустити»: наступні питання чекають за дверима. */
  let pantrySkipped = $state(false)
  let pantryAsked = $state<PantryAsk[]>([])
  let pantrySince = $state<number | null>(null)
  const COLD_KEY = 'komora:cold'
  let coldRun = $state(localStorage.getItem(COLD_KEY) !== '0')
  let pantryCold = $state(false)
  let runKey = $state('')

  function takeAnswer(questionId: string, option: TraceOption): void {
    if (option.style) eventStyle = option.style
    if (option.target !== null) {
      budget = option.target
      budgetSaid = true
    }
    void answerProgress(runKey, questionId, option.id).catch(() => {})
  }

  function watchProgress(key: string, apply: (steps: TraceStep[]) => void): () => void {
    let busy = false
    let seen = 0
    const tick = async () => {
      if (busy) return
      busy = true
      try {
        const got = await readProgress(key)
        if (got.steps.length >= seen) {
          seen = got.steps.length
          apply(got.steps)
        }
      } catch {
      } finally {
        busy = false
      }
    }
    const timer = setInterval(() => void tick(), 500)
    void tick()
    return () => clearInterval(timer)
  }

  async function run(from: BuildRequest['source']) {
    source = from
    error = null
    keyRefused = false
    if (modelWantsKey) {
      error = 'ця модель працює на твоєму ключі OpenAI — додай ключ і збери ще раз'
      keyRefused = true
      return
    }
    navigate('running')

    const progressKey = crypto.randomUUID()
    runKey = progressKey
    const sent = { ...buildRequest(), progressKey }
    thoughts = thoughtsFor(pantry, sent, pantrySource?.source ?? 'receipts')
    elapsed = 0
    liveSteps = []
    const started = performance.now()
    const ticking = setInterval(() => (elapsed = performance.now() - started), 250)
    const stopWatching = watchProgress(progressKey, (steps) => (liveSteps = steps))

    const result = await loadBasket(sent)
    clearInterval(ticking)
    stopWatching()
    liveSteps = []
    refreshQuota()
    if (!result.ok) {
      navigate('start')
      error = result.message
      keyRefused = result.status === NO_PAYER
      refused('build', sent, result)
      if (from === 'cart') refreshCartState()
    } else {
      basket = withoutSkipped(result.data)
      remember({ kind: 'build', request: sent, basket: result.data })
      adoptTarget(result.data)
      built = settings
      once = new Set()
      qty = {}
      swapPolicy = {}
      swapsDirty = false
      swapChains = {}
      swapsReviewed = false
      checkout = null
    carryOver = null
      if (screen === 'running') navigate('cart')
      else cartReady = true
    }
  }

  function uniqueByArticle(lines: CartLine[]): CartLine[] {
    const seen = new Set<string>()
    return lines.filter((line) => {
      if (seen.has(line.externalProductId)) return false
      seen.add(line.externalProductId)
      return true
    })
  }

  function withoutSkipped<T extends { questions: { intent: string }[] }>(next: T): T {
    const skipped = new Set(answers.filter((a) => a.skip).map((a) => a.intent))
    if (skipped.size === 0) return next
    return { ...next, questions: next.questions.filter((q) => !skipped.has(q.intent)) }
  }

  function answerQuestion(next: ClarifyAnswer) {
    answers = [...answers.filter((item) => item.intent !== next.intent), next]
    if (next.skip && basket !== null) {
      basket = {
        ...basket,
        questions: basket.questions.filter((q) => q.intent !== next.intent),
      }
      return
    }
    if (basket !== null) {
      if (next.intent in answering) return
      answering = {
        ...answering,
        [next.intent]: next.slug ?? next.query ?? next.text ?? '',
      }
      reasked = reasked.filter((intent) => intent !== next.intent)
      void mutate({
        kind: 'refill',
        request: { intents: [], answers: [next], model: model || null, fast },
        run: (runId) => sendRefill(runId, [], model || null, [next]),
      }).then((ok) => {
        const rest = { ...answering }
        delete rest[next.intent]
        answering = rest
        if (ok && basket?.questions.some((q) => q.intent === next.intent)) {
          reasked = [...reasked, next.intent]
        }
        refreshQuota()
      })
      return
    }
    void run(source)
  }

  /** Чому комора не прочиталась. `null` -- прочиталась (#166). */
  let pantryFailed = $state<string | null>(null)

  let pantryInFlight: Promise<void> | null = null
  let pantryRun = 0

  let sourceBusy = $state(false)

  let deedNote = $state<string | null>(null)

  async function tellSource(
    work: () => Promise<Loaded<PantryState>>,
    said?: (rows: number, left: number, state: PantryState) => string,
  ): Promise<void> {
    if (sourceBusy) {
      deedNote = 'зачекай -- попередня дія ще не завершилась'
      return
    }
    sourceBusy = true
    deedNote = null
    try {
      const done = await work()
      if (!done.ok) {
        error = done.message
        return
      }
      pantry = done.data.items
      pantryTruth = done.data.items
      pantrySource = done.data
      if (said && done.data.changed !== null) {
        deedNote = said(done.data.changed, done.data.items.length, done.data)
      }
    } finally {
      sourceBusy = false
    }
  }

  function emptyGenerateNote(state: PantryState): string {
    if (state.kinds > 0) {
      return 'нового не знайшлось: усі доведені види вже у твоєму списку'
    }
    if (state.receipts > 0 || state.orders > 0) {
      return (
        "покупки бачу, а видів для списку ще немає: вид з'являється, " +
        'коли він трапився у трьох покупках у різні дні'
      )
    }
    return 'покупок ще не видно -- список поки нема з чого складати'
  }

  function wipeNote(rows: number, left: number): string {
    const wiped = `стерто ${plural(rows, { one: 'рядок', few: 'рядки', many: 'рядків' })} списку`
    if (left === 0) return wiped
    return (
      `${wiped}; на екрані лишилось ${left} — це рядки з чеків: ` +
      'комора рахує їх щоразу заново, і стирати там нема чого'
    )
  }

  let composing = $state(false)

  async function composeShoppingList(): Promise<void> {
    if (sourceBusy) return
    sourceBusy = true
    composing = true
    deedNote = null
    try {
      const done = await nextShoppingList()
      if (!done.ok) {
        error = done.message
        return
      }
      wanted = done.data.rows
      deedNote =
        done.data.changes.length > 0
          ? done.data.changes.join('; ')
          : `список на наступну покупку без змін: ${plural(done.data.rows.length, {
              one: 'рядок',
              few: 'рядки',
              many: 'рядків',
            })}`
    } finally {
      sourceBusy = false
      composing = false
    }
  }

  let barBusy = $state(false)

  let wanted = $state<WantedRow[]>([])
  let wantedBusy = $state(false)

  async function tellWanted(work: () => Promise<Loaded<WantedRow[]>>): Promise<void> {
    if (wantedBusy) return
    wantedBusy = true
    try {
      const said = await work()
      if (!said.ok) {
        error = said.message
        return
      }
      wanted = said.data
    } finally {
      wantedBusy = false
    }
  }

  function keepFromPantry(label: string): void {
    const mark = (yes: boolean) =>
      (pantry = pantry.map((row) => (row.label === label ? { ...row, wanted: yes } : row)))
    mark(true)
    void (async () => {
      const said = await keepWanted(label)
      if (!said.ok) {
        mark(false)
        error = said.message
        return
      }
      wanted = said.data
    })()
  }

  let rememberSwaps = $state(false)
  let savedSwaps = $state<SavedSwap[]>([])
  let swapsFocus = $state<'urgent' | 'all'>('all')
  let savedSwapsBusy = $state(false)

  function refreshSavedSwaps(): void {
    void loadSavedSwaps().then((got) => {
      if (got.ok) savedSwaps = got.data
    })
  }

  async function forgetSavedSwap(id: string): Promise<void> {
    if (savedSwapsBusy) return
    savedSwapsBusy = true
    try {
      const said = await dropSavedSwap(id)
      if (!said.ok) {
        error = said.message
        return
      }
      savedSwaps = said.data
    } finally {
      savedSwapsBusy = false
    }
  }

  function refreshWanted(): void {
    void loadWanted().then((got) => {
      if (got.ok) wanted = got.data
    })
  }

  let barDeed = $state<string | null>(null)

  async function tellBar(
    work: () => Promise<Loaded<BarState>>,
    said?: (rows: number) => string,
  ): Promise<void> {
    if (barBusy) return
    barBusy = true
    barDeed = null
    try {
      const done = await work()
      if (!done.ok) {
        error = done.message
        return
      }
      bar = done.data
      if (said && done.data.changed !== null) barDeed = said(done.data.changed)
    } finally {
      barBusy = false
    }
  }

  function refreshPantry(force = false): Promise<void> {
    if (pantryInFlight !== null && !force) return pantryInFlight
    const run = ++pantryRun
    pantryLoaded = false
    pantryPending = Date.now()
    pantrySince = pantryPending
    pantryCold = coldRun && localStorage.getItem(PANTRY_SEEN) !== '1'
    if (modelWantsKey) {
      pantryFailed = NO_KEY_NOTE
      pantryLoaded = true
      pantryPending = null
      pantryInFlight = null
      return Promise.resolve()
    }
    const asked = loadPantry(pantryCold).then((loaded) => {
      if (run !== pantryRun) return
      if (loaded.ok && modelWantsKey) {
        pantryFailed = NO_KEY_NOTE
      } else if (loaded.ok) {
        pantry = loaded.data.items
        pantrySource = loaded.data
        if (!budgetSaid && loaded.data.spend !== null) budget = loaded.data.spend.target
        pantryTruth = loaded.data.items
        pantryFailed = null
        void refinePantryState(run)
      } else {
        error = loaded.message
        pantryFailed = loaded.message
      }
      pantryLoaded = true
      pantryPending = null
      pantryInFlight = null
      void peekBar()
    })
    pantryInFlight = asked
    return asked
  }

  /**
   * Що рядок КАЖЕ гостю -- рівно те, що петля вміє змінити (#330).
   *
   * Порівнюються не об'єкти, а чотири поля: мітка виду, речення глузду,
   * цикл і питання на рядку. Решта в рядку від петлі не залежить, і
   * порівняння цілих об'єктів дало б «змінилось» на кожній відповіді.
   */
  const said = (rows: PantryItem[]): string =>
    rows.map((row) => `${row.id}|${row.label}|${row.sanity}|${row.cycleDays}|${row.ask}`).join(';')

  /**
   * Петля комори: те, чого першій відповіді бракувало (#330).
   *
   * Рядки лягають НА МІСЦЕ -- порядок, який гість уже бачить, лишається
   * той самий: він міняється при відкритті, а не під пальцем (#145). Зниклі
   * (мітка злила близнюків) знімаються, нові стають у хвіст: переставити
   * список під рукою гостя гірше, ніж показати новий рядок останнім.
   *
   * Відмова тут мовчазна навмисно: комора вже намальована і вже правдива, а
   * червоний банер на місці уточнення читався б як поломка комори. Що петля
   * не приїхала, каже порожній `refined` і трейс.
   */
  async function answerPantry(
    answers: Record<string, number>,
    more = false,
  ): Promise<void> {
    if (Object.keys(answers).length === 0) {
      pantryDoor = pantryAsked
      pantryAsked = []
      pantrySkipped = true
      return
    }
    const said = pantryAsked.filter((probe) => probe.label in answers)
    const covers = Object.fromEntries(said.map((probe) => [probe.label, probe.covers]))
    const kinds: Record<string, string> = {}
    for (const probe of said) {
      if (probe.kind) kinds[probe.label] = probe.kind
      probe.covers.forEach((label, at) => {
        const key = probe.coverKinds?.[at]
        if (key) kinds[label] = key
      })
    }
    pantryAsked = []
    pantrySkipped = !more
    pantryAnswering = true
    pantryAnsweringMore = more
    pantrySince = pantrySince ?? Date.now()
    pantryRun += 1
    const run = pantryRun
    try {
      await refinePantryState(run, answers, covers, kinds, more)
    } finally {
      pantryAnswering = false
      pantryAnsweringMore = false
      if (run === pantryRun && pantryAsked.length === 0) pantrySince = null
    }
  }

  /**
   * Зшити журнал кроків, не показавши той самий крок двічі (#302).
   *
   * Номер наскрізний і видає його СЕРВЕР в одному місці (`stitch`), тож саме
   * він і є ознакою «це той самий крок». Порівнювати текст не можна: два
   * оберти петлі законно кажуть однакову фразу, і злиття за нею з'їло б
   * роботу, яка справді сталась двічі.
   */
  function joinSteps(before: TraceStep[], fresh: TraceStep[]): TraceStep[] {
    const seen = new Set(before.map((step) => step.seq))
    return [...before, ...fresh.filter((step) => !seen.has(step.seq))]
  }

  async function refinePantryState(
    run: number,
    answers: Record<string, number> = {},
    covers: Record<string, string[]> = {},
    kinds: Record<string, string> = {},
    more = false,
  ): Promise<void> {
    const progressKey = crypto.randomUUID()
    if (!pantryAnswering) pantrySteps = [...(pantrySource?.trace ?? [])]
    const before = pantrySteps
    pantryLooping = true
    const stopWatching = watchProgress(progressKey, (steps) => {
      if (run === pantryRun) pantrySteps = joinSteps(before, steps)
    })
    const shown = pantrySource?.trace ?? []
    const seen = Math.max(shown.length, pantrySteps.length)
    const done = await loopPantry(
      progressKey,
      pantryCold,
      fast,
      answers,
      covers,
      kinds,
      seen,
      more,
    )
    stopWatching()
    refreshQuota()
    if (run === pantryRun) pantryLooping = false
    if (run === pantryRun && done.ok) {
      const fresh = done.data.asked ?? []
      if (pantrySkipped) {
        pantryDoor = fresh
        pantryAsked = []
      } else {
        pantryAsked = fresh
      }
    }
    if (run === pantryRun && pantryAsked.length === 0) pantrySince = null
    if (run !== pantryRun || !done.ok) return
    const fresh = new Map(done.data.items.map((row) => [row.id, row]))
    const kept = pantry
      .filter((row) => fresh.has(row.id))
      .map((row) => fresh.get(row.id) as PantryItem)
    const added = done.data.items.filter((row) => !pantry.some((old) => old.id === row.id))
    const next = [...new Map([...kept, ...added].map((row) => [row.id, row])).values()]
    if (said(next) !== said(pantry)) {
      pantry = next
      pantryTruth = pantry
    }
    pantrySource = { ...done.data, trace: [...shown, ...done.data.trace] }
  }

  async function openPantry() {
    screen = 'pantry'
    if (pantryFailed === null && (pantry.length > 0 || pantryLoaded)) return
    await refreshPantry(pantryInFlight === null)
  }

  async function peekBar() {
    if (bar) return
    const loaded = await loadBar()
    if (loaded.ok) bar = loaded.data
  }

  async function openBar() {
    screen = 'bar'
    if (bar) return
    const loaded = await loadBar()
    if (loaded.ok) bar = loaded.data
    else error = loaded.message
  }

  let focusPick = $state<string | null>(null)

  function showPick(id: string) {
    focusPick = id
    navigate('trace')
  }

  let trail = $state<Screen[]>([])
  const backTo = $derived(trail.at(-1) ?? 'start')
  const backHere = $derived(backLabel(backTo))

  function navigate(next: Screen) {
    error = null
    keyRefused = false
    closePopovers()
    const to = next === 'cart' && basket === null ? 'start' : next
    const deeper = pushed(trail, screen, to)
    if (deeper.length > trail.length) history.pushState({ komora: deeper.length }, '')
    trail = deeper
    show(to)
  }

  /** «Назад» — рівно один крок сліду. Порожній слід веде на початок. */
  function goBack() {
    const step = popped(trail)
    trail = step.trail
    show(step.to)
  }

  function show(next: Screen) {
    if (next === 'cart' || next === 'running') cartReady = false
    if (next !== 'swaps') swapsFromCheckout = false
    if (next !== 'trace') focusPick = null
    if (next === 'pantry') void openPantry()
    else if (next === 'bar') void openBar()
    else screen = next
  }

  function clearAll() {
    if (!confirmClear) {
      confirmClear = true
      clearTimeout(clearTimer)
      clearTimer = setTimeout(() => (confirmClear = false), 3500)
      return
    }
    clearTimeout(clearTimer)
    confirmClear = false
    const all = [...(basket?.lines ?? []), ...extras].map((line) => line.externalProductId)
    void (async () => {
      for (const id of all) await correct(id, 'still_have')
    })()
  }

  let pantryQueue = new Map<string, PantryEdit>()
  let pantryBusy = $state(new Set<string>())
  let pantrySettle: ReturnType<typeof setTimeout> | undefined
  let pantryPump: Promise<void> | null = null
  let pantryTruth: PantryItem[] = []

  function tellPantry(id: string, edit: PantryEdit, wait = false) {
    error = null
    pantryQueue.set(id, edit)
    pantryBusy = new Set([...pantryBusy, id])
    clearTimeout(pantrySettle)
    if (wait) pantrySettle = setTimeout(() => void pumpPantry(), SETTLE_MS)
    else void pumpPantry()
  }

  async function pumpPantry(): Promise<void> {
    if (pantryPump !== null) return pantryPump
    const drain = async () => {
      while (pantryQueue.size > 0) {
        const [id, edit] = pantryQueue.entries().next().value as [string, PantryEdit]
        pantryQueue.delete(id)
        const said = await sendPantryMark(
          id,
          edit.action,
          edit.qty,
          edit.days,
          edit.group,
          edit.chain,
        )
        if (!pantryQueue.has(id)) {
          const rest = new Set(pantryBusy)
          rest.delete(id)
          pantryBusy = rest
        }
        if (!said.ok) {
          error = said.message
          const was = pantryTruth.find((row) => row.id === id)
          if (was) pantry = pantry.map((row) => (row.id === id ? was : row))
          continue
        }
        pantryTruth = said.data.items
        pantry = keepOrder(said.data.items, orderOf(pantry))
        pantrySource = said.data
        pantryLoaded = true
      }
    }
    pantryPump = drain().finally(() => (pantryPump = null))
    return pantryPump
  }

  function sayBought(id: string, qty: number | null): void {
    if (qty !== null) pantry = withQty(pantry, id, qty)
    tellPantry(
      id,
      qty === null
        ? { action: 'bought', qty: 0, days: 0 }
        : { action: 'qty', qty, days: 0 },
    )
  }

  function adjustPantryQty(id: string, delta: number) {
    const item = pantry.find((row) => row.id === id)
    if (!item || item.qty === null) return
    const next = stepped(item.qty, delta, pantryStep(item.unit))
    pantry = withQty(pantry, id, next)
    tellPantry(id, { action: 'qty', qty: next, days: 0 }, true)
  }

  function addPantryItem(label: string) {
    const name = label.trim()
    if (!name) return
    const exists = pantry.some((item) => item.label.toLowerCase() === name.toLowerCase())
    if (exists) {
      error = `«${name}» уже в коморі — знайди його пошуком`
      return
    }
    pantry = [
      {
        id: `manual:${name}`,
        label: name,
        writtenAs: [],
        keeps: null,
        group: null,
        aisle: null,
        parts: [],
        mandate: null,
        wanted: false,
        qty: null,
        named: false,
        usualQty: null,
        sanity: null,
        trust: '',
        ask: false,
        leftRatio: null,
        daysLeft: null,
        cycleDays: null,
        cycleSaid: false,
        unit: '',
        state: 'додано вручну',
        runningOut: false,
        promo: null,
        arrived: null,
        usual: null,
        source: 'manual',
        imageUrl: null,
      },
      ...pantry,
    ]
    void fillPantryUnit(name)
  }

  async function fillPantryUnit(name: string) {
    const temporary = `manual:${name}`
    const resolved = await resolvePantryUnit(name)
    if (!resolved.ok) {
      const local = resolved.status === 503
      pantry = pantry.map((item) =>
        item.id === temporary
          ? {
              ...item,
              state: local
                ? 'додано вручну · поки лише в цій вкладці'
                : 'додано вручну · чеки не прочитались',
            }
          : item,
      )
      return
    }
    const row = resolved.data
    pantry = [row, ...pantry.filter((item) => item.id !== temporary && item.id !== row.id)]
  }

  async function forgetPantryRow(id: string) {
    const dropped = await dropPantryItem(id)
    if (!dropped.ok) {
      error = dropped.message
      return
    }
    pantry = pantry.filter((item) => item.id !== id)
  }

  function addToPantry() {
    const names = parseList(pantryQuery)
    if (names.length === 0) return
    for (const name of names) addPantryItem(name)
    pantryQuery = ''
    pantryAddOpen = false
  }

  let checkout = $state<CheckoutResult | null>(null)
  let checkingOut = $state(false)
  let carryOver = $state<CartCarryOver | null>(null)

  type Mutation = {
    [K in RunKind]: {
      kind: K
      request: Extract<DoneRun, { kind: K }>['request']
      run: (runId: string) => Promise<Loaded<Basket>>
      done: (ok: boolean) => void
    }
  }[RunKind]

  let basketQueue: Mutation[] = []
  let basketBusy = $state(false)

  function mutate<K extends RunKind>(job: {
    kind: K
    request: Extract<DoneRun, { kind: K }>['request']
    run: (runId: string) => Promise<Loaded<Basket>>
  }): Promise<boolean> {
    return new Promise<boolean>((done) => {
      basketQueue.push({ ...job, done } as Mutation)
      void drainBasket()
    })
  }

  async function drainBasket(): Promise<void> {
    if (basketBusy) return
    basketBusy = true
    try {
      while (basketQueue.length > 0) {
        const job = basketQueue.shift() as Mutation
        if (!basket) {
          job.done(false)
          continue
        }
        error = null
        keyRefused = false
        const result = await job.run(basket.runId)
        if (!result.ok) {
          error = result.message
          keyRefused = result.status === NO_PAYER
          refused(job.kind, job.request, result)
          job.done(false)
          continue
        }
        basket = withoutSkipped(result.data)
        adoptTarget(result.data)
        remember({
          kind: job.kind,
          request: job.request,
          basket: result.data,
        } as DoneRun)
        built = settings
        checkout = null
        carryOver = null
        job.done(true)
      }
    } finally {
      basketBusy = false
    }
  }

  function takeCheaperLine(article: string, to: string): Promise<boolean> {
    return mutate({
      kind: 'cheaper',
      request: { externalProductId: article, to },
      run: (runId) => sendCheaper(runId, article, to),
    })
  }

  function correct(
    id: string,
    action: 'still_have' | 'ran_out_earlier' | 'never_again',
  ): Promise<boolean> {
    if (extras.some((line) => line.externalProductId === id)) {
      if (action !== 'ran_out_earlier') extras = extras.filter((l) => l.externalProductId !== id)
      return Promise.resolve(true)
    }
    return mutate({
      kind: 'correction',
      request: { externalProductId: id, action },
      run: (runId) => sendCorrection(runId, id, action),
    })
  }


  function pickAnswer(intent: string, pick: ClarifyPick): Promise<boolean> {
    return mutate({
      kind: 'pick',
      request: { intent, externalProductId: pick.externalProductId },
      run: (runId) => sendPick(runId, intent, pick.externalProductId),
    })
  }

  async function refill(intents: string[]): Promise<boolean> {
    const ok = await mutate({
      kind: 'refill',
      request: { intents, answers: [], model: model || null, fast },
      run: (runId) => sendRefill(runId, intents, model || null),
    })
    if (ok) added = [...added, ...intents]
    refreshQuota()
    return ok
  }

  const swapsStep = $derived(
    basket !== null &&
      !swapsReviewed &&
      swapsToReview(
        [...basket.lines, ...extras].filter((line) => line.reason !== 'at_home'),
        basket.feedback,
      ),
  )

  let swapsDirty = $state(false)
  let swapsSyncing = $state(false)

  async function syncSwaps(): Promise<boolean> {
    if (!basket || !swapsDirty || swapsSyncing) return true
    swapsSyncing = true
    const sent = { swaps: swapDecisions(), remember: rememberSwaps }
    const ok = await mutate({
      kind: 'swaps',
      request: sent,
      run: (runId) => sendSwaps(runId, sent.swaps, sent.remember),
    })
    swapsSyncing = false
    if (!ok) return false
    swapsDirty = false
    if (sent.remember) refreshSavedSwaps()
    return true
  }

  async function confirmSwaps() {
    if (!(await syncSwaps())) return
    swapsReviewed = true
    goBack()
    void submitCheckout()
  }

  async function submitCheckout(existing?: CarryOverState) {
    if (!basket || checkingOut) return
    if (!(await syncSwaps())) return
    if (swapsStep) {
      swapsFromCheckout = true
      navigate('swaps')
      return
    }
    checkingOut = true
    error = null
    const result = await sendCheckout(
      basket.runId,
      existing,
      Object.keys(qty).length > 0 ? qty : undefined,
      extras.length > 0
        ? extras.map((line) => ({
            externalProductId: line.externalProductId,
            qty: qty[line.externalProductId] ?? line.qty,
            name: line.name,
          }))
        : undefined,
      model || null,
      fast,
    )
    checkingOut = false
    if (!result.ok) {
      error = result.message
      return
    }
    if (result.data.carryOver?.state === 'asking') {
      carryOver = result.data.carryOver
      return
    }
    carryOver = null
    checkout = result.data
    if (result.data.basket) basket = withoutSkipped(result.data.basket)
  }
</script>

<div class="page">
  <div class="app">
    <div class="wash wash-a" aria-hidden="true"></div>
    <div class="wash wash-b" aria-hidden="true"></div>

    <Chrome
      screen={view}
      {model}
      {models}
      {today}
      {trail}
      hasBasket={basket !== null}
      {cartReady}
      debugOn={debugOpen}
      coldOn={coldRun}
      onCold={(on) => {
        coldRun = on
        localStorage.setItem(COLD_KEY, on ? '1' : '0')
        void refreshPantry(true)
      }}
      llmKey={link.llmKey}
      {fast}
      onModel={(id, keepOpen) => {
        model = id
        try {
          localStorage.setItem(MODEL_KEY, id)
        } catch {
        }
        fast = null
        if (keyRefused) {
          keyRefused = false
          error = null
        }
        if (!keepOpen) closePopovers()
      }}
      onFast={(on) => (fast = on)}
      onKey={saveLlmKey}
      onForgetKey={() => void forgetLlmKey()}
      onNavigate={navigate}
      onDebug={() => {
        debugOpen = !debugOpen
        closePopovers()
      }}
      onAbout={() => {
        onboardingOpen = true
        closePopovers()
      }}
      onLogout={() => {
        closePopovers()
        localStorage.removeItem(PANTRY_SEEN)
        localStorage.removeItem(COLD_KEY)
        coldRun = true
        void disconnect()
      }}
      onBreach={() => {
        closePopovers()
        breachSeq = null
        breachOpen = true
      }}
      onTour={() => {
        closePopovers()
        tourKey = TOUR_KEYS[view] ?? TOUR_KEY
        tourOpen = true
      }}
    />

    {#if error && (link.connected || error !== link.note)}
      <div class="error" role="alert">
        <p class="error-text">{keyRefused && link.llmKey ? KEY_SAVED : error}</p>
        {#if keyRefused && !link.llmKey}
          <KeyForm onKey={saveLlmKey} />
        {/if}
      </div>
    {/if}

    {#if isDoc(view)}
      <Doc id={view} label={backHere} onBack={goBack} />
    {:else if keyGate}
      <section class="key-gate" data-testid="key-gate">
        <h2>Потрібен ключ</h2>
        <p>
          Обрана модель працює на твоєму ключі OpenAI. Додай ключ або перемкнись на
          модель без ключа, і ПанTry почне з комори.
        </p>
        <KeyForm onKey={saveLlmKey} />
        {#if freeModel}
          <button class="secondary" type="button" onclick={() => switchModel(freeModel.id)}>
            Перемкнутись на {freeModel.label}
          </button>
        {/if}
      </section>
    {:else if view === 'connect'}
      <Connect label={backHere} onBack={goBack} />
    {:else if view === 'start'}
      <Start
        {mode}
        {rules}
        {rulesNote}
        {pantryLoaded}
        {pantryPending}
        {pantrySource}
        {pantryFailed}
        onPantryRetry={() => void refreshPantry(true)}
        {deliveryLoaded}
        {delivery}
        {place}
        {placeNote}
        {placeResults}
        {placeSearching}
        {placeSearchNote}
        onPlaceSearch={findPlace}
        onPlaceChoose={pickPlace}
        onDeliveryRetry={readDeliveryOptions}
        {budget}
        spend={pantrySource?.spend ?? null}
        {draft}
        {pantry}
        list={shoppingList}
        {wanted}
        {wantedBusy}
        onWantedAdd={(text) => {
          const rows = parseList(text)
          if (rows.length === 0) return
          shoppingList = ''
          void (async () => {
            for (const row of rows) await tellWanted(() => keepWanted(row))
          })()
        }}
        onWantedDrop={(id) => void tellWanted(() => dropWanted(id))}
        onWantedHome={(row) =>
          void tellWanted(() => keepWanted(row.label, !row.atHome))}
        barCount={extras.filter((line) => line.reason === 'occasion').length}
        drinkKinds={bar ? bar.items.length : null}
        people={occasionPeople}
        onPeople={(value) => (occasionPeople = value)}
        onMode={(id) => (mode = id)}
        onDelivery={(id) => (delivery = id)}
        onBar={() => navigate('bar')}
        onPantry={() => navigate('pantry')}
        onList={(value) => {
          shoppingList = value
          answers = []
        }}
        onToggleRule={toggleRule}
        onRemoveRule={removeRule}
        onDraft={(value) => (draft = value)}
        onAddRule={addRule}
        onBudget={(value) => {
          budget = value
          budgetSaid = true
        }}
        onSave={saveBudget}
        {autoSwap}
        onAutoSwap={() => (autoSwap = !autoSwap)}
        {barInWeek}
        onBarInWeek={toggleBarInWeek}
        {cartState}
        {quota}
        looping={pantryLooping}
        onRun={() => run('list')}
        onRunCart={() => run('cart')}
      />
    {:else if view === 'running'}
      <Running
        {elapsed}
        {thoughts}
        steps={liveSteps}
        journal={debugOpen}
        onAnswer={takeAnswer}
      />
    {:else if view === 'cart' && basket}
      <Cart
        {basket}
        {once}
        {qty}
        {extras}
        {mode}
        {rules}
        {rulesNote}
        {deliveryOptions}
        {deliveryLoaded}
        onDeliveryRetry={readDeliveryOptions}
        {delivery}
        {place}
        {budget}
        spend={pantrySource?.spend ?? null}
        {pantrySource}
        {draft}
        {stale}
        staleLabel={staleChip}
        {confirmClear}
        {checkout}
        {checkingOut}
        {carryOver}
        {touched}
        onCheckout={() => void submitCheckout()}
        onRebuild={() => void run(source)}
        onKeepBudget={(named) => {
          budget = named
          budgetSaid = true
          void run(source)
        }}
        onCarryOver={(existing) => void submitCheckout(existing)}
        onToggleOnce={(id) => (once = withToggled(once, id))}
        onRemove={(id) => void correct(id, 'still_have')}
        onAdd={(id) => void correct(id, 'ran_out_earlier')}
        onQty={(id, next) => (qty = { ...qty, [id]: next })}
        onExtra={(items) => (extras = [...extras, ...items])}
        onClearAll={clearAll}
        onRestore={() => void run(source)}
        onToggleRule={toggleRule}
        onRemoveRule={removeRule}
        onDraft={(value) => (draft = value)}
        onAddRule={addRule}
        onBudget={(value) => {
          budget = value
          budgetSaid = true
        }}
        onSave={saveBudget}
        onDelivery={(id) => (delivery = id)}
        onStale={() => (rebuildAsk = true)}
        onAnswer={answerQuestion}
        onPick={pickAnswer}
        onSwaps={(focus) => {
          swapsFocus = focus ?? 'all'
          navigate('swaps')
        }}
        onCheaper={(article, to) => void takeCheaperLine(article, to)}
        onTrace={() => navigate('trace')}
        onWhy={showPick}
        onPlace={() => (placeOpen = true)}
        refilling={basketBusy}
        {answering}
        {reasked}
        onRefill={(intents) => void refill(intents)}
      />
    {:else if view === 'swaps' && basket}
      <Swaps
        focus={swapsFocus}
        lines={uniqueByArticle([...basket.lines, ...extras]).filter(
          (line) => line.reason !== 'at_home',
        )}
        feedback={basket.feedback}
        confirming={swapsStep && swapsFromCheckout}
        onConfirm={confirmSwaps}
        policy={swapPolicy}
        chains={swapChains}
        remember={rememberSwaps}
        onRemember={() => {
          rememberSwaps = !rememberSwaps
          swapsDirty = true
        }}
        saved={savedSwaps}
        savedBusy={savedSwapsBusy}
        onForget={(id) => void forgetSavedSwap(id)}
        {autoSwap}
        onAutoSwap={() => (autoSwap = !autoSwap)}
        onPolicy={(id, value) => {
          swapPolicy = { ...swapPolicy, [id]: value }
          swapsDirty = true
        }}
        onChain={(id, chain) => {
          swapChains = { ...swapChains, [id]: chain }
          swapsDirty = true
        }}
        {stale}
        {staleWhy}
        onRebuild={() => run(source)}
        onOptions={(id, text) =>
          basket
            ? loadSwapOptions(basket.runId, id, text)
            : Promise.resolve({ ok: false as const, message: 'кошик ще не зібраний', status: null })}
        onBack={() => {
          void syncSwaps()
          goBack()
        }}
      />
    {:else if view === 'trace' && basket}
      <Trace
        {basket}
        {extras}
        focus={focusPick}
        {logOpen}
        debug={debugOpen}
        {toll}
        onToggleLog={() => (logOpen = !logOpen)}
        onBack={goBack}
      />
    {:else if view === 'pantry'}
      <Pantry
        items={pantry}
        {toll}
        loaded={pantryLoaded}
        failed={pantryFailed}
        onRetry={() => void refreshPantry(true)}
        source={pantrySource}
        pending={pantryPending}
        debug={debugOpen}
        steps={pantrySteps}
        looping={pantryLooping}
        answering={pantryAnswering}
        answeringMore={pantryAnsweringMore}
        asked={pantryAsked}
        door={pantryDoor}
        onDoor={() => {
          pantryAsked = pantryDoor
          pantryDoor = []
          pantrySkipped = false
        }}
        onAnswer={answerPantry}
        since={pantrySince}
        addOpen={pantryAddOpen}
        query={pantryQuery}
        onQuery={(value) => (pantryQuery = value)}
        onAddToggle={() => {
          pantryAddOpen = !pantryAddOpen
          pantryQuery = ''
        }}
        onAddNamed={(label) => {
          pantryAddOpen = true
          pantryQuery = label
        }}
        onAdd={addToPantry}
        onAdjust={adjustPantryQty}
        busy={pantryBusy}
        onBought={(id, qty) => sayBought(id, qty)}
        onCycle={(id, days) =>
          tellPantry(
            id,
            days === null
              ? { action: 'forget_cycle', qty: 0, days: 0 }
              : { action: 'cycle', qty: 0, days },
          )}
        onForget={(id) => void forgetPantryRow(id)}
        onHide={(id) => tellPantry(id, { action: 'hide', qty: 0, days: 0 })}
        onMandate={(id, chain) =>
          tellPantry(id, {
            action: chain.length === 0 ? 'forget_mandate' : 'mandate',
            qty: 0,
            days: 0,
            chain,
          })}
        onUnhide={(label) => tellPantry(label, { action: 'unhide', qty: 0, days: 0 })}
        onSplit={(intent) =>
          tellPantry(intent, { action: 'split', qty: 0, days: 0, group: intent })}
        onUnsplit={(intent) =>
          tellPantry(intent, { action: 'unsplit', qty: 0, days: 0, group: intent })}
        onToList={keepFromPantry}
        onSource={(mode) => void tellSource(() => setPantrySource(mode))}
        deed={deedNote}
        {composing}
        onNextList={() => void composeShoppingList()}
        onGenerate={() =>
          void tellSource(buildPantryFromPurchases, (rows, _left, state) =>
            rows > 0
              ? `склав список із покупок: ${rows} ${plural(rows, {
                  one: 'вид',
                  few: 'види',
                  many: 'видів',
                })}`
              : emptyGenerateNote(state),
          )}
        onWipe={() =>
          void tellSource(clearPantryList, (rows, left) =>
            rows > 0
              ? wipeNote(rows, left)
              : 'у списку не було жодного дописаного рядка — стирати не було чого',
          )}
        {sourceBusy}
        backLabel={backHere}
        onBack={goBack}
      />
    {:else if view === 'bar'}
      <Bar
        {bar}
        added={new Set(extras.map((line) => line.externalProductId))}
        {qty}
        {mode}
        showBack={!inTabs('bar', trail)}
        onMode={(id) => (mode = id)}
        onAdd={(line) => (extras = [...extras, line])}
        onRemove={(id) => {
          extras = extras.filter((l) => l.externalProductId !== id)
          const { [id]: _dropped, ...restQty } = qty
          qty = restQty
        }}
        onQty={(id, next) => (qty = { ...qty, [id]: next })}
        onSource={(mode) => void tellBar(() => setBarSource(mode))}
        onGenerate={() =>
          void tellBar(buildBarFromPurchases, (rows) =>
            rows > 0
              ? `склав бар із покупок: ${rows} ${plural(rows, {
                  one: 'вид',
                  few: 'види',
                  many: 'видів',
                })}`
              : 'у покупках не знайшлось напоїв, які можна додати',
          )}
        onWipe={() =>
          void tellBar(clearBarList, (rows) =>
            rows > 0
              ? `стерто ${plural(rows, { one: 'рядок', few: 'рядки', many: 'рядків' })}`
              : 'у барі не було жодного дописаного рядка — стирати не було чого',
          )}
        deed={barDeed}
        onAddKind={(label) => void tellBar(() => addBarKind(label))}
        onForget={(id) => void tellBar(() => dropBarKind(id))}
        onGroup={(label, kind) => void tellBar(() => setBarGroup(label, kind))}
        sourceBusy={barBusy}
        backLabel={backHere}
        onBack={goBack}
      />
    {/if}

    {#if placeOpen}
      <PlacePicker
        {place}
        results={placeResults}
        searching={placeSearching}
        searchNote={placeSearchNote}
        onSearch={findPlace}
        onChoose={askPlace}
        onClose={() => (placeOpen = false)}
      />
    {/if}

    {#if placeAsk}
      <Modal label="Змінити адресу?">
        <p class="ask-text">
          {placeAsk.label} — це інший магазин, а з ним інші ціни, залишки й
          асортимент. Перезберу кошик під нову адресу і перевірю кожну з
          {plural(basket?.lines.filter(isBuying).length ?? 0, {
            one: 'позиції',
            few: 'позицій',
            many: 'позицій',
          })}.
        </p>
        <div class="ask-actions">
          <button class="ask-later" type="button" onclick={() => (placeAsk = null)}>
            Лишити стару
          </button>
          <button
            class="ask-go"
            type="button"
            onclick={() => {
              const chosen = placeAsk
              placeAsk = null
              if (chosen) void pickPlace(chosen).then(() => run(source))
            }}
          >
            Змінити і перезібрати
          </button>
        </div>
      </Modal>
    {/if}

    {#if rebuildAsk}
      <Modal label="Перезібрати кошик?">
        <p class="ask-text">
          Кошик зібрано за іншими налаштуваннями. Ось що змінилось після
          збірки:
        </p>
        <ul class="ask-diff">
          {#each staleWhy as line (line)}
            <li>{line}</li>
          {/each}
        </ul>
        <p class="ask-text">
          Перезібрати з цим? Агент перерішить задачу цілком — не просто
          викине позиції, а перебалансує список.
        </p>
        <div class="ask-actions">
          <button
            class="ask-later"
            type="button"
            onclick={() => {
              rebuildAsk = false
              revertSettings()
            }}
          >
            Прибрати зміну
          </button>
          <button
            class="ask-go"
            type="button"
            onclick={() => {
              rebuildAsk = false
              void run(source)
            }}
          >
            Перезібрати
          </button>
        </div>
        <button class="ask-skip" type="button" onclick={() => (rebuildAsk = false)}>
          Вирішу пізніше
        </button>
      </Modal>
    {/if}
  </div>

  <Onboarding open={onboardingOpen} onDone={closeOnboarding} />

  <Tour open={tourOpen} onClose={closeTour} />

  <Breach open={breachOpen} seq={breachSeq} onClose={() => (breachOpen = false)} />

  <Debug
    open={debugOpen}
    screen={view}
    live={liveSteps}
    pantry={pantrySteps}
    spent={tollRun}
    spentLogin={toll}
    {model}
    {models}
    {signature}
    {builtWith}
    {stale}
    {basket}
    {runs}
    hidden={hiddenRuns}
    {error}
    {health}
    onClose={() => (debugOpen = false)}
  />
</div>

<style>
  .page {
    min-height: 100dvh;
    display: flex;
    justify-content: center;
    background: var(--page-bg);
  }

  .app {
    width: 100%;
    max-width: var(--col);
    position: relative;
    min-height: 100dvh;
    display: flex;
    flex-direction: column;
    background: var(--app-bg);
    overflow-x: clip;
  }

  .wash {
    position: absolute;
    border-radius: 50%;
    pointer-events: none;
    z-index: 0;
  }

  .wash-a {
    top: -120px;
    right: -90px;
    width: 320px;
    height: 320px;
    background: radial-gradient(circle, rgb(240 169 59 / 0.2), rgb(240 169 59 / 0) 70%);
  }

  .wash-b {
    top: 400px;
    left: -140px;
    width: 340px;
    height: 340px;
    background: radial-gradient(circle, rgb(200 90 50 / 0.14), rgb(200 90 50 / 0) 70%);
  }

  .ask-text {
    margin: 0;
    font-size: 13px;
    line-height: 1.5;
  }

  .ask-actions {
    display: flex;
    gap: 8px;
    margin-top: 12px;
  }

  .ask-later {
    flex: 1;
    min-height: 44px;
    border-radius: 11px;
    font-size: 13px;
    font-weight: 700;
    color: var(--ink);
    border: 1px solid var(--hair-strong);
    background: transparent;
  }

  .ask-go {
    flex: 1.3;
    min-height: 44px;
    border-radius: 11px;
    font-size: 13px;
    font-weight: 800;
    color: var(--pri-ink);
    background: var(--pri-bg);
  }

  .ask-diff {
    margin: 9px 0 0;
    list-style: disc;
    padding-inline-start: 18px;
    font-size: 12.5px;
    line-height: 1.55;
    color: var(--muted);
  }

  .ask-skip {
    width: 100%;
    min-height: 40px;
    margin-top: 8px;
    font-size: 12.5px;
    font-weight: 600;
    color: var(--faint);
    background: transparent;
  }

  .error {
    position: relative;
    z-index: 1;
    margin: 12px 16px 0;
    padding: 11px 12px;
    border-radius: 12px;
    font-size: 12.5px;
    line-height: 1.45;
    color: var(--warn);
    border: 1px solid rgb(232 147 90 / 0.45);
    background: var(--row-risk);
  }

  .error-text {
    margin: 0;
  }

  .error :global(.keyrow.keyrow) {
    padding: 9px 0 0;
  }

  .error :global(.keyfail.keyfail) {
    margin: 7px 0 0;
    color: var(--ink);
    font-weight: 700;
  }

  .error :global(.keynote.keynote) {
    margin: 7px 0 0;
    color: var(--ink);
    opacity: 0.75;
  }
  .key-gate {
    padding: 28px 20px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .key-gate h2 {
    margin: 0;
    font-size: 22px;
  }
  .key-gate p {
    margin: 0;
    color: var(--muted);
  }
</style>
