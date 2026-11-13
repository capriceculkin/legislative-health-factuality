"""discourse_window.py   The discourse parse of each answer-key sentence again, this time with the sentence before and the
sentence after it (same bill, same day), so one sentence and a three-sentence window can be compared in both languages.

  cd ~/MiscellaneousProjects/legislative-health-factuality && source venv/bin/activate
  python3 scripts/v6/discourse_window.py

Reads data/dbpedia_pipeline/{us,ontario,quebec}/sentences_v3.json and parity_parses.json (Desktop/next_steps/oct20).
Writes ~/Desktop/next_steps/oct20/discourse_window.json: for each sentence, the window text, where the sentence starts in it, and
the UniRST parse of the window (French twice: ANNODIS labels and RST-DT labels). Nothing else changes. About 10 minutes."""
import json, os, re, sys, time
from pathlib import Path

PROJECT = Path.cwd() if (Path.cwd() / "data").exists() else Path.home() / "MiscellaneousProjects" / "legislative-health-factuality"
sys.path.insert(0, str(PROJECT / "scripts" / "v4"))
import parse_corpus_v5 as V   # noqa: E402   the same discourse parser and settings as the full run

DESK = Path.home() / "Desktop" / "next_steps" / "oct20"
PARSES = next((p for p in (DESK / "parity_parses.json", PROJECT / "data" / "parity_oct19" / "parity_parses.json") if p.exists()), DESK / "parity_parses.json")
OUT = DESK / "discourse_window.json"
JUR = {"US": "us", "ON": "ontario", "QC": "quebec"}


def say(m):
    print(time.strftime("%H:%M:%S"), m, flush=True)


def norm(t):
    return re.sub(r"\s+", " ", (t or "")).strip().lower()


def key_of(sid):
    j, bill, day, p, s = sid.split("|")
    return j, bill, day, int(p[1:]), int(s[1:])


def main():
    rows = [r for r in json.load(open(PARSES, encoding="utf-8"))["rows"] if r.get("sentence_id")]
    say(f"{len(rows)} answer-key sentences with a sentence id")
    need = {key_of(r["sentence_id"])[0] for r in rows}
    groups = {}
    for j in sorted(need):
        p = PROJECT / "data" / "dbpedia_pipeline" / JUR[j] / "sentences_v3.json"
        say(f"reading {p.relative_to(PROJECT)}")
        for x in json.load(open(p, encoding="utf-8")):
            try:
                jj, bill, day, pi, si = key_of(x["sentence_id"])
            except Exception:                                  # noqa: BLE001
                continue
            groups.setdefault((jj, bill, day), []).append((pi, si, x["text"]))
    for g in groups.values():
        g.sort()
    out, missing = [], 0
    for k, r in enumerate(rows, 1):
        j, bill, day, pi, si = key_of(r["sentence_id"])
        g = groups.get((j, bill, day), [])
        idx = next((i for i, (a, b, t) in enumerate(g) if (a, b) == (pi, si) and norm(V.clean(t)) == norm(r["text"])), None)
        if idx is None:                                        # ids moved after a rebuild: find the same text that day
            idx = next((i for i, (a, b, t) in enumerate(g) if norm(V.clean(t)) == norm(r["text"])), None)
        if idx is None:
            missing += 1
            out.append({"n": r["n"], "status": "sentence not found in sentences_v3.json"})
            continue
        prev = V.clean(g[idx - 1][2]) if idx > 0 else ""
        nxt = V.clean(g[idx + 1][2]) if idx + 1 < len(g) else ""
        window = " ".join(x for x in (prev, r["text"], nxt) if x)
        start = len(prev) + 1 if prev else 0
        assert window[start:start + len(r["text"])] == r["text"]
        rec = {"n": r["n"], "lang": r["lang"], "window": window, "start": start, "prev": prev, "next": nxt}
        rec["disc_window"], rec["status"] = V.rst_parse(window, r["lang"])
        if r["lang"] == "fr":
            keep = V.INV["fr"]; V.INV["fr"] = "eng.rst.rstdt"
            try:
                rec["disc_window_rstdt"], rec["status_rstdt"] = V.rst_parse(window, "fr")
            finally:
                V.INV["fr"] = keep
        out.append(rec)
        if k % 10 == 0 or k == len(rows):
            say(f"   {k}/{len(rows)} done")
    json.dump({"made": time.strftime("%Y-%m-%d %H:%M"), "rows": out}, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    say(f"== wrote {OUT} ({len(out) - missing} parsed, {missing} not found). Send it to the chat.")


if __name__ == "__main__":
    main()
