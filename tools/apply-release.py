#!/usr/bin/env python3
"""
Применяет релизный payload к сайту.

    python tools/apply-release.py --payload ../negolosom/build/site-payload/latest.json

Что делает инструмент: вставляет заготовку нового выпуска (на страницу истории,
на главную и в `llms-full.txt`), пересобирает всю разметку JSON-LD из самой страницы
и обновляет всё производное — версию, даты, `?v=`, счётчики цифрами и прописью,
`sitemap.xml` и текстовые файлы для моделей. В конце разносит общие блоки
через `sync-shared.py`.

Чего инструмент **не** делает: не переписывает прозу. Формулировки выпусков на сайте
намеренно короче витринных, карточки «Возможности» и вопросы FAQ пишутся руками.
Заготовка нового выпуска приезжает текстом из журнала — её потом правят, и повторный
прогон её не тронет: вставка идёт только там, где выпуска ещё нет.

Идемпотентность обязательна: второй прогон подряд обязан не менять ни байта.
Это проверяет `--selftest`.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sitelib import (  # noqa: E402
    ANY_NUMERAL,
    COUNTERS,
    HTML_PAGES,
    ROOT,
    Counter,
    Rule,
    apply_rules,
    date_words,
    json_value_span,
    node_of_type,
    numeral,
    parse_releases,
    parse_slides,
    plural,
    read,
    read_jsonld,
    replace_json_array,
    replace_json_scalar,
    setup_stdout,
    write,
)

SITE = "https://negolosom.ru"


# ---------------------------------------------------------------------------
# Вставка заготовок
# ---------------------------------------------------------------------------


def insert_history_block(root: Path, release: dict) -> bool:
    """Заготовка выпуска на страницу истории. Уже есть — не трогаем."""
    rel = "obnovleniya/index.html"
    html = read(rel, root)
    if f'id="{release["anchor"]}"' in html:
        return False

    bullets = "\n".join(f"            <li>{b}</li>" for b in release["bullets"])
    block = (
        f'        <article class="release" id="{release["anchor"]}">\n'
        f'          <div class="release__meta">\n'
        f'            <h2 class="release__version">{release["version"]}</h2>\n'
        f'            <time class="release__date" datetime="{release["date"]}">'
        f"{date_words(release['date'])}</time>\n"
        f"          </div>\n"
        f'          <ul class="bullets">\n{bullets}\n          </ul>\n'
        f"        </article>\n\n"
    )
    anchor = '<div class="release-list" data-reveal-group>\n'
    if anchor not in html:
        raise SystemExit(f"{rel}: не нашёл контейнер списка выпусков")
    write(rel, html.replace(anchor, anchor + block, 1), root)
    return True


_CARD = re.compile(r'[ \t]*<article class="card release-card">.*?</article>\n', re.S)


def insert_main_card(root: Path, release: dict, history: list[dict]) -> bool:
    """
    Заготовка карточки на главной. Главная показывает ровно две последние версии,
    поэтому третья уезжает: её текст остаётся на странице истории.
    """
    rel = "index.html"
    html = read(rel, root)
    if f'release-card__version">Версия {release["version"]}<' in html:
        return False

    bullets = "\n".join(f"          <li>{b}</li>" for b in release["bullets"])
    card = (
        f'      <article class="card release-card">\n'
        f'        <div class="release-card__head">\n'
        f'          <div class="release-card__vrow">\n'
        f'            <h3 class="release-card__version">Версия {release["version"]}</h3>\n'
        f'            <span class="tag tag--plain">Актуальная версия</span>\n'
        f"          </div>\n"
        f'          <time class="release-card__date" datetime="{release["date"]}">'
        f"{date_words(release['date'])}</time>\n"
        f"        </div>\n"
        f'        <ul class="bullets">\n{bullets}\n        </ul>\n'
        f"      </article>\n"
    )
    anchor = '<div class="releases" data-reveal-group>\n'
    if anchor not in html:
        raise SystemExit(f"{rel}: не нашёл контейнер карточек «Что нового»")
    html = html.replace(anchor, anchor + card + "\n", 1)

    cards = _CARD.findall(html)
    for extra in cards[2:]:
        html = html.replace(extra, "", 1)

    html = retag_cards(html, history)
    write(rel, html, root)
    return True


def retag_cards(html: str, history: list[dict]) -> str:
    """
    Метку «Актуальная версия» носит только верхняя карточка. У нижней метка
    «Только APK», если эта версия в RuStore не выходила, и нет метки вовсе,
    если выходила.
    """
    status = {item["version"]: item["status"] for item in history}
    cards = _CARD.findall(html)

    for index, card in enumerate(cards[:2]):
        version = re.search(r'release-card__version">Версия ([\d.]+)<', card)
        if not version:
            continue
        if index == 0:
            label = "Актуальная версия"
        elif status.get(version.group(1)) == "skipped":
            label = "Только APK"
        else:
            label = None

        without = re.sub(r'\n[ \t]*<span class="tag tag--plain">[^<]*</span>', "", card)
        if label:
            fixed = without.replace(
                f'<h3 class="release-card__version">Версия {version.group(1)}</h3>',
                f'<h3 class="release-card__version">Версия {version.group(1)}</h3>\n'
                f'            <span class="tag tag--plain">{label}</span>',
                1,
            )
        else:
            fixed = without
        if fixed != card:
            html = html.replace(card, fixed, 1)
    return html


def insert_llms_entry(root: Path, release: dict) -> bool:
    """Заготовка выпуска в текстовой копии истории для моделей."""
    rel = "llms-full.txt"
    text = read(rel, root)
    heading = f"### {release['version']} — {date_words(release['date'])}"
    if f"### {release['version']} " in text:
        return False

    anchor = re.search(r"^## История версий.*$", text, re.M)
    if not anchor:
        raise SystemExit(f"{rel}: не нашёл раздел «История версий»")

    first = re.search(r"^### ", text[anchor.end():], re.M)
    if not first:
        raise SystemExit(f"{rel}: в истории версий нет ни одного выпуска")
    at = anchor.end() + first.start()

    bullets = "\n".join(f"- {b}" for b in release["bullets"])
    write(rel, text[:at] + f"{heading}\n\n{bullets}\n\n" + text[at:], root)
    return True


# ---------------------------------------------------------------------------
# JSON-LD
# ---------------------------------------------------------------------------


#: Заглушка на время скалярных правок: без неё замена `softwareVersion` попала бы
#: и в пятнадцать карточек списка выпусков, где у каждой своя версия.
MAIN_ENTITY_SLOT = "@@mainEntity@@"


def rebuild_jsonld(root: Path, payload: dict, counts: dict) -> list[str]:
    """
    Приводит разметку в соответствие со страницей. Раньше она писалась руками рядом
    с видимым текстом и от него отставала — отсюда `softwareVersion` 2.8.0
    на странице версии 2.9.0 и 2.9.0 внутри карточки выпуска 2.8.0.

    Правки точечные, а не «разобрать и собрать заново»: пересборка развернула бы
    написанные в одну строку объекты и выдала бы диффом весь файл. Разбор всё равно
    делается — но только чтобы убедиться, что JSON цел.
    """
    version = payload["app"]["version"]
    date = payload["release"]["date"]
    releases = parse_releases(read("obnovleniya/index.html", root))
    changed = []

    for rel in ("index.html", "obnovleniya/index.html", "voprosy/index.html", "policy/index.html"):
        html = read(rel, root)
        block = read_jsonld(html, rel)
        body = html[block.span[0]:block.span[1]]
        updated = body

        main_entity = ""
        if rel == "obnovleniya/index.html":
            # Список выпусков вынимается целиком: внутри у каждой карточки своя версия
            # и своя дата, и общие скалярные замены их бы затёрли.
            start, end, _ = json_value_span(updated, "mainEntity", "{")
            main_entity = updated[start:end]
            updated = updated[:start] + MAIN_ENTITY_SLOT + updated[end:]

        if node_of_type(block.data, "MobileApplication") is not None:
            updated = replace_json_scalar(updated, "softwareVersion", version, 1)
        updated = replace_json_scalar(
            updated, "dateModified", date, updated.count('"dateModified"')
        )

        if rel == "index.html":
            updated = replace_json_array(updated, "screenshot", [
                json.dumps(f"{SITE}/assets/img/screens/{name}-488.webp", ensure_ascii=False)
                for name, _alt in parse_slides(html)
            ])

        if rel == "obnovleniya/index.html":
            main_entity = replace_json_scalar(main_entity, "numberOfItems", len(releases), 1)
            main_entity = replace_json_array(main_entity, "itemListElement",
                                             item_list_items(releases))
            updated = updated.replace(MAIN_ENTITY_SLOT, main_entity)

        html = html[:block.span[0]] + updated + html[block.span[1]:]
        read_jsonld(html, rel)  # собранное обязано оставаться разбираемым

        if updated != body:
            write(rel, html, root)
            changed.append(rel)

    counts["releases"] = len(releases)
    return changed


def item_list_items(releases: list) -> list[str]:
    """Список выпусков в разметке — зеркало видимых блоков, и только оно."""
    items = [
        {
            "@type": "ListItem",
            "position": position,
            "item": {
                "@type": "SoftwareApplication",
                "@id": f"{SITE}/obnovleniya/#{release.anchor}",
                "name": f"Не пиши голосовое! {release.version}",
                "softwareVersion": release.version,
                "datePublished": release.date,
                "operatingSystem": "Android 7.0+",
                "applicationCategory": "ProductivityApplication",
                "url": f"{SITE}/obnovleniya/#{release.anchor}",
                "releaseNotes": " ".join(release.bullets),
            },
        }
        for position, release in enumerate(releases, start=1)
    ]
    return [json.dumps(item, ensure_ascii=False, indent=2) for item in items]


# ---------------------------------------------------------------------------
# Текстовые правила
# ---------------------------------------------------------------------------


def counter_rules(counter: Counter, value: int) -> list[Rule]:
    """
    Правила «числительное плюс существительное» для одного счётчика.

    Число ищется во всех формах, которые вообще умеет писать `numeral`, — иначе
    правило перестало бы срабатывать, как только счётчик изменится. Существительное
    входит в шаблон, а места перечислены поимённо: без этого «пятнадцать» из «ещё
    пятнадцать языков» и «три экрана» из подписи обложки тоже попали бы под замену.

    Регистр первой буквы сохраняется: «Пятнадцать выпусков» стоит в начале
    og:description и в лиде страницы, и строчная буква там была бы опечаткой.
    """
    rules: list[Rule] = []
    forms = counter.forms()
    noun = counter.noun

    if counter.digit_files:
        rules.append(Rule(
            f"{counter.key} цифрами", list(counter.digit_files),
            rf"\d+ (?:{forms})\b", f"{value} {plural(value, *noun)}", counter.digit_expect,
        ))

    def replace(match: re.Match) -> str:
        words = numeral(value)
        if match.group(0)[0].isupper():
            words = words[0].upper() + words[1:]
        return f"{words} {plural(value, *noun)}"

    rules.append(Rule(
        f"{counter.key} прописью", list(counter.word_files),
        rf"(?i:{ANY_NUMERAL}) (?:{forms})\b", replace, counter.word_expect,
    ))
    return rules


def text_rules(payload: dict, counts: dict, cache_bust: str | None) -> list[Rule]:
    version = payload["app"]["version"]
    date = payload["release"]["date"]
    spoken = date_words(date)

    return [
        Rule("подпись версии в шапке", ["index.html"],
             r"(<span>Магазин приложений, версия )[\d.]+(</span>)", rf"\g<1>{version}\g<2>", 1),
        Rule("версия над экранами", ["index.html"],
             r'(<p class="lead">Версия )[\d.]+(</p>)', rf"\g<1>{version}\g<2>", 1),
        Rule("подпись под кнопками", ["index.html"],
             r'(<p class="download__version">Версия )[\d.]+( от )[^<]+(</p>)',
             rf"\g<1>{version}\g<2>{spoken}\g<3>", 1),
        Rule("строка политики", ["policy/index.html"],
             r"(Обновлено )[^.]+( года\. Действует для версии приложения )[\d.]+",
             rf"\g<1>{spoken}\g<2>{version}", 1),
        Rule("версия в llms.txt", ["llms.txt"],
             r"(Текущая версия )[\d.]+( от )[^.]+( года)", rf"\g<1>{version}\g<2>{spoken}\g<3>", 1),
        Rule("версия в llms-full.txt", ["llms-full.txt"],
             r"(Версия приложения )[\d.]+( от )[^.]+( года\. Файл обновлён )[^.]+( года)",
             rf"\g<1>{version}\g<2>{spoken}\g<3>{spoken}\g<4>", 1),
        Rule("время правки страницы истории", ["obnovleniya/index.html"],
             r'(<meta property="article:modified_time" content=")[\d-]+', rf"\g<1>{date}", 1),
        Rule("дата в карте сайта", ["sitemap.xml"], r"(<lastmod>)[\d-]+(</lastmod>)",
             rf"\g<1>{date}\g<2>", 4),
    ] + [
        rule
        for counter in COUNTERS
        for rule in counter_rules(counter, counts[counter.key])
    ]


# ---------------------------------------------------------------------------
# Метка кэша
# ---------------------------------------------------------------------------


def next_cache_bust(root: Path, date: str, content_changed: bool) -> str:
    """
    `?v=ГГГГ-ММ-ДД`, а при второй правке за день — с суффиксом. Хеша в именах файлов
    нет, поэтому метка обязана меняться: иначе у вернувшегося посетителя останется
    старый CSS.

    Но меняться она обязана **только когда что-то изменилось**. Иначе повторный
    прогон на неизменившемся сайте каждый раз выдавал бы новую метку и сбрасывал
    кэш у всех посетителей на ровном месте — и заодно ломал бы идемпотентность,
    на которую опирается `-Resume` в оркестраторе.
    """
    current = re.search(r"\?v=([\d-]+)", read("index.html", root))
    if not current:
        return date
    mark = current.group(1)
    if not mark.startswith(date):
        return date
    if not content_changed:
        return mark
    tail = mark[len(date):]
    return f"{date}-{int(tail.lstrip('-') or '1') + 1}"


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------


def apply_payload(payload: dict, root: Path = ROOT, run_sync: bool = True) -> dict:
    release = payload["release"]

    inserted = {
        "история": insert_history_block(root, release),
        "главная": insert_main_card(root, release, payload["history"]),
        "llms-full": insert_llms_entry(root, release),
    }

    counts = {
        "faq": read("voprosy/index.html", root).count('<article class="qa"'),
        "screens": len(parse_slides(read("index.html", root))),
        "releases": 0,
    }
    changed = rebuild_jsonld(root, payload, counts)
    changed += apply_rules(text_rules(payload, counts, None), root)

    # Метка кэша считается последней: она зависит от того, изменилось ли что-то ещё.
    cache_bust = next_cache_bust(root, release["date"], bool(changed) or any(inserted.values()))
    changed += apply_rules([
        Rule("метка кэша", HTML_PAGES, r"(\?v=)[\d-]+", rf"\g<1>{cache_bust}", "each"),
    ], root)

    if run_sync:
        subprocess.run(
            [sys.executable, str(root / "tools" / "sync-shared.py")],
            check=True, cwd=root, capture_output=True,
        )

    return {"inserted": inserted, "counts": counts, "cacheBust": cache_bust, "changed": changed}


def main() -> None:
    setup_stdout()
    parser = argparse.ArgumentParser(description="Применяет релизный payload к сайту")
    parser.add_argument("--payload", help="путь к latest.json, собранному site-payload.ps1")
    parser.add_argument("--selftest", action="store_true", help="прогнать самопроверку")
    args = parser.parse_args()

    if args.selftest:
        from selftest_site import run_selftest

        run_selftest()
        return

    if not args.payload:
        raise SystemExit("нужен --payload или --selftest")

    payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
    result = apply_payload(payload)

    print(f"версия {payload['app']['version']}, метка кэша {result['cacheBust']}")
    for what, done in result["inserted"].items():
        print(f"  {what}: {'вставлена заготовка' if done else 'уже была'}")
    counts = result["counts"]
    print(f"  счётчики: выпусков {counts['releases']}, ответов {counts['faq']}, "
          f"экранов {counts['screens']}")
    print("Дальше: python tools/check-release.py")


if __name__ == "__main__":
    main()
