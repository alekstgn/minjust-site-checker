# -*- coding: utf-8 -*-
"""Слияние вердиктов субагентов + детерминированного правила ±500 знаков.

Приоритет итогового вердикта о маркировке:
  1. Правило ±500 («иноагент»/«иностранный агент» в окне от упоминания) — есть → «есть»
  2. Иначе вердикт ИИ («есть»/«нет»/«неопределённо»)
  Для тёзок — «не применимо (тёзка)» независимо от правила.
"""
import glob
import json
import sys


def main():
    matches = json.load(open("matches_raw.json", encoding="utf-8"))
    rule = json.load(open("marking_rule.json", encoding="utf-8"))
    verdicts = {}
    for f in sorted(glob.glob("ai_batch/batch_*_verdicts.json")):
        for v in json.load(open(f, encoding="utf-8")):
            verdicts[v["idx"]] = v

    for i, r in enumerate(matches):
        v = verdicts.get(i, {})
        ru = rule.get(str(i), {})
        r["ai_subject"] = v.get("subject", "")
        r["ai_subject_note"] = v.get("subject_note", "")
        r["ai_marking"] = v.get("marking", "")
        r["ai_evidence"] = v.get("marking_evidence", "")
        r["ai_comment"] = v.get("comment", "")
        r["rule_marking"] = ru.get("rule", "")
        r["rule_evidence"] = ru.get("evidence", "")

        if r["ai_subject"] == "тёзка/другое значение":
            r["final_marking"] = "не применимо (тёзка)"
        elif r["rule_marking"] == "есть":
            r["final_marking"] = "есть (правило ±500)"
        elif r["ai_marking"] == "есть":
            r["final_marking"] = "есть (ИИ)"
        else:
            r["final_marking"] = r["ai_marking"] or "нет"

    json.dump(matches, open("matches_verdicts.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    real = [r for r in matches if r["ai_subject"] == "реальная сущность"]
    from collections import Counter
    print(f"слито: {len(verdicts)} ИИ-вердиктов + правило на {len(matches)} находок")
    print("реальных сущностей:", len(real))
    print("итоговая маркировка (реальные):", dict(Counter(r["final_marking"] for r in real)))


if __name__ == "__main__":
    sys.exit(main())
