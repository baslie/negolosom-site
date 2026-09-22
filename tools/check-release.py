#!/usr/bin/env python3
"""
Проверяет, что сайт внутренне согласован после выпуска.

    python tools/check-release.py

Возвращает 1 и перечисляет расхождения. Проверки самодостаточны: эталон берётся
из самого сайта — из блоков выпусков, из карусели, из числа вопросов. Внешний
источник нужен ровно один и необязателен: манифест кадров приложения, чтобы
сверить состав и подписи экранов.

Зачем это нужно, видно по тому, что нашлось при заведении инструмента:
`obnovleniya/index.html` держал в `MobileApplication` версию 2.8.0, когда сайт
был уже на 2.9.0, а внутри карточки выпуска 2.8.0 стояло `softwareVersion` 2.9.0.
Обе ошибки — из класса «разметка отстала от видимого текста», и ловятся они только
сверкой одного с другим.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date as date_type
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sitelib import (  # noqa: E402
    ANY_NUMERAL,
    COUNTERS,
    HTML_PAGES,
    ROOT,
    graph_nodes,
    node_of_type,
    numeral,
    parse_releases,
    parse_slides,
    plural,
    read,
    read_jsonld,
    setup_stdout,
    squash,
)

SITE = "https://negolosom.ru"
SHARED_REGION = re.compile(
    r"<!-- #region @shared:(?P<name>[\w-]+)[^>]*-->"
    r"(?P<body>.*?)"
    r"<!-- #endregion @shared:(?P=name) -->",
    re.S,
)


class Report:
    def __init__(self) -> None:
        self.problems: list[str] = []
        self.checks = 0

    def check(self, condition: bool, message: str) -> bool:
        self.checks += 1
        if not condition:
            self.problems.append(message)
        return condition


def check_jsonld_parses(report: Report, root: Path) -> dict[str, object]:
    """Разметку правят руками, и сломанный JSON тихо выпадает из индексации."""
    blocks = {}
    for rel in HTML_PAGES:
        html = read(rel, root)
        if "application/ld+json" not in html:
            continue
        try:
            blocks[rel] = read_jsonld(html, rel)
        except ValueError as error:
            report.check(False, str(error))
    return blocks


def check_versions(report: Report, blocks: dict, releases: list) -> None:
    current = releases[0].version

    for rel, block in blocks.items():
        app = node_of_type(block.data, "MobileApplication")
        if app is None:
            continue
        report.check(
            app.get("softwareVersion") == current,
            f"{rel}: softwareVersion = {app.get('softwareVersion')!r}, "
            f"а свежий выпуск сайта — {current}",
        )


def check_item_list(report: Report, blocks: dict, releases: list) -> None:
    block = blocks.get("obnovleniya/index.html")
    if block is None:
        return report.check(False, "obnovleniya: нет блока JSON-LD")

    page = node_of_type(block.data, "WebPage") or node_of_type(block.data, "CollectionPage")
    item_list = (page or {}).get("mainEntity")
    if not item_list:
        return report.check(False, "obnovleniya: в разметке нет списка выпусков")

    items = item_list.get("itemListElement", [])
    report.check(
        item_list.get("numberOfItems") == len(releases),
        f"obnovleniya: numberOfItems = {item_list.get('numberOfItems')}, "
        f"а блоков выпусков {len(releases)}",
    )
    report.check(
        len(items) == len(releases),
        f"obnovleniya: элементов списка {len(items)}, а блоков выпусков {len(releases)}",
    )

    for position, (entry, release) in enumerate(zip(items, releases), start=1):
        item = entry.get("item", {})
        where = f"obnovleniya: выпуск {release.version}"
        report.check(entry.get("position") == position, f"{where}: position = {entry.get('position')}")
        report.check(
            item.get("softwareVersion") == release.version,
            f"{where}: в разметке softwareVersion = {item.get('softwareVersion')!r}",
        )
        report.check(
            item.get("datePublished") == release.date,
            f"{where}: в разметке дата {item.get('datePublished')!r}, в блоке {release.date}",
        )
        report.check(
            item.get("@id") == f"{SITE}/obnovleniya/#{release.anchor}",
            f"{where}: якорь разметки не совпадает с id блока",
        )
        report.check(
            squash(item.get("releaseNotes", "")) == squash(" ".join(release.bullets)),
            f"{where}: releaseNotes разошлись с пунктами блока",
        )

    anchors = [release.anchor for release in releases]
    report.check(len(set(anchors)) == len(anchors), "obnovleniya: якоря выпусков повторяются")


def check_counters(report: Report, root: Path, values: dict[str, int]) -> None:
    """
    Счётчики проверяются только там, где они объявлены в `COUNTERS`. Сканировать
    весь текст нельзя: «три экрана» из подписи обложки и «ещё пятнадцать языков»
    — не счётчики сайта, и требовать от них согласия с числом экранов бессмысленно.
    """
    for counter in COUNTERS:
        value = values[counter.key]
        digits = f"{value} {plural(value, *counter.noun)}"
        words = f"{numeral(value)} {plural(value, *counter.noun)}"

        seen_digits = 0
        for rel in counter.digit_files:
            for match in re.finditer(rf"\d+ (?:{counter.forms()})\b", read(rel, root)):
                seen_digits += 1
                report.check(match.group(0) == digits,
                             f"{rel}: «{match.group(0)}», ожидалось «{digits}»")
        if counter.digit_files:
            report.check(seen_digits == counter.digit_expect,
                         f"счётчик «{counter.key}» цифрами встретился {seen_digits} раз, "
                         f"ожидалось {counter.digit_expect}")

        seen_words = 0
        for rel in counter.word_files:
            for match in re.finditer(rf"(?i:{ANY_NUMERAL}) (?:{counter.forms()})\b",
                                     read(rel, root)):
                seen_words += 1
                report.check(match.group(0).lower() == words,
                             f"{rel}: «{match.group(0)}», ожидалось «{words}»")
        report.check(seen_words == counter.word_expect,
                     f"счётчик «{counter.key}» прописью встретился {seen_words} раз, "
                     f"ожидалось {counter.word_expect}")


def check_cache_bust(report: Report, root: Path) -> None:
    found = set()
    for rel in HTML_PAGES:
        text = read(rel, root)
        marks = set(re.findall(r"\?v=([\d-]+)", text))
        report.check(len(marks) == 1, f"{rel}: меток кэша несколько — {sorted(marks)}")
        found |= marks
    report.check(len(found) == 1, f"метка кэша разная на страницах: {sorted(found)}")


def check_sitemap(report: Report, root: Path, newest: str) -> None:
    text = read("sitemap.xml", root)
    urls = re.findall(r"<loc>([^<]+)</loc>", text)
    dates = re.findall(r"<lastmod>([^<]+)</lastmod>", text)

    report.check(len(urls) == 4, f"sitemap: {len(urls)} адресов, ожидалось 4")
    report.check(len(dates) == len(urls), "sitemap: не у каждого адреса есть lastmod")
    today = date_type.today().isoformat()
    for value in dates:
        report.check(value <= today, f"sitemap: lastmod {value} в будущем")
        report.check(value >= newest, f"sitemap: lastmod {value} старше выпуска {newest}")


def check_faq(report: Report, root: Path, blocks: dict) -> int:
    html = read("voprosy/index.html", root)
    anchors = re.findall(r'<article class="qa" id="([^"]+)">', html)
    report.check(len(set(anchors)) == len(anchors), "voprosy: якоря вопросов повторяются")

    block = blocks.get("voprosy/index.html")
    if block is not None:
        faq_page = node_of_type(block.data, "FAQPage")
        questions = (faq_page or {}).get("mainEntity", [])
        report.check(
            len(questions) == len(anchors),
            f"voprosy: в разметке {len(questions)} вопросов, в тексте {len(anchors)}",
        )
    return len(anchors)


def check_screens(report: Report, root: Path, blocks: dict, frames: Path | None) -> int:
    html = read("index.html", root)
    slides = parse_slides(html)

    for name, alt in slides:
        report.check(bool(alt.strip()), f"слайд «{name}» без подписи alt")
        for width in (244, 488):
            for ext in ("avif", "webp"):
                rel = f"assets/img/screens/{name}-{width}.{ext}"
                report.check((root / rel).is_file(), f"нет картинки {rel}")

    block = blocks.get("index.html")
    if block is not None:
        app = node_of_type(block.data, "MobileApplication") or {}
        shots = app.get("screenshot", [])
        expected = [f"{SITE}/assets/img/screens/{name}-488.webp" for name, _ in slides]
        report.check(shots == expected, "index: массив screenshot разошёлся с каруселью")

    if frames and frames.is_file():
        manifest = json.loads(frames.read_text(encoding="utf-8"))
        site_frames = sorted(
            (f["site"] for f in manifest["frames"] if "site" in f),
            key=lambda s: s["slide"],
        )
        report.check(
            [s["name"] for s in site_frames] == [name for name, _ in slides],
            "состав и порядок экранов разошлись с манифестом кадров приложения",
        )
        by_name = {s["name"]: s["alt"] for s in site_frames}
        for name, alt in slides:
            if name in by_name:
                report.check(
                    squash(by_name[name]) == squash(alt),
                    f"подпись экрана «{name}» разошлась с манифестом приложения",
                )
    return len(slides)


def check_shared_blocks(report: Report, root: Path) -> None:
    source = {m.group("name"): m.group("body") for m in SHARED_REGION.finditer(read("index.html", root))}
    report.check(bool(source), "index.html: не нашлось ни одного общего блока")

    for rel in HTML_PAGES[1:]:
        for match in SHARED_REGION.finditer(read(rel, root)):
            name = match.group("name")
            if name not in source:
                report.check(False, f"{rel}: общий блок «{name}» есть, а в index.html его нет")
                continue
            # Разносчик делает якоря абсолютными и ставит aria-current — сравниваем
            # с той же поправкой, иначе честная синхронизация выглядела бы расхождением.
            expected = source[name].replace('href="#', 'href="/#')
            report.check(
                _normalise(match.group("body")) == _normalise(expected),
                f"{rel}: общий блок «{name}» отстал от index.html — запустите sync-shared.py",
            )


def _normalise(html: str) -> str:
    html = re.sub(r'\s+aria-current="page"', "", html)
    html = re.sub(r"<a class=\"([^\"]*)\" href=\"[^\"]*\">([^<]*)</a>", r"\2", html)
    html = re.sub(r"<span[^>]*>([^<]*)</span>", r"\1", html)
    return squash(html)


def check_llms(report: Report, root: Path, releases: list) -> None:
    newest = releases[0]
    for rel in ("llms.txt", "llms-full.txt"):
        text = read(rel, root)
        report.check(newest.version in text, f"{rel}: нет текущей версии {newest.version}")
    report.check(
        f"### {newest.version} " in read("llms-full.txt", root),
        f"llms-full.txt: в истории версий нет раздела про {newest.version}",
    )


def check_local_links(report: Report, root: Path) -> None:
    for rel in HTML_PAGES:
        html = read(rel, root)
        for target in set(re.findall(r'(?:href|src)="(/[^"#?]+)', html)):
            if target.endswith("/"):
                target += "index.html"
            report.check((root / target.lstrip("/")).is_file(), f"{rel}: битая ссылка {target}")


def run(root: Path = ROOT, frames: Path | None = None) -> Report:
    report = Report()
    releases = parse_releases(read("obnovleniya/index.html", root))
    blocks = check_jsonld_parses(report, root)

    check_versions(report, blocks, releases)
    check_item_list(report, blocks, releases)
    faq = check_faq(report, root, blocks)
    screens = check_screens(report, root, blocks, frames)
    check_counters(report, root, {"releases": len(releases), "faq": faq, "screens": screens})
    check_cache_bust(report, root)
    check_sitemap(report, root, releases[0].date)
    check_shared_blocks(report, root)
    check_llms(report, root, releases)
    check_local_links(report, root)
    return report


def main() -> None:
    setup_stdout()
    parser = argparse.ArgumentParser(description="Проверяет согласованность сайта после выпуска")
    parser.add_argument("--frames", help="манифест кадров приложения (design/frames.json)")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        from selftest_site import run_selftest

        run_selftest()
        return

    frames = Path(args.frames) if args.frames else ROOT.parent / "negolosom" / "design" / "frames.json"
    report = run(frames=frames)

    if report.problems:
        print(f"Расхождений: {len(report.problems)} (проверок {report.checks})")
        for problem in report.problems:
            print(f"  - {problem}")
        raise SystemExit(1)
    print(f"Сайт согласован: проверок {report.checks}, расхождений нет")


if __name__ == "__main__":
    main()
