# negolosom.ru

Лендинг Android-приложения **«Не пиши голосовое!»** — голосовые заметки с локальным распознаванием речи на русском. Работает офлайн, без облака и аккаунтов, на модели [GigaAM v3](https://github.com/salute-developers/GigaAM).

Сайт: [negolosom.ru](https://negolosom.ru)

## Стек

Одностраничник без сборщика: `index.html` + `styles.css`, ассеты (`logo.svg`, скриншоты `1.png`/`2.png`/`3.png`) в `assets/`. Шрифт — Source Sans 3 (Google Fonts). OG-изображение — `screens/screens.jpg`.

## Запуск

```bash
python -m http.server 8000
```

## Деплой

GitHub Pages из `main`, корень репозитория. Домен `negolosom.ru` подключён через `CNAME`.
