
export function parseList(text: string): string[] {
  const seen = new Set<string>()
  const lines: string[] = []
  for (const raw of text.split(/[\n,;]+/)) {
    const line = raw.trim()
    if (!line) continue
    const key = line.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    lines.push(line)
  }
  return lines
}


const CONNECTORS = new Set([
  'і', 'й', 'та', 'ще', 'плюс', 'також', 'потім', 'може', 'давай', 'якщо',
  'або', 'чи',
  'треба', 'потрібно', 'надо', 'необхідно',
  'купити', 'купить', 'купи', 'купімо', 'закупити',
  'взяти', 'візьми', 'візьмемо', 'брати',
  'замовити', 'замов', 'замовимо', 'додати', 'додай', 'докупити', 'докупи',
  'щось', 'шось', 'нам', 'мені', 'собі', 'би', 'б', 'же', 'ж',
  'сьогодні', 'завтра', 'зараз', 'вже', 'уже', 'скоро', 'терміново',
])

const NUMERALS = new Set([
  'два', 'дві', 'три', 'чотири', "п'ять", 'шість', 'сім', 'вісім', "дев'ять",
  'десять', 'пару', 'кілька', 'багато', 'трохи',
])

const ADJ_SUFFIXES = [
  'ий', 'ій',
  'ова', 'ову', 'ева', 'еву', 'єва', 'єву',
  'ена', 'ену', 'єна', 'єну',
  'яна', 'яну', 'ична', 'ичну', 'ічна', 'ічну',
  'еве', 'ове', 'яне', 'ене',
]

function attachesToNext(word: string): boolean {
  if (NUMERALS.has(word)) return true
  return ADJ_SUFFIXES.some(
    (suffix) => word.endsWith(suffix) && word.length > suffix.length + 1,
  )
}

function capitalize(item: string): string {
  return item.charAt(0).toLocaleUpperCase('uk') + item.slice(1)
}

export function splitSpoken(phrase: string): string[] {
  const words = phrase.split(/[\s,;.!?]+/).filter(Boolean)
  const items: string[] = []
  let current: string[] = []

  for (const word of words) {
    const lower = word.toLowerCase()
    if (CONNECTORS.has(lower)) {
      if (current.length > 0) {
        items.push(current.join(' '))
        current = []
      }
      continue
    }
    current.push(word)
    if (!attachesToNext(lower)) {
      items.push(current.join(' '))
      current = []
    }
  }
  if (current.length > 0) items.push(current.join(' '))
  return items.map(capitalize)
}
