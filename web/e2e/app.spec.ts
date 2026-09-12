import { expect, test, type Locator, type Page } from "@playwright/test";

import { AUTO_SWAP_CAP_UAH } from "../src/lib/facts";

import {
  type MockOptions,
  BAR,
  BAR_DROPPED,
  BAR_NO_DRINKS,
  BAR_NO_RECEIPTS,
  BAR_ONLY_DROPPED,
  BAR_UNNAMED,
  basket,
  DELIVERY,
  LINES,
  mockApi,
  PANTRY,
  POSTPONED,
  PROFILE_RULES,
  QUOTA,
  QUOTA_SPENT,
  TOPUP_ITEMS,
  TOTAL,
  withAutoSwap,
} from "./fixtures";


const ONBOARD_KEY = "komora:onboarded";
const TOUR_KEY = "komora:toured";
const PANTRY_TOUR_KEY = "komora:toured-pantry";

/** Гість, який тут не вперше: без онбордингу і без підказок. */
/**
 * Відкрити згорнуті налаштування списку комори (#337).
 *
 * Три дії #109 і перемикач режиму поїхали під `details`: до першого рядка
 * комори було 426 px з 844, і найдорожчий блок був саме цей -- два режими і
 * три дії, які гість чіпає раз (#125, живий прогін 06.09). Стан лишився на
 * екрані заголовком, самі перемикачі -- за одним дотиком, і тести ходять
 * тим самим шляхом, що гість.
 */
async function openListSettings(page: Page): Promise<void> {
  const window_ = page.getByRole("dialog", { name: "Як вести комору" });
  if (await window_.isVisible()) return;
  const gear = page.locator("button.gear");
  if ((await gear.count()) === 0) return;
  await gear.click();
  await expect(window_).toBeVisible();
}

async function skipIntro(page: Page): Promise<void> {
  await page.addInitScript(
    ([onboard, tour, pantryTour]: [string, string, string]) => {
      localStorage.setItem(onboard, "1");
      localStorage.setItem(tour, "1");
      localStorage.setItem(pantryTour, "1");
    },
    [ONBOARD_KEY, TOUR_KEY, PANTRY_TOUR_KEY] as [string, string, string],
  );
}

/**
 * Запустити збірку в режимі «на тиждень» (#284).
 *
 * Замовчування режиму -- «зі списку»: у ньому кошик збирається рівно з того,
 * що гість записав сам, без комори, циклів і добору під суму. Тести, які
 * перевіряють саме комору, мусять назвати режим ВГОЛОС -- інакше вони
 * міряли б не той продукт, який збирає кнопка (#228).
 */
async function buildWeek(page: Page): Promise<void> {
  await toStart(page);
  await page.getByRole("button", { name: "на тиждень", exact: true }).click();
  await page.getByRole("button", { name: /^Зібрати / }).click();
}

/** Підключений гість на робочому екрані — стан, з якого починається продукт. */
async function openApp(page: Page, options: MockOptions = {}): Promise<void> {
  await mockApi(page, options);
  await skipIntro(page);
  await enter(page);
  await expect(page.getByRole("button", { name: /^Зібрати / })).toBeVisible();
}

/**
 * Довести тест до стартового екрана (#341).
 *
 * Після входу відкривається КОМОРА, тож усе, що судить старт, мусить спершу
 * туди дійти. Ідемпотентний навмисно: помічники старту (`buildWeek`) звуть
 * його самі, а тести, які вже стоять на старті, звуть його вдруге -- і
 * другий клік по «На початок» повів би з кошика назад, тобто помічник
 * ламав би те, чому має допомагати.
 */
async function toStart(page: Page): Promise<void> {
  const visible = (locator: Locator) => locator.isVisible().catch(() => false);
  if (await visible(page.getByRole("dialog").first())) return;
  if (!(await visible(page.getByTestId("pantry-screen")))) return;
  await page.getByRole("button", { name: "На початок" }).first().click();
  await expect(page.getByRole("button", { name: /^Зібрати / })).toBeVisible();
}

/**
 * Відкрити застосунок ТАМ, звідки тест судить, -- на старті (#341).
 *
 * Після входу продукт садить гостя в комору, тож голий `goto` більше не
 * означає «я на старті». Один іменований вхід замість тридцяти восьми
 * копій одного рядка: правило, яке кожен тест копіює собі, -- це правило,
 * якого наступний тест не зробить.
 *
 * Хто судить САМУ посадку, зве `goto` напряму і каже це вголос.
 */
async function enter(page: Page): Promise<void> {
  await page.goto("/");
  await toStart(page);
}

/**
 * Перезавантажити сторінку і лишитись там, звідки тест судить (#341).
 *
 * `page.reload()` теж більше не означає «я на старті»: після входу продукт
 * садить гостя в комору, і тести про те, що слово гостя ПЕРЕЖИВАЄ
 * перезавантаження, після нього опинялись не там, де питали.
 *
 * Окремо від `enter`, бо перевіряють вони РІЗНЕ: `goto` -- це новий вхід,
 * `reload` -- та сама вкладка. Один помічник на двох сховав би саме ту
 * різницю, заради якої ці тести й написані.
 */
async function reenter(page: Page): Promise<void> {
  await page.reload();
  await toStart(page);
}

/**
 * Те саме, але лишаючись там, куди продукт садить гостя (#341).
 *
 * Потрібен рівно тим тестам, які про КОМОРУ: заходити в неї з кнопки
 * «Закінчується» означало б перевіряти шлях, яким гість більше не ходить.
 */
async function openPantryApp(
  page: Page,
  options: MockOptions = {},
): Promise<void> {
  await mockApi(page, options);
  await skipIntro(page);
  await page.goto("/");
  await expect(page.getByTestId("pantry-screen")).toBeVisible();
}

/**
 * Відчинити вікно питань комори (#09.09) і віддати саме вікно.
 *
 * Двері, а не картка над списком: питання займали ~330 px з 844 у кожного,
 * хто комору просто гортав. Тести ходять сюди ТИМ САМИМ шляхом, що гість --
 * інакше вони перевіряли б розкладку, якої на екрані немає.
 */
async function openAsks(page: Page): Promise<Locator> {
  await page.locator(".ask-door").click();
  const card = page.getByRole("dialog", { name: "Питання про твій дім" });
  await expect(card).toBeVisible();
  return card;
}

/**
 * «Оформити» разом із кроком замін, коли той стоїть на дорозі (#49).
 *
 * Крок показується не завжди — лише коли є що вирішувати, — тож тести, які
 * перевіряють ЗВІТ, а не крок, проходять його одним викликом і не починають
 * усі однаково.
 */
/**
 * Вхід «Чекає твого рішення» відкриває лише термінове (рішення власника
 * 11.09); тест, якому потрібен весь екран, розкриває решту тут -- як гість,
 * однією кнопкою. Без термінового кнопки немає, і тоді нема чого розкривати.
 */
async function revealRest(page: Page): Promise<void> {
  await page.locator("article.card").first().waitFor();
  const reveal = page.getByTestId("reveal-rest");
  if (await reveal.count()) await reveal.click();
}

async function checkout(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Оформити" }).click();
  const confirm = page.getByRole("button", { name: "Погоджую -- оформити" });
  await confirm.or(page.locator(".paid")).first().waitFor();
  if (await confirm.isVisible()) {
    await page
      .getByRole("checkbox", { name: /Згоден, щоб збирач замінив/ })
      .check();
    await confirm.click();
  }
}

/**
 * Дотик по назві рядка (#72).
 *
 * Прокрутка серединою обов'язкова: рядок під згином Playwright підводить до
 * самого верху, а там його накриває липка шапка — і клік іде в неї. Гість
 * докручує сам, тож це артефакт тесту, а не продукту.
 */
async function tapName(page: Page, name: string): Promise<void> {
  const button = page.getByRole("button", { name, exact: true });
  await button.evaluate((node) => node.scrollIntoView({ block: "center" }));
  await button.click();
}

function opaque(color: string): boolean {
  const alpha = color.match(/rgba\([^)]+,\s*([\d.]+)\)/);
  return alpha === null || Number(alpha[1]) >= 0.99;
}


test("онбординг гортається слайдами і показується рівно один раз", async ({
  page,
}) => {
  await mockApi(page, { session: { connected: false } });
  await enter(page);
  const promo = page.getByRole("dialog", { name: "Про ПанTry" });
  await expect(promo).toBeVisible();

  await expect(promo.getByRole("heading")).toContainText("Знає, що вдома");
  await expect(promo.getByRole("tab")).toHaveCount(4);

  for (let i = 0; i < 3; i += 1)
    await promo.getByRole("button", { name: "Далі" }).click();
  await expect(promo.getByRole("heading")).toContainText("Далі — твій акаунт");

  await promo.getByRole("button", { name: "Далі" }).click();
  await expect(promo).toBeHidden();
  await expect(
    page.getByRole("heading", { name: "Акаунт «Сільпо»" }),
  ).toBeVisible();

  await reenter(page);
  await expect(page.getByRole("dialog", { name: "Про ПанTry" })).toBeHidden();
});

test("онбординг: «пропустити» веде туди ж, куди останній слайд", async ({
  page,
}) => {
  await mockApi(page, { session: { connected: false } });
  await enter(page);
  const promo = page.getByRole("dialog", { name: "Про ПанTry" });
  await promo.getByRole("button", { name: "пропустити" }).click();
  await expect(promo).toBeHidden();
  await reenter(page);
  await expect(page.getByRole("dialog", { name: "Про ПанTry" })).toBeHidden();
});

test("кнопка онбордингу не з'їжджає під згин на низькому екрані", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 560 });
  await mockApi(page);
  await enter(page);
  const go = page
    .getByRole("dialog", { name: "Про ПанTry" })
    .getByRole("button", { name: "Далі" });
  await expect(go).toBeInViewport();

  const box = (await go.boundingBox())!;
  expect(box.y + box.height).toBeLessThanOrEqual(560);
});


test("без акаунта першим екраном ворота, а не чужі дані", async ({ page }) => {
  await mockApi(page, { session: { connected: false } });
  await skipIntro(page);
  await enter(page);

  await expect(
    page.getByRole("heading", { name: "Акаунт «Сільпо»" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /^Зібрати / })).toBeHidden();

  await expect(page.getByText(/чеки, кошик, профіль/)).toBeVisible();
  await expect(page.getByText("чеки офлайн і онлайн")).toBeHidden();

  await page.getByText(/докладно/).click();
  await expect(page.getByText("чеки офлайн і онлайн")).toBeVisible();

  await expect(
    page.getByRole("link", { name: "Підключити «Сільпо»" }),
  ).toBeVisible();
  await expect(page.locator("button.back")).toHaveCount(0);
});

test("онбординг не викликає горизонтальної прокрутки при перемиканні", async ({
  page,
}) => {
  await mockApi(page);
  await enter(page);
  const promo = page.getByRole("dialog", { name: "Про ПанTry" });
  await promo.getByRole("button", { name: "Далі" }).click();

  const overflow = await page.evaluate(
    () =>
      document.documentElement.scrollWidth -
      document.documentElement.clientWidth,
  );
  expect(overflow, "сторінка поїхала вбік").toBeLessThanOrEqual(0);
});

test("кнопка входу прибита до низу екрана", async ({ page }) => {
  await mockApi(page, { session: { connected: false } });
  await skipIntro(page);
  await enter(page);

  const connect = page.getByRole("link", { name: "Підключити «Сільпо»" });
  await expect(connect).toBeVisible();
  const box = (await connect.boundingBox())!;
  const height = page.viewportSize()!.height;
  expect(box.y + box.height).toBeGreaterThan(height * 0.75);
});

test("без бекенда кнопки входу немає, а причина названа словами", async ({
  page,
}) => {
  await mockApi(page, { session: null });
  await skipIntro(page);
  await enter(page);

  await expect(
    page.getByRole("heading", { name: "Акаунт «Сільпо»" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Підключити «Сільпо»" }),
  ).toBeHidden();
  await expect(page.getByText(/Бекенд не відповідає/)).toBeVisible();
});

test("сторінки журі ворота пропускають", async ({ page }) => {
  await mockApi(page, { session: { connected: false } });
  await skipIntro(page);
  await enter(page);
  await page.getByRole("button", { name: "Меню" }).click();
  await page.getByRole("button", { name: /якість/ }).click();
  await expect(page.getByRole("heading", { name: "Якість" })).toBeVisible();
});

test("посилання назовні зі сторінки ідей не забирає гостя з демо", async ({
  page,
}) => {
  await mockApi(page, { session: { connected: false } });
  await skipIntro(page);
  await enter(page);
  await page.getByRole("button", { name: "Меню" }).click();
  await page.getByRole("button", { name: /ідеї/ }).click();

  const out = page.getByRole("link", { name: /схема і кейси ролей/ });
  await expect(out).toHaveAttribute(
    "href",
    "https://pidsobka.m-klimnyk.workers.dev/",
  );
  await expect(out).toHaveAttribute("target", "_blank");
  await expect(out).toHaveAttribute("rel", /noopener/);
  await expect(
    page.getByText("це КОНЦЕПЦІЯ, а не продукт", { exact: false }),
  ).toBeVisible();
});

test("без акаунта жодного запиту по дані не йде", async ({ page }) => {
  const asked: string[] = [];
  await page.route("**/api/**", (route) => {
    asked.push(new URL(route.request().url()).pathname);
    return route.fallback();
  });
  await mockApi(page, { session: { connected: false } });
  await skipIntro(page);
  await enter(page);
  await expect(
    page.getByRole("heading", { name: "Акаунт «Сільпо»" }),
  ).toBeVisible();

  const data = asked.filter((path) => !/\/(auth\/session|health)$/.test(path));
  expect(data, `без акаунта пішли запити: ${data.join(", ")}`).toEqual([]);
});

test("токен помер посеред роботи: екран підключення, а не «збій» (#63)", async ({
  page,
}) => {
  await openApp(page);
  await page.route("**/api/basket", (route) =>
    route.fulfill({
      status: 401,
      json: { detail: "З'єднання із Сільпо розірвано — підключись знову." },
    }),
  );

  await buildWeek(page);

  await expect(
    page.getByRole("heading", { name: "Акаунт «Сільпо»" }),
  ).toBeVisible({
    timeout: 20_000,
  });
});

test("чуже тіло у відповіді не стає банером: гість читає причину, а не верстку (#298)", async ({
  page,
}) => {
  await mockApi(page, {
    checkoutForeign: {
      status: 502,
      body: "<html><head><title>502 Bad gateway</title></head><body>error code: 502</body></html>",
    },
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page.getByRole("button", { name: "Оформити" }).click();
  await page
    .getByRole("checkbox", { name: /Згоден, щоб збирач замінив/ })
    .check();
  await page.getByRole("button", { name: "Погоджую -- оформити" }).click();

  const banner = page.getByRole("alert");
  await expect(banner).toContainText("з'єднання із сервером обірвалось");
  await expect(banner).not.toContainText("502 Bad gateway");
  await expect(banner).not.toContainText("html");
});


test("композер правила непрозорий (живе скло 14.08: мінифікатор губив blur)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: "+ правило" }).click();
  const composer = page
    .getByRole("dialog", { name: "Своє правило" })
    .locator("> div")
    .first();
  await expect(composer).toBeVisible();
  const bg = await composer.evaluate(
    (el) => getComputedStyle(el).backgroundColor,
  );
  expect(opaque(bg), `фон композера просвічує: ${bg}`).toBe(true);
});

test("комора: заглушка без фото і повітря перед доком", async ({ page }) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();
  const list = page.locator('ul.list, ul[class*="list"]').first();
  await expect(list.locator("li").first()).toBeVisible();

  const thumb = list.locator("li").first().locator("div").first();
  await expect(thumb).not.toHaveText("");

  const margin = await list.evaluate((el) => getComputedStyle(el).marginBottom);
  expect(parseFloat(margin)).toBeGreaterThanOrEqual(12);

  await expect(
    page.getByRole("button", { name: "На початок" }).last(),
  ).toBeVisible();
});

test("комора каже, що саме триває, поки вона рахується (#56)", async ({
  page,
}) => {
  await mockApi(page, { pantry: "slow" });
  await skipIntro(page);
  await enter(page);

  const wait = page.locator('[data-wait="pantry"]');
  await expect(wait).toBeVisible({ timeout: 15_000 });
  await expect(wait).toHaveAttribute("data-step", /place|history|kinds/);
  await expect(
    page.getByText(
      /^(get_my_delivery_addresses|get_my_offline_orders|модель)$/,
    ),
  ).toBeVisible();

  await expect(wait).toHaveAttribute("data-step", "kinds", { timeout: 10_000 });
  await expect(page.getByText(/назви видів рахує модель/)).toBeVisible();
});

test("комора чекає ВІКНОМ АГЕНТА: справжні кроки і факти про дім (#341)", async ({
  page,
}) => {
  await openPantryApp(page, { pantry: "slow" });

  const window = page.locator(".running");
  await expect(window).toBeVisible({ timeout: 15_000 });
  await expect(window.getByText("Заповнюю комору")).toBeVisible();
  const live = window.locator(".step.live");
  await expect(live).toHaveAttribute("data-step", /place|history|kinds/);
  await expect(window.getByText(/^\d+ с/)).toBeVisible();
  await expect(window.getByText("%")).toHaveCount(0);
});

test("заповнення ЗАКРИВАЄ комору, а не стоїть над неназваними рядками", async ({
  page,
}) => {
  await openPantryApp(page, { pantryCold: true, pantryLoop: "slow" });

  const window = page.locator(".running");
  await expect(window).toBeVisible({ timeout: 15_000 });
  await expect(window.getByText("Заповнюю комору")).toBeVisible();
  await expect(page.locator(".rail")).toHaveCount(0);
  await expect(page.getByPlaceholder("знайти у коморі")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: /Назад|Комора|Закрити/ }),
  ).toBeTruthy();
});

test("кроки заповнення можна забрати ОДНИМ json (прохання власника 09.09)", async ({
  page,
}) => {
  await openPantryApp(page, { pantryCold: true, pantryLoop: "slow" });

  const window = page.locator(".running");
  await expect(window).toBeVisible({ timeout: 15_000 });
  await expect(window.locator(".copy-all")).toHaveText(
    /копіювати кроки \(\d+\)/,
    {
      timeout: 15_000,
    },
  );
});

test("двері в комору є і ПОКИ вона читається (живий тест 09.09)", async ({
  page,
}) => {
  await mockApi(page, { pantry: "slow" });
  await skipIntro(page);
  await page.goto("/");
  await toStart(page);

  const door = page.locator("button.stock");
  await expect(door).toBeVisible();
  await door.click();
  await expect(page.getByTestId("pantry-screen")).toBeVisible();
  await expect(page.locator(".running")).toBeVisible();
});

test("готова комора не лишає по собі підписів кроків (#56)", async ({
  page,
}) => {
  await openApp(page);
  await expect(
    page.getByRole("button", { name: /Закінчується/ }),
  ).toBeVisible();
  await expect(
    page.getByText(/Читаю чеки|Дивлюсь, у якому ти магазині/),
  ).toHaveCount(0);
});

test("порожня комора каже, що вона порожня, і не питається вдруге (#56)", async ({
  page,
}) => {
  const asked: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.endsWith("/api/pantry"))
      asked.push(request.url());
  });

  await mockApi(page, { pantry: "empty" });
  await skipIntro(page);
  await enter(page);
  await toStart(page);
  await expect(page.getByText(/Комора наповнюється сама/)).toBeVisible();

  await page.getByRole("button", { name: "зі списку", exact: true }).click();
  await page.getByPlaceholder(/молоко/i).fill("молоко");
  await page.getByRole("button", { name: /Зібрати зі списку/ }).click();
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page.getByRole("button", { name: "комора", exact: true }).click();
  await expect(page.getByText(/Комора наповнюється сама/)).toBeVisible();

  await page.getByRole("button", { name: "кошик", exact: true }).click();
  await page.getByRole("button", { name: "комора", exact: true }).click();
  await expect(page.getByText(/Комора наповнюється сама/)).toBeVisible();
  expect(asked).toHaveLength(1);
});

test("гість, який лише замовляє доставку, не чує «покупок не видно» (#234)", async ({
  page,
}) => {
  await mockApi(page, { pantry: "delivery-only" });
  await skipIntro(page);
  await enter(page);

  await expect(page.getByText(/Комора наповнюється сама/)).toHaveCount(0);
  await expect(
    page.getByText(/Перші покупки вже бачу: 76.замовлень/),
  ).toBeVisible();
});

test("новому гостю не пропонують кнопку, яка гарантовано відмовить (#38)", async ({
  page,
}) => {
  await mockApi(page, { pantry: "empty" });
  await skipIntro(page);
  await enter(page);

  await page.getByRole("button", { name: "на тиждень", exact: true }).click();
  const run = page.getByRole("button", { name: /^Зібрати / });
  await expect(run).toBeDisabled();
  await expect(page.getByText(/Напиши, що потрібно/)).toBeVisible();

  await page.getByRole("button", { name: "зі списку", exact: true }).click();
  await page.getByPlaceholder(/молоко/i).fill("молоко, хліб");
  const byList = page.getByRole("button", { name: /Зібрати зі списку/ });
  await expect(byList).toBeEnabled();
  await expect(page.getByText(/підберу з полиці/)).toBeVisible();
});

test("чеки є, а комора порожня — це третій стан, і він не «чеків немає» (#38)", async ({
  page,
}) => {
  await mockApi(page, { pantry: "fresh" });
  await skipIntro(page);
  await enter(page);
  await toStart(page);
  await page.getByRole("button", { name: "на тиждень", exact: true }).click();

  await expect(page.getByText(/Перші покупки вже бачу: 2.чеки/)).toBeVisible();
  await expect(page.getByText(/Комора наповнюється сама/)).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Зібрати / })).toBeDisabled();
  await expect(page.getByText(/Напиши, що потрібно/)).toBeVisible();
});

test("інша адреса — інша комора: запит повторюється (#56)", async ({
  page,
}) => {
  const asked: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.endsWith("/api/pantry"))
      asked.push(request.url());
  });

  await openApp(page);
  await expect.poll(() => asked.length).toBe(1);

  await page.getByRole("button", { name: /змінити/ }).click();
  await page.getByLabel("Адреса доставки").fill("Вінниця, Пирогова, 20");
  await page.getByRole("button", { name: "Знайти" }).click();
  await page
    .getByRole("button", { name: "Вінниця, вулиця Пирогова, 20" })
    .click();

  await expect.poll(() => asked.length).toBe(2);
});

test("комора: нуль лишається тільки там, де воно закінчилось (#62)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();
  const list = page.locator('ul.list, ul[class*="list"]').first();

  const oil = list.locator("li").filter({ hasText: "Олія оливкова" });
  await expect(oil.getByText("ще ~1 дн")).toBeVisible();
  await expect(oil.getByText("0", { exact: true })).toHaveCount(0);
  await expect(
    oil.getByRole("button", { name: "Менше: Олія оливкова" }),
  ).toHaveCount(0);
  const oilBar = oil.getByRole("progressbar");
  expect(Number(await oilBar.getAttribute("aria-valuenow"))).toBeGreaterThan(0);

  const tuna = list.locator("li").filter({ hasText: "Тунець" });
  await expect(tuna.getByText("закінчилось", { exact: true })).toBeVisible();
  await expect(tuna.getByRole("progressbar")).toHaveAttribute(
    "aria-valuenow",
    "0",
  );

  const rice = list.locator("li").filter({ hasText: "Рис" });
  await expect(rice.getByText("2 уп")).toBeVisible();
  await expect(rice.getByRole("button", { name: "Менше: Рис" })).toBeVisible();
  await expect(rice.getByText("ще ~12 дн")).toBeVisible();
});

test("екран збору каже правду про кроки і думає вголос про ТВІЙ дім", async ({
  page,
}) => {
  await mockApi(page, { build: "slow" });
  await skipIntro(page);
  await enter(page);
  await page.keyboard.press("`");
  await buildWeek(page);

  const running = page.locator(".running");
  await expect(running).toBeVisible();
  await expect(running.getByText("%")).toHaveCount(0);
  await expect(running.getByText("get_my_offline_orders")).toBeVisible({
    timeout: 4000,
  });

  await expect(running.getByText(/^\d+ с/)).toBeVisible();
  const first = await running.getByText(/^\d+ с/).textContent();
  await page.waitForTimeout(2500);
  const later = await running.getByText(/^\d+ с/).textContent();
  expect(later).not.toBe(first);

  const knows = running.locator(".thought").filter({ hasText: "Твоя комора" });
  await expect(knows).toBeVisible({ timeout: 9000 });
  expect((await knows.innerText()).replace(/\s+/g, " ")).toContain(
    "це 10 видів",
  );
});

test("доданий руками вид бере одиницю з чеків, а не «шт» з дефолту (#39)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();
  await page.getByRole("button", { name: "+ Додати" }).click();
  await page.getByPlaceholder(/вид, а не марка/).fill("свинина");
  await page.getByRole("button", { name: "Додати в комору" }).click();

  const list = page.locator('ul.list, ul[class*="list"]').first();
  const row = list.locator("li").filter({ hasText: "свинина" });
  await expect(row).toBeVisible();
  await expect(row.getByText(/у чеках це Свинина охолоджена/)).toBeVisible();
  await expect(row.getByText("шт", { exact: true })).toHaveCount(0);
  await expect(row.getByRole("button", { name: /^Менше/ })).toHaveCount(0);
});

test("дописаний вид переживає перезавантаження сторінки (#126)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();
  await page.getByRole("button", { name: "+ Додати" }).click();
  await page.getByPlaceholder(/вид, а не марка/).fill("васабі");
  await page.getByRole("button", { name: "Додати в комору" }).click();
  await expect(page.getByText(/у чеках «Сільпо» такого немає/)).toBeVisible();

  await reenter(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  await expect(page.getByText("васабі").first()).toBeVisible();
});

test("комору можна перевести на себе, і чеки перестають додавати рядки (#109)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();
  const rows = page.locator('ul.list, ul[class*="list"]').first().locator("li");
  await expect(rows.first()).toBeVisible();

  await openListSettings(page);
  await page.getByRole("button", { name: "веду сам", exact: true }).click();

  await expect(page.locator(".intro")).toContainText("Цей список ведеш ти");
  await expect(rows).toHaveCount(0);
  await expect(page.locator(".outside")).toContainText(/є ще \d+ видів/);
});

test("«скласти з покупок» наповнює список гостя (#109)", async ({ page }) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();
  await openListSettings(page);
  await page.getByRole("button", { name: "веду сам", exact: true }).click();
  const rows = page.locator('ul.list, ul[class*="list"]').first().locator("li");
  await expect(rows).toHaveCount(0);

  await openListSettings(page);
  await page.getByRole("button", { name: "Скласти з покупок" }).click();

  await expect(rows.first()).toBeVisible();
  await expect(page.locator(".outside")).toHaveCount(0);
});

test("«на наступну покупку» кладе те, що закінчується, у список з підставами (#306)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();
  await page.getByRole("button", { name: "На наступну покупку" }).click();

  await expect(page.locator(".deed-said")).toContainText("додав");

  await page.getByText("До покупок").click();
  const want = page.locator(".want").first();
  await expect(want).toBeVisible();
  await expect(want).toContainText("закінчилось сьогодні");
});

test("перерахунок списку не чіпає того, що гість набрав руками (#306)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByPlaceholder(/треба щось конкретне/).fill("батарейки");
  await page.getByRole("button", { name: "+ у список на потім" }).click();
  await expect(
    page.locator(".want").filter({ hasText: "батарейки" }),
  ).toBeVisible();

  await page.getByRole("button", { name: /Закінчується/ }).click();
  await page.getByRole("button", { name: "На наступну покупку" }).click();
  await page.getByRole("button", { name: "На наступну покупку" }).click();
  await expect(page.locator(".deed-said")).toContainText("без змін");

  await page.getByText("До покупок").click();
  await expect(
    page.locator(".want").filter({ hasText: "батарейки" }),
  ).toBeVisible();
});

test("стирання списку питає підтвердження і не чіпає рядки з покупок (#109)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();
  const rows = page.locator('ul.list, ul[class*="list"]').first().locator("li");
  const before = await rows.count();

  await openListSettings(page);
  await page.getByRole("button", { name: "Стерти список" }).click();
  await expect(
    page.getByRole("button", { name: "Точно стерти" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Точно стерти" }).click();

  await expect(rows).toHaveCount(before);
});

test("дописаний рядок каже, що поїде в кошик (#105)", async ({ page }) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();
  await page.getByRole("button", { name: "+ Додати" }).click();
  await page.getByPlaceholder(/вид, а не марка/).fill("васабі");
  await page.getByRole("button", { name: "Додати в комору" }).click();

  await expect(
    page.getByText(/такого немає — беру в наступний кошик/),
  ).toBeVisible();
});

test("на акаунті без жодного чека комору можна вести списком (#126)", async ({
  page,
}) => {
  await mockApi(page, { pantry: "empty" });
  await skipIntro(page);
  await enter(page);

  await page.getByRole("button", { name: /Записати, що вдома/ }).click();
  await page.getByRole("button", { name: "+ Додати" }).click();
  await page.getByPlaceholder(/вид, а не марка/).fill("васабі, хліб");
  await page.getByRole("button", { name: "Додати в комору" }).click();

  await expect(page.getByText("васабі").first()).toBeVisible();
  await expect(page.getByText("хліб").first()).toBeVisible();
  await expect(page.getByText(/у чеках «Сільпо» такого немає/)).toHaveCount(2);

  await reenter(page);

  await expect(page.getByText(/2 видів у списку/)).toBeVisible();
  await page.getByRole("button", { name: /у списку/ }).click();

  await expect(page.getByText("васабі").first()).toBeVisible();
  await expect(page.getByText("хліб").first()).toBeVisible();
});

test("дописаний вид можна прибрати, а рядок з чеків — ні (#126)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();
  await page.getByRole("button", { name: "+ Додати" }).click();
  await page.getByPlaceholder(/вид, а не марка/).fill("васабі");
  await page.getByRole("button", { name: "Додати в комору" }).click();

  const list = page.locator('ul.list, ul[class*="list"]').first();
  const mine = list.locator("li").filter({ hasText: "васабі" });
  await expect(mine.getByRole("button", { name: /^Прибрати/ })).toBeVisible();

  const fromReceipts = list.locator("li").filter({ hasText: PANTRY[0]!.label });
  await expect(
    fromReceipts.getByRole("button", { name: /^Прибрати/ }),
  ).toHaveCount(0);

  await expect(page.getByText(/у чеках «Сільпо» такого немає/)).toBeVisible();
  await mine.getByRole("button", { name: /^Прибрати/ }).click();
  await expect(mine).toHaveCount(0);

  await reenter(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();
  await expect(page.getByText("васабі")).toHaveCount(0);
});

test("незнайомий вид лишається без одиниці, а не вигаданим (#39)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();
  await page.getByRole("button", { name: "+ Додати" }).click();
  await page.getByPlaceholder(/вид, а не марка/).fill("васабі");
  await page.getByRole("button", { name: "Додати в комору" }).click();

  const row = page.locator("li").filter({ hasText: "васабі" });
  await expect(row.getByText(/у чеках «Сільпо» такого немає/)).toBeVisible();
  await expect(row.getByText("шт", { exact: true })).toHaveCount(0);
});

test("доданий рядок стає ПЕРШИМ, а не падає в хвіст списку (#85)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const rows = page.locator('ul.list, ul[class*="list"]').first().locator("li");
  await expect(rows.first()).not.toContainText("васабі");

  await page.getByRole("button", { name: "+ Додати" }).click();
  await page.getByPlaceholder(/вид, а не марка/).fill("васабі");
  await page.getByRole("button", { name: "Додати в комору" }).click();

  await expect(rows.first()).toContainText("васабі");
});

test("вид, який комора вже веде, не роздвоюється на порожнього близнюка (#85)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const rows = page.locator('ul.list, ul[class*="list"]').first().locator("li");
  await page.getByRole("button", { name: "+ Додати" }).click();
  await page.getByPlaceholder(/вид, а не марка/).fill("Рис жасминовий");
  await page.getByRole("button", { name: "Додати в комору" }).click();

  const rice = rows.filter({ hasText: "Рис" });
  await expect(rice).toHaveCount(1);
  await expect(rice.first()).toContainText("цикл ~19 дн");
  await expect(rows.first()).toContainText("Рис");
});

async function stubSpeech(
  page: Page,
  options: { deaf?: boolean } = {},
): Promise<void> {
  await page.addInitScript((opts: { deaf?: boolean }) => {
    class FakeRecognition {
      lang = "";
      continuous = false;
      interimResults = false;
      onresult: ((event: unknown) => void) | null = null;
      onerror: ((event: { error: string }) => void) | null = null;
      onend: (() => void) | null = null;
      start() {
        const w = window as unknown as Record<string, unknown>;
        w.__rec = this;
        w.__starts = ((w.__starts as number) ?? 0) + 1;
        if (opts.deaf) setTimeout(() => this.onend?.(), 0);
      }
      stop() {
        this.onend?.();
      }
    }
    const w = window as unknown as Record<string, unknown>;
    w.SpeechRecognition = FakeRecognition;
    w.webkitSpeechRecognition = FakeRecognition;
    w.__say = (text: string, final: boolean) => {
      const rec = w.__rec as InstanceType<typeof FakeRecognition> | undefined;
      rec?.onresult?.({
        resultIndex: 0,
        results: [{ isFinal: final, 0: { transcript: text } }],
      });
    };
    w.__fail = (code: string) => {
      const rec = w.__rec as InstanceType<typeof FakeRecognition> | undefined;
      rec?.onerror?.({ error: code });
    };
    w.__grow = (texts: string[]) => {
      const rec = w.__rec as InstanceType<typeof FakeRecognition> | undefined;
      rec?.onresult?.({
        resultIndex: 0,
        results: texts.map((text) => ({ isFinal: true, 0: { transcript: text } })),
      });
    };
    w.__tick = (name: string) => {
      const rec = w.__rec as unknown as Record<
        string,
        (() => void) | undefined
      >;
      rec?.[`on${name}`]?.();
    };
  }, options);
}

async function openPantryForm(page: Page): Promise<void> {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();
  await page.getByRole("button", { name: "+ Додати" }).click();
}

async function openPantryAdd(page: Page): Promise<void> {
  await openPantryForm(page);
  await page.getByRole("button", { name: "надиктувати назву" }).click();
  await expect(page.getByRole("dialog", { name: "Диктування" })).toBeVisible();
}

test("«вже купив» забирає рядок із «закінчилось» (#73)", async ({ page }) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const row = page
    .locator("li.row")
    .filter({ hasText: "Тунець консервований" });
  await expect(row).toContainText("мабуть, закінчилось");

  await row.getByRole("button", { name: "вже купив" }).click();

  await page
    .getByRole("dialog", { name: "Скільки взяв" })
    .getByRole("button", { name: "просто купив" })
    .click();

  await expect(row).not.toContainText("мабуть, закінчилось");
  await expect(row).toContainText("взято сьогодні");
  await expect(row.getByRole("button", { name: "вже купив" })).toHaveCount(0);
});

test("«вже купив» дає сказати, СКІЛЬКИ саме (#99)", async ({ page }) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const row = page.locator("li.row").filter({ hasText: "Йогурт питний" });
  await expect(row).toContainText("мабуть, закінчилось");
  await row.getByRole("button", { name: "вже купив" }).click();

  const ask = page.getByRole("dialog", { name: "Скільки взяв" });
  await expect(ask).toContainText("звично береш 4 шт");
  await ask.getByRole("button", { name: /^2/ }).click();

  await expect(row).toContainText("удома ~2 шт");
  await expect(row).not.toContainText("мабуть, закінчилось");
  await expect(row).toContainText("ще ~4 дн");
});

test("ваговий вид питає частками, а не штуками (#99)", async ({ page }) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const row = page.locator("li.row").filter({ hasText: "Філе куряче" });
  await row.getByRole("button", { name: "вже купив" }).click();

  const ask = page.getByRole("dialog", { name: "Скільки взяв" });
  await expect(ask).toContainText("звично береш 0,6 кг");
  await ask.getByRole("button", { name: /^0,3/ }).click();

  await expect(row).toContainText("удома ~0,3 кг");
  await expect(row).not.toContainText("мабуть, закінчилось");
});

test("«просто купив» лишається дією без числа (#99)", async ({ page }) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const row = page.locator("li.row").filter({ hasText: "Йогурт питний" });
  await row.getByRole("button", { name: "вже купив" }).click();
  await page
    .getByRole("dialog", { name: "Скільки взяв" })
    .getByRole("button", { name: "просто купив" })
    .click();

  await expect(row).toContainText("взято сьогодні");
  await expect(row).not.toContainText("мабуть, закінчилось");
});

test("питання про кількість можна закрити, нічого не сказавши (#99)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const row = page.locator("li.row").filter({ hasText: "Йогурт питний" });
  await row.getByRole("button", { name: "вже купив" }).click();
  await page
    .getByRole("dialog", { name: "Скільки взяв" })
    .getByRole("button", { name: "Скасувати" })
    .click();

  await expect(page.getByRole("dialog", { name: "Скільки взяв" })).toHaveCount(
    0,
  );
  await expect(row).toContainText("мабуть, закінчилось");
});

test("кожен рядок з чеків дає сказати, на скільки вистачає (#144)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const uneven = page.locator("li.row").filter({ hasText: "Кетчуп" });
  await expect(uneven).toContainText("береш нерівно");
  await expect(uneven.getByRole("button", { name: "вже купив" })).toHaveCount(
    0,
  );

  await uneven
    .getByRole("button", { name: /сказати, на скільки вистачає/ })
    .click();
  await page
    .getByRole("dialog", { name: "На скільки вистачає" })
    .getByRole("button", { name: "на 3 дні" })
    .click();

  await expect(uneven).toContainText("вистачає на ~3 дн");
  await expect(uneven).not.toContainText("оцінка");
  await expect(uneven.getByRole("button", { name: "вже купив" })).toBeVisible();

  await expect(uneven).not.toContainText("вистачає на ~3 дн?");
  await expect(uneven.locator(".state")).toHaveCount(1);
});

test("назване число переживає перечитування комори (#144, #126)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const row = page.locator("li.row").filter({ hasText: "Морозиво" });
  await row
    .getByRole("button", { name: /сказати, на скільки вистачає/ })
    .click();
  await page
    .getByRole("dialog", { name: "На скільки вистачає" })
    .getByRole("button", { name: "на 2 дні" })
    .click();
  await expect(row).toContainText("вистачає на ~2 дн");

  await page.getByRole("button", { name: "На початок" }).first().click();
  await page.getByRole("button", { name: /Закінчується/ }).click();

  await expect(
    page.locator("li.row").filter({ hasText: "Морозиво" }),
  ).toContainText("вистачає на ~2 дн");
});

test("назване число можна зняти, і рядок повертається до оцінки (#144)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const row = page.locator("li.row").filter({ hasText: "Морозиво" });
  await row
    .getByRole("button", { name: /сказати, на скільки вистачає/ })
    .click();
  await page
    .getByRole("dialog", { name: "На скільки вистачає" })
    .getByRole("button", { name: "на 2 дні" })
    .click();
  await expect(row).toContainText("вистачає на ~2 дн");
  await expect(row).not.toContainText("оцінка");

  await row
    .getByRole("button", { name: /виправити, на скільки вистачає/ })
    .click();
  await page
    .getByRole("dialog", { name: "На скільки вистачає" })
    .getByRole("button", { name: "рахуй з чеків" })
    .click();

  await expect(row).toContainText("давно не брав: 76 дн при звичних ~32");
});

test("своє число не впирається в нашу стелю кратності (#144)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const row = page
    .locator("li.row")
    .filter({ hasText: "Тунець консервований" });
  await row.getByRole("button", { name: "вже купив" }).click();

  const ask = page.getByRole("dialog", { name: "Скільки взяв" });
  await expect(ask.getByRole("button", { name: /^10 шт/ })).toHaveCount(0);
  await ask.getByLabel("або скільки саме").fill("10");
  await ask.getByRole("button", { name: "Записати" }).click();

  await expect(row).toContainText("удома ~10 шт");
});

test("«вже купив» є лише там, де комора справді сперечається (#73)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const full = page.locator("li.row").filter({ hasText: "Сіль" });
  await expect(full).toContainText("ще ~84 дн");
  await expect(full.getByRole("button", { name: "вже купив" })).toHaveCount(0);
});

test("дублікат у коморі каже про себе, а не мовчить (#73)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();
  await page.getByRole("button", { name: "+ Додати" }).click();
  await page.getByLabel(/що вже стоїть у коморі/).fill("Рис");
  await page.getByRole("button", { name: "Додати в комору" }).click();

  await expect(page.getByRole("alert")).toContainText("«Рис» уже в коморі");
});

test("пошук у коморі знаходить вид, якого не видно без прокрутки (#93)", async ({
  page,
}) => {
  const asked: string[] = [];
  await mockApi(page, { pantry: "long" });
  await skipIntro(page);
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.endsWith("/api/pantry"))
      asked.push(request.url());
  });
  await enter(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const target = page.getByText("Запас 33", { exact: true });
  await expect(target).toHaveCount(1);
  await expect(target).not.toBeInViewport();

  const before = asked.length;
  await page.getByLabel("знайти у коморі").fill("запас 33");

  await expect(page.locator(".pantry li.row")).toHaveCount(1);
  await expect(target).toBeInViewport();
  await expect(page.getByText("1 з 43")).toBeVisible();
  expect(asked.length, "фільтр не ходить у мережу").toBe(before);
});

test("рейка відділів фільтрує комору, а не переставляє її (#337)", async ({
  page,
}) => {
  await mockApi(page, { pantry: "long" });
  await skipIntro(page);
  await enter(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const rail = page.getByRole("navigation", { name: "Відділи комори" });
  await expect(rail).toBeVisible();

  const all = await page.locator(".pantry li.row").count();
  await rail.getByRole("button", { name: /Для дому/ }).click();

  const some = await page.locator(".pantry li.row").count();
  expect(some, "відділ ріже список").toBeGreaterThan(0);
  expect(some, "відділ ріже список").toBeLessThan(all);
  await expect(page.getByText(/Відділ «Для дому»/)).toBeVisible();

  await page.getByRole("button", { name: "показати все" }).click();
  await expect(page.locator(".pantry li.row")).toHaveCount(all);
});

test("повторний дотик по відділу знімає фільтр (#337)", async ({ page }) => {
  await mockApi(page, { pantry: "long" });
  await skipIntro(page);
  await enter(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const all = await page.locator(".pantry li.row").count();
  const aisle = page
    .getByRole("navigation", { name: "Відділи комори" })
    .getByRole("button", { name: /Для дому/ });
  await aisle.click();
  await expect(aisle).toHaveAttribute("aria-pressed", "true");
  await aisle.click();
  await expect(aisle).toHaveAttribute("aria-pressed", "false");
  await expect(page.locator(".pantry li.row")).toHaveCount(all);
});

test("рейки немає там, де відділ один: вона нічого не розводить (#337)", async ({
  page,
}) => {
  await mockApi(page, { pantry: "one-aisle" });
  await skipIntro(page);
  await enter(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  await expect(page.locator(".pantry li.row").first()).toBeVisible();
  await expect(
    page.getByRole("navigation", { name: "Відділи комори" }),
  ).toHaveCount(0);
});

test("колесо над рейкою крутить рейку, а не сторінку (#337)", async ({
  page,
}) => {
  await mockApi(page, { pantry: "long" });
  await skipIntro(page);
  await enter(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const rail = page.getByRole("navigation", { name: "Відділи комори" });
  const room = await rail.evaluate((el) => el.scrollWidth - el.clientWidth);
  expect(room, "рейці є куди їхати").toBeGreaterThan(0);

  await rail.hover();
  await page.mouse.wheel(0, 200);

  await expect
    .poll(() => rail.evaluate((el) => el.scrollLeft))
    .toBeGreaterThan(0);
});

test("стрілка рейки стоїть на одній лінії з чипами (#337)", async ({
  page,
}) => {
  await mockApi(page, { pantry: "long" });
  await skipIntro(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await enter(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const rail = page.getByRole("navigation", { name: "Відділи комори" });
  await expect(rail).toBeVisible();
  const ahead = page.getByRole("button", { name: "Наступні відділи" });
  await expect(ahead).toBeVisible();

  const middles = await rail.evaluate((el) => {
    const mid = (n: Element | null) => {
      if (n === null) return null;
      const b = n.getBoundingClientRect();
      return b.top + b.height / 2;
    };
    return {
      chip: mid(el.querySelector("button")),
      arrow: mid(el.parentElement!.querySelector(".rail-step.ahead")),
      wrap: el.parentElement!.getBoundingClientRect().height,
      rail: el.getBoundingClientRect().height,
    };
  });

  expect(middles.chip).not.toBeNull();
  expect(middles.arrow).not.toBeNull();
  expect(
    Math.abs((middles.arrow ?? 0) - (middles.chip ?? 0)),
    "значок стрілки на одній лінії з текстом чипа",
  ).toBeLessThan(1);
  expect(
    Math.abs(middles.wrap - middles.rail),
    "обгортка не вища за рейку: усе, що позиціонується від неї, інакше з'їжджає",
  ).toBeLessThan(1);
});

test("стрілки рейки стоять лише там, куди є куди їхати (#337)", async ({
  page,
}) => {
  await mockApi(page, { pantry: "long" });
  await skipIntro(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await enter(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const rail = page.getByRole("navigation", { name: "Відділи комори" });
  await expect(rail).toBeVisible();
  const ahead = page.getByRole("button", { name: "Наступні відділи" });
  const back = page.getByRole("button", { name: "Попередні відділи" });

  await expect(ahead).toBeVisible();
  await expect(back).toHaveCount(0);

  await ahead.click();
  await expect
    .poll(() => rail.evaluate((el) => el.scrollLeft))
    .toBeGreaterThan(0);
  await expect(back).toBeVisible();

  await rail.evaluate((el) => (el.scrollLeft = el.scrollWidth));
  await expect(ahead).toHaveCount(0);
  await expect(back).toBeVisible();
});

test("на краю рейка віддає колесо сторінці (#337)", async ({ page }) => {
  await mockApi(page, { pantry: "long" });
  await skipIntro(page);
  await enter(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const rail = page.getByRole("navigation", { name: "Відділи комори" });
  await rail.evaluate((el) => (el.scrollLeft = el.scrollWidth));

  await rail.hover();
  await page.mouse.wheel(0, 200);

  await expect
    .poll(() => page.evaluate(() => window.scrollY))
    .toBeGreaterThan(0);
});

test("речення про вид читається цілком, а не в один рядок (#337)", async ({
  page,
}) => {
  await mockApi(page);
  await skipIntro(page);
  await enter(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const row = page
    .locator(".pantry li.row")
    .filter({ hasText: "Туалетний папір" })
    .first();
  await row.getByRole("button", { name: /докладніше/ }).click();
  const sense = page.getByRole("list").getByText(/паперові рушники витрачають/);
  await expect(sense).toBeVisible();
  const clipped = await sense.evaluate(
    (el) => el.scrollWidth > el.clientWidth + 1,
  );
  expect(clipped, "речення про вид обрізане по горизонталі").toBe(false);
});

test("налаштування списку -- за однією кнопкою, а стан лишається на екрані (#337)", async ({
  page,
}) => {
  await mockApi(page);
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const gear = page.locator("button.gear");
  await expect(gear).toHaveText("з покупок");
  await expect(
    page.getByRole("button", { name: "веду сам", exact: true }),
  ).toBeHidden();

  await gear.click();
  const window_ = page.getByRole("dialog", { name: "Як вести комору" });
  await expect(window_).toBeVisible();
  await expect(
    window_.getByRole("button", { name: "Скласти з покупок" }),
  ).toBeVisible();

  await window_.getByRole("button", { name: "веду сам", exact: true }).click();
  await expect(window_).toBeHidden({ timeout: 15_000 });
  await expect(gear).toHaveText("веду сам", { timeout: 15_000 });
});

test("фото товару не з'їжджає, коли розкрити назви (#337)", async ({
  page,
}) => {
  await mockApi(page, { pantry: "twins" });
  await skipIntro(page);
  await enter(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const row = page
    .locator(".pantry li.row")
    .filter({ has: page.getByRole("button", { name: /докладніше|згорнути/ }) })
    .first();
  const toggle = row.getByRole("button", { name: /докладніше|згорнути/ }).first();
  const thumb = row.locator(".thumb").first();

  const offset = async () => {
    const [box, top] = await Promise.all([
      thumb.boundingBox(),
      row.boundingBox(),
    ]);
    return Math.round((box?.y ?? 0) - (top?.y ?? 0));
  };

  const closed = await offset();
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");

  expect(await offset(), "фото з'їхало разом із висотою рядка").toBe(closed);
});

test("значок «розгорнути назви» не стрибає при відкритті (#337)", async ({
  page,
}) => {
  await mockApi(page, { pantry: "twins" });
  await skipIntro(page);
  await enter(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const toggle = page
    .getByRole("list")
    .getByRole("button", { name: /докладніше|згорнути/ })
    .first();
  const closed = await toggle.boundingBox();
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  const open = await toggle.boundingBox();
  expect(open?.width, "кнопка змінила ширину разом зі стрілкою").toBe(
    closed?.width,
  );
});

test("чого в коморі немає — сказано, і поруч дія (#93)", async ({ page }) => {
  await mockApi(page, { pantry: "long" });
  await skipIntro(page);
  await enter(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  await page.getByLabel("знайти у коморі").fill("шафран");
  await expect(page.getByText("«шафран» у коморі немає")).toBeVisible();

  await page.getByRole("button", { name: "Додати цей вид" }).click();
  await expect(
    page.getByRole("dialog", { name: "Додати в комору" }),
  ).toBeVisible();
  await expect(page.getByLabel(/що вже стоїть у коморі/)).toHaveValue("шафран");
});

test("коротка комора обходиться без пошуку (#93)", async ({ page }) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  await expect(
    page.getByRole("button", { name: "Додати", exact: false }).first(),
  ).toBeVisible();
  await expect(page.getByLabel("знайти у коморі")).toHaveCount(0);
});

test("голос у коморі: «Готово» кладе почуте в поле, а не одразу в комору (#32)", async ({
  page,
}) => {
  await stubSpeech(page);
  await openPantryAdd(page);
  await page.evaluate(() => (window as any).__say("халва і родзинки", true));
  await expect(page.getByText("Готово — додати (2)")).toBeVisible();
  await page.getByRole("button", { name: /Готово — додати/ }).click();

  await expect(page.locator("#pantry-add")).toHaveValue("Халва, Родзинки");
  await expect(
    page.locator("ul.list").getByText("Халва", { exact: true }),
  ).toHaveCount(0);

  await page.getByRole("button", { name: "Додати в комору" }).click();
  await expect(
    page.locator("ul.list").getByText("Халва", { exact: true }),
  ).toBeVisible();
  await expect(
    page.locator("ul.list").getByText("Родзинки", { exact: true }),
  ).toBeVisible();
});

test("голос у коморі: надиктоване дописується до вже набраного", async ({
  page,
}) => {
  await stubSpeech(page);
  await openPantryForm(page);
  await page.locator("#pantry-add").fill("рис");
  await page.getByRole("button", { name: "надиктувати назву" }).click();
  await expect(page.getByRole("dialog", { name: "Диктування" })).toBeVisible();
  await page.evaluate(() => (window as any).__say("гречка", true));
  await page.getByRole("button", { name: /Готово — додати/ }).click();
  await expect(page.locator("#pantry-add")).toHaveValue("рис, Гречка");
});

test("голос у коморі: «Готово» забирає і чернетку, не лише зафіксоване", async ({
  page,
}) => {
  await stubSpeech(page);
  await openPantryAdd(page);
  await page.evaluate(() => (window as any).__say("гречка", false));
  await page.getByRole("button", { name: "Готово", exact: true }).click();
  await expect(page.locator("#pantry-add")).toHaveValue("Гречка");
});

test("голос у коморі: відмова мікрофона видима, а не мовчазна", async ({
  page,
}) => {
  await stubSpeech(page);
  await openPantryAdd(page);
  await page.evaluate(() => (window as any).__fail("not-allowed"));
  await page.evaluate(() =>
    ((window as any).__rec as { onend: () => void }).onend(),
  );
  await expect(page.getByRole("alert")).toContainText("мікрофон заборонено");
});

test("глухе розпізнавання називає себе, а не мовчить (#310)", async ({
  page,
}) => {
  await stubSpeech(page, { deaf: true });
  await openPantryAdd(page);

  const dialog = page.getByRole("dialog", { name: "Диктування" });
  await expect(dialog.getByRole("alert")).toContainText(
    /набери словами|на клавіатурі/,
    {
      timeout: 5_000,
    },
  );
  await expect(dialog).toHaveCount(1);
  await page.waitForFunction(() => (window as any).__starts >= 5);
  await page.evaluate(() => (window as any).__say("вода", true));
  await expect(dialog.locator(".rec-chip").first()).toContainText(/вода/i);
  await dialog.getByRole("button", { name: /Готово — додати/ }).click();
  await expect(dialog).toHaveCount(0);
});

test("розпізнавання, яке мовчить і НЕ гасне, теж називає себе (#310)", async ({
  page,
}) => {
  await stubSpeech(page);
  await page.addInitScript(() => {
    localStorage.setItem(
      "komora:speech-tweaks",
      JSON.stringify({ singleShot: false, finalOnly: false, noMeter: false }),
    );
  });
  await openPantryAdd(page);

  await expect(page.getByText("хвиля вимкнена")).toBeVisible({
    timeout: 8_000,
  });
  await expect(page.getByRole("alert")).toContainText(
    /набери словами|на клавіатурі/,
    {
      timeout: 8_000,
    },
  );
});

test("журнал каже НУЛЬ подій від двигуна, коли шлях мертвий (#310)", async ({
  page,
}) => {
  await stubSpeech(page);
  await page.addInitScript(() => localStorage.setItem("komora:speech-diag", "1"));
  await openPantryAdd(page);

  const dialog = page.getByRole("dialog", { name: "Диктування" });
  await expect(dialog).toContainText("подій від двигуна: 0");
});

test("журнал рахує події, щойно двигун подав голос (#310)", async ({
  page,
}) => {
  await stubSpeech(page);
  await page.addInitScript(() => localStorage.setItem("komora:speech-diag", "1"));
  await openPantryAdd(page);

  const dialog = page.getByRole("dialog", { name: "Диктування" });
  await expect(dialog).toContainText("подій від двигуна: 0");

  await page.evaluate(() => {
    const w = window as any;
    w.__tick("start");
    w.__tick("audiostart");
    w.__tick("speechstart");
  });

  await expect(dialog).toContainText("подій від двигуна: 3");
  await expect(dialog).toContainText("speechstart");
});

test("дослід «без хвилі» називає СВОЮ підставу, а не чужу (#310)", async ({
  page,
}) => {
  await stubSpeech(page);
  await page.addInitScript(() => {
    localStorage.setItem("komora:speech-diag", "1");
    localStorage.setItem(
      "komora:speech-tweaks",
      JSON.stringify({ noMeter: true }),
    );
  });
  await openPantryAdd(page);

  const dialog = page.getByRole("dialog", { name: "Диктування" });
  await expect(dialog).toContainText("хвиля не відкривалась");
  await expect(page.getByText("хвиля вимкнена")).toHaveCount(0);
});

test("порожні сесії не крутяться нескінченно (#310)", async ({ page }) => {
  await stubSpeech(page, { deaf: true });
  await openPantryAdd(page);
  await expect(page.getByRole("alert")).toContainText(
    /набери словами|на клавіатурі/,
    {
      timeout: 5_000,
    },
  );

  await page.waitForTimeout(600);
  const starts = await page.evaluate(
    () => (window as unknown as Record<string, number>).__starts,
  );
  expect(starts).toBeLessThanOrEqual(5);
});

test("«Зібрати на тиждень» веде в кошик з позиціями і сумою", async ({
  page,
}) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByText(/позиці/).first()).toBeVisible();
});

test("заміни: погоджене і те, що чекає рішення, — два різні блоки (#58)", async ({
  page,
}) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const ask = page.locator("button.decide");
  await expect(ask).toContainText("Чекає твого рішення");
  await expect(ask).toContainText("2 позиції просять твого слова");

  const report = page.locator("button.swaps:not(.decide)");
  await expect(report).toContainText("Заміни погоджено наперед");
  await expect(report).toContainText("2 позиції");

  await expect(
    page.getByText("потребує погодження заміни").first(),
  ).toBeVisible();

  const place = page.locator("button.place").first();
  const gap = await place.evaluate((el) => {
    const above = el.previousElementSibling!.getBoundingClientRect();
    return el.getBoundingClientRect().top - above.bottom;
  });
  expect(gap).toBeGreaterThanOrEqual(8);
});


/** Кошик того, у кого в замовленні стоїть «не збирайте те, що потребує уточнень». */
const BANNED = {
  feedback: {
    changes: "disapprovedChanges" as const,
    contacts: "call" as const,
  },
};

test("заборонені заміни: кошик каже, чия рука спрацює, а чия ні (#49)", async ({
  page,
}) => {
  await mockApi(page, { basket: BANNED });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const report = page.getByTestId("swaps-approved");
  await expect(report).toContainText("Заміни спрацюють до слота");
  await expect(report).toContainText("біля полиці збирач міняти не буде");
  await expect(report).not.toContainText("збирач не дзвонитиме");
});

test("дозволені заміни: обіцянка про збирача лишається на місці (#49)", async ({
  page,
}) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const report = page.getByTestId("swaps-approved");
  await expect(report).toContainText("Заміни погоджено наперед");
  await expect(report).toContainText("збирач не дзвонитиме");
});

test("екран замін називає галочку і НЕ пропонує її перемкнути (#49)", async ({
  page,
}) => {
  await mockApi(page, { basket: BANNED });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await page.getByTestId("swaps-approved").click();

  const setting = page.getByTestId("feedback");
  await expect(setting).toContainText("Біля полиці збирач міняти не буде");
  await expect(setting).toContainText("Доставка та оплата");
  await expect(setting).toContainText("Ми в чужі налаштування не пишемо");
  await expect(setting.locator("button")).toHaveCount(0);

  const hand = page.locator(".hand").first();
  await expect(hand).toContainText("до слота заміню я");
  await expect(hand).toContainText("біля полиці збирач міняти не буде");

  await expect(page.locator(".outro")).not.toContainText(
    "знімає дзвінок збирача",
  );
});

test("дзвінок увімкнений: екран замін каже це вголос (#49)", async ({
  page,
}) => {
  await openApp(page);
  await buildWeek(page);
  await page.getByTestId("swaps-approved").click();

  await expect(page.getByTestId("feedback")).toContainText("дзвінок буде");
});

test("крок замін стоїть між «Оформити» і звітом, і закінчує оформлення (#49)", async ({
  page,
}) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await page.getByRole("button", { name: "Оформити" }).click();
  await expect(
    page.getByRole("heading", { name: "Погодження замін" }),
  ).toBeVisible();
  const confirm = page.getByRole("button", { name: "Погоджую -- оформити" });
  await expect(confirm).toBeVisible();

  await page
    .getByRole("checkbox", { name: /Згоден, щоб збирач замінив/ })
    .check();
  await confirm.click();
  await expect(page.getByText(/рядків у кошику/)).toBeVisible();
});

test("крок замін не показується, коли вирішувати нічого (#49)", async ({
  page,
}) => {
  await mockApi(page, {
    basket: {
      lines: LINES.map((line) => ({
        ...line,
        atRisk: false,
        chain: [],
        mandate: null,
      })),
    },
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await page.getByRole("button", { name: "Оформити" }).click();
  await expect(page.getByText(/рядків у кошику/)).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Погодження замін" }),
  ).toBeHidden();
});

test("рядок називає дешевше того ж виду і міняється в один дотик (#230)", async ({
  page,
}) => {
  await mockApi(page, {
    basket: {
      lines: LINES.map((line, index) =>
        index === 0
          ? {
              ...line,
              cheaper: {
                externalProductId: "demo-milk-cheap",
                name: "Молоко «Премія» 2,5%",
                price: 39.9,
                saving: 22.6,
              },
            }
          : line,
      ),
    },
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const hint = page.locator("button.cheaper");
  await expect(hint).toHaveCount(1);
  await expect(hint).toContainText("Молоко «Премія» 2,5%");
  await expect(hint).toContainText("-45");

  await hint.click();

  await expect(page.getByText("Молоко «Премія» 2,5%").first()).toBeVisible();
  await expect(page.locator("button.cheaper")).toHaveCount(0);
});

test("«назад» у браузері веде всередині застосунку, а не з нього (#229)", async ({
  page,
}) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await page.getByRole("button", { name: "комора", exact: true }).click();
  await expect(page.getByRole("button", { name: "Оформити" })).toBeHidden();

  await page.goBack();

  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible();
});

test("недобір під ціль не бреше про покупки гостя (#231)", async ({ page }) => {
  await mockApi(page, {
    basket: {
      budget: 3000,
      postponed: [],
      fillNote: "12 того ж виду, що вже в кошику",
    },
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await expect(
    page.getByText(/решта пулу: 12 того ж виду, що вже в кошику/),
  ).toBeVisible();
  await expect(
    page.getByText(/більше з твоїх покупок не назбирується/),
  ).toBeHidden();
});

test("порожній ланцюжок називає свою причину (#228)", async ({ page }) => {
  await mockApi(page, {
    basket: {
      lines: LINES.map((line, index) =>
        line.chain.length > 0
          ? { ...line, atRisk: true }
          : {
              ...line,
              atRisk: true,
              chain: [],
              mandate: null,
              swapFork: null,
              consideredTotal: index % 2 === 0 ? 1 : 5,
            },
      ),
    },
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await page.getByRole("button", { name: "Оформити" }).click();
  await expect(
    page.getByRole("heading", { name: "Погодження замін" }),
  ).toBeVisible();

  await expect(page.getByText(/Замінити нема чим/).first()).toBeVisible();
  await expect(
    page.getByText(/Схожого того ж виду на цей слот не знайшлось/).first(),
  ).toBeVisible();
});

test("вилка цін вимагає ПІДПИСУ гостя, а не стоячого дозволу (#90)", async ({
  page,
}) => {
  const withFork = LINES.map((line) =>
    line.externalProductId === "demo-water"
      ? {
          ...line,
          atRisk: false,
          needsApproval: false,
          chain: [],
          mandateAhead: true,
          mandate:
            "якщо немає — рівноцінна заміна того самого виду у межах 26,09–31,89 грн, інакше не брати",
          swapFork: { low: 26.09, high: 31.89, per: "" },
        }
      : {
          ...line,
          atRisk: false,
          needsApproval: false,
          chain: [],
          swapFork: null,
        },
  );
  await mockApi(page, { basket: { lines: withFork } });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await page.getByRole("button", { name: "Оформити" }).click();
  await expect(
    page.getByRole("heading", { name: "Погодження замін" }),
  ).toBeVisible();

  const water = page
    .locator("article.card")
    .filter({ hasText: "Вода Карпатська Джерельна" });
  await expect(water.locator(".fork-range")).toHaveText(
    "Візьмуть від 26,09 до 31,89 ₴",
  );
});

test("рядок без мандата не обіцяє того, чого не буде в comment (#106)", async ({
  page,
}) => {
  await mockApi(page, {
    basket: {
      lines: LINES.map((line) =>
        line.chain.length > 0
          ? { ...line, atRisk: true }
          : { ...line, atRisk: true, chain: [], mandate: null, swapFork: null },
      ),
    },
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page.getByRole("button", { name: "Оформити" }).click();
  await expect(
    page.getByRole("heading", { name: "Погодження замін" }),
  ).toBeVisible();

  await expect(page.getByText(/заміну не погоджено/)).toHaveCount(0);
  await expect(page.getByText(/нічого:/).first()).toBeVisible();
  await expect(page.getByText(/замініть на схожі/).first()).toBeVisible();
});

test("вхід Б: чужий кошик доводиться до дверей із застосованою заміною", async ({
  page,
}) => {
  await openApp(page);
  await page.locator('[data-tour="from-cart"]').click();
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await expect(
    page.getByText(/поклав погоджену заміну №1/).first(),
  ).toBeVisible();
  await expect(page.getByText("Сир Джюгас 12 міс.")).toHaveCount(0);
});

test("ланцюжок складається з конкретних SKU і в тому порядку, який назвав гість (#59)", async ({
  page,
}) => {
  const sent: Record<string, unknown>[] = [];
  const swapped: Record<string, unknown>[] = [];
  await mockApi(page, {
    onBuild: (body) => sent.push(body),
    onSwaps: (body) => swapped.push(body),
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page.locator("button.swaps").first().click();
  await revealRest(page);

  const card = page
    .locator("article.card")
    .filter({ hasText: "Вода Карпатська Джерельна" });
  await card.getByRole("button", { name: "+ Додати заміну" }).click();

  const picker = page.getByRole("dialog", { name: "Чим заміняти" });
  await expect(picker.getByText("Поляна Квасова 0,5 л")).toBeVisible();
  await expect(picker.getByText(/0,5л · залишок 12/)).toBeVisible();

  await picker.getByRole("button", { name: /Поляна Квасова/ }).click();
  await picker.getByRole("button", { name: /Моршинська/ }).click();
  await picker.getByRole("button", { name: "Готово" }).click();

  const mandate = card.locator(".mandate-text");
  await expect(mandate).toContainText(
    "Поляна Квасова 0,5 л, потім Моршинська сильногазована 1,5 л",
  );

  await card.getByRole("button", { name: /Вище: Моршинська/ }).click();
  await expect(mandate).toContainText(
    "Моршинська сильногазована 1,5 л, потім Поляна Квасова 0,5 л",
  );

  await expect(page.getByRole("button", { name: "Перезібрати" })).toHaveCount(
    0,
  );
  await page.getByRole("button", { name: "До кошика" }).click();
  await expect(page.getByRole("button", { name: "Оформити" })).toBeEnabled();

  const last = swapped.at(-1) as {
    swaps: { externalProductId: string; chain: string[] }[];
  };
  const water = last.swaps.find(
    (swap) => swap.externalProductId === "demo-water",
  );
  expect(
    water?.chain,
    "ланцюжок гостя їде на сервер ЯК Є, разом з порядком",
  ).toEqual(["demo-morshynska", "demo-polyana"]);
  expect(sent, "погодження заміни не тягне повного прогону").toHaveLength(1);

  await page.locator("button.swaps").first().click();
  await revealRest(page);
  const after = page
    .locator("article.card")
    .filter({ hasText: "Вода Карпатська Джерельна" });
  await expect(after.locator(".mandate-text")).toContainText(
    "Моршинська сильногазована 1,5 л, потім Поляна Квасова 0,5 л",
  );
  await expect(after.getByText("додав ти").first()).toBeVisible();
});

test("погоджена заміна запам'ятовується лише з явного «так» (#224)", async ({
  page,
}) => {
  const swapped: Record<string, unknown>[] = [];
  await mockApi(page, { onSwaps: (body) => swapped.push(body) });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page.locator("button.swaps").first().click();
  await revealRest(page);

  const card = page
    .locator("article.card")
    .filter({ hasText: "Вода Карпатська Джерельна" });
  await card.getByRole("button", { name: "+ Додати заміну" }).click();
  const picker = page.getByRole("dialog", { name: "Чим заміняти" });
  await picker.getByRole("button", { name: /Поляна Квасова/ }).click();
  await picker.getByRole("button", { name: "Готово" }).click();

  await page.getByRole("button", { name: "До кошика" }).click();
  expect((swapped.at(-1) as { remember?: boolean }).remember).toBe(false);
  await page.locator("button.swaps").first().click();
  await revealRest(page);
  await expect(page.getByRole("heading", { name: "Діє надалі" })).toHaveCount(
    0,
  );

  await page.getByRole("checkbox", { name: /Запам'ятати ці заміни/ }).check();

  const withChain = await page
    .locator("article.card:has(ol.chain li .sub)")
    .count();
  const allCards = await page.locator("article.card").count();
  expect(withChain).toBeGreaterThan(0);
  expect(allCards).toBeGreaterThan(withChain);
  const note = page.locator(".remember-note");
  await expect(note).toContainText(`ці ${withChain}`);
  await expect(note).not.toContainText(`ці ${allCards}`);

  await page.getByRole("button", { name: "До кошика" }).click();
  expect((swapped.at(-1) as { remember?: boolean }).remember).toBe(true);

  await page.locator("button.swaps").first().click();
  await revealRest(page);
  await expect(page.getByRole("heading", { name: "Діє надалі" })).toBeVisible();
  const rows = page.locator(".saved li");
  const before = await rows.count();
  expect(before).toBeGreaterThan(0);

  await page
    .getByLabel(/Зняти погодження/)
    .first()
    .click();
  await expect(rows).toHaveCount(before - 1);
});

test("погоджена заміна не гасить «Оформити» і не тягне прогону (#77)", async ({
  page,
}) => {
  const sent: Record<string, unknown>[] = [];
  const swapped: Record<string, unknown>[] = [];
  await mockApi(page, {
    onBuild: (body) => sent.push(body),
    onSwaps: (body) => swapped.push(body),
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await page.locator("button.swaps").first().click();
  await revealRest(page);
  const card = page
    .locator("article.card")
    .filter({ hasText: "Вода Карпатська Джерельна" });
  await card.getByRole("button", { name: "+ Додати заміну" }).click();
  const picker = page.getByRole("dialog", { name: "Чим заміняти" });
  await picker.getByRole("button", { name: /Поляна Квасова/ }).click();
  await picker.getByRole("button", { name: "Готово" }).click();

  await expect(page.getByRole("button", { name: "Перезібрати" })).toHaveCount(
    0,
  );

  await page.getByRole("button", { name: "До кошика" }).click();
  const checkout = page.getByRole("button", { name: "Оформити" });
  await expect(checkout).toBeEnabled();
  await expect(page.getByText(/зібрано за іншими налаштуваннями/)).toHaveCount(
    0,
  );

  expect(swapped).toHaveLength(1);
  expect(
    sent,
    "повний прогін лишився один — той, що зібрав кошик",
  ).toHaveLength(1);
});

test("шлях до дверей синхронізує погоджене сам (#77)", async ({ page }) => {
  const swapped: Record<string, unknown>[] = [];
  await mockApi(page, { onSwaps: (body) => swapped.push(body) });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await page.getByRole("button", { name: "Оформити" }).click();
  const confirm = page.getByRole("button", { name: "Погоджую -- оформити" });
  await expect(confirm).toBeVisible();

  const card = page
    .locator("article.card")
    .filter({ hasText: "Вода Карпатська Джерельна" });
  await card.getByRole("button", { name: "+ Додати заміну" }).click();
  const picker = page.getByRole("dialog", { name: "Чим заміняти" });
  await picker.getByRole("button", { name: /Моршинська/ }).click();
  await picker.getByRole("button", { name: "Готово" }).click();

  await page
    .getByRole("checkbox", { name: /Згоден, щоб збирач замінив/ })
    .check();
  await confirm.click();
  await expect(page.locator(".paid")).toBeVisible();

  expect(swapped.length, "рішення доїхало до плану до запису").toBeGreaterThan(
    0,
  );
  const last = swapped.at(-1) as {
    swaps: { externalProductId: string; chain: string[] }[];
  };
  const water = last.swaps.find(
    (swap) => swap.externalProductId === "demo-water",
  );
  expect(water?.chain).toEqual(["demo-morshynska"]);
});

test("заміна з іншого виду називається вголос і в ланцюжок не йде (#80)", async ({
  page,
}) => {
  await mockApi(page);
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page.locator("button.swaps").first().click();
  await revealRest(page);

  const card = page
    .locator("article.card")
    .filter({ hasText: "Вода Карпатська Джерельна" });
  await card.getByRole("button", { name: "+ Додати заміну" }).click();
  const picker = page.getByRole("dialog", { name: "Чим заміняти" });

  await expect(
    picker.getByText("Вермішель Мівіна з куркою 59,2 г"),
  ).toHaveCount(0);

  await picker.getByLabel("Пошук заміни").fill("Мівіна");
  await picker.getByRole("button", { name: "Знайти" }).click();

  const foreign = picker.getByRole("button", { name: /Мівіна/ });
  await expect(foreign).toContainText("інший вид");

  await foreign.click();
  await expect(picker.getByText(/не з «Вода мінеральна»/)).toBeVisible();

  await picker.getByRole("button", { name: "Готово" }).click();
  await expect(card.locator(".chain")).not.toContainText("Мівіна");
  await expect(card.locator(".mandate")).not.toContainText("Мівіна");

  await card.getByRole("button", { name: "+ Додати заміну" }).click();
  await picker.getByLabel("Пошук заміни").fill("Моршинська");
  await picker.getByRole("button", { name: "Знайти" }).click();
  await picker.getByRole("button", { name: /Моршинська/ }).click();
  await picker.getByRole("button", { name: "Готово" }).click();
  await expect(card.locator(".mandate-text")).toContainText(
    "Моршинська сильногазована 1,5 л",
  );
});

test("вікно заміни: фото рядка і картка товару в «Сільпо» (#304)", async ({
  page,
}) => {
  await mockApi(page);
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page.locator("button.swaps").first().click();
  await revealRest(page);

  const card = page
    .locator("article.card")
    .filter({ hasText: "Вода Карпатська Джерельна" });
  await card.getByRole("button", { name: "+ Додати заміну" }).click();
  const picker = page.getByRole("dialog", { name: "Чим заміняти" });

  const borjomi = picker.locator("li").filter({ hasText: "Боржомі" });
  await expect(borjomi.locator("img")).toHaveAttribute(
    "src",
    /^data:image\/gif/,
  );
  const polyana = picker.locator("li").filter({ hasText: "Поляна Квасова" });
  await expect(polyana.locator("img")).toHaveCount(0);
  await expect(polyana.locator(".pick-thumb")).not.toHaveText("");

  const open = polyana.getByRole("link", {
    name: /Відкрити «Поляна Квасова/,
  });
  await expect(open).toHaveAttribute(
    "href",
    "https://silpo.ua/product/voda-polyana-kvasova-0-5-l-123456",
  );
  await expect(open).toHaveAttribute("target", "_blank");
  await expect(borjomi.getByRole("link")).toHaveCount(0);

  await picker.getByRole("button", { name: /Поляна Квасова/ }).click();
  await picker.getByRole("button", { name: "Готово" }).click();
  await expect(card.locator(".mandate-text")).toContainText("Поляна Квасова");
});

test("голос у полі заміни -- той самий диктофон, і він САМ шукає (#304)", async ({
  page,
}) => {
  await stubSpeech(page);
  await mockApi(page);
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page.locator("button.swaps").first().click();
  await revealRest(page);

  const card = page
    .locator("article.card")
    .filter({ hasText: "Вода Карпатська Джерельна" });
  await card.getByRole("button", { name: "+ Додати заміну" }).click();
  const picker = page.getByRole("dialog", { name: "Чим заміняти" });
  await expect(picker.getByText("Поляна Квасова 0,5 л")).toBeVisible();

  await picker.getByRole("button", { name: "надиктувати заміну" }).click();
  await expect(page.getByRole("dialog", { name: "Диктування" })).toBeVisible();
  await page.evaluate(() =>
    (window as unknown as { __say: (t: string, f: boolean) => void }).__say(
      "Моршинська",
      true,
    ),
  );
  await page.getByRole("button", { name: /Готово — додати/ }).click();

  await expect(picker.getByLabel("Пошук заміни")).toHaveValue("Моршинська");
  await expect(
    picker.getByText("Моршинська сильногазована 1,5 л"),
  ).toBeVisible();
  await expect(picker.getByText("Поляна Квасова 0,5 л")).toHaveCount(0);
});

test("авто-заміна називає вилку грошима рядка, а не відсотком (#90)", async ({
  page,
}) => {
  const sent: Record<string, unknown>[] = [];
  await mockApi(page, { onBuild: (body) => sent.push(body) });
  await skipIntro(page);
  await enter(page);
  await toStart(page);

  const toggle = page.getByRole("button", {
    name: "Дозволити заміну без питань",
  });
  await toggle.click();
  await expect(toggle).toContainText("візьмуть рівноцінне");
  await expect(toggle).toContainText("заміни побачиш перед оформленням");
  await expect(toggle).not.toContainText("%");

  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  expect(
    (sent.at(-1) as { autoSwap?: boolean }).autoSwap,
    "тумблер їде в запит",
  ).toBe(true);

  await page.locator("button.swaps").first().click();
  await revealRest(page);

  const card = page
    .locator("article.card")
    .filter({ hasText: "Йогурт Активіа натуральний" });
  await expect(card.locator(".fork-range")).toHaveText(
    "Візьмуть від 31,41 до 38,39 ₴",
  );
  await expect(card.locator(".fork-basis")).toContainText("зараз 34,90 ₴");
  await expect(card.locator(".fork-basis")).toContainText("не привезуть");
  await expect(card.locator(".mandate-text")).toContainText("31,41–38,39 грн");
});

test("ланцюжок і вилка -- дві руки, і кожна називає себе на своїй картці (#352)", async ({
  page,
}) => {
  await mockApi(page);
  await skipIntro(page);
  await enter(page);

  await page
    .getByRole("button", { name: "Дозволити заміну без питань" })
    .click();
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page.locator("button.swaps").first().click();
  await revealRest(page);

  const toggle = page.getByRole("button", {
    name: "Авто-заміна без погодження",
  });
  await expect(toggle).toContainText("де є список замін — везуть за ним");
  await expect(toggle).toContainText("Де ланцюжка немає");
  await expect(toggle).toContainText(
    `не дорожче ніж на ${AUTO_SWAP_CAP_UAH} ₴`,
  );

  const chained = page
    .locator("article.card")
    .filter({ hasText: "Корм Club 4 Paws кролик" });
  await expect(chained.locator(".chain-cap")).toHaveText(
    "Не буде — візьму по черзі:",
  );
  await expect(chained.locator(".sub-name").first()).toHaveText(
    "Club 4 Paws кролик 85 г",
  );
  await expect(chained.locator(".sub-source").first()).toContainText("21,90 ₴");
  await expect(chained.locator(".fork-range")).toHaveCount(0);
  await expect(chained).not.toContainText(
    `не дорожче ніж на ${AUTO_SWAP_CAP_UAH} ₴`,
  );

  const forked = page
    .locator("article.card")
    .filter({ hasText: "Йогурт Активіа натуральний" });
  await expect(forked.locator(".chain-cap")).toHaveText(
    "Ланцюжка немає — лишається межа в грошах:",
  );
  await expect(forked.locator(".fork-range")).toHaveText(
    "Візьмуть від 31,41 до 38,39 ₴",
  );
  await expect(forked.locator(".sub-name")).toHaveCount(0);

  const rule = page.getByRole("button", { name: "Авто-заміна без погодження" });
  await expect(rule).toContainText("рівноцінна заміна того самого виду");
  await expect(rule).toContainText(`не дорожче ніж на ${AUTO_SWAP_CAP_UAH} ₴`);
  await expect(rule).toContainText("не знайдеться — не привезуть");
  await expect(rule).toContainText("не привезуть");
  await expect(rule).not.toContainText("%");
});

test("рахунок замін у кошику називає руку, а не одне слово на дві (#352)", async ({
  page,
}) => {
  await mockApi(page);
  await skipIntro(page);
  await enter(page);

  await page
    .getByRole("button", { name: "Дозволити заміну без питань" })
    .click();
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const block = page.getByTestId("swaps-approved");
  await expect(block).not.toContainText("Заміни погоджено наперед");
  await expect(block.locator(".swaps-title")).toHaveText(
    "Заміни сплановано наперед",
  );
  await expect(block.locator(".swaps-note")).toHaveText(
    "3 позиції, з них 1 — межа в грошах · збирач не дзвонитиме",
  );

  await block.click();
  await expect(
    page
      .locator("article.card")
      .filter({ hasText: "Йогурт Активіа натуральний" })
      .locator(".chain-cap"),
  ).toHaveText("Ланцюжка немає — лишається межа в грошах:");
});

test("а коли ВСІ мандати -- вилки, «з них» називати нема від чого (#352)", async ({
  page,
}) => {
  const withFork = withAutoSwap(basket());
  await mockApi(page, {
    basket: {
      lines: withFork.lines.map((line) =>
        line.mandate !== null && line.swapFork === null
          ? { ...line, chain: [], mandate: null }
          : line,
      ),
    },
  });
  await skipIntro(page);
  await enter(page);

  await page
    .getByRole("button", { name: "Дозволити заміну без питань" })
    .click();
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const block = page.getByTestId("swaps-approved");
  await expect(block.locator(".swaps-title")).toHaveText(
    "Заміни сплановано наперед",
  );
  await expect(block.locator(".swaps-note")).toHaveText(
    "1 позиція — межа в грошах, товар не названий · збирач не дзвонитиме",
  );
});

test("підпис групи не зве вилку «заміною напоготові» (#352)", async ({
  page,
}) => {
  const calm = withAutoSwap(basket()).lines.map((line) => ({
    ...line,
    atRisk: false,
    needsApproval: false,
  }));
  await mockApi(page, { basket: { lines: calm } });
  await skipIntro(page);
  await page.goto("/");
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page.locator("button.swaps").first().click();
  await revealRest(page);

  const shown = calm.filter((line) => line.reason !== "at_home");
  await expect(page.getByTestId("rest")).toHaveText(
    `Кошик -- ${shown.length}, з них 2 із заміною напоготові і 1 з межею в грошах`,
  );

  await expect(
    page
      .locator("article.card")
      .filter({ hasText: "Йогурт Активіа натуральний" })
      .locator(".chain-cap"),
  ).toHaveText("Ланцюжка немає — лишається межа в грошах:");
});

test("відкладене стелею — це кнопка з трьома числами, а не рядок «не влізло» (#79)", async ({
  page,
}) => {
  await mockApi(page, { basket: { postponed: POSTPONED, budget: 3000 } });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const week = page.locator('[data-tour="refill"]');
  const act = week.getByRole("button", { name: /Закрити решту тижня/ });
  await expect(act).toContainText("ще 3 позиції");
  await expect(week).toContainText("~565");
  await expect(week).toContainText(
    "до нижньої межі 2 700 ₴ (ціль 3 000 ₴ ±10%)",
  );
  const left = new Intl.NumberFormat("uk-UA", { maximumFractionDigits: 0 })
    .format(3000 * 0.9 - TOTAL)
    .replace(/ /g, " ");
  await expect(week).toContainText(`бракує ${left} ₴ до нижньої межі 2 700 ₴`);
  await expect(week).toContainText("без 1 виду — ціни в чеках немає");

  const held = page.locator('[data-tour="postponed"]');
  await expect(held).toContainText("йогурт");
  await expect(held).not.toContainText("Кава Lavazza");
});

test("потреба, під яку на полиці нічого немає, лишається на екрані (#138)", async ({
  page,
}) => {
  await mockApi(page, { basket: { postponed: POSTPONED, budget: 3000 } });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const held = page.locator('[data-tour="postponed"]');
  await expect(held).toContainText("Морозиво Хрещатик пломбір");
  await expect(held).toContainText("на цей слот");
  const act = page
    .locator('[data-tour="refill"]')
    .getByRole("button", { name: /Закрити решту тижня/ });
  await expect(act).toContainText("ще 3 позиції");
});

test("межа без відкладеного все одно називає себе числами (#134)", async ({
  page,
}) => {
  await mockApi(page, { basket: { budget: 3000 } });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const week = page.locator('[data-tour="refill"]');
  await expect(
    week.getByRole("button", { name: /Закрити решту тижня/ }),
  ).toHaveCount(0);
  await expect(week).toContainText("таких видів 9 з 10");
  await expect(week).toContainText("напиши, що треба");
  const left = new Intl.NumberFormat("uk-UA", { maximumFractionDigits: 0 })
    .format(3000 * 0.9 - TOTAL)
    .replace(/ /g, " ");
  await expect(week).toContainText(
    `бракує ${left} ₴ до нижньої межі 2 700 ₴ (ціль 3 000 ₴ ±10%)`,
  );
});

test("на акаунті без пулу чип не обіцяє добір під суму (#206)", async ({
  page,
}) => {
  await mockApi(page, { pantry: "delivery-only" });
  await skipIntro(page);
  await enter(page);

  await expect(
    page.getByRole("button", {
      name: "нема з чого добирати: бачу 76 замовлень",
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /зібрати приблизно на/ }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "на тиждень", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Зібрати на тиждень", exact: true }),
  ).toBeVisible();
});

test("малий пул чип називає числом, а не мовчить до збірки (#206)", async ({
  page,
}) => {
  await mockApi(page, { pantry: "small-pool" });
  await skipIntro(page);
  await enter(page);

  await expect(
    page.getByRole("button", {
      name: "зібрати приблизно на 1 500 ₴ · з твоїх покупок ~600 ₴",
    }),
  ).toBeVisible();
});

test("кошик показує прогрес до цілі, а не голу суму (#206)", async ({
  page,
}) => {
  await mockApi(page, { basket: { budget: 2000 } });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const shown = new Intl.NumberFormat("uk-UA", { maximumFractionDigits: 0 })
    .format(Math.round(TOTAL))
    .replace(/ /g, " ");
  await expect(page.locator(".dock-sum .num")).toContainText(
    `${shown} ₴ з 2 000 ₴`,
  );
  await expect(page.locator(".dock-why")).toContainText("таких видів 9 з 10");
  await expect(page.locator(".dock-why")).not.toContainText("напиши, що треба");
});

test("порада «напиши, що треба» веде в поле, а не лишається реченням (#206)", async ({
  page,
}) => {
  await mockApi(page, { basket: { budget: 3000 } });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const week = page.locator('[data-tour="refill"]');
  await week.getByRole("button", { name: "напиши, що треба" }).click();

  await expect(week.locator(".week-add input")).toBeFocused();
});

test("після добору межа не замовкає знову (#134)", async ({ page }) => {
  await mockApi(page, { basket: { postponed: POSTPONED, budget: 3000 } });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const week = page.locator('[data-tour="refill"]');
  await week.getByRole("button", { name: /Закрити решту тижня/ }).click();
  await expect(
    week.getByRole("button", { name: /Закрити решту тижня/ }),
  ).toHaveCount(0);
  await expect(week).toContainText("таких видів 9 з 10");
  await expect(week).toContainText(
    "до нижньої межі 2 700 ₴ (ціль 3 000 ₴ ±10%)",
  );
});

test("вхід Б пояснює недобір СВОЇМИ словами, а не циклами (#134)", async ({
  page,
}) => {
  await mockApi(page, { basket: { budget: 3000 } });
  await skipIntro(page);
  await enter(page);
  await toStart(page);
  await page.locator('[data-tour="from-cart"]').click();
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const week = page.locator('[data-tour="refill"]');
  await expect(week).toContainText("цей кошик наповнив хтось інший");
  await expect(week).not.toContainText("ти береш рівно");
  await expect(week).toContainText(
    "до нижньої межі 2 700 ₴ (ціль 3 000 ₴ ±10%)",
  );
});

test("добір докидає відкладене в той самий кошик, а не перезбирає його (#79, #13)", async ({
  page,
}) => {
  await mockApi(page, { basket: { postponed: POSTPONED, budget: 3000 } });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const before = await page.locator("ul.list > li").count();
  await page
    .locator('[data-tour="refill"]')
    .getByRole("button", { name: /Закрити решту тижня/ })
    .click();

  await expect(page.locator("ul.list > li")).toHaveCount(before + 3);
  await expect(
    page.getByText("Кава Lavazza Crema e Gusto 250 г"),
  ).toBeVisible();
  await expect(page.getByText("Молоко Селянське 2,5%").first()).toBeVisible();

  await expect(
    page
      .locator('[data-tour="refill"]')
      .getByRole("button", { name: /Закрити решту тижня/ }),
  ).toHaveCount(0);
});

test("«додати ще» в кошику докидає назване словами (#13)", async ({ page }) => {
  await mockApi(page, { basket: { postponed: POSTPONED, budget: 3000 } });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const before = await page.locator("ul.list > li").count();
  const week = page.locator('[data-tour="refill"]');
  await week.getByPlaceholder("Додати ще").fill("печиво вівсяне");
  await week.getByRole("button", { name: "Додати", exact: true }).click();

  await expect(page.locator("ul.list > li")).toHaveCount(before + 1);
  await expect(page.getByText("Печиво вівсяне Богуславна 250 г")).toBeVisible();
});

test("банер порога не називає вигідне невигідним (живий тест 22.08)", async ({
  page,
}) => {
  await mockApi(page, {
    basket: { topUp: { threshold: TOTAL + 19.6, saving: 30, items: [] } },
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const eco = page.locator(".eco");
  await expect(eco).toContainText("це вигідно");
  await expect(eco).toContainText("нема чого запропонувати");
  await expect(eco).not.toContainText("невигідно");
});

test("докидати справді невигідно — і тоді так і сказано", async ({ page }) => {
  await mockApi(page, {
    basket: {
      topUp: { threshold: TOTAL + 120, saving: 30, items: TOPUP_ITEMS },
    },
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const eco = page.locator(".eco");
  await expect(eco).toContainText("докидати невигідно");
  await expect(eco.getByRole("button")).toHaveCount(0);
});

test("добір і докидання до порога доставки — дві різні дії (#79)", async ({
  page,
}) => {
  await mockApi(page, {
    basket: {
      postponed: POSTPONED,
      budget: 3000,
      topUp: { threshold: TOTAL + 20, saving: 58, items: TOPUP_ITEMS },
    },
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const eco = page.locator(".eco");
  await expect(eco).toContainText("доставка");
  await expect(eco.getByRole("button")).toContainText("до порога");

  const week = page.locator('[data-tour="refill"]');
  await expect(week.getByRole("button").first()).toContainText("решту тижня");
  await expect(week).not.toContainText("доставка");
});

test("добір з 409 лишає кошик на екрані: вкладки і трейс на місці (#302)", async ({
  page,
}) => {
  await mockApi(page, {
    basket: { postponed: POSTPONED, budget: 3000 },
    refillError:
      "на цій полиці зараз немає: «Пюре Mark&Mart запечене яблучк-морквочка без цукру». Спробуй інший слот або назви інакше",
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const week = page.locator('[data-tour="refill"]');
  await week.getByRole("button", { name: /Закрити решту тижня/ }).click();

  await expect(page.locator(".error")).toContainText(
    "на цій полиці зараз немає",
  );
  await expect(page.locator(".error")).toContainText(
    "інший слот або назви інакше",
  );

  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "комора", exact: true }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Що зробив агент" }).click();
  await expect(
    page.getByRole("heading", { name: "Що зробив агент" }),
  ).toBeVisible();
});

test("два добори поспіль не вбивають трейс дублем ключа (#302)", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (exc) => errors.push(String(exc)));

  await mockApi(page, { basket: { postponed: POSTPONED, budget: 3000 } });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const week = page.locator('[data-tour="refill"]');
  await week.locator(".week-add input").fill("печиво");
  await week.getByRole("button", { name: "Додати", exact: true }).click();
  await expect(page.getByText("Печиво вівсяне Богуславна 250 г")).toBeVisible({
    timeout: 20_000,
  });

  await week.getByRole("button", { name: /Закрити решту тижня/ }).click();
  await expect(page.getByText("Кава Lavazza Crema e Gusto 250 г")).toBeVisible({
    timeout: 20_000,
  });

  await expect(
    page.getByRole("button", { name: "комора", exact: true }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Що зробив агент" }).click();
  await expect(
    page.getByRole("heading", { name: "Що зробив агент" }),
  ).toBeVisible();
  await expect(page.locator(".cards .card").first()).toBeVisible();
  expect(errors).toEqual([]);
});

test("«Очистити показ» ховає картки, а роботу агента лишає (E11-а)", async ({
  page,
}) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  const linesBefore = await page.locator("li.row").count();

  await page.getByRole("button", { name: "Що зробив агент" }).click();
  await expect(page.getByText(/Агент ухвалив/)).toBeVisible();

  await page.getByRole("button", { name: "Очистити показ" }).click();
  await expect(page.getByText(/Решту сховано з показу/)).toBeVisible();

  const back = page.getByRole("button", { name: /Показати сховане/ });
  await expect(back).toBeVisible();
  await back.click();
  await expect(page.getByText(/Агент ухвалив/)).toBeVisible();

  await page.getByRole("button", { name: "До кошика" }).click();
  await expect(page.locator("li.row")).toHaveCount(linesBefore);
});

test("під дебагом трейс каже, що він під дебагом (E11)", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("komora:debug", "1"));
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page.getByRole("button", { name: "Що зробив агент" }).click();

  await expect(page.getByTestId("trace-debug")).toBeVisible();
});


type Spot =
  | "start"
  | "cart"
  | "connect"
  | "quality"
  | "stack"
  | "ideas"
  | "pantry"
  | "bar"
  | "trace"
  | "swaps";

/** Як екран упізнати. Не за класом: клас — це оформлення. */
const MARK: Record<Spot, string | RegExp> = {
  start: /^Зібрати /,
  cart: "Оформити",
  connect: "Акаунт «Сільпо»",
  quality: "Якість",
  stack: "Технології",
  ideas: "Ідеї",
  pantry: /(з покупок|веду сам)/,
  bar: "Бар",
  trace: "Що зробив агент",
  swaps: "Погодження замін",
};

async function at(page: Page, spot: Spot): Promise<void> {
  await expect(
    page.getByText(MARK[spot], { exact: false }).first(),
  ).toBeVisible();
}

/** Тим самим шляхом, яким туди ходить гість. */
async function goTo(page: Page, spot: Spot): Promise<void> {
  if (spot === "connect") {
    await page.locator('[data-tour="link"]').click();
  } else if (spot === "quality" || spot === "stack" || spot === "ideas") {
    await page.getByRole("button", { name: "Меню" }).click();
    const label = { quality: "якість", stack: "технології", ideas: "ідеї" }[
      spot
    ];
    await page
      .getByRole("button", { name: label, exact: false })
      .first()
      .click();
  } else if (spot === "trace") {
    await page.getByRole("button", { name: "Що зробив агент" }).click();
  } else if (spot === "swaps") {
    await page.locator("button.swaps").first().click();
    await revealRest(page);
  } else if (spot === "pantry") {
    await page
      .getByRole("button", { name: /Закінчується|комора/ })
      .first()
      .click();
  } else if (spot === "bar") {
    const link = page.getByRole("button", {
      name: /Напої до приводу|що з напоїв удома|^бар$/,
    });
    if ((await link.count()) === 0) {
      await page.getByRole("button", { name: "подія", exact: true }).click();
    }
    await link.first().click();
  }
  await at(page, spot);
}

async function goBack(page: Page): Promise<void> {
  const dock = page.locator("button", {
    hasText: /^(До покупок|До кошика|До комори|До бару|До акаунта)$/,
  });
  if (await dock.count()) await dock.first().click();
  else await page.locator("button.back").first().click();
}

async function buildBasket(page: Page): Promise<void> {
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
}

test("назад завжди веде туди, звідки прийшли — матрицею, а не по одному шляху (#92)", async ({
  page,
}) => {
  await mockApi(page);
  await skipIntro(page);
  await enter(page);

  for (const spot of [
    "connect",
    "quality",
    "stack",
    "ideas",
    "pantry",
    "bar",
  ] as Spot[]) {
    await test.step(`старт → ${spot} → назад`, async () => {
      await goTo(page, spot);
      await goBack(page);
      await at(page, "start");
    });
  }

  await buildBasket(page);

  for (const spot of [
    "connect",
    "quality",
    "stack",
    "ideas",
    "pantry",
    "bar",
    "trace",
    "swaps",
  ] as Spot[]) {
    await test.step(`кошик → ${spot} → назад`, async () => {
      await goTo(page, spot);
      await goBack(page);
      await at(page, "cart");
    });
  }
});

test("назад іде слідом на два кроки: акаунт → якість → назад → назад (#92)", async ({
  page,
}) => {
  await mockApi(page);
  await skipIntro(page);
  await enter(page);
  await buildBasket(page);

  await goTo(page, "connect");
  await goTo(page, "quality");
  await goBack(page);
  await at(page, "connect");
  await goBack(page);
  await at(page, "cart");
});

test("підказки не міняють екран, з якого їх запустили (#92)", async ({
  page,
}) => {
  await mockApi(page);
  await skipIntro(page);
  await enter(page);
  await buildBasket(page);

  await page.getByRole("button", { name: "Меню" }).click();
  await page.getByRole("button", { name: "підказки", exact: false }).click();

  await at(page, "cart");

  const tour = page.getByRole("dialog", { name: "Підказки" });
  await expect(tour).toBeVisible();
  const titles: string[] = [];
  for (let i = 0; i < 12; i += 1) {
    titles.push(await tour.locator("h2").innerText());
    const next = tour.locator("button.next");
    const last = (await next.innerText()) === "Зрозуміло";
    await next.click();
    if (last) break;
  }

  expect(titles).toContain("Кожен рядок пояснює себе");
  expect(titles).not.toContain("Просто перелічи, що треба");
  await at(page, "cart");
});

test("комора зі старту не лишає гостя у вкладках кошика (#92)", async ({
  page,
}) => {
  await mockApi(page);
  await skipIntro(page);
  await enter(page);
  await toStart(page);
  await buildBasket(page);

  await goTo(page, "pantry");
  await expect(
    page.getByRole("button", { name: "кошик", exact: true }),
  ).toBeVisible();
  await goBack(page);

  await page.getByRole("button", { name: "На початок" }).first().click();
  await at(page, "start");
  await goTo(page, "pantry");
  await expect(
    page.getByRole("button", { name: "кошик", exact: true }),
  ).toHaveCount(0);
  await goBack(page);
  await at(page, "start");
});

test("трейс не показує 0 мс там, де був живий виклик (#60)", async ({
  page,
}) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page.getByRole("button", { name: "Що зробив агент" }).click();

  const cycles = page.locator("article").filter({ hasText: "core.cycles" });
  await expect(cycles.getByText("не міряли")).toBeVisible();
  await expect(cycles.getByText(/<1\s*мс/)).toHaveCount(0);

  const search = page
    .locator("article")
    .filter({ hasText: "find_products_batch" })
    .first();
  await expect(search.getByText(/400\s*мс/)).toBeVisible();
  await expect(search.getByText(/<1\s*мс/)).toHaveCount(0);
});

test("«<1 мс» лишається ЗАМІРЯНОМУ нулю, а незаміряне каже це словами (#279)", async ({
  page,
}) => {
  const sample = basket().trace.find((step) => step.decision)!;
  const trace = [
    {
      ...sample,
      id: "step-measured",
      seq: sample.seq,
      tool: "core.fast",
      durationMs: 0,
      decision: "таймер стояв і показав нуль",
    },
    {
      ...sample,
      id: "step-unmeasured",
      seq: sample.seq + 1,
      tool: "core.unclocked",
      durationMs: null,
      decision: "таймера над цим кроком не було",
    },
  ];
  await openApp(page, { basket: { trace } });
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page.getByRole("button", { name: "Що зробив агент" }).click();

  const measured = page.locator("article").filter({ hasText: "core.fast" });
  await expect(measured.getByText(/<1\s*мс/)).toBeVisible();

  const unmeasured = page
    .locator("article")
    .filter({ hasText: "core.unclocked" });
  await expect(unmeasured.getByText("не міряли")).toBeVisible();
  await expect(unmeasured.getByText(/<1\s*мс/)).toHaveCount(0);
});

test("трейс каже, ЧОМУ саме ця позиція, і з чого агент обирав (#43)", async ({
  page,
}) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page.getByRole("button", { name: "Що зробив агент" }).click();

  const milk = page.locator('[data-pick="demo-milk"]');
  await expect(milk.getByText("обрано з 4")).toBeVisible();
  await expect(milk.getByText("Молоко Яготинське 2,6%")).toBeVisible();
  await expect(milk.getByText("75,99 ₴")).toBeVisible();
  await expect(milk.getByText(/Галичина.*/)).toBeVisible();
  await expect(milk.getByText("немає", { exact: false })).toBeVisible();

  const water = page.locator('[data-pick="demo-water"]');
  await expect(water.getByText("вибору не було")).toBeVisible();
});

test("дотик по рядку кошика веде в ЙОГО картку, а не «кудись у трейс» (#72)", async ({
  page,
}) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await tapName(page, "Олія оливкова Monini 0,5 л");

  const oil = page.locator('[data-pick="demo-oil"]');
  await expect(oil).toBeInViewport();
  await expect(oil).toHaveClass(/focused/);
  await expect(page.locator('[data-pick="demo-milk"]')).not.toBeInViewport();
});

test("«Що зробив агент» не виділяє нікого (#72)", async ({ page }) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await tapName(page, "Банани");
  await expect(page.locator('[data-pick="demo-bananas"]')).toHaveClass(
    /focused/,
  );

  await page.getByRole("button", { name: "До кошика" }).click();
  await page.getByRole("button", { name: "Що зробив агент" }).click();
  await expect(page.locator("article.focused")).toHaveCount(0);
});

test("рядок без обґрунтування не вдає посилання (#72)", async ({ page }) => {
  await mockApi(page, {
    basket: {
      lines: LINES.map((line) =>
        line.externalProductId === "demo-water"
          ? { ...line, considered: [], consideredTotal: 0 }
          : line,
      ),
    },
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const water = "Вода Карпатська Джерельна";
  await expect(
    page.getByRole("button", { name: water, exact: true }),
  ).toHaveCount(0);
  await expect(page.getByText(water).first()).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Банани", exact: true }),
  ).toBeVisible();
});

test("докинутий рядок теж має свою картку в трейсі (#72)", async ({ page }) => {
  await mockApi(page, {
    basket: {
      topUp: { threshold: TOTAL + 20, saving: 58, items: TOPUP_ITEMS },
    },
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page.getByRole("button", { name: "Докинути" }).click();

  await tapName(page, "Гречка Сквирянка 800 г");
  const buckwheat = page.locator('[data-pick="demo-buckwheat"]');
  await expect(buckwheat).toBeInViewport();
  await expect(buckwheat).toHaveClass(/focused/);
});

test("невидима зона чипса не краде дотик по назві (#72)", async ({ page }) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const button = page.getByRole("button", {
    name: "Олія оливкова Monini 0,5 л",
    exact: true,
  });
  await button.evaluate((node) => node.scrollIntoView({ block: "center" }));
  const hit = await button.evaluate((node) => {
    const box = node.getBoundingClientRect();
    const at = document.elementFromPoint(
      box.x + box.width / 2,
      box.y + box.height / 2,
    );
    return at === node
      ? "назва"
      : String((at as HTMLElement | null)?.className);
  });
  expect(hit).toBe("назва");
});

test("кошик каже, ЧОМУ саме цей слот, а не лише коли (#88)", async ({
  page,
}) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const why = page.getByTestId("slot-why");
  await expect(why).toHaveText(
    "чому цей слот: перший вільний із 7 у 20 найближчих",
  );

  await page.getByRole("button", { name: "Що зробив агент" }).click();
  await expect(
    page.getByRole("heading", { name: "перший вільний із 7 у 20 найближчих" }),
  ).toBeVisible();
});

test("чужому слоту підстава не вигадується (#88)", async ({ page }) => {
  await mockApi(page, {
    basket: {
      slot: {
        start: "2026-08-14T11:00:00+03:00",
        end: "2026-08-14T13:00:00+03:00",
        note: null,
      },
    },
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await expect(page.getByTestId("slot-why")).toHaveCount(0);
  await expect(page.getByText(/11:00.13:00/).first()).toBeVisible();
});

test("«Оформити» пише кошик і віддає посилання на підтвердження", async ({
  page,
}) => {
  await openApp(page);
  await buildWeek(page);
  const button = page.getByRole("button", { name: "Оформити" });
  await expect(button).toBeVisible({ timeout: 20_000 });
  await expect(button).toBeEnabled();

  await checkout(page);
  await expect(page.getByText(/рядків у кошику/)).toBeVisible();
  await expect(
    page.getByRole("link", { name: /Підтвердити|Оформити/ }).first(),
  ).toBeVisible();
});

test("«Оформити» не гасне на правленій кількості (02.09)", async ({ page }) => {
  await openApp(page);
  await buildWeek(page);
  const checkout = page.getByRole("button", { name: "Оформити" });
  await expect(checkout).toBeVisible({ timeout: 20_000 });

  await page
    .getByRole("button", { name: /^Більше: / })
    .first()
    .click();
  await expect(checkout).toBeEnabled();
  await expect(checkout).not.toHaveAttribute("title", /перезбери/);
});

test("прибраний рядок глушиться, а не зникає", async ({ page }) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const first = page.getByRole("button", { name: /^Прибрати / }).first();
  const name = (await first.getAttribute("aria-label"))!.replace(
    "Прибрати ",
    "",
  );
  await first.click();

  await expect(page.getByText(name, { exact: true })).toBeVisible();
  await expect(
    page.getByText("ти сказав, що ще є вдома — не купую").first(),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: `Додати ${name}` }),
  ).toBeVisible();
});

test("ваговий рядок каже ціну за кілограм і рухається кроком картки (#78)", async ({
  page,
}) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const row = page.locator("li.row").filter({ hasText: "Банани" });
  await expect(row.locator(".qty-unit")).toHaveText("кг");
  await expect(row.locator(".price")).toHaveText(/58,68/);
  await expect(row.locator(".per")).toHaveText(/48,90.*\/кг/);

  await row.getByRole("button", { name: /^Більше/ }).click();
  await expect(row.locator(".qty-input")).toHaveValue("1,6");

  const pieces = page.locator("li.row").filter({ hasText: "Молоко Селянське" });
  await expect(pieces.locator(".per")).toHaveCount(0);
});

test.describe("слот показується київським часом, а не часом пристрою", () => {
  test.use({ timezoneId: "America/New_York" });

  test("слот 11:00–13:00 не зсувається під пристрій", async ({ page }) => {
    await openApp(page);
    await buildWeek(page);
    await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.getByText(/11:00–13:00/).first()).toBeVisible();
  });
});

test("бар зі старту повертає на старт, а не в кошик (#32)", async ({
  page,
}) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await page.getByRole("button", { name: "На початок" }).click();
  await expect(page.getByRole("button", { name: /^Зібрати / })).toBeVisible();

  await page.getByRole("button", { name: "подія", exact: true }).click();
  await page.getByRole("button", { name: /Напої до приводу/ }).click();
  await expect(page.getByRole("heading", { name: "Бар" })).toBeVisible();

  const dock = page.getByRole("button", { name: "На початок" }).last();
  await expect(dock).toBeVisible();
  await dock.click();
  await expect(page.getByRole("button", { name: /^Зібрати / })).toBeVisible();
});

test("бар відкривається з головної без жодного приводу (#246)", async ({
  page,
}) => {
  await openApp(page);

  await page.getByRole("button", { name: "що з напоїв удома" }).click();

  await expect(page.getByRole("heading", { name: "Бар" })).toBeVisible();
  await page.getByRole("button", { name: "На початок" }).last().click();
  await expect(page.getByRole("button", { name: /^Зібрати / })).toBeVisible();
});

test("під приводом дверей у бар рівно одні, а не двоє (#246)", async ({
  page,
}) => {
  await openApp(page);
  await expect(
    page.getByRole("button", { name: "що з напоїв удома" }),
  ).toBeVisible();

  await page.getByRole("button", { name: "подія", exact: true }).click();

  await expect(
    page.getByRole("button", { name: "що з напоїв удома" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: /Напої до приводу/ }),
  ).toBeVisible();
});

test("зібраний кошик не забирає екран у гостя, а називає себе (#147)", async ({
  page,
}) => {
  await openApp(page, { build: "slow" });
  await buildWeek(page);

  await page.getByRole("button", { name: "На початок" }).first().click();
  await expect(page.getByRole("button", { name: /^Зібрати / })).toBeVisible();

  const ready = page.getByRole("button", { name: "кошик готовий ›" });
  await expect(ready).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("button", { name: /^Зібрати / })).toBeVisible();

  await ready.click();
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible();
  await expect(ready).toHaveCount(0);
});

test("гість, який дочекався збірки, потрапляє в кошик без зайвого дотику (#147)", async ({
  page,
}) => {
  await openApp(page, { build: "slow" });
  await buildWeek(page);

  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await expect(
    page.getByRole("button", { name: "кошик готовий ›" }),
  ).toHaveCount(0);
});

test("бар із кошика повертає в кошик (#32)", async ({ page }) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await page
    .getByRole("link", { name: "бар" })
    .or(page.getByRole("button", { name: "бар" }))
    .first()
    .click();
  const dock = page.getByRole("button", { name: "До кошика" });
  await expect(dock).toBeVisible();
  await dock.click();
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible();
});

test("порожній бар називає причину, і причин три (#5)", async ({ page }) => {
  await test.step("покупок не видно взагалі", async () => {
    await mockApi(page, { bar: BAR_NO_RECEIPTS });
    await skipIntro(page);
    await enter(page);
    await page.getByRole("button", { name: "подія", exact: true }).click();
    await page.getByRole("button", { name: /Напої до приводу/ }).click();
    await expect(page.getByText(/Поки їх не видно/)).toBeVisible();
  });
});

test("бар без напоїв не звинувачує модель, а бар без моделі не звинувачує чеки (#5)", async ({
  page,
}) => {
  await test.step("чеки є, напоїв серед звичного немає", async () => {
    await mockApi(page, { bar: BAR_NO_DRINKS });
    await skipIntro(page);
    await enter(page);
    await page.getByRole("button", { name: "подія", exact: true }).click();
    await page.getByRole("button", { name: /Напої до приводу/ }).click();
    await expect(
      page.getByText(/Серед звичного напоїв поки немає/),
    ).toBeVisible();
    await expect(page.getByText(/з 3-ї покупки/)).toBeVisible();
  });
});

test("рядок списку переживає перезавантаження сторінки (#110)", async ({
  page,
}) => {
  await openApp(page);

  await page.getByPlaceholder(/треба щось конкретне/).fill("батарейки");
  await page.getByRole("button", { name: "+ у список на потім" }).click();
  await expect(page.getByLabel("Прибрати зі списку: батарейки")).toBeVisible();

  await reenter(page);

  await expect(page.getByLabel("Прибрати зі списку: батарейки")).toBeVisible();
  await expect(page.getByPlaceholder(/треба щось конкретне/)).toHaveValue("");
});

test("рядок списку згорає на оформленні і каже про це (#110)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByPlaceholder(/треба щось конкретне/).fill("батарейки");
  await page.getByRole("button", { name: "+ у список на потім" }).click();
  await expect(page.getByLabel("Прибрати зі списку: батарейки")).toBeVisible();

  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await checkout(page);

  await expect(page.getByText(/Зі списку на покупку згоріло/)).toBeVisible();
  await expect(page.getByText("батарейки").last()).toBeVisible();
});

test("рядок списку лягає в комору, а разова покупка -- ні (#238)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByPlaceholder(/треба щось конкретне/).fill("батарейки");
  await page.getByRole("button", { name: "+ у список на потім" }).click();
  await page.getByPlaceholder(/треба щось конкретне/).fill("вугілля");
  await page.getByRole("button", { name: "+ у список на потім" }).click();

  await page.getByLabel("Не класти в комору після покупки: вугілля").click();
  await expect(
    page.getByLabel("Класти в комору після покупки: вугілля"),
  ).toBeVisible();

  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await checkout(page);

  await expect(page.getByText(/батарейки.*у комору/)).toBeVisible();
  await expect(page.getByText(/вугілля.*разова покупка/)).toBeVisible();
});

test("рядок списку можна зняти руками -- передумав (#110)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByPlaceholder(/треба щось конкретне/).fill("батарейки");
  await page.getByRole("button", { name: "+ у список на потім" }).click();

  await page.getByLabel("Прибрати зі списку: батарейки").click();

  await expect(page.getByLabel("Прибрати зі списку: батарейки")).toBeHidden();
});

async function openBar(page: Page): Promise<void> {
  await skipIntro(page);
  await enter(page);
  await page.getByRole("button", { name: "подія", exact: true }).click();
  await page.getByRole("button", { name: /Напої до приводу/ }).click();
  await expect(page.getByRole("heading", { name: "Бар" })).toBeVisible();
}

test("дописаний у бар вид з'являється рядком і без вигаданої вилки (#146)", async ({
  page,
}) => {
  await mockApi(page);
  await openBar(page);

  await page.getByLabel("дописати вид у бар").fill("віскі бленд");
  await page.getByRole("button", { name: "+ Додати" }).click();

  const row = page.locator("li.row", { hasText: "віскі бленд" });
  await expect(row).toBeVisible();
  await expect(row.getByText(/покупок цього виду ще не видно/)).toBeVisible();
  await expect(row.getByText(/ти дописав це сам/)).toBeVisible();
});

test("полицю бару ставить гість, а не тільки модель (#261)", async ({
  page,
}) => {
  await mockApi(page);
  await openBar(page);

  const strong = page.locator("section", {
    has: page.getByRole("heading", { name: "міцний", exact: true }),
  });
  const light = page.locator("section", {
    has: page.getByRole("heading", { name: "слабкий", exact: true }),
  });
  await expect(strong.locator("li.row", { hasText: "Горілка" })).toBeVisible();

  await page
    .getByRole("button", { name: "Змінити полицю для «Горілка»" })
    .click();
  await page.getByRole("button", { name: "слабкий", exact: true }).click();

  const moved = light.locator("li.row", { hasText: "Горілка" });
  await expect(moved).toBeVisible();
  await expect(moved.getByText("полицю обрав ти")).toBeVisible();
  await expect(strong.locator("li.row", { hasText: "Горілка" })).toBeHidden();

  await page
    .getByRole("button", { name: "Змінити полицю для «Горілка»" })
    .click();
  await page.getByRole("button", { name: "здогад агента" }).click();

  await expect(strong.locator("li.row", { hasText: "Горілка" })).toBeVisible();
  await expect(light.locator("li.row", { hasText: "Горілка" })).toBeHidden();
});

test("стерти список бару не чіпає рядків з покупок (#146)", async ({
  page,
}) => {
  await mockApi(page);
  await openBar(page);

  await page.getByLabel("дописати вид у бар").fill("абсент");
  await page.getByRole("button", { name: "+ Додати" }).click();
  await expect(page.locator("li.row", { hasText: "абсент" })).toBeVisible();

  await openListSettings(page);
  await page.getByRole("button", { name: "Стерти список" }).click();
  await page.getByRole("button", { name: "Точно стерти" }).click();

  await expect(page.locator("li.row", { hasText: "абсент" })).toBeHidden();
  await expect(page.locator("li.row", { hasText: "Горілка" })).toBeVisible();
});

test("бар у режимі гостя показує лише список і називає решту числом (#146)", async ({
  page,
}) => {
  await mockApi(page);
  await openBar(page);

  await openListSettings(page);
  await page.getByRole("button", { name: "веду сам" }).click();

  await expect(page.locator("li.row", { hasText: "Горілка" })).toBeHidden();
  await expect(page.getByText(/У покупках є ще \d+ видів/)).toBeVisible();

  await page.getByRole("button", { name: "Додати їх" }).click();
  await expect(page.locator("li.row", { hasText: "Горілка" })).toBeVisible();
});

test("бар, який агент не встиг назвати, каже «ще не порахував» (#5)", async ({
  page,
}) => {
  await mockApi(page, { bar: BAR_UNNAMED });
  await skipIntro(page);
  await enter(page);
  await page.getByRole("button", { name: "подія", exact: true }).click();
  await page.getByRole("button", { name: /Напої до приводу/ }).click();

  await expect(page.getByText(/ще не порахував/)).toBeVisible();
  await expect(page.getByText(/напоїв поки немає/)).toBeHidden();
});

test("рядок бару показує, ЗВІДКИ взялась цінова вилка (#5)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: "подія", exact: true }).click();
  await page.getByRole("button", { name: /Напої до приводу/ }).click();

  await expect(page.getByText(/брав за цю ціну/).first()).toBeVisible();
});


test("підключений стан не пропонує підключатись удруге", async ({ page }) => {
  await openApp(page);
  await expect(page.getByRole("button", { name: "Сільпо" })).toBeVisible();
  await page.getByRole("button", { name: "Сільпо" }).click();
  await expect(
    page.getByRole("button", { name: /Вийти й відкликати/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Підключити «Сільпо»" }),
  ).toBeHidden();
});

test("зі згоди повертає туди, звідки прийшли", async ({ page }) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();
  await page.getByRole("button", { name: "Сільпо" }).click();
  await expect(
    page.getByRole("heading", { name: "Акаунт «Сільпо»" }),
  ).toBeVisible();

  await page.getByRole("button", { name: "До комори" }).click();
  await expect(page.getByRole("button", { name: "Додати" })).toBeVisible();
});

/** Колір крапки стану — computed, а не з класу: перевіряємо те, що видно. */
async function dotColor(page: Page): Promise<string> {
  return page
    .locator("button.link .dot")
    .evaluate((node) => getComputedStyle(node).backgroundColor);
}

/** Значення токена палітри — щоб тест перевіряв ЗНАЧЕННЯ, а не хардкод. */
async function token(page: Page, name: string): Promise<string> {
  return page.evaluate((variable) => {
    const probe = document.createElement("span");
    probe.style.color = `var(${variable})`;
    document.body.append(probe);
    const value = getComputedStyle(probe).color;
    probe.remove();
    return value;
  }, name);
}

test("стан акаунта видно кольором І словом, а не лише кольором (#94)", async ({
  page,
}) => {
  await openApp(page);

  const chip = page.locator("button.link");
  await expect(chip).toContainText("Сільпо");
  expect(await dotColor(page)).toBe(await token(page, "--good"));

  await page.route("**/api/basket", (route) =>
    route.fulfill({
      status: 401,
      json: { detail: "термін дії доступу минув" },
    }),
  );
  await buildWeek(page);

  await expect(chip).toContainText("не підключено");
  expect(await dotColor(page)).toBe(await token(page, "--warn"));
});

test("розрив виглядає однаково, хай яка причина (#94)", async ({ page }) => {
  await mockApi(page, {
    session: { connected: false, reason: "термін дії доступу минув" },
  });
  await skipIntro(page);
  await enter(page);
  const expired = await dotColor(page);

  await mockApi(page, {
    session: { connected: false, reason: "ти вийшов з акаунта" },
  });
  await reenter(page);
  await expect(page.locator("button.link")).toContainText("не підключено");

  expect(await dotColor(page)).toBe(expired);
});

test("вихід не питає зайвого — питати нема про що (24.08)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: "Сільпо" }).click();

  await expect(page.getByText(/доступ перестане діяти одразу/)).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Вийти й відкликати/ }),
  ).toBeVisible();
  await expect(page.getByText(/Стежу за/)).toBeHidden();
});

test("згода каже, що в акаунт без гостя ніхто не заходить (24.08)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: "Сільпо" }).click();

  await page.getByText(/докладно/).click();
  await expect(
    page.getByText(/не заходимо в твій акаунт, коли тебе немає/),
  ).toBeVisible();
  await expect(
    page.getByText(/у твоєму браузері, не в нашій базі/),
  ).toBeVisible();
});


test("до запису сума названа оцінкою, а не обіцянкою", async ({ page }) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible();

  await expect(page.getByText(/оцінка за цінами полиці/)).toBeVisible();
});

test("після запису показана сума «Сільпо», а розбіжність названа числом", async ({
  page,
}) => {
  await openApp(page);
  await buildWeek(page);
  await checkout(page);

  const report = page.locator(".paid");
  await expect(report.getByText("до оплати")).toBeVisible();
  await expect(report).toContainText(/1\s?104/);
  await expect(report).toContainText(/1\s?153/, { timeout: 2000 });
  await expect(page.getByText(/моя оцінка була/)).toContainText(/менше\s+на/);
  await expect(page.getByText(/оцінка за цінами полиці/)).toBeHidden();
});

test("балабонуси названі числом, а кнопки застосування немає (#17)", async ({
  page,
}) => {
  await openApp(page);
  await buildWeek(page);
  await checkout(page);

  await expect(page.getByText(/340 балабонусів/)).toBeVisible();
  await expect(page.getByText(/застосувати їх можна в «Сільпо»/)).toBeVisible();
  await expect(page.getByRole("button", { name: /балабонус/i })).toHaveCount(0);
  await expect(page.getByRole("checkbox", { name: /балабонус/i })).toHaveCount(
    0,
  );
  await expect(page.getByText(/340\s*₴/)).toHaveCount(0);
});

function money(text: string): string {
  return text.replace(/\s+/gu, " ").trim();
}

test("після запису плашка бере суму «Сільпо», а не нашу оцінку (#81)", async ({
  page,
}) => {
  await openApp(page);
  await buildWeek(page);
  await checkout(page);
  await expect(page.getByRole("link", { name: /Підтвердити/ })).toBeVisible({
    timeout: 20_000,
  });

  const toPay = money(await page.locator(".paid .pay dd").innerText());
  expect(money(await page.locator(".dock-sum .num").innerText())).toBe(toPay);
  await expect(page.locator(".dock-note")).toContainText("до оплати");

  await expect(page.locator(".summary .totals")).toHaveCount(0);
  await expect(page.getByText(/суму порахувало «Сільпо»/)).toBeVisible();
});

test("до запису плашка називає своє число оцінкою (#81)", async ({ page }) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await expect(page.locator(".dock-note")).toContainText("оцінка");
});

test("правка складу після запису каже, що в кошик вона не поїхала (#81)", async ({
  page,
}) => {
  await openApp(page);
  await buildWeek(page);
  await checkout(page);
  await expect(page.getByRole("link", { name: /Підтвердити/ })).toBeVisible({
    timeout: 20_000,
  });

  await page
    .getByRole("button", { name: /^Більше: / })
    .first()
    .click();
  await expect(page.getByText(/склад правлений після запису/)).toBeVisible();

  const toPay = money(await page.locator(".paid .pay dd").innerText());
  expect(money(await page.locator(".dock-sum .num").innerText())).toBe(toPay);
});


test("перелік способів каже вголос, коли живий лишився один (#101)", async ({
  page,
}) => {
  await mockApi(page, {
    delivery: DELIVERY.map((option, index) =>
      index === 0
        ? option
        : {
            ...option,
            available: false,
            unavailableReason: "за твоєю адресою так не возять",
          },
    ),
  });
  await skipIntro(page);
  await enter(page);

  await expect(page.getByText(/Доступний один спосіб/)).toBeVisible();
  await expect(page.getByText(/за твоєю адресою так не возять/)).toBeVisible();
  await expect(page.getByRole("button", { name: "самовивіз" })).toBeDisabled();
});

test("коли способів кілька, перелік про це мовчить (#101)", async ({
  page,
}) => {
  await openApp(page);

  await expect(page.getByText(/Доступний один спосіб/)).toBeHidden();
  await expect(page.getByRole("button", { name: "самовивіз" })).toBeEnabled();
});

test("поки умови доставки їдуть, секція не називає жодної причини (#164)", async ({
  page,
}) => {
  await mockApi(page, { deliveryWait: "slow" });
  await skipIntro(page);
  await enter(page);

  const section = page.locator('[data-tour="delivery"]');
  await expect(section).toBeVisible();
  await expect(
    page.getByText(/не передбачено|ще немає|не возять|немає вільних/),
  ).toHaveCount(0);
  await expect(section.locator("button")).toHaveCount(0);
  await expect(section.getByText(/Читаю умови доставки/)).toBeVisible();

  await expect(section.getByRole("button", { name: "самовивіз" })).toBeVisible({
    timeout: 20_000,
  });
  await expect(section.getByText(/Читаю умови доставки/)).toBeHidden();
});

test("кошик без умов доставки не мовчить про мінімум і вагу (#185)", async ({
  page,
}) => {
  await openApp(page, { deliveryWait: "dead" });
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const dock = page.locator('[data-tour="checkout"]');
  await expect(dock).toContainText("Умов доставки я не прочитав");
  await expect(
    dock.getByRole("button", { name: "Прочитати ще раз" }),
  ).toBeVisible();
});

test("вибір способу розрізняє «ще їде» і «впало» (#185)", async ({ page }) => {
  await openApp(page, { deliveryWait: "dead" });
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await page.getByRole("button", { name: "спосіб не прочитався" }).click();
  const sheet = page.getByRole("dialog", { name: "Як забирати" });
  await expect(sheet).toContainText("Умов доставки я не прочитав");
  await expect(
    sheet.getByRole("button", { name: "Прочитати ще раз" }),
  ).toBeVisible();
});

test("умови доставки не доїхали — секція каже це словами і лишає дію (#164)", async ({
  page,
}) => {
  const silpo = await mockApi(page, { deliveryWait: "dead" });
  await skipIntro(page);
  await enter(page);

  const section = page.locator('[data-tour="delivery"]');
  await expect(section).toBeVisible();
  await expect(
    page.getByText(/не передбачено|не возять|Доступний один спосіб/),
  ).toHaveCount(0);
  await expect(section.getByRole("button", { name: "самовивіз" })).toHaveCount(
    0,
  );
  await expect(
    section.getByText(/Умови доставки не прочитались/),
  ).toBeVisible();
  await expect(
    section.getByText(/silpo_get_time_slots не відповів/),
  ).toBeVisible();

  const reach = await page.evaluate(() => {
    const hittable = (node: Element | null) => {
      if (node === null) return false;
      const box = node.getBoundingClientRect();
      if (box.bottom <= 0 || box.top >= window.innerHeight) return false;
      const top = document.elementFromPoint(
        box.left + box.width / 2,
        box.top + box.height / 2,
      );
      return top === node || node.contains(top);
    };
    const cause = [
      ...document.querySelectorAll('[data-tour="delivery"] p'),
    ].find((node) =>
      /Умови доставки не прочитались/.test(node.textContent ?? ""),
    );
    const action = [
      ...document.querySelectorAll('[data-tour="delivery"] button'),
    ].find((node) => /Прочитати умови ще раз/.test(node.textContent ?? ""));
    return {
      scrollY: window.scrollY,
      cause: hittable(cause ?? null),
      action: hittable(action ?? null),
    };
  });
  expect(reach.scrollY).toBe(0);
  expect(reach.cause && !reach.action).toBe(false);

  silpo.healDelivery();
  await section.getByRole("button", { name: /Прочитати умови ще раз/ }).click();

  await expect(
    section.getByRole("button", { name: "самовивіз" }),
  ).toBeEnabled();
  await expect(section.getByText(/Умови доставки не прочитались/)).toBeHidden();
});

test("зміна адреси не лишає термів попередньої (#164)", async ({ page }) => {
  const silpo = await mockApi(page, { deliveryWait: "slow" });
  await skipIntro(page);
  await enter(page);

  const section = page.locator('[data-tour="delivery"]');
  await expect(section.getByRole("button", { name: "самовивіз" })).toBeVisible({
    timeout: 20_000,
  });

  silpo.breakDelivery();
  await page.getByRole("button", { name: /змінити/ }).click();
  await page.getByLabel("Адреса доставки").fill("Вінниця, Пирогова, 20");
  await page.getByRole("button", { name: "Знайти" }).click();
  await page
    .getByRole("button", { name: "Вінниця, вулиця Пирогова, 20" })
    .click();

  await expect(section.getByText(/Читаю умови доставки/)).toBeVisible();
  await expect(page.getByText(/немає вільних кур'єрів/)).toHaveCount(0);
  await expect(section.locator("button")).toHaveCount(0);

  await expect(section.getByText(/Умови доставки не прочитались/)).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByText(/немає вільних кур'єрів/)).toHaveCount(0);
});

test("вибір способу в кошику теж каже, що живий лишився один (#101)", async ({
  page,
}) => {
  await mockApi(page, {
    delivery: DELIVERY.map((option, index) =>
      index === 0
        ? option
        : {
            ...option,
            available: false,
            unavailableReason: "за твоєю адресою так не возять",
          },
    ),
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await page.getByRole("button", { name: "кур'єр" }).click();
  await expect(page.getByText(/пропонує один спосіб/)).toBeVisible();
});


test("старт каже адресу і магазин, який збирає", async ({ page }) => {
  await openApp(page);

  await expect(
    page.getByText("Вінниця, вулиця Соборна, 1, кв. 2"),
  ).toBeVisible();
  await expect(
    page.getByText("збирає Вінниця, вулиця Соборна, 46"),
  ).toBeVisible();
  await expect(
    page.getByText("магазин збирання визначено за цією адресою"),
  ).toBeVisible();
});

test("гостю без збереженої адреси її питають одразу, а не ховають під дотик", async ({
  page,
}) => {
  await mockApi(page, {
    place: {
      address: null,
      tag: null,
      branch: null,
      branchId: null,
      source: "none",
      note: "магазин ще не визначено — назви адресу доставки",
      deliveryTypes: [],
      saved: [],
    },
  });
  await skipIntro(page);
  await enter(page);

  await expect(page.getByText("Адресу ще не знаю")).toBeVisible();
  await expect(page.getByLabel("Адреса доставки")).toBeVisible();
});

test("філія з нашого конфіга називає і себе, і дію (#345, #134)", async ({
  page,
}) => {
  await mockApi(page, {
    place: {
      address: null,
      tag: null,
      branch: "Вінниця, вулиця Соборна, 46",
      branchId: "demo-branch-1",
      source: "config",
      note:
        "магазин з налаштувань сервера, не за твоєю адресою — " +
        "назви адресу, і ціни з наявністю будуть з твоєї філії",
      deliveryTypes: [],
      saved: [],
    },
  });
  await skipIntro(page);
  await enter(page);

  const picker = page.getByRole("dialog", { name: "Куди веземо" });
  await expect(picker).toBeVisible();
  await picker.getByRole("button", { name: "Закрити" }).click();

  await expect(
    page.getByText("збирає Вінниця, вулиця Соборна, 46"),
  ).toBeVisible();
  await expect(
    page.getByText(/назви адресу, і ціни з наявністю/),
  ).toBeVisible();

  await expect(page.getByText("назвати адресу")).toBeVisible();
  await expect(page.getByText("змінити")).toHaveCount(0);
});

test("пошук адреси показує варіанти, а не бере перший-ліпший", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /змінити/ }).click();

  await page.getByLabel("Адреса доставки").fill("Вінниця, Пирогова, 20");
  await page.getByRole("button", { name: "Знайти" }).click();

  await expect(page.getByRole("button", { name: /Боярка/ })).toBeVisible();
  await page
    .getByRole("button", { name: "Вінниця, вулиця Пирогова, 20" })
    .click();

  await expect(
    page.getByText("Вінниця, вулиця Пирогова, 20", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("збирає Вінниця, вулиця Келецька, 117"),
  ).toBeVisible();
});

test("адресу можна змінити на зібраному кошику — з перезбіркою (#95)", async ({
  page,
}) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await expect(
    page.getByText("збирає Вінниця, вулиця Соборна, 46"),
  ).toBeVisible();

  await page.locator("button.place").click();
  await page.getByLabel("Адреса доставки").fill("Вінниця, Пирогова, 20");
  await page.getByRole("button", { name: "Знайти" }).click();
  await page
    .getByRole("button", { name: "Вінниця, вулиця Пирогова, 20" })
    .click();

  const ask = page.getByRole("dialog", { name: "Змінити адресу?" });
  await expect(ask).toContainText("це інший магазин");
  await expect(ask).toContainText("перевірю кожну з 10 позицій");

  await ask.getByRole("button", { name: "Змінити і перезібрати" }).click();

  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await expect(
    page.getByText("збирає Вінниця, вулиця Келецька, 117"),
  ).toBeVisible();
});

test("відмова від перезбірки лишає стару адресу, а не половину (#95)", async ({
  page,
}) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await page.locator("button.place").click();
  await page.getByLabel("Адреса доставки").fill("Вінниця, Пирогова, 20");
  await page.getByRole("button", { name: "Знайти" }).click();
  await page
    .getByRole("button", { name: "Вінниця, вулиця Пирогова, 20" })
    .click();
  await page.getByRole("button", { name: "Лишити стару" }).click();

  await expect(
    page.getByText("збирає Вінниця, вулиця Соборна, 46"),
  ).toBeVisible();
  await expect(page.getByText("Вінниця, вулиця Пирогова, 20")).toHaveCount(0);
});

test("вибір адреси відкривається окремим вікном, а не списком під полем (#83)", async ({
  page,
}) => {
  await openApp(page);
  const where = async () =>
    await page.locator('[data-tour="pantry"]').evaluate((node) => {
      const box = node.getBoundingClientRect();
      return Math.round(box.top + window.scrollY);
    });
  const before = await where();

  await page.getByRole("button", { name: /змінити/ }).click();

  await expect(page.getByRole("dialog", { name: "Куди веземо" })).toBeVisible();
  expect(await where()).toBe(before);
});

test("старий бекенд без /api/place не лишає блок у вічному скелеті", async ({
  page,
}) => {
  await mockApi(page);
  await page.route("**/api/place", (route) =>
    route.fulfill({
      status: 501,
      json: { detail: "наживо ще не реалізовано" },
    }),
  );
  await skipIntro(page);
  await enter(page);

  await expect(page.getByText("Куди веземо — не знаю")).toBeVisible();
  await expect(page.getByText("наживо ще не реалізовано")).toBeVisible();
});

test("кошик показує, куди веземо, до кнопки «Оформити»", async ({ page }) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible();

  await expect(
    page.getByText("збирає Вінниця, вулиця Соборна, 46"),
  ).toBeVisible();
});


test("підказки підсвічують справжні елементи і показуються один раз", async ({
  page,
}) => {
  await mockApi(page);
  await page.addInitScript(
    ([onboard]: [string]) => localStorage.setItem(onboard, "1"),
    [ONBOARD_KEY] as [string],
  );
  await enter(page);

  const tour = page.getByRole("dialog", { name: "Підказки" });
  await expect(tour).toBeVisible();
  await expect(tour.getByText("1 / 5")).toBeVisible();

  await tour.getByRole("button", { name: "пропустити" }).click();
  await expect(tour).toBeHidden();

  await toStart(page);
  await expect(tour).toBeVisible();
  await expect(tour.getByText("1 / 9")).toBeVisible();
  await expect(tour.getByRole("heading")).toContainText("Твій акаунт");

  await tour.getByRole("button", { name: "пропустити" }).click();
  await expect(tour).toBeHidden();
  await reenter(page);
  await expect(page.getByRole("dialog", { name: "Підказки" })).toBeHidden();
});

test("крок підказки зникає разом з елементом, якого немає", async ({
  page,
}) => {
  await mockApi(page, { session: null });
  await page.addInitScript(
    ([onboard]: [string]) => localStorage.setItem(onboard, "1"),
    [ONBOARD_KEY] as [string],
  );
  await enter(page);
  await expect(page.getByRole("dialog", { name: "Підказки" })).toBeHidden();
});

test("підказки повертаються з бургера", async ({ page }) => {
  await openApp(page);
  await page.getByRole("button", { name: "Меню" }).click();
  await page.getByRole("button", { name: /підказки/ }).click();
  await expect(page.getByRole("dialog", { name: "Підказки" })).toBeVisible();
});


test("перший гість бачить «злам», і в ньому названо його номер", async ({
  page,
}) => {
  await mockApi(page, { session: { connected: true, greet: 3 } });
  await skipIntro(page);
  await enter(page);

  const breach = page.getByRole("dialog", { name: "Ініціалізація" });
  await expect(breach).toBeVisible();
  await breach.getByRole("button", { name: "пропустити" }).click();

  await expect(breach.getByText("ДОСТУП ДО СЕРВІСУ НАДАНО")).toBeVisible();
  await expect(breach.getByText(/ти #3 з перших десяти/)).toBeVisible();
  await expect(breach.getByText(/стерто 0 з 0/)).toBeVisible();
  await expect(
    breach.getByText(/токен справді\s+живе у твоєму браузері/),
  ).toBeVisible();

  await breach.getByRole("button", { name: "Увійти" }).click();
  await expect(breach).toBeHidden();
});

test("решта гостей заставки не бачить", async ({ page }) => {
  await openApp(page);
  await expect(
    page.getByRole("dialog", { name: "Ініціалізація" }),
  ).toBeHidden();
});

test("запуск пасхалки руками схований за панеллю дебагу", async ({ page }) => {
  await openApp(page);
  const burger = page.getByRole("button", { name: "Меню" });
  await burger.click();
  await expect(page.getByRole("button", { name: /режим хакера/ })).toBeHidden();

  await burger.click();
  await page.keyboard.press("Backquote");
  await burger.click();
  const hidden = page.getByRole("button", { name: /режим хакера/ });
  await expect(hidden).toBeVisible();
  await hidden.click();

  await expect(
    page.getByRole("dialog", { name: "Ініціалізація" }),
  ).toBeVisible();
});

test("клавіша ` працює після кліку по кнопці", async ({ page }, testInfo) => {
  test.skip(
    testInfo.project.name !== "desktop",
    "панель ховається на вузькому екрані",
  );
  await page.setViewportSize({ width: 1440, height: 900 });
  await openApp(page);

  await page.getByRole("button", { name: "подія", exact: true }).click();
  await page.keyboard.press("`");
  await expect(
    page.getByRole("complementary", { name: "Панель дебагу" }),
  ).toBeVisible();
});

test("вихід з акаунта є і в меню, не лише за чипсом", async ({ page }) => {
  await openApp(page);
  await page.getByRole("button", { name: "Меню" }).click();
  await page.getByRole("button", { name: /вийти з «Сільпо»/ }).click();

  await expect(
    page.getByRole("heading", { name: "Акаунт «Сільпо»" }),
  ).toBeVisible();
});

test("дебаг називає версію UI і коміт збірки", async ({ page }, testInfo) => {
  test.skip(
    testInfo.project.name !== "desktop",
    "панель ховається на вузькому екрані",
  );
  await page.setViewportSize({ width: 1440, height: 900 });
  await openApp(page);
  await page.keyboard.press("`");

  const panel = page.getByRole("complementary", { name: "Панель дебагу" });
  await expect(panel).toBeVisible();
  await expect(panel.getByText(/^\d{4}\.\d{2}\.\d{2}-\d{4}$/)).toBeVisible();
});

test("дебаг: повний JSON запиту і відповіді з копіюванням", async ({
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "desktop",
    "панель ховається на вузькому екрані",
  );
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.context().grantPermissions(["clipboard-write"]);
  await openApp(page);
  await page.keyboard.press("`");
  const panel = page.getByRole("complementary", { name: "Панель дебагу" });
  await expect(panel).toBeVisible();

  await expect(
    panel.getByText("прогону ще не було — зберіть кошик").first(),
  ).toBeVisible();

  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const request = panel.locator("details", { hasText: "запит" }).first();
  await request.getByRole("button", { name: "копіювати" }).click();
  await expect(
    request.getByRole("button", { name: "скопійовано" }),
  ).toBeVisible();

  await request.locator("summary").click();
  await expect(request.locator("pre")).toContainText('"shoppingList"');
  await expect(panel.getByText("відповідь — Basket цілком")).toBeVisible();
});

test("відмова агента стоїть окремо від «не знайшлось» і несе причину", async ({
  page,
}) => {
  await mockApi(page, {
    basket: {
      unresolved: ["шафран"],
      declined: [
        { intent: "масло", why: "фасовки 100 г під цей намір немає" },
        { intent: "Рулет курячий", why: "усі знайдені рулети солодкі" },
      ],
    },
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const declined = page.locator(".missed").filter({ hasText: "Агент не взяв" });
  await expect(declined.locator("li").first()).toHaveText(
    "масло — фасовки 100 г під цей намір немає",
  );
  await expect(declined.locator("li").nth(1)).toHaveText(
    "Рулет курячий — усі знайдені рулети солодкі",
  );
  await expect(declined).toContainText("Зніми правило");
  const missed = page.locator(".missed").filter({ hasText: "Не знайшлось" });
  await expect(missed).toContainText("шафран");
  await expect(missed).not.toContainText("масло");
});

test("без відмов агента блоку «Агент не взяв» на екрані немає", async ({
  page,
}) => {
  await mockApi(page, { basket: { declined: [] } });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await expect(
    page.locator(".missed").filter({ hasText: "Агент не взяв" }),
  ).toHaveCount(0);
});

test("назване, якого на слот немає, радить інше вікно, а не інші слова", async ({
  page,
}) => {
  await mockApi(page, {
    basket: { unresolved: ["шафран"], notCollected: ["свинина", "Спрайт"] },
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const missed = page.locator(".missed");
  await expect(missed.filter({ hasText: "Не знайшлось" })).toContainText(
    "шафран",
  );
  const slot = missed.filter({ hasText: "На цей слот немає" });
  await expect(slot).toContainText("свинина");
  await expect(slot).toContainText("Спрайт");
  await expect(slot).toContainText("інший слот");
  await expect(missed.filter({ hasText: "Не знайшлось" })).not.toContainText(
    "Спрайт",
  );
});

test("причин «не поїхало» кілька -- вони згорнуті під одне число (#350)", async ({
  page,
}) => {
  await mockApi(page, {
    basket: { unresolved: ["шафран"], notCollected: ["свинина", "Спрайт"] },
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const all = page.locator("details.missed-all");
  await expect(all).toContainText("Не поїхало в кошик: 3");
  await expect(all).not.toHaveAttribute("open", /.*/);

  await all.locator("summary").click();
  await expect(all).toHaveAttribute("open", /.*/);
  await expect(
    all.locator(".missed").filter({ hasText: "Не знайшлось" }),
  ).toBeVisible();
  await expect(
    all.locator(".missed").filter({ hasText: "На цей слот немає" }),
  ).toBeVisible();
});

test("причина одна -- згортати нічого, і шапки над нею немає", async ({
  page,
}) => {
  await mockApi(page, { basket: { unresolved: ["шафран"] } });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await expect(
    page.locator(".missed").filter({ hasText: "Не знайшлось" }),
  ).toBeVisible();
  await expect(page.getByText("Не поїхало в кошик")).toBeHidden();
});

const CHEESE = {
  intent: "сир",
  question: "Сир твердий чи кисломолочний?",
  options: [
    {
      title: "сир твердий",
      slug: "",
      query: "сир твердий",
      count: 6,
      priceFrom: 99,
      byWeight: false,
    },
    {
      title: "Сир кисломолочний",
      slug: "syr-kyslo",
      query: null,
      count: 8,
      priceFrom: 39.99,
      byWeight: false,
    },
    {
      title: "Свинина",
      slug: "svynyna",
      query: null,
      count: 4,
      priceFrom: 272.46,
      byWeight: true,
    },
  ],
  picks: [],
};

/**
 * Питання, під яке дерево не дало НІЧОГО (#190).
 *
 * Живий випадок 30.08 і повторення на проді 31.08: агент питає конкретне, а
 * відповісти можна було лише «інше» або «не треба». Числа справжні -- під
 * «Томат черрі» дев'ять позицій однієї фасовки 250 г розійшлись від 71,99 до
 * 154 ₴, і саме ця вилка й робить питання питанням.
 */
const CHERRY = {
  intent: "Томат La Parcela Черрі Angello",
  question: "Обирати конкретний сорт чи будь-який черрі?",
  options: [],
  picks: [
    {
      externalProductId: "9001",
      name: "Томат Гордій Черрі",
      price: 71.99,
      ratio: "250г",
      byWeight: false,
    },
    {
      externalProductId: "9002",
      name: "Томат черрі",
      price: 154,
      ratio: "250г",
      byWeight: false,
    },
  ],
};

test("двоякий намір питає чипсами з цінами, а не вирішує мовчки", async ({
  page,
}) => {
  const sent: Record<string, unknown>[] = [];
  await mockApi(page, {
    basket: { questions: [CHEESE] },
    onRefill: (body) => sent.push(body),
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const ask = page.locator(".ask");
  await expect(ask).toContainText("Сир твердий чи кисломолочний?");
  await expect(ask.getByRole("button", { name: /^сир твердий/ })).toContainText(
    "від 99",
  );
  await expect(ask.getByRole("button", { name: /^Свинина/ })).toContainText(
    "/кг",
  );
  await expect(ask.getByRole("button", { name: /^Сири$/ })).toHaveCount(0);
  await expect(ask).toContainText("в кошик не їде");

  await ask.getByRole("button", { name: /^сир твердий/ }).click();
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.locator(".ask")).toHaveCount(0);

  const last = sent.at(-1) as { answers: { intent: string; slug: string }[] };
  expect(last.answers).toEqual([
    {
      intent: "сир",
      slug: null,
      query: "сир твердий",
      text: null,
      skip: false,
    },
  ]);
});

test("варіант-вузол і варіант-фраза живуть в одному списку і відповідають по-різному (#280)", async ({
  page,
}) => {
  const sent: Record<string, unknown>[] = [];
  await mockApi(page, {
    basket: { questions: [CHEESE] },
    onRefill: (body) => sent.push(body),
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const ask = page.locator(".ask");
  await expect(ask.locator(".options button")).toHaveCount(3);
  await expect(
    ask.getByRole("button", { name: /^Сир кисломолочний/ }),
  ).toContainText("від 39,99");

  await ask.getByRole("button", { name: /^Сир кисломолочний/ }).click();
  await expect(page.locator(".ask")).toHaveCount(0, { timeout: 20_000 });

  const last = sent.at(-1) as { answers: Record<string, unknown>[] };
  expect(last.answers).toEqual([
    {
      intent: "сир",
      slug: "syr-kyslo",
      query: null,
      text: null,
      skip: false,
    },
  ]);
});

test("питання: види окремо, «інше» і «не треба» — за лінією (#100)", async ({
  page,
}) => {
  await mockApi(page, { basket: { questions: [CHEESE] } });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const ask = page.locator(".ask");
  const option = ask.getByRole("button", { name: /^сир твердий/ });
  const paint = await option.evaluate((el) => {
    const css = getComputedStyle(el);
    return { border: css.borderTopWidth, background: css.backgroundColor };
  });
  expect(paint.border).toBe("1px");
  expect(paint.background).not.toBe("rgba(0, 0, 0, 0)");

  await expect(ask.locator(".options button")).toHaveCount(3);
  await expect(
    ask.locator(".options").getByRole("button", { name: "не треба" }),
  ).toHaveCount(0);

  await ask.getByRole("button", { name: "інше" }).click();
  await expect(ask.getByRole("button", { name: "не треба" })).toBeVisible();
});

test("«Вище межі» — заголовок і пояснення, а не суцільний абзац (#100)", async ({
  page,
}) => {
  await mockApi(page, { basket: { budget: 300 } });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const over = page
    .locator(".missed")
    .filter({ hasText: "Вище верхньої межі на" });
  await expect(over.locator("p")).toHaveCount(2);

  const tone = await over.evaluate((el) => {
    const head = el.querySelector("strong") as HTMLElement;
    const why = el.querySelector(".why") as HTMLElement;
    return {
      head: getComputedStyle(head).color,
      why: getComputedStyle(why).color,
    };
  });
  expect(tone.head, "кричить саме число, а не весь блок").not.toBe(tone.why);
});

test("добір: перелік видів лягає в один рядок, решта названа числом (#100)", async ({
  page,
}) => {
  await mockApi(page, {
    basket: {
      budget: 3000,
      postponed: Array.from({ length: 6 }, (_, i) => ({
        intent: `Кава Lavazza Crema e Gusto ${i + 1}`,
        reason: "закінчилось, але не влізло в звичний розмір кошика (14 поз.)",
        estimate: 245,
        refillable: true,
      })),
    },
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const what = page.locator('[data-tour="refill"] .week-what');
  await expect(what).toContainText("і ще 5");
  const lines = await what.evaluate(
    (el) =>
      el.getBoundingClientRect().height /
      parseFloat(getComputedStyle(el).lineHeight),
  );
  expect(Math.round(lines), "перелік — один рядок, а не абзац").toBe(1);
});

test("дебаг тримає прогони списком і каже, що змінила відповідь гостя (#55)", async ({
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "desktop",
    "панель ховається на вузькому екрані",
  );
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockApi(page, { basket: { questions: [CHEESE] } });
  await skipIntro(page);
  await enter(page);
  await page.keyboard.press("`");
  const panel = page.getByRole("complementary", { name: "Панель дебагу" });

  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await expect(panel.getByText("прогони · 1")).toBeVisible();
  await expect(panel.getByText("первинний збір")).toBeVisible();

  await page
    .locator(".ask")
    .getByRole("button", { name: /^сир твердий/ })
    .click();
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await expect(panel.getByText("прогони · 2")).toBeVisible();
  await expect(panel.getByText("уточнення «сир» → сир твердий")).toBeVisible();
  await expect(panel.getByText("первинний збір")).toBeVisible();

  await expect(panel.locator(".delta").first()).toContainText("-1 питання");

  const runs = panel.locator("article.run");
  await expect(runs).toHaveCount(2);
  await runs
    .first()
    .locator("details", { hasText: "запит" })
    .first()
    .locator("summary")
    .click();
  await expect(runs.first().locator("pre").first()).toContainText('"answers"');
});

test("правка рядка — теж прогін, і панель каже, який з них на екрані (#84)", async ({
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "desktop",
    "панель ховається на вузькому екрані",
  );
  await page.setViewportSize({ width: 1440, height: 900 });
  await openApp(page);
  await page.keyboard.press("`");
  const panel = page.getByRole("complementary", { name: "Панель дебагу" });

  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await expect(panel.getByText("прогони · 1")).toBeVisible();
  await expect(panel.getByText("на екрані")).toHaveCount(1);
  const step = panel.locator("article.step", { hasText: "agent.correction" });
  await expect(step).toHaveCount(0);

  const line = page.getByRole("button", { name: /^Прибрати / }).first();
  const name = (await line.getAttribute("aria-label"))!.replace(
    "Прибрати ",
    "",
  );
  await line.click();
  await expect(
    page.getByText("ти сказав, що ще є вдома — не купую").first(),
  ).toBeVisible();

  await expect(panel.getByText("прогони · 2")).toBeVisible();
  const runs = panel.locator("article.run");
  await expect(runs).toHaveCount(2);
  await expect(runs.first()).toContainText(
    `правка «${name}» → ти сказав, що ще є вдома`,
  );
  await expect(runs.last()).toContainText("первинний збір");

  await expect(panel.getByText("на екрані")).toHaveCount(1);
  await expect(runs.first().getByText("на екрані")).toBeVisible();

  await expect(step).toHaveCount(1);
});

test("добір — теж прогін, і в панелі він названий своїм рядком (#84, #79)", async ({
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "desktop",
    "панель ховається на вузькому екрані",
  );
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockApi(page, { basket: { postponed: POSTPONED, budget: 3000 } });
  await skipIntro(page);
  await enter(page);
  await page.keyboard.press("`");
  const panel = page.getByRole("complementary", { name: "Панель дебагу" });

  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page
    .locator('[data-tour="refill"]')
    .getByRole("button", { name: /Закрити решту тижня/ })
    .click();
  await expect(panel.getByText("прогони · 2")).toBeVisible();
  const runs = panel.locator("article.run");
  await expect(runs.first()).toContainText(
    "добір: решта тижня → Печиво вівсяне",
  );
  await expect(runs.first().getByText("на екрані")).toBeVisible();
  const steps = panel
    .locator("section.block")
    .filter({ hasNotText: "петля комори" })
    .locator("article.step");
  await expect(
    steps.filter({ hasText: "silpo_get_my_offline_orders" }),
  ).toHaveCount(1);
  await expect(
    steps.filter({ hasText: "silpo_find_products_batch" }),
  ).toHaveCount(1);
});

test("крок, що ходив у модель, називає свій промпт іменем і хешем (#295)", async ({
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "desktop",
    "панель ховається на вузькому екрані",
  );
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockApi(page, { basket: { postponed: POSTPONED, budget: 3000 } });
  await skipIntro(page);
  await enter(page);
  await page.keyboard.press("`");
  const panel = page.getByRole("complementary", { name: "Панель дебагу" });

  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page
    .locator('[data-tour="refill"]')
    .getByRole("button", { name: /Закрити решту тижня/ })
    .click();

  const steps = panel.locator("article.step");
  const agent = steps.filter({ hasText: "Mistral Large 3" });
  await expect(agent).toHaveCount(1);
  await expect(agent.locator(".prompt")).toHaveText(
    "промпт: pick[head@0e82ff24,label@7d9d6d22,tail@83ac1de5]",
  );

  const search = steps.filter({ hasText: "silpo_find_products_batch" });
  await expect(search).toHaveCount(1);
  await expect(search.locator(".prompt")).toHaveCount(0);
});

test("крок плану на екрані несе числа, а сам план -- аргументом під дебагом (#301)", async ({
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "desktop",
    "панель ховається на вузькому екрані",
  );
  await page.setViewportSize({ width: 1440, height: 900 });
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await page.getByRole("button", { name: "Що зробив агент" }).click();
  const card = page
    .locator("article.card")
    .filter({ hasText: "рішення моделі" });
  await expect(card).toContainText("план від моделі, знято 1: 15 кроків");
  await expect(card).not.toContainText("history.receipts");
  await expect(card).not.toContainText("cart.reread");

  await page.keyboard.press("`");
  const panel = page.getByRole("complementary", { name: "Панель дебагу" });
  const step = panel.locator("article.step").filter({ hasText: "agent.plan" });
  await expect(step).toContainText("план від моделі, знято 1: 15 кроків");
  await step.getByText("аргументи (редаговані)").click();
  await expect(step.locator("pre")).toContainText(
    "history.receipts -> history.orders",
  );
  await expect(step.locator("pre")).toContainText("cart.revalidate");
});

test("слот у кроці трейсу -- людською мовою, а ISO лишається аргументом (#301)", async ({
  page,
}) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page.getByRole("button", { name: "Що зробив агент" }).click();

  const log = page.locator(".log");
  await log.getByRole("button", { name: "Показати журнал" }).click();
  await expect(log.locator("pre")).toContainText("обрано слот пт 11:00–13:00");
  await expect(log.locator("pre")).not.toContainText("T11:00:00");
});

test("на питання можна відповісти своїми словами, а не лише переліком", async ({
  page,
}) => {
  const sent: Record<string, unknown>[] = [];
  await mockApi(page, {
    basket: { questions: [CHEESE] },
    onRefill: (body) => sent.push(body),
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const ask = page.locator(".ask");
  await ask.getByRole("button", { name: "інше" }).click();
  await ask.getByLabel("Інший варіант").fill("бринза");
  await ask.getByRole("button", { name: "Ок" }).click();

  await expect(page.locator(".ask")).toHaveCount(0, { timeout: 20_000 });
  const last = sent.at(-1) as { answers: { intent: string; text: string }[] };
  expect(last.answers).toEqual([
    { intent: "сир", slug: null, query: null, text: "бринза", skip: false },
  ]);
});

test("«не треба» — така сама відповідь, як і вибір", async ({ page }) => {
  const sent: Record<string, unknown>[] = [];
  await mockApi(page, {
    basket: { questions: [CHEESE] },
    onBuild: (body) => sent.push(body),
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await page.locator(".ask").getByRole("button", { name: "не треба" }).click();
  await expect(page.locator(".ask")).toHaveCount(0);
  const afterSkip = sent.length;

  await page.getByRole("button", { name: "На початок" }).click();
  await buildWeek(page);
  await expect
    .poll(() => sent.length, { timeout: 20_000 })
    .toBeGreaterThan(afterSkip);

  const last = sent.at(-1) as { answers: { intent: string; skip: boolean }[] };
  expect(last.answers).toEqual([
    { intent: "сир", slug: null, query: null, text: null, skip: true },
  ]);
});

test("на демо диктофон одномовний: перемикача мови не видно", async ({
  page,
}) => {
  await stubSpeech(page);
  await openPantryAdd(page);

  const dialog = page.getByRole("dialog", { name: "Диктування" });
  await expect(dialog).toBeVisible();
  await expect(
    dialog.getByRole("group", { name: "Мова розпізнавання" }),
  ).toHaveCount(0);
  expect(await page.evaluate(() => (window as any).__rec.lang)).toBe("uk-UA");
});

test("мова диктування перемикається і запам'ятовується", async ({ page }) => {
  await stubSpeech(page);
  await page.addInitScript(() => localStorage.setItem("komora:debug", "1"));
  await openPantryAdd(page);

  const dialog = page.getByRole("dialog", { name: "Диктування" });
  await expect(dialog.getByRole("button", { name: "укр" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(await page.evaluate(() => (window as any).__rec.lang)).toBe("uk-UA");

  await page.evaluate(() => (window as any).__say("сир", true));
  await expect(dialog.getByText("сир")).toBeVisible();

  await dialog.getByRole("button", { name: "рус" }).click();
  await expect(dialog.getByRole("button", { name: "рус" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  expect(await page.evaluate(() => (window as any).__rec.lang)).toBe("ru-RU");
  await expect(dialog.getByText("сир")).toHaveCount(0);

  await reenter(page);
  await openPantryAdd(page);
  await expect(
    page
      .getByRole("dialog", { name: "Диктування" })
      .getByRole("button", { name: "рус" }),
  ).toHaveAttribute("aria-pressed", "true");
  expect(await page.evaluate(() => (window as any).__rec.lang)).toBe("ru-RU");
});

test("знята галочка правила теж питає про перезбірку — і запит валідний", async ({
  page,
}) => {
  const sent: Record<string, unknown>[] = [];
  await mockApi(page, { onBuild: (body) => sent.push(body) });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await page.getByRole("button", { name: "здоровіше", exact: true }).click();

  const ask = page.getByRole("dialog", { name: "Перезібрати кошик?" });
  await expect(ask).toBeVisible();
  await ask.getByRole("button", { name: "Перезібрати" }).click();
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  expect(sent.at(-1)?.source).toBe("list");
});

test("кожен контрол старту доїжджає в запит (#135)", async ({ page }) => {
  const sent: Record<string, unknown>[] = [];
  await openApp(page, { onBuild: (body) => sent.push(body) });

  await page.getByRole("button", { name: "подія", exact: true }).click();
  await page.getByRole("button", { name: "Більше людей" }).click();
  const people = Number(await page.locator(".people-n").innerText());
  await page.getByRole("button", { name: /зібрати приблизно на/ }).click();
  await page.getByRole("button", { name: "1 200", exact: true }).click();
  await page.getByRole("button", { name: "На цей раз" }).click();
  await page
    .getByPlaceholder(/молоко/)
    .first()
    .fill("васабі");

  await page.getByRole("button", { name: "Зібрати на подію" }).click();
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const body = sent.at(-1) ?? {};
  expect(body.mode).toBe("event");
  expect(body.occasionPeople).toBe(people);
  expect(body.budget).toBe(1200);
  expect(body.shoppingList).toEqual(["васабі"]);
  expect(body.delivery).toBeTruthy();
  expect(body.source).toBe("list");
});

test("чипс розбіжності називає ЩО змінилось і сам прогону не запускає (#86)", async ({
  page,
}) => {
  const sent: Record<string, unknown>[] = [];
  await mockApi(page, { onBuild: (body) => sent.push(body) });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  expect(sent).toHaveLength(1);

  await page.getByRole("button", { name: /зібрати приблизно на/ }).click();
  const money = page.getByRole("dialog", { name: "Межа на цей кошик" });
  await money.getByRole("button", { name: /^3\s*300$/ }).click();
  await money.getByRole("button", { name: "На цей раз" }).click();

  const chip = page.getByRole("button", { name: /що робити/ });
  await expect(chip).toContainText("межа");
  await expect(chip).not.toContainText("правила змінились");

  await chip.click();
  const ask = page.getByRole("dialog", { name: "Перезібрати кошик?" });
  await expect(ask).toBeVisible();
  await expect(ask).toContainText("межа");
  expect(sent).toHaveLength(1);
});

test("«Прибрати зміну» — така сама відповідь, як перезбірка (#86)", async ({
  page,
}) => {
  const sent: Record<string, unknown>[] = [];
  await mockApi(page, { onBuild: (body) => sent.push(body) });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const rule = page.getByRole("button", { name: "здоровіше", exact: true });
  await rule.click();

  const ask = page.getByRole("dialog", { name: "Перезібрати кошик?" });
  await expect(ask).toContainText("знято правило «здоровіше»");
  await ask.getByRole("button", { name: "Прибрати зміну" }).click();

  await expect(ask).toHaveCount(0);
  await expect(rule).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: /що робити/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeEnabled();
  expect(sent).toHaveLength(1);

  await elsewhere(page);
  await expect(
    page.getByRole("button", { name: "здоровіше", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
});

test("межа: зняте видно поіменно, а перевищення — числом (#57)", async ({
  page,
}) => {
  await mockApi(page, {
    basket: {
      budget: 300,
      trimmed: [
        {
          intent: "Кава Lavazza",
          name: "Кава Lavazza Crema e Gusto",
          price: 245,
          reason: "цього тижня можна пропустити — брав два тижні тому",
        },
      ],
    },
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const cut = page.locator(".missed").filter({ hasText: "Не влізло в 300" });
  await expect(cut).toContainText("Кава Lavazza Crema e Gusto");
  await expect(cut).toContainText("цього тижня можна пропустити");

  const over = page
    .locator(".missed")
    .filter({ hasText: "Вище верхньої межі на" });
  await expect(over).toContainText("Назване тобою агент не знімає");
});

test("без межі жоден з двох станів не з'являється", async ({ page }) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.locator(".missed").filter({ hasText: "межі" })).toHaveCount(
    0,
  );
});

test("ціль кошика приходить з ЙОГО замовлень, а не з нашого числа (#212)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: "на тиждень", exact: true }).click();

  await expect(
    page.getByRole("button", { name: /Зібрати на тиждень на/ }),
  ).toContainText("1 500");

  await page.getByRole("button", { name: /зібрати приблизно на/ }).click();
  await expect(page.getByText(/медіана 1500, p75 2100/)).toBeVisible();
  await expect(
    page.getByRole("button", { name: "3 300", exact: true }),
  ).toBeVisible();
});

test("названа гостем сума сильніша за пораховану (#212)", async ({ page }) => {
  await openApp(page);
  await page.getByRole("button", { name: "на тиждень", exact: true }).click();
  await page.getByRole("button", { name: /зібрати приблизно на/ }).click();
  await page.getByRole("button", { name: "1 200", exact: true }).click();
  await expect(
    page.getByRole("button", { name: /Зібрати на тиждень на/ }),
  ).toContainText("1 200");

  await page.getByRole("button", { name: "На цей раз" }).click();

  await page.getByRole("button", { name: /Закінчується/ }).click();
  const list = page.locator('ul.list, ul[class*="list"]').first();
  await expect(list.locator("li").first()).toBeVisible();
  await page.getByRole("button", { name: "На початок" }).last().click();

  await expect(
    page.getByRole("button", { name: /Зібрати на тиждень на/ }),
  ).toContainText("1 200");
});

test("панель бюджету каже про тиждень зміряним числом, а не обіцянкою", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /зібрати приблизно на/ }).click();

  const frame = page.locator('[data-tour="week-spend"]');
  await expect(frame).toContainText("цього тижня вже витрачено");
  await expect(frame).toContainText("1 000");
  await expect(frame).toContainText("2 чеки");
  await expect(page.getByText("агент ріже добране з циклів")).toBeVisible();
});

test("тиждень без покупок каже про це, а не показує нуль", async ({ page }) => {
  await mockApi(page, {
    week: { spent: 0, receipts: 0, since: "2026-08-17T00:00:00" },
  });
  await skipIntro(page);
  await enter(page);
  await page.getByRole("button", { name: /зібрати приблизно на/ }).click();

  await expect(page.locator('[data-tour="week-spend"]')).toContainText(
    "цього тижня покупок ще не було",
  );
});

test("кнопка чужого кошика каже, що саме доводитиме (#53)", async ({
  page,
}) => {
  await openApp(page);

  const button = page.locator('[data-tour="from-cart"]');
  await expect(button).toContainText("У кошику 7 позицій");
  await expect(button).toContainText("1 253");
  await expect(button).toBeEnabled();
});

test("док не займає пів екрана на порожній коморі (#125)", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page, {
    pantry: "empty",
    cart: { rows: 0, total: 0, slot: null },
  });
  await skipIntro(page);
  await enter(page);
  await expect(page.getByRole("button", { name: /^Зібрати / })).toBeDisabled();

  const dock = await page.locator(".dock").boundingBox();
  expect(dock, "док мусить бути на екрані").not.toBeNull();
  expect(dock!.height, "було 343 з 844 — 41% екрана").toBeLessThan(300);

  const chips = page.locator('[data-tour="week"] .chip');
  for (const box of await chips.evaluateAll((nodes) =>
    nodes.map((node) => node.getBoundingClientRect().right),
  )) {
    expect(box, "чип визирає за край екрана 390 px").toBeLessThanOrEqual(390);
  }
});

test("порожній кошик гасить кнопку і каже, що з ним робити", async ({
  page,
}) => {
  await mockApi(page, { cart: { rows: 0, total: 0, slot: null } });
  await skipIntro(page);
  await enter(page);

  await expect(page.locator('[data-tour="from-cart"]')).toHaveCount(0);
});

test("кошик не прочитався — кнопка лишається робочою, але вже нічого не стверджує", async ({
  page,
}) => {
  await mockApi(page, { cart: "unknown" });
  await skipIntro(page);
  await enter(page);

  const button = page.locator('[data-tour="from-cart"]');
  await expect(button).toContainText("Перевірити кошик у «Сільпо»");
  await expect(button).toBeEnabled();
});

test("кошик спорожнів у «Сільпо» — кнопка гасне на поверненні на вкладку (#89)", async ({
  page,
}) => {
  const silpo = await mockApi(page);
  await skipIntro(page);
  await enter(page);

  const button = page.locator('[data-tour="from-cart"]');
  await expect(button).toContainText("У кошику 7 позицій");

  silpo.emptyCart();
  await page.evaluate(() =>
    document.dispatchEvent(new Event("visibilitychange")),
  );

  await expect(page.locator('[data-tour="from-cart"]')).toHaveCount(0);
});

test("кошик спорожнів між читанням і кліком — відповідь для гостя, а не суперечність (#89)", async ({
  page,
}) => {
  const silpo = await mockApi(page);
  await skipIntro(page);
  await enter(page);

  const button = page.locator('[data-tour="from-cart"]');
  await expect(button).toContainText("У кошику 7 позицій");

  silpo.emptyCart();
  await button.click();

  const said = page.getByRole("alert");
  await expect(said).toContainText("кошик у «Сільпо» порожній", {
    timeout: 20_000,
  });
  await expect(said).toContainText(/Зібрати на тиждень/);
  await expect(said).not.toContainText("вхід");

  await expect(page.locator('[data-tour="from-cart"]')).toHaveCount(0);
});


test("введений список знімає «Кошик порожній» — і стирання його повертає (#74)", async ({
  page,
}) => {
  await mockApi(page, { cart: { rows: 0, total: 0, slot: null } });
  await skipIntro(page);
  await enter(page);

  const cart = page.locator('[data-tour="from-cart"]');
  const field = page.locator('[data-tour="list"] textarea');
  await expect(cart).toHaveCount(0);

  await page.getByRole("button", { name: "зі списку", exact: true }).click();
  await field.fill("хліб, молоко, чай");
  await expect(
    page.getByRole("button", { name: "Зібрати зі списку (3)" }),
  ).toBeVisible();
  await expect(cart).toHaveCount(0);

  await field.fill("");
  await expect(cart).toHaveCount(0);
});

test("повний кошик під списком важить рядок і каже ціну переходу (#74)", async ({
  page,
}) => {
  await openApp(page);

  const cart = page.locator('[data-tour="from-cart"]');
  await expect(cart).toContainText("перевір і доведи до дверей");

  await page.locator('[data-tour="list"] textarea').fill("хліб, молоко");
  await expect(cart).toContainText("У кошику 7 позицій");
  await expect(cart).toContainText("список не поїде");
  await expect(cart).not.toContainText("перевір і доведи до дверей");
  await expect(cart).toBeEnabled();
});

test("стеля, яка спрацювала, названа на екрані, а не лише в трейсі (#61)", async ({
  page,
}) => {
  await mockApi(page, {
    basket: {
      postponed: [
        {
          intent: "Кава Lavazza",
          reason:
            "закінчилось, але не влізло в звичний розмір кошика (14 поз.)",
          estimate: 245,
          refillable: true,
        },
        {
          intent: "Олія Monini",
          reason:
            "закінчилось, але не влізло в звичний розмір кошика (14 поз.)",
          estimate: 279,
          refillable: true,
        },
        {
          intent: "сир",
          reason:
            "двоякий намір понад стелю 3 питань — спитаю наступним прогоном",
          estimate: null,
          refillable: false,
        },
      ],
    },
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const week = page.locator('[data-tour="refill"]');
  await expect(week).toContainText("Кава Lavazza · Олія Monini");
  await expect(week.getByRole("button").first()).toContainText("ще 2 позиції");

  const block = page.locator('[data-tour="postponed"]');
  await expect(block).toContainText("Відкладено на наступний раз");
  await expect(block).toContainText("двоякий намір понад стелю");
  await expect(block).not.toContainText("Кава Lavazza");
});

test("відкладене -- список з причиною при кожному виді, а не абзац (#350)", async ({
  page,
}) => {
  const ceiling =
    "двоякий намір понад стелю 3 питань — спитаю наступним прогоном";
  const promo = "береш це по акції, а зараз її немає — чекаю акції";
  const missing = "закінчилось, але на цей слот у «Сільпо» його не знайшлось";
  const waiting = [
    "Авокадо Хасс стиглий",
    "Вода мінеральна Моршинська Спортик негазована",
    "Лохина",
    "Цибуля Марс",
    "Печериці свіжі",
  ];
  await mockApi(page, {
    basket: {
      postponed: [
        {
          intent: "Вершки Яготинські 15% т/б",
          reason: ceiling,
          estimate: null,
          refillable: false,
        },
        ...waiting.map((intent) => ({
          intent,
          reason: promo,
          estimate: 74,
          refillable: false,
        })),
        {
          intent: "Паляничка сирна",
          reason: missing,
          estimate: 39,
          refillable: false,
        },
      ],
      budget: 3000,
    },
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const block = page.locator('[data-tour="postponed"]');
  await expect(block).toContainText(`${promo} — 5`);
  await expect(block.locator("li.held-group > ul > li")).toHaveText(waiting);
  await expect(block).not.toContainText("·");

  const rows = block.locator("ul.held > li");
  await expect(rows).toHaveCount(3);
  await expect(rows.first()).toContainText("Вершки Яготинські 15% т/б");
  await expect(rows.first()).toContainText("спитаю наступним прогоном");
  await expect(rows.last()).toContainText("Паляничка сирна");
});

test("трейс не обіцяє скасування, якого немає, і не показує нуль у гривнях (#75, #76)", async ({
  page,
}) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page.getByRole("button", { name: "Що зробив агент" }).click();

  await expect(page.getByRole("button", { name: "Скасувати" })).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "копіювати крок" }).first(),
  ).toBeVisible();

  await expect(page.getByText("вартість прогону")).toHaveCount(0);
  await expect(page.getByText("токенів моделі")).toBeVisible();
  await expect(page.getByText("7972")).toBeVisible();
});

test("технічний журнал називає кеш шлюзу числом, і нуль теж відповідь (#291)", async ({
  page,
}) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page.getByRole("button", { name: "Що зробив агент" }).click();

  await expect(
    page.getByText("з кешу шлюзу — 4704 вхідних токенів з 6410"),
  ).toBeVisible();
});

test("промах кешу шлюзу каже про себе нулем, а не зникає з журналу (#291)", async ({
  page,
}) => {
  await mockApi(page, {
    basket: { stats: { ...basket().stats, tokensCached: 0 } },
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page.getByRole("button", { name: "Що зробив агент" }).click();

  await expect(
    page.getByText("з кешу шлюзу — 0 вхідних токенів з 6410"),
  ).toBeVisible();
});

test("вага без фасовки не рахується нулем, а ліміт слота не мовчить (#7)", async ({
  page,
}) => {
  const patched = basket().lines.map((line, index) =>
    index === 0
      ? { ...line, weightKg: null }
      : index === 1
        ? { ...line, weightKg: 5 }
        : line,
  );
  await mockApi(page, { basket: { lines: patched } });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await expect(page.locator(".facts")).toContainText("від ");
  await expect(page.locator(".summary")).toContainText(
    "без фасовки — ваги в картці немає",
  );

  const blocker = page.locator(".dock .blocker");
  await expect(blocker).toContainText("кур'єр бере до 30 кг");
  await expect(page.getByRole("button", { name: "Оформити" })).toBeEnabled();
});


const NARROW = { width: 390, height: 844 };

function narrowOnly(testInfo: { project: { name: string } }): void {
  test.skip(testInfo.project.name !== "mobile", "сітку міряємо на телефоні");
}

type Rect = { x: number; y: number; width: number; height: number };

/** Чи перетинаються два прямокутники. Один піксель дотику — ще не наїзд. */
function overlap(a: Rect, b: Rect): boolean {
  return (
    a.x + a.width > b.x + 1 &&
    b.x + b.width > a.x + 1 &&
    a.y + a.height > b.y + 1 &&
    b.y + b.height > a.y + 1
  );
}

/** Прямокутник елемента. `null` — елемента на екрані немає. */
async function box(page: Page, selector: string) {
  const found = page.locator(selector).first();
  if ((await found.count()) === 0) return null;
  return found.boundingBox();
}

test("кошик стоїть в ОДНІЙ сітці: жоден блок не ширший за список (#82)", async ({
  page,
}, testInfo) => {
  narrowOnly(testInfo);
  await page.setViewportSize(NARROW);
  await mockApi(page, { basket: { postponed: POSTPONED, budget: 3000 } });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const list = await box(page, "ul.list");
  expect(list, "без списку міряти нема від чого").not.toBeNull();

  for (const selector of [
    ".place",
    ".week",
    ".eco",
    ".swaps",
    ".swaps.decide",
    ".summary",
  ]) {
    const block = await box(page, selector);
    if (block === null) continue;
    expect(Math.round(block.x), `${selector}: лівий край`).toBe(
      Math.round(list!.x),
    );
    expect(Math.round(block.width), `${selector}: ширина`).toBe(
      Math.round(list!.width),
    );
  }
});

test("сума й дія в плашці ніколи не перекриваються (#82)", async ({
  page,
}, testInfo) => {
  narrowOnly(testInfo);
  await mockApi(page, {
    basket: {
      lines: TOPUP_ITEMS.map((line) => ({
        ...line,
        externalProductId: "demo-costly",
        name: "Кошик на місяць",
        price: 128_456.78,
      })),
    },
  });
  await skipIntro(page);
  await enter(page);

  for (const width of [320, 360, 390]) {
    await page.setViewportSize({ width, height: 780 });
    if (width === 320) {
      await buildWeek(page);
      await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
        timeout: 20_000,
      });
    }

    const sum = await box(page, ".dock-sum");
    const act =
      (await box(page, ".dock .checkout")) ??
      (await box(page, ".dock a.primary"));
    expect(sum, `${width}: плашка без суми`).not.toBeNull();
    expect(act, `${width}: плашка без дії`).not.toBeNull();
    expect(overlap(sum!, act!), `${width}: сума заходить під кнопку`).toBe(
      false,
    );

    const spill = await page
      .locator(".dock-sum .num")
      .evaluate((el) => el.scrollWidth - el.clientWidth);
    expect(
      spill,
      `${width}: число не влазить у свою колонку`,
    ).toBeLessThanOrEqual(1);
  }
});

test("після запису довга дія їде на свій рядок, а не тисне суму (#82)", async ({
  page,
}, testInfo) => {
  narrowOnly(testInfo);
  await page.setViewportSize({ width: 320, height: 780 });
  await mockApi(page);
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await checkout(page);
  await expect(page.getByRole("link", { name: /Підтвердити/ })).toBeVisible({
    timeout: 20_000,
  });

  const sum = await box(page, ".dock-sum");
  const act = await box(page, ".dock a.primary");
  expect(overlap(sum!, act!), "сума під посиланням").toBe(false);
  await expect(page.locator(".dock-note")).toContainText("11:00");
});

test("форма товару переживає обрізану назву і не мовчить у переліку замін (#102)", async ({
  page,
}) => {
  await mockApi(page);
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const row = page
    .locator("li.row")
    .filter({ hasText: "Хліб Київський житній" });
  await expect(row.locator(".form")).toHaveText("нарізаний");

  await row.evaluate((el) => el.scrollIntoView({ block: "center" }));
  await expect(row).toBeInViewport();
  await row.getByRole("button", { name: "Чому ця позиція тут" }).click();
  await expect(row.locator(".pop")).toContainText("7 без нарізки, 1 нарізаним");

  const milk = page.locator("li.row").filter({ hasText: "Молоко Селянське" });
  await expect(milk.locator(".form")).toHaveCount(0);
});

test("у переліку замін форма стоїть серед фактів, а не в кінці назви (#102)", async ({
  page,
}) => {
  await mockApi(page);
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page.locator("button.swaps").first().click();
  await revealRest(page);

  const card = page
    .locator("article.card")
    .filter({ hasText: "Хліб Київський житній" });
  await card.getByRole("button", { name: "+ Додати заміну" }).click();

  const picker = page.getByRole("dialog", { name: "Чим заміняти" });
  const sliced = picker
    .locator("li")
    .filter({ hasText: "Хліб Київський тостовий" });
  await expect(sliced.locator(".pick-facts")).toContainText("нарізаний");

  const water = picker.locator("li").filter({ hasText: "Поляна Квасова" });
  await expect(water.locator(".pick-facts")).not.toContainText("нарізаний");
});

test("мандат наперед не тисне вгору екрана і каже, звідки взявся (#87)", async ({
  page,
}) => {
  const ahead = LINES.map((line) =>
    line.externalProductId === "demo-milk"
      ? {
          ...line,
          mandate: "якщо немає — Молоко Яготинське 2,6%, інакше не брати",
          mandateAhead: true,
        }
      : line,
  );
  await mockApi(page, { basket: { lines: ahead } });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page.locator("button.swaps").first().click();
  await revealRest(page);

  const rest = page.locator('[data-testid="rest"] ~ article.card');
  await expect(rest.filter({ hasText: "Молоко Селянське 2,5%" })).toHaveCount(
    1,
  );

  const top = page.locator(".cards > article.card");
  await expect(top.first()).toContainText("Корм Club 4 Paws");
  await expect(top.nth(1)).toContainText("Йогурт Активіа");

  await expect(page.getByTestId("rest")).toContainText("із заміною напоготові");

  const milk = page
    .locator("article.card")
    .filter({ hasText: "Молоко Селянське 2,5%" });
  await expect(milk.locator(".mandate-cap")).toHaveText(
    "поїде збирачу -- готово наперед",
  );
  await expect(milk.locator(".mandate-text")).toContainText("Яготинське");

  const yogurt = page
    .locator("article.card")
    .filter({ hasText: "Йогурт Активіа" });
  await expect(yogurt.locator(".mandate-cap")).toHaveText("поїде збирачу");
});

test("погодження показує ВЕСЬ кошик, а не лише термінове (#128)", async ({
  page,
}) => {
  await mockApi(page);
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page.locator("button.swaps").first().click();
  const shown = LINES.filter((line) => line.reason !== "at_home");
  const urgent = shown.filter((line) => line.atRisk || line.needsApproval);
  await expect(page.locator("article.card")).toHaveCount(urgent.length);
  const reveal = page.getByTestId("reveal-rest");
  await expect(reveal).toContainText(
    `Показати решту кошика — ${shown.length - urgent.length}`,
  );
  await reveal.click();
  const bread = page
    .locator('[data-testid="rest"] ~ article.card')
    .filter({ hasText: "Хліб Київський житній" });
  await expect(bread.locator(".mandate-text")).toContainText("Хліб Дарницький");
  await expect(page.locator("article.card")).toHaveCount(shown.length);
  await expect(reveal).toHaveCount(0);

  await expect(page.locator(".group").first()).toHaveText(
    new RegExp(`^${urgent.length}.позиції просять рішення$`),
  );
  await expect(page.getByTestId("rest")).toContainText(
    new RegExp(`Решта кошика -- ${shown.length - urgent.length}`),
  );
});

test("без термінового екран не називає весь кошик рештою (#128)", async ({
  page,
}) => {
  const calm = LINES.map((line) => ({
    ...line,
    atRisk: false,
    needsApproval: false,
  }));
  await mockApi(page, { basket: { lines: calm } });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page.locator("button.swaps").first().click();
  await revealRest(page);

  const shown = calm.filter((line) => line.reason !== "at_home");
  await expect(page.locator("article.card")).toHaveCount(shown.length);
  await expect(page.getByTestId("rest")).toHaveText(
    new RegExp(`^Кошик -- ${shown.length},`),
  );
  await expect(page.getByText("Решта кошика")).toHaveCount(0);

  await expect(page.locator(".empty")).toContainText(
    "із заміною напоготові -- вони нижче",
  );
});

/**
 * Що вже лежить у кошику «Сільпо» поза цим планом (#30).
 *
 * Стан народжується МІЖ двома прогонами: перший записав 14 рядків, другий
 * зібрав 11 — і в кошику лишилось 14, бо `add_or_update_cart_products`
 * тільки додає.
 */
const LEFTOVERS = [
  { name: "Кава мелена 230 г", qty: 1, total: 189.9 },
  { name: "Печиво вівсяне 300 г", qty: 2, total: 84 },
];

async function toCheckout(page: Page, leftovers = LEFTOVERS): Promise<void> {
  await mockApi(page, { carryOver: leftovers });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await checkout(page);
}

test("кошик з минулого прогону питає вікном, а не тихо доливається (#30)", async ({
  page,
}) => {
  await toCheckout(page);

  const ask = page.getByRole("dialog", { name: "У кошику вже щось лежить" });
  await expect(ask).toBeVisible();
  await expect(ask).toContainText("Кава мелена 230 г");
  await expect(ask).toContainText("Печиво вівсяне 300 г");

  await expect(page.locator(".paid")).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "Підтвердити в «Сільпо»" }),
  ).toHaveCount(0);
});

test("«Доповнити» лишає чуже в кошику — і називає його у звіті (#30)", async ({
  page,
}) => {
  await toCheckout(page);
  await page.getByRole("button", { name: "Доповнити" }).click();

  await expect(
    page.getByText("Лишилось у кошику поза цим планом:"),
  ).toBeVisible();
  await expect(page.getByText("Кава мелена 230 г")).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Підтвердити в «Сільпо»" }),
  ).toBeVisible();
  await expect(
    page.getByRole("dialog", { name: "У кошику вже щось лежить" }),
  ).toHaveCount(0);
});

test("«Почати заново» знімає перелічене і каже про це словами (#30)", async ({
  page,
}) => {
  await toCheckout(page);
  await page.getByRole("button", { name: "Почати заново" }).click();

  await expect(page.getByText("Знято з кошика:")).toBeVisible();
  await expect(page.getByText("Печиво вівсяне 300 г")).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Підтвердити в «Сільпо»" }),
  ).toBeVisible();
});


const RULES_KEY = "komora:rules";

/** Другий пристрій — це той самий сервер і порожній браузер. */
async function elsewhere(page: Page): Promise<void> {
  await page.evaluate((key) => localStorage.removeItem(key), RULES_KEY);
  await reenter(page);
}

test("написане правило переживає порожній браузер (#45)", async ({ page }) => {
  await mockApi(page);
  await skipIntro(page);
  await enter(page);

  await page.getByRole("button", { name: "+ правило" }).click();
  const composer = page.getByRole("dialog", { name: "Своє правило" });
  await composer.getByRole("textbox").fill("без свинини");
  await composer.getByRole("button", { name: "Додати правило" }).click();
  await expect(
    page.getByRole("button", { name: "без свинини", exact: true }),
  ).toBeVisible();

  await elsewhere(page);

  await expect(
    page.getByRole("button", { name: "без свинини", exact: true }),
  ).toBeVisible();
});

test("видалене правило не повертається з сервера (#45)", async ({ page }) => {
  await mockApi(page);
  await skipIntro(page);
  await enter(page);

  await page
    .getByRole("button", { name: "Видалити правило «здоровіше»" })
    .click();
  await expect(
    page.getByRole("button", { name: "здоровіше", exact: true }),
  ).toHaveCount(0);

  await elsewhere(page);

  await expect(
    page.getByRole("button", { name: "здоровіше", exact: true }),
  ).toHaveCount(0);
});

test("правила зі старого браузера доїжджають на сервер самі (#45)", async ({
  page,
}) => {
  await mockApi(page, { rules: [] });
  await skipIntro(page);
  await page.addInitScript(
    ([key]: [string]) =>
      localStorage.setItem(
        key,
        JSON.stringify([
          { id: "rule:нічого в склі", label: "нічого в склі", active: true },
        ]),
      ),
    [RULES_KEY] as [string],
  );
  await enter(page);
  await expect(
    page.getByRole("button", { name: "нічого в склі", exact: true }),
  ).toBeVisible();

  await elsewhere(page);

  await expect(
    page.getByRole("button", { name: "нічого в склі", exact: true }),
  ).toBeVisible();
});

test("обмеження профілю «Сільпо» не вдає тумблер (#45)", async ({ page }) => {
  await mockApi(page, { profile: PROFILE_RULES });
  await skipIntro(page);
  await enter(page);

  await expect(page.getByText("без лактози")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "без лактози", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Видалити правило «без лактози»" }),
  ).toHaveCount(0);
});

test("сховище правил мовчить — це видно, а не порожньо (#45)", async ({
  page,
}) => {
  await mockApi(page, { rulesDown: true });
  await skipIntro(page);
  await page.addInitScript(
    ([key]: [string]) =>
      localStorage.setItem(
        key,
        JSON.stringify([
          {
            id: "rule:менше цукру",
            label: "менше цукру",
            active: true,
            pending: false,
          },
        ]),
      ),
    [RULES_KEY] as [string],
  );
  await enter(page);

  await expect(
    page.getByRole("button", { name: "менше цукру", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Показані правила з цього браузера"),
  ).toBeVisible();
});

test("правило, записане поки база мовчала, не зникає від сусідньої правки (#45)", async ({
  page,
}) => {
  const silpo = await mockApi(page);
  await skipIntro(page);
  await enter(page);
  await expect(
    page.getByRole("button", { name: "здоровіше", exact: true }),
  ).toBeVisible();

  silpo.breakRules();
  await page.getByRole("button", { name: "+ правило" }).click();
  const composer = page.getByRole("dialog", { name: "Своє правило" });
  await composer.getByRole("textbox").fill("нічого в склі");
  await composer.getByRole("button", { name: "Додати правило" }).click();
  await expect(page.getByText("поки лишилось у цьому браузері")).toBeVisible();

  silpo.healRules();
  await page
    .getByRole("button", { name: "Видалити правило «здоровіше»" })
    .click();
  await expect(
    page.getByRole("button", { name: "здоровіше", exact: true }),
  ).toHaveCount(0);

  await expect(
    page.getByRole("button", { name: "нічого в склі", exact: true }),
  ).toBeVisible();

  await reenter(page);
  await expect(
    page.getByRole("button", { name: "нічого в склі", exact: true }),
  ).toBeVisible();

  await elsewhere(page);
  await expect(
    page.getByRole("button", { name: "нічого в склі", exact: true }),
  ).toBeVisible();
});

test("часткова синхронізація не стирає недонесені правила (#119)", async ({
  page,
}) => {
  const silpo = await mockApi(page, { rules: [], ruleWritesDown: true });
  await skipIntro(page);
  await page.addInitScript(
    ([key]: [string]) =>
      localStorage.setItem(
        key,
        JSON.stringify([
          {
            id: "local:нічого в склі",
            label: "нічого в склі",
            active: true,
            pending: true,
          },
          {
            id: "local:менше цукру",
            label: "менше цукру",
            active: true,
            pending: true,
          },
        ]),
      ),
    [RULES_KEY] as [string],
  );
  await enter(page);

  await expect(
    page.getByRole("button", { name: "нічого в склі", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "менше цукру", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("поки лишилась у цьому браузері")).toBeVisible();

  await reenter(page);
  await expect(
    page.getByRole("button", { name: "нічого в склі", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "менше цукру", exact: true }),
  ).toBeVisible();

  silpo.healRuleWrites();
  await reenter(page);
  await expect(page.getByText("поки лишилась у цьому браузері")).toHaveCount(0);
  await elsewhere(page);
  await expect(
    page.getByRole("button", { name: "нічого в склі", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "менше цукру", exact: true }),
  ).toBeVisible();
});

test("невдала збірка лягає в список прогонів разом зі своїм запитом (#91)", async ({
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "desktop",
    "панель ховається на вузькому екрані",
  );
  await page.setViewportSize({ width: 1440, height: 900 });
  const silpo = await mockApi(page);
  await skipIntro(page);
  await enter(page);
  await page.keyboard.press("`");
  const panel = page.getByRole("complementary", { name: "Панель дебагу" });

  silpo.breakBuild(502, "модель не відповіла вчасно");
  await buildWeek(page);
  await expect(page.getByRole("alert")).toContainText(
    "модель не відповіла вчасно",
  );

  await expect(panel.getByText("прогони · 1")).toBeVisible();
  const runs = panel.locator("article.run");
  await expect(runs).toHaveCount(1);
  await expect(runs.first()).toContainText("збірка — не вдалась");
  await expect(runs.first()).toContainText("502");
  await expect(runs.first()).toContainText("модель не відповіла вчасно");

  await expect(
    runs.first().locator("details", { hasText: "відповідь" }),
  ).toHaveCount(0);

  await runs
    .first()
    .locator("details", { hasText: "запит" })
    .first()
    .locator("summary")
    .click();
  await expect(runs.first().locator("pre").first()).toContainText('"delivery"');

  silpo.healBuild();
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await expect(panel.getByText("прогони · 2")).toBeVisible();
  await expect(runs).toHaveCount(2);
  await expect(runs.first()).toContainText("первинний збір");
  await expect(runs.last()).toContainText("збірка — не вдалась");
  await expect(panel.getByText("на екрані")).toHaveCount(1);
});

test("відповідь, яка не доїхала, названа так, а не вигаданим кодом (#91)", async ({
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "desktop",
    "панель ховається на вузькому екрані",
  );
  await page.setViewportSize({ width: 1440, height: 900 });
  const silpo = await mockApi(page);
  await skipIntro(page);
  await enter(page);
  await page.keyboard.press("`");
  const panel = page.getByRole("complementary", { name: "Панель дебагу" });

  silpo.breakBuild(null);
  await buildWeek(page);
  await expect(page.getByRole("alert")).toBeVisible();

  const runs = panel.locator("article.run");
  await expect(runs).toHaveCount(1);
  await expect(runs.first()).toContainText("не доїхало");
});

test("стеля списку прогонів називає себе, а номери не збиваються (#91)", async ({
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "desktop",
    "панель ховається на вузькому екрані",
  );
  await page.setViewportSize({ width: 1440, height: 900 });
  const silpo = await mockApi(page);
  await skipIntro(page);
  await enter(page);
  await page.keyboard.press("`");
  const panel = page.getByRole("complementary", { name: "Панель дебагу" });

  silpo.breakBuild(500, "сервер спіткнувся");
  await page.getByRole("button", { name: "на тиждень", exact: true }).click();
  const start = page.getByRole("button", { name: /^Зібрати / });
  for (let attempt = 1; attempt <= 7; attempt += 1) {
    await start.click();
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(panel.getByText(`прогони · ${attempt}`)).toBeVisible();
  }

  const runs = panel.locator("article.run");
  await expect(runs).toHaveCount(6);
  await expect(
    panel.getByText("показані останні 6 · ще 1 прогін витіснено"),
  ).toBeVisible();

  await expect(runs.last().locator(".seq")).toHaveText("#2");
  await expect(runs.first().locator(".seq")).toHaveText("#7");
});

test("«взяв більше за звичне» комора тримає, а не зводить до звичного (#103)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const row = page
    .locator("li.row")
    .filter({ hasText: "Тунець консервований" });
  await row.getByRole("button", { name: "вже купив" }).click();

  const ask = page.getByRole("dialog", { name: "Скільки взяв" });
  await expect(ask).toContainText("звично береш 1 шт");
  await expect(ask).not.toContainText("комора поки не веде");

  const four = ask.getByRole("button", { name: /^4 шт/ });
  await expect(four).not.toContainText("на ~");
  await expect(
    ask.getByRole("button", { name: /на скільки тобі цього вистачає/ }),
  ).toBeVisible();
  await four.click();

  await expect(row).not.toContainText("мабуть, закінчилось");
  await expect(row).toContainText("ще ~56 дн");
  await expect(row).toContainText("удома ~4 шт");
});

test("назване гостем число повертає горизонт у вікно (#144)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const row = page
    .locator("li.row")
    .filter({ hasText: "Тунець консервований" });
  await row
    .getByRole("button", { name: /сказати, на скільки вистачає/ })
    .click();
  await page
    .getByRole("dialog", { name: "На скільки вистачає" })
    .getByRole("button", { name: "на тиждень" })
    .click();

  await expect(row).toContainText("вистачає на ~7 дн");

  await row.getByRole("button", { name: "вже купив" }).click();
  const ask = page.getByRole("dialog", { name: "Скільки взяв" });
  await expect(ask.getByRole("button", { name: /^4 шт/ })).toContainText(
    "на ~28 дн",
  );
});

test("рядок із запасом наперед не сперечається з власним циклом (#103)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const row = page
    .locator("li.row")
    .filter({ hasText: "Тунець консервований" });
  await row.getByRole("button", { name: "вже купив" }).click();
  await page
    .getByRole("dialog", { name: "Скільки взяв" })
    .getByRole("button", { name: /^3 шт/ })
    .click();

  await expect(row).toContainText("запас понад цикл ~14 дн");
  const bar = row.getByRole("progressbar");
  await expect(bar).toHaveAttribute("aria-valuenow", "100");
});

test("запас наперед не заважає сказати, що взяв МЕНШЕ (#103, #99)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const row = page.locator("li.row").filter({ hasText: "Йогурт питний" });
  await row.getByRole("button", { name: "вже купив" }).click();

  const ask = page.getByRole("dialog", { name: "Скільки взяв" });
  await expect(ask.getByRole("button", { name: /^\d/ })).toHaveCount(6);
  await ask.getByRole("button", { name: /^2 шт/ }).click();

  await expect(row).toContainText("удома ~2 шт");
  await expect(row).toContainText("ще ~4 дн");
});

test("стеля прогонів називає себе числами і лишає дію (#34)", async ({
  page,
}) => {
  await mockApi(page, { quota: { ...QUOTA, left: 2 } });
  await skipIntro(page);
  await enter(page);

  await expect(
    page.getByText("прогонів: 1 з 6 у цій сесії, 3 з 12 за добу"),
  ).toBeVisible();
  await page.getByRole("button", { name: "на тиждень", exact: true }).click();
  await expect(page.getByRole("button", { name: /^Зібрати / })).toBeEnabled();
});

test("поки стеля далеко, її числа мовчать (#34, живий тест 07.09)", async ({
  page,
}) => {
  await mockApi(page);
  await skipIntro(page);
  await enter(page);

  await page.getByRole("button", { name: "на тиждень", exact: true }).click();
  await expect(page.getByRole("button", { name: /^Зібрати / })).toBeEnabled();
  await expect(page.getByText("прогонів:")).toHaveCount(0);
});

test("вичерпана стеля гасить обидві кнопки і каже, що робити (#34)", async ({
  page,
}) => {
  await mockApi(page, { quota: QUOTA_SPENT });
  await skipIntro(page);
  await enter(page);

  await expect(
    page.getByText("на сьогодні стеля прогонів вичерпана: 12 з 12"),
  ).toBeVisible();
  await expect(page.getByText("оновиться опівночі за Києвом")).toBeVisible();
  await expect(page.getByText("Комора і решта екранів працюють")).toBeVisible();
  await expect(
    page.getByRole("link", {
      name: "https://github.com/mykhailoklimnyk/pantry/issues",
    }),
  ).toBeVisible();

  await page.getByRole("button", { name: "на тиждень", exact: true }).click();
  await expect(page.getByRole("button", { name: /^Зібрати / })).toBeDisabled();
  await expect(
    page.getByRole("button", { name: /доведи до дверей/ }),
  ).toBeDisabled();
});

test("комора лишається робочою під вичерпаною стелею (#34)", async ({
  page,
}) => {
  await mockApi(page, { quota: QUOTA_SPENT });
  await skipIntro(page);
  await page.goto("/");

  await expect(page.getByTestId("pantry-screen")).toBeVisible();
  await expect(page.locator("li.row").first()).toBeVisible();
});

test("чип режиму і степер людей доїжджають у запит, а не лише в текст (#132)", async ({
  page,
}) => {
  const sent: Record<string, unknown>[] = [];
  await mockApi(page, { onBuild: (body) => sent.push(body) });
  await skipIntro(page);
  await enter(page);

  await page.getByRole("button", { name: "подія", exact: true }).click();
  await page.getByRole("button", { name: "Більше людей" }).click();

  await page.getByRole("button", { name: "Зібрати на подію" }).click();
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  expect(sent.at(-1)?.mode).toBe("event");
  expect(sent.at(-1)?.occasionPeople).toBe(5);
});

test("режим без приводу не возить чужого числа (#132, #284)", async ({
  page,
}) => {
  const sent: Record<string, unknown>[] = [];
  await mockApi(page, { onBuild: (body) => sent.push(body) });
  await skipIntro(page);
  await enter(page);

  await page.getByRole("button", { name: "на тиждень", exact: true }).click();
  await expect(page.getByRole("button", { name: "Більше людей" })).toHaveCount(
    0,
  );

  await page.getByRole("button", { name: /^Зібрати / }).click();
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  expect(sent.at(-1)?.mode).toBe("week");
  expect(sent.at(-1)?.occasionPeople).toBeNull();
});

test("три режими — три назви кнопки, і кожна називає СВОЮ роботу (#284)", async ({
  page,
}) => {
  const sent: Record<string, unknown>[] = [];
  await mockApi(page, { onBuild: (body) => sent.push(body) });
  await skipIntro(page);
  await enter(page);

  await expect(
    page.getByRole("button", { name: /Зібрати на тиждень на/ }),
  ).toBeEnabled();

  await page.getByRole("button", { name: "подія", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Зібрати на подію" }),
  ).toBeEnabled();

  await page.getByRole("button", { name: "зі списку", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Зібрати зі списку" }),
  ).toBeDisabled();
  await page.getByPlaceholder(/молоко/i).fill("молоко, хліб");
  await page.getByRole("button", { name: "Зібрати зі списку (2)" }).click();
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  expect(sent.at(-1)?.mode).toBe("list");
});

test("рядок без доведеного циклу не малює смуги і не каже «закінчилось» (#133)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const rare = page.locator("li.row").filter({ hasText: "Кетчуп" });
  await expect(
    rare.getByText(/береш нерівно: між покупками від 2 до 68 дн/),
  ).toBeVisible();
  await expect(rare.getByRole("progressbar")).toHaveCount(0);
  await expect(rare.getByText("закінчилось")).toHaveCount(0);
  await expect(rare.getByRole("button", { name: "вже купив" })).toHaveCount(0);
});

test("вид, який мовчить два з половиною цикли, каже саме це (#133)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const silent = page.locator("li.row").filter({ hasText: "Морозиво" });
  await expect(
    silent.getByText(/давно не брав: 76 дн при звичних ~32/),
  ).toBeVisible();
  await expect(silent.getByText("мабуть, закінчилось")).toHaveCount(0);
  await expect(silent.getByRole("button", { name: "вже купив" })).toBeVisible();
});

test("старт не обіцяє нагляду за тим, у чого немає циклу (#133)", async ({
  page,
}) => {
  await openApp(page);

  await expect(page.getByText(/10 видів, 9 під наглядом/)).toBeVisible();
});


test("три дотики по «+» дають +3, а не +1 (#145)", async ({ page }) => {
  const sent: number[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/pantry") && request.method() === "PATCH") {
      sent.push((request.postDataJSON() as { qty: number }).qty);
    }
  });

  await openApp(page, { pantryWrite: "slow" });
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const row = page.locator("li.row").filter({ hasText: "Рис" });
  const plus = row.getByRole("button", { name: "Більше: Рис" });
  await plus.click();
  await plus.click();
  await plus.click();

  await expect(row.locator(".qty")).toHaveText("5 уп");
  await expect(row.locator(".state")).not.toHaveClass(/stale/, {
    timeout: 5000,
  });
  expect(sent).toEqual([5]);
});

test("поки слово гостя їде, стан рядка не вдає, що вже перерахований (#145)", async ({
  page,
}) => {
  await openApp(page, { pantryWrite: "slow" });
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const row = page.locator("li.row").filter({ hasText: "Рис" });
  await expect(row.locator(".state")).not.toHaveClass(/stale/);

  await row.getByRole("button", { name: "Більше: Рис" }).click();

  await expect(row.locator(".state")).toHaveClass(/stale/);
  await expect(row.locator(".state")).not.toHaveClass(/stale/, {
    timeout: 5000,
  });
});

test("слово гостя не переставляє список під його ж пальцем (#145)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const rows = page.locator("li.row");
  const names = rows.locator(".name");
  const before = await names.allInnerTexts();
  const tuna = rows.filter({ hasText: "Тунець консервований" });
  await expect(tuna).toContainText("мабуть, закінчилось");

  await tuna.getByRole("button", { name: "вже купив" }).click();
  await page
    .getByRole("dialog", { name: "Скільки взяв" })
    .getByRole("button", { name: "просто купив" })
    .click();

  await expect(tuna).not.toContainText("мабуть, закінчилось");
  expect(await names.allInnerTexts()).toEqual(before);
});

test("слово, яке не доїхало, зникає з екрана і називає себе (#145)", async ({
  page,
}) => {
  await openApp(page, { pantryWrite: "dead" });
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const row = page.locator("li.row").filter({ hasText: "Рис" });
  await expect(row.locator(".qty")).toHaveText("2 уп");

  await row.getByRole("button", { name: "Більше: Рис" }).click();

  await expect(page.getByText(/не вдалось запам/)).toBeVisible();
  await expect(row.locator(".qty")).toHaveText("2 уп");
  await expect(
    page
      .locator("li.row")
      .filter({ hasText: "Туалетний папір" })
      .locator(".qty"),
  ).toHaveText("6 рул");
});

test("«вже купив» більше не гасне на час запиту (#145)", async ({ page }) => {
  await openApp(page, { pantryWrite: "slow" });
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const row = page
    .locator("li.row")
    .filter({ hasText: "Тунець консервований" });
  await row.getByRole("button", { name: "вже купив" }).click();
  await page
    .getByRole("dialog", { name: "Скільки взяв" })
    .getByRole("button", { name: "просто купив" })
    .click();

  const already = row.locator("button.already");
  await expect(already).toHaveText("…");
  await expect(already).toBeEnabled();
});

function sum(text: string): number {
  return Number(text.replace(/[^\d,]/g, "").replace(",", "."));
}

test("трейс відмінює число рішень: «5 рішень», а не «5 рішення» (#173)", async ({
  page,
}) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page.getByRole("button", { name: "Що зробив агент" }).click();

  const lede = page.locator(".lede");
  await expect(lede).toContainText("Агент ухвалив 6 рішень");
  await expect(lede).not.toContainText("6 рішення");
});

test("одне рішення в трейсі не ламає речення (#173)", async ({ page }) => {
  const single = basket()
    .trace.filter((step) => step.decision)
    .slice(0, 1);
  await openApp(page, { basket: { trace: single } });
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page.getByRole("button", { name: "Що зробив агент" }).click();

  await expect(page.locator(".lede")).toContainText(
    "Агент ухвалив 1 рішення, збираючи твій кошик",
  );
});

test("три числа блоку межі сходяться між собою (#173)", async ({ page }) => {
  await openApp(page, { basket: { budget: 3000 } });
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const note =
    (await page
      .locator('[data-tour="refill"] .week-note')
      .first()
      .textContent()) ?? "";
  const parts = note.match(
    /бракує\s*([\d\s,]+)₴\s*до нижньої межі\s*([\d\s,]+)₴\s*\(ціль\s*([\d\s,]+)₴/,
  );
  expect(parts, `рядок межі: ${note}`).not.toBeNull();
  const [short, low, goal] = parts!.slice(1).map(sum);
  const total = sum((await page.locator(".sum").first().textContent()) ?? "");

  expect(low).toBe(Math.round(goal! * 0.9));
  expect(short).toBe(low! - total);
});

test("банер перебору називає ту межу, від якої рахує різницю (#173)", async ({
  page,
}) => {
  await openApp(page, { basket: { budget: 300 } });
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const over = page
    .locator(".missed")
    .filter({ hasText: "Вище верхньої межі на" });
  const head = sum((await over.locator("strong").textContent()) ?? "");
  const why = (await over.locator(".why").textContent()) ?? "";
  const pair = why.match(
    /([\d\s,]+)₴\s*проти\s*([\d\s,]+)₴\s*— це ціль\s*([\d\s,]+)₴/,
  );
  expect(pair, `пояснення перебору: ${why}`).not.toBeNull();
  const [total, high, goal] = pair!.slice(1).map(sum);

  expect(high).toBe(Math.round(goal! * 1.1));
  expect(head).toBeCloseTo(total! - high!, 2);
});

test("кошик вище коридору не звітує «вже в межах цілі» (#173)", async ({
  page,
}) => {
  await openApp(page, { basket: { postponed: POSTPONED, budget: 300 } });
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await expect(
    page.locator(".missed").filter({ hasText: "Вище верхньої межі на" }),
  ).toBeVisible();

  const week = page.locator('[data-tour="refill"]');
  await expect(week).not.toContainText("в межах цілі");
  await expect(week).toContainText("вище верхньої межі 330 ₴ на");
});

test("порожній кошик не пропонує кнопки, яка нічого не робить (#165)", async ({
  page,
}) => {
  await openApp(page, { basket: { lines: [] } });
  await buildWeek(page);

  const empty = page.locator(".empty");
  await expect(empty).toBeVisible({ timeout: 20_000 });
  await expect(page.getByRole("button", { name: /Написати/ })).toHaveCount(0);
  await expect(empty.locator("button")).toHaveCount(1);
  await expect(
    empty.getByRole("button", { name: "Зібрати ще раз" }),
  ).toBeVisible();
  await expect(empty).not.toContainText("напишіть, що саме не так");

  await expect(empty).not.toContainText("ви все видалили");
  await expect(empty.getByRole("heading")).toHaveText(
    "Збірка не дала жодного рядка",
  );
  await expect(empty).toContainText("Ціль зараз");
});

test("кнопка про весь кошик називає те, що робить (#186)", async ({ page }) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const clear = page.getByRole("button", { name: "Усе вже вдома" });
  await expect(clear).toBeVisible();
  await clear.click();
  await expect(
    page.getByRole("button", { name: "Точно, усе вдома?" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Точно, усе вдома?" }).click();

  await expect(page.locator(".empty")).toHaveCount(0);
  await expect(page.getByText("схоже, ще є вдома").first()).toBeVisible();
});

test("дві швидкі правки поспіль -- і жодна не гине мовчки (#174)", async ({
  page,
}) => {
  await openApp(page);
  await buildWeek(page);
  const rows = page.locator("li.row");
  await expect(rows.first()).toBeVisible();

  const first = LINES[0]!.name;
  const second = LINES[1]!.name;
  await page.evaluate(
    ([one, two]) => {
      const press = (label: string) =>
        document
          .querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`)
          ?.click();
      press(one as string);
      press(two as string);
    },
    [`Прибрати ${first}`, `Прибрати ${second}`],
  );

  await expect(
    page.getByRole("button", { name: `Додати ${first}` }),
  ).toBeVisible({ timeout: 15_000 });
  await expect(
    page.getByRole("button", { name: `Додати ${second}` }),
  ).toBeVisible({ timeout: 15_000 });
});

test("той самий товар під двома намірами не валить увесь кошик", async ({
  page,
}) => {
  await openApp(page, { basket: { lines: [...LINES, { ...LINES[0]! }] } });
  await buildWeek(page);

  const rows = page.locator("li.row");
  await expect(rows.first()).toBeVisible();
  await expect(rows).toHaveCount(LINES.length);
  await expect(rows.filter({ hasText: LINES[0]!.name })).toHaveCount(1);
});

test("блок над списком не злипається з першим рядком", async ({ page }) => {
  await mockApi(page, { basket: { unresolved: ["свинина"] } });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const missed = await page.locator(".missed").first().boundingBox();
  const list = await page.locator(".list").first().boundingBox();
  expect(missed).not.toBeNull();
  expect(list).not.toBeNull();
  expect(list!.y - (missed!.y + missed!.height)).toBeGreaterThanOrEqual(10);
});

test("обведені блоки над списком не торкаються його рамки (#127)", async ({
  page,
}) => {
  await mockApi(page, {
    basket: {
      budget: 300,
      trimmed: [
        {
          intent: "Кава Lavazza",
          name: "Кава Lavazza Crema e Gusto",
          price: 245,
          reason: "цього тижня можна пропустити — брав два тижні тому",
        },
      ],
    },
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const gaps = await page.evaluate(() => {
    const boxes = [...document.querySelectorAll<HTMLElement>(".missed, .list")];
    return boxes.slice(1).map((el, i) => ({
      after: (boxes[i]!.textContent || "").slice(0, 24),
      gap: Math.round(
        el.getBoundingClientRect().top -
          boxes[i]!.getBoundingClientRect().bottom,
      ),
    }));
  });

  expect(
    gaps.length,
    "на екрані мусять бути обидва стани і список",
  ).toBeGreaterThan(1);
  for (const { after, gap } of gaps) {
    expect(
      gap,
      `після «${after}» блоки злиплись у одну фігуру`,
    ).toBeGreaterThanOrEqual(8);
  }
});

test("«Додати ще» в кошику чує голос, і надиктоване лягає в ПОЛЕ (#129)", async ({
  page,
}) => {
  await stubSpeech(page);
  await mockApi(page);
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const field = page.locator(".week-add input");
  await expect(field).toHaveValue("");

  await page.getByRole("button", { name: "надиктувати, що додати" }).click();
  await expect(page.getByRole("dialog", { name: "Диктування" })).toBeVisible();
  await page.evaluate(() => (window as any).__say("халва і родзинки", true));
  await page.getByRole("button", { name: /Готово — додати/ }).click();

  await expect(field).toHaveValue("Халва, Родзинки");
  await expect(
    page
      .locator(".week-add")
      .getByRole("button", { name: "Додати", exact: true }),
  ).toBeEnabled();
  await expect(field).toHaveValue("Халва, Родзинки");
});

test("надиктоване ДОПИСУЄТЬСЯ до набраного, а не затирає його (#129)", async ({
  page,
}) => {
  await stubSpeech(page);
  await mockApi(page);
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const field = page.locator(".week-add input");
  await field.fill("сметана");
  await page.getByRole("button", { name: "надиктувати, що додати" }).click();
  await page.evaluate(() => (window as any).__say("гречка", true));
  await page.getByRole("button", { name: /Готово — додати/ }).click();

  await expect(field).toHaveValue("сметана, Гречка");
});

test("число з вікна «скільки взяв» стоїть на екрані ще до відповіді сервера (#191)", async ({
  page,
}) => {
  await openApp(page, { pantryWrite: "slow" });
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const row = page.locator("li.row").filter({ hasText: "Йогурт питний" });
  await row.getByRole("button", { name: "вже купив" }).click();
  await page
    .getByRole("dialog", { name: "Скільки взяв" })
    .getByRole("button", { name: /^2/ })
    .click();

  await expect(row.locator(".qty")).toHaveText("2 шт", { timeout: 1000 });
  await expect(row.locator(".state")).toHaveClass(/stale/);
});

test("«просто купив» без числа не вигадує кількості (#191)", async ({
  page,
}) => {
  await openApp(page, { pantryWrite: "slow" });
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const row = page.locator("li.row").filter({ hasText: "Морозиво" });
  const before = await row.locator(".qty").count();
  await row.getByRole("button", { name: "вже купив" }).click();

  await expect(row).not.toContainText("з твоїх слів удома");
  expect(await row.locator(".qty").count(), "кількість узялась нізвідки").toBe(
    before,
  );
});

test("близнюки одного наміру стоять під одним заголовком, і гість може їх розділити (#335)", async ({
  page,
}) => {
  await openApp(page, { pantry: "twins" });
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const rows = page.locator("li.row, li.band");
  const band = page.locator("li.band").filter({ hasText: "сир" });
  await expect(band).toContainText(/2\s+назви з чеків/);
  await expect(band).toContainText("1 закінчується");

  const order = await rows.allTextContents();
  const head = order.findIndex((text) => /2\s+назви з чеків/.test(text));
  expect(head, "заголовка немає в переліку").toBeGreaterThanOrEqual(0);
  expect(order[head + 1]).toContain("сир · твердий");
  expect(order[head + 2]).toContain("сир · вершковий");

  await expect(
    page.locator("li.row").filter({ hasText: "сир · твердий" }),
  ).toContainText("цикл ~6 дн");
  await expect(
    page.locator("li.row").filter({ hasText: "сир · вершковий" }),
  ).toContainText("цикл ~21 дн");

  await band.getByRole("button", { name: /Розділити/ }).click();
  await expect(page.locator("li.band").filter({ hasText: "сир" })).toHaveCount(
    0,
  );
  await expect(
    page.locator("li.row").filter({ hasText: "сир · твердий" }),
  ).toBeVisible();

  const hard = page.locator("li.row").filter({ hasText: "сир · твердий" });
  await expect(hard.locator(".parts")).toHaveCount(0);
  await hard.getByRole("button", { name: /докладніше|згорнути/ }).click();
  const under = hard.locator(".parts li");
  await expect(under).toHaveCount(2);
  await expect(under.first()).toContainText("Сир Комо Гауда 45%");
  await expect(under.first()).toContainText("9 дн тому");
  await expect(under.first()).toHaveClass(/fresh/);
  await expect(under.last()).not.toHaveClass(/fresh/);

  const note = page.locator(".hidden-note").filter({ hasText: "не зводжу" });
  await expect(note).toContainText("сир");
  await note.getByRole("button", { name: /Звести/ }).click();
  await expect(
    page.locator("li.band").filter({ hasText: "сир" }),
  ).toBeVisible();
});

test("з рядка комори є дорога в список на наступну покупку (#338)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const row = page
    .locator("li.row")
    .filter({ hasText: "Тунець консервований" });
  await expect(row).toBeVisible();
  await expect(row.getByText("у списку на покупку")).toHaveCount(0);

  await row.getByRole("button", { name: /У список на покупку/ }).click();

  await expect(row.getByText("у списку на покупку")).toBeVisible();
  await expect(
    row.getByRole("button", { name: /У список на покупку/ }),
  ).toHaveCount(0);

  await page.getByRole("button", { name: "На початок" }).last().click();
  await expect(
    page.getByLabel("Прибрати зі списку: Тунець консервований"),
  ).toBeVisible();

  await reenter(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();
  await expect(
    page
      .locator("li.row")
      .filter({ hasText: "Тунець консервований" })
      .getByText("у списку на покупку"),
  ).toBeVisible();
});

test("вид, який гість не хоче бачити, зникає з комори і називає себе (#124)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const row = page.locator("li.row").filter({ hasText: "Йогурт питний" });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: /Не показувати/ }).click();

  await expect(
    page.locator("li.row").filter({ hasText: "Йогурт питний" }),
  ).toHaveCount(0);
  const note = page.locator(".hidden-note");
  await expect(note).toContainText("ти прибрав з обліку 1");
  await expect(note).toContainText("Йогурт питний");

  await note.getByRole("button", { name: /Повернути/ }).click();
  await expect(
    page.locator("li.row").filter({ hasText: "Йогурт питний" }),
  ).toBeVisible();
});

test("«не показуй» і «вже купив» -- різні осі, і кнопки різні (#124)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const row = page.locator("li.row").filter({ hasText: "Йогурт питний" });
  await expect(row.getByRole("button", { name: "вже купив" })).toBeVisible();
  await expect(
    row.getByRole("button", { name: /Не показувати/ }),
  ).toBeVisible();
});

test("рядок бару каже ФАСОВКУ, у межах якої порахована вилка (#256)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: "що з напоїв удома" }).click();
  await expect(page.getByRole("heading", { name: "Бар" })).toBeVisible();

  const vodka = page.locator("li.row").filter({ hasText: "Горілка" }).first();
  await expect(vodka).toContainText("0,5л");
  await expect(vodka).toContainText("брав 0,5л за");
});

test("адресу можна назвати з кошика і тоді, коли її ще немає (#253)", async ({
  page,
}) => {
  await openApp(page, { placeDown: true });
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const door = page.getByRole("button", { name: /Адресу ще не знаю/ });
  await expect(door).toBeVisible();
  await door.click();

  await expect(page.getByRole("dialog", { name: "Куди веземо" })).toBeVisible();
});

test("вікно додавання в комору пропонує ВИДИ, а не товари (#257)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();
  await page.getByRole("button", { name: "+ Додати" }).click();

  const add = page.getByRole("dialog", { name: "Додати в комору" });
  await expect(add).toBeVisible();
  await expect(add.getByPlaceholder(/вид, а не марка/)).toBeVisible();
  await expect(
    add.getByRole("button", { name: "Мед акацієвий" }),
  ).toBeVisible();
  await expect(add.getByRole("button", { name: /Сквирянка/ })).toHaveCount(0);
});

test("у режимі «веду сам» приклади беруться з ЙОГО покупок (#257, #26)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();
  await openListSettings(page);
  await page.getByRole("button", { name: "веду сам" }).click();
  await expect(page.getByText(/У покупках є ще/)).toBeVisible();

  await page.getByRole("button", { name: "+ Додати" }).click();
  const add = page.getByRole("dialog", { name: "Додати в комору" });
  await expect(add.getByRole("button", { name: "гречка" })).toHaveCount(0);
  await expect(add.locator("button.hint").first()).toBeVisible();
});

test("дотик по чипу уточнення не перерішує весь кошик (#244)", async ({
  page,
}) => {
  const builds: string[] = [];
  page.on("request", (request) => {
    const url = request.url();
    if (
      request.method() === "POST" &&
      url.includes("/api/basket") &&
      !url.includes("/refill")
    ) {
      builds.push(url);
    }
  });

  await openApp(page, { basket: { questions: [CHEESE] } });
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const ask = page.locator(".ask");
  await expect(ask).toBeVisible();
  const before = builds.length;

  await ask.getByRole("button", { name: /Сир кисломолочний/ }).click();

  await expect(page.locator(".ask")).toHaveCount(0, { timeout: 20_000 });
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible();
  expect(builds.length, "чип уточнення замовив повну перезбірку").toBe(before);
});

test("«не треба» знімає питання БЕЗ повної перезбірки (#190)", async ({
  page,
}) => {
  const builds: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/basket") && request.method() === "POST") {
      builds.push(request.url());
    }
  });

  await mockApi(page, { basket: { questions: [CHEESE] } });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const ask = page.locator(".ask");
  await expect(ask).toBeVisible();
  const before = builds.length;

  await ask.getByRole("button", { name: "не треба" }).click();

  await expect(page.locator(".ask")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible();
  expect(builds.length, "«не треба» замовило повну перезбірку").toBe(before);
});

test("зниклий вид бару називає СВОЮ причину, а не чужий поріг (#182)", async ({
  page,
}) => {
  await test.step("зник ОДИН вид з кількох -- рядок поруч зі списком", async () => {
    await mockApi(page, { bar: BAR_DROPPED });
    await skipIntro(page);
    await enter(page);
    await page.getByRole("button", { name: "подія", exact: true }).click();
    await page.getByRole("button", { name: /Напої до приводу/ }).click();
    await expect(page.getByText(/Ще\s+2\s+види не показано/)).toBeVisible();
    await expect(page.getByText(/ні ціни, ні дати покупки/)).toBeVisible();
    await expect(page.getByText(/з 3-ї покупки/)).toHaveCount(0);
  });
});

test("порожній бар зі знятими видами не звинувачує поріг покупок (#182)", async ({
  page,
}) => {
  await mockApi(page, { bar: BAR_ONLY_DROPPED });
  await skipIntro(page);
  await enter(page);
  await page.getByRole("button", { name: "подія", exact: true }).click();
  await page.getByRole("button", { name: /Напої до приводу/ }).click();

  await expect(
    page.getByText(/Напої в чеках є, але показати їх нема з чим/),
  ).toBeVisible();
  await expect(page.getByText(/з 3-ї покупки/)).toHaveCount(0);
  await expect(page.getByText(/Серед звичного напоїв поки немає/)).toHaveCount(
    0,
  );
});

test("питання без варіантів дає відповіддю самі товари — з цінами (#190)", async ({
  page,
}) => {
  await mockApi(page, { basket: { questions: [CHERRY] } });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const ask = page.locator(".ask");
  await expect(ask).toContainText("Обирати конкретний сорт");

  const picks = ask.locator(".picks li");
  await expect(picks).toHaveCount(2);
  await expect(picks.first()).toContainText("Томат Гордій Черрі");
  await expect(picks.first()).toContainText("71,99");
  await expect(picks.first()).not.toContainText("від");
  await expect(picks.nth(1)).toContainText("154");
  await expect(picks.first()).toContainText("250г");

  await expect(ask.getByRole("button", { name: "інше" })).toBeVisible();
  await expect(ask.getByRole("button", { name: "не треба" })).toBeVisible();
});

test("дотик по товару ДОДАЄ його, а не замовляє перезбірку (#190)", async ({
  page,
}) => {
  const builds: string[] = [];
  const picked: Record<string, unknown>[] = [];
  page.on("request", (request) => {
    const url = request.url();
    if (request.method() !== "POST") return;
    if (url.endsWith("/api/basket")) builds.push(url);
    if (url.includes("/pick")) picked.push(request.postDataJSON());
  });

  await mockApi(page, { basket: { questions: [CHERRY] } });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  const before = builds.length;

  await page.locator(".ask .picks li button").first().click();

  await expect.poll(() => picked.length, { timeout: 10_000 }).toBe(1);
  expect(picked[0]).toEqual({
    intent: "Томат La Parcela Черрі Angello",
    externalProductId: "9001",
  });
  expect(builds.length, "дотик по товару замовив повну перезбірку").toBe(
    before,
  );
});

test("модель на ключі гостя питає ключ, а не мовчки їде на нашій (#197)", async ({
  page,
}) => {
  await mockApi(page);
  await skipIntro(page);
  await enter(page);

  await page.locator(".models .pill").click();
  const menu = page.locator(".models .menu");
  await expect(menu.getByText("рекомендовані")).toBeVisible();

  const luna = menu.getByRole("option", { name: /GPT-5.6 Luna/ });
  await expect(luna).toContainText("потрібен ключ");

  await luna.click();
  await expect(menu.getByPlaceholder("sk-...")).toBeVisible();

  await menu.getByPlaceholder("sk-...").fill("не ключ");
  await menu.getByRole("button", { name: "Зберегти" }).click();
  await expect(menu.getByText(/починається з «sk-»/)).toBeVisible();

  await menu.getByPlaceholder("sk-...").fill("sk-" + "a".repeat(40));
  await menu.getByRole("button", { name: "Зберегти" }).click();
  await expect(menu.getByPlaceholder("sk-...")).toBeHidden();
  await expect(menu.getByText("прибрати мій ключ OpenAI")).toBeVisible();
});

test("швидкий режим видно, але він не знімається і в запит не їде (10.09, #198)", async ({
  page,
}) => {
  const sent: Record<string, unknown>[] = [];
  await mockApi(page, { onBuild: (body) => sent.push(body) });
  await skipIntro(page);
  await enter(page);

  await page.locator(".models .pill").click();
  const fast = page.locator(".models .menu .fastrow input");
  await expect(fast).toBeChecked();

  await expect(fast).toBeDisabled();
  await page.keyboard.press("Escape");
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  expect(sent.at(-1)?.fast ?? null).toBeNull();
});

test("записано, але оформити не можна — це окремий стан, а не мовчання (#251)", async ({
  page,
}) => {
  const writes: number[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/checkout")) writes.push(1);
  });

  await mockApi(page, {
    blockers: ["product.offer.status.not_available"],
    blockerNotes: [
      "частину товарів «Сільпо» не прийняло: їх зняли з продажу вже після збірки",
    ],
    retryHelps: true,
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);

  const button = page.getByRole("button", { name: "Оформити" });
  await expect(button).toBeVisible({ timeout: 20_000 });
  await button.click();
  const confirm = page.getByRole("button", { name: "Погоджую -- оформити" });
  await confirm.or(page.locator(".checkout.done")).first().waitFor();
  if (await confirm.isVisible()) {
    await page
      .getByRole("checkbox", { name: /Згоден, щоб збирач замінив/ })
      .check();
    await confirm.click();
  }

  const dock = page.locator(".checkout.done");
  await expect(dock).toContainText(/не прийняло/);
  await expect(dock).toContainText(/Записав/);
  await expect(dock).toContainText(/1\s?157/);

  const back = page.getByTestId("cart-link");
  await expect(back).toBeVisible();
  await expect(back).toHaveAttribute("href", "https://silpo.ua/checkout-new");
  await expect(
    page.getByRole("link", { name: "Підтвердити в «Сільпо»" }),
  ).toHaveCount(0);

  await expect(button).toBeHidden();
  expect(writes.length).toBe(1);
});

test("«стерти список» каже, ЩО воно стерло — і нуль теж відповідь (#245)", async ({
  page,
}) => {
  await mockApi(page);
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  await openListSettings(page);
  await page.getByRole("button", { name: "Скласти з покупок" }).click();
  await expect(page.locator(".deed-said")).toContainText(
    /склав список із покупок/,
    {
      timeout: 15_000,
    },
  );

  await openListSettings(page);
  await page.getByRole("button", { name: "Стерти список" }).click();
  await page.getByRole("button", { name: "Точно стерти" }).click();
  await expect(page.locator(".deed-said")) // `\s`, а не пробіл: `plural` склеює число зі словом НЕРОЗРИВНИМ
    .toContainText(/стерто \d+\s+ряд/, {
      timeout: 15_000,
    });
  await expect(page.locator(".deed-said")).toContainText(
    /на екрані лишилось \d+ — це рядки з чеків/,
  );

  await openListSettings(page);
  await page.getByRole("button", { name: "Стерти список" }).click();
  await page.getByRole("button", { name: "Точно стерти" }).click();
  await expect(page.locator(".deed-said")).toContainText(
    /стирати не було чого/,
    {
      timeout: 15_000,
    },
  );
});

test("перезбірка бере і те, що дописали ПІСЛЯ збірки (#252)", async ({
  page,
}) => {
  const sent: Record<string, unknown>[] = [];
  await mockApi(page, { onBuild: (body) => sent.push(body) });
  await skipIntro(page);
  await enter(page);

  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await page.getByPlaceholder("Додати ще: сметана, хліб").fill("сметана");
  await page.locator(".week-add button[type=submit]").click();
  await expect(page.locator(".week-asking")).toContainText("сметана");

  await expect(page.locator(".week-asking")).toBeHidden({ timeout: 20_000 });
  await page.getByRole("button", { name: "На початок" }).click();
  await buildWeek(page);

  await expect.poll(() => sent.length, { timeout: 20_000 }).toBeGreaterThan(1);
  expect(sent.at(-1)?.shoppingList).toContain("сметана");
});

test("ціна вагового кандидата каже, що вона за кілограм (#242)", async ({
  page,
}) => {
  await mockApi(page);
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await page.getByRole("button", { name: "Що зробив агент" }).click();
  const weighed = page.locator(".rejected li", {
    hasText: "Молоко фермерське розливне",
  });
  await expect(weighed).toContainText("/кг");

  await expect(
    page.locator(".rejected li", { hasText: "Молоко Яготинське" }),
  ).toContainText("900г");
});

test("стояча згода на авто-заміну не дістається наступному гостю (#171)", async ({
  page,
}) => {
  await mockApi(page);
  await openApp(page);

  await page
    .getByRole("button", { name: /Дозволити заміну без питань/ })
    .click();
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem("komora:autoswap")))
    .toBe("1");

  await page.getByRole("button", { name: "Сільпо" }).click();
  await page.getByRole("button", { name: /Вийти й відкликати/ }).click();

  await expect
    .poll(() => page.evaluate(() => localStorage.getItem("komora:autoswap")))
    .toBe(null);
});

test("комора після збою читання не вдає порожню — і пробує ще раз (#166)", async ({
  page,
}) => {
  const reads: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.endsWith("/api/pantry"))
      reads.push(request.url());
  });

  await openApp(page, { pantry: "dead" });

  await expect(page.getByText(/не відповів/).last()).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByText(/нема з чого рахуватись/)).toBeHidden();

  const again = page.getByRole("button", { name: /Спробувати ще раз/ });
  await expect(
    page.getByRole("button", { name: /Записати, що вдома/ }),
  ).toBeHidden();

  const before = reads.length;
  await again.click();
  await expect
    .poll(() => reads.length, { timeout: 15_000 })
    .toBeGreaterThan(before);
});

test("селектор моделей: недоступні приховані з лічильником, а Luna названа не з Bedrock (02.09)", async ({
  page,
}) => {
  await mockApi(page);
  await skipIntro(page);
  await enter(page);
  await page.keyboard.press("`");

  await page.locator(".models .pill").click();
  const menu = page.locator(".models .menu");
  await expect(menu.locator(".menu-head")).not.toContainText("Bedrock");
  await expect(menu.getByRole("option", { name: /Claude Opus 5/ })).toHaveCount(
    0,
  );
  await expect(menu.getByText(/ще 1 у каталозі без доступу/)).toBeVisible();
  await expect(
    menu.getByRole("option", { name: /GPT-5.6 Luna/ }),
  ).toContainText("OpenAI");
  const large = menu.getByRole("option", { name: /Mistral Large 3/ });
  await expect(large.locator(".model-note")).not.toHaveClass(/ellipsis/);

  const luna = menu.getByRole("option", { name: /GPT-5.6 Luna/ });
  const clipped = await luna
    .locator(".model-name")
    .evaluate((el) => el.scrollWidth > el.clientWidth);
  expect(clipped, "назву Luna обрізано").toBe(false);

  await luna.click();
  await expect(menu).toBeVisible();
  await expect(menu.locator(".keyrow input")).toBeVisible();
});

test("каталог Bedrock у меню моделей ходить за прапорцем дебагу з бургера, одразу і в обидва боки (10.09)", async ({
  page,
}) => {
  await mockApi(page);
  await skipIntro(page);
  await enter(page);

  const pill = page.locator(".models .pill");
  const menu = page.locator(".models .menu");
  await pill.click();
  await expect(menu.getByText(/devstral/i)).toHaveCount(0);
  await page.keyboard.press("Escape");

  const toggle = async () => {
    await page.getByRole("button", { name: "Меню" }).click();
    await page.getByRole("button", { name: /панель дебагу/ }).click();
  };
  await toggle();
  await pill.click();
  await expect(menu.getByText(/devstral/i)).toBeVisible();
  await expect(menu.getByText(/видно, бо панель дебагу увімкнена/)).toBeVisible();
  await page.keyboard.press("Escape");

  await toggle();
  await pill.click();
  await expect(menu.getByText(/devstral/i)).toHaveCount(0);
});

test("ланка ланцюжка називає свою ціну і фасовку (02.09)", async ({ page }) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page.locator("button.swaps").first().click();
  await revealRest(page);

  const card = page.locator("article.card").filter({ hasText: "Club 4 Paws" });
  const links = card.locator(".chain li");
  await expect(links.nth(0)).toContainText("з твоєї історії · 21,90 ₴ · 85г");
  await expect(links.nth(1)).toContainText("22,50 ₴");
  await expect(links.nth(2)).toContainText("пропонує «Сільпо»");
  await expect(links.nth(2)).not.toContainText("₴");
});

test("як забирати: продукт пропонує лише кур'єра і самовивіз (02.09)", async ({
  page,
}) => {
  await mockApi(page);
  await skipIntro(page);
  await enter(page);

  const section = page.locator('[data-tour="delivery"]');
  await expect(section.getByRole("button", { name: "кур'єр" })).toBeVisible();
  await expect(
    section.getByRole("button", { name: "самовивіз" }),
  ).toBeVisible();
  await expect(
    section.getByRole("button", {
      name: /Нова пошта|експрес|LOKO|без поспіху/,
    }),
  ).toHaveCount(0);
  await expect(section.getByText(/Нова пошта|експрес/)).toHaveCount(0);
});

test("«-1» на позиції не гасить «Оформити»: кількість їде в запис без перезбірки (02.09)", async ({
  page,
}) => {
  await openApp(page);
  await buildWeek(page);
  const button = page.getByRole("button", { name: "Оформити" });
  await expect(button).toBeVisible({ timeout: 20_000 });

  const milk = page.locator("li.row").filter({ hasText: "Молоко Селянське" });
  await milk.getByRole("button", { name: /^Менше/ }).click();
  await expect(milk.locator(".qty-input")).toHaveValue("1");
  await expect(button).toBeEnabled();
  await expect(page.getByText(/докинуте на екрані ще не в плані/)).toHaveCount(
    0,
  );

  const sent = page.waitForRequest(
    (request) =>
      request.url().endsWith("/checkout") && request.method() === "POST",
  );
  await checkout(page);
  const body = (await sent).postDataJSON() as {
    lines?: Record<string, number>;
  };
  expect(Object.values(body.lines ?? {})).toEqual([1]);
});

test("докинуте до порога їде в запис без перезбірки: «Оформити» не гасне, тіло везе extras (11.09)", async ({
  page,
}) => {
  await mockApi(page, {
    basket: {
      topUp: { threshold: TOTAL + 20, saving: 58, items: TOPUP_ITEMS },
    },
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  const button = page.getByRole("button", { name: "Оформити" });
  await expect(button).toBeVisible({ timeout: 20_000 });

  await page.locator(".eco").getByRole("button", { name: /до порога/ }).click();
  await expect(button).toBeEnabled();
  await expect(page.getByText(/докинуте на екрані ще не в плані/)).toHaveCount(
    0,
  );

  const sent = page.waitForRequest(
    (request) =>
      request.url().endsWith("/checkout") && request.method() === "POST",
  );
  await checkout(page);
  const body = (await sent).postDataJSON() as {
    extras?: { externalProductId: string; qty: number }[];
  };
  expect(body.extras?.map((extra) => extra.externalProductId)).toEqual(
    TOPUP_ITEMS.slice(0, 1).map((item) => item.externalProductId),
  );
});

test("під дебагом екран збору показує справжні кроки, поки збірка йде, а не фази за таймером (02.09)", async ({
  page,
}) => {
  const sent: Record<string, unknown>[] = [];
  await mockApi(page, {
    buildDelayMs: 6000,
    onBuild: (body) => sent.push(body),
    progress: [
      {
        id: "step-slot",
        seq: 1,
        tool: "silpo_get_time_slots",
        args: {},
        durationMs: 412,
        calls: null,
        tokensIn: null,
        tokensOut: null,
        resultSummary: "слот: сьогодні 18:00-20:00",
        decision: null,
        tag: null,
        tagTone: "muted",
        externalProductId: null,
        prompt: null,
        question: null,
      },
      {
        id: "step-history",
        seq: 2,
        tool: "silpo_get_my_offline_orders",
        args: {},
        durationMs: 1290,
        calls: null,
        tokensIn: null,
        tokensOut: null,
        resultSummary: "чеків прочитано: 46",
        decision: null,
        tag: null,
        tagTone: "muted",
        externalProductId: null,
        prompt: null,
        question: null,
      },
    ],
  });
  await skipIntro(page);
  await enter(page);
  await page.keyboard.press("`");
  await buildWeek(page);

  const live = page.locator(".running .step.live");
  await expect(live).toContainText("чеків прочитано: 46");
  await expect(live.locator(".call")).toContainText(
    "silpo_get_my_offline_orders",
  );
  await expect(page.locator(".running .step.done")).toContainText([
    "слот: сьогодні 18:00-20:00",
  ]);

  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  expect(typeof sent[0]?.progressKey).toBe("string");
});

test("без дебагу на екрані збору кроки видно словами, а імена інструментів -- ні (#288, 10.09)", async ({
  page,
}) => {
  await mockApi(page, {
    build: "slow",
    progress: [
      {
        id: "step-history",
        seq: 1,
        tool: "silpo_get_my_offline_orders",
        args: {},
        durationMs: 1290,
        calls: null,
        tokensIn: null,
        tokensOut: null,
        resultSummary: "чеків прочитано: 46",
        decision: null,
        tag: null,
        tagTone: "muted",
        externalProductId: null,
        prompt: null,
        question: null,
      },
    ],
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);

  const running = page.locator(".running");
  await expect(running).toBeVisible();
  await expect(running.getByText(/^\d+ с/)).toBeVisible();

  await expect(running.locator(".step.live")).toContainText("чеків прочитано: 46");
  await expect(running.getByText("get_my_offline_orders")).toHaveCount(0);
  await expect(running.locator(".call")).toHaveCount(0);
  await expect(running.locator(".copy-all")).toHaveCount(0);

  const knows = running.locator(".thought").filter({ hasText: "Твоя комора" });
  await expect(knows).toBeVisible({ timeout: 9000 });
});

test("рядок комори каже, що вид береться по акції, і скільки (#265)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const paper = page
    .locator("li")
    .filter({ hasText: "Туалетний папір" })
    .first();
  await paper.getByRole("button", { name: /докладніше/ }).click();
  await expect(paper).toContainText("береш по акції: 9 з 10, зазвичай по 12");
  const rice = page.locator("li").filter({ hasText: "Рис" }).first();
  await expect(rice).not.toContainText("по акції");
});

test("акція, що зникла між збіркою і записом, називається поіменно (#265)", async ({
  page,
}) => {
  await openApp(page, { promoGone: ["Пиво Hike Blanche світле з/б"] });
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await checkout(page);

  await expect(page.getByText(/Акція зникла, поки писали/)).toBeVisible();
  await expect(page.getByText("Пиво Hike Blanche світле з/б")).toBeVisible();
  await expect(
    page.getByText(/прибери в кошику «Сільпо», якщо без акції не треба/),
  ).toBeVisible();
});

test("попередження кошика доїжджають на екран окремо від блокерів (#272)", async ({
  page,
}) => {
  await openApp(page, { warnings: ["ціна змінилась між збіркою і записом"] });
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await checkout(page);

  await expect(page.getByText("«Сільпо» попереджає:")).toBeVisible();
  await expect(
    page.getByText("ціна змінилась між збіркою і записом"),
  ).toBeVisible();
  await expect(page.locator(".handed-list.stop")).toHaveCount(0);
});

test("дотик по чипу одразу каже «шукаю», а другий дотик нічого не шле (#281)", async ({
  page,
}) => {
  const sent: Record<string, unknown>[] = [];
  await mockApi(page, {
    basket: { questions: [CHEESE] },
    onRefill: (body) => sent.push(body),
    refillDelayMs: 1500,
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const ask = page.locator(".ask");
  const cheese = ask.getByRole("button", { name: /^сир твердий/ });
  const sour = ask.getByRole("button", { name: /^Сир кисломолочний/ });
  await cheese.click();
  await expect(cheese).toContainText("шукаю");
  await expect(sour).toBeDisabled();
  await expect(ask.getByRole("button", { name: "не треба" })).toBeDisabled();
  await expect(ask).toContainText("Шукаю під твою відповідь");

  await expect(ask).toHaveCount(0, { timeout: 10_000 });
  expect(sent).toHaveLength(1);
});

test("агент перепитав після відповіді -- картка каже це, а не стоїть як до дотику (#281)", async ({
  page,
}) => {
  await mockApi(page, { basket: { questions: [CHEESE] }, reask: true });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const ask = page.locator(".ask");
  const cheese = ask.getByRole("button", { name: /^сир твердий/ });
  await cheese.click();
  await expect(ask).toContainText("агент перепитав", { timeout: 10_000 });
  await expect(cheese).toBeEnabled();
  await expect(cheese).not.toContainText("шукаю");
});

test("бейдж ключа лишається в рамці рядка, коли меню моделей не влазить у висоту", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 360 });
  await mockApi(page);
  await skipIntro(page);
  await enter(page);

  await page.locator(".models .pill").click();
  const menu = page.locator(".models .menu");
  const luna = menu.getByRole("option", { name: /GPT-5.6 Luna/ });
  await expect(luna.locator(".cost")).toContainText("потрібен ключ");

  const row = await luna.boundingBox();
  const badge = await luna.locator(".cost").boundingBox();
  expect(row && badge).toBeTruthy();
  expect(badge!.y + badge!.height).toBeLessThanOrEqual(
    row!.y + row!.height + 0.5,
  );
  const scrolls = await menu
    .locator(".menu-list")
    .evaluate((el) => el.scrollHeight > el.clientHeight);
  expect(scrolls, "список мусить прокручуватись, коли не влазить").toBe(true);
});

test("питання агента стоїть карткою ПОСЕРЕД збірки, а не під дебагом (#285)", async ({
  page,
}) => {
  const said: { questionId: string; optionId: string }[] = [];
  await mockApi(page, {
    buildDelayMs: 6000,
    onAnswer: (answer) => said.push(answer),
    progress: [
      {
        id: "step-ask",
        seq: 1,
        tool: "agent.understand",
        args: {},
        durationMs: 900,
        calls: null,
        tokensIn: null,
        tokensOut: null,
        resultSummary: "питаю гостя: Готуєш сам чи береш готове?",
        decision: null,
        tag: "питання",
        tagTone: "muted",
        externalProductId: null,
        prompt: null,
        question: {
          id: "q1",
          ask: "Готуєш сам чи береш готове?",
          why: "від цього залежить, що брати — сире чи нарізку",
          options: [
            { id: "o1", label: "готую сам", style: "cooking", target: null },
            { id: "o2", label: "беру готове", style: "ready", target: null },
          ],
          waitS: 25,
        },
      },
    ],
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);

  const ask = page.locator(".running .ask");
  await expect(ask).toContainText("Готуєш сам чи береш готове?");
  await expect(ask).toContainText("від цього залежить");
  await expect(ask).toContainText("25 с");

  await ask.getByRole("button", { name: "беру готове" }).click();
  await expect(ask).toHaveCount(0);
  expect(said).toEqual([{ questionId: "q1", optionId: "o2" }]);

  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
});

test("кошик над межею питає, що зняти, а не радить зробити це самому (#303)", async ({
  page,
}) => {
  const said: { questionId: string; optionId: string }[] = [];
  await mockApi(page, {
    buildDelayMs: 6000,
    onAnswer: (answer) => said.push(answer),
    progress: [
      {
        id: "step-over",
        seq: 1,
        tool: "агент",
        args: { "над межею, грн": "460.04" },
        durationMs: 12,
        calls: null,
        tokensIn: null,
        tokensOut: null,
        resultSummary:
          "кошик вище межі на 460 грн, а різати лишилось лише назване тобою — питаю, що робити",
        decision: null,
        tag: "питання",
        tagTone: "warn",
        externalProductId: null,
        prompt: null,
        question: {
          id: "over",
          ask: "Кошик на 2220 грн — це на 460 вище твоєї межі 1760. Що робимо?",
          why: "назване тобою я не знімаю без твого слова",
          options: [
            {
              id: "cut:201",
              label: "зняти Кава Lavazza — лишиться 1700 грн",
              style: null,
              target: null,
            },
            {
              id: "raise",
              label: "підняти ціль до 2100 грн",
              style: null,
              target: 2100,
            },
          ],
          waitS: 25,
        },
      },
    ],
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);

  const ask = page.locator(".running .ask");
  await expect(ask).toContainText("на 460 вище твоєї межі");
  await expect(ask).toContainText("лишиться 1700 грн");
  await expect(ask).toContainText("підняти ціль до 2100 грн");

  await ask
    .getByRole("button", { name: "зняти Кава Lavazza — лишиться 1700 грн" })
    .click();
  await expect(ask).toHaveCount(0);
  expect(said).toEqual([{ questionId: "over", optionId: "cut:201" }]);

  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
});

test("піднята ціль переживає прогін і стає ціллю наступної збірки (#303)", async ({
  page,
}) => {
  const sent: Record<string, unknown>[] = [];
  await mockApi(page, {
    buildDelayMs: 6000,
    onBuild: (body) => sent.push(body),
    progress: [
      {
        id: "step-over",
        seq: 1,
        tool: "агент",
        args: {},
        durationMs: 12,
        calls: null,
        tokensIn: null,
        tokensOut: null,
        resultSummary: "кошик вище межі на 460 грн — питаю, що робити",
        decision: null,
        tag: "питання",
        tagTone: "warn",
        externalProductId: null,
        prompt: null,
        question: {
          id: "over",
          ask: "Що робимо?",
          why: null,
          options: [
            {
              id: "cut:201",
              label: "зняти Кава Lavazza — лишиться 1700 грн",
              style: null,
              target: null,
            },
            {
              id: "raise",
              label: "підняти ціль до 2100 грн",
              style: null,
              target: 2100,
            },
          ],
          waitS: 25,
        },
      },
    ],
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);

  await page
    .locator(".running .ask")
    .getByRole("button", { name: "підняти ціль до 2100 грн" })
    .click();
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await expect(
    page.getByRole("button", { name: /зібрати приблизно на/ }),
  ).toContainText("2 100");
  await page.getByRole("button", { name: "здоровіше", exact: true }).click();
  const again = page.getByRole("dialog", { name: "Перезібрати кошик?" });
  await again.getByRole("button", { name: "Перезібрати" }).click();
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  expect(sent.at(-1)?.budget).toBe(2100);
});

const DECK_MS = 25_000;

test("картка «найчастіше» називає ВІДДІЛ, а не вид (09.09)", async ({
  page,
}) => {
  await openApp(page, { buildDelayMs: DECK_MS });
  await buildWeek(page);

  const running = page.locator(".running");
  await expect(running.getByText(/Тримаю межу/)).toBeVisible({
    timeout: DECK_MS,
  });
  const deck = await running.locator(".thoughts").innerText();

  const often = deck.split("\n").find((line) => line.startsWith("Найчастіше"));
  expect(often).toBeDefined();
  expect(often).toContain("відділ «");
  expect(often).toMatch(/покуп\S*\s+у\s+\d+\s+вид/);

  const next = deck.split("\n").find((line) => line.startsWith("Далі в черзі"));
  if (next !== undefined) expect(next).toContain("відділу «");
});

test("«скласти з покупок» не робить із рядка «доданий руками» (#300)", async ({
  page,
}) => {
  await openApp(page, { buildDelayMs: DECK_MS });
  await page.getByRole("button", { name: /Закінчується/ }).click();
  await openListSettings(page);
  await page.getByRole("button", { name: "веду сам", exact: true }).click();
  await openListSettings(page);
  await page.getByRole("button", { name: "Скласти з покупок" }).click();
  await openListSettings(page);
  await page.getByRole("button", { name: "з покупок", exact: true }).click();

  await page.getByRole("button", { name: "На початок" }).last().click();
  await buildWeek(page);

  const running = page.locator(".running");
  await expect(running.getByText(/Тримаю межу/)).toBeVisible({
    timeout: DECK_MS,
  });
  expect(await running.locator(".thoughts").innerText()).not.toContain(
    "Ти додав руками",
  );
});

test("у режимі списку фраза не приписує гостю авторства (#300)", async ({
  page,
}) => {
  await openApp(page, { buildDelayMs: DECK_MS });
  await page.getByRole("button", { name: /Закінчується/ }).click();
  await openListSettings(page);
  await page.getByRole("button", { name: "веду сам", exact: true }).click();
  await openListSettings(page);
  await page.getByRole("button", { name: "Скласти з покупок" }).click();

  await page.getByRole("button", { name: "На початок" }).last().click();
  await buildWeek(page);

  const running = page.locator(".running");
  await expect(running.getByText(/Список ведеш ти/)).toBeVisible({
    timeout: DECK_MS,
  });
  expect(await running.locator(".thoughts").innerText()).not.toContain(
    "Ти додав руками",
  );
});

test("глузд про вид стоїть на рядку, а питання -- лише там, де ритм бреше (#305)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const rice = page.locator(".row", { hasText: "Рис" }).first();
  const paper = page.locator(".row", { hasText: "Туалетний папір" }).first();

  await expect(rice.getByText(/рис витрачають рівно/)).toBeVisible();
  await expect(paper.getByText(/паперові рушники витрачають/)).toBeVisible();

  await expect(paper.locator(".sense-line.asking")).toHaveCount(1);
  await expect(rice.locator(".sense-line.asking")).toHaveCount(0);
});

test("слово гостя, яке перегрупувалось, називає СЕБЕ на рядку (#355)", async ({
  page,
}) => {
  await openPantryApp(page);

  const rice = page.locator(".row", { hasText: "Рис" }).first();
  await expect(rice.getByText(/Рис довгозернистий/)).toBeVisible();
});

test("рядок комори каже, що приїхало з доставки, і лише там, де приїхало (10.09)", async ({
  page,
}) => {
  await openPantryApp(page);

  const rice = page.locator(".row", { hasText: "Рис" }).first();
  await expect(rice.getByText("приїхало вчора")).toBeVisible();
  await expect(page.locator(".arrived")).toHaveCount(1);
});

test("підказки «додати в комору» -- зі СВОЇХ видів, і кожен стан підписаний (#339)", async ({
  page,
}) => {
  await openPantryApp(page);
  await page.getByRole("button", { name: "+ Додати" }).click();

  const note = page.locator(".suggest-note");
  await expect(note).toHaveText(/з твоїх покупок/);
  await expect(
    page.getByRole("button", { name: "Мед акацієвий" }),
  ).toBeVisible();

  await page.getByPlaceholder(/вид/i).first().fill("рис");
  await expect(note).toHaveText(/таке в тебе вже є/);
});

test("«не додавати» -- це відповідь: вид іде з обліку, а стек рухається далі", async ({
  page,
}) => {
  await openPantryApp(page);

  const card = await openAsks(page);
  const count = card.locator(".ask-count");
  await expect(count).toHaveText("залишилось 4 види");
  const first = await card.locator(".ask-name").textContent();

  const [request] = await Promise.all([
    page.waitForRequest(
      (r) => r.url().includes("/api/pantry") && r.method() !== "GET",
    ),
    card.getByRole("button", { name: "не веду цей вид" }).click(),
  ]);

  expect(JSON.stringify(request.postDataJSON())).toContain("hide");
  await expect(card.locator(".ask-name")).not.toHaveText(first ?? "");
  await expect(count).toHaveText("залишилось 3 види");
  await card.getByRole("button", { name: "не веду цей вид" }).click();
  await expect(count).toHaveText("залишилось 2 види");
});

test("«не зараз» ховає стек і НЕ пише слова гостя", async ({ page }) => {
  await openPantryApp(page);

  const card = await openAsks(page);

  let wrote = false;
  page.on("request", (r) => {
    if (r.url().includes("/api/pantry") && r.method() !== "GET") wrote = true;
  });
  await card.getByRole("button", { name: "відкласти всі" }).click();

  await expect(card).toHaveCount(0);
  await expect(page.locator(".ask-door")).toHaveCount(0);
  expect(wrote).toBe(false);
});

test("картка питання називає ВІСЬ і те, що гість бачив у чеку", async ({
  page,
}) => {
  await openPantryApp(page);

  const card = await openAsks(page);
  await expect(card.locator(".ask-q")).toHaveText(/\d/);
  await expect(card.locator(".ask-seen")).toHaveText(/^з чеків: \S/);
});

test("слово гостя знімає питання з рядка, не питаючи вдруге (#305)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const paper = page.locator(".row", { hasText: "Туалетний папір" }).first();
  await expect(paper.locator(".sense-line.asking")).toHaveCount(1);

  await paper.getByRole("button", { name: /вистачає/ }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "на тиждень", exact: true })
    .click();

  await expect(paper.locator(".state.said")).toBeVisible();
});

test("аварійний план називає себе банером, а звичайний кошик мовчить", async ({
  page,
}) => {
  await mockApi(page, {
    basket: { planNote: "модель не відповіла (таймаут) — план з коду" },
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const note = page.getByTestId("plan-note");
  await expect(note).toContainText("зібрано аварійним планом");
  await expect(note).toContainText("модель не відповіла");
  await expect(note).toContainText("без вибору агента");
});

test("на кошику від моделі банера аварійного плану немає", async ({ page }) => {
  await mockApi(page);
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await expect(page.getByTestId("plan-note")).toHaveCount(0);
});

test("невзяте з набраного тексту стоїть банером і ховається дотиком (#347)", async ({
  page,
}) => {
  await mockApi(page, {
    basket: { textIgnored: ["0501234567", "дякую"] },
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const note = page.getByTestId("text-ignored");
  await expect(note).toContainText("з набраного не взяв");
  await expect(note).toContainText("0501234567");
  await expect(note).toContainText("дякую");

  await note.getByRole("button", { name: "Сховати" }).click();
  await expect(page.getByTestId("text-ignored")).toHaveCount(0);
});

test("на кошику, де переріз узяв усе, банера невзятого немає (#347)", async ({
  page,
}) => {
  await mockApi(page);
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await expect(page.getByTestId("text-ignored")).toHaveCount(0);
});

test("комора каже, ЗВІДКИ вона взялась, і числа сходяться з екраном (#334)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const why = page.getByRole("group").filter({ hasText: "звідки це" }).first();
  await expect(why).toBeVisible();

  await expect(page.getByText("зі сховища 115, дочитано 3")).toBeHidden();

  await page.getByText(/звідки це/).click();

  await expect(page.getByText("зі сховища 115, дочитано 3")).toBeVisible();
  await expect(
    page.getByText("видів 143: з кешу 143, спитано 0"),
  ).toBeVisible();
  await expect(page.getByText(/рядків 44: зі смугою 12/)).toBeVisible();

  await expect(
    page.getByText("історія зберігається, тож щоразу дочитується лише хвіст"),
  ).toBeVisible();
});

test("полиця, яка замовкла, називає себе банером, а не маленьким кошиком (#343)", async ({
  page,
}) => {
  await mockApi(page, {
    basket: {
      shelfNote:
        "полиця не відповіла на 39 запитів з 41 — це не маленький кошик, " +
        "а мовчання магазину; спробуй ще раз за хвилину",
    },
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const note = page.getByTestId("shelf-note");
  await expect(note).toContainText("полиця не відповіла");
  await expect(note).toContainText("39");
  await expect(note).toContainText("41");
  await expect(note).toContainText("ще раз");
});

test("на здоровому кошику банера про мовчання полиці немає (#343)", async ({
  page,
}) => {
  await mockApi(page);
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  await expect(page.getByTestId("shelf-note")).toHaveCount(0);
});

test("розкривається БУДЬ-ЯКИЙ рядок, а не лише перший (#337)", async ({
  page,
}) => {
  await openApp(page, { pantry: "twins" });
  await page.getByRole("button", { name: /Закінчується/ }).click();

  const hard = page.locator("li.row").filter({ hasText: "сир · твердий" });
  const cream = page.locator("li.row").filter({ hasText: "сир · вершковий" });

  await cream.getByRole("button", { name: /докладніше|згорнути/ }).click();
  await expect(cream.locator(".parts li")).toHaveCount(2);
  await expect(cream.locator(".parts li").first()).toContainText(
    "Сир Президент Крем-Чіз",
  );
  await expect(hard.locator(".parts")).toHaveCount(0);

  await hard.getByRole("button", { name: /докладніше|згорнути/ }).click();
  await expect(hard.locator(".parts li")).toHaveCount(2);
  await expect(cream.locator(".parts li")).toHaveCount(2);

  await cream.getByRole("button", { name: /докладніше|згорнути/ }).click();
  await expect(cream.locator(".parts")).toHaveCount(0);
  await expect(hard.locator(".parts li")).toHaveCount(2);
});

test("комора: друга відповідь уточнює рядок і НЕ переставляє список (#330)", async ({
  page,
}) => {
  await openApp(page, { pantryLoop: "found" });
  await page.getByRole("button", { name: /Закінчується/ }).click();
  const list = page.locator('ul.list, ul[class*="list"]').first();
  const first = list.locator("li.row").first();

  await expect(page.getByTestId("pantry-refined")).toHaveText("уточнено: 1", {
    timeout: 15_000,
  });
  await first.getByRole("button", { name: /докладніше/ }).click();
  await expect(first.getByText("паляничку з'їдають за раз")).toBeVisible();
  await expect(first).toContainText("паляничку з'їдають за раз");
});

test("комора: петля, якій не було чого робити, каже це вголос (#330)", async ({
  page,
}) => {
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  await expect(page.getByTestId("pantry-refined")).toHaveText(
    "нічого не бракувало",
    { timeout: 15_000 },
  );
});

test("комора: петля, яка не приїхала, не червонить робочий екран (#330)", async ({
  page,
}) => {
  await openApp(page, { pantryLoop: "dead" });
  await page.getByRole("button", { name: /Закінчується/ }).click();
  const list = page.locator('ul.list, ul[class*="list"]').first();
  await expect(list.locator("li.row").first()).toBeVisible();

  await expect(page.getByTestId("pantry-refined")).toHaveCount(0);
  await expect(page.getByText(/не відповів|не вдалося/)).toHaveCount(0);
});

test("холодний режим переживає оновлення сторінки -- і називає себе (#341)", async ({
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "desktop",
    "смужка живе під панеллю дебагу, а панель -- від 1240 px",
  );
  await page.addInitScript(() => {
    localStorage.setItem("komora:debug", "1");
    localStorage.setItem("komora:cold", "1");
  });
  await openApp(page);
  await page.getByRole("button", { name: /Закінчується/ }).click();

  await page.getByRole("button", { name: "Меню" }).click();
  await expect(page.getByText("кеш назв видів")).toBeVisible();
  await expect(page.getByText("не читати")).toBeVisible();

  await page.reload();
  await page.getByRole("button", { name: "Меню" }).click();
  await expect(page.getByText("не читати")).toBeVisible();
});

test("вхід: перший екран -- комора, а не збірка кошика (#341)", async ({
  page,
}) => {
  await mockApi(page);
  await skipIntro(page);
  await page.goto("/");

  await expect(page.getByTestId("pantry-screen")).toBeVisible();
  await page.getByRole("button", { name: "На початок" }).first().click();
  await expect(page.getByRole("button", { name: /^Зібрати / })).toBeVisible();
});

test("комора: поки петля йде, шапка каже КРОК, а не мовчить (#341)", async ({
  page,
}) => {
  await openPantryApp(page, { pantryLoop: "slow" });

  const working = page.getByTestId("pantry-working");
  await expect(working).toBeVisible({ timeout: 15_000 });
  await expect(working).toContainText(/[а-яіїєґ]{4}/i);

  await expect(page.getByTestId("pantry-refined")).toBeVisible({
    timeout: 20_000,
  });
  await expect(working).toHaveCount(0);
});

test("другий запуск не веде в комору знову, навіть коли петля впала", async ({
  page,
}) => {
  await openPantryApp(page, { pantryLoop: "dead" });
  await expect(page.getByTestId("pantry-screen")).toBeVisible();

  await page.reload();
  await expect(page.getByTestId("pantry-screen")).toHaveCount(0);
  await expect(page.getByText("у коморі зараз")).toBeVisible();
});

test("два оберти петлі не вбивають комору дублем ключа (#302)", async ({
  page,
}) => {
  const boom: string[] = [];
  page.on("pageerror", (error) => boom.push(String(error)));

  await page.addInitScript(() => localStorage.setItem("komora:debug", "1"));
  await openPantryApp(page);
  await page.getByText(/звідки це:/).click();

  await expect(page.getByText(/оберт 1:/).first()).toBeVisible();
  await expect(page.getByText(/оберт 2:/).first()).toBeVisible();
  expect(boom.join("\n")).not.toContain("each_key_duplicate");
});

test("холодний прогін -- ОДИН РАЗ НА ВХІД, а не на кожне відкриття", async ({
  page,
}) => {
  const cold: boolean[] = [];
  page.on("request", (r) => {
    if (!r.url().includes("/api/pantry")) return;
    if (r.method() === "GET") cold.push(r.url().includes("cold=true"));
  });

  await openPantryApp(page);
  await expect(page.getByTestId("pantry-screen")).toBeVisible();
  expect(cold[0], "перший вхід -- холодний").toBe(true);

  await page.reload();
  await expect(
    page.getByTestId("pantry-screen").or(page.getByText("у коморі зараз")),
  ).toBeVisible();
  expect(cold.at(-1), "після заповнення -- уже теплий").toBe(false);
});

test("трейс комори каже, скільки коштував увесь вхід, а не лише оберт", async ({
  page,
}) => {
  await openPantryApp(page);
  await page.getByText(/звідки це:/).click();

  await expect(page.getByText(/цей вхід:/)).toBeVisible();
  await expect(page.getByText(/38412 → 2907 ток\./)).toBeVisible();
});

test("той самий рядок про вхід стоїть і в журналі кошика", async ({ page }) => {
  await openApp(page);
  await buildBasket(page);
  await page.getByRole("button", { name: "Що зробив агент" }).click();

  await expect(page.getByText(/цей вхід:/)).toBeVisible();
});

test("двері до покупок під час заповнення відчинені, і ціна названа", async ({
  page,
}) => {
  await openPantryApp(page, { pantryLoop: "stuck" });
  await toStart(page);

  const run = page.getByRole("button", { name: /^Зібрати / });
  await expect(run).toBeEnabled();
  await expect(page.getByText(/Комора ще заповнюється/)).toBeVisible();
});

test("а коли петля не йде, ціни під кнопкою немає", async ({ page }) => {
  await openApp(page);
  await expect(page.getByRole("button", { name: /^Зібрати / })).toBeEnabled();
  await expect(page.getByText(/Комора ще заповнюється/)).toHaveCount(0);
});

test("панель дебагу переживає кроки з однаковим номером (#302)", async ({
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "desktop",
    "панель ховається на вузькому екрані",
  );
  const boom: string[] = [];
  page.on("pageerror", (error) => boom.push(String(error)));

  await page.addInitScript(() => localStorage.setItem("komora:debug", "1"));
  await openPantryApp(page, { pantryLoop: "slow" });

  await expect(page.getByText(/трейс · петля комори/)).toBeVisible({
    timeout: 15_000,
  });
  expect(boom.join("\n")).not.toContain("each_key_duplicate");
});

test("панель дебагу каже, скільки з'їв ЦЕЙ забіг — комора і замовлення разом", async ({
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "desktop",
    "панель ховається на вузькому екрані",
  );
  await page.addInitScript(() => localStorage.setItem("komora:debug", "1"));
  await openApp(page);

  const panel = page.getByRole("complementary", { name: "Панель дебагу" });
  await expect(panel.getByText(/цей забіг:/)).toHaveCount(0);

  await buildBasket(page);

  await expect(panel.getByText(/цей забіг:/)).toBeVisible();
  await expect(panel.getByText(/весь вхід:/)).toBeVisible();
  await expect(panel.getByText(/цей забіг:.*→.*ток\./)).toBeVisible();
  await expect(panel.getByText(/цей забіг: 1(\s)прогін/)).toBeVisible();
  await expect(panel.getByText(/весь вхід: 5(\s)прогонів/)).toBeVisible();
});

test("крок трейсу каже число викликів, а токени лишає підсумку (11.09)", async ({
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "desktop",
    "панель ховається на вузькому екрані",
  );
  await page.addInitScript(() => localStorage.setItem("komora:debug", "1"));
  await openPantryApp(page, { pantryLoop: "slow" });

  const panel = page.getByRole("complementary", { name: "Панель дебагу" });
  await expect(panel.getByText(/^2(\s)виклики$/)).toBeVisible();
});

test("двері бару кажуть своє число, а не мовчать (#370)", async ({ page }) => {
  await mockApi(page, { bar: BAR });
  await skipIntro(page);
  await enter(page);

  const door = page.getByRole("button", { name: "що з напоїв удома" });
  await expect(door).toBeVisible();
  const text = (await door.innerText()).replace(/\s+/g, " ");
  expect(text).toContain(`удома ${BAR.items.length} видів`);
  expect(text).not.toMatch(
    new RegExp(`${BAR.items.length} ${BAR.items.length}`),
  );
});

test("двері бару не малюють нуля, поки бар не прочитаний (#76)", async ({
  page,
}) => {
  await mockApi(page, { bar: BAR_NO_DRINKS });
  await skipIntro(page);
  await enter(page);

  const door = page.getByRole("button", { name: "що з напоїв удома" });
  await expect(door).toBeVisible();
  await expect(door).not.toContainText("0");
});

test.describe("питання агента в коморі (#386)", () => {
  test("питання стоять на екрані кроків і кажуть, кого накриє відповідь", async ({
    page,
  }) => {
    await openPantryApp(page, { pantryLoop: "asking" });

    const asked = page.getByTestId("pantry-asked");
    await expect(asked).toBeVisible({ timeout: 15_000 });
    await expect(asked).toContainText("як швидко у вас закінчується хліб?");
    await expect(asked).toContainText("булка");
  });

  test("відповідь продовжує той самий оберт, а питання зникають", async ({
    page,
  }) => {
    await openPantryApp(page, { pantryLoop: "asking" });
    await page.getByTestId("pantry-asked").waitFor({ timeout: 15_000 });

    await page
      .getByTestId("pantry-asked")
      .getByRole("button", { name: "на 3 дні" })
      .click();
    await expect(page.getByRole("button", { name: "Ще питання" })).toBeVisible();
    await page.getByTestId("pantry-asked-done").click();

    await expect(page.getByText("Записую твою відповідь")).toBeVisible();
    await expect(page.getByTestId("pantry-asked")).toBeHidden();

    await expect(page.getByText("уточнено: 3")).toBeVisible();

    const door = page.getByRole("button", { name: /питання про твій дім/ });
    await expect(door).toBeVisible();
    await expect(door).toContainText("1");
    await door.click();
    await expect(page.getByTestId("pantry-asked")).toContainText("молоко");
  });

  test("екран з питаннями не пастка: вихід один і він зберігає відповідь", async ({
    page,
  }) => {
    await openPantryApp(page, { pantryLoop: "asking" });
    await page.getByTestId("pantry-asked").waitFor({ timeout: 15_000 });

    await expect(page.getByRole("button", { name: "відкласти всі" })).toHaveCount(0);
    await expect(page.locator(".cover .dock")).toHaveCount(0);
    await expect(
      page.getByTestId("pantry-asked-done"),
    ).toBeVisible();
  });
});

test("межа під привід -- рішення агента, і гість вертає своє число одним дотиком", async ({
  page,
}) => {
  await mockApi(page, {
    basket: {
      agentTarget: {
        named: 1600,
        proposed: 3000,
        target: 3000,
        why: "гості на шістьох",
        refused: null,
      },
    },
  });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });

  const note = page.getByTestId("agent-target");
  await expect(note).toContainText("рішення агента");
  await expect(note).toContainText("гості на шістьох");

  const sent = page.waitForRequest(
    (request) =>
      request.method() === "POST" && (request.postData() ?? "").includes('"budgetSaid":true'),
  );
  await note.getByRole("button", { name: /лишити/ }).click();
  const body = (await sent).postDataJSON() as { budget: number; budgetSaid: boolean };
  expect(body.budget).toBe(1600);
  expect(body.budgetSaid).toBe(true);
});

test("рядок під заголовком групи лишається сіткою: значок поруч з назвою (10.09)", async ({
  page,
}) => {
  await mockApi(page, { pantry: "twins" });
  await skipIntro(page);
  await page.goto("/");
  await expect(page.getByTestId("pantry-screen")).toBeVisible();
  const row = page.locator("li.band + li.row").first();
  await expect(row).toBeVisible({ timeout: 20_000 });
  const thumb = await row.locator(".thumb").boundingBox();
  const name = await row.locator(".name").boundingBox();
  expect(thumb).not.toBeNull();
  expect(name).not.toBeNull();
  expect(Math.abs((thumb?.y ?? 0) - (name?.y ?? 999))).toBeLessThan(24);
  expect(name?.x ?? 0).toBeGreaterThan((thumb?.x ?? 0) + (thumb?.width ?? 0) - 1);
});

test("перемикач кешу не перемикає себе: перший вхід холодний, оновлення тепле (10.09)", async ({
  page,
}, testInfo) => {
  test.skip(
    testInfo.project.name !== "desktop",
    "перемикач живе в меню під панеллю дебагу, а панель -- від 1240 px",
  );
  await page.addInitScript(() => {
    localStorage.setItem("komora:debug", "1");
  });
  const pantryCalls: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.pathname === "/api/pantry") pantryCalls.push(url.search);
  });
  await mockApi(page);
  await skipIntro(page);
  await page.goto("/");
  await expect(page.getByTestId("pantry-screen")).toBeVisible();
  await expect(page.locator("li.row").first()).toBeVisible({ timeout: 20_000 });
  expect(pantryCalls[0]).toBe("?cold=true");

  await page.getByRole("button", { name: "Меню" }).click();
  await expect(page.getByText("не читати")).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("komora:cold"))).toBeNull();

  await page.reload();
  await page.getByRole("button", { name: /Закінчується/ }).click();
  await expect(page.locator("li.row").first()).toBeVisible({ timeout: 20_000 });
  expect(pantryCalls[pantryCalls.length - 1]).toBe("");
  await page.getByRole("button", { name: "Меню" }).click();
  await expect(page.getByText("не читати")).toBeVisible();
});

test("кошик вище межі, але в коридорі: плашка називає верхню межу (10.09)", async ({
  page,
}) => {
  const limit = TOTAL - 20;
  await mockApi(page, { basket: { budget: limit } });
  await skipIntro(page);
  await enter(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  const of = page.locator(".dock-sum .of");
  await expect(of).toContainText("у коридорі до");
  const high = new Intl.NumberFormat("uk-UA", { maximumFractionDigits: 0 })
    .format(Math.round(limit * 1.1))
    .replace(/\u00a0/g, " ");
  await expect(of).toContainText(high);
});

test("нуль викликів моделі пишеться словами, а не «0 викликів» (10.09)", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "бічна панель дебагу живе від 1240 px");
  await page.addInitScript(() => localStorage.setItem("komora:debug", "1"));
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  const step = page.locator("article.step", { hasText: "get_orders_history" }).first();
  await expect(step).toContainText("модель не питали");
  await expect(step).not.toContainText("0 викликів");
  const planned = page.locator("article.step", { hasText: "agent.plan" }).first();
  await expect(planned.locator(".spend")).toHaveCount(0);
});

test("наростаючий фінал Android дає приріст, а не повтор фрази (10.09)", async ({ page }) => {
  await stubSpeech(page);
  await openPantryAdd(page);
  const dialog = page.getByRole("dialog", { name: "Диктування" });
  await expect(dialog).toBeVisible();
  await page.evaluate(() => {
    const w = window as any;
    w.__grow(["вода"]);
    w.__grow(["вода", "вода чай"]);
    w.__grow(["вода", "вода чай", "вода чай"]);
    w.__grow(["вода", "вода чай", "вода чай", "Вода, чай"]);
    w.__grow(["вода", "вода чай", "вода чай", "Вода, чай", "вода чай огірки"]);
  });
  const chips = dialog.locator(".rec-phrases > *");
  await expect(chips).toHaveCount(3);
  await expect(chips.nth(0)).toContainText(/вода/i);
  await expect(chips.nth(1)).toContainText(/чай/i);
  await expect(chips.nth(1)).not.toContainText(/вода/i);
  await expect(chips.nth(2)).toContainText(/огірки/i);
  await expect(chips.nth(2)).not.toContainText(/чай/i);
});

test("панель дебагу диктування живе за своїм ключем, а не за панеллю застосунку (10.09)", async ({
  page,
}) => {
  await stubSpeech(page);
  await page.addInitScript(() => localStorage.setItem("komora:debug", "1"));
  await openPantryAdd(page);
  const dialog = page.getByRole("dialog", { name: "Диктування" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("подій від двигуна")).toHaveCount(0);
  await expect(dialog.getByText("без хвилі")).toHaveCount(0);
});

test("док «До покупок» у вікні заповнення має ті самі відступи, що в готовій коморі", async ({
  page,
}) => {
  await openPantryApp(page, { pantry: "slow" });
  const screen = page.getByTestId("pantry-screen");
  await expect(screen.getByText("Заповнюю комору")).toBeVisible({ timeout: 15_000 });
  const back = page.getByRole("button", { name: "До покупок" });
  await expect(back).toBeVisible();
  const [frame, button] = await Promise.all([screen.boundingBox(), back.boundingBox()]);
  if (!frame || !button) throw new Error("немає розмірів вікна або кнопки");
  expect(button.x - frame.x).toBeGreaterThanOrEqual(12);
  expect(frame.x + frame.width - (button.x + button.width)).toBeGreaterThanOrEqual(12);
});

test("годинник іде і тоді, коли записується відповідь гостя", async ({ page }) => {
  await openPantryApp(page, { pantryLoop: "asking", answerHoldMs: 4_000 });
  const asked = page.getByTestId("pantry-asked");
  await asked.waitFor({ timeout: 15_000 });
  await asked.getByRole("button", { name: "на 3 дні" }).click();
  await expect(page.getByRole("button", { name: "Ще питання" })).toBeVisible();
  await page.getByTestId("pantry-asked-done").click();
  const window = page.locator(".running");
  await expect(window.getByText("Записую твою відповідь")).toBeVisible();
  await expect(window.locator(".clock")).toHaveText(/^[1-9]\d* с$/, { timeout: 3_000 });
});

test("вхід «Заміни погоджено наперед» відкриває весь кошик без кнопки решти", async ({
  page,
}) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await page.getByTestId("swaps-approved").click();
  const shown = LINES.filter((line) => line.reason !== "at_home");
  await expect(page.locator("article.card")).toHaveCount(shown.length);
  await expect(page.getByTestId("reveal-rest")).toHaveCount(0);
});

test("рядок без погодженої заміни їде без мандата, і звіт називає його", async ({
  page,
}) => {
  await openApp(page);
  await buildWeek(page);
  await expect(page.getByRole("button", { name: "Оформити" })).toBeVisible({
    timeout: 20_000,
  });
  await checkout(page);
  const waiting = LINES.filter((line) => line.needsApproval && line.mandate === null);
  expect(waiting.length).toBeGreaterThan(0);
  await expect(
    page.getByText(`Без мандата поїхало ${waiting.length} поз.`, { exact: false }),
  ).toBeVisible();
  await expect(
    page.locator(".handed-list strong", { hasText: waiting[0]?.name ?? "" }),
  ).toBeVisible();
});

test("картка питань: чипи відповіді головні, хрестик угорі, решта тихим рядком (11.09)", async ({
  page,
}) => {
  await openPantryApp(page);
  const card = await openAsks(page);
  const chips = card.locator("button.hint");
  await expect(chips.first()).toBeVisible();
  const close = card.getByRole("button", { name: "Закрити" });
  const [closeBox, chipBox] = await Promise.all([close.boundingBox(), chips.first().boundingBox()]);
  expect(closeBox !== null && chipBox !== null && closeBox.y < chipBox.y).toBe(true);
  await expect(card.getByRole("button", { name: "інше…" })).toBeVisible();
  await expect(card.locator("button.secondary")).toHaveCount(0);
});

test("мікрофон стоїть усередині поля «Додати ще», а не збоку (11.09)", async ({ page }) => {
  await stubSpeech(page);
  await openApp(page);
  await buildWeek(page);
  const field = page.getByPlaceholder("Додати ще: сметана, хліб");
  const mic = page.getByRole("button", { name: "надиктувати, що додати" });
  await expect(mic).toBeVisible();
  const [f, m] = await Promise.all([field.boundingBox(), mic.boundingBox()]);
  expect(f !== null && m !== null).toBe(true);
  if (f && m) {
    expect(m.x).toBeGreaterThanOrEqual(f.x);
    expect(m.x + m.width).toBeLessThanOrEqual(f.x + f.width + 1);
    expect(m.y + m.height / 2).toBeGreaterThan(f.y);
    expect(m.y + m.height / 2).toBeLessThan(f.y + f.height);
  }
});
test("модель без ключа зачиняє вхід: ворота ключа на вході, а не в коморі (11.09)", async ({
  page,
}) => {
  await openApp(page);
  await page.locator(".models .pill").click();
  await page.locator(".models .menu").getByRole("option", { name: /GPT-5.6 Luna/ }).click();
  await page.keyboard.press("Escape");
  const gate = page.getByTestId("key-gate");
  await expect(gate).toBeVisible();
  await gate.getByRole("button", { name: /Перемкнутись на/ }).click();
  await expect(gate).toHaveCount(0);
});

