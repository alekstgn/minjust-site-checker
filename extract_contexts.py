# -*- coding: utf-8 -*-
"""Готовит данные для ИИ-контекстного анализа срабатываний.

Вход:  matches_raw.json + site_text/pages_history.json
Выход: ai_batch/batch_N.json — находки с широким контекстом (±500 знаков)
       и хвостом страницы (там обычно стоят сноски «* признаны иноагентами»).
"""
import json
import os
import re
import sys


def tokenize(text):
    return [(m.group(0).lower().replace("ё", "е"), m.start(), m.end())
            for m in re.finditer(r"[^\W_]+", text, re.UNICODE)]


def find_context(text, entity_name, window=500):
    """Ищет все вхождения токенов имени сущности, возвращает самое длинное окружение."""
    toks = tokenize(text)
    pat = [t for t, _, _ in tokenize(entity_name)]
    best = ""
    n = len(pat)
    for i in range(len(toks) - n + 1):
        if [t for t, _, _ in toks[i:i + n]] == pat:
            s, e = toks[i][1], toks[i + n - 1][2]
            a = text.rfind(" ", 0, max(0, s - window))
            b = text.find(" ", min(len(text), e + window))
            ctx = text[a + 1 if a != -1 else 0: b if b != -1 else len(text)]
            if len(ctx) > len(best):
                best = re.sub(r"\s+", " ", ctx).strip()
    return best


def main(matches_file="matches_raw.json", pages_file="site_text/pages_history.json",
         out_dir="ai_batch", batch_size=70):
    matches = json.load(open(matches_file, encoding="utf-8"))
    pages = {p["url"]: p for p in json.load(open(pages_file, encoding="utf-8"))}
    os.makedirs(out_dir, exist_ok=True)

    items = []
    for idx, r in enumerate(matches):
        p = pages.get(r["url"])
        text = p.get("text", "") if p else ""
        ctx = find_context(text, r["matched"]) or r.get("context", "")
        # хвост страницы: сноски со звёздочками обычно в конце
        tail = re.sub(r"\s+", " ", text[-450:]).strip() if text else ""
        items.append({
            "idx": idx,
            "url": r["url"],
            "section": r.get("section", ""),
            "page_title": r.get("title", ""),
            "kind": r["kind"],
            "entity": r["matched"],
            "entity_status": r.get("status", ""),
            "tier": r.get("tier", ""),
            "hit_context": r.get("context", ""),
            "wide_context": ctx[:1800],
            "page_tail": tail,
        })

    for b in range(0, len(items), batch_size):
        chunk = items[b:b + batch_size]
        with open(f"{out_dir}/batch_{b // batch_size:02d}.json", "w", encoding="utf-8") as f:
            json.dump(chunk, f, ensure_ascii=False, indent=1)
        print(f"{out_dir}/batch_{b // batch_size:02d}.json: {len(chunk)} находок")
    print(f"всего: {len(items)}")


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
