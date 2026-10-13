# -*- coding: utf-8 -*-
"""Массовая выгрузка текстов страниц history.ru по разделам (URL из sitemap)."""
import json
import re
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import requests
import urllib3
from lxml import html as lhtml

urllib3.disable_warnings()
warnings.filterwarnings("ignore")

BASE = "https://history.ru"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
DROP = "//script|//style|//noscript|//nav|//header|//footer|//aside|//*[@class='breadcrumb']"

SECTIONS = {
    "Статьи": "/read/articles/",
    "Памятники": "/read/monuments/",
    "События": "/read/news/",
    "Биографии": "/read/biographies/",
    "Исследования": "/read/science/",
}

_tls = requests.packages.urllib3.util.ssl_.create_urllib3_context()


def load_sitemap_urls():
    urls = []
    for i in (1, 2):
        xml = open(f"site_text/sitemap{i}.xml", encoding="utf-8", errors="replace").read()
        urls += re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
    return urls


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


def fetch_one(session, section, url):
    for attempt in range(3):
        try:
            r = session.get(url, timeout=60, verify=False)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            text = extract_text(r.text)
            if len(text) < 150:
                return None
            return {"url": url, "section": section, "title": extract_title(r.text), "text": text}
        except Exception:
            if attempt == 2:
                return None
            time.sleep(1.5 * (attempt + 1))


def main():
    all_urls = load_sitemap_urls()
    tasks = []
    for section, prefix in SECTIONS.items():
        for u in all_urls:
            path = urlparse(u).path
            if path.startswith(prefix) and path != prefix:
                tasks.append((section, u))
    print(f"к выгрузке: {len(tasks)} страниц")

    session = requests.Session()
    session.headers.update(UA)

    pages, done = [], 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch_one, session, s, u): (s, u) for s, u in tasks}
        for fut in as_completed(futs):
            res = fut.result()
            done += 1
            if res:
                pages.append(res)
            if done % 250 == 0:
                rate = done / (time.time() - t0)
                print(f"  {done}/{len(tasks)} ({rate:.1f} стр/с, ок {len(pages)})")
                with open("site_text/pages.json", "w", encoding="utf-8") as f:
                    json.dump(pages, f, ensure_ascii=False)

    with open("site_text/pages.json", "w", encoding="utf-8") as f:
        json.dump(pages, f, ensure_ascii=False)
    from collections import Counter
    c = Counter(p["section"] for p in pages)
    print("готово:", dict(c), f"всего {len(pages)} за {time.time()-t0:.0f}с")


if __name__ == "__main__":
    sys.exit(main())
