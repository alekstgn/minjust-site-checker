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
         dropped_file="dropped_aliases.json", out_file="matches.xlsx", site_name="history.ru",
         mode="full"):
    """mode='full' — обычный отчёт; mode='unmarked' — главный лист только БЕЗ пометки
    (замаркированные и тёзки уходят на справочные листы, из выдачи скрыты)."""
    matches = json.load(open(matches_file, encoding="utf-8"))
    pages = json.load(open(pages_file, encoding="utf-8"))
    dropped = json.load(open(dropped_file, encoding="utf-8"))

    orgs = [r for r in matches if r["kind"] != "экстремистский материал"]
    mats = [r for r in matches if r["kind"] == "экстремистский материал"]
    has_ai = bool(orgs) and "ai_marking" in orgs[0]

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
    ]
    if has_ai:
        real = [r for r in orgs if r.get("ai_subject") == "реальная сущность"]
        imark = [r for r in real if r.get("final_marking", "").startswith("есть")]
        imark_rule = [r for r in real if r.get("final_marking") == "есть (правило ±500)"]
        imark_ai = [r for r in real if r.get("final_marking") == "есть (ИИ)"]
        nomark = [r for r in real if r.get("final_marking") == "нет"]
        rows += [
            ["  ИИ: подтверждено реальных упоминаний", len(real)],
            ["  ИИ: отсечено тёзок/совпадений слов", len(orgs) - len(real)],
            ["  ИТОГ: с маркировкой (правило ±500 знаков)", len(imark_rule)],
            ["  ИТОГ: с маркировкой (нашёл ИИ)", len(imark_ai)],
            ["  ИТОГ: всего с маркировкой", len(imark)],
            ["  ИТОГ: БЕЗ маркировки (см. лист «Без маркировки»)", len(nomark)],
        ]
    rows += [
        ["  точные совпадения названия/ФИО", len([r for r in orgs if "точное" in r["tier"]])],
        ["  возможные (инициалы/порядок слов)", len([r for r in orgs if "точное" not in r["tier"]])],
        ["Совпадения названий экстремистских материалов", len(mats)],
        ["  (название совпало — контекст часто исторический термин, требует просмотра)", ""],
        [""],
        ["КАК ЧИТАТЬ ОТЧЁТ", ""],
        ["  Лист «Иноагенты и организации» — основной результат", ""],
        ["  Серый в колонке «ИИ: маркировка» = тёзка/другое значение, можно не трогать", ""],
        ["  Зелёный = маркировка статуса стоит, всё в порядке", ""],
        ["  Красный = реальное упоминание БЕЗ маркировки — см. лист «Без маркировки»", ""],
        ["  Лист «Материалы» = совпали названия запрещённых книг/фильмов/изданий", ""],
        [""],
        ["ОГРАНИЧЕНИЯ МЕТОДА", ""],
        ["  Проверялись тексты страниц; текст в картинках/PDF-вложениях не анализировался", ""],
        ["  ИИ видит контекст ±500 знаков и конец страницы; пометка в виде сноски,", ""],
        ["   вынесенной в другое место страницы, могла быть не замечена", ""],
        ["  Вердикты ИИ — черновик для человека, финальное решение за редакцией", ""],
    ]
    for r in rows:
        ws3.append(r)
    ws3["A1"].font = Font(bold=True, size=13)
    for rr in (4, 12, 19, 26, 32):
        ws3.cell(row=rr, column=1).font = Font(bold=True, size=11)
    set_widths(ws3, [95, 90])

    # ================= Иноагенты и организации =================
    def write_org_sheet(name, rows_list):
        ws = wb.create_sheet(name)
        headers = ["Раздел", "Страница (ссылка)", "Заголовок страницы", "Тип",
                   "Что найдено (по реестру)", "Что именно совпало", "Уверенность",
                   "Статус в реестре", "Вхождений на странице", "Контекст"]
        if has_ai:
            headers += ["ИИ: сущность или тёзка", "ИИ: пояснение", "ИИ: маркировка",
                        "Правило ±500 знаков", "Доказательство правила", "МАРКИРОВКА (ИТОГ)", "ИИ: комментарий"]
        ws.append(headers)
        style_header(ws)
        for r in rows_list:
            line = [r["section"], r["url"], r["title"], r["kind"], r["matched"],
                    r["alias_label"], TIER_RU.get(r["tier"], r["tier"]), r["status"],
                    r["hits_on_page"], r["context"]]
            if has_ai:
                line += [r.get("ai_subject", ""), r.get("ai_subject_note", ""),
                         r.get("ai_marking", ""), r.get("rule_marking", ""),
                         r.get("rule_evidence", ""), r.get("final_marking", ""), r.get("ai_comment", "")]
            ws.append(line)
            row = ws.max_row
            if not has_ai:
                ws.cell(row=row, column=7).fill = PatternFill("solid", fgColor=TIER_FILL.get(r["tier"], "FFFFFF"))
            else:
                fin = r.get("final_marking", "")
                if fin.startswith("не применимо"):
                    fill = "D9D9D9"  # серый — тёзка
                elif fin.startswith("есть"):
                    fill = "C6EFCE"  # зелёный — маркировка есть
                elif fin == "неопределённо":
                    fill = "FFEB9C"
                else:
                    fill = "FFC7CE"  # красный — без маркировки
                ws.cell(row=row, column=16).fill = PatternFill("solid", fgColor=fill)
            link(ws, row, 2, r["url"])
        n_cols = len(headers)
        for i, w in enumerate([13, 40, 28, 24, 40, 24, 24, 20, 9, 70, 16, 30, 13, 13, 40, 18, 45], 1):
            if i <= n_cols:
                ws.column_dimensions[get_column_letter(i)].width = w
        for r_ in ws.iter_rows(min_row=2):
            for c in r_:
                c.alignment = Alignment(vertical="top", wrap_text=True)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:{get_column_letter(n_cols)}{ws.max_row}"

    orgs.sort(key=lambda r: (0 if "точное" in r["tier"] else 1, r["kind"], r["section"], r["url"]))
    if mode == "unmarked" and has_ai:
        # режим заказчика: в выдаче только реальные упоминания БЕЗ пометки;
        # замаркированные и тёзки — на справочных листах
        nomark = [r for r in orgs if r.get("ai_subject") == "реальная сущность"
                  and not r.get("final_marking", "").startswith("есть")]
        marked = [r for r in orgs if r.get("ai_subject") == "реальная сущность"
                  and r.get("final_marking", "").startswith("есть")]
        teski = [r for r in orgs if r.get("ai_subject") == "тёзка/другое значение"]
        write_org_sheet("БЕЗ МАРКИРОВКИ (главный)", nomark)
        write_org_sheet("С пометкой (скрыто)", marked)
        write_org_sheet("Тёзки (справочно)", teski)
    else:
        write_org_sheet("Иноагенты и организации", orgs)

    # ================= Без маркировки (дубль-лист только в полном режиме) =================
    if has_ai and mode != "unmarked":
        nomark = [r for r in orgs if r.get("ai_subject") == "реальная сущность"
                  and not r.get("final_marking", "").startswith("есть")]
        ws = wb.create_sheet("Без маркировки")
        ws.append(["Раздел", "Страница (ссылка)", "Заголовок страницы", "Сущность из реестра",
                   "Статус в реестре", "Итог маркировки", "ИИ: комментарий", "Контекст"])
        style_header(ws)
        nomark.sort(key=lambda r: (r["kind"], r["matched"], r["section"]))
        for r in nomark:
            ws.append([r["section"], r["url"], r["title"], r["matched"],
                       r["status"], r.get("final_marking", ""), r.get("ai_comment", ""), r["context"]])
            link(ws, ws.max_row, 2, r["url"])
        set_widths(ws, [13, 42, 30, 40, 20, 18, 45, 85])
        for r_ in ws.iter_rows(min_row=2):
            for c in r_:
                c.alignment = Alignment(vertical="top", wrap_text=True)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = f"A1:G{ws.max_row}"

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
