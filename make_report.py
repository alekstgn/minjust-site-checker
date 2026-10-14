# -*- coding: utf-8 -*-
"""Финальный Excel-отчёт по проверке history.ru: matches_raw.json + site_text/pages.json → matches.xlsx"""
import json
import sys
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

TIER_RU = {
    "точное": "Точное совпадение названия",
    "точное ФИО": "Точное совпадение ФИО",
    "возможное (инициалы)": "Возможное (Фамилия И. О.)",
    "возможное (перестановка)": "Возможное (другой порядок слов)",
    "возможное (имя-фамилия)": "Возможное (имя-фамилия)",
}
TIER_FILL = {
    "точное": "FFC7CE",          # красный
    "точное ФИО": "FFC7CE",
    "возможное (инициалы)": "FFEB9C",  # жёлтый
    "возможное (перестановка)": "FFEB9C",
    "возможное (имя-фамилия)": "FFEB9C",
}
MAT_FILL = "BDD7EE"  # голубой для материалов

HFILL = PatternFill("solid", fgColor="4472C4")
HFONT = Font(color="FFFFFF", bold=True)


def style_header(ws):
    for c in ws[1]:
        c.fill = HFILL
        c.font = HFONT
        c.alignment = Alignment(vertical="center", wrap_text=True)


def set_widths(ws, widths):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def link(ws, row, col, url):
    cell = ws.cell(row=row, column=col)
    if url:
        cell.hyperlink = url
        cell.font = Font(color="0563C1", underline="single")


def main(matches_file="matches_raw.json", pages_file="site_text/pages.json",
         dropped_file="dropped_aliases.json", out_file="matches.xlsx", site_name="history.ru"):
    matches = json.load(open(matches_file, encoding="utf-8"))
    pages = json.load(open(pages_file, encoding="utf-8"))
    dropped = json.load(open(dropped_file, encoding="utf-8"))

    orgs = [r for r in matches if r["kind"] != "экстремистский материал"]
    mats = [r for r in matches if r["kind"] == "экстремистский материал"]

    wb = Workbook()

    # ================= Сводка =================
    ws3 = wb.active
    ws3.title = "Сводка"
    from collections import Counter
    by_section = Counter(p["section"] for p in pages)
    rows = [
        [f"Проверка текстов сайта {site_name} на упоминания иностранных агентов, экстремистских и запрещённых организаций и материалов"],
        ["Дата проверки", date.today().strftime("%d.%m.%Y")],
        [""],
        ["ПРОВЕРЕННЫЙ ОБЪЁМ", ""],
        ["Всего страниц проверено", len(pages)],
    ]
    for sec, cnt in by_section.most_common():
        rows.append([f"  {sec}", cnt])
    rows += [
        [""],
        ["ИСТОЧНИКИ", ""],
        ["  Реестр иностранных агентов Минюста", "https://minjust.gov.ru/ru/pages/reestr-inostryannykh-agentov/"],
        ["  Федеральный список экстремистских материалов", "https://minjust.gov.ru/ru/extremist-materials/"],
        ["  Перечень экстремистских организаций Минюста", "https://reestrs.minjust.gov.ru/ (реестр 59961ebb)"],
        ["  Перечень нежелательных организаций Минюста", "https://reestrs.minjust.gov.ru/ (реестр c2d1692e)"],
        [""],
        ["РЕЗУЛЬТАТЫ", ""],
        ["Упоминания иноагентов и организаций (страница×сущность)", len(orgs)],
        ["  точные совпадения названия/ФИО", len([r for r in orgs if "точное" in r["tier"]])],
        ["  возможные (инициалы/порядок слов — распространённые фамилии)", len([r for r in orgs if "точное" not in r["tier"]])],
        ["Совпадения названий экстремистских материалов", len(mats)],
        ["  (название совпало — контекст почти всегда исторический термин, требует просмотра)", ""],
        [""],
        ["КАК ЧИТАТЬ ОТЧЁТ", ""],
        ["  Лист «Иноагенты и организации» — основной результат", ""],
        ["  Красная отметка = точное совпадение названия организации или полного ФИО", ""],
        ["  Жёлтая = сработали инициалы или переставленные слова (распространённые фамилии) — проверьте контекст", ""],
        ["  Лист «Материалы» = совпали названия запрещённых книг/фильмов/изданий; контекст часто", ""],
        ["  оказывается историческим термином («Коктейль Молотова», «Василий Тёркин»), но просмотреть стоит", ""],
        [""],
        ["ОГРАНИЧЕНИЯ МЕТОДА", ""],
        ["  Проверялись тексты страниц; текст в картинках/PDF-вложениях не анализировался", ""],
        ["  Однословные названия организаций-иноагентов проверялись только при ≤5 упоминаниях слова по всему сайту", ""],
        ["  Полный список отфильтрованных алиасов — на листе «Отсеянные алиасы»", ""],
    ]
    for r in rows:
        ws3.append(r)
    ws3["A1"].font = Font(bold=True, size=13)
    for rr in (4, 12, 19, 26, 32):
        ws3.cell(row=rr, column=1).font = Font(bold=True, size=11)
    set_widths(ws3, [95, 90])

    # ================= Иноагенты и организации =================
    ws = wb.create_sheet("Иноагенты и организации")
    headers = ["Раздел", "Страница (ссылка)", "Заголовок страницы", "Тип",
               "Что найдено (по реестру)", "Что именно совпало", "Уверенность",
               "Статус в реестре", "Вхождений на странице", "Контекст"]
    ws.append(headers)
    style_header(ws)
    orgs.sort(key=lambda r: (0 if "точное" in r["tier"] else 1, r["kind"], r["section"], r["url"]))
    for r in orgs:
        ws.append([r["section"], r["url"], r["title"], r["kind"], r["matched"],
                   r["alias_label"], TIER_RU.get(r["tier"], r["tier"]), r["status"],
                   r["hits_on_page"], r["context"]])
        row = ws.max_row
        ws.cell(row=row, column=7).fill = PatternFill("solid", fgColor=TIER_FILL.get(r["tier"], "FFFFFF"))
        link(ws, row, 2, r["url"])
    set_widths(ws, [13, 42, 32, 26, 42, 26, 26, 20, 10, 95])
    for r_ in ws.iter_rows(min_row=2):
        for c in r_:
            c.alignment = Alignment(vertical="top", wrap_text=True)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:J{ws.max_row}"

    # ================= Материалы =================
    ws = wb.create_sheet("Материалы (проверить)")
    ws.append(["Раздел", "Страница (ссылка)", "Заголовок страницы",
               "Название материала из федерального списка", "Пункт ФСЭМ", "Вхождений", "Контекст"])
    style_header(ws)
    mats.sort(key=lambda r: (-r["hits_on_page"], r["matched"]))
    for r in mats:
        ws.append([r["section"], r["url"], r["title"], r["matched"],
                   r["status"], r["hits_on_page"], r["context"]])
        row = ws.max_row
        ws.cell(row=row, column=4).fill = PatternFill("solid", fgColor=MAT_FILL)
        link(ws, row, 2, r["url"])
    set_widths(ws, [13, 42, 32, 40, 16, 10, 95])
    for r_ in ws.iter_rows(min_row=2):
        for c in r_:
            c.alignment = Alignment(vertical="top", wrap_text=True)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:G{ws.max_row}"

    # ================= Проверенные страницы =================
    ws = wb.create_sheet("Проверенные страницы")
    ws.append(["Раздел", "Страница (ссылка)", "Заголовок", "Объём текста, знаков"])
    style_header(ws)
    for p in pages:
        ws.append([p.get("section", ""), p.get("url", ""), p.get("title", ""), len(p.get("text") or "")])
        link(ws, ws.max_row, 2, p.get("url", ""))
    set_widths(ws, [16, 60, 55, 18])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:D{ws.max_row}"

    # ================= Отсеянные алиасы =================
    ws = wb.create_sheet("Отсеянные алиасы")
    ws.append(["Алиас (вариант названия)", "Тип сущности", "Сколько страниц со словом", "Причина отсева"])
    style_header(ws)
    seen = set()
    for d in sorted(dropped, key=lambda x: -(x["df"] if isinstance(x["df"], (int, float)) else 0)):
        key = (d["alias"], d["kind"], d["причина"])
        if key in seen:
            continue
        seen.add(key)
        ws.append([d["alias"], d["kind"], d["df"], d["причина"]])
    set_widths(ws, [50, 28, 22, 70])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:D{ws.max_row}"

    wb.save(out_file)
    print(f"saved {out_file}: орг/агентов {len(orgs)}, материалов {len(mats)}, страниц {len(pages)}, отсеяных алиасов {len(seen)}")


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
