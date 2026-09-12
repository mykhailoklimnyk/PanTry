<script lang="ts">
  import KeyForm from './KeyForm.svelte'
  import Logo from './Logo.svelte'
  import { dayLabel } from './format'
  import { popover, togglePopover } from './popover.svelte'
  import { link } from './session.svelte'
  import { theme, toggleTheme } from './theme.svelte'
  import { inTabs, type Screen } from './navigation'
  import type { Loaded } from './data'
  import type { ModelOption } from './types'
  import { MENU } from './pages'

  interface Props {
    screen: Screen
    /** Id обраної моделі — як його розуміє Bedrock, не людська назва. */
    model: string
    /** Перелік із `/api/models`. Loaded, а не масив: відмову показуємо
     *  в меню, а не вдаємо порожній список — порожній селектор виглядає
     *  як робочий продукт без моделей. */
    models: Loaded<ModelOption[]>
    /** Чи лежить у браузері ключ гостя до OpenAI (#197). Сам ключ сюди не
     *  приходить ніколи — він httpOnly і виходить лише в наш запит. */
    llmKey: boolean
    /** Швидкий режим: null — гість перемикача не чіпав, отже діє
     *  замовчування моделі. Не `false`: вимкнув сам — значить вимкнено. */
    fast: boolean | null
    /** Без кошика таби нікуди не ведуть — половина з них порожня. */
    hasBasket: boolean
    /** Кошик зібрався, поки гість читав інший екран (#147). Показуємо це
     *  чипсом, а не переходом: забрати екран з-під пальця — та сама поломка,
     *  що з правкою під час перерахунку (#145). */
    cartReady: boolean
    /** Слід «звідки прийшли»: вкладки належать контексту КОШИКА, і комора,
     *  відкрита зі старту, не має лишати гостя в них (#92). */
    trail: Screen[]
    debugOn: boolean
    /** Холодний прогін: не читати кеш назв видів. Живе поруч із панеллю
     *  дебагу і показується разом з нею -- серверні ворота на прапорець
     *  `KOMORA_INSIDERS`, тож чужому він не діє МОВЧКИ, а мовчазний контрол
     *  від зламаного не відрізнити (#38). */
    coldOn: boolean
    today: Date
    onModel: (id: string, keepOpen: boolean) => void
    onFast: (on: boolean) => void
    /** Зберегти ключ. Повертає причину відмови або null, якщо лягло. */
    onKey: (key: string) => Promise<string | null>
    onForgetKey: () => void
    onNavigate: (screen: Screen) => void
    onDebug: () => void
    onCold: (on: boolean) => void
    onAbout: () => void
    /** Показати підказки по інтерфейсу ще раз. */
    onTour: () => void
    /** Запустити пасхалку руками. Живе під дебагом — див. розмітку меню. */
    onBreach: () => void
    /** Вийти з акаунта. У меню, а не тільки за чипсом: вихід мусить бути
     *  там, де його шукають, — а шукають його в меню. */
    onLogout: () => void
  }

  const {
    screen,
    model,
    models,
    llmKey,
    fast,
    hasBasket,
    cartReady,
    trail,
    debugOn,
    coldOn,
    today,
    onModel,
    onFast,
    onKey,
    onForgetKey,
    onNavigate,
    onDebug,
    onCold,
    onAbout,
    onTour,
    onBreach,
    onLogout,
  }: Props = $props()

  const menuOpen = $derived(popover.id === 'models')
  let bar = $state<HTMLElement | null>(null)

  $effect(() => {
    const node = bar
    if (node === null) return
    const say = () =>
      document.documentElement.style.setProperty('--chrome-h', `${node.offsetHeight}px`)
    say()
    const watch = new ResizeObserver(say)
    watch.observe(node)
    return () => watch.disconnect()
  })


  const pickable = $derived(models.ok && models.data.length > 0)

  $effect(() => {
    if (!pickable && popover.id === 'models') togglePopover('models')
  })

  const list = $derived(models.ok ? models.data : [])
  const shown = $derived(list.filter((item) => item.available))
  const hidden = $derived(list.length - shown.length)
  const top = $derived(shown.filter((item) => item.recommended))
  const rest = $derived(shown.filter((item) => !item.recommended))

  const burgerOpen = $derived(popover.id === 'burger')

  const selected = $derived(
    models.ok ? models.data.find((item) => item.id === model) : undefined,
  )

  const fastOn = $derived(fast === null ? (selected?.fastByDefault ?? false) : fast)

  const keyWanted = $derived((selected?.needsKey ?? false) && !llmKey)

  const DEFAULT_FAMILY = 'Mistral'
  const short = $derived(
    (selected?.label ?? (model ? model.split('.').pop() : DEFAULT_FAMILY) ?? DEFAULT_FAMILY)
      .replace('Claude ', '')
      .split(' ')[0],
  )

  const tabs: { id: Screen; label: string }[] = [
    { id: 'cart', label: 'кошик' },
    { id: 'pantry', label: 'комора' },
    { id: 'bar', label: 'бар' },
  ]

  const showTabs = $derived(hasBasket && inTabs(screen, trail))
</script>

<header class="chrome glass" bind:this={bar}>
  <div class="top">
    <div class="brand">
      <button class="home" type="button" aria-label="На початок" onclick={() => onNavigate('start')}>
        <span class="logo"><Logo size={46} /></span>
        <span class="name"><span class="pan">Пан</span><span class="try">Try</span></span>
      </button>

      <div class="day">
        <span class="date">{dayLabel(today)}</span>
        {#if link.ready && link.backend}
          <button
            class="link"
            class:on={link.connected}
            type="button"
            data-tour="link"
            title={link.connected
              ? 'акаунт «Сільпо» підключено'
              : 'акаунт «Сільпо» не підключено — торкнись, щоб підключити'}
            onclick={() => onNavigate('connect')}
          >
            <span class="dot" aria-hidden="true"></span>
            {link.connected ? 'Сільпо' : 'не підключено'}
          </button>
        {/if}
      </div>
    </div>

    <div class="models">
      <button
        class="pill"
        type="button"
        data-popover
        disabled={!pickable}
        aria-expanded={menuOpen}
        title={pickable ? 'модель прогону' : 'перелік моделей ще не прочитався'}
        onclick={() => togglePopover('models')}
      >
        {short}{#if pickable}<span class="caret" aria-hidden="true">▾</span>{/if}
      </button>

      {#if menuOpen}
        <div class="menu" data-popover role="listbox" tabindex="-1" aria-label="Модель">
          <div class="menu-head">
            <span>модель</span>
            <span class="hint">для тесту</span>
          </div>

          <div class="menu-list">
            {#if models.ok}
              {#snippet row(item: ModelOption)}
                <button
                  class="model"
                  class:on={item.id === model}
                  class:off={!item.available}
                  type="button"
                  role="option"
                  aria-selected={item.id === model}
                  disabled={!item.available}
                  onclick={() => onModel(item.id, item.needsKey && !llmKey)}
                >
                  <span class="dot" aria-hidden="true"></span>
                  <span class="model-text">
                    <span class="model-name ellipsis">{item.label}</span>
                    <span class="model-note">{item.note ?? item.id}</span>
                    {#if item.needsKey}
                      <span class="cost">OpenAI · {llmKey ? 'ключ є' : 'потрібен ключ'}</span>
                    {/if}
                  </span>
                </button>
              {/snippet}

              <p class="group">рекомендовані — заміряні на пастках і на швидкості</p>
              {#each top as item (item.id)}{@render row(item)}{/each}

              {#if keyWanted}
                <KeyForm {onKey} />
              {:else if llmKey}
                <button type="button" class="keydrop" onclick={onForgetKey}>
                  прибрати мій ключ OpenAI
                </button>
              {/if}

              {#if selected?.supportsFast}
                <label class="fastrow">
                  <input
                    type="checkbox"
                    checked={fastOn}
                    disabled
                    onchange={(event) => onFast(event.currentTarget.checked)}
                  />
                  <span class="fast-text">
                    <span>швидкий режим</span>
                    <span class="fast-note">
                      два паралельні потоки у збірці кошика і в заповненні комори;
                      заміряно на обох моделях, тому завжди увімкнено
                    </span>
                  </span>
                </label>
              {/if}

              {#if rest.length > 0 && debugOn}
                <p class="group">решта каталогу Bedrock — видно, бо панель дебагу увімкнена</p>
                {#each rest as item (item.id)}{@render row(item)}{/each}
              {/if}
              {#if hidden > 0 && debugOn}
                <p class="group">ще {hidden} у каталозі без доступу — приховано</p>
              {/if}
            {:else}
              <p class="menu-fail">{models.message}</p>
            {/if}
          </div>

          <p class="menu-foot">
            Дві моделі, заміряні на пастках і на швидкості: Mistral платить проєкт,
            Luna — твій ключ. Той самий тиждень можна зібрати обома і звірити.
          </p>
        </div>
      {/if}
    </div>

    <div class="burger-wrap">
      <button
        class="icon"
        type="button"
        data-popover
        aria-expanded={burgerOpen}
        aria-label="Меню"
        onclick={() => togglePopover('burger')}
      >
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
          <path d="M4 7h16M4 12h16M4 17h16" />
        </svg>
      </button>

      {#if burgerOpen}
        <div class="menu burger" data-popover>
          <button class="theme" type="button" onclick={toggleTheme}>
            <span class="theme-label">тема</span>
            <span class="theme-value">{theme.value === 'dark' ? 'темна' : 'світла'}</span>
          </button>

          <button class="theme" type="button" onclick={onDebug}>
            <span class="theme-label">панель дебагу</span>
            <span class="theme-value">{debugOn ? 'увімкнена' : 'вимкнена'}</span>
          </button>

          <button class="theme" type="button" onclick={() => onCold(!coldOn)}>
            <span class="theme-label">кеш назв видів</span>
            <span class="theme-value">{coldOn ? 'не читати' : 'читати'}</span>
          </button>

          <div class="sep"></div>

          <button class="doc" type="button" onclick={onAbout}>
            <span class="doc-label">про ПанTry</span>
            <span class="doc-note">що це і навіщо</span>
          </button>

          <button class="doc" type="button" onclick={onTour}>
            <span class="doc-label">підказки</span>
            <span class="doc-note">що для чого на екрані</span>
          </button>

          {#if debugOn}
            <button class="doc" type="button" onclick={onBreach}>
              <span class="doc-label">режим хакера</span>
              <span class="doc-note">ОоО. новий користувач</span>
            </button>
          {/if}

          {#each MENU as page (page.id)}
            <button class="doc" type="button" onclick={() => onNavigate(page.id)}>
              <span class="doc-label">{page.label}</span>
              <span class="doc-note">{page.note}</span>
            </button>
          {/each}

          {#if link.connected}
            <div class="sep"></div>
            <button class="doc out" type="button" onclick={onLogout}>
              <span class="doc-label">вийти з «Сільпо»</span>
              <span class="doc-note">доступ перестане діяти одразу</span>
            </button>
          {/if}

          <p class="menu-foot">створено для хакатону «Сільпо» AI Factory</p>
        </div>
      {/if}
    </div>
  </div>

  {#if showTabs}
    <nav class="tabs" aria-label="Розділи">
      {#each tabs as tab (tab.id)}
        <button
          class="tab"
          class:on={screen === tab.id}
          type="button"
          aria-current={screen === tab.id ? 'page' : undefined}
          onclick={() => onNavigate(tab.id)}
        >
          {tab.label}
        </button>
      {/each}
    </nav>
  {:else if cartReady}
    <nav class="tabs" aria-label="Розділи">
      <button class="tab ready" type="button" onclick={() => onNavigate('cart')}>
        кошик готовий ›
      </button>
    </nav>
  {/if}
</header>

<style>
  .chrome {
    position: sticky;
    top: 0;
    z-index: 20;
    border-bottom: 1px solid var(--hair);
  }

  .top {
    display: flex;
    align-items: center;
    gap: 11px;
    padding: 14px 16px 12px;
  }

  .brand {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    column-gap: 11px;
    flex: 1;
    min-width: 0;
  }

  .home {
    display: flex;
    align-items: center;
    gap: 11px;
    min-width: 0;
    text-align: left;
    color: inherit;
  }

  .logo {
    width: 46px;
    height: 46px;
    flex: none;
    display: grid;
    place-items: center;
  }

  .name {
    display: block;
    font-size: 19px;
    font-weight: 900;
    letter-spacing: 0;
    line-height: 1.1;
    color: #fff6e0;
    -webkit-text-stroke: 1.1px #2f1b0f;
    paint-order: stroke fill;
  }

  .name .try {
    color: #f6b431;
  }

  .day {
    display: flex;
    align-items: center;
    gap: 6px;
    margin: 3px 0 0 51px;
    min-width: 0;
  }

  .date {
    font-size: 12.5px;
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .link {
    display: flex;
    align-items: center;
    gap: 5px;
    flex: none;
    padding: 2px 8px;
    min-height: 22px;
    border-radius: 999px;
    font-size: 10.5px;
    font-weight: 800;
    letter-spacing: 0.02em;
    white-space: nowrap;
    color: var(--badge);
    border: 1px solid var(--acc-edge);
    background: var(--acc-soft);
  }

  .link.on {
    color: var(--faint);
    border-color: var(--hair-strong);
    background: var(--chip-bg);
  }

  .link .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--warn);
  }

  .link.on .dot {
    background: var(--good);
  }

  .icon {
    width: 34px;
    height: 34px;
    border-radius: 11px;
    flex: none;
    display: grid;
    place-items: center;
    color: var(--muted);
    border: 1px solid var(--hair);
    background: var(--chip-bg);
  }

  .burger-wrap,
  .models {
    position: relative;
    flex: none;
  }

  .burger {
    width: min(250px, calc(100vw - 24px));
  }

  .theme,
  .doc {
    display: flex;
    width: 100%;
    align-items: baseline;
    gap: 8px;
    padding: 11px 10px;
    min-height: 44px;
    border-radius: 11px;
    text-align: left;
    color: var(--ink);
  }

  .theme:hover,
  .doc:hover {
    background: var(--chip-bg);
  }

  .theme-label,
  .doc-label {
    flex: 1;
    font-size: 13px;
    font-weight: 700;
  }

  .theme-value {
    font-size: 12px;
    color: var(--badge);
    font-weight: 700;
  }

  .doc {
    flex-direction: column;
    align-items: stretch;
    gap: 2px;
  }

  .doc-note {
    font-size: 11px;
    color: var(--muted);
    line-height: 1.3;
  }

  .out .doc-label {
    color: var(--warn);
  }

  .sep {
    height: 1px;
    margin: 6px 2px;
    background: var(--hair);
  }

  .pill {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 6px 10px;
    min-height: 34px;
    border-radius: 999px;
    font-size: 11.5px;
    font-weight: 700;
    white-space: nowrap;
    color: var(--badge);
    border: 1px solid var(--badge-edge);
    background: var(--badge-fill);
  }

  .pill:disabled {
    color: var(--muted);
    border-color: var(--hair);
    background: var(--chip-bg);
    cursor: default;
  }

  .caret {
    opacity: 0.7;
  }

  .menu {
    position: absolute;
    top: calc(100% + 8px);
    right: 0;
    width: min(290px, calc(100vw - 24px));
    max-height: calc(100dvh - 110px);
    display: flex;
    flex-direction: column;
    z-index: 60;
    padding: 11px 12px;
    border-radius: 16px;
    border: 1px solid var(--hair-strong);
    background: var(--menu-bg);
    backdrop-filter: blur(26px) saturate(160%);
    box-shadow: 0 18px 44px rgb(0 0 0 / 0.42);
  }

  .menu-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px;
    flex: none;
    font-size: 11.5px;
    color: var(--muted);
  }

  .hint {
    font-size: 10.5px;
    color: var(--faint);
    white-space: nowrap;
  }

  .menu-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin: 9px -2px 0;
    padding: 0 2px;
    min-height: 0;
    overflow-y: auto;
    overscroll-behavior: contain;
    scrollbar-width: thin;
    scrollbar-color: var(--hair-strong) transparent;
  }

  .model {
    display: flex;
    flex: none;
    align-items: center;
    gap: 9px;
    text-align: left;
    padding: 9px 10px;
    min-height: 44px;
    width: 100%;
    border-radius: 11px;
    border: 1px solid var(--hair-strong);
    background: transparent;
    color: var(--ink);
  }

  .model.on {
    border-color: var(--acc-edge);
    background: var(--acc-soft);
  }

  .model.off {
    opacity: 0.45;
    color: var(--muted);
    cursor: not-allowed;
  }

  .dot {
    width: 14px;
    height: 14px;
    border-radius: 50%;
    flex: none;
    border: 2px solid var(--hair-strong);
  }

  .model.on .dot {
    border-color: var(--badge);
    background: var(--badge);
  }

  .model-text {
    flex: 1;
    min-width: 0;
  }

  .model-name {
    display: block;
    font-size: 13px;
    font-weight: 700;
    line-height: 1.25;
  }

  .group {
    margin: 6px 8px 2px;
    font-size: 10px;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--muted);
  }

  .fast-note {
    margin: 0 8px 6px;
    font-size: 11px;
    line-height: 1.35;
    color: var(--muted);
  }

  .keydrop {
    margin: 2px 8px 6px;
    padding: 0;
    border: 0;
    background: none;
    color: var(--muted);
    font: inherit;
    font-size: 11px;
    text-decoration: underline;
    cursor: pointer;
  }

  .fastrow {
    display: flex;
    gap: 8px;
    align-items: flex-start;
    padding: 6px 8px;
    font-size: 12px;
    cursor: pointer;
  }

  .fast-text {
    display: grid;
    gap: 2px;
  }

  .fast-note {
    margin: 0;
  }

  .model-note {
    display: block;
    font-size: 11px;
    color: var(--muted);
    margin-top: 2px;
    line-height: 1.3;
  }

  .cost {
    display: block;
    margin-top: 3px;
    font-size: 10.5px;
    font-weight: 700;
    color: var(--warn);
  }

  .menu-foot {
    font-size: 10.5px;
    color: var(--faint);
    margin-top: 9px;
    line-height: 1.4;
    flex: none;
  }

  .menu-fail {
    font-size: 12px;
    color: var(--warn);
    line-height: 1.4;
    padding: 8px 2px;
  }

  .tabs {
    display: flex;
    gap: 3px;
    margin: 0 16px 10px;
    padding: 3px;
    border-radius: 13px;
    border: 1px solid var(--hair-strong);
    background: var(--chip-bg);
  }

  .tab {
    flex: 1;
    min-height: 40px;
    padding: 10px 4px;
    border-radius: 10px;
    font-size: 12.5px;
    font-weight: 700;
    color: var(--muted);
    border: 1px solid transparent;
    background: transparent;
  }

  .tab.on {
    color: var(--badge);
    border-color: var(--acc-edge);
    background: var(--acc-soft);
  }

  @media (width <= 380px) {
    .top {
      gap: 8px;
      padding: 12px 12px 10px;
    }

    .name {
      font-size: 17.5px;
    }

    .date {
      font-size: 11.5px;
    }

    .day {
      margin-left: 44px;
    }

    .icon {
      width: 32px;
      height: 32px;
    }

    .pill {
      padding: 6px 8px;
      font-size: 11px;
    }

    .tabs {
      padding: 0 12px 10px;
    }

    .tab {
      font-size: 11.5px;
    }
  }

  .ready {
    color: var(--accent);
    font-weight: 600;
  }
</style>
