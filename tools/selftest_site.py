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

from sitelib import ROOT, read, setup_stdout, write  # noqa: E402


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


def run_selftest() -> None:
    setup_stdout()
    apply_release = _load("apply-release")
    check_release = _load("check-release")
    runner = Runner()

    with tempfile.TemporaryDirectory(prefix="site-selftest-") as tmp:
        tmp_path = Path(tmp)

        print("\n▸ Текущий сайт")
        site = copy_site(tmp_path)

        def apply_current() -> None:
            payload = json.loads((ROOT / "tools" / "selftest-payload.json").read_text("utf-8")) \
                if (ROOT / "tools" / "selftest-payload.json").is_file() \
                else payload_for(site, "2.9.0", "2026-09-22", ["не используется"])
            apply_release.apply_payload(payload, root=site, run_sync=True)
            report = check_release.run(root=site)
            assert not report.problems, "\n".join(report.problems)

        runner.case("после применения сайт согласован", apply_current)

        def idempotent() -> None:
            before = tmp_path / "before"
            shutil.copytree(site, before)
            payload = payload_for(site, "2.9.0", "2026-09-22", ["не используется"])
            apply_release.apply_payload(payload, root=site, run_sync=True)
            changed = dirs_equal(before, site)
            shutil.rmtree(before)
            assert not changed, f"второй прогон изменил: {changed}"

        runner.case("второй прогон не меняет ни байта", idempotent)

        print("\n▸ Следующий выпуск")
        fresh = copy_site(tmp_path / "next")

        def release_next() -> None:
            # Дата выпуска — сегодняшняя: карта сайта справедливо не принимает
            # lastmod из будущего, и синтетическая дата ломала бы проверку.
            payload = payload_for(fresh, "2.10.0", TODAY, [
                "Первый пункт нового выпуска — заготовка из журнала.",
                "Второй пункт нового выпуска.",
            ])
            result = apply_release.apply_payload(payload, root=fresh, run_sync=True)
            assert all(result["inserted"].values()), f"вставлено не всё: {result['inserted']}"
            assert result["counts"]["releases"] == 16, result["counts"]

            report = check_release.run(root=fresh)
            assert not report.problems, "\n".join(report.problems)

        runner.case("заготовка вставлена в трёх местах, сайт согласован", release_next)

        def counters_grew() -> None:
            assert "шестнадцать выпусков" in read("llms.txt", fresh), "счётчик прописью не вырос"
            assert "16 выпусков" in read("index.html", fresh), "счётчик цифрами не вырос"

        runner.case("счётчики выросли и прописью, и цифрами", counters_grew)

        def cards_retagged() -> None:
            html = read("index.html", fresh)
            cards = apply_release._CARD.findall(html)
            assert len(cards) == 2, f"на главной {len(cards)} карточек вместо двух"
            assert "Версия 2.10.0" in cards[0] and "Актуальная версия" in cards[0]
            assert "Актуальная версия" not in cards[1], "метка осталась на старой карточке"

        runner.case("на главной две карточки, метка у свежей", cards_retagged)

        def next_is_idempotent() -> None:
            before = tmp_path / "next-before"
            shutil.copytree(fresh, before)
            payload = payload_for(fresh, "2.10.0", TODAY, ["другой текст, не должен попасть"])
            apply_release.apply_payload(payload, root=fresh, run_sync=True)
            changed = dirs_equal(before, fresh)
            shutil.rmtree(before)
            assert not changed, f"повторный выпуск изменил: {changed}"

        runner.case("повторный прогон выпуска ничего не переписывает", next_is_idempotent)

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


def _blank_first_alt(site: Path) -> None:
    """Пустая подпись — самая частая потеря при перевёрстке карусели."""
    text = read("index.html", site)
    fixed = re.sub(r'(-244\.webp"[^>]*?alt=")[^"]+(")', r"\g<1>\g<2>", text, count=1)
    assert fixed != text, "не нашлось ни одной подписи слайда"
    write("index.html", fixed, site)


BREAKAGES = {
    "сломанный JSON-LD": lambda site: (
        _swap(site, "index.html", '"@context": "https://schema.org",', '"@context" "https://schema.org",'),
        "JSON-LD не разбирается",
    )[1],
    "версия приложения отстала": lambda site: (
        _swap(site, "voprosy/index.html", '"softwareVersion": "2.9.0"', '"softwareVersion": "2.8.0"'),
        "softwareVersion",
    )[1],
    "число выпусков в разметке разошлось": lambda site: (
        _swap(site, "obnovleniya/index.html", '"numberOfItems": 15', '"numberOfItems": 14'),
        "numberOfItems",
    )[1],
    "счётчик прописью отстал": lambda site: (
        _swap(site, "llms.txt", "пятнадцать выпусков", "четырнадцать выпусков"),
        "ожидалось «пятнадцать выпусков»",
    )[1],
    "метка кэша разная на страницах": lambda site: (
        _swap(site, "voprosy/index.html", "?v=2026-09-22-1", "?v=2026-09-21-1"),
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
        _swap(site, "sitemap.xml", "<lastmod>2026-09-22</lastmod>", "<lastmod>2099-01-01</lastmod>"),
        "в будущем",
    )[1],
    "битая локальная ссылка": lambda site: (
        _swap(site, "index.html", 'href="/assets/css/styles.css', 'href="/assets/css/styles-typo.css'),
        "битая ссылка",
    )[1],
}


if __name__ == "__main__":
    run_selftest()
