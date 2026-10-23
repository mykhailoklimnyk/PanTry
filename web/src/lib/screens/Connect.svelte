<script lang="ts">
  import Back from '../Back.svelte'
  import { connectUrl, disconnect, link } from '../session.svelte'

  interface Props {
    label: string
    onBack: () => void
  }

  const { label, onBack }: Props = $props()


  function leave() {
    void disconnect()
  }

  const READS = [
    {
      what: 'чеки офлайн і онлайн',
      why: 'із них видно, як швидко в тебе що закінчується: молоко за три дні, сіль за пів року. Без покупок Комора нічого не передбачить — вийде звичайний список.',
    },
    {
      what: 'кошик',
      why: 'його міг наповнити хто завгодно — помічник «Сільпо», ти руками, повтор замовлення. Комора перевіряє наявність на твій слот, узгоджує заміни наперед, рахує економіку — і доводить замовлення до дверей.',
    },
    {
      what: 'профіль і філія',
      why: "наявність рахується на конкретний магазин: у сусідньому дві позиції з п'яти можуть бути відсутні як клас.",
    },
    {
      what: 'обмеження в їжі',
      why: 'алергії й заборони з твого профілю «Сільпо». Уже заповнені — питати вдруге немає сенсу.',
    },
    {
      what: 'слоти доставки',
      why: 'коли доставка безкоштовна, скільки можна замовити і скільки це важить. Умови показуємо ті, що діють у «Сільпо» просто зараз.',
    },
  ]

  const WRITES = [
    {
      what: 'рядки в кошик — і тільки після «Оформити»',
      why: 'разом із запискою тому, хто збиратиме замовлення: чим саме дозволено замінити.',
    },
  ]

  const NEVER = [
    'не оформлюємо замовлення і не платимо — це робиш ти сам',
    'не змінюємо профіль, адреси й улюблене',
    'не пишемо нічого, поки ти не натиснув «Оформити»',
    'не чіпаємо оформлене замовлення — цього не може вже ніхто',
    'не заходимо в твій акаунт, коли тебе немає',
  ]

  const SUMMARY = [
    { mark: 'читаємо', text: 'чеки, кошик, профіль, обмеження в їжі, слоти' },
    { mark: 'пишемо', text: 'рядки в кошик — і лише після твого «Оформити»' },
    { mark: 'не робимо', text: 'не оформлюємо замовлення і не платимо' },
  ]
</script>

<div class="connect">
  <div class="top">
    {#if link.connected}
      <Back {label} onClick={onBack} />
    {/if}
    <h1>Акаунт «Сільпо»</h1>
  </div>

  {#if link.connected}
    <p class="lede">
      Підключено. <b>ПанTry</b> читає твою історію і кошик у твоєму ж акаунті —
      рівно те, що перелічено нижче.
    </p>

  {:else}
    <p class="lede">
      <b>ПанTry</b> рахує те, що вдома в ТЕБЕ — тому починається все з твого акаунта.
      Логін проходить на боці «Сільпо», пароля ми не бачимо.
    </p>
  {/if}

  {#if link.note}
    <p class="note" role="status">{link.note}</p>
  {/if}

  <ul class="summary">
    {#each SUMMARY as row (row.mark)}
      <li>
        <span class="mark">{row.mark}</span>
        <span class="mark-text">{row.text}</span>
      </li>
    {/each}
  </ul>

  <details class="more">
    <summary>докладно: що читаємо, що пишемо, чого не робимо і де живе доступ</summary>

    <section>
      <h2>що читаємо</h2>
      <ul>
        {#each READS as row (row.what)}
          <li>
            <span class="what">{row.what}</span>
            <p class="why">{row.why}</p>
          </li>
        {/each}
      </ul>
    </section>

    <section>
      <h2>що пишемо</h2>
      <ul>
        {#each WRITES as row (row.what)}
          <li class="write">
            <span class="what">{row.what}</span>
            <p class="why">{row.why}</p>
          </li>
        {/each}
      </ul>
    </section>

    <section>
      <h2>чого не робимо ніколи</h2>
      <ul class="never">
        {#each NEVER as line (line)}
          <li><span class="what">{line}</span></li>
        {/each}
      </ul>
    </section>

    <section>
      <h2>де живе доступ</h2>
      <ul>
        <li>
          <span class="what">у твоєму браузері, не в нашій базі</span>
          <p class="why">
            Зашифрований, у cookie, яку не читає жоден скрипт на сторінці.
            У базі його немає — отже немає ні в бекапі, ні в дампі.
          </p>
        </li>
        <li>
          <span class="what">«Вийти» справді відкликає, а не просто забуває</span>
          <p class="why">
            Перевірено живим дослідом: токен після цього не працює, і б'є це
            точково — інший твій пристрій лишається підключеним.
          </p>
        </li>
      </ul>
    </section>
  </details>

  <div class="spacer"></div>

  <div class="dock">
    {#if link.connected}
      <button class="out" type="button" onclick={leave}>Вийти й відкликати доступ</button>
      <p class="promise">доступ перестане діяти одразу, на цьому пристрої й у нас</p>
    {:else if link.backend}
      <a class="go" href={connectUrl()}>Підключити «Сільпо»</a>
      <p class="promise">
        нічого не спишеться — вхід дає читати історію, а кошик поїде лише
        після твого «Оформити»
      </p>
    {:else}
      <p class="offline">
        Бекенд не відповідає, тож підключитись зараз нікуди. Це не поломка
        входу: сам логін живе на боці «Сільпо», а от прочитати твою історію
        нам зараз нічим. Спробуй пізніше.
      </p>
    {/if}
  </div>
</div>

<style>
  .connect {
    flex: 1;
    display: flex;
    flex-direction: column;
    padding: 16px 16px 0;
  }

  .spacer {
    flex: 1;
    min-height: 16px;
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

  .note {
    margin-top: 12px;
    padding: 11px 12px;
    border-radius: 12px;
    font-size: 12.5px;
    line-height: 1.45;
    color: var(--warn);
    border: 1px solid rgb(232 147 90 / 0.45);
    background: var(--row-risk);
  }

  .summary {
    margin-top: 16px;
    display: flex;
    flex-direction: column;
    gap: 1px;
    border-radius: 14px;
    overflow: hidden;
    border: 1px solid var(--hair);
  }

  .summary li {
    display: flex;
    align-items: baseline;
    gap: 10px;
    padding: 11px 13px;
    border: none;
    border-radius: 0;
    background: var(--list-bg);
  }

  .mark {
    flex: none;
    width: 68px;
    font-size: 11px;
    font-weight: 700;
    color: var(--badge);
  }

  .mark-text {
    flex: 1;
    min-width: 0;
    font-size: 12.5px;
    line-height: 1.4;
  }

  .more {
    margin-top: 14px;
  }

  .more > summary {
    padding: 11px 13px;
    border-radius: 12px;
    font-size: 12.5px;
    font-weight: 700;
    color: var(--muted);
    border: 1px solid var(--hair);
    background: transparent;
    cursor: pointer;
    list-style: none;
  }

  .more > summary::-webkit-details-marker {
    display: none;
  }

  .more > summary::after {
    content: ' ›';
    color: var(--badge);
  }

  .more[open] > summary::after {
    content: ' ×';
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

  li.write {
    border-color: var(--acc-edge);
    background: var(--acc-soft);
  }

  .never li {
    border-style: dashed;
  }

  .what {
    display: block;
    font-size: 13.5px;
    font-weight: 700;
    line-height: 1.35;
  }

  .why {
    font-size: 12px;
    color: var(--muted);
    margin-top: 5px;
    line-height: 1.5;
  }

  .dock {
    position: sticky;
    bottom: 0;
    margin: 16px -16px 0;
    padding: 12px 16px calc(12px + env(safe-area-inset-bottom, 0px));
    border-top: 1px solid var(--hair);
    background: var(--glass-bg);
    backdrop-filter: blur(22px) saturate(160%);
  }

  .go {
    display: block;
    width: 100%;
    padding: 16px;
    border-radius: 16px;
    font-size: clamp(16px, 4.4vw, 17.5px);
    font-weight: 800;
    text-align: center;
    color: var(--pri-ink);
    background: var(--pri-bg);
  }

  .out {
    width: 100%;
    padding: 15px;
    border-radius: 16px;
    font-size: 15px;
    font-weight: 700;
    color: var(--warn);
    border: 1px solid rgb(232 147 90 / 0.45);
    background: transparent;
  }

  .promise,
  .offline {
    margin-top: 9px;
    font-size: 11.5px;
    color: var(--faint);
    text-align: center;
    line-height: 1.45;
  }

  @media (width <= 380px) {
    .connect {
      padding-inline: 12px;
    }

    h1 {
      font-size: 21px;
    }

    .dock {
      margin-inline: -12px;
      padding-inline: 12px;
    }
  }
</style>
