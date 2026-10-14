# -*- coding: utf-8 -*-
"""Выгрузка текстов страниц rvio.ru из sitemap: центральные новости + региональные отделения."""
import json
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

BASE = "https://rvio.ru"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
DROP = "//script|//style|//noscript|//nav|//header|//footer|//aside|//*[@class='breadcrumb']"
OUT = "site_text/pages_rvio.json"


def load_urls():
    xml = open("site_text/rvio_sitemap.xml", encoding="utf-8", errors="replace").read()
    return re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)


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
    if p[0] == "activities":
        return "Новости РВИО"
    if p[0].isdigit():
        return f"Регионы /{p[0]}"
    return "Прочее"


def fetch_one(session, url):
    for attempt in range(3):
        try:
            r = session.get(url, timeout=60, verify=False)
            if r.status_code in (404, 500):
                return None
            r.raise_for_status()
            text = extract_text(r.text)
            if len(text) < 150 or "Сайт временно недоступен" in text[:200]:
                return None
            return {"url": url, "section": section_of(url), "title": extract_title(r.text), "text": text}
        except Exception:
            if attempt == 2:
                return None
            time.sleep(1.5 * (attempt + 1))


def main():
    urls = [u for u in load_urls() if u.rstrip("/") != BASE]
    print(f"к выгрузке: {len(urls)}")
    session = requests.Session()
    session.headers.update(UA)

    pages, done = [], 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(fetch_one, session, u): u for u in urls}
        for fut in as_completed(futs):
            res = fut.result()
            done += 1
            if res:
                pages.append(res)
            if done % 1000 == 0:
                rate = done / (time.time() - t0)
                print(f"  {done}/{len(urls)} ({rate:.1f} стр/с, ок {len(pages)})", flush=True)
                with open(OUT, "w", encoding="utf-8") as f:
                    json.dump(pages, f, ensure_ascii=False)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(pages, f, ensure_ascii=False)
    from collections import Counter
    print("готово:", dict(Counter(p["section"].split(" /")[0] for p in pages)), f"всего {len(pages)} за {time.time()-t0:.0f}с")


if __name__ == "__main__":
    sys.exit(main())
