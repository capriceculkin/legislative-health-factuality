#!/usr/bin/env python3
"""
patch_quebec_oldformat4.py   (edits scripts/step1_debate_text/quebec_rebuild.py; keeps a backup)

From Claude's reading of all 422 Quebec 1985-1994 sections against their Journal pages (Oct 5):
  1. The tabling of a committee's report ("Etude detaillee du projet de loi 267", "Auditions et etude detaillee
     du projet de loi 267") is not a debate of the bill: on the 1985-1991 pages such a heading no longer starts
     the bill, as on the pages of 1994 on, where the "Depot de rapports de commissions" section is skipped. Bill
     267's section of 1989-06-21 (212 paragraphs of petitions and oral questions) came from one such heading.
  2. The study of a bill in committee of the whole starts only at a bare "Etude detaillee" or "Commission
     pleniere" heading, not at a tabling heading that merely contains those words.
  3. The Chair announcing the order of business ("on a convenu de continuer les debats en enchainant avec la prise
     en consideration du rapport ... projet de loi 83") is not the call of that bill (Bill 83 of 1990-12-12 had
     taken 31 paragraphs of Bill 107's debate that way).
Pages of 1994 on, and pages that print "Affaires courantes" or "Affaires du jour", are read exactly as before.
Run from the project folder:  python3 scripts/step1_debate_text/patch_quebec_oldformat4.py
"""
import shutil, sys, time
from pathlib import Path
ROOT = Path.cwd() if (Path.cwd() / "data").exists() else Path(__file__).resolve().parents[2]
P = ROOT / "scripts" / "step1_debate_text" / "quebec_rebuild.py"
s = P.read_text(encoding="utf-8")
if "PATCHED_OLDFORMAT4_2026_10_05" in s:
    print("quebec_rebuild.py already has this patch; nothing to do."); sys.exit(0)
if "PATCHED_OLDFORMAT3_2026_10_05" not in s:
    sys.exit("quebec_rebuild.py does not have the fix7e patch (patch_quebec_oldformat3.py); nothing changed. Send this output to Claude.")
AFTER = '''def _old_goes_on(t):'''
DEFS4 = r'''# PATCHED_OLDFORMAT4_2026_10_05: report tablings, study mode, and agenda announcements. See patch_quebec_oldformat4.py.
_OLD_TABLING = re.compile(r"^(?:(?:auditions?|consultations?\s+\w+|etude)\s+(?:et\s+)?(?:etude\s+)?detaillee\s+d|etude\s+d[eu]\b|auditions?\b"
                          r"|consultations?\b|depot\b|rapport\s+(?:de|du|sur)\b|verification\b)")
_OLD_AGENDA = re.compile(r"\b(?:convenu|entente|enchain\w*|par\s+la\s+suite|ensuite|apres\s+quoi|nous\s+(?:allons|passerons)\s+(?:ensuite|alors|par\s+la\s+suite))\b")


# a supply bill is presented, read and adopted in one motion: "propose que l'Assemblee soit saisie du projet de loi 151,
# Loi no 2 sur les credits, qu'elle en adopte le principe et qu'elle adopte le projet de loi"
_OLD_ANCHORS.append(("adoption", re.compile(r"propose\s+que\s+l['’]assemblee\s+soit\s+saisie\s+du\s+projet\s+de\s+loi\s+" + N_NUM)))


# the Chair's call may close a sentence before naming the bill: "L'article 40. Il s'agit de la prise en consideration du
# rapport du projet de loi 413"
_OLD_CALL = re.compile(r"^(?:(?:le|la)\s+(?:vice-)?presidente?[^:]{0,40}:\s*(?:a\s+)?|a\s+)l['’]article\s+\d+\s*,?\s*"
                       r"(?:(?:du|au|de\s+notre|de\s+son)\s+feuilleton)?\.?(?:[^.]|(?<=\bm)\.|(?<=\bmme)\.|(?<=\bmm)\.){0,250}?"
                       r"projet\s+de\s+loi\s+" + N_NUM)      # "M." and "Mme" do not end the sentence


def _old_called(t, num):
    """the paragraph is the Chair calling this bill ("A l'article 38 de notre feuilleton, M. le depute propose l'adoption
    du projet de loi 262"): on an end-of-session day a bill is taken up under "Motions sans preavis" with no new section"""
    m = _OLD_CALL.match(_norm(t)[:400]) if t else None
    return bool(m) and int(m.group("num")) == num


def _old_study_v2(n, current, study_bill):
    if n in ("etude detaillee", "commission pleniere") or (n.startswith("commission pleniere") and "credits" not in n
                                                           and len(n) <= 40):
        return current
    if n.startswith(("mise aux voix du rapport", "rapport de la commission", "adoption", "prise en consideration")):
        return None
    return study_bill


'''
EDITS = [
    (AFTER, DEFS4 + AFTER),
    ("                    study_bill = _old_study(n, current, study_bill)\n",
     "                    study_bill = _old_study_v2(hrun, current, study_bill)\n"),
    ('            if m and len(text) <= 250 and (not section.startswith(_NO_DEBATE_SECTIONS) or (\n'
     '                    strict and nj.startswith("projet de loi") and not section.startswith(_QUESTION_SECTIONS))):\n',
     '            if strict and m and _OLD_TABLING.match(nj):\n'
     '                m = None          # the tabling of a report on the bill, not its debate\n'
     '            if m and len(text) <= 250 and (not section.startswith(_NO_DEBATE_SECTIONS) or (\n'
     '                    strict and nj.startswith("projet de loi") and (not section.startswith(_QUESTION_SECTIONS)\n'
     '                    or any(st in n for st in STAGE_HEADS)))      # a stage named: the question period is over\n'
     '                    or (old_format and nj.startswith("projet de loi") and _old_called(_next_para(pi), int(m.group(1))))):\n'
     '                if old_format and section.startswith(_NO_DEBATE_SECTIONS) and not strict:\n'
     '                    section = "affaires du jour (implied: the Chair calls the bill)"\n'),
    ("            for st, rx in (FR_ANCHORS + _OLD_ANCHORS if strict else FR_ANCHORS):\n                m = rx.search(head) if st in _SWITCH_STAGES else None\n",
     "            for st, rx in (FR_ANCHORS + _OLD_ANCHORS if strict else FR_ANCHORS):\n                m = rx.search(head) if st in _SWITCH_STAGES else None\n"
     "                if m and strict and _OLD_AGENDA.search(head[:m.start()]):\n"
     "                    m = None      # the Chair announces the order of business, not a call\n"),
    ('            m = _OLD_CALL.match(n[:400])\n            if m and int(m.group("num")) != current:\n',
     '            m = _OLD_CALL.match(n[:400])\n            if m and _OLD_AGENDA.search(n[:m.start()]):\n                m = None\n'
     '            if m and int(m.group("num")) != current:\n'),
]
missing = [i for i, (a, _) in enumerate(EDITS, 1) if s.count(a) != 1]
if missing:
    sys.exit(f"quebec_rebuild.py does not contain the expected code for edit(s) {missing}; nothing changed. Send this output to Claude.")
for a, b in EDITS: s = s.replace(a, b)
compile(s, str(P), "exec")
backup = P.with_name("quebec_rebuild_before_oldformat4_" + time.strftime("%Y%m%d-%H%M%S") + ".py")
shutil.copy2(P, backup); P.write_text(s, encoding="utf-8")
sys.path.insert(0, str(P.parent))
try:
    import importlib; Q = importlib.import_module("quebec_rebuild")
    SP = "Merci, M. le President. " * 30; H = "<p align='center'>{}</p>"; T = "<p>{}</p>"
    page = ("<html><body><contenu>"
            + T.format("Dépôt de rapports de commissions. M. le président de la commission.")
            + H.format("Auditions et étude détaillée du projet de loi 267") + T.format("M. Bélanger: J'ai l'honneur de déposer le rapport. " + SP)
            + H.format("Étude détaillée des projets de loi") + H.format("229, 245 et 275") + T.format("M. Filion: Je dépose le rapport. " + SP)
            + H.format("Autre centre hospitalier réclamé") + T.format("M. X: Je dépose l'extrait d'une pétition. " + SP)
            + H.format("Projet de loi 40") + H.format("Commission plénière") + T.format("Le Président: " + SP) + H.format("Étude détaillée")
            + H.format("Définitions") + T.format("M. V: " + SP) + H.format("Mise aux voix du rapport") + T.format("Adopté. " + SP)
            + H.format("Projet de loi 107 Adoption du principe") + T.format("Le Président: À l'article 5 du feuilleton, le ministre propose l'adoption du principe du projet de loi 107. " + SP)
            + T.format("Le Vice-Président: Alors, on a convenu de continuer les débats en enchaînant avec la prise en considération du rapport de la commission sur le projet de loi 83, puis l'adoption du projet de loi 64. " + SP)
            + H.format("Mme Carmen Juneau") + T.format("Mme Juneau: cette motion est spécifique au projet de loi 107. " + SP)
            + H.format("Projet de loi 83") + H.format("Prise en considération du rapport de la commission qui en a fait l'étude détaillée")
            + T.format("Le Vice-Président: À l'article 32, le ministre du Revenu propose de prendre en considération le rapport sur le projet de loi 83. " + SP)
            + "</contenu></body></html>")
    got = {k: len(v) for k, v in Q.parse_page(page, old_format=True)[0].items()}
    want = {40: 3, 107: 3, 83: 1}
    assert got == want, ("old-format page", got, "expected", want)
    with_aff = page.replace("<contenu>", "<contenu>" + H.format("Affaires du jour"))
    assert Q.parse_page(with_aff, old_format=True)[0] == Q.parse_page(with_aff)[0], "a page with Affaires du jour reads as before"
except Exception as e:  # noqa: BLE001
    shutil.copy2(backup, P)
    sys.exit(f"The checks on the edited quebec_rebuild.py failed ({e!r}); quebec_rebuild.py was put back as it was. Send this output to Claude.")
print(f"Patched {P.relative_to(ROOT)} (backup: {backup.name}). Checks passed: a report tabling does not start a bill, "
      "study mode starts only at a bare heading, an agenda announcement is not a call, and a page with Affaires du jour reads as before.")
