#!/usr/bin/env python3
"""
fix_sections_fix8.py   (edits the US and Ontario section data; keeps copies; a minute)

The corrections from Claude's full read of the US and Ontario sections against their saved pages (Oct 5):

 US 1. Lines lost at page breaks. Where the Record prints a page marker and text on the same line
       ("[[Page H4384]] our senior citizens to be continued while permitting a"), the line was dropped, and where
       that line began a new speaker ("  [[Page H4389]] Mr. WYDEN. Mr. Chairman, ...") the speech was glued to the
       one before. 11 places, all in two sections (H.R. 483 on 1995-04-06, H.R. 1590 on 1995-05-16). The text is put
       back from the saved pages, and us_rebuild.py reads such lines from now on.
 US 2. Text that is not about the bill is set aside (tag "notbill", which text_choices.json keeps out):
       - H.R. 5716 on 2002-11-14: the section is the whole end-of-session "Disposing of various legislative measures"
         (about 45 bills, 45,829 counted words). Only its H.R. 5716 part is kept (the bill's heading and text, and
         Mr. Boehner's statement); the rest is about other bills (HOPE VI housing, S. 2237, ...).
       - H.R. 3607 on 1989-11-21: three special orders at the end of the day (leveraged buyouts, smog, hospital
         closings) that never mention the bill.
       - H.R. 670 on 1993-03-25: the weekly schedule colloquy (Michel and Gephardt), which never mentions the bill.
       - H.R. 3762 on 2016-02-01: a one-minute speech on the Iran Terror Finance Transparency Act.
       - H.R. 2668 on 2013-07-16: a one-minute speech on H.R. 2667, the other mandate-delay bill.
 ON 3. Two Ontario bill-days are another bill with the same short title: 33-1 Bill 52 on 1985-12-17 is the first
       reading of Bill 86, and 33-3 Bill 79 on 1987-06-29 is the first reading of Bill 106. They are added to
       data/v3_exclusions.json with the reason, so apply_exclusions.py takes their sentences and claims out.
Every edit checks the text it expects first; if anything is not as expected, nothing is changed.
Run from the project folder:  python3 scripts/step1_debate_text/fix_sections_fix8.py <copy folder>
"""
import difflib
import json
import os
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / "data" / "us" / "v3" / "segments_index.json").exists():
    ROOT = Path.home() / "MiscellaneousProjects" / "legislative-health-factuality"
os.chdir(ROOT)
BACK = Path(sys.argv[1]) if len(sys.argv) > 1 else None
if BACK is None or not BACK.is_dir():
    sys.exit("Give the copy folder made by run_fix8.sh. Nothing changed.")
US = Path("data/us")
INDEX = US / "v3" / "segments_index.json"
REB = Path("scripts/step1_debate_text/us_rebuild.py")
CHO_PY = Path("scripts/step1_debate_text/apply_us_text_choices.py")
CHO = US / "v3" / "text_choices.json"
EXC = Path("data/v3_exclusions.json")
REPORT = Path("outputs/audit/fix8_corrections.txt")
MARK = "PATCHED_PAGEMARK_2026_10_05"
LINES = []


def say(s=""):
    print(s, flush=True)
    LINES.append(str(s))


OLD_LINE = '        s = ln.rstrip()\n'
NEW_LINE = ('        s = re.sub(r"^(\\s*)\\[\\[Page [^\\]]*\\]\\]\\s*(?=\\S)", r"\\1", ln.rstrip())  # ' + MARK +
            ': keep the text after a page marker\n')


def readers(src):
    i = src.index("def daily_paragraphs(text):")
    j = src.index("# ====", i)
    body = src[i:j]
    old_body = body.replace(NEW_LINE, OLD_LINE)
    if old_body.count(OLD_LINE) != 1:
        raise RuntimeError("us_rebuild.py daily_paragraphs is not in the expected form")
    new_body = old_body.replace(OLD_LINE, NEW_LINE)
    a, b = {"re": re}, {"re": re}
    exec(old_body, a)
    exec(new_body, b)
    return a["daily_paragraphs"], b["daily_paragraphs"], i, j, old_body, new_body


def repair_unit(sec_paras, sec_tags, raw, old, new):
    a, b = old(raw), new(raw)
    if a == b:
        return None
    sa = [p.strip() for p in a]
    pos, k = [], 0
    for w in (p.strip() for p in sec_paras):
        while k < len(sa) and sa[k] != w:
            k += 1
        if k == len(sa):
            raise RuntimeError("a section paragraph is not on the saved page in order")
        pos.append(k)
        k += 1
    tag_at = {pos[n]: sec_tags[n] for n in range(len(sec_paras))}
    out_p, out_t, changed = [], [], 0
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op == "equal":
            for d, q in enumerate(range(i1, i2)):
                if q in tag_at:
                    out_p.append(b[j1 + d])
                    out_t.append(tag_at[q])
            continue
        if op == "insert":
            if (i1 - 1) in tag_at and i1 in tag_at:
                for q in range(j1, j2):
                    out_p.append(b[q])
                    out_t.append(tag_at[i1 - 1])
                    changed += 1
            continue
        mine = [q for q in range(i1, i2) if q in tag_at]
        if not mine:
            continue
        if len(mine) != i2 - i1 or len({tag_at[q] for q in mine}) > 1:
            raise RuntimeError("a changed stretch crosses the section's edge or mixes tags")
        for q in range(j1, j2):
            out_p.append(b[q])
            out_t.append(tag_at[mine[0]])
            changed += 1
    return out_p, out_t, changed


def rle(tags):
    out = []
    for t in tags:
        if out and out[-1][0] == t:
            out[-1][1] += 1
        else:
            out.append([t, 1])
    return out


def words_by_tag(paras, tags):
    c = Counter()
    for p, t in zip(paras, tags):
        c[t] += len(p.split())
    return dict(c)


def notbill(t):
    rest = t.split("+", 1)[1] if "+" in t else ""
    return "notbill" + ("+" + rest if rest else "")


def main():
    if any("fix8 (2026-10-05)" in n for e in json.load(open(INDEX, encoding="utf-8")) for n in (e.get("notes") or [])):
        say("fix8 is already in segments_index.json; nothing to do.")
        return
    src = REB.read_text(encoding="utf-8")
    old, new, i, j, old_body, new_body = readers(src)
    idx = json.load(open(INDEX, encoding="utf-8"))
    key = {(e["bill_key"], e["debate_date"]): e for e in idx}
    files = {}

    def load(e):
        k = (e["bill_key"], e["debate_date"])
        if k not in files:
            ps = [p for p in (US / e["file"]).read_text(encoding="utf-8").split("\n\n") if p.strip()]
            tags = [t for t, n in e["para_tags"] for _ in range(n)]
            if len(ps) != len(tags):
                raise RuntimeError(f"{k}: {len(ps)} paragraphs but {len(tags)} tags")
            files[k] = [ps, tags]
        return files[k]

    # US 1: lines lost at page breaks, in every US section
    say("== US 1. lines lost at page markers")
    touched = {}
    for e in idx:
        units = e["para_units"]
        if not any(u.startswith("CREC-") for u, _ in units):
            continue
        ps, tags = load(e)
        i0, np_, nt, nu, ch = 0, [], [], [], 0
        for u, n in units:
            seg, tg = ps[i0:i0 + n], tags[i0:i0 + n]
            i0 += n
            if u.startswith("CREC-"):
                page = US / "v3" / "cache" / "daily" / f"CREC-{u[5:15]}" / f"{u}.txt"
                if not page.exists():
                    raise RuntimeError(f"saved page missing: {page}")
                r = repair_unit(seg, tg, page.read_text(encoding="utf-8", errors="ignore"), old, new)
                if r:
                    seg, tg, c = r
                    ch += c
            np_ += seg
            nt += tg
            nu.append([u, len(seg)])
        if ch:
            files[(e["bill_key"], e["debate_date"])] = [np_, nt]
            e["para_units"] = nu
            touched[(e["bill_key"], e["debate_date"])] = (len(ps), len(np_), ch)
    expect = {("104-HR483", "1995-04-06"), ("104-HR1590", "1995-05-16")}
    for k, (a, b, c) in sorted(touched.items()):
        say(f"   {k[0]} {k[1]}: {a} -> {b} paragraphs, {c} paragraphs put back or corrected")
    if set(touched) != expect:
        raise RuntimeError(f"expected the page-marker repair to touch {sorted(expect)}, it touched {sorted(touched)}")

    # US 2: text that is not about the bill
    say("== US 2. text that is not about the bill, tagged notbill (set aside by text_choices.json)")

    def retag(k, rng, guard):
        e = key[k]
        ps, tags = load(e)
        for gi, gtext in guard:
            if gtext not in ps[gi]:
                raise RuntimeError(f"{k}: paragraph {gi} does not contain {gtext!r}")
        n = 0
        for q in rng:
            if not tags[q].startswith("notbill"):
                tags[q] = notbill(tags[q])
                n += 1
        say(f"   {k[0]} {k[1]}: {n} paragraphs set aside")
        return n

    def unit_range(k, uid):
        i0 = 0
        for u, n in key[k]["para_units"]:
            if u == uid:
                return range(i0, i0 + n)
            i0 += n
        raise RuntimeError(f"{k}: piece {uid} not found")

    k = ("107-HR5716", "2002-11-14")
    nk = len(load(key[k])[0])
    keep = range(120, 142)
    retag(k, [q for q in range(nk) if q not in keep],
          [(122, "H.R. 5716"), (137, "Mr. BOEHNER"), (141, "H.R. 5716"), (142, "Discharged From the Committee"),
           (2, "DISPOSING OF VARIOUS LEGISLATIVE MEASURES")])
    k = ("101-HR3607", "1989-11-21")
    r = unit_range(k, "1989-11-21-block115")
    retag(k, r, [(r[0], "WHEN IT RAINS, IT POURS"), (r[0] + 2, "ANNUNZIO")])
    k = ("103-HR670", "1993-03-25")
    r = unit_range(k, "1993-03-25-block042")
    retag(k, r, [(r[0] + 1, "inquire of the distinguished majority leader the program")])
    k = ("114-HR3762", "2016-02-01")
    retag(k, range(len(load(key[k])[0])), [(1, "IRAN TERROR FINANCE TRANSPARENCY ACT")])
    k = ("113-HR2668", "2013-07-16")
    retag(k, range(len(load(key[k])[0])), [(1, "AUTHORITY FOR MANDATE DELAY ACT")])

    # write the US files and the index
    for (bk, d), (ps, tags) in files.items():
        e = key[(bk, d)]
        if [t for t, n in e["para_tags"] for _ in range(n)] == tags and (bk, d) not in touched:
            continue
        if (bk, d) in touched:
            (US / e["file"]).write_text("\n\n".join(ps) + "\n", encoding="utf-8")
        e["para_tags"] = rle(tags)
        e["tag_words"] = words_by_tag(ps, tags)
        e.setdefault("notes", []).append("fix8 (2026-10-05): see outputs/audit/fix8_corrections.txt")
    tmp = INDEX.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, INDEX)

    # us_rebuild.py reads page-marker lines from now on
    if MARK not in src:
        REB.write_text(src[:i] + new_body + src[j:], encoding="utf-8")
        compile(REB.read_text(encoding="utf-8"), str(REB), "exec")
        say("== us_rebuild.py now keeps the text after a page marker")

    # text choices: notbill is out
    cpy = CHO_PY.read_text(encoding="utf-8")
    if '"notbill"' not in cpy:
        a = cpy.count('"held": "in", "no_debate_days": "in"}')
        if a != 1:
            raise RuntimeError("apply_us_text_choices.py DEFAULTS not in the expected form")
        cpy = cpy.replace('"held": "in", "no_debate_days": "in"}', '"held": "in", "no_debate_days": "in", "notbill": "out"}')
        cpy = cpy.replace("   no_debate_days  bill-days", "   notbill    text read by hand and found not to be about the bill (fix8,\n"
                          "              outputs/audit/fix8_corrections.txt)                default: out\n   no_debate_days  bill-days", 1)
        compile(cpy, str(CHO_PY), "exec")
        CHO_PY.write_text(cpy, encoding="utf-8")
    ch = json.load(open(CHO, encoding="utf-8")) if CHO.exists() else {}
    ch["notbill"] = "out"
    CHO.write_text(json.dumps(ch, indent=1) + "\n", encoding="utf-8")
    say("== text_choices.json: notbill out")

    # Ontario 3: two bill-days of another bill
    exc = json.load(open(EXC, encoding="utf-8")) if EXC.exists() else []
    h = json.load(open("data/canada/ontario/v3/hansard_segments_v3.json", encoding="utf-8"))
    new_exc = [
        ("33-1-Bill52", "1985-12-17", "Bill 86",
         "not a Bill 52 sitting: the Hansard text for this day is the first reading of Bill 86, another bill titled "
         "An Act to amend the Health Protection and Promotion Act (moved by Mr. D. S. Cooke); Bill 52 is not named"),
        ("33-3-Bill79", "1987-06-29", "Bill 106",
         "not a Bill 79 debate: the Hansard text kept for this day is the first reading of Bill 106, another bill titled "
         "An Act to amend the Occupational Health and Safety Act (moved by Hon. Mr. Wrye); Bill 79 is not named"),
    ]
    for bk, d, other, why in new_exc:
        ps = h.get(bk, {}).get(d, [])
        if not ps or not any(other in p.get("text", "") for p in ps) or any(
                re.search(r"\bBill " + bk.split("Bill")[1] + r"\b", p.get("text", "")) for p in ps):
            raise RuntimeError(f"Ontario {bk} {d}: the text is not as read (expected {other}, and no mention of the bill)")
        if not any(r.get("jurisdiction") == "ontario" and r.get("bill_key") == bk and r.get("date") == d for r in exc):
            exc.append({"jurisdiction": "ontario", "bill_key": bk, "date": d, "reason": why,
                        "evidence": f"the OLA Hansard paragraphs saved for this bill-day ({ps[0].get('para_url', ps[0].get('url', ''))})",
                        "verified": "by hand against the official Hansard text saved in data/canada/ontario/v3 (checked 2026-10-05)"})
        say(f"   Ontario {bk} {d}: added to data/v3_exclusions.json ({other})")
    EXC.write_text(json.dumps(exc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(__doc__ + "\n" + "\n".join(LINES) + "\n", encoding="utf-8")
    say(f"== wrote {REPORT}")


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:  # noqa: BLE001
        for rel in ("data/us/v3/segments_index.json", "scripts/step1_debate_text/us_rebuild.py", "scripts/step1_debate_text/apply_us_text_choices.py",
                    "data/us/v3/text_choices.json", "data/v3_exclusions.json",
                    "data/us/v3/cr_segments_v3/104-HR483_1995-04-06.txt", "data/us/v3/cr_segments_v3/104-HR1590_1995-05-16.txt"):
            b = BACK / Path(rel).name
            if b.exists():
                shutil.copy2(b, rel)
            elif rel.endswith("v3_exclusions.json") and (BACK / "no_exclusions_file").exists() and Path(rel).exists():
                os.remove(rel)
        sys.exit(f"fix8 stopped ({ex}); every file was put back as it was. Send this output to Claude.")
