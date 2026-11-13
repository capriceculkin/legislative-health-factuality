#!/usr/bin/env python3
"""
patch_quebec_oldformat.py   (edits scripts/step1_debate_text/quebec_rebuild.py; keeps a backup)

Pages of 1985-1987 (33rd legislature) print none of the section headings later pages have ("Affaires
courantes", "Affaires du jour"), so nothing ended a bill's text once it began. Bill 2's section of 1985-12-18 had
1,140 paragraphs: after the vote on its principle and its referral to committee (about 16 paragraphs) it ran on
through a motion on Vieux-Quebec, a motion on the Gulf refinery, the budget statement and the study of
supplementary credits. The same happened to 33-1 Bill 118 (1986-12-12) and 33-1 Bill 31 (1986-06-11), where the
Chair's call of the next bill was worded in the older way ("il s'agit de la motion proposant l'adoption du principe
du projet de loi 67").

Only for bills of the 1985-1994 sessions, and only on a page with neither "Affaires courantes" nor "Affaires du
jour" as a heading:
  - a heading that is not a stage of the bill (adoption, mise aux voix, renvoi, etude detaillee ...), a member's
    or the Chair's name, or part of the bill's study (an act, an article, an amendment) ends the bill's text.
    While the Assembly studies the bill itself in committee of the whole, a heading ends it only when it is
    clearly other business (oral questions, a motion, a statement, a tabling, the budget credits ...).
  - the Chair's call in the older wording ("A l'article 31, au feuilleton, il s'agit de la motion proposant
    l'adoption du principe du projet de loi 67", "il s'agit du debat pour l'adoption du projet de loi 154")
    starts that bill. A member who only mentions such a debate in a speech does not.
Pages of 1994 on are read exactly as before (the new rules are off for them), and so is any page that prints
"Affaires courantes" or "Affaires du jour".

Run from the project folder:  python3 scripts/step1_debate_text/patch_quebec_oldformat.py
If the file does not contain the expected code, nothing is changed.
"""
import shutil
import sys
import time
from pathlib import Path

ROOT = Path.cwd() if (Path.cwd() / "data").exists() else Path(__file__).resolve().parents[2]
P = ROOT / "scripts" / "step1_debate_text" / "quebec_rebuild.py"
s = P.read_text(encoding="utf-8")
if "PATCHED_OLDFORMAT_2026_10_05" in s:
    print("quebec_rebuild.py already has this patch; nothing to do.")
    sys.exit(0)

DEFS = r'''
# PATCHED_OLDFORMAT_2026_10_05: pages of 1985-1987 print no section headings ("Affaires du jour" ...), so on
# them, for bills of the 1985-1994 sessions only, a heading that is not part of the bill's own business ends it,
# and the older wording of the Chair's call starts a bill. See patch_quebec_oldformat.py.
_OLD_STRUCT = re.compile(r"^(?:affaires courantes|affaires du jour)")
_OLD_CONTINUE = ("adoption", "reprise", "prise en consideration", "mise aux voix", "vote", "renvoi", "etude detaillee",
                 "commission pleniere", "remarques preliminaires", "debat", "motion de report", "motion de scission",
                 "motion de renvoi", "motion d'amendement", "motion de sous-amendement", "motion de cloture",
                 "document depose", "documents deposes", "suite", "(suite)", "replique", "loi ", "article",
                 "articles", "dispositions", "amendement", "sous-amendement", "presentation", "titre", "chapitre",
                 "section ", "question de reglement", "questions de reglement", "rappel au reglement",
                 "point de reglement", "decision", "consentement", "intervention", "suspension", "explication",
                 "rapport de la commission pleniere")
_OLD_NAME = re.compile(r"^(?:m|mm|mme|mmes|mlle)\.?\s+[a-z]|^(?:le|la)\s+(?:vice-)?presidente?\b")
# while the bill itself is studied in committee of the whole, only clearly other business ends it
_OLD_OTHER = re.compile(r"^(?:questions?\s+orales?|questions\s+et\s+reponses|motions?\b|enonce|declarations?\b|depot\b"
                        r"|diagramme|leader|lettres?\b|credits|etats\s+financiers|annexe|ajournement|avis\b"
                        r"|renseignements|messages?\b|commission\s+pleniere|affaires|projets?\s+de\s+loi"
                        r"|rapport\s+de\s+la\s+commission\s+(?!pleniere)|nomination|deces|hommage|condoleances)")
_OLD_ANCHORS = [
    ("principe", re.compile(r"propos\w*\s+l['’]adoption\s+du\s+principe\s+du\s+projet\s+de\s+loi\s+" + N_NUM)),
    ("adoption", re.compile(r"(?:propos\w*|debat\s+(?:pour|sur))\s+l['’]adoption\s+du\s+projet\s+de\s+loi\s+" + N_NUM)),
]
_OLD_CALL = re.compile(r"^(?:(?:le|la)\s+(?:vice-)?presidente?[^:]{0,40}:\s*)?a\s+l['’]article\s+\d+\s*,?\s*"
                       r"(?:du|au)\s+feuilleton[^.]{0,250}?projet\s+de\s+loi\s+" + N_NUM)


def _old_continues(n):
    if n.startswith("commission pleniere") and "credits" in n:
        return False          # the study of the budget credits is not a bill's study
    return n.startswith(_OLD_CONTINUE) or n.startswith(tuple(STAGE_HEADS)) or bool(_OLD_NAME.match(n))


def _old_keeps(n, in_study):
    return _old_continues(n) or (in_study and not _OLD_OTHER.match(n))


def _old_study(n, current, study_bill):
    """the bill whose committee-of-the-whole study is under way (None when none is)"""
    if n.startswith(("commission pleniere", "etude detaillee")) and "credits" not in n:
        return current
    if n.startswith(("mise aux voix du rapport", "rapport de la commission", "adoption", "prise en consideration")):
        return None
    return study_bill


def _old_stage(head, num):
    """the stage a Chair's call names ('motion proposant l'adoption du principe' -> principe)"""
    for st, rx in _OLD_ANCHORS + FR_ANCHORS:
        m = rx.search(head) if st != "feuilleton" else None
        if m and int(m.group("num")) == num:
            return st
    return "feuilleton"


def _is_old_session(d):
    try:
        return int(str(d.get("bill_session") or "99-1").split("-")[0]) <= 34
    except ValueError:
        return False
'''

EDITS = [
    ("_SPLIT_NUM = re.compile(", None),      # DEFS go after the line that holds this (handled below)
    ("def parse_page(html):\n", "def parse_page(html, old_format=False):\n"),
    ('    root = soup.find("contenu") or soup.body or soup\n    current, method, stage, section = None, None, None, ""\n',
     '    root = soup.find("contenu") or soup.body or soup\n'
     '    # PATCHED_OLDFORMAT_2026_10_05: the stricter reading is used only for 1985-1994 bills on a page with\n'
     '    # neither "Affaires courantes" nor "Affaires du jour" as a heading\n'
     '    strict = bool(old_format) and not any(\n'
     '        _OLD_STRUCT.match(_norm(q.get_text(" ", strip=True))) for q in root.find_all("p") if _is_heading(q, toc_labels))\n'
     '    study_bill = None\n'
     '    current, method, stage, section = None, None, None, ""\n'),
    ("            elif current is not None:\n                stage = next((s for s in STAGE_HEADS if n.startswith(s)), stage)\n            continue\n",
     "            elif current is not None and strict and not _old_keeps(n, study_bill == current):\n"
     "                current, method, stage = None, None, None    # another item begins (older pages)\n"
     "            elif current is not None:\n                stage = next((s for s in STAGE_HEADS if n.startswith(s)), stage)\n"
     "                if strict:\n"
     "                    study_bill = _old_study(n, current, study_bill)\n"
     "            continue\n"),
    ("            for st, rx in FR_ANCHORS:\n                if quoted",
     "            for st, rx in (FR_ANCHORS + _OLD_ANCHORS if strict and _CHAIR.match(n) else FR_ANCHORS):\n"
     "                if quoted"),
    ("            for st, rx in FR_ANCHORS:\n                m = rx.search(head) if st in _SWITCH_STAGES",
     "            for st, rx in (FR_ANCHORS + _OLD_ANCHORS if strict else FR_ANCHORS):\n"
     "                m = rx.search(head) if st in _SWITCH_STAGES"),
    ('        blocks.append({"text": text, "heading": False, "bill": current, "section": section})\n',
     '        if strict:\n'
     '            m = _OLD_CALL.match(n[:400])\n'
     '            if m and int(m.group("num")) != current:\n'
     '                current, method = int(m.group("num")), "chair_anchor"\n'
     '                stage = _old_stage(n[:400], current)\n'
     '        blocks.append({"text": text, "heading": False, "bill": current, "section": section})\n'),
    ("                cache[p] = parse_page(f.read())\n",
     "                cache[p] = parse_page(f.read(), old_format=_is_old_session(d))\n"),
]
missing = [i for i, (a, _) in enumerate(EDITS, 1) if s.count(a) != 1]
if missing:
    sys.exit(f"quebec_rebuild.py does not contain the expected code for edit(s) {missing}; nothing changed. "
             "Send this output to Claude.")
# definitions after the _SPLIT_NUM line
i = s.index("_SPLIT_NUM = re.compile(")
j = s.index("\n", i) + 1
s = s[:j] + DEFS + s[j:]
for a, b in EDITS:
    if b is not None:
        s = s.replace(a, b)
compile(s, str(P), "exec")
backup = P.with_name("quebec_rebuild_before_oldformat_" + time.strftime("%Y%m%d-%H%M%S") + ".py")
shutil.copy2(P, backup)
P.write_text(s, encoding="utf-8")

# checks on the edited module: an old-format page and a page of today's format
sys.path.insert(0, str(P.parent))
import importlib  # noqa: E402
Q = importlib.import_module("quebec_rebuild")
SP = "Merci, M. le President. " * 30
H = "<p align='center'>{}</p>"
old_page = ("<html><body><contenu>"
            + H.format("Projet de loi 3") + "<p>Le Président: M. le ministre présente le projet de loi concernant les mines. " + SP + "</p>"
            + H.format("M. Raymond Savoie") + "<p>" + SP + "</p>"
            + H.format("QUESTIONS ORALES DES DÉPUTÉS") + "<p>M. X: lors du débat sur l'adoption du projet de loi 2, le ministre a promis. " + SP + "</p>"
            + H.format("Mise aux voix de l'adoption du principe du projet de loi 2") + "<p>Le Président: Que les députés favorables veuillent bien se lever. " + SP + "</p>"
            + H.format("Renvoi à la commission du budget et de l'administration") + "<p>Le Président: Adopté. " + SP + "</p>"
            + H.format("Le Vieux-Québec, valeur culturelle mondiale") + "<p>M. Y: " + SP + "</p>"
            + H.format("Énoncé de politiques budgétaires du gouvernement") + "<p>M. Levesque: " + SP + "</p>"
            + H.format("Projet de loi 31") + H.format("Adoption du principe") + "<p>M. Z: " + SP + "</p>"
            + "<p>Le Président: À l'article 31, au feuilleton, il s'agit de la motion proposant l'adoption du principe du projet de loi 67, Loi concernant la ville. " + SP + "</p>"
            + "<p>M. W: " + SP + "</p>"
            + "<p>À l'article 28 du feuilleton, il s'agit du débat pour l'adoption du projet de loi 154, Loi modifiant la Loi sur la Société. " + SP + "</p>"
            + "<p>M. S: " + SP + "</p>"
            + H.format("Projet de loi 40") + H.format("Commission plénière") + "<p>Le Président: " + SP + "</p>"
            + H.format("Étude détaillée") + H.format("Définitions") + "<p>M. V: " + SP + "</p>"
            + H.format("Entrée en vigueur") + "<p>M. V: " + SP + "</p>"
            + H.format("Mise aux voix du rapport") + "<p>Le Président: Adopté. " + SP + "</p>"
            + H.format("Motion proposant que l'Assemblée appuie la raffinerie") + "<p>Mme H: " + SP + "</p>"
            + H.format("Projet de loi 50") + H.format("Commission plénière") + H.format("Étude détaillée")
            + "<p>M. U: " + SP + "</p>"
            + H.format("Commission plénière Étude des crédits budgétaires supplémentaires") + "<p>M. T: " + SP + "</p>"
            + "</contenu></body></html>")
try:
    segs_new, _ = Q.parse_page(old_page, old_format=True)
    segs_off, _ = Q.parse_page(old_page)
    got = {k: len(v) for k, v in segs_new.items()}
    want = {3: 2, 2: 2, 31: 1, 67: 2, 154: 2, 40: 4, 50: 1}
    assert got == want, ("old-format page", got, "expected", want)
    assert [x["stage"] for x in segs_new[154]] == ["adoption", "adoption"], [x["stage"] for x in segs_new[154]]
    assert len(segs_off.get(2, [])) > 2, "with the new rules off, the page reads as before"
    with_aff = old_page.replace("<contenu>", "<contenu>" + H.format("Affaires du jour"))
    assert ({k: len(v) for k, v in Q.parse_page(with_aff, old_format=True)[0].items()}
            == {k: len(v) for k, v in Q.parse_page(with_aff)[0].items()}), "a page with Affaires du jour reads as before"
except Exception as e:  # noqa: BLE001
    shutil.copy2(backup, P)
    sys.exit(f"The checks on the edited quebec_rebuild.py failed ({e!r}); quebec_rebuild.py was put back as it was. "
             "Send this output to Claude.")
print(f"Patched {P.relative_to(ROOT)} (backup: {backup.name}). Checks passed: on an old-format page Bill 2 keeps "
      f"only its own paragraphs ({len(segs_off.get(2, []))} before, {len(segs_new.get(2, []))} now), a bill studied "
      "in committee of the whole keeps its whole study, and a page with Affaires du jour reads as before.")
