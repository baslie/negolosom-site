#!/usr/bin/env python3
"""
Общие части инструментов выпуска: числительные, склонения, JSON-LD и разбор страниц.

Идея у всего файла одна: **у каждого факта одно место**. Номер версии живёт
в `payload`, история выпусков — в разметке `obnovleniya/index.html`, подписи экранов —
в разметке главной. Всё остальное — счётчики, числительные прописью, JSON-LD —
выводится из них, а не пишется руками во второй раз. Ровно потому, что второй раз
и разъезжается: `obnovleniya/index.html` держал `softwareVersion` 2.8.0 при версии
2.9.0, а внутри карточки 2.8.0 стояло 2.9.0.

Файл только объявляет функции. Точки входа — `apply-release.py` и `check-release.py`.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Страницы сайта. Порядок важен только для вывода.
HTML_PAGES = [
    "index.html",
    "obnovleniya/index.html",
    "voprosy/index.html",
    "policy/index.html",
    "404.html",
]


def setup_stdout() -> None:
    """Windows-консоль по умолчанию cp1251 и роняет вывод на первой же кириллице."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:  # pragma: no cover — старый Python
        pass


# ---------------------------------------------------------------------------
# Файлы
# ---------------------------------------------------------------------------


def read(rel: str, root: Path = ROOT) -> str:
    return (root / rel).read_text(encoding="utf-8")


def write(rel: str, text: str, root: Path = ROOT) -> None:
    """Переводы строк — LF: так велит `.gitattributes`, и так лежит весь сайт."""
    (root / rel).write_text(text, encoding="utf-8", newline="")


# ---------------------------------------------------------------------------
# Русские числительные и склонения
# ---------------------------------------------------------------------------

_ONES_M = [
    "", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять",
    "десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать",
    "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать",
]
_TENS = {20: "двадцать", 30: "тридцать", 40: "сорок", 50: "пятьдесят", 60: "шестьдесят"}
_FEMININE = {"один": "одна", "два": "две"}


def numeral(value: int, gender: str = "masculine") -> str:
    """
    Число прописью, 1…69. Род нужен только единице и двойке: «один выпуск», но
    «одна версия»; «два выпуска», но «две версии».
    """
    if not 1 <= value <= 69:
        raise ValueError(f"числительное {value} вне поддержанного диапазона 1…69")

    if value < 20:
        words = [_ONES_M[value]]
    else:
        tens, ones = divmod(value, 10)
        words = [_TENS[tens * 10]]
        if ones:
            words.append(_ONES_M[ones])

    if gender == "feminine":
        words[-1] = _FEMININE.get(words[-1], words[-1])
    return " ".join(words)


def plural(value: int, one: str, few: str, many: str) -> str:
    """Склонение существительного при числе: 1 выпуск, 2 выпуска, 5 выпусков."""
    rest100 = value % 100
    if 11 <= rest100 <= 14:
        return many
    rest10 = value % 10
    if rest10 == 1:
        return one
    if 2 <= rest10 <= 4:
        return few
    return many


#: Все формы, которые умеет выдавать `numeral` — для поиска «какое число сейчас стоит».
ANY_NUMERAL = "|".join(
    sorted(
        {numeral(n, g) for n in range(1, 70) for g in ("masculine", "feminine")},
        key=len,
        reverse=True,
    )
)

MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


@dataclass(frozen=True)
class Counter:
    """
    Счётчик, который сайт называет в тексте — цифрами и прописью.

    Места перечислены поимённо, а не ищутся по всему сайту, и это важно: слово
    «экрана» встречается в подписи обложки («логотип, заголовок и три экрана»),
    а «пятнадцать» — в «ещё пятнадцать языков». Без списка мест правка счётчика
    задела бы и их.
    """

    key: str
    noun: tuple[str, str, str]
    digit_files: tuple[str, ...]
    digit_expect: int
    word_files: tuple[str, ...]
    word_expect: int

    def forms(self) -> str:
        return "|".join(sorted(set(self.noun), key=len, reverse=True))


#: Где на сайте названы количества. Числа в `*_expect` — сколько раз правило обязано
#: сработать; изменилось место — правило покраснеет, и это единственный способ
#: заметить, что счётчик завёлся ещё где-то.
COUNTERS = (
    Counter(
        key="releases",
        noun=("выпуск", "выпуска", "выпусков"),
        digit_files=("index.html", "obnovleniya/index.html"),
        digit_expect=2,
        word_files=("obnovleniya/index.html", "llms.txt", "llms-full.txt"),
        word_expect=6,
    ),
    Counter(
        key="faq",
        noun=("ответ", "ответа", "ответов"),
        digit_files=(),
        digit_expect=0,
        word_files=("voprosy/index.html", "llms.txt"),
        word_expect=5,
    ),
    Counter(
        key="screens",
        noun=("экран", "экрана", "экранов"),
        digit_files=(),
        digit_expect=0,
        word_files=("llms.txt",),
        word_expect=1,
    ),
)


def date_words(iso: str) -> str:
    """«2026-09-22» -> «22 сентября 2026»."""
    year, month, day = (int(part) for part in iso.split("-"))
    return f"{day} {MONTHS[month - 1]} {year}"


# ---------------------------------------------------------------------------
# JSON-LD
# ---------------------------------------------------------------------------

_LD_BLOCK = re.compile(
    r'(?P<open>[ \t]*<script type="application/ld\+json">\n)'
    r"(?P<body>.*?)"
    r"(?P<close>\n[ \t]*</script>)",
    re.S,
)


@dataclass
class JsonLd:
    """Разобранный блок разметки вместе с местом, откуда он взят."""

    data: dict
    indent: str
    span: tuple[int, int]


def read_jsonld(html: str, where: str = "") -> JsonLd:
    match = _LD_BLOCK.search(html)
    if not match:
        raise ValueError(f"{where}: не нашёл блок application/ld+json")
    body = match.group("body")
    indent = re.match(r"[ \t]*", body).group(0)
    try:
        data = json.loads(body)
    except json.JSONDecodeError as error:
        raise ValueError(f"{where}: JSON-LD не разбирается — {error}") from error
    return JsonLd(data=data, indent=indent, span=match.span("body"))


def write_jsonld(html: str, block: JsonLd) -> str:
    """Собирает блок обратно с тем же отступом, что был у исходного."""
    dumped = json.dumps(block.data, ensure_ascii=False, indent=2)
    body = "\n".join(block.indent + line if line else line for line in dumped.split("\n"))
    start, end = block.span
    return html[:start] + body + html[end:]


def json_value_span(text: str, key: str, opener: str = "[", after: int = 0) -> tuple[int, int, str]:
    """
    Границы значения ключа в тексте JSON и отступ его строки.

    Нужно, чтобы править разметку точечно, а не пересобирать её целиком: `json.dumps`
    развернул бы написанные в одну строку `{ "@id": … }` и выдал бы диффом весь файл
    вместо двух строк. Скобки считаются с учётом строк — внутри значений встречаются
    и кавычки, и сами скобки.

    `after` сдвигает начало поиска. Он обязателен, когда ключ встречается дважды:
    на странице истории `itemListElement` есть и у «хлебной крошки», и у списка
    выпусков, и первым в тексте идёт как раз не тот.
    """
    closer = {"[": "]", "{": "}"}[opener]
    anchor = re.compile(rf'^(?P<indent>[ \t]*)"{re.escape(key)}":\s*{re.escape(opener)}',
                        re.M).search(text, after)
    if not anchor:
        raise ValueError(f"в JSON не нашёлся ключ «{key}»")

    start = text.index(opener, anchor.start())
    depth, index, in_string, escaped = 0, start, False, False
    while index < len(text):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return start, index + 1, anchor.group("indent")
        index += 1
    raise ValueError(f"в JSON не закрылось значение ключа «{key}»")


def replace_json_array(text: str, key: str, items: list[str], after: int = 0) -> str:
    """Подменяет массив целиком, сохраняя отступ исходной строки."""
    start, end, indent = json_value_span(text, key, "[", after)
    if not items:
        return text[:start] + "[]" + text[end:]

    inner = indent + "  "
    shifted = [
        "\n".join(inner + line if line else line for line in item.split("\n"))
        for item in items
    ]
    body = "[\n" + ",\n".join(shifted) + "\n" + indent + "]"
    return text[:start] + body + text[end:]


def replace_json_scalar(text: str, key: str, value: object, expect: int) -> str:
    """Подменяет скалярное значение ключа. Сработало не столько раз — ошибка."""
    dumped = json.dumps(value, ensure_ascii=False)
    pattern = rf'("{re.escape(key)}":\s*)(?:"[^"]*"|-?\d+(?:\.\d+)?|true|false|null)'
    new_text, count = re.subn(pattern, lambda m: m.group(1) + dumped, text)
    if count != expect:
        raise ValueError(f"ключ «{key}»: заменено {count} значений, ожидалось {expect}")
    return new_text


def graph_nodes(data: dict) -> list[dict]:
    """Узлы `@graph`, а если графа нет — сам объект."""
    return list(data.get("@graph", [data]))


def node_of_type(data: dict, wanted: str) -> dict | None:
    for node in graph_nodes(data):
        types = node.get("@type")
        types = types if isinstance(types, list) else [types]
        if wanted in types:
            return node
    return None


# ---------------------------------------------------------------------------
# Разбор страниц
# ---------------------------------------------------------------------------


@dataclass
class Release:
    """Выпуск, как он записан в разметке страницы истории."""

    version: str
    anchor: str
    date: str
    bullets: list[str] = field(default_factory=list)
    note: str | None = None


_RELEASE_BLOCK = re.compile(
    r'<article class="release" id="(?P<anchor>[^"]+)">(?P<body>.*?)</article>', re.S
)
_RELEASE_VERSION = re.compile(r'<h2 class="release__version">(?P<v>[^<]+)</h2>')
_RELEASE_DATE = re.compile(r'<time class="release__date" datetime="(?P<d>[^"]+)"')
_RELEASE_NOTE = re.compile(r'<p class="release__note">(?P<t>.*?)</p>', re.S)
_BULLET = re.compile(r"<li>(?P<t>.*?)</li>", re.S)


def parse_releases(html: str) -> list[Release]:
    """История выпусков из разметки — источник правды для JSON-LD и счётчиков."""
    releases = []
    for match in _RELEASE_BLOCK.finditer(html):
        body = match.group("body")
        version = _RELEASE_VERSION.search(body)
        date = _RELEASE_DATE.search(body)
        if not version or not date:
            raise ValueError(f"выпуск {match.group('anchor')}: нет версии или даты")
        note = _RELEASE_NOTE.search(body)
        releases.append(
            Release(
                version=version.group("v").strip(),
                anchor=match.group("anchor"),
                date=date.group("d").strip(),
                bullets=[squash(b.group("t")) for b in _BULLET.finditer(body)],
                note=squash(note.group("t")) if note else None,
            )
        )
    if not releases:
        raise ValueError("на странице истории нет ни одного выпуска")
    return releases


_SLIDE = re.compile(
    r'<li class="carousel__slide">.*?'
    r'<img src="/assets/img/screens/(?P<name>[a-z0-9-]+)-244\.webp"[^>]*?'
    r'alt="(?P<alt>[^"]*)"',
    re.S,
)


def parse_slides(html: str) -> list[tuple[str, str]]:
    """Пары «смысловое имя экрана, подпись alt» в порядке карусели."""
    slides = [(m.group("name"), m.group("alt")) for m in _SLIDE.finditer(html)]
    if not slides:
        raise ValueError("на главной не нашлось ни одного слайда карусели")
    return slides


def squash(text: str) -> str:
    """Схлопывает переносы и повторные пробелы: разметка переносит, текст — нет."""
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------------------
# Текстовые правила
# ---------------------------------------------------------------------------


@dataclass
class Rule:
    """
    Одна текстовая замена.

    `expect` обязателен: правило, сработавшее не то число раз, валит прогон.
    Это не педантизм — именно так ловится «на странице появилось ещё одно место
    с версией, а про него забыли». Значение `"each"` означает «хотя бы раз
    в каждом из перечисленных файлов».

    `repl` — строка подстановки либо функция от совпадения: числительным нужна
    функция, чтобы «Пятнадцать» в начале предложения не стало строчным.
    """

    name: str
    files: list[str]
    pattern: str
    repl: object
    expect: int | str


def apply_rules(rules: list[Rule], root: Path = ROOT, dry_run: bool = False) -> list[str]:
    """Применяет правила и возвращает список изменившихся файлов."""
    hits: dict[str, int] = {}
    texts: dict[str, str] = {}

    for rule in rules:
        for rel in rule.files:
            text = texts.get(rel)
            if text is None:
                text = texts[rel] = read(rel, root)
            new_text, count = re.subn(rule.pattern, rule.repl, text)
            hits[rule.name] = hits.get(rule.name, 0) + count
            if rule.expect == "each" and count == 0:
                raise SystemExit(f"правило «{rule.name}»: ни одного совпадения в {rel}")
            texts[rel] = new_text

    problems = [
        f"правило «{rule.name}»: совпадений {hits.get(rule.name, 0)}, ожидалось {rule.expect}"
        for rule in rules
        if isinstance(rule.expect, int) and hits.get(rule.name, 0) != rule.expect
    ]
    if problems:
        raise SystemExit("Правила замен не сошлись:\n  - " + "\n  - ".join(problems))

    changed = []
    for rel, text in texts.items():
        if text != read(rel, root):
            changed.append(rel)
            if not dry_run:
                write(rel, text, root)
    return changed
