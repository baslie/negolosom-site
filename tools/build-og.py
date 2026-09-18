#!/usr/bin/env python3
"""Превращает снятый скриншот заготовки в /assets/img/og-cover.jpg.

Обложку рендерит браузер, а не Pillow: Pillow не растрирует SVG (логотип) и
потребовал бы отдельного TTF с ручным кернингом кириллицы. Рендер страницей
переиспользует боевой styles.css, поэтому обложка не разъезжается с сайтом.

Как пересобрать обложку целиком:
    1. python -m http.server 8321
    2. открыть http://127.0.0.1:8321/tools/og/ в окне ровно 1200x630
    3. сохранить скриншот вьюпорта как tools/og/og-cover.png
    4. python tools/build-og.py

Иконка для iOS снимается так же со страницы tools/og/icon.html в окне
180x180 и сохраняется сразу в assets/img/apple-touch-icon.png — конвертация
ей не нужна.
"""

from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "tools" / "og" / "og-cover.png"
OUT = ROOT / "assets" / "img" / "og-cover.jpg"
SIZE = (1200, 630)


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"нет скриншота: {SRC} (см. инструкцию в шапке файла)")

    im = Image.open(SRC).convert("RGB")
    if im.size != SIZE:
        im = im.resize(SIZE, Image.LANCZOS)

    # progressive=True — превью подгружается постепенно, это заметно в лентах,
    # где обложку показывают до полной загрузки.
    im.save(OUT, quality=86, optimize=True, progressive=True)
    print(f"{OUT.relative_to(ROOT)}: {OUT.stat().st_size // 1024} КБ, {im.size[0]}x{im.size[1]}")


if __name__ == "__main__":
    main()
