#!/usr/bin/env python3
"""
Неразрывные пробелы в видимом тексте страниц.

    python tools/typograph.py            # расставить на всех страницах
    python tools/typograph.py --check    # только показать, где не хватает

Неразрывный пробел (U+00A0) не даёт строке оборваться в неправильном месте:
предлог «в» не повисает в конце строки, «30 МБ» не разъезжается на две,
тире не начинает строку. CSS (`text-wrap: balance` и `pretty`) это лишь
смягчает: запретить такой перенос он не умеет.

Правила:

- после коротких слов — однобуквенных и двухбуквенных («в», «на», «не», «и»)
  и предлогов и союзов из трёх букв («для», «без», «при», «или»): «в ленте»;
- между числом и словом за ним: «30 МБ», «10 секунд», «5 октября»;
- перед тире: «Включите в настройках — и …»;
- перед частицами «ли», «же», «бы».

Трогается только текст между тегами внутри `<body>`. Не трогаются атрибуты
(`alt`, `content`), `<head>` с заголовком и описанием, JSON-LD и прочие `<script>`,
`<style>`, `<pre>`, `<code>`, `<svg>` и комментарии — там неразрывный пробел либо
не нужен, либо попал бы в данные. Текстовые файлы для моделей (`llms*.txt`)
тоже не трогаются: строк там не переносят.

Символ — сам U+00A0, а не `&nbsp;`. Так его понимают `squash()` и все сверки
инструментов: `\\s` в регулярных выражениях Python его ловит, и в JSON-LD,
собранный из пунктов выпусков, уходит обычный пробел, а не строка `&nbsp;`.

Правка идемпотентна: второй проход по готовому тексту не меняет ни байта.
`sitelib.write()` пропускает через типограф каждую HTML-страницу, поэтому
текст, вставленный `apply-release.py`, приходит на сайт уже с неразрывными
пробелами. Текст, вписанный руками, расставляет запуск этого файла,
а `check-release.py` валит выпуск, если где-то их не хватает.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

NBSP = " "

#: Пробел в шаблонах правил, которые ищут текст на страницах: после типографа
#: на месте обычного пробела может стоять неразрывный.
SP = "[  ]"

_SHORT_3 = "без|для|над|под|при|про|обо|изо|или"
#: Короткое слово целиком: строчное или с заглавной в начале предложения.
#: Аббревиатуры из двух заглавных («МБ», «ГБ») сюда не попадают: «МБ» привязан
#: к числу перед ним, а к следующему слову привязывать его незачем.
#: Частицы «ли», «же», «бы» привязываются к слову перед ними, а не после.
_SHORT = rf"(?!(?:ли|же|бы)\s)(?:[а-яё]{{1,2}}|[А-ЯЁ][а-яё]?|(?i:{_SHORT_3}))"
_WORD_EDGE = r"(?<![\w\-])"

_AFTER_SHORT = re.compile(rf"{_WORD_EDGE}({_SHORT})\s+(?=\S)")
_AFTER_NUMBER = re.compile(r"(?<![\w.,:/])(\d+)\s+(?=[A-Za-zА-Яа-яЁё])")
_BEFORE_DASH = re.compile(r"(?<=\S)\s+(?=—)")
_BEFORE_PARTICLE = re.compile(r"(?<=[\w»)])\s+(?=(?:ли|же|бы)(?![\w\-]))")

#: Короткое слово или число в конце текстового узла, за которым идёт строчный тег:
#: «в <a href>настройках</a>».
_TAIL = re.compile(rf"(?:{_WORD_EDGE}{_SHORT}|(?<![\w.,:/])\d+)\s+$")
_HEAD_DASH = re.compile(r"^\s+(?=—)")

INLINE = {"a", "abbr", "b", "code", "em", "i", "kbd", "mark", "q", "small", "span",
          "strong", "sub", "sup", "time"}

#: Теги, внутрь которых типограф не заходит, и всё остальное, что текстом не является.
_TOKEN = re.compile(
    r"<!--.*?-->"
    r"|<(?P<raw>script|style|pre|code|textarea|svg)\b.*?</(?P=raw)\s*>"
    r"|<[^>]*>",
    re.S | re.I,
)
_TAG_NAME = re.compile(r"<\s*(/?)\s*([a-zA-Z][\w-]*)")


def _tag(token: str) -> tuple[bool, str]:
    """(закрывающий ли, имя) для тега; для комментария — пустое имя."""
    match = _TAG_NAME.match(token)
    if not match:
        return False, ""
    return bool(match.group(1)), match.group(2).lower()


def fix_text(text: str) -> str:
    """Правила внутри одного текстового узла."""
    text = _AFTER_SHORT.sub(lambda m: m.group(1) + NBSP, text)
    text = _AFTER_NUMBER.sub(lambda m: m.group(1) + NBSP, text)
    text = _BEFORE_DASH.sub(NBSP, text)
    text = _BEFORE_PARTICLE.sub(NBSP, text)
    return text


def typograph(html: str) -> str:
    """Расставляет неразрывные пробелы в тексте страницы. Идемпотентна."""
    return _run(html, None)


def missing(html: str) -> list[str]:
    """Места, где типограф поставил бы неразрывный пробел, — с кусочком текста вокруг."""
    places: list[str] = []
    _run(html, places)
    return places


def _run(html: str, places: list[str] | None) -> str:
    body = re.search(r"<body\b", html, re.I)
    start = body.start() if body else 0
    head, rest = html[:start], html[start:]

    parts: list[str] = []
    position = 0
    previous = ""
    for match in _TOKEN.finditer(rest):
        text = rest[position:match.start()]
        if text:
            parts.append(_fix_node(text, previous, match.group(0), places))
        parts.append(match.group(0))
        previous = match.group(0)
        position = match.end()
    if position < len(rest):
        parts.append(_fix_node(rest[position:], previous, "", places))
    return head + "".join(parts)


def _fix_node(text: str, previous: str, following: str, places: list[str] | None) -> str:
    fixed = fix_text(text)

    closing, name = _tag(following)
    if following and not closing and name in INLINE:
        fixed = _TAIL.sub(lambda m: m.group(0).rstrip() + NBSP, fixed)

    closing, name = _tag(previous)
    if previous and closing and name in INLINE:
        fixed = _HEAD_DASH.sub(NBSP, fixed)

    if places is not None and fixed != text:
        places.extend(_changed_gaps(text, fixed))
    return fixed


def _changed_gaps(text: str, fixed: str) -> list[str]:
    """
    Пробелы, которые типограф заменил. Правила меняют только пробельные промежутки,
    и пробельный класс регулярок ловит неразрывный пробел, поэтому разбиение по промежуткам у исходника
    и результата совпадает по числу кусков — их можно сравнить попарно.
    """
    before = re.split(r"(\s+)", text)
    after = re.split(r"(\s+)", fixed)
    gaps = []
    for index in range(1, min(len(before), len(after)), 2):
        if before[index] != after[index]:
            left = before[index - 1][-20:] if index - 1 >= 0 else ""
            right = before[index + 1][:20] if index + 1 < len(before) else ""
            gaps.append(f"«{left}␣{right}»")
    return gaps or ["«" + text.strip()[:40] + "»"]


def main() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from sitelib import HTML_PAGES, read, setup_stdout, write

    setup_stdout()
    parser = argparse.ArgumentParser(description="Неразрывные пробелы на страницах сайта")
    parser.add_argument("--check", action="store_true", help="только показать места")
    args = parser.parse_args()

    total = 0
    for rel in HTML_PAGES:
        html = read(rel)
        places = missing(html)
        total += len(places)
        if not places:
            continue
        print(f"{rel}: {len(places)}")
        if args.check:
            for place in places[:10]:
                print(f"    {place}")
            if len(places) > 10:
                print(f"    … и ещё {len(places) - 10}")
        else:
            write(rel, html)  # write() сам пропускает страницу через типограф

    if args.check and total:
        raise SystemExit(1)
    print("Неразрывные пробелы на месте" if not total else
          f"{'Не хватает' if args.check else 'Расставлено'}: {total}")


if __name__ == "__main__":
    main()
