# -*- coding: utf-8 -*-
"""Слияние вердиктов субагентов с исходными находками → matches_verdicts.json"""
import glob
import json
import sys


def main():
    matches = json.load(open("matches_raw.json", encoding="utf-8"))
    verdicts = {}
    for f in sorted(glob.glob("ai_batch/batch_*_verdicts.json")):
        for v in json.load(open(f, encoding="utf-8")):
            verdicts[v["idx"]] = v

    missing = len(matches) - len(verdicts)
    for i, r in enumerate(matches):
        v = verdicts.get(i)
        if v:
            r["ai_subject"] = v.get("subject", "")
            r["ai_subject_note"] = v.get("subject_note", "")
            r["ai_marking"] = v.get("marking", "")
            r["ai_evidence"] = v.get("marking_evidence", "")
            r["ai_comment"] = v.get("comment", "")

    json.dump(matches, open("matches_verdicts.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"слияно: {len(verdicts)} вердиктов на {len(matches)} находок, без вердикта: {missing}")


if __name__ == "__main__":
    sys.exit(main())
