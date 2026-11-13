#!/usr/bin/env python3
"""
patch_sentence_joins.py   (edits scripts/step1_debate_text/build_sentences_v3.py and scripts/step1_debate_text/apply_us_text_choices.py; keeps
backups; needs scripts/step1_debate_text/para_join.py next to them)

build_sentences_v3.py split sentences inside each paragraph. Where the source breaks a sentence across paragraphs
(US inserted statements printed line by line, page markers; Quebec 1985-1994 column and page breaks), the sentence
became two fragments. Now:
  - US and Quebec paragraphs are grouped with para_join.py before the sentence split (Ontario is not touched: its
    paragraphs come whole from the OLA search, and none of its 55,663 paragraph breaks falls inside a sentence)
  - Quebec 1985-1994 text gets the checked OCR word corrections and the line-end hyphen joins
  - US 1985-1993 text: a word split by a hyphen at a column end is joined again (scripts/step1_debate_text/us_words.txt)
  - apply_us_text_choices.py places each US sentence in its paragraph group (same tag), not in a single paragraph
  - audit_review_data.py finds a claim's text in its section also when such a word was joined
The section files themselves are not changed.
"""
import shutil
import sys
import time
from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / "scripts" / "step1_debate_text" / "build_sentences_v3.py").exists():
    ROOT = Path.home() / "MiscellaneousProjects" / "legislative-health-factuality"
V3 = ROOT / "scripts" / "step1_debate_text"
MARK = "PATCHED_SENTENCE_JOINS_2026_10_06"
stamp = time.strftime("%Y%m%d-%H%M%S")
for _f in ("para_join.py", "us_words.txt"):
    if not (V3 / _f).exists():
        sys.exit(f"scripts/step1_debate_text/{_f} is missing; nothing changed.")


def patch(name, pairs):
    p = V3 / name
    s = p.read_text(encoding="utf-8")
    if MARK in s:
        print(f"{name} already patched")
        return
    for old, new in pairs:
        if s.count(old) != 1:
            sys.exit(f"{name} is not in the expected form (looking for {old.strip()[:60]!r}); nothing changed there. "
                     "Send this output to Claude.")
        s = s.replace(old, new)
    compile(s, str(p), "exec")
    shutil.copy2(p, p.with_name(p.stem + f"_before_joins_{stamp}.py"))
    p.write_text(s, encoding="utf-8")
    print(f"patched {name}")


patch("build_sentences_v3.py", [
    ("from v3_common import rp, load_json, save_json, detect_lang\n",
     "from v3_common import rp, load_json, save_json, detect_lang\n"
     f"import para_join as PJ   # {MARK}: sentences broken across paragraphs are joined (see para_join.py)\n"
     "TALLY = {}\n"
     "US_WORDS = PJ.load_us_words(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'us_words.txt'))\n"),
    ('            yield key, sess, day, [p["text"] for p in paras]\n',
     '            yield key, sess, day, list(enumerate(p["text"] for p in paras))\n'),
    ('    for e in idx:\n        with open(os.path.join(base, e["file"]), encoding="utf-8") as f:\n'
     '            paras = [p.strip() for p in f.read().split("\\n\\n") if p.strip()]\n'
     '        day = f"{e[\'date\'][:4]}-{e[\'date\'][4:6]}-{e[\'date\'][6:]}"\n'
     '        yield e["bill_key"], e["bill_session"], day, paras\n',
     '    vocab = PJ.quebec_vocab(base, idx)\n'
     '    fixes = PJ.load_ocr_fixes(os.path.join(base, "v3", "ocr_word_fixes.json"))\n'
     '    for e in idx:\n        with open(os.path.join(base, e["file"]), encoding="utf-8") as f:\n'
     '            text = f.read()\n'
     '        pre = e.get("source") == "bibliotheque_pre1994"\n'
     '        if pre:\n'
     '            text = PJ.fix_quebec_text(text, fixes.get(e["file"]), vocab, TALLY)\n'
     '        paras = [p.strip() for p in text.split("\\n\\n") if p.strip()]\n'
     '        groups = PJ.quebec_groups(paras, vocab if pre else None, TALLY)\n'
     '        TALLY["paragraph_joins"] = TALLY.get("paragraph_joins", 0) + len(paras) - len(groups)\n'
     '        day = f"{e[\'date\'][:4]}-{e[\'date\'][4:6]}-{e[\'date\'][6:]}"\n'
     '        yield e["bill_key"], e["bill_session"], day, groups\n'),
    ('        yield e["bill_key"], e["congress"], e["debate_date"], paras\n',
     '        groups = PJ.us_groups(e, paras, US_WORDS, TALLY)\n'
     '        TALLY["paragraph_joins"] = TALLY.get("paragraph_joins", 0) + len(paras) - len(groups)\n'
     '        yield e["bill_key"], e["congress"], e["debate_date"], groups\n'),
    ("        for pi, para in enumerate(paras):\n", "        for pi, para in paras:\n"),
    ('    print(f"{j}: {len(out):,} sentences, {len({s[\'bill_key\'] for s in out})} bills -> {path}")\n',
     '    print(f"{j}: {len(out):,} sentences, {len({s[\'bill_key\'] for s in out})} bills -> {path}")\n'
     '    print(f"   text repairs: {dict(TALLY)}")\n'
     '    TALLY.clear()\n'),
])

patch("apply_us_text_choices.py", [
    ("from pathlib import Path\n",
     "from pathlib import Path\n"
     "sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n"
     f"import para_join as PJ   # {MARK}: a sentence is placed in its paragraph group\n"),
    ('        tags_of[k] = (paras, [t + ("+no_debate_days" if nd else "") for t in tags])\n',
     '        tags_of[k] = (paras, [t + ("+no_debate_days" if nd else "") for t in tags], PJ.us_groups(e, paras))\n'),
    ("        paras, tags = tags_of[k]\n        sq = [squash(p) for p in paras]\n",
     "        paras, tags, groups = tags_of[k]\n        sq = [squash(p) for p in paras]\n"
     "        for gi, gt in groups:\n            sq[gi] = squash(gt)\n"),
])

patch("audit_review_data.py", [
    ("def file_text(fp):\n",
     f"def _dehyph(s):   # {MARK}: words joined again across a column break (para_join.py)\n"
     "    return re.sub(r\"(?<=[A-Za-z])- (?=[a-z])\", \"\", s)\n\n\ndef file_text(fp):\n"),
    ("            pos = text.find(key) if key else -1\n",
     "            pos = text.find(key) if key else -1\n"
     "            if pos < 0 and key:\n"
     "                pos = _dehyph(text).find(_dehyph(key))\n"),
])
