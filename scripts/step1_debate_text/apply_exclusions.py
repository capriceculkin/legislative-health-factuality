#!/usr/bin/env python3
"""
apply_exclusions.py
Removes bill-days listed in data/v3_exclusions.json from the sentences and
predications files, but ONLY after the bill-day is confirmed against an official
record independent of our own text:
  US       Congress.gov action list for the bill has no House action that day
  Ontario  the OLA bill status page does not list that date for the bill
  or the entry carries a by-hand verification against the official record.
Anything not confirmed is HELD (kept in the data) and listed for a look.
Report: outputs/audit/exclusions_applied.csv The files as they were before any exclusion are
kept next to them as *_pre_exclusions.json; a second run does not overwrite that backup
with an already-trimmed file. Safe to run more than once.

Run from project root:  python3 scripts/step1_debate_text/apply_exclusions.py
"""
import csv, json, shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
EXC = ROOT / "data" / "v3_exclusions.json"
AUD = ROOT / "outputs" / "audit"


def load_exclusions():
    if not EXC.exists():
        return []
    with open(EXC, encoding="utf-8") as f:
        return json.load(f)


def excluded(rules, j, bk, d):
    for r in rules:
        if r["jurisdiction"] == j and r["bill_key"] == bk and r.get("date", "*") in ("*", d):
            return r
    return None


MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]


def verify(r):
    """(True, note) when an official record independent of our text confirms the bill was
    not before the House that day; (False, note) otherwise."""
    import re
    if r.get("verified"):
        return True, r["verified"]
    j, bk, d = r["jurisdiction"], r["bill_key"], r.get("date", "*")
    if d == "*":
        return False, "whole-bill removals are not done here (see the health list decisions)"
    if j == "us":
        p = ROOT / "data/v3_status_cache/us" / f"{bk}.actions.json"
        if not p.exists():
            return False, "no Congress.gov action list cached for this bill"
        acts = json.loads(p.read_text(encoding="utf-8")).get("actions") or []
        same = [a.get("text", "") for a in acts if str(a.get("actionDate", ""))[:10] == d
                and not (re.search(r"\bSenate\b", a.get("text", "")) and not re.search(r"\bHouse\b", a.get("text", "")))]
        if same:
            return False, f"Congress.gov shows House action on this bill that day ({same[0][:120]}); the real debate may be missing"
        return True, f"Congress.gov lists {len(acts)} actions for this bill and none in the House on {d}"
    if j == "ontario":
        p = ROOT / "data/v3_status_cache/ontario" / f"{bk}.html"
        if not p.exists():
            return False, "no OLA bill status page for this bill (before 1995 or not published)"
        t = p.read_text(encoding="utf-8", errors="ignore")
        y, m, dd = d.split("-")
        long = f"{MONTHS[int(m) - 1]} {int(dd)}, {y}"
        if long in t:
            return False, f"the OLA status page lists {long} for this bill; the real debate may be missing"
        return True, f"the OLA status page for this bill does not list {long}"
    return False, "no independent official check available"


def keep_backup(p, bak, stamp):
    """True when the file on disk was written by this script, so the backup next to it
    already holds the file as it was before any exclusion and must not be overwritten.
    False after a rebuild has written a fresh file (then the fresh file is backed up)."""
    if not bak.exists():
        return False
    st = p.stat()
    if stamp.exists():
        return stamp.read_text().split() == [str(st.st_size), str(st.st_mtime_ns)]
    # files from before the stamp existed: this script only ever shrinks the file it
    # backed up, so a file smaller than its backup is one it wrote
    return st.st_size < bak.stat().st_size


def main():
    rules = load_exclusions()
    checked = []
    for r in rules:
        ok, note = verify(r)
        checked.append((r, ok, note))
    rules = [r for r, ok, _ in checked if ok]
    print(f"confirmed against the official record: {len(rules)}; held (kept in the data): "
          f"{sum(1 for _, ok, _ in checked if not ok)}")
    print(f"removing the {len(rules)} confirmed bill-days")
    AUD.mkdir(parents=True, exist_ok=True)
    report = []
    for j in ("us", "ontario", "quebec"):
        mine = [r for r in rules if r["jurisdiction"] == j]
        if not mine:
            continue
        for kind in ("sentences_v3.json", "predications_v3.json"):
            p = ROOT / "data" / "dbpedia_pipeline" / j / kind
            with open(p, encoding="utf-8") as f:
                rows = json.load(f)
            keep, gone = [], Counter()
            for r in rows:
                hit = excluded(mine, j, r.get("bill_key", ""), r.get("date", ""))
                if hit:
                    gone[(hit["bill_key"], hit.get("date", "*"))] += 1
                else:
                    keep.append(r)
            if gone:
                bak = p.with_name(p.stem + "_pre_exclusions.json")
                stamp = p.with_name(p.stem + "_pre_exclusions.stamp")
                if keep_backup(p, bak, stamp):
                    print(f"  {j} {kind}: the existing backup already holds this file before any exclusion; kept")
                else:
                    shutil.copy2(p, bak)
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(keep, f, ensure_ascii=False)
                st = p.stat()
                stamp.write_text(f"{st.st_size} {st.st_mtime_ns}")
            print(f"  {j} {kind}: removed {sum(gone.values()):,} of {len(rows):,}")
            for (bk, d), n in sorted(gone.items()):
                report.append({"jurisdiction": j, "file": kind, "bill_key": bk, "date": d, "rows_removed": n})
    with open(AUD / "exclusions_applied.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["status", "jurisdiction", "bill_key", "date", "official_check", "reason",
                                          "sentence_rows_removed", "predication_rows_removed"])
        w.writeheader()
        for r, ok, note in checked:
            rm = {x["file"]: x["rows_removed"] for x in report if x["bill_key"] == r["bill_key"] and x["date"] == r.get("date", "*")}
            w.writerow({"status": "REMOVED" if ok else "HELD", "jurisdiction": r["jurisdiction"], "bill_key": r["bill_key"],
                        "date": r.get("date", "*"), "official_check": note, "reason": r.get("reason", ""),
                        "sentence_rows_removed": rm.get("sentences_v3.json", 0),
                        "predication_rows_removed": rm.get("predications_v3.json", 0)})
    (AUD / "exclusions_confirmed.json").write_text(json.dumps([r for r in rules], ensure_ascii=False, indent=1),
                                                   encoding="utf-8")
    print(f"wrote {AUD / 'exclusions_applied.csv'}")


if __name__ == "__main__":
    main()
