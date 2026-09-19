#!/usr/bin/env python3
"""Готовит скриншоты приложения для карусели на главной.

Источник — экспорт из макета, он лежит вне этого репозитория:
    ~/Desktop/negolosom/design/site-assets/screen-*.png
Другой каталог задаётся переменной окружения NEGOLOSOM_DESIGN.
Десять PNG 1080x2400. Соотношение 9:20 совпадает с карточкой карусели
(244x542), поэтому кадрировать не нужно — только уменьшить.

Результат: assets/img/screens/<имя>-<ширина>.{avif,webp}
Ширины 244 (DPR 1) и 488 (DPR 2 и 3). PNG-фолбэка нет: WebP понимают все
браузеры с 2020 года, AVIF — около 95 %.

Запуск:  python tools/build-images.py
"""

import os
from pathlib import Path
from PIL import Image

SRC = Path(os.environ.get(
    "NEGOLOSOM_DESIGN",
    Path.home() / "Desktop" / "negolosom" / "design" / "site-assets",
))
OUT = Path(__file__).resolve().parent.parent / "assets" / "img" / "screens"
WIDTHS = (244, 488)

# Исходное имя -> смысловое имя на сайте.
NAMES = {
    "screen-01-empty-light": "empty",
    "screen-02-list-light": "list",
    "screen-03-settings-light": "settings",
    "screen-04-list-dark": "list-dark",
    "screen-05-card-light": "card",
    "screen-06-recording-light": "recording",
    "screen-07-transcribing-light": "transcribing",
    "screen-08-export-light": "export",
    "screen-09-onboarding-light": "onboarding",
    "screen-10-search-light": "search",
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    for stem, name in sorted(NAMES.items(), key=lambda kv: kv[1]):
        src = SRC / f"{stem}.png"
        if not src.exists():
            raise SystemExit(f"нет исходника: {src}")

        # Альфа у исходников сплошная — RGB экономит вес без потерь.
        im = Image.open(src).convert("RGB")

        for width in WIDTHS:
            height = round(width * im.height / im.width)
            resized = im.resize((width, height), Image.LANCZOS)
            avif = OUT / f"{name}-{width}.avif"
            webp = OUT / f"{name}-{width}.webp"
            resized.save(avif, quality=58, speed=4)
            resized.save(webp, quality=80, method=6)
            total += 2
            print(f"{name}-{width}: avif {avif.stat().st_size // 1024} КБ, "
                  f"webp {webp.stat().st_size // 1024} КБ")

    print(f"\nготово: {total} файлов, {sum(f.stat().st_size for f in OUT.iterdir()) // 1024} КБ")


if __name__ == "__main__":
    main()
