#!/usr/bin/env python3
"""Собирает /favicon.ico из assets/img/apple-touch-icon.png.

Логотип лежит в SVG, но растрировать его нечем: Pillow не читает SVG, а
ImageMagick в системе нет. Иконка для iOS — уже готовый растр того же
логотипа на фирменном фоне, снятый браузером со страницы tools/og/icon.html
(см. шапку build-og.py), поэтому .ico собирается из неё без потери качества.

Зачем .ico, если в разметке есть SVG-иконка: браузеры возьмут SVG, а боты,
превью-сервисы и старые клиенты дёргают /favicon.ico по соглашению — без
файла там отдаётся страница 404.

Запуск:
    python tools/build-favicon.py
"""

import sys
from pathlib import Path

from PIL import Image

# Консоль Windows по умолчанию cp1252 и падает на кириллице в выводе.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "img" / "apple-touch-icon.png"
OUT = ROOT / "favicon.ico"
SIZES = [(16, 16), (32, 32), (48, 48)]


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"нет исходника: {SRC} (см. инструкцию в шапке файла)")

    im = Image.open(SRC).convert("RGBA")
    im.save(OUT, format="ICO", sizes=SIZES)

    sizes = ", ".join(f"{w}x{h}" for w, h in SIZES)
    print(f"{OUT.relative_to(ROOT)}: {OUT.stat().st_size // 1024} КБ, размеры {sizes}")


if __name__ == "__main__":
    main()
