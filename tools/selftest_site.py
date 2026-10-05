#!/usr/bin/env python3
"""
Самопроверка инструментов выпуска.

    python tools/apply-release.py --selftest
    python tools/check-release.py --selftest

Проверяется на копии настоящего сайта во временной папке, а не на синтетических
заготовках: половина ценности этих инструментов — в том, что они справляются
с реальной разметкой, со всеми её «написано в одну строку» и «два `itemListElement`
на странице». Копия ничем не отличается от живого сайта, кроме того, что её не жалко.

Главный сценарий — выпуск следующей версии: инструмент обязан вставить заготовку
в трёх местах, пересчитать счётчики с пятнадцати на шестнадцать, сдвинуть карточку
на главной и оставить сайт согласованным. Второй прогон подряд обязан не изменить
ни байта: на это опирается возобновление с места сбоя.
"""

from __future__ import annotations

import datetime
import filecmp
import importlib.util
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sitelib import (  # noqa: E402
    ROOT,
    numeral,
    parse_releases,
    plural,
    read,
    setup_stdout,
    write,
)
from typograph import NBSP, missing, typograph  # noqa: E402


def _load(name: str):
    """Модули названы через дефис, обычным import их не взять."""
    path = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Runner:
    def __init__(self) -> None:
        self.passed = 0
        self.failed: list[str] = []

    def case(self, name: str, body) -> None:
        try:
            body()
            self.passed += 1
            print(f"  ✓ {name}")
        except Exception as error:  # noqa: BLE001 — самопроверке нужен любой сбой
            self.failed.append(name)
            print(f"  ✖ {name}\n      {error}")


def copy_site(into: Path) -> Path:
    site = into / "site"
    shutil.copytree(
        ROOT, site,
        ignore=shutil.ignore_patterns(".git", ".playwright-mcp", "__pycache__"),
    )
    return site


def payload_for(site: Path, version: str, date: str, bullets: list[str]) -> dict:
    """Payload, какой собрал бы `site-payload.ps1` в репозитории приложения."""
    from sitelib import parse_releases, parse_slides

    history = [{"version": version, "code": 99, "status": "draft", "publishedOn": None}]
    for release in parse_releases(read("obnovleniya/index.html", site)):
        status = "skipped" if release.version == "2.8.0" else "published"
        history.append({"version": release.version, "code": None,
                        "status": status, "publishedOn": release.date})

    return {
        "schema": 1,
        "app": {"version": version, "versionCode": 99, "minAndroid": "7.0"},
        "release": {
            "version": version,
            "anchor": "v" + version.replace(".", "-"),
            "date": date,
            "rustoreStatus": "draft",
            "bullets": bullets,
        },
        "history": history,
        "screens": [{"name": name, "slide": i, "alt": alt}
                    for i, (name, alt) in enumerate(parse_slides(read("index.html", site)), 1)],
    }


def dirs_equal(left: Path, right: Path) -> list[str]:
    """Пути файлов, которые различаются. Пустой список — копии совпадают."""
    diff = []

    def walk(compare: filecmp.dircmp, prefix: str = "") -> None:
        diff.extend(prefix + name for name in compare.diff_files)
        diff.extend(prefix + name for name in compare.left_only + compare.right_only)
        for name, sub in compare.subdirs.items():
            walk(sub, f"{prefix}{name}/")

    walk(filecmp.dircmp(str(left), str(right), ignore=["__pycache__"]))
    return diff


def current_release(site: Path = ROOT):
    """
    Свежий выпуск сайта. Самопроверка опирается на него, а не на зашитую версию:
    зашитые 2.9.0 и «пятнадцать» сделали её одноразовой — через три выпуска
    краснела половина проверок.
    """
    return parse_releases(read("obnovleniya/index.html", site))[0]


def next_version(version: str) -> str:
    major, minor, _patch = (int(part) for part in version.split("."))
    return f"{major}.{minor + 1}.0"


def run_selftest() -> None:
    setup_stdout()
    apply_release = _load("apply-release")
    check_release = _load("check-release")
    runner = Runner()

    with tempfile.TemporaryDirectory(prefix="site-selftest-") as tmp:
        tmp_path = Path(tmp)

        print("\n▸ Текущий сайт")
        site = copy_site(tmp_path)

        current = current_release(site)
        releases_now = _count(site)

        def apply_current() -> None:
            payload = payload_for(site, current.version, current.date, ["не используется"])
            apply_release.apply_payload(payload, root=site, run_sync=True)
            report = check_release.run(root=site)
            assert not report.problems, "\n".join(report.problems)

        runner.case("после применения сайт согласован", apply_current)

        def idempotent() -> None:
            before = tmp_path / "before"
            shutil.copytree(site, before)
            payload = payload_for(site, current.version, current.date, ["не используется"])
            apply_release.apply_payload(payload, root=site, run_sync=True)
            changed = dirs_equal(before, site)
            shutil.rmtree(before)
            assert not changed, f"второй прогон изменил: {changed}"

        runner.case("второй прогон не меняет ни байта", idempotent)

        print("\n▸ Следующий выпуск")
        fresh = copy_site(tmp_path / "next")
        upcoming = next_version(current.version)

        def release_next() -> None:
            # Дата выпуска — сегодняшняя: карта сайта справедливо не принимает
            # lastmod из будущего, и синтетическая дата ломала бы проверку.
            payload = payload_for(fresh, upcoming, TODAY, [
                "Первый пункт нового выпуска — заготовка из журнала.",
                "Второй пункт нового выпуска.",
            ])
            result = apply_release.apply_payload(payload, root=fresh, run_sync=True)
            assert all(result["inserted"].values()), f"вставлено не всё: {result['inserted']}"
            assert result["counts"]["releases"] == releases_now + 1, result["counts"]

            report = check_release.run(root=fresh)
            assert not report.problems, "\n".join(report.problems)

        runner.case("заготовка вставлена в трёх местах, сайт согласован", release_next)

        def counters_grew() -> None:
            grown = releases_now + 1
            noun = plural(grown, "выпуск", "выпуска", "выпусков")
            assert f"{numeral(grown)} {noun}" in read("llms.txt", fresh), "счётчик прописью не вырос"
            assert f"{grown}{NBSP}{noun}" in read("index.html", fresh), "счётчик цифрами не вырос"

        runner.case("счётчики выросли и прописью, и цифрами", counters_grew)

        def cards_retagged() -> None:
            html = read("index.html", fresh)
            cards = apply_release._CARD.findall(html)
            assert len(cards) == 2, f"на главной {len(cards)} карточек вместо двух"
            assert f"Версия {upcoming}" in cards[0] and "Актуальная версия" in cards[0]
            assert "Актуальная версия" not in cards[1], "метка осталась на старой карточке"

        runner.case("на главной две карточки, метка у свежей", cards_retagged)

        def next_is_idempotent() -> None:
            before = tmp_path / "next-before"
            shutil.copytree(fresh, before)
            payload = payload_for(fresh, upcoming, TODAY, ["другой текст, не должен попасть"])
            apply_release.apply_payload(payload, root=fresh, run_sync=True)
            changed = dirs_equal(before, fresh)
            shutil.rmtree(before)
            assert not changed, f"повторный выпуск изменил: {changed}"

        runner.case("повторный прогон выпуска ничего не переписывает", next_is_idempotent)

        def inserted_is_typographed() -> None:
            # Заготовка приезжает из журнала с обычными пробелами — на сайт она
            # обязана лечь уже с неразрывными, иначе линтер завалил бы каждый выпуск.
            history = read("obnovleniya/index.html", fresh)
            assert f"выпуска{NBSP}— заготовка" in history, "тире в заготовке не привязано"
            assert f"из{NBSP}журнала" in history, "предлог в заготовке не привязан"
            assert not missing(read("index.html", fresh)), "на главной остались пропуски"

        runner.case("вставленная заготовка уже с неразрывными пробелами", inserted_is_typographed)

        print("\n▸ Типограф")
        for name, (source, expected) in TYPOGRAPH_CASES.items():
            runner.case(name, _typograph_case(source, expected))

        print("\n▸ Поломки, которые обязан поймать линтер")
        for name, breakage in BREAKAGES.items():
            runner.case(name, _breaks(check_release, tmp_path, breakage))

    print()
    if runner.failed:
        print(f"Провалено: {len(runner.failed)}, пройдено: {runner.passed}")
        raise SystemExit(1)
    print(f"Пройдено проверок: {runner.passed}")


def _breaks(check_release, tmp_path: Path, breakage):
    """Ломает копию сайта и требует, чтобы линтер это заметил."""
    def run() -> None:
        broken = copy_site(tmp_path / f"broken-{abs(hash(breakage)) % 10**6}")
        try:
            expected = breakage(broken)
            report = check_release.run(root=broken)
            assert any(expected in problem for problem in report.problems), (
                f"линтер не заметил поломку; ожидали «{expected}», "
                f"нашлось: {report.problems}"
            )
        finally:
            shutil.rmtree(broken, ignore_errors=True)
    return run


TODAY = datetime.date.today().isoformat()


def _swap(site: Path, rel: str, old: str, new: str) -> None:
    text = read(rel, site)
    assert text.count(old) >= 1, f"в {rel} не нашлось {old!r}"
    write(rel, text.replace(old, new, 1), site)


def _desync_cache_bust(site: Path) -> None:
    """
    Разводит метку кэша на одной странице. Текущее значение читается, а не зашито:
    после каждого выпуска оно меняется, и зашитое сделало бы проверку одноразовой.
    """
    text = read("voprosy/index.html", site)
    fixed = re.sub(r"\?v=[\d-]+", "?v=1999-01-01", text, count=1)
    assert fixed != text, "не нашлось метки кэша"
    write("voprosy/index.html", fixed, site)


def _count(site: Path) -> int:
    return len(parse_releases(read("obnovleniya/index.html", site)))


def _releases_words(value: int) -> str:
    return f"{numeral(value)} {plural(value, 'выпуск', 'выпуска', 'выпусков')}"


def _append_plain_text(site: Path) -> None:
    """
    Абзац, вписанный мимо инструментов. `write()` расставил бы пробелы сам,
    поэтому файл пишется напрямую — так, как его сохранил бы редактор.
    """
    path = site / "404.html"
    text = path.read_text(encoding="utf-8")
    fixed = text.replace("</main>", "<p>Загляните в ленту — и на главную</p></main>", 1)
    assert fixed != text, "в 404.html не нашлось </main>"
    path.write_text(fixed, encoding="utf-8", newline="")


def _blank_first_alt(site: Path) -> None:
    """Пустая подпись — самая частая потеря при перевёрстке карусели."""
    text = read("index.html", site)
    fixed = re.sub(r'(-244\.webp"[^>]*?alt=")[^"]+(")', r"\g<1>\g<2>", text, count=1)
    assert fixed != text, "не нашлось ни одной подписи слайда"
    write("index.html", fixed, site)


def _typograph_case(source: str, expected: str):
    def run() -> None:
        got = typograph(source)
        assert got == expected, f"было {source!r}, стало {got!r}, ждали {expected!r}"
        assert typograph(got) == got, "второй проход изменил текст"
    return run


_N = NBSP

#: Строки без `<body>` типограф обрабатывает целиком — так короче писать случаи.
TYPOGRAPH_CASES = {
    "предлог и союз привязаны к слову": (
        "<p>Работает в ленте и на телефоне</p>",
        f"<p>Работает в{_N}ленте и{_N}на{_N}телефоне</p>",
    ),
    "предлог с заглавной и из трёх букв": (
        "<p>В ленте для записи</p>", f"<p>В{_N}ленте для{_N}записи</p>",
    ),
    "аббревиатура не привязывается к следующему слову": (
        "<p>весит 30 МБ памяти</p>", f"<p>весит 30{_N}МБ памяти</p>",
    ),
    "число со словом, но не версия и не время": (
        "<p>Версия 2.12.0 от 5 октября, в 18:40 вместо</p>",
        f"<p>Версия 2.12.0 от{_N}5{_N}октября, в{_N}18:40 вместо</p>",
    ),
    "тире привязано к слову перед ним": (
        "<p>Включите — и готово</p>", f"<p>Включите{_N}— и{_N}готово</p>",
    ),
    "частица привязана к слову перед ней": (
        "<p>Можно ли так</p>", f"<p>Можно{_N}ли так</p>",
    ),
    "предлог перед строчным тегом": (
        '<p>в <a href="/">настройках</a> — и всё</p>',
        f'<p>в{_N}<a href="/">настройках</a>{_N}— и{_N}всё</p>',
    ),
    "дефисное слово не трогается": (
        "<p>только по-русски и всё</p>", f"<p>только по-русски и{_N}всё</p>",
    ),
    "head, атрибуты, скрипты и код не трогаются": (
        '<head><title>Не пиши в чат</title></head><body>'
        '<img alt="в ленте"><script>var a = "в ленте";</script><code>в ленте</code></body>',
        '<head><title>Не пиши в чат</title></head><body>'
        '<img alt="в ленте"><script>var a = "в ленте";</script><code>в ленте</code></body>',
    ),
}


BREAKAGES = {
    "сломанный JSON-LD": lambda site: (
        _swap(site, "index.html", '"@context": "https://schema.org",', '"@context" "https://schema.org",'),
        "JSON-LD не разбирается",
    )[1],
    "версия приложения отстала": lambda site: (
        _swap(site, "voprosy/index.html", f'"softwareVersion": "{current_release(site).version}"',
              '"softwareVersion": "1.0.0"'),
        "softwareVersion",
    )[1],
    "число выпусков в разметке разошлось": lambda site: (
        _swap(site, "obnovleniya/index.html", f'"numberOfItems": {_count(site)}',
              f'"numberOfItems": {_count(site) - 1}'),
        "numberOfItems",
    )[1],
    "счётчик прописью отстал": lambda site: (
        _swap(site, "llms.txt", _releases_words(_count(site)), _releases_words(_count(site) - 1)),
        f"ожидалось «{_releases_words(_count(site))}»",
    )[1],
    "метка кэша разная на страницах": lambda site: (
        _desync_cache_bust(site),
        "метка кэша",
    )[1],
    "общий блок не разнесён": lambda site: (
        _swap(site, "index.html", "Магазин приложений, версия", "Магазин приложений — версия"),
        "отстал от index.html",
    )[1],
    "у экрана пропала подпись": lambda site: (
        _blank_first_alt(site),
        "без подписи alt",
    )[1],
    "дата в карте сайта из будущего": lambda site: (
        _swap(site, "sitemap.xml", f"<lastmod>{current_release(site).date}</lastmod>",
              "<lastmod>2099-01-01</lastmod>"),
        "в будущем",
    )[1],
    "битая локальная ссылка": lambda site: (
        _swap(site, "index.html", 'href="/assets/css/styles.css', 'href="/assets/css/styles-typo.css'),
        "битая ссылка",
    )[1],
    "руками вписан текст без неразрывных пробелов": lambda site: (
        _append_plain_text(site),
        "не хватает неразрывных пробелов",
    )[1],
}


if __name__ == "__main__":
    run_selftest()
