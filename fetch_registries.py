# -*- coding: utf-8 -*-
"""Выгрузка реестров Минюста (иноагенты, экстремистские организации, нежелательные организации)
через REST API reestrs.minjust.gov.ru."""
import json
import time
import sys
import warnings

import requests
import urllib3

# Минюст использует российский корневой УЦ, которого нет в certifi —
# для публичного read-only API отключаем проверку сертификата.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore")

BASE = "https://reestrs.minjust.gov.ru"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}

REGISTRIES = {
    "foreign_agents": "39b95df9-9a68-6b6d-e1e3-e6388507067e",   # Реестр иностранных агентов
    "extremist_orgs": "59961ebb-9f0e-d885-7ebc-b90399923b03",   # Перечень организаций, признанных экстремистскими
    "undesirable_orgs": "c2d1692e-a9f6-5a79-13ee-5da5b42980df", # Нежелательные организации
}


def fetch_registry(name, reg_id, page_size=500):
    rows = []
    offset = 0
    session = requests.Session()
    session.headers.update(UA)
    while True:
        payload = {"offset": offset, "limit": page_size, "search": "", "facets": {}, "sort": []}
        for attempt in range(5):
            try:
                r = session.post(f"{BASE}/rest/registry/{reg_id}/values", json=payload, timeout=120, verify=False)
                r.raise_for_status()
                break
            except Exception as e:
                print(f"  retry {attempt+1} ({e})")
                time.sleep(3 * (attempt + 1))
        else:
            raise RuntimeError(f"failed to fetch {name} at offset {offset}")
        data = r.json()
        values = data.get("values", [])
        rows.extend(values)
        print(f"{name}: offset={offset}, got={len(values)}, total={data.get('size')}")
        offset += len(values)
        if not values or offset >= data.get("size", 0):
            break
        time.sleep(0.4)
    return {"registry_id": reg_id, "total": data.get("size"), "rows": rows}


def main():
    for name, reg_id in REGISTRIES.items():
        out = f"registries/{name}.json"
        result = fetch_registry(name, reg_id)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
        print(f"saved {out}: {len(result['rows'])} rows (server total: {result['total']})")


if __name__ == "__main__":
    sys.exit(main())
