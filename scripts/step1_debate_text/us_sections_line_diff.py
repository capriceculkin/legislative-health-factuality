#!/usr/bin/env python3
"""
us_sections_line_diff.py   (reads only; changes nothing)

For every US bill-day whose text changed by 300+ words in any tag against an earlier pass (debate, held, rule,
companion, ...), shows the Record paragraphs that the two versions of the section rule read differently: which
measure a line brings up, and which measure the text belongs to, this bill's own paragraphs first. This is the
evidence for any change that was not meant.

Run from the project folder:
   python3 scripts/step1_debate_text/us_sections_line_diff.py data/_before_us_sections3_<stamp>
(the folder holds the earlier pass: segments_index.json, cr_segments_v3/, and scripts/us_sections.py)
Writes outputs/audit/us_sections_line_diff.txt
"""
import importlib.util
import json
import os
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
LINES = []
CHANGE_MIN, SHOW_DAYS, SHOW_PARAS = 300, 40, 14


def say(s=""):
    print(s, flush=True)
    LINES.append(str(s))


def load(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def tag_words(index, folder):
    out = {}
    for e in index:
        try:
            paras = [x.strip() for x in (folder / Path(e["file"]).name).read_text(encoding="utf-8").split("\n\n") if x.strip()]
        except OSError:
            continue
        tg = [t for t, n in e["para_tags"] for _ in range(n)]
        c = Counter()
        for x, t in zip(paras, tg):
            c[t.split("+")[0]] += len(x.split())
        out[(e["bill_key"], e["debate_date"])] = (c, e)
    return out


def short(s, n=170):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 3] + "..."


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: us_sections_line_diff.py data/_before_us_sections3_<stamp>")
    old_dir = ROOT / sys.argv[1] if not Path(sys.argv[1]).is_absolute() else Path(sys.argv[1])
    old_code = old_dir / "scripts" / "us_sections.py"
    if not old_code.exists():
        sys.exit(f"{old_code} not found; nothing to compare.")
    spec = importlib.util.spec_from_file_location("us_sections_earlier", old_code)
    OLD = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(OLD)
    import us_sections as NEW
    os.environ.setdefault("GOVINFO_API_KEY", "cache-only")
    import us_rebuild as U

    old = tag_words(load(old_dir / "segments_index.json", []) or [], old_dir / "cr_segments_v3")
    new = tag_words(load(ROOT / "data" / "us" / "v3" / "segments_index.json", []) or [], ROOT / "data" / "us" / "v3" / "cr_segments_v3")
    emptied_now = {(x["bill_key"], x["debate_date"]): x
                   for x in load(ROOT / "data" / "us" / "v3" / "segments_emptied.json", []) or []}
    picks = []
    for k in set(old) | set(new):
        oc = old.get(k, (Counter(), None))[0]
        nc = new.get(k, (Counter(), None))[0]
        size = max([abs(nc.get(t, 0) - oc.get(t, 0)) for t in set(oc) | set(nc)] or [0])
        if size >= CHANGE_MIN:
            picks.append((size, k, dict(oc), dict(nc)))
    say("=" * 100 + f"\nLINES READ DIFFERENTLY, against {old_dir.name}\n"
        f"bill-days whose text changed by {CHANGE_MIN}+ words in any tag: {len(picks)} (largest {SHOW_DAYS} shown)\n"
        + "=" * 100)
    for size, k, oc, nc in sorted(picks, key=lambda x: -x[0])[:SHOW_DAYS]:
        bk, day = k
        say(f"\n{bk} {day}: before {oc or 'not in the data'}  ->  now {nc or 'not in the data'}")
        try:
            units = U.daily_units(day) if day >= U.DAILY_FROM else U.bound_units(day, set())
        except Exception as ex:                       # noqa: BLE001
            say(f"   could not load the Record for this day ({ex.__class__.__name__}: {ex})")
            continue
        if not units:
            say("   no Record units cached for this day")
            continue
        _, lo, _ = OLD.analyze_day(day, units, U.is_proc_title, frozenset(U.GENERIC_TITLES))
        _, ln, _ = NEW.analyze_day(day, units, U.is_proc_title, frozenset(U.GENERIC_TITLES))
        me = None
        e_any = (new.get(k) or old.get(k) or (None, None))[1]
        if e_any:
            me = NEW.key_of(e_any["type"], e_any["number"])

        def lab(x):
            st = x["state"]
            st = NEW.label(st[1]) if st[0] == "M" else (st[0] or "none")
            line = f"; line {x['formula']} {NEW.label(x['cons'])}" if x["cons"] else ""
            return f"belongs to {st}{line}"
        diffs = []
        for u in sorted(units, key=NEW.unit_order):
            for i, p in enumerate(u["paragraphs"]):
                a, b = lo[u["id"]][i], ln[u["id"]][i]
                if (a["state"], a["cons"], a["formula"]) == (b["state"], b["cons"], b["formula"]):
                    continue
                mine = me is not None and me in (a["cons"], b["cons"]) or ("M", me) in (a["state"], b["state"])
                diffs.append((not mine, len(diffs), u, i, p, a, b))
        n_mine = sum(1 for d in diffs if not d[0])
        for _, _, u, i, p, a, b in sorted(diffs, key=lambda d: (d[0], d[1]))[:SHOW_PARAS]:
            say(f"   [{short(u.get('title', ''), 50)} #{i}] before: {lab(a)} | now: {lab(b)}")
            say(f"        {short(p)}")
        say(f"   paragraphs read differently that day: {len(diffs)}, of which {n_mine} are or were this bill's"
            + (f" (first {SHOW_PARAS} shown, this bill's first)" if len(diffs) > SHOW_PARAS else ""))
        # the per-bill decisions (what was taken out or held, and why), before and now
        for name, src in (("before", old.get(k)), ("now", new.get(k) or ((Counter(), emptied_now[k]) if k in emptied_now else None))):
            e = src[1] if src else None
            if e is None:
                continue
            for r in e.get("removed", [])[:6]:
                say(f"   {name}: taken out {r.get('words', 0):,} w {r.get('kind', '')} {r.get('measure', '')}: "
                    f"{short(r.get('why_removed') or 'two checks agree', 120)}")
            for h in e.get("held", [])[:6]:
                say(f"   {name}: held {h.get('words', 0):,} w {h.get('measure', '')}: {short(h.get('why'), 120)}")
    out = ROOT / "outputs" / "audit" / "us_sections_line_diff.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    say(f"\nwrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
