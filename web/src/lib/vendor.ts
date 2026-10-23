
export interface VendorReason {
  code: string
  text: string
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

function looksLikeCode(text: string): boolean {
  return /^[a-z][a-z_]*(\.[a-z][a-z_]*)+$/i.test(text.trim())
}

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
