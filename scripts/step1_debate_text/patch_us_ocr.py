#!/usr/bin/env python3
"""
patch_us_ocr.py   (edits scripts/step1_debate_text/build_sentences_v3.py, apply_us_text_choices.py, audit_review_data.py; keeps
backups; needs fix10 first, and scripts/step1_debate_text/para_join.py and data/us/v3/ocr_word_fixes.json from this bundle)

The 1985-1993 US pages were read by two OCR engines, but what neither engine settled was left as the scanner read
it. Those leftovers are corrected now, from data/us/v3/ocr_word_fixes.json (each by position, and only if the old
text is still there; never across a paragraph break):
  brackets the scanner misread   "<IL>" -> "(IL)", "CMr. WAXMAN]" -> "[Mr. WAXMAN]", "subsection fb)" -> "(b)",
                                 "(BJ" -> "(B)", "SmithCNJ>" -> "Smith(NJ)"
  words split or run together    "Govern ment" -> "Government", "twothirds" -> "two thirds"
  stray marks and misread letters "th.e" -> "the", "cllnical" -> "clinical", "wlll" -> "will"
The section files are not changed: the sentence builder, the text-choice step and the audit all read the text with
the same corrections, so a claim is still found in its section.
"""
import shutil
import sys
import time
from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / "scripts" / "step1_debate_text" / "build_sentences_v3.py").exists():
    ROOT = Path.home() / "MiscellaneousProjects" / "legislative-health-factuality"
V3 = ROOT / "scripts" / "step1_debate_text"
MARK = "PATCHED_US_OCR_2026_10_06"
stamp = time.strftime("%Y%m%d-%H%M%S")
if "PATCHED_SENTENCE_JOINS_2026_10_06" not in (V3 / "build_sentences_v3.py").read_text(encoding="utf-8"):
    sys.exit("fix10 has not been applied yet (build_sentences_v3.py has no sentence joins). Run fix10 first; "
             "nothing changed.")
for f in (V3 / "para_join.py", ROOT / "data" / "us" / "v3" / "ocr_word_fixes.json"):
    if not f.exists():
        sys.exit(f"{f} is missing; nothing changed.")


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
    shutil.copy2(p, p.with_name(p.stem + f"_before_usocr_{stamp}.py"))
    p.write_text(s, encoding="utf-8")
    print(f"patched {name}")


patch("build_sentences_v3.py", [
    ('        with open(os.path.join(base, e["file"]), encoding="utf-8") as f:\n'
     '            paras = [p.strip() for p in f.read().split("\\n\\n") if p.strip()]\n'
     '        groups = PJ.us_groups(e, paras, US_WORDS, TALLY)\n',
     '        with open(os.path.join(base, e["file"]), encoding="utf-8") as f:\n'
     f'            text = f.read()   # {MARK}: the 1985-1993 scanner leftovers corrected\n'
     '        text = PJ.apply_fixes(text, PJ.fixes_for(os.path.join(base, "v3", "ocr_word_fixes.json"), e["file"]),\n'
     '                              TALLY, "us_ocr_fixed")\n'
     '        paras = [p.strip() for p in text.split("\\n\\n") if p.strip()]\n'
     '        groups = PJ.us_groups(e, paras, US_WORDS, TALLY)\n'),
])

patch("apply_us_text_choices.py", [
    ('            paras = [p.strip() for p in (US / e["file"]).read_text(encoding="utf-8").split("\\n\\n") if p.strip()]\n',
     f'            text = PJ.apply_fixes((US / e["file"]).read_text(encoding="utf-8"),   # {MARK}\n'
     '                                  PJ.fixes_for(US / "v3" / "ocr_word_fixes.json", e["file"]), {})\n'
     '            paras = [p.strip() for p in text.split("\\n\\n") if p.strip()]\n'),
])

patch("audit_review_data.py", [
    ('def file_text(fp):\n    try:\n        return norm_ws(Path(fp).read_text(encoding="utf-8", errors="ignore"))\n',
     f'def _us_fixed(fp, text):   # {MARK}: the same corrections the sentences were built from\n'
     '    try:\n'
     '        sys.path.insert(0, str(ROOT / "scripts" / "step1_debate_text"))\n'
     '        import para_join as PJ\n'
     '        try:\n'
     '            rel = Path(fp).relative_to(ROOT / "data" / "us").as_posix()\n'
     '        except ValueError:\n'
     '            rel = Path(fp).resolve().relative_to((ROOT / "data" / "us").resolve()).as_posix()\n'
     '        return PJ.apply_fixes(text, PJ.fixes_for(ROOT / "data" / "us" / "v3" / "ocr_word_fixes.json", rel), {})\n'
     '    except (ValueError, ImportError, OSError):\n'
     '        return text\n\n\n'
     'def file_text(fp):\n    try:\n'
     '        return norm_ws(_us_fixed(fp, Path(fp).read_text(encoding="utf-8", errors="ignore")))\n'),
])
