# -*- coding: utf-8 -*-
"""Выгрузка текстов страниц znanierussia.ru (статьи-энциклопедия + новости).

Карточки /events (100-200 знаков) и мёртвые /speakers («Спикер не найден»)
не выгружаются сознательно — там нет текста для анализа.
"""
import gzip
import json
import os
import re
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import urllib3
from lxml import html as lhtml

urllib3.disable_warnings()
warnings.filterwarnings("ignore")

BASE = "https://znanierussia.ru"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
DROP = "//script|//style|//noscript|//nav|//header|//footer|//aside|//*[@class='breadcrumb']"
OUT = "site_text/pages_znanie.json"


def load_urls():
    def locs(x):
        return re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", x)
    urls = []
    urls += locs(open("site_text/znanie_main.xml", encoding="utf-8", errors="replace").read())
    events = locs(open("site_text/znanie_events.xml", encoding="utf-8", errors="replace").read())
    urls += [u for u in events if "/news/" in u]
    for gz in ("site_text/znanie_wiki0.xml.gz", "site_text/znanie_wiki1.xml.gz"):
        urls += locs(gzip.open(gz, "rt", encoding="utf-8", errors="replace").read())
    return sorted(set(u for u in urls if u.rstrip("/") != BASE))


def extract_text(page_html):
    doc = lhtml.fromstring(page_html)
    for bad in doc.xpath(DROP):
        parent = bad.getparent()
        if parent is not None:
            parent.remove(bad)
    for xp in ["//article", "//main", "//div[contains(@class,'content') and not(contains(@class,'content-'))]",
               "//div[@id='content']", "//body"]:
        nodes = doc.xpath(xp)
        if nodes:
            t = re.sub(r"[ \t]+", " ", nodes[0].text_content())
            t = re.sub(r"\n\s*\n+", "\n", t).strip()
            if len(t) > 200:
                return t
    return re.sub(r"\s+", " ", doc.text_content() or "").strip()


def extract_title(page_html):
    doc = lhtml.fromstring(page_html)
    t = doc.xpath("//h1//text()")
    if t and t[0].strip():
        return re.sub(r"\s+", " ", t[0]).strip()
    t = doc.xpath("//title//text()")
    return re.sub(r"\s+", " ", t[0]).strip() if t else ""


def section_of(url):
    p = url.replace(BASE, "").strip("/").split("/")
    if p[0] == "news":
        return "Новости"
    if p[0] == "articles":
        return "Статьи (энциклопедия)"
    return "Прочее"


def fetch_one(session, url):
    for attempt in range(8):
        try:
            r = session.get(url, timeout=60, verify=False)
            if r.status_code in (404, 500):
                return None
            if r.status_code in (429, 503):
                # сайт лимитирует — пауза и повтор, страницу не роняем
                time.sleep(45 + 20 * attempt)
                continue
            r.raise_for_status()
            text = extract_text(r.text)
            if len(text) < 300 or "Спикер не найден" in text[:100]:
                return None
            return {"url": url, "section": section_of(url), "title": extract_title(r.text), "text": text}
        except Exception:
            time.sleep(3 + 2 * attempt)
    return None


def main():
    urls = load_urls()
    # докачка: пропускаем уже выгруженные
    pages = []
    if os.path.exists(OUT):
        pages = json.load(open(OUT, encoding="utf-8"))
        done_urls = {p["url"] for p in pages}
        urls = [u for u in urls if u not in done_urls]
        print(f"в чекпоинте {len(done_urls)} страниц, к докачке: {len(urls)}", flush=True)
    else:
        print(f"к выгрузке: {len(urls)}", flush=True)
    session = requests.Session()
    session.headers.update(UA)
    base = len(pages)

    done = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(fetch_one, session, u): u for u in urls}
        for fut in as_completed(futs):
            res = fut.result()
            done += 1
            if res:
                pages.append(res)
            if done % 1000 == 0:
                rate = done / (time.time() - t0)
                print(f"  {done}/{len(urls)} ({rate:.1f} стр/с, ок {len(pages)-base})", flush=True)
                with open(OUT, "w", encoding="utf-8") as f:
                    json.dump(pages, f, ensure_ascii=False)
            if done % 20000 == 0:
                with open(OUT.replace(".json", "_ckpt.json"), "w", encoding="utf-8") as f:
                    json.dump(pages, f, ensure_ascii=False)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(pages, f, ensure_ascii=False)
    from collections import Counter
    print("готово:", dict(Counter(p["section"] for p in pages)), f"всего {len(pages)} за {time.time()-t0:.0f}с")


if __name__ == "__main__":
    sys.exit(main())
