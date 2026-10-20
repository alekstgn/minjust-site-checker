# -*- coding: utf-8 -*-
"""Детерминированное правило маркировки (по требованию заказчика):

Если в пределах 500 знаков от упоминания сущности есть слово «иноагент»
(в любой форме) или «иностранный агент» (в любой форме), сущность считается
МАРКИРОВАННОЙ. Для организаций дополнительно: «нежелательн...», «запрещенн...»,
«экстремистск...», «признана ... в РФ» рядом с названием.

Вход:  matches_raw.json + site_text/pages_history.json
Выход: marking_rule.json — {idx: {"rule": "есть"/"нет", "evidence": "..."}}
"""
import json
import re
import sys

WINDOW = 500

MARK_PATTERNS = {
    "иноагент": re.compile(r"\bиноагент\w*\b", re.I),
    "иностранный агент": re.compile(r"\bиностранны\w+\s+агент\w*\b", re.I),
}
ORG_MARK_PATTERNS = {
    "нежелательная": re.compile(r"\bнежелательн\w*\b", re.I),
    "запрещённая": re.compile(r"\bзапрещ[её]нн\w*\b", re.I),
    "экстремистская": re.compile(r"\bэкстремистск\w*\b", re.I),
    "признана в РФ": re.compile(r"признан\w*\s+(?:иностранн\w+|экстремистск\w+|нежелательн\w+|в\s+РФ|в\s+России)", re.I),
    "реестр Минюста": re.compile(r"реестр\w*\s+(?:Минюста|иностранных\s+агентов)", re.I),
}

SUFFIXES = ["иями", "ями", "ами", "ов", "ев", "ей", "ий", "ия", "ие", "ии",
            "ой", "ый", "ая", "яя", "ое", "ее", "ые", "ие", "ом", "ем", "ым", "им",
            "ую", "юю", "ох", "ах", "ях", "ья", "ье", "ьи",
            "у", "ю", "а", "я", "ы", "и", "е", "о", "ь"]
MIN_STEM = 5


def stem(w):
    if len(w) <= MIN_STEM:
        return w
    for suf in SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= MIN_STEM:
            return w[: len(w) - len(suf)]
    return w


def norm(s):
    s = s.lower().replace("ё", "е")
    return re.sub(r"\s+", " ", re.sub(r"[^0-9a-zа-я]+", " ", s)).strip()


def quoted_parts(s):
    return [q.strip() for q in re.findall(r"[«»\"]([^«»\"]{3,200}?)[«»\"]", s or "")]


def variants_for(match_rec):
    """Все текстовые варианты, которыми сущность могла быть написана в тексте."""
    name = match_rec["matched"]
    kind = match_rec["kind"]
    out = {norm(name)}
    for q in quoted_parts(name):
        out.add(norm(q))
    # ФИО-варианты
    pre = re.split(r"[«\"]", name)[0].strip()
    toks = norm(pre).split()
    if kind == "иноагент" and 2 <= len(toks) <= 3:
        if len(toks) == 3:
            fam, im, ot = toks
            out |= {f"{fam} {im} {ot}", f"{im} {fam} {ot}", f"{fam} {im[0]} {ot[0]}",
                    f"{im[0]} {ot[0]} {fam}", f"{im} {fam}", f"{fam}", }
        else:
            fam, im = toks
            out |= {f"{fam} {im}", f"{im} {fam}", f"{fam}"}
        # одиночная фамилия ищется только если её стем уникален — здесь упрощаем:
        # одиночную фамилию допускаем, окно ±500 от ЛЮБОГО вхождения варианта
    # краткое название без «шапки»
    base = re.sub(r"[«»\"]", " ", name)
    out.add(norm(base))
    return {v for v in out if len(v) >= 4}


def find_occurrences(text, variant):
    """Позиции вхождений варианта (по стем-токенам) в тексте."""
    toks = [(m.group(0), m.start(), m.end()) for m in re.finditer(r"[^\W_]+", text, re.UNICODE)]
    pat = [stem(t.lower().replace("ё", "е")) for t in variant.split()]
    if not pat:
        return []
    occ = []
    n = len(toks)
    for i in range(n - len(pat) + 1):
        if [stem(toks[i + k][0].lower().replace("ё", "е")) for k in range(len(pat))] == pat:
            occ.append((toks[i][1], toks[i + len(pat) - 1][2]))
    return occ


def main(matches_file="matches_raw.json", pages_file="site_text/pages_history.json",
         out_file="marking_rule.json"):
    matches = json.load(open(matches_file, encoding="utf-8"))
    pages = {p["url"]: p for p in json.load(open(pages_file, encoding="utf-8"))}
    result = {}
    for idx, r in enumerate(matches):
        page = pages.get(r["url"])
        if not page:
            continue
        text = page.get("text") or ""
        pats = dict(MARK_PATTERNS)
        if r["kind"] != "экстремистский материал":
            pats.update(ORG_MARK_PATTERNS)
        found_ev = ""
        for variant in variants_for(r):
            for s, e in find_occurrences(text, variant):
                window = text[max(0, s - WINDOW): min(len(text), e + WINDOW)]
                for label, rx in pats.items():
                    mm = rx.search(window)
                    if mm:
                        ctx = re.sub(r"\s+", " ", window[max(0, mm.start() - 60): mm.end() + 60]).strip()
                        found_ev = f"[{label}] …{ctx}…"
                        break
                if found_ev:
                    break
            if found_ev:
                break
        result[idx] = {"rule": "есть" if found_ev else "нет", "evidence": found_ev}
    json.dump(result, open(out_file, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n_yes = sum(1 for v in result.values() if v["rule"] == "есть")
    print(f"правило ±500 знаков: marking=есть у {n_yes} из {len(result)} находок")


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
