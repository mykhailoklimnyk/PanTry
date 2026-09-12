<!--
  ЗГЕНЕРОВАНО: scripts/gen_licenses.py — руками не правити.
  Джерело — lock-файли, а не встановлене середовище: воно залежить від ОС.
  Розділи «Моделі» і «Дані» задані в самому скрипті: це рішення проєкту,
  а не факт середовища.
-->

# Ліцензії

Перелік на виконання п. 8.6 умов хакатону: бібліотеки, open-source компоненти,
моделі, датасети.

Зібраний з `uv.lock` і `web/package-lock.json`, тому не залежить від того, на
якій ОС його згенерували, і охоплює всі платформозалежні збірки.

Сам проєкт — **Apache-2.0**, повний текст у [LICENSE](../LICENSE).


## Python

Пакетів у `uv.lock`: **82** (з транзитивними).

| Пакет | Версія | Ліцензія |
| --- | --- | --- |
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anthropic | 0.121.0 | MIT |
| anyio | 4.14.2 | MIT |
| attrs | 26.1.0 | MIT |
| boto3 | 1.43.69 | Apache-2.0 |
| botocore | 1.43.69 | Apache-2.0 |
| certifi | 2026.7.22 | MPL-2.0 |
| cffi | 2.1.1 | MIT-0 |
| click | 8.4.2 | BSD-3-Clause |
| colorama | 0.4.6 | BSD License |
| coverage | 7.15.4 | Apache-2.0 |
| cryptography | 50.0.0 | Apache-2.0 OR BSD-3-Clause |
| distro | 1.9.0 | Apache License, Version 2.0 |
| docstring-parser | 0.18.0 | MIT |
| fastapi | 0.141.1 | MIT |
| granian | 2.8.1 | BSD-3-Clause |
| h11 | 0.16.0 | MIT |
| httpcore | 1.0.9 | BSD-3-Clause |
| httpcore2 | 2.10.0 | BSD-3-Clause |
| httpx | 0.28.1 | BSD-3-Clause |
| httpx2 | 2.10.0 | BSD-3-Clause |
| httpx2-jsfetch | 1.0 | BSD-3-Clause |
| hypothesis | 6.165.4 | MPL-2.0 |
| idna | 3.18 | BSD-3-Clause |
| iniconfig | 2.3.0 | MIT |
| jiter | 0.16.0 | MIT |
| jmespath | 1.1.0 | MIT |
| jsonschema | 4.26.0 | MIT |
| jsonschema-specifications | 2025.9.1 | MIT |
| komora | 0.1.0 | Apache-2.0 |
| libcst | 1.9.0 | MIT License |
| linkify-it-py | 2.1.0 | MIT |
| markdown-it-py | 4.2.0 | MIT License |
| mcp | 2.0.0 | MIT |
| mcp-types | 2.0.0 | MIT |
| mdit-py-plugins | 0.6.1 | MIT License |
| mdurl | 0.1.2 | MIT License |
| mutmut | 3.7.0 | BSD-3-Clause |
| opentelemetry-api | 1.44.0 | Apache-2.0 |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| platformdirs | 4.11.2 | MIT |
| pluggy | 1.6.0 | MIT |
| psycopg | 3.3.4 | LGPL-3.0-only |
| psycopg-binary | 3.3.4 | LGPL-3.0-only |
| psycopg-pool | 3.3.1 | LGPL-3.0-only |
| pycparser | 3.0 | BSD-3-Clause |
| pydantic | 2.13.4 | MIT |
| pydantic-core | 2.46.4 | MIT |
| pydantic-settings | 2.15.0 | MIT |
| pygments | 2.20.0 | BSD-2-Clause |
| pyjwt | 2.13.0 | MIT |
| pytest | 9.1.1 | MIT |
| pytest-asyncio | 1.4.0 | Apache-2.0 |
| pytest-socket | 0.8.0 | MIT |
| python-dateutil | 2.9.0.post0 | Dual License |
| python-dotenv | 1.2.2 | BSD-3-Clause |
| python-multipart | 0.0.32 | Apache-2.0 |
| pywin32 | 312 | PSF |
| pyyaml | 6.0.3 | MIT |
| referencing | 0.37.0 | MIT |
| rich | 15.0.0 | MIT |
| rpds-py | 2026.6.3 | MIT |
| ruff | 0.16.2 | MIT |
| s3transfer | 0.19.2 | Apache License 2.0 |
| setproctitle | 1.3.7 | BSD-3-Clause |
| six | 1.17.0 | MIT |
| sniffio | 1.3.1 | MIT OR Apache-2.0 |
| sortedcontainers | 2.4.0 | Apache 2.0 |
| sse-starlette | 3.4.8 | BSD-3-Clause |
| starlette | 1.6.0 | BSD-3-Clause |
| structlog | 26.1.0 | MIT OR Apache-2.0 |
| textual | 8.2.8 | MIT |
| truststore | 0.10.4 | MIT |
| ty | 0.0.71 | MIT License |
| typing-extensions | 4.16.0 | PSF-2.0 |
| typing-inspection | 0.4.4 | MIT |
| tzdata | 2026.3 | Apache-2.0 |
| uc-micro-py | 2.0.0 | MIT |
| urllib3 | 2.7.0 | MIT |
| uvicorn | 0.52.1 | BSD-3-Clause |
| winloop | 0.6.3 | MIT License |

## Node (фронтенд)

Пакетів у `web/package-lock.json`: **184**. Перелік охоплює й платформозалежні збірки для інших ОС — вони можуть поставитись у CI або в іншого розробника.

| Пакет | Версія | Ліцензія |
| --- | --- | --- |
| @cloudflare/kv-asset-handler | 0.5.0 | MIT OR Apache-2.0 |
| @cloudflare/unenv-preset | 2.16.1 | MIT OR Apache-2.0 |
| @cloudflare/workerd-darwin-64 | 1.20260811.1 | Apache-2.0 |
| @cloudflare/workerd-darwin-arm64 | 1.20260811.1 | Apache-2.0 |
| @cloudflare/workerd-linux-64 | 1.20260811.1 | Apache-2.0 |
| @cloudflare/workerd-linux-arm64 | 1.20260811.1 | Apache-2.0 |
| @cloudflare/workerd-windows-64 | 1.20260811.1 | Apache-2.0 |
| @cspotcode/source-map-support | 0.8.1 | MIT |
| @emnapi/runtime | 1.11.3 | MIT |
| @esbuild/aix-ppc64 | 0.28.1 | MIT |
| @esbuild/android-arm | 0.28.1 | MIT |
| @esbuild/android-arm64 | 0.28.1 | MIT |
| @esbuild/android-x64 | 0.28.1 | MIT |
| @esbuild/darwin-arm64 | 0.28.1 | MIT |
| @esbuild/darwin-x64 | 0.28.1 | MIT |
| @esbuild/freebsd-arm64 | 0.28.1 | MIT |
| @esbuild/freebsd-x64 | 0.28.1 | MIT |
| @esbuild/linux-arm | 0.28.1 | MIT |
| @esbuild/linux-arm64 | 0.28.1 | MIT |
| @esbuild/linux-ia32 | 0.28.1 | MIT |
| @esbuild/linux-loong64 | 0.28.1 | MIT |
| @esbuild/linux-mips64el | 0.28.1 | MIT |
| @esbuild/linux-ppc64 | 0.28.1 | MIT |
| @esbuild/linux-riscv64 | 0.28.1 | MIT |
| @esbuild/linux-s390x | 0.28.1 | MIT |
| @esbuild/linux-x64 | 0.28.1 | MIT |
| @esbuild/netbsd-arm64 | 0.28.1 | MIT |
| @esbuild/netbsd-x64 | 0.28.1 | MIT |
| @esbuild/openbsd-arm64 | 0.28.1 | MIT |
| @esbuild/openbsd-x64 | 0.28.1 | MIT |
| @esbuild/openharmony-arm64 | 0.28.1 | MIT |
| @esbuild/sunos-x64 | 0.28.1 | MIT |
| @esbuild/win32-arm64 | 0.28.1 | MIT |
| @esbuild/win32-ia32 | 0.28.1 | MIT |
| @esbuild/win32-x64 | 0.28.1 | MIT |
| @fontsource-variable/manrope | 5.3.0 | OFL-1.1 |
| @fontsource/ibm-plex-mono | 5.3.0 | OFL-1.1 |
| @img/colour | 1.1.0 | MIT |
| @img/sharp-darwin-arm64 | 0.35.2 | Apache-2.0 |
| @img/sharp-darwin-x64 | 0.35.2 | Apache-2.0 |
| @img/sharp-freebsd-wasm32 | 0.35.2 | Apache-2.0 |
| @img/sharp-libvips-darwin-arm64 | 1.3.1 | LGPL-3.0-or-later |
| @img/sharp-libvips-darwin-x64 | 1.3.1 | LGPL-3.0-or-later |
| @img/sharp-libvips-linux-arm | 1.3.1 | LGPL-3.0-or-later |
| @img/sharp-libvips-linux-arm64 | 1.3.1 | LGPL-3.0-or-later |
| @img/sharp-libvips-linux-ppc64 | 1.3.1 | LGPL-3.0-or-later |
| @img/sharp-libvips-linux-riscv64 | 1.3.1 | LGPL-3.0-or-later |
| @img/sharp-libvips-linux-s390x | 1.3.1 | LGPL-3.0-or-later |
| @img/sharp-libvips-linux-x64 | 1.3.1 | LGPL-3.0-or-later |
| @img/sharp-libvips-linuxmusl-arm64 | 1.3.1 | LGPL-3.0-or-later |
| @img/sharp-libvips-linuxmusl-x64 | 1.3.1 | LGPL-3.0-or-later |
| @img/sharp-linux-arm | 0.35.2 | Apache-2.0 |
| @img/sharp-linux-arm64 | 0.35.2 | Apache-2.0 |
| @img/sharp-linux-ppc64 | 0.35.2 | Apache-2.0 |
| @img/sharp-linux-riscv64 | 0.35.2 | Apache-2.0 |
| @img/sharp-linux-s390x | 0.35.2 | Apache-2.0 |
| @img/sharp-linux-x64 | 0.35.2 | Apache-2.0 |
| @img/sharp-linuxmusl-arm64 | 0.35.2 | Apache-2.0 |
| @img/sharp-linuxmusl-x64 | 0.35.2 | Apache-2.0 |
| @img/sharp-wasm32 | 0.35.2 | Apache-2.0 AND LGPL-3.0-or-later AND MIT |
| @img/sharp-webcontainers-wasm32 | 0.35.2 | Apache-2.0 |
| @img/sharp-win32-arm64 | 0.35.2 | Apache-2.0 AND LGPL-3.0-or-later |
| @img/sharp-win32-ia32 | 0.35.2 | Apache-2.0 AND LGPL-3.0-or-later |
| @img/sharp-win32-x64 | 0.35.2 | Apache-2.0 AND LGPL-3.0-or-later |
| @jridgewell/gen-mapping | 0.3.13 | MIT |
| @jridgewell/remapping | 2.3.5 | MIT |
| @jridgewell/resolve-uri | 3.1.2 | MIT |
| @jridgewell/sourcemap-codec | 1.5.5 | MIT |
| @jridgewell/trace-mapping | 0.3.31 | MIT |
| @oxc-project/types | 0.144.0 | MIT |
| @playwright/test | 1.62.1 | Apache-2.0 |
| @poppinss/colors | 4.1.6 | MIT |
| @poppinss/dumper | 0.6.5 | MIT |
| @poppinss/exception | 1.2.3 | MIT |
| @rolldown/binding-android-arm64 | 1.2.4 | MIT |
| @rolldown/binding-darwin-arm64 | 1.2.4 | MIT |
| @rolldown/binding-darwin-x64 | 1.2.4 | MIT |
| @rolldown/binding-freebsd-x64 | 1.2.4 | MIT |
| @rolldown/binding-linux-arm-gnueabihf | 1.2.4 | MIT |
| @rolldown/binding-linux-arm64-gnu | 1.2.4 | MIT |
| @rolldown/binding-linux-arm64-musl | 1.2.4 | MIT |
| @rolldown/binding-linux-ppc64-gnu | 1.2.4 | MIT |
| @rolldown/binding-linux-s390x-gnu | 1.2.4 | MIT |
| @rolldown/binding-linux-x64-gnu | 1.2.4 | MIT |
| @rolldown/binding-linux-x64-musl | 1.2.4 | MIT |
| @rolldown/binding-openharmony-arm64 | 1.2.4 | MIT |
| @rolldown/binding-win32-arm64-msvc | 1.2.4 | MIT |
| @rolldown/binding-win32-x64-msvc | 1.2.4 | MIT |
| @rolldown/pluginutils | 1.0.1 | MIT |
| @sindresorhus/is | 7.2.0 | MIT |
| @speed-highlight/core | 1.2.24 | CC0-1.0 |
| @sveltejs/acorn-typescript | 1.0.12 | MIT |
| @sveltejs/load-config | 0.2.3 | MIT |
| @sveltejs/vite-plugin-svelte | 7.3.0 | MIT |
| @types/estree | 1.0.9 | MIT |
| @types/node | 26.2.0 | MIT |
| @types/trusted-types | 2.0.7 | MIT |
| @typescript/native | 7.0.2 | Apache-2.0 |
| @typescript/typescript-aix-ppc64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-darwin-arm64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-darwin-x64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-freebsd-arm64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-freebsd-x64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-linux-arm | 7.0.2 | Apache-2.0 |
| @typescript/typescript-linux-arm64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-linux-loong64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-linux-mips64el | 7.0.2 | Apache-2.0 |
| @typescript/typescript-linux-ppc64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-linux-riscv64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-linux-s390x | 7.0.2 | Apache-2.0 |
| @typescript/typescript-linux-x64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-netbsd-arm64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-netbsd-x64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-openbsd-arm64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-openbsd-x64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-sunos-x64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-win32-arm64 | 7.0.2 | Apache-2.0 |
| @typescript/typescript-win32-x64 | 7.0.2 | Apache-2.0 |
| acorn | 8.18.0 | MIT |
| aria-query | 5.3.1 | Apache-2.0 |
| axobject-query | 4.1.0 | Apache-2.0 |
| blake3-wasm | 2.1.5 | MIT |
| chokidar | 4.0.3 | MIT |
| clsx | 2.1.1 | MIT |
| cookie | 1.1.1 | MIT |
| deepmerge | 4.3.1 | MIT |
| detect-libc | 2.1.2 | Apache-2.0 |
| devalue | 5.9.0 | MIT |
| error-stack-parser-es | 1.0.5 | MIT |
| esbuild | 0.28.1 | MIT |
| esm-env | 1.2.2 | MIT |
| esrap | 2.3.2 | MIT |
| fdir | 6.5.0 | MIT |
| fsevents | 2.3.2 | MIT |
| is-reference | 3.0.3 | MIT |
| kleur | 4.1.5 | MIT |
| lightningcss | 1.33.0 | MPL-2.0 |
| lightningcss-android-arm64 | 1.33.0 | MPL-2.0 |
| lightningcss-darwin-arm64 | 1.33.0 | MPL-2.0 |
| lightningcss-darwin-x64 | 1.33.0 | MPL-2.0 |
| lightningcss-freebsd-x64 | 1.33.0 | MPL-2.0 |
| lightningcss-linux-arm-gnueabihf | 1.33.0 | MPL-2.0 |
| lightningcss-linux-arm64-gnu | 1.33.0 | MPL-2.0 |
| lightningcss-linux-arm64-musl | 1.33.0 | MPL-2.0 |
| lightningcss-linux-x64-gnu | 1.33.0 | MPL-2.0 |
| lightningcss-linux-x64-musl | 1.33.0 | MPL-2.0 |
| lightningcss-win32-arm64-msvc | 1.33.0 | MPL-2.0 |
| lightningcss-win32-x64-msvc | 1.33.0 | MPL-2.0 |
| locate-character | 3.0.0 | MIT |
| magic-string | 0.30.21 | MIT |
| miniflare | 5.20260811.0-alpha | MIT |
| mri | 1.2.0 | MIT |
| nanoid | 3.3.18 | MIT |
| obug | 2.1.4 | MIT |
| path-to-regexp | 6.3.0 | MIT |
| pathe | 2.0.3 | MIT |
| picocolors | 1.1.1 | ISC |
| picomatch | 4.0.5 | MIT |
| playwright | 1.62.1 | Apache-2.0 |
| playwright-core | 1.62.1 | Apache-2.0 |
| postcss | 8.5.26 | MIT |
| readdirp | 4.1.2 | MIT |
| rolldown | 1.2.4 | MIT |
| sade | 1.8.1 | MIT |
| semver | 7.8.5 | ISC |
| sharp | 0.35.2 | Apache-2.0 |
| source-map-js | 1.2.1 | BSD-3-Clause |
| supports-color | 10.2.2 | MIT |
| svelte | 5.56.9 | MIT |
| svelte-check | 4.7.5 | MIT |
| tinyglobby | 0.2.17 | MIT |
| tslib | 2.8.1 | 0BSD |
| typescript | 6.0.3 | Apache-2.0 |
| undici | 7.29.0 | MIT |
| undici-types | 8.3.0 | MIT |
| unenv | 2.0.0-rc.24 | MIT |
| vite | 8.2.1 | MIT |
| vitefu | 1.1.3 | MIT |
| workerd | 1.20260811.1 | Apache-2.0 |
| wrangler | 4.122.0 | MIT OR Apache-2.0 |
| ws | 8.21.0 | MIT |
| youch | 4.1.0-beta.10 | MIT |
| youch-core | 0.3.3 | MIT |
| zimmerframe | 1.1.4 | MIT |

## Моделі

Ваги не розповсюджуються: доступ виключно через API постачальника.

| Модель | Доступ | Умови |
| --- | --- | --- |
| Claude (Anthropic) | через Amazon Bedrock | комерційні умови постачальника; ваги не розповсюджуються |
| Mistral, OpenAI gpt-oss, Qwen та інші на Bedrock | через Amazon Bedrock | умови відповідних постачальників; використовуються як резерв і для розробки |

## Дані

Публічних датасетів проєкт не використовує.

| Джерело | Звідки | Умови |
| --- | --- | --- |
| Історія покупок гостя | власні дані користувача через офіційний MCP «Сільпо» | не розповсюджуються; у публічні фікстури йдуть лише анонімізовані похідні (ADR-03) |
| Каталог і слоти «Сільпо» | офіційний MCP | зображення товарів і бренд не хостимо — лише посилання на CDN; логотип не використовуємо; сам каталог у репозиторій не їде (нижче) |

### Каталог у репозиторій НЕ їде, і це рішення, а не пропуск

Щоб відрізнити «м'ясний рулет» від «рулета з маком», продукт будує мапу
артикул-вузол обходом каталогу (18 філій, 49 415 товарів, 52 хв). Три яруси
напрацювань, і вони різні за суттю:

- **орфографічний словник** (191 слово: `мясний` -> `м'ясний`) -- публікується.
  Це правопис української мови, а не дані «Сільпо»: той самий список будується
  з будь-якого українського корпусу, і замісної вартості для них не має;
- **перелік стилізованих брендів** (51 слово, які не зводяться до однієї
  абетки) -- публікується з описом походження. Це назви торгових марок
  рядками, без логотипів і без стилю;
- **сам каталог** (назви, `slug`, `id`, ціни, залишки) -- **не публікується.**
  Три причини, і кожної досить окремо: це суттєве вилучення з чужої бази, а не
  похідна ідея; ціни й залишки протухають за тиждень, а публічний репозиторій
  вічний -- вийшов би файл, який виглядає як факт про «Сільпо» і бреше; і
  хакатон проводить саме «Сільпо», тож вивантажений каталог у нашому
  публічному репозиторії читається як «ми вас спарсили», а не як продукт.

Тому мапа не є артефактом репозиторію ВЗАГАЛІ. Вона живе там само, де вже
живе дерево категорій, -- у Postgres, куди її кладе крон (`db/categories.py`,
`komora-categories`). У git їде код, який її будує; дані лишаються в базі.

А в «Ідеях» стоїть протилежний бік цього ж: дайте вузол і фасовку полями в
API -- і обходити 858 листків по 18 філіях не доведеться нікому. Обхідний
шлях ми лікуємо пропозицією, а не мовчанням.
