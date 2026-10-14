# -*- coding: utf-8 -*-
"""Поиск упоминаний иноагентов / экстремистских и нежелательных организаций /
экстремистских материалов в текстах страниц сайта.

Вход:  site_text/pages.json  — [{"url":..., "section":..., "title":..., "text":...}, ...]
Выход: matches_raw.json + dropped_aliases.json
"""
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict

# ---------------------------------------------------------------------------
# Нормализация и стемминг
# ---------------------------------------------------------------------------

SUFFIXES = [
    "иями", "ями", "ами", "ов", "ев", "ей", "ий", "ия", "ие", "ии",
    "ой", "ый", "ая", "яя", "ое", "ее", "ые", "ие", "ом", "ем", "ым", "им",
    "ую", "юю", "ох", "ах", "ях", "ья", "ье", "ьи",
    "у", "ю", "а", "я", "ы", "и", "е", "о", "ь",
]
MIN_STEM = 5

# однословный алиас допускается, только если слово встречается не более чем на DF_LIMIT_SINGLE страницах
DF_LIMIT = 20
DF_LIMIT_SINGLE = 5

STOPWORDS = {
    "а", "в", "во", "и", "на", "под", "для", "по", "о", "об", "от", "до", "из", "за", "к", "ко",
    "что", "это", "как", "так", "такой", "такие", "такое", "именно", "название", "названием", "все",
    "всё", "при", "или", "либо", "не", "ни", "да", "но", "то", "же", "бы", "ли", "уже", "еще",
    "мне", "меня", "мы", "вы", "они", "он", "она", "оно", "который", "которая", "которое",
    "страница", "странице", "сайте", "сайт", "казалось", "кажется",
}


def stem(w):
    if len(w) <= MIN_STEM:
        return w
    for suf in SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= MIN_STEM:
            return w[: len(w) - len(suf)]
    return w


def norm(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s).lower()
    s = s.replace("ё", "е")
    out = []
    for ch in s:
        cat = unicodedata.category(ch)
        if cat.startswith("L") or cat.startswith("N"):
            out.append(ch)
        else:
            out.append(" ")
    return re.sub(r"\s+", " ", "".join(out)).strip()


def tokenize_with_offsets(text):
    res = []
    for m in re.finditer(r"[^\W_]+", text, re.UNICODE):
        tok = m.group(0).lower().replace("ё", "е")
        res.append((stem(tok), m.start(), m.end()))
    return res


QUOTES = re.compile(r"[«»\"“”„‟]([^«»\"“”„‟]{3,200}?)[«»\"“”„‟]")


def quoted_parts(s):
    parts = []
    for q in QUOTES.findall(s or ""):
        q = q.strip().strip(" .!?,;:…-–—")
        if q:
            parts.append(q)
    return parts


# ---------------------------------------------------------------------------
# Загрузка реестров
# ---------------------------------------------------------------------------

def load_entities():
    entities = []

    def add(kind, name, status, registry_ref):
        entities.append({"kind": kind, "name": name.strip(), "status": status, "ref": registry_ref})

    fa = json.load(open("registries/foreign_agents.json", encoding="utf-8"))
    for r in fa["rows"]:
        raw = (r.get("field_2_s") or "").strip()
        if not raw:
            continue
        excl = (r.get("field_5_dt") or "").strip()
        status = f"Исключён из реестра {excl}" if excl else "Действующий иноагент"
        e = {
            "kind": "иноагент",
            "name": raw,
            "status": status,
            "ref": f"рег. № {r.get('field_8_s') or ''}".strip(),
            "type": (r.get("field_7_s") or "").strip(),
        }
        entities.append(e)

    eo = json.load(open("registries/extremist_orgs.json", encoding="utf-8"))
    for r in eo["rows"]:
        raw = (r.get("field_2_s") or "").strip()
        if raw:
            add("экстремистская организация", raw, "Запрещена судом", f"п. {r.get('field_1_s') or ''}".strip())

    un = json.load(open("registries/undesirable_orgs.json", encoding="utf-8"))
    for r in un["rows"]:
        raw = (r.get("field_5_s") or "").strip()
        if raw:
            st = (r.get("field_10_s") or "").strip() or "Нежелательная"
            add("нежелательная организация", raw, st, f"расп. № {r.get('field_3_s') or ''}".strip())

    em = json.load(open("registries/extremist_materials.json", encoding="utf-8"))
    for r in em["rows"]:
        for q in quoted_parts(r["material"]):
            if len(norm(q)) >= 8:
                add("экстремистский материал", q, f"Федеральный список, п. {r['num']}", f"ФСЭМ п. {r['num']}")

    return entities


FIO_RE = re.compile(
    r"^[А-ЯЁ][а-яё]+(?:-(?:[А-ЯЁ][а-яё]+))?(?: [А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)*){1,2}$"
)


def person_variants(name):
    n = norm(name)
    toks = n.split()
    variants = []
    if len(toks) == 3:
        fam, im, ot = toks
        variants.append((f"{fam} {im} {ot}", "ФИО полностью", "точное ФИО"))
        variants.append((f"{im} {fam} {ot}", "Имя Фамилия Отчество", "возможное (перестановка)"))
        variants.append((f"{fam} {im[0]} {ot[0]}", "Фамилия И. О.", "возможное (инициалы)"))
        variants.append((f"{im[0]} {ot[0]} {fam}", "И. О. Фамилия", "возможное (инициалы)"))
        variants.append((f"{im} {fam}", "Имя Фамилия", "возможное (имя-фамилия)"))
    elif len(toks) == 2:
        fam, im = toks
        variants.append((f"{fam} {im}", "Фамилия Имя", "точное ФИО"))
        variants.append((f"{im} {fam}", "Имя Фамилия", "возможное (перестановка)"))
    return variants


def build_patterns(entities, df, bdf, dropped):
    """df: Counter(токен -> число страниц); bdf: зарезервирован (частотность биграмм)."""
    pats = []

    def tok_tuple(s):
        return tuple(stem(t) for t in norm(s).split())

    def single_token_ok(s, kind, rest=""):
        """однословные алиасы — только очень редкие в корпусе слова (сравнение по стему);
        для организаций — ещё и если в остальной части имени нет своего редкого слова
        (иначе это ветки/филиалы вида «Свидетели Иеговы «Березовский»», где в кавычках город)"""
        w = stem(norm(s).split()[0])
        if df.get(w, 0) > DF_LIMIT_SINGLE:
            dropped.append({"alias": s, "kind": kind, "df": df.get(w, 0),
                            "причина": f"слово встречается на {df.get(w, 0)} страницах"})
            return False
        if rest:
            rest_toks = [stem(t) for t in norm(rest).split()]
            if any(df.get(t, 0) <= DF_LIMIT for t in rest_toks):
                dropped.append({"alias": s, "kind": kind, "df": df.get(w, 0),
                                "причина": "в имени вне кавычек есть редкое слово — кавычки лишь уточнение (город/филиал)"})
                return False
        return True

    def has_distinctive_token(s, kind):
        """в алиасе должно быть хотя бы одно редкое слово, иначе это шум"""
        toks = [stem(t) for t in norm(s).split()]
        if any(df.get(t, 0) <= DF_LIMIT for t in toks):
            return True
        dropped.append({"alias": s, "kind": kind,
                        "df": max(df.get(t, 0) for t in toks),
                        "причина": "все слова алиаса частотные"})
        return False

    for idx, e in enumerate(entities):
        name = e["name"]
        kind = e["kind"]
        seen = set()

        # физлицо? у иноагентов есть авторитетная колонка «Тип»; при её отсутствии — эвристика ФИО
        pre_quote = re.split(r"[«\"]", name)[0].strip()
        if kind == "иноагент" and e.get("type"):
            is_person = "Физические лица" in e["type"]
        else:
            is_person = kind == "иноагент" and FIO_RE.match(pre_quote) is not None

        # 1. Полное название (для организаций — целиком, с «шапкой»)
        n = norm(pre_quote if is_person else name)
        ntok = tok_tuple(n)
        if len(n) >= 6 and ntok:
            # названия материалов — это фрагменты из описаний, к ним те же фильтры мусора
            if kind == "экстремистский материал":
                toks_n = norm(name).split()
                ok = (n[:1].isalnum()
                      and not all(t in STOPWORDS for t in toks_n)
                      and has_distinctive_token(name, kind))
                if not ok:
                    continue
            if len(ntok) == 1 and not single_token_ok(n, kind):
                pass
            else:
                pats.append((ntok, "точное" if not is_person else "точное ФИО", "полное название", idx))
                seen.add(ntok)

        # 2. Названия в кавычках (не для физлиц)
        if not is_person:
            for q in quoted_parts(name):
                nq = norm(q)
                first_char = nq[:1]
                toks_q = norm(q).split()
                if not (first_char.isalnum()):
                    dropped.append({"alias": q, "kind": kind, "df": "-", "причина": "фрагмент начинается не с буквы/цифры"})
                    continue
                if all(t in STOPWORDS for t in toks_q):
                    dropped.append({"alias": q, "kind": kind, "df": "-", "причина": "фрагмент из служебных слов"})
                    continue
                if len(nq) < 5:
                    continue
                nqt = tok_tuple(q)
                if not nqt or nqt in seen:
                    continue
                if len(nqt) == 1:
                    if kind == "экстремистский материал" and len(nq) < 14:
                        continue
                    rest = re.sub(r"[«»\"“”„‟]" + re.escape(q) + r"[«»\"“”„‟]", " ", name)
                    if not single_token_ok(q, kind, rest=rest):
                        continue
                else:
                    if not has_distinctive_token(q, kind):
                        continue
                    # у организаций кавычки могут быть лишь уточнением (город/филиал):
                    # если в остальной части имени есть редкое слово — алиас не самостоятельный
                    if kind != "экстремистский материал":
                        rest = re.sub(r"[«»\"“”„‟]" + re.escape(q) + r"[«»\"“”„‟]", " ", name)
                        rest_toks = [stem(t) for t in norm(rest).split()]
                        if rest_toks and any(df.get(t, 0) <= DF_LIMIT for t in rest_toks):
                            dropped.append({"alias": q, "kind": kind, "df": "-",
                                            "причина": "в имени вне кавычек есть редкое слово — кавычки лишь уточнение (город/филиал)"})
                            continue
                pats.append((nqt, "точное", "краткое название «%s»" % q, idx))
                seen.add(nqt)

            # название без кавычек целиком (для имён с вложенными кавычками)
            if not is_person and any(c in name for c in "«»\""):
                plain = re.sub(r"[«»\"“”„‟]", " ", name)
                pt = tok_tuple(plain)
                if len(pt) >= 2 and pt not in seen:
                    pats.append((pt, "точное", "полное название (без кавычек)", idx))
                    seen.add(pt)

        # 3. Варианты ФИО
        if is_person:
            for v, label, tier in person_variants(pre_quote):
                vt = tok_tuple(v)
                if vt and vt not in seen:
                    pats.append((vt, tier, label, idx))
                    seen.add(vt)
    return pats


# ---------------------------------------------------------------------------
# Поиск
# ---------------------------------------------------------------------------

def search(pages, pats, entities, ctx_chars=120):
    index = defaultdict(list)
    for p in pats:
        index[p[0][0]].append(p)

    results = []
    for page in pages:
        text = page.get("text") or ""
        toks = tokenize_with_offsets(text)
        ntoks = len(toks)
        i = 0
        while i < ntoks:
            cands = index.get(toks[i][0])
            if cands:
                for ptoks, tier, label, eidx in cands:
                    ln = len(ptoks)
                    if i + ln > ntoks:
                        continue
                    if tuple(toks[i + k][0] for k in range(ln)) == ptoks:
                        e = entities[eidx]
                        start, end = toks[i][1], toks[i + ln - 1][2]
                        # название организации вида «Шапка «Имя»»: совпадение не должно
                        # продолжаться словами (иначе «проект "Эхо"» поймает «Эхо наших побед»)
                        if e["kind"] != "иноагент" or not FIO_RE.match(e["name"].split(" «")[0]):
                            has_q = any(c in e["name"] for c in "«»\"“”„‟")
                            if has_q and ln <= 3:
                                j = end
                                while j < len(text) and text[j].isspace():
                                    j += 1
                                if j < len(text) and (text[j].isalpha() or text[j].isdigit()):
                                    i += 1
                                    continue
                                # название целиком в кавычках — проверяем Заглавность в оригинале,
                                # иначе «Настоящая Россия» поймает «...настоящим России»
                                if e["name"][:1] in "«\"“„":
                                    span = text[toks[i][1]:end]
                                    words = re.findall(r"[^\W_]+", span, re.UNICODE)
                                    if not (words and all(w[0].isupper() for w in words)):
                                        i += 1
                                        continue
                        a = text.rfind(" ", 0, max(0, start - ctx_chars))
                        b = text.find(" ", min(len(text), end + ctx_chars))
                        context = re.sub(r"\s+", " ", text[a + 1 if a != -1 else 0: b if b != -1 else len(text)]).strip()
                        e = entities[eidx]
                        results.append({
                            "section": page.get("section", ""),
                            "url": page.get("url", ""),
                            "title": page.get("title", ""),
                            "kind": e["kind"],
                            "matched": e["name"],
                            "alias_label": label,
                            "tier": tier,
                            "status": e["status"],
                            "context": context,
                        })
                        break
            i += 1
    return results


# ---------------------------------------------------------------------------

def main(pages_file="site_text/pages.json"):
    entities = load_entities()

    pages = json.load(open(pages_file, encoding="utf-8"))
    print(f"страниц: {len(pages)}")

    # частота слов и биграмм по корпусу (число страниц, где встречаются)
    df = Counter()
    bdf = Counter()
    for p in pages:
        toks = [t for t, _, _ in tokenize_with_offsets(p.get("text") or "")]
        for tok in set(toks):
            df[tok] += 1
        for pair in set(zip(toks, toks[1:])):
            bdf[pair] += 1

    dropped = []
    pats = build_patterns(entities, df, bdf, dropped)
    print(f"сущностей: {len(entities)}, паттернов: {len(pats)}, отсеяно алиасов: {len(dropped)}")

    results = search(pages, pats, entities)
    dedup = {}
    for r in results:
        key = (r["url"], r["matched"], r["tier"])
        if key not in dedup:
            r["hits_on_page"] = 1
            dedup[key] = r
        else:
            dedup[key]["hits_on_page"] += 1

    out = list(dedup.values())
    with open("matches_raw.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    with open("dropped_aliases.json", "w", encoding="utf-8") as f:
        json.dump(dropped, f, ensure_ascii=False, indent=1)

    print(f"совпадений (уникальных страница×сущность×тип): {len(out)}")
    from collections import Counter as C
    print("по типу:", dict(C(r["kind"] for r in out)))
    top = C(r["matched"] for r in out).most_common(12)
    print("топ сущностей:")
    for name, cnt in top:
        print(f"  {cnt:5d}  {name[:75]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*(sys.argv[1:] or [])))
