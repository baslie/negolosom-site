# Вендорные библиотеки

Файлы скачаны с jsDelivr с прибитой версией и лежат в репозитории, чтобы сайт не
зависел от стороннего CDN. Сборки — UMD/IIFE, подключаются обычными
`<script defer>` и кладут глобали (не ES-модули: `type="module"` спрятал бы их в
модульную область видимости).

Порядок подключения обязателен: `gsap` → `ScrollTrigger` → `lenis` → `embla` →
плагины Embla → `main.js`. `defer` сохраняет порядок, `async` — нет.

Обновление: скачать новый файл под новым именем (версия в имени — это бесплатный
cache-bust), поменять пути в `<script>` на всех страницах, пересчитать хеши.

| Файл | Пакет | Версия | Глобаль | Лицензия |
|---|---|---|---|---|
| `gsap-3.15.0.min.js` | gsap | 3.15.0 | `window.gsap` | GreenSock Standard «No Charge» |
| `ScrollTrigger-3.15.0.min.js` | gsap | 3.15.0 | `window.ScrollTrigger` | GreenSock Standard «No Charge» |
| `lenis-1.3.26.min.js` | lenis | 1.3.26 | `window.Lenis` | MIT |
| `embla-carousel-8.6.0.umd.js` | embla-carousel | 8.6.0 | `window.EmblaCarousel` | MIT |
| `embla-carousel-auto-scroll-8.6.0.umd.js` | embla-carousel-auto-scroll | 8.6.0 | `window.EmblaCarouselAutoScroll` | MIT |
| `embla-carousel-wheel-gestures-8.1.0.umd.js` | embla-carousel-wheel-gestures | 8.1.0 | `window.EmblaCarouselWheelGestures` | MIT |

Мажорная версия плагинов Embla обязана совпадать с мажорной версией ядра.

Источник: `https://cdn.jsdelivr.net/npm/<пакет>@<версия>/<путь>`.
Пути внутри пакетов: gsap — `dist/`, lenis — `dist/`, embla-carousel и
auto-scroll — корень пакета, wheel-gestures — `dist/`.

## SHA-256

```
b0b14d67b55b0c43c756ac0b106cfcb09d0879945f6ead64451065b0672916a2  ScrollTrigger-3.15.0.min.js
f05b5dbfe37d79b636b9db74ad04ed5e99b4bce369d781b0fb38b0b2ac619e66  embla-carousel-8.6.0.umd.js
1dc04a4b1df212c036572aaca908fd255c86cfb3d05b6cab29a10415c3d588e4  embla-carousel-auto-scroll-8.6.0.umd.js
234cdd36e7712a7f6c61e916a204e467255ed47310bb3cbaa56209130075ed3c  embla-carousel-wheel-gestures-8.1.0.umd.js
92bb9a96476f983d212a2bc4f54c889039c1696dd4461d40a736860938570fbb  gsap-3.15.0.min.js
53195c9797e7ce7bf9d7fa9242b08209e57f46de4c9dac126a6494fa780e3346  lenis-1.3.26.min.js
```

Пересчёт: `sha256sum assets/js/vendor/*.js`
