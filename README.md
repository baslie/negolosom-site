# negolosom.ru

Сайт Android-приложения **«Не пиши голосовое!»** — голосовые заметки с локальным распознаванием
речи на русском. Работает офлайн, без облака и аккаунтов, на модели
[GigaAM v3](https://github.com/salute-developers/GigaAM).

Живой сайт: [negolosom.ru](https://negolosom.ru)

## Стек

Статический сайт **без сборщика**: HTML, один CSS-файл, один JS-файл. Ни `package.json`, ни
`node_modules`, ни шага сборки — что лежит в репозитории, то и отдаётся.

```
index.html                       главная, девять секций
obnovleniya/index.html           история версий, 12 выпусков
voprosy/index.html               восемь вопросов с якорями
policy/index.html  политика конфиденциальности
404.html                         страница не найдена (GitHub Pages подхватывает сам)

assets/
  css/styles.css                 весь стиль сайта, 23 секции по оглавлению в шапке файла
  js/main.js                     вся интерактивность
  js/vendor/                     UMD-сборки библиотек, см. VENDOR.md
  fonts/                         Source Sans 3, вариативный woff2, кириллица + латиница
  img/logo.svg                   логотип, он же favicon
  img/og-cover.jpg               обложка для соцсетей 1200x630
  img/apple-touch-icon.png       иконка для iOS 180x180
  img/screens/                   девять экранов приложения, AVIF и WebP в ширинах 244 и 488

tools/                           утилиты, которые НЕ участвуют в отдаче сайта
  build-images.py                скриншоты приложения -> AVIF/WebP
  build-og.py                    скриншот заготовки -> og-cover.jpg
  og/                            заготовки обложки и иконки
  sync-shared.py                 разносит общие блоки разметки по страницам
```

## Запуск

```bash
python -m http.server 8000
```

Открыть <http://127.0.0.1:8000/>. Адреса со слешем (`/voprosy/`) сервер отдаёт из
`voprosy/index.html` — так же, как GitHub Pages.

## Деплой

GitHub Pages из ветки `main`, корень репозитория. Домен `negolosom.ru` подключён через `CNAME`.
Отдельного шага сборки нет: `git push` — и через минуту обновилось.

Файл `.nojekyll` отключает обработку Jekyll: без него Pages игнорировал бы каталоги,
начинающиеся с подчёркивания.

## Как вносить правки

### Общие блоки разметки

Шапка, мобильное меню, панель скачивания, подвал и плавающая кнопка физически повторяются в
каждом файле — сборщика, который их подставит, тут нет. Чтобы копии не разъезжались, каждая
обёрнута маркерами:

```html
<!-- #region @shared:footer -->
...
<!-- #endregion @shared:footer -->
```

Источник правды — `index.html`. Правите блок там и запускаете:

```bash
python tools/sync-shared.py
```

Скрипт перепишет одноимённые блоки во всех остальных страницах и заодно подставит
`aria-current="page"` нужной ссылке и сделает якоря абсолютными. **Правки, внесённые в общий
блок мимо `index.html`, будут затёрты.**

### Картинки экранов

Исходники живут вне этого репозитория —
`C:\Users\Roman\Desktop\negolosom\design\site-assets\screen-*.png` (девять PNG 1080×2400,
экспорт из макета `website.pen`). После замены исходников:

```bash
python tools/build-images.py
```

### Обложка для соцсетей

1. `python -m http.server 8000`
2. открыть <http://127.0.0.1:8000/tools/og/> в окне ровно 1200×630, снять скриншот вьюпорта
   в `tools/og/og-cover.png`
3. `python tools/build-og.py`

Иконка для iOS снимается так же со страницы `tools/og/icon.html` в окне 180×180 и сохраняется
сразу в `assets/img/apple-touch-icon.png`.

### Новый выпуск приложения

Номер версии и даты разъезжаются по многим файлам, а сборщика нет — пройдите по списку целиком:

- [ ] `obnovleniya/index.html` — новый блок выпуска, `numberOfItems` и `itemListElement` в JSON-LD
- [ ] `obnovleniya/index.html` — `article:modified_time` и `dateModified`
- [ ] `index.html` — блок «Что нового» (две последние версии) и подпись под кнопками
- [ ] `index.html` — `softwareVersion` и `dateModified` в JSON-LD
- [ ] `sitemap.xml` — `lastmod` изменившихся страниц
- [ ] `llms.txt` — номер версии и дата в абзаце после `>`
- [ ] `llms-full.txt` — шапка и новый выпуск в разделе истории версий
- [ ] `voprosy/index.html` и `policy/index.html` — если выпуск меняет ответы или
      поведение с данными, поправить и текст, и `dateModified`

После публикации — пинг поисковиков (Яндекс и Bing понимают IndexNow):

```
uv run --directory C:/Users/Roman/Desktop/seo-geo-tools seo-geo indexnow submit   --project negolosom https://negolosom.ru/ https://negolosom.ru/obnovleniya/
```

### Иконка сайта

`favicon.ico` собирается из `assets/img/apple-touch-icon.png` командой `python tools/build-favicon.py`.
Логотип лежит в SVG, но растрировать его нечем: Pillow не читает SVG. Пересобирать нужно только
если поменялся логотип — тогда сначала переснимите `apple-touch-icon.png` (см. выше).

### Библиотеки

GSAP + ScrollTrigger, Lenis, Embla Carousel с двумя плагинами лежат в `assets/js/vendor/` с
версией в имени файла. Версии, имена глобалей, лицензии и SHA-256 — в
[`assets/js/vendor/VENDOR.md`](assets/js/vendor/VENDOR.md).

Сайт полностью работоспособен без них: карусель остаётся горизонтальным скроллом со
scroll-snap, меню и подсказки написаны на голом DOM, появление секций включается только после
успешной инициализации GSAP.

### Кэш

Сборщика нет, значит нет и хеша в имени файла. `styles.css` и `main.js` подключены с
`?v=ГГГГ-ММ-ДД` — при заметной правке **поменяйте дату во всех пяти HTML-файлах**, иначе у
вернувшихся посетителей останется старая версия. Если правите второй раз за день, добавьте
к дате номер: `?v=2026-09-18-2`.

## Что где лежит

| Что | Где |
|---|---|
| Макет | `C:\Users\Roman\Desktop\negolosom\design\website.pen` (pen.dev) |
| Исходники скриншотов | там же, `design/site-assets/` |
| Репозиторий приложения | `baslie/negolosom` (приватный) |
| APK и журнал изменений | `baslie/negolosom-releases` (публичный) |
| Аналитика сайта | Яндекс.Метрика, счётчик 108682111, Вебвизор включён |
