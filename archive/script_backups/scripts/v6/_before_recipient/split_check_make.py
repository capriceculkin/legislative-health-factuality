"""split_check_make.py   Builds the hand check of sentence breaks (the step 2 gold standard).

Picks real paragraphs from the debate text, in six groups so OCR and born-digital text, and English and French, are
each checked: US before 1994 (OCR) and after, Ontario English and Ontario French, Quebec before 1994 (OCR) and after.
Only paragraphs that still have sentences in sentences_v3.json (after the exclusions) are used, at least 40 words long,
drawn with a fixed seed so the draw can be repeated. Writes split_check.html: the raw paragraphs with NO breaks shown.
The person checking clicks between words where a sentence ends. Our splitter's breaks are stored in the file but stay
hidden until every paragraph is marked, so the check is blind.

    cd ~/MiscellaneousProjects/legislative-health-factuality && source venv/bin/activate
    python3 split_check_make.py [--per 8] [--out ~/Desktop/next_steps/oct21/split_check.html]"""
import argparse, json, os, random, re, sys
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--per", type=int, default=8)
ap.add_argument("--out", default=str(Path.home() / "Desktop" / "next_steps" / "oct21" / "split_check.html"))
a = ap.parse_args()
PROJECT = Path.cwd()
sys.path.insert(0, str(PROJECT / "scripts" / "v3"))
os.chdir(PROJECT)
import build_sentences_v3 as B          # the splitter that made sentences_v3.json, unchanged

def say(m):
    print(m, flush=True)

groups = {}
for j in ("us", "ontario", "quebec"):
    p = PROJECT / "data" / "dbpedia_pipeline" / j / "sentences_v3.json"
    say(f"reading {p.relative_to(PROJECT)}")
    keep = set()
    for s in json.load(open(p, encoding="utf-8")):
        k, day, pi = s["sentence_id"].split("|")[1:4]
        keep.add((k, day, int(pi[1:])))
    say(f"   {len(keep):,} paragraphs with sentences; reading the debate text ({j}) ...")
    src = {"ontario": B.units_ontario, "quebec": B.units_quebec, "us": B.units_us}[j]
    try:
        units = list(src())
    except (SystemExit, Exception) as e:
        say(f"   SKIPPED {j}: {e}"); continue
    for key, sess, day, paras in units:
        for pi, para in paras:
            if (key, day, pi) not in keep or len(para.split()) < 40:
                continue
            plang, _ = B.detect_lang(para, B.DEFAULT_LANG[j])
            if j == "us":
                g = "US House, 1985 to 1993 (scanned, OCR)" if day < "1994" else "US House, 1994 on (born digital)"
            elif j == "ontario":
                g = "Ontario, English" if plang == "en" else "Ontario, French"
            else:
                g = "Quebec, before 1994 (scanned, OCR)" if day < "1994" else "Quebec, 1994 on (born digital)"
            groups.setdefault(g, []).append((key, day, pi, para))
    B.TALLY.clear()

rnd = random.Random(20261021)
items = []
for g in sorted(groups):
    pool = groups[g]
    pick = rnd.sample(pool, min(a.per, len(pool)))
    say(f"   {g}: {len(pool):,} paragraphs, picked {len(pick)}")
    for key, day, pi, para in pick:
        words = para.split()
        pieces = B.split_sentences(para)
        # where our splitter breaks: after which word (pieces are whole runs of words)
        breaks, n = [], 0
        for piece in pieces[:-1]:
            n += len(piece.split()); breaks.append(n - 1)
        dropped = [x for x in pieces if len(x) < 20]
        items.append({"id": f"{key}|{day}|p{pi}", "group": g, "words": words, "ours": breaks, "dropped": dropped})

html = open(Path(__file__).with_name("split_check_template.html"), encoding="utf-8").read()
data = json.dumps({"made": "split_check_make.py, seed 20261021", "items": items}, ensure_ascii=False).replace("</", "<\\/")
out = Path(os.path.expanduser(a.out)); out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(html.replace("__DATA__", data), encoding="utf-8")
say(f"== wrote {out} ({len(items)} paragraphs, {sum(len(i['words']) for i in items):,} words). Open it in your browser.")
