export interface AgentTarget {
  named: number
  proposed: number
  target: number
  why: string
  refused: string | null
}

export interface AnswerTaken {
  taken: boolean
}

export interface Bar {
  changed: number | null
  items: BarItem[]
  receipts: number
  orders: number
  kinds: number
  named: number
  trackedFrom: number
  source: string
  unlisted: number
  dropped: number
}

export interface BarGroupChoice {
  label: string
  kind: DrinkKind | null
}

export interface BarItem {
  id: string
  label: string
  kind: DrinkKind | null
  kindSaid: boolean
  times: number
  daysSince: number | null
  source: 'receipts' | 'manual'
  usual: ProductPick | null
  priceFrom: number | null
  priceTo: number | null
  forkNote: string
}

export interface Basket {
  runId: string
  lines: CartLine[]
  total: number
  baseTotal: number | null
  deliveryCost: number
  totalWeightKg: number
  topUp: TopUp | null
  blockers: string[]
  slot: SlotWindow | null
  checkoutWebLink: string | null
  trace: TraceStep[]
  stats: RunStats
  feedback: OrderFeedback
  unresolved: string[]
  declined: Declined[]
  questions: Clarification[]
  postponed: Postponed[]
  budget: number | null
  textIgnored: string[]
  shelfNote: string | null
  planNote: string | null
  agentTarget: AgentTarget | null
  trimmed: Trimmed[]
  fillCut: Trimmed[]
  twinsDropped: TwinsDropped[]
  fillNote: string | null
  cyclesNote: string | null
  notCollected: string[]
}

export interface BuildRequest {
  source: 'list' | 'cart'
  delivery: string
  mode: 'list' | 'week' | 'event'
  progressKey: string | null
  occasionPeople: number | null
  cold: boolean
  eventStyle: 'cooking' | 'ready' | null
  shoppingList: string[]
  listText: string
  barInWeek: boolean
  budgetSaid: boolean
  budget: number | null
  keep: string[]
  swaps: SwapDecision[]
  exclusions: string[]
  rules: string[]
  model: string | null
  fast: boolean | null
  autoSwap: boolean
  autoSwapPercent: number
  answers: ClarifyAnswer[]
}

export interface CarryOverLine {
  name: string
  qty: number
  total: number
}

export type CarryOverState = 'asking' | 'kept' | 'removed'

export interface CartCarryOver {
  state: CarryOverState
  total: number
  lines: CarryOverLine[]
}

export interface CartLine {
  externalProductId: string
  name: string
  qty: number
  unit: string
  step: number | null
  price: number
  basePrice: number | null
  saleNote: string | null
  weightKg: number | null
  imageUrl: string | null
  cardUrl: string | null
  reason: Reason
  explanation: string
  explanationDetail: string | null
  confidence: number
  atRisk: boolean
  needsApproval: boolean
  chain: Substitute[]
  mandate: string | null
  mandateAhead: boolean
  decided: boolean
  swapFork: PriceFork | null
  considered: SwapOption[]
  sliced: boolean
  slicingNote: string | null
  cheaper: Cheaper | null
  consideredTotal: number
}

export interface CartState {
  rows: number
  total: number
  slot: SlotWindow | null
}

export interface CartTotals {
  products: number
  discount: number
  delivery: number
  serviceFee: number | null
  toPay: number
  estimate: number | null
}

export type Changes = 'approvedChanges' | 'disapprovedChanges'

export interface Cheaper {
  externalProductId: string
  name: string
  price: number
  saving: number
}

export interface CheaperRequest {
  externalProductId: string
  to: string
}

export interface CheckoutExtra {
  externalProductId: string
  qty: number
  name: string
}

export interface CheckoutRequest {
  existing: CarryOverState
  lines: Record<string, number> | null
  extras: CheckoutExtra[] | null
  model: string | null
  fast: boolean | null
}

export interface CheckoutResult {
  written: number
  skipped: CheckoutSkip[]
  blockers: string[]
  blockerNotes: string[]
  warnings: string[]
  retryHelps: boolean
  mandateLost: string[]
  unmandated: string[]
  stockCut: string[]
  basket: Basket | null
  checkoutWebLink: string | null
  cartWebLink: string | null
  totals: CartTotals | null
  bonusAvailable: number | null
  wantedBurned: string[]
  wantedStocked: string[]
  promoGone: string[]
  carryOver: CartCarryOver | null
  trace: TraceStep[]
  summary: string
}

export interface CheckoutSkip {
  name: string
  reason: string
}

export interface Clarification {
  intent: string
  question: string
  options: ClarifyOption[]
  picks: ClarifyPick[]
}

export interface ClarifyAnswer {
  intent: string
  slug: string | null
  query: string | null
  text: string | null
  skip: boolean
}

export interface ClarifyOption {
  title: string
  slug: string
  query: string | null
  count: number
  priceFrom: number | null
  byWeight: boolean
}

export interface ClarifyPick {
  externalProductId: string
  name: string
  price: number
  ratio: string | null
  byWeight: boolean
}

export type Contacts = 'call' | 'doNotCall'

export interface CorrectionRequest {
  externalProductId: string
  action: 'still_have' | 'ran_out_earlier' | 'never_again'
}

export interface Declined {
  intent: string
  why: string
}

export interface DeliveryOption {
  id: string
  label: string
  note: string
  cost: number
  minOrder: number | null
  threshold: number | null
  maxWeightKg: number | null
  serviceFee: number | null
  available: boolean
  unavailableReason: string | null
}

export type DrinkKind = 'strong' | 'wine' | 'light'

export interface Exclusion {
  id: string
  label: string
  permanent: boolean
  active: boolean
}

export interface GuestLink {
  connected: boolean
  expiresAt: string | null
  reason: string | null
  greet: number | null
  llmKey: boolean
}

export interface Health {
  database: boolean
  loginReady: boolean
  version: string | null
}

export interface LlmKeyRequest {
  key: string
}

export interface ModelOption {
  id: string
  label: string
  note: string | null
  available: boolean
  active: boolean
  recommended: boolean
  needsKey: boolean
  supportsFast: boolean
  fastByDefault: boolean
}

export interface NextList {
  rows: WantedRow[]
  changes: string[]
  note: string
}

export interface OrderFeedback {
  changes: Changes | null
  contacts: Contacts | null
}

export interface Pantry {
  items: PantryItem[]
  fresh: boolean
  refined: string | null
  asked: PantryAsk[]
  spent: RunCost | null
  changed: number | null
  receipts: number
  orders: number
  kinds: number
  trackedFrom: number
  hidden: string[]
  atBar: string[]
  apart: string[]
  outside: string[]
  spend: SpendTarget | null
  trace: TraceStep[]
  aisles: PantryAisle[]
  source: string
  unlisted: number
  tripGap: number
  listLimit: number
  targetPool: number
  targetEstimate: number | null
}

export interface PantryAdjustment {
  id: string
  action: 'bought' | 'qty' | 'cycle' | 'forget_cycle' | 'hide' | 'unhide' | 'split' | 'unsplit' | 'mandate' | 'forget_mandate'
  qty: number
  group: string
  days: number
  chain: string[]
}

export interface PantryAisle {
  title: string
  rows: number
}

export interface PantryAsk {
  label: string
  ask: string
  covers: string[]
  kind: string
  coverKinds: string[]
  usual: string
}

export interface PantryEntry {
  label: string
}

export interface PantryItem {
  id: string
  label: string
  qty: number | null
  usualQty: number | null
  unit: string
  named: boolean
  leftRatio: number | null
  daysLeft: number | null
  cycleDays: number | null
  sanity: string | null
  keeps: string | null
  ask: boolean
  cycleSaid: boolean
  state: string
  runningOut: boolean
  promo: string | null
  arrived: string | null
  usual: ProductPick | null
  trust: string
  source: 'receipts' | 'manual'
  aisle: string | null
  group: string | null
  imageUrl: string | null
  wanted: boolean
  writtenAs: string[]
  mandate: PantryMandate | null
  parts: PantryPart[]
}

export interface PantryLink {
  article: string
  name: string
}

export interface PantryMandate {
  links: PantryLink[]
  agreed: boolean
}

export interface PantryPart {
  label: string
  unit: string
  receipts: number
  daysSince: number | null
  fresh: boolean
}

export interface PickRequest {
  intent: string
  externalProductId: string
}

export interface Place {
  address: string | null
  tag: string | null
  branch: string | null
  branchId: string | null
  source: 'address' | 'cart' | 'config' | 'none'
  note: string
  deliveryTypes: string[]
  saved: PlaceOption[]
}

export interface PlaceChoice {
  label: string
  latitude: number
  longitude: number
  id: string | null
  city: string | null
  street: string | null
  house: string | null
}

export interface PlaceOption {
  id: string | null
  label: string
  tag: string | null
  latitude: number
  longitude: number
  city: string | null
  street: string | null
  house: string | null
  confirmed: boolean
}

export interface PlaceQuery {
  text: string
}

export interface Postponed {
  intent: string
  reason: string
  estimate: number | null
  refillable: boolean
}

export interface PriceFork {
  low: number
  high: number
  per: string
}

export interface ProductPick {
  externalProductId: string
  name: string
  share: string
  price: number
  unit: string
  pack: string
}

export interface Progress {
  steps: TraceStep[]
  done: boolean
}

export interface ProgressAnswer {
  questionId: string
  optionId: string
}

export interface Quota {
  blocked: boolean
  scope: 'session' | 'day' | 'budget-day' | 'budget-total' | null
  headline: string
  action: string | null
  left: number
  resetsAt: string | null
  contact: string | null
  toll: Toll | null
}

export type Reason = 'cycle' | 'frequency' | 'undelivered' | 'dish' | 'topup' | 'at_home' | 'occasion' | 'substituted'

export interface RefillRequest {
  intents: string[]
  answers: ClarifyAnswer[]
  model: string | null
  fast: boolean | null
}

export interface RefineRequest {
  covers: Record<string, string[]>
  seen: number
  kinds: Record<string, string>
  more: boolean
  answers: Record<string, number>
  progressKey: string | null
  cold: boolean
  fast: boolean | null
}

export interface RuleEntry {
  label: string
  active: boolean
}

export interface RuleToggle {
  active: boolean
}

export interface RunCost {
  calls: number
  durationMs: number
  costUsd: number | null
  tokensIn: number
  tokensOut: number
}

export interface RunStats {
  receipts: number
  orders: number
  cycled: number
  mcpCalls: number
  durationMs: number
  costUsd: number
  tokensIn: number
  tokensOut: number
  tokensCached: number
  model: string
}

export interface SavedSwap {
  id: string
  label: string
  links: string[]
}

export interface SlotWindow {
  start: string
  end: string
  note: string | null
}

export interface SourceChoice {
  mode: 'receipts' | 'manual'
}

export interface SpendTarget {
  target: number
  orders: number
  presets: number[]
  note: string
}

export interface Substitute {
  externalProductId: string
  name: string
  source: string
  price: number | null
  ratio: string | null
  byWeight: boolean
}

export interface SwapDecision {
  externalProductId: string
  policy: 'substitute' | 'skip' | 'call'
  chain: string[]
}

export interface SwapOption {
  externalProductId: string
  name: string
  price: number
  ratio: string | null
  byWeight: boolean
  stock: number | null
  available: boolean
  imageUrl: string | null
  cardUrl: string | null
  sameKind: boolean | null
  kind: string | null
  sliced: boolean
}

export interface SwapsRequest {
  swaps: SwapDecision[]
  remember: boolean
}

export interface Toll {
  runs: number
  usd: number | null
  unpriced: number
  tokensIn: number
  tokensOut: number
  guestUsd: number | null
}

export interface TopUp {
  threshold: number
  saving: number
  items: CartLine[]
}

export interface TraceOption {
  id: string
  label: string
  style: 'cooking' | 'ready' | null
  target: number | null
}

export interface TraceQuestion {
  id: string
  ask: string
  why: string | null
  options: TraceOption[]
  waitS: number
}

export interface TraceStep {
  id: string
  seq: number
  tool: string
  args: Record<string, unknown>
  durationMs: number | null
  calls: number | null
  tokensIn: number | null
  tokensOut: number | null
  resultSummary: string
  decision: string | null
  tag: string | null
  tagTone: 'good' | 'warn' | 'muted'
  externalProductId: string | null
  prompt: string | null
  question: TraceQuestion | null
}

export interface Trimmed {
  intent: string
  name: string | null
  price: number | null
  reason: string
}

export interface TwinsDropped {
  name: string
  keptName: string
  why: string
}

export interface WantedEntry {
  label: string
  atHome: boolean
}

export interface WantedRow {
  id: string
  label: string
  why: string | null
  atHome: boolean
}

export interface WeekSpend {
  spent: number
  receipts: number
  since: string
}
