# -*- coding: utf-8 -*-
"""Выгрузка текстов страниц сайта по разделам.

Использование:
  python -X utf8 fetch_site.py <BASE_URL> --sections "Статьи=/articles" "Памятники=/monuments" ...

Если разделы не указаны — сначала выводит sitemap/меню и подсказывает, какие пути есть.
Тексты складываются в site_text/pages.json: [{"url","section","title","text"}]
"""
import json
import re
import sys
import time
import warnings
from urllib.parse import urljoin, urlparse

import requests
import urllib3
from lxml import html as lhtml

urllib3.disable_warnings()
warnings.filterwarnings("ignore")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
DROP = "//script|//style|//noscript|//nav|//header|//footer|//aside|//*[@class='breadcrumb']"


def get(session, url, **kw):
    r = session.get(url, timeout=60, verify=False, **kw)
    r.raise_for_status()
    return r.text


def load_sitemap(session, base, seen=None):
    """Рекурсивно обходит sitemap index."""
    seen = seen or set()
    urls = []
    try:
        xml = get(session, urljoin(base, "/sitemap.xml"))
    except Exception:
        return urls
    if ".gz" in xml[:200] or xml.startswith("\x1f\x8b"):
        import gzip
        xml = gzip.decompress(xml.encode("latin-1") if isinstance(xml, str) else xml).decode("utf-8", "replace")
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
    for loc in locs:
        if loc.endswith(".xml") and loc not in seen:
            seen.add(loc)
            sub = load_sitemap(session, loc, seen)
            urls.extend(sub)
        else:
            urls.append(loc)
    return urls


def extract_text(page_html):
    doc = lhtml.fromstring(page_html)
    for bad in doc.xpath(DROP):
        bad.getparent().remove(bad)
    # приоритет: article, main, .content-подобные контейнеры, затем body
    for xp in ["//article", "//main", "//div[contains(@class,'content') and not(contains(@class,'content-'))]",
               "//div[@id='content']", "//body"]:
        nodes = doc.xpath(xp)
        if nodes:
            t = re.sub(r"[ \t]+", " ", nodes[0].text_content())
            t = re.sub(r"\n\s*\n+", "\n", t).strip()
            if len(t) > 200:
                return t
    t = re.sub(r"\s+", " ", doc.text_content()).strip()
    return t


def extract_title(page_html):
    doc = lhtml.fromstring(page_html)
    t = doc.xpath("//h1//text()")
    if t and t[0].strip():
        return re.sub(r"\s+", " ", t[0]).strip()
    t = doc.xpath("//title//text()")
    return re.sub(r"\s+", " ", t[0]).strip() if t else ""


def same_site(base, url):
    return urlparse(url).netloc == urlparse(base).netloc


def discover_from_section(session, base, section_url, max_pages=2000):
    """Обходит раздел: пагинация ?page=N / /page-N + обычные ссылки из индексных страниц."""
    to_visit = [urljoin(base, section_url)]
    visited = set()
    page_urls = []
    while to_visit and len(visited) < max_pages:
        url = to_visit.pop(0)
        if url in visited or not same_site(base, url):
            continue
        visited.add(url)
        try:
            html = get(session, url)
        except Exception as e:
            print(f"  ! skip {url} ({e})")
            continue
        page_urls.append(url)
        doc = lhtml.fromstring(html)
        for a in doc.xpath("//a[@href]"):
            href = urljoin(url, a.get("href"))
            frag = urlparse(href)
            if not same_site(base, href) or frag.path in ("", "/"):
                continue
            # ссылки пагинации и ссылки внутри раздела
            if frag.path.startswith(urlparse(urljoin(base, section_url)).path):
                if href not in visited and href not in to_visit and len(visited) + len(to_visit) < max_pages:
                    to_visit.append(href)
        time.sleep(0.25)
    return page_urls


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    base = args[0].rstrip("/")
    sections = {}
    i = 1
    while i < len(args):
        if args[i] == "--sections":
            i += 1
            continue
        if "=" in args[i]:
            name, path = args[i].split("=", 1)
            sections[name] = path
        i += 1

    session = requests.Session()
    session.headers.update(UA)

    if not sections:
        sm = [u for u in load_sitemap(session, base) if same_site(base, u)]
        print(f"sitemap: {len(sm)} URL, примеры:")
        for u in sm[:40]:
            print("  ", u)
        return 0

    pages = []
    for name, path in sections.items():
        print(f"раздел «{name}»: обход {urljoin(base, path)}")
        urls = discover_from_section(session, base, path)
        print(f"  найдено страниц: {len(urls)}")
        for u in urls:
            try:
                html = get(session, u)
            except Exception as e:
                print(f"  ! skip {u} ({e})")
                continue
            text = extract_text(html)
            if len(text) < 100:
                continue
            pages.append({"url": u, "section": name, "title": extract_title(html), "text": text})
            time.sleep(0.25)
        print(f"  сохранено с текстом: {len(pages)}")

    import os
    os.makedirs("site_text", exist_ok=True)
    with open("site_text/pages.json", "w", encoding="utf-8") as f:
        json.dump(pages, f, ensure_ascii=False)
    print(f"итого: {len(pages)} страниц → site_text/pages.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
