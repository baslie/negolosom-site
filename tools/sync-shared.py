#!/usr/bin/env python3
"""Разносит общие куски разметки из index.html по остальным страницам.

Сайт собран без сборщика, поэтому шапка, меню, панель скачивания, подвал и
плавающая кнопка физически повторяются в каждом файле. Чтобы копии не
разъезжались, каждая обёрнута парой комментариев:

    <!-- #region @shared:footer -->
    ...
    <!-- #endregion @shared:footer -->

Источник правды — index.html. Правите блок там, запускаете скрипт, и он
переписывает содержимое одноимённых блоков во всех остальных страницах.
Блоки, которых на странице нет, просто пропускаются.

Две правки применяются на лету, потому что шапка всё-таки чуть отличается:
  * класс site-header--home остаётся только на главной (там кнопка «Скачать»
    проявляется лишь после прокрутки — на первом экране она избыточна);
  * ссылке текущего раздела проставляется aria-current="page".

Запуск:  python tools/sync-shared.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "index.html"

BLOCKS = ("header", "menu", "download", "footer", "fab")

# Страница -> какой ссылке в шапке ставить aria-current.
TARGETS = {
    "obnovleniya/index.html": "/obnovleniya/",
    "voprosy/index.html": "/voprosy/",
    "politika-privatnosti/index.html": None,
    "404.html": None,
}


def region(name: str) -> re.Pattern:
    """Маркер может нести пояснение после имени блока, поэтому хвост до -->
    разрешён: <!-- #region @shared:header — правишь здесь -->."""
    return re.compile(
        r"(<!-- #region @shared:" + name + r"[^>]*-->)(.*?)"
        r"(<!-- #endregion @shared:" + name + r"[^>]*-->)",
        re.S,
    )


def main() -> None:
    # Консоль Windows по умолчанию cp1251/cp1252 и спотыкается о кириллицу.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

    src = SOURCE.read_text(encoding="utf-8")

    parts = {}
    for name in BLOCKS:
        found = region(name).search(src)
        if not found:
            sys.exit(f"в index.html нет блока @shared:{name}")
        parts[name] = found.group(2)

    for rel, current in TARGETS.items():
        path = ROOT / rel
        if not path.exists():
            print(f"пропущено (файла нет): {rel}")
            continue

        text = path.read_text(encoding="utf-8")
        touched = []

        for name in BLOCKS:
            body = parts[name]
            # На главной якоря короткие (#ekrany) — их перехватывает Lenis и
            # доводит плавно. На остальных страницах такой ссылке некуда
            # вести, поэтому делаем её абсолютной.
            body = body.replace('href="#', 'href="/#')

            if name == "header":
                if current:
                    body = body.replace(
                        f'<a class="nav__link" href="{current}">',
                        f'<a class="nav__link" href="{current}" aria-current="page">')
            new, n = region(name).subn(
                lambda m, b=body: m.group(1) + b + m.group(3), text)
            if n:
                text = new
                touched.append(name)

        path.write_text(text, encoding="utf-8")
        print(f"{rel}: {', '.join(touched) if touched else 'общих блоков нет'}")


if __name__ == "__main__":
    main()
