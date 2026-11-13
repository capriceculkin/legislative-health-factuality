#!/usr/bin/env python3
"""
patch_quebec_oldformat2.py   (edits scripts/step1_debate_text/quebec_rebuild.py; keeps a backup)

Follow-up to patch_quebec_oldformat.py (Oct 4). On the 1985-1991 pages a heading is often printed over two or three
lines:
    Prise en consideration du
    rapport de la commission qui
    en a fait l'etude detaillee
The Oct 4 rules read each line alone, so "rapport de la commission qui" (54 times), "de la commission qui en a
fait" (38 times) and similar pieces ended a bill's text in the middle of its own report stage. Now a line that
starts with a small letter right after another heading line is read together with it, and if the whole heading is
part of the bill's business the bill's text goes on.
Also part of a bill's own business on these pages, so they no longer end its text: the tabling of the committee's
report on the bill ("Depot du rapport de la commission qui en a fait l'etude detaillee"), amendments tabled
("Depot d'amendements"), and motions on the bill's debate ("Motion d'ajournement du debat", "Motion proposant de
scinder le projet de loi", "Motion proposant de reporter ...").
Pages of 1994 on, and pages that print "Affaires courantes" or "Affaires du jour", are read exactly as before.

Run from the project folder:  python3 scripts/step1_debate_text/patch_quebec_oldformat2.py
If the file does not contain the expected code, nothing is changed.
"""
import shutil
import sys
import time
from pathlib import Path

ROOT = Path.cwd() if (Path.cwd() / "data").exists() else Path(__file__).resolve().parents[2]
P = ROOT / "scripts" / "step1_debate_text" / "quebec_rebuild.py"
s = P.read_text(encoding="utf-8")
if "PATCHED_OLDFORMAT2_2026_10_05" in s:
    print("quebec_rebuild.py already has this patch; nothing to do.")
    sys.exit(0)
if "PATCHED_OLDFORMAT_2026_10_05" not in s:
    sys.exit("quebec_rebuild.py does not have the Oct 4 patch (patch_quebec_oldformat.py); nothing changed. "
             "Send this output to Claude.")

DEFS_AFTER = '''def _is_old_session(d):
    try:
        return int(str(d.get("bill_session") or "99-1").split("-")[0]) <= 34
    except ValueError:
        return False
'''
DEFS2 = r'''

# PATCHED_OLDFORMAT2_2026_10_05: more of a bill's own business on the older pages
_OLD_CONTINUE2 = re.compile(r"^(?:depot\s+du\s+rapport\s+de\s+la\s+commission|depot\s+d['’](?:un\s+)?amendements?"
                            r"|motion\s+d['’]ajournement\s+du\s+debat|projet\s+de\s+loi\s)")
_OLD_BILL_MOTION = re.compile(r"^motion\s+(?:proposant\s+(?:de\s+|que\s+(?:le\s+)?)?(?:scinder|reporter|renvoyer|"
                              r"projet\s+de\s+loi)|de\s+(?:report|scission|renvoi|cloture))")
_old_continues_v1 = _old_continues


def _old_continues(n):  # noqa: F811
    return _old_continues_v1(n) or bool(_OLD_CONTINUE2.match(n)) or bool(_OLD_BILL_MOTION.match(n))
'''

EDITS = [
    (DEFS_AFTER, DEFS_AFTER + DEFS2),
    ('    study_bill = None\n    current, method, stage, section = None, None, None, ""\n',
     '    study_bill = None\n'
     '    # PATCHED_OLDFORMAT2_2026_10_05: a heading printed over several lines is read as one heading\n'
     '    hrun, hprev, last_heading, cont = "", (None, None, None), False, False\n'
     '    current, method, stage, section = None, None, None, ""\n'),
    ('            blocks.append({"text": text, "heading": True, "bill": current, "section": section})\n',
     '            blocks.append({"text": text, "heading": True, "bill": current, "section": section})\n'
     '            cont = strict and last_heading and text[:1].islower()\n'
     '            if cont:\n'
     '                hrun = hrun + " " + n\n'
     '            else:\n'
     '                hrun, hprev = n, (current, method, stage)\n'
     '            last_heading = True\n'),
    ("            elif current is not None and strict and not _old_keeps(n, study_bill == current):\n"
     "                current, method, stage = None, None, None    # another item begins (older pages)\n",
     "            elif (strict and cont and current is None and hprev[0] is not None and not _TOP_RE.match(hrun)\n"
     "                  and _old_keeps(hrun, study_bill == hprev[0])):\n"
     "                current, method, stage = hprev    # the rest of a heading printed over several lines\n"
     "            elif current is not None and strict and not _old_keeps(hrun, study_bill == current):\n"
     "                current, method, stage = None, None, None    # another item begins (older pages)\n"),
    ("        if current is None and not section.startswith(_NO_DEBATE_SECTIONS):\n            head = n[:400]\n",
     "        last_heading = False\n"
     "        if current is None and not section.startswith(_NO_DEBATE_SECTIONS):\n            head = n[:400]\n"),
]
missing = [i for i, (a, _) in enumerate(EDITS, 1) if s.count(a) != 1]
if missing:
    sys.exit(f"quebec_rebuild.py does not contain the expected code for edit(s) {missing}; nothing changed. "
             "Send this output to Claude.")
for a, b in EDITS:
    s = s.replace(a, b)
compile(s, str(P), "exec")
backup = P.with_name("quebec_rebuild_before_oldformat2_" + time.strftime("%Y%m%d-%H%M%S") + ".py")
shutil.copy2(P, backup)
P.write_text(s, encoding="utf-8")

sys.path.insert(0, str(P.parent))
try:
    import importlib  # noqa: E402
    Q = importlib.import_module("quebec_rebuild")
    SP = "Merci, M. le President. " * 30
    H = "<p align='center'>{}</p>"
    page = ("<html><body><contenu>"
            + H.format("Projet de loi 69") + H.format("Prise en considération du") + H.format("rapport de la commission qui")
            + H.format("en a fait l'étude détaillée") + "<p>Le Président: Nous prenons en considération le rapport. " + SP + "</p>"
            + H.format("M. Pagé") + "<p>" + SP + "</p>"
            + H.format("Dépôt d'amendements") + "<p>" + SP + "</p>"
            + H.format("Motion d'ajournement du débat") + "<p>" + SP + "</p>"
            + H.format("Motion proposant de scinder le projet de loi") + "<p>" + SP + "</p>"
            + H.format("Mise aux voix") + "<p>Le Président: Adopté. " + SP + "</p>"
            + H.format("Le Vieux-Québec, valeur") + H.format("culturelle mondiale et") + "<p>M. Y: " + SP + "</p>"
            + H.format("Projet de loi 245") + H.format("Dépôt du rapport de la commission qui en a fait l'étude détaillée")
            + "<p>M. Lemieux: J'ai l'honneur de déposer le rapport. " + SP + "</p>"
            + H.format("Prise en") + H.format("considération du rapport de la commission") + "<p>M. Z: " + SP + "</p>"
            + H.format("Votes reportés") + H.format("sur la motion") + "<p>M. W: " + SP + "</p>"
            + H.format("Vérification des engagements financiers") + "<p>M. V: " + SP + "</p>"
            + "</contenu></body></html>")
    got = {k: len(v) for k, v in Q.parse_page(page, old_format=True)[0].items()}
    want = {69: 6, 245: 2}
    assert got == want, ("old-format page", got, "expected", want)
    with_aff = page.replace("<contenu>", "<contenu>" + H.format("Affaires du jour"))
    assert Q.parse_page(with_aff, old_format=True)[0] == Q.parse_page(with_aff)[0], "a page with Affaires du jour reads as before"
except Exception as e:  # noqa: BLE001
    shutil.copy2(backup, P)
    sys.exit(f"The checks on the edited quebec_rebuild.py failed ({e!r}); quebec_rebuild.py was put back as it was. "
             "Send this output to Claude.")
print(f"Patched {P.relative_to(ROOT)} (backup: {backup.name}). Checks passed: a heading printed over several lines "
      "is read as one, the tabling of the bill's report, amendments and motions on its debate stay with the bill, and "
      "a page with Affaires du jour reads as before.")
