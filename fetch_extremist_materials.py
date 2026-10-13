# -*- coding: utf-8 -*-
"""Скачивание федерального списка экстремистских материалов Минюста (55 страниц по 100 записей)."""
import json
import re
import time
import warnings

import requests
import urllib3

urllib3.disable_warnings()
warnings.filterwarnings("ignore")

BASE = "https://minjust.gov.ru/ru/extremist-materials/"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
ROW = re.compile(r"<tr><td>(\d+)</td><td>(.*?)</td><td>(.*?)</td></tr>", re.S)


def strip_tags(s):
    s = re.sub(r"<[^>]+>", " ", s)
    s = s.replace("&quot;", '"').replace("&#34;", '"').replace("&laquo;", "«").replace("&raquo;", "»")
    s = s.replace("&amp;", "&").replace("&nbsp;", " ").replace("&mdash;", "—").replace("&ndash;", "–")
    s = s.replace("&gt;", ">").replace("&lt;", "<").replace("&rsquo;", "’").replace("&lsquo;", "‘")
    s = s.replace("&ldquo;", "“").replace("&rdquo;", "”")
    return re.sub(r"\s+", " ", s).strip()


def main():
    session = requests.Session()
    session.headers.update(UA)
    all_rows = []
    page = 1
    while page <= 60:
        for attempt in range(4):
            try:
                r = session.get(BASE, params={"page": page}, timeout=90, verify=False)
                r.raise_for_status()
                break
            except Exception as e:
                print(f"page {page}: retry {attempt + 1} ({e})")
                time.sleep(3 * (attempt + 1))
        else:
            raise RuntimeError(f"failed page {page}")
        rows = [(int(n), strip_tags(mat), strip_tags(date)) for n, mat, date in ROW.findall(r.text)]
        if not rows:
            print(f"page {page}: no rows, stop")
            break
        all_rows.extend(rows)
        print(f"page {page}: {len(rows)} rows (cumulative {len(all_rows)}, last #{rows[-1][0]})")
        if len(rows) < 100:
            break
        page += 1
        time.sleep(0.5)
    with open("registries/extremist_materials.json", "w", encoding="utf-8") as f:
        json.dump({"total": len(all_rows), "rows": [{"num": n, "material": m, "date": d} for n, m, d in all_rows]}, f, ensure_ascii=False)
    print(f"saved registries/extremist_materials.json: {len(all_rows)} entries")


if __name__ == "__main__":
    main()
