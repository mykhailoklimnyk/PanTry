/**
 * Причини, якими «Сільпо» блокує оформлення -- словами гостя, а не кодом.
 *
 * `CheckoutResult.blockers` несе коди чужої системи (`validations[]` рівня
 * error). Опис `silpo_get_shopping_cart_by_id`, знятий живим викликом 07.09,
 * каже про них прямо: `message` -- «a STABLE, dot-namespaced identifier
 * (e.g. "order.payment_types.disabled", "product.offer.stock.max") -- NOT a
 * human-readable sentence. Match against these known identifiers rather than
 * trying to parse or translate the string directly.» Тобто ключування кодом
 * тут не наша самодіяльність, а те, чого прямо просить вендор.
 *
 * Живий тест 07.09: на екрані стояв рівно такий код --
 * `branch.location.not_available` -- копія, а не пояснення. `blockerNotes`
 * мав нести людський переклад (`core/blockers.py`), але для нового коду
 * перекладу не було, і лягла туди сама копія. Тому словник звіряє те, що
 * прислав сервер: людський текст лишається як є (сервер бачить контекст,
 * якого тут немає), а копія коду підміняється. Незнайомий код НЕ ховається:
 * людське «магазин відмовив» плюс сам код дрібним -- мовчазний різ
 * невідомого гірший за незрозумілий код.
 */

export interface VendorReason {
  /** Код лишається завжди, дрібним, поруч -- для фідбеку й журналу. */
  code: string
  text: string
  /** Що робити далі. Порожньо -- дії з нашого боку немає. */
  action: string
}

const DICTIONARY: Record<string, { text: string; action: string }> = {
  "timeslot.not_available": {
    text: "Слот, під який зібрано кошик, уже зайнятий.",
    action: "обери інший час доставки і перезбери кошик",
  },
  "order.cost.min": {
    text: "Сума кошика нижча за мінімум цього способу доставки.",
    action: "докинь ще щось або зміни спосіб доставки",
  },
  "branch.location.not_available": {
    text: "Магазин, з якого мав їхати кошик, зараз недоступний для цієї адреси.",
    action: "перевір адресу доставки або спробуй трохи пізніше",
  },
  "product.offer.status.not_available": {
    text: "Частину товарів «Сільпо» не прийняло: їх зняли з продажу вже після збірки.",
    action: "перезбери кошик під те, що є зараз",
  },
  "product.offer.stock.max": {
    text: "Товару на складі менше, ніж поїхало в кошик.",
    action: "зменш кількість цього рядка і спробуй ще раз",
  },
  "order.payment_types.disabled": {
    text: "Спосіб оплати для цього замовлення вимкнено.",
    action: "зміни спосіб оплати в «Сільпо» і повернись сюди",
  },
}

const UNKNOWN_TEXT = "Магазин відмовив прийняти позицію."
const UNKNOWN_ACTION = "спробуй перезібрати кошик; якщо повториться -- це варто показати нам"

/** Код, скопійований у поле для людини, а не написаний для неї (живий
 *  випадок 07.09: `branch.location.not_available` на екрані як є). */
function looksLikeCode(text: string): boolean {
  return /^[a-z][a-z_]*(\.[a-z][a-z_]*)+$/i.test(text.trim())
}

/**
 * Пояснення одного блокера.
 *
 * `note` -- те, що прислав сервер (`blockerNotes`, #251). Коли він уже
 * людський, лишаємо його як є: сервер бачить контекст, якого словник не
 * знає. Порожній або схожий на код -- підміняємо словником, а за браком
 * запису в ньому -- загальною фразою з кодом дрібним.
 *
 * `context` -- структуровані дані блокера (суми, причини), які вендор
 * прямо радить брати ЗВІДТИ, а не з `message`: «context carries the
 * structured data needed to build a user-facing message yourself». У
 * `CheckoutResult` цього поля сервер ще не віддає (нема що читати -- звіряй
 * `HANDOFF-B.md`), тож параметр приймаємо наперед, щоб сигнатура не
 * розповзлася по двох місцях, коли поле з'явиться; поки він завжди
 * відсутній, кожен код працює на своєму словниковому реченні без чисел.
 */
export function vendorReason(
  code: string,
  note: string,
  context?: Record<string, unknown> | null,
): VendorReason {
  void context
  const known = DICTIONARY[code]
  const human = note.trim() !== "" && !looksLikeCode(note)
  if (human) return { code, text: note, action: known?.action ?? "" }
  if (known) return { code, text: known.text, action: known.action }
  return { code, text: UNKNOWN_TEXT, action: UNKNOWN_ACTION }
}
