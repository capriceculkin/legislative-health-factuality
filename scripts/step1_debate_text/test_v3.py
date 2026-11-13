#!/usr/bin/env python3
"""
test_v3.py   (offline; uses temporary folders; touches none of your data)

Tests every rule in the v3 rebuild on inputs modeled on the cases raised at the
Sept 24 meeting: Bill 94 in 33-1, the Business of the House mention of Bill 54,
the Third Readings list, the Quebec Bill 28 "plus tot aujourd'hui" start, Bill 116
on 1995-12-04, the Dec 8 / Dec 9 2006 legislative day, and three-column PDF pages.

    python3 scripts/step1_debate_text/test_v3.py
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import v3_common as C  # noqa: E402

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not cond else ""))


# --------------------------------------------------------------------------- language

def test_language():
    print("\nLanguage detection (function-word method; lingua adds the second method when installed)")
    cases = [("Tout \u00e0 l'heure je vous ai parl\u00e9 de la r\u00e9forme des soins de sant\u00e9 dans le Nord.", "fr"),
             ("Cette situation juridique a amen\u00e9 plusieurs personnes \u00e0 soulever un doute.", "fr"),
             ("The House, by a vote of 395 to 27, again gave its approval to the conference report.", "en"),
             ("Northern Ontario suffered at the hands of the previous government for many years.", "en"),
             ("Mr. Speaker, the member for Nickel Belt is right about the hospital in Sudbury.", "en")]
    for text, want in cases:
        got, _ = C.lang_heuristic(text)
        check(f"'{text[:40]}...' -> {want}", got == want, f"got {got}")
    check("English contraction don't is not counted as French",
          C.lang_heuristic("I don't think it's right that we can't fund it")[0] == "en")


# --------------------------------------------------------------------------- Ontario anchors + assignment

def test_ontario_anchors():
    print("\nOntario anchors")
    a = C.find_anchors_en("Hon. Mr. Elston moved second reading of Bill 94, An Act regulating the Amounts that "
                          "Persons may charge for rendering Services that are Insured Services under the Health "
                          "Insurance Act.", "Procedure", "HEALTH CARE ACCESSIBILITY ACT")
    check("moved second reading of Bill 94 is a strong anchor", a and a[0]["bill_number"] == 94 and a[0]["strong"])
    check("long title captured", a and a[0]["long_title"].startswith("An Act regulating the Amounts"))
    a = C.find_anchors_en("Resuming the adjourned debate on the motion for second reading of Bill 94, An Act "
                          "regulating the Amounts ...", "", "HEALTH CARE ACCESSIBILITY ACT (CONTINUED)")
    check("Resuming the adjourned debate ... Bill 94 is strong", a and a[0]["strong"] and a[0]["stage"] == "second_resumed")
    a = C.find_anchors_en("Resuming the debate adjourned on March 2, 2020, on the motion for second reading of "
                          "the following bill: Bill 175, An Act to amend various Acts", "", "Connecting People")
    check("modern 'following bill: Bill 175' phrasing is strong", a and a[0]["bill_number"] == 175 and a[0]["strong"])
    a = C.find_anchors_en("I would like to indicate the business of the House for next week. On Monday we will "
                          "deal with Bill 54 and then Bill 94.", "Hon. Mr. Nixon", "BUSINESS OF THE HOUSE")
    check("Business of the House mention of Bill 54 is NOT an anchor", not a)
    a = C.find_anchors_en("The minister moved second reading of Bill 94 last week and has not answered.",
                          "Mr. Grossman", "EXTRA BILLING", "Oral Questions")
    check("question period sentence about Bill 94 is at most a weak anchor", all(not x["strong"] for x in a))
    a = C.find_anchors_en("Bill 89, An Act to amend the Executive Council Act.", "", "THIRD READINGS")
    check("Third Readings list item is a strong anchor for Bill 89", a and a[0]["bill_number"] == 89 and a[0]["strong"])
    a = C.find_anchors_en("Bill 94, An Act regulating the Amounts ...", "", "ROYAL ASSENT")
    check("Royal Assent list items are never anchors", not a)
    check("session from URL: parliament-33/session-1 -> 33-1",
          C.url_session("https://www.ola.org/en/legislative-business/house-documents/parliament-33/session-1/"
                        "1986-01-14/hansard") == "33-1")
    check("topic normalization drops (CONTINUED) and French half",
          C.norm_topic("HEALTH CARE ACCESSIBILITY ACT (CONTINUED)") == "HEALTH CARE ACCESSIBILITY ACT"
          and C.norm_topic("Connecting People to Home and Community Care Act, 2020 / Loi de 2020") ==
          "CONNECTING PEOPLE TO HOME AND COMMUNITY CARE ACT 2020")


def test_ontario_assign():
    print("\nOntario assignment end to end (temporary folder)")
    import ontario_rebuild as O
    tmp = tempfile.mkdtemp()
    try:
        O.OUT, O.MASTER, O.ANCHORS = tmp, os.path.join(tmp, "m.json"), os.path.join(tmp, "a.json")
        O.RAW_DIR, O.SEGMENTS, O.TEXT_DIR = os.path.join(tmp, "raw"), os.path.join(tmp, "s.json"), os.path.join(tmp, "t")
        u1 = "https://www.ola.org/en/legislative-business/house-documents/parliament-33/session-1/{d}/hansard"
        u2 = "https://www.ola.org/en/legislative-business/house-documents/parliament-33/session-2/{d}/hansard"

        def row(d, topic, text, n, url=u1, spk="", tob=""):
            return {"date": d, "topic": topic, "paragraph": text, "url": url.format(d=d), "speaker": spk,
                    "paraUrl": f"{url.format(d=d)}#P{n}", "typeOfBusiness": tob, "session": ""}
        rows = [
            row("1986-01-14", "HEALTH CARE ACCESSIBILITY ACT",
                "Hon. Mr. Elston moved second reading of Bill 94, An Act regulating the Amounts ...", 1, spk="Procedure"),
            row("1986-01-14", "HEALTH CARE ACCESSIBILITY ACT", "Extra billing touches universality of medicare.", 2),
            row("1986-01-20", "HEALTH CARE ACCESSIBILITY ACT (CONTINUED)",
                "Resuming the adjourned debate on the motion for second reading of Bill 94, An Act ...", 1),
            row("1986-01-21", "HEALTH CARE ACCESSIBILITY ACT (CONTINUED)", "The debate continues with no anchor.", 1),
            row("1985-12-19", "BUSINESS OF THE HOUSE", "Next week we will consider Bill 94 and Bill 54.", 1),
            row("1986-02-10", "THIRD READINGS", "Bill 89, An Act to amend the Executive Council Act.", 1),
            row("1986-02-10", "THIRD READINGS", "Bill 94, An Act regulating the Amounts ...", 2),
            row("1986-02-10", "THIRD READINGS", "Motion agreed to.", 3),
            row("1986-01-15", "EXTRA BILLING", "Will the minister withdraw Bill 94?", 1, tob="Oral Questions"),
            row("1986-05-06", "HEALTH CARE ACCESSIBILITY ACT", "Paragraph from session 33-2.", 1, url=u2),
        ]
        anchors = []
        for r in rows:
            for a in C.find_anchors_en(r["paragraph"], r["speaker"], r["topic"], r["typeOfBusiness"]):
                anchors.append({"row_id": r["paraUrl"], "session": C.url_session(r["url"]), "bill_number": a["bill_number"],
                                "stage": a["stage"], "strong": a["strong"], "date": r["date"], "topic": r["topic"],
                                "topic_norm": C.norm_topic(r["topic"]), "long_title": a["long_title"]})
        C.save_json(anchors, O.ANCHORS)
        C.save_json({"33-1-Bill94": {"bill_key": "33-1-Bill94", "session": "33-1", "bill_number": 94, "health": True,
                                     "anchor_dates": ["1986-01-14", "1986-01-20", "1986-02-10"],
                                     "topics": ["HEALTH CARE ACCESSIBILITY ACT"], "old_index_keys": [],
                                     "long_title": "An Act regulating", "health_basis": "lexicon"}}, O.MASTER)
        C.save_json(rows, os.path.join(O.RAW_DIR, "33-1-Bill94.json"))
        O.cmd_assign()
        seg = C.load_json(O.SEGMENTS)["33-1-Bill94"]
        check("assigned dates are 1986-01-14, 01-20, 01-21, 02-10",
              sorted(seg) == ["1986-01-14", "1986-01-20", "1986-01-21", "1986-02-10"], str(sorted(seg)))
        check("continuation day with no anchor assigned through the heading hash",
              seg.get("1986-01-21", [{}])[0].get("assignment_method") == "topic_hash_exact")
        check("Business of the House (1985-12-19) not assigned", "1985-12-19" not in seg)
        check("question period (1986-01-15) not assigned", "1986-01-15" not in seg)
        tr = [p["text"][:8] for p in seg.get("1986-02-10", [])]
        check("Third Readings: Bill 89 line excluded, Bill 94 line and what follows kept",
              tr == ["Bill 94,", "Motion a"], str(tr))
        check("paragraph whose URL says 33-2 dropped from 33-1-Bill94", "1986-05-06" not in seg)
    finally:
        shutil.rmtree(tmp)


# --------------------------------------------------------------------------- Quebec

# Both fixtures copy the real assnat structure seen in Caprice's diagnostics, INCLUDING the
# <form> wrapper around the table of contents and the debate text. The earlier fixtures had
# no <form>, which is why they passed while every real page returned zero bills.
QC_OLD = """<html><body><form><div><div>
<p><tabledesmatieres><h4><a href="#951204001"> Affaires courantes</a></h4><ul>
<h4><a href="#951204002">Pr\u00e9sentation de projets de loi</a></h4><ul>
<li><a href="#951204003">Projet de loi 117  Loi modifiant la Loi sur le r\u00e9gime des eaux</a></li>
<li><a href="#951204009">Projet de loi 116  Loi modifiant de nouveau la Loi sur les services de sant\u00e9</a></li>
<ul><li><a href="#951204010">M. Jean Rochon</a></li></ul></ul>
<h4><a href="#951204022">Questions et r\u00e9ponses orales</a></h4>
<h4><a href="#951204036">Affaires du jour</a></h4><ul>
<li><a href="#951204041">Projet de loi 102</a></li></ul></ul></tabledesmatieres></p>
<contenu><br/><a name="Page05351"></a>(Quatorze heures sept minutes)<p></p>
<p><b>Le Pr\u00e9sident: </b> \u00c0 l'ordre, s'il vous pla\u00eet!</p>
<p><br/><center><p><a name="951204001"><b> Affaires courantes </b></a></p></center></p>
<p> Nous allons proc\u00e9der aux affaires courantes.</p>
<p><br/><center><p><a name="951204002"><b> Pr\u00e9sentation de projets de loi </b></a></p></center></p>
<p><br/><center><p><a name="951204003"><b> Projet de loi 117 </b></a></p></center></p>
<p><b>M. Gendron: </b> C'est un projet de loi sur le r\u00e9gime des eaux.</p>
<p><br/><center><p><a name="951204009"><b> Projet de loi 116 </b></a></p></center></p>
<p><b>Le Pr\u00e9sident: </b> \u00c0 l'article c du feuilleton, M. le ministre de la Sant\u00e9.</p>
<p><br/><center><p><a name="951204010"><b> M. Jean Rochon </b></a></p></center></p>
<p><b>M. Rochon: </b> M. le Pr\u00e9sident, ce projet de loi modifie diverses dispositions.</p>
<p><a name="Page05353"></a>Il propose d'abord un nouveau mode de formation du conseil.</p>
<p><br/><center><p><a name="951204022"><b> Questions et r\u00e9ponses orales </b></a></p></center></p>
<p><b>M. Johnson: </b> Pourquoi fermer des h\u00f4pitaux alors que le projet de loi n\u00b0 116 ne r\u00e8gle rien?</p>
<p><br/><center><p><a name="951204036"><b> Affaires du jour </b></a></p></center></p>
<p><br/><center><p><a name="951204041"><b> Projet de loi 102 </b></a></p></center></p>
<p><b>M. Dupont: </b> Nous reprenons le d\u00e9bat, ajourn\u00e9 plus t\u00f4t aujourd'hui, sur le projet de loi n\u00b0 102.</p>
<p>Comme on l'a vu avec le projet de loi n\u00b0 83, le gouvernement agit sans consulter.</p>
<p>Mr. Speaker, the Minister has not explained this bill.</p>
</contenu></div></div></form></body></html>"""

QC_NEW = """<html><body><form><div>
<p><tabledesmatieres>
<p><a href="#_Toc01"><b><span>Affaires courantes</span></b></a></p>
<p><a href="#_Toc02"><span>D\u00e9p\u00f4t de rapports de commissions</span></a></p>
<p><a href="#_Toc03"><span>\u00c9tude d\u00e9taill\u00e9e du projet de loi n\u00b0 94</span></a></p>
<p><a href="#_Toc04"><span>Questions et r\u00e9ponses orales</span></a></p>
<p><a href="#_Toc05"><span>Projet de loi visant principalement \u00e0 instaurer la responsabilit\u00e9</span></a></p>
<p><a href="#_Toc06"><span>Affaires du jour</span></a></p>
<p><a href="#_Toc07"><span>Projet de loi n\u00b0 2</span></a></p>
<p><a href="#_Toc08"><span>Pr\u00e9sentation</span></a></p>
<p><a href="#_Toc09"><span>M. Christian Dub\u00e9</span></a></p>
<p><a href="#_Toc10"><span>Adoption du principe</span></a></p>
<p><a href="#_Toc11"><span>Ajournement</span></a></p>
</tabledesmatieres></p>
<contenu><p style="text-align: justify"><a name="Page00503"></a><i>(Huit heures cinq minutes)</i></p>
<p style="font-weight:bold;text-align: center;"><a name="_Toc99a"></a><a name="_Toc01">Affaires courantes</a></p>
<p style="text-align: justify"><a name="_Toc02"></a>D\u00e9p\u00f4t de rapports de commissions</p>
<p style="text-align: justify"><a name="_Toc03"></a>\u00c9tude d\u00e9taill\u00e9e du projet de loi n\u00b0 94</p>
<p style="text-align: justify"><b>M. Tanguay : </b>Je d\u00e9pose le rapport de la Commission sur le projet de loi n\u00b0 94.</p>
<p style="font-weight:bold;text-align: center;"><a name="_Toc04"></a>Questions et r\u00e9ponses orales</p>
<p style="text-align: justify"><a name="_Toc05"></a>Projet de loi visant principalement \u00e0 instaurer la responsabilit\u00e9</p>
<p style="text-align: justify"><b>Mme Rizqy : </b>Le projet de loi n\u00b0 2 est une loi sp\u00e9ciale contre les m\u00e9decins.</p>
<p style="font-weight:bold;text-align: center;"><a name="_Toc06"></a>Affaires du jour</p>
<p style="text-align: justify"><a name="_Toc07a"></a><a name="_Toc07"></a>Projet de loi n\u00b0 2</p>
<p style="text-align: justify"><a name="_Toc08"></a>Pr\u00e9sentation</p>
<p style="text-align: justify"><a name="_Toc09"></a>M. Christian Dub\u00e9</p>
<p style="text-align: justify"><b>M. Dub\u00e9 : </b>Mme la Pr\u00e9sidente, je pr\u00e9sente le projet de loi n\u00b0 2.</p>
<p style="text-align: justify"><a name="_Toc10"></a>Adoption du principe</p>
<p style="text-align: justify"><b>M. Tanguay : </b>Nous nous opposons \u00e0 ce projet de loi.</p>
<p style="font-weight:bold;text-align: center;"><a name="_Toc11"></a>Ajournement</p>
<p style="text-align: justify">L'Assembl\u00e9e ajourne ses travaux.</p>
</contenu></div></form></body></html>"""


def test_quebec():
    print("\nQuebec parser on replicas of the real page structures (including the <form> wrapper)")
    import quebec_rebuild as Q
    if Q.BeautifulSoup is None:
        check("beautifulsoup4 installed", False)
        return
    segs, _ = Q.parse_page(QC_OLD)
    t = lambda b: [x["text"] for x in segs.get(b, [])]
    check("OLD format: Bill 116 found although the page sits inside <form>", len(t(116)) == 3, str(t(116)))
    check("OLD format: paragraph carrying a Page anchor is kept as debate text",
          any(x.startswith("Il propose d'abord") for x in t(116)))
    check("OLD format: speaker label 'M. Jean Rochon' is not stored as debate text",
          not any(x.strip() == "M. Jean Rochon" for x in t(116)))
    check("OLD format: question period mention of Bill 116 is excluded",
          not any("fermer des h\u00f4pitaux" in x for x in t(116)))
    check("OLD format: Bill 117 does not absorb Bill 116", not any("sant\u00e9" in x.lower() for x in t(117)))
    check("OLD format: Bill 102 kept, starts at a full paragraph, mid-speech Bill 83 ignored",
          t(102) and t(102)[0].startswith("M. Dupont") and 83 not in segs and len(t(102)) == 3, str(t(102)))
    segs, _ = Q.parse_page(QC_NEW)
    t = lambda b: [x["text"] for x in segs.get(b, [])]
    check("NEW format: Bill 2 found under Affaires du jour", len(t(2)) == 2, str(t(2)))
    check("NEW format: question period speech about Bill 2 is excluded",
          not any("loi sp\u00e9ciale" in x for x in t(2)))
    check("NEW format: committee report tabling does not create a Bill 94 debate", 94 not in segs, str(segs.keys()))
    check("NEW format: Ajournement ends the segment", not any("ajourne ses travaux" in x for x in t(2)))
    bad = QC_OLD.replace("<form>", "").replace("</form>", "")
    check("parser gives the same answer with or without the <form> wrapper",
          {k: len(v) for k, v in Q.parse_page(bad)[0].items()} == {k: len(v) for k, v in Q.parse_page(QC_OLD)[0].items()})
    check("Bill 116 regex matches 'projet de loi n\u00b0 116' and not 11",
          C.fr_bill_re(116).search("le projet de loi n\u00b0 116, Loi") and not C.fr_bill_re(11).search("n\u00b0 116"))


# --------------------------------------------------------------------------- US

def make_three_column_pdf(path):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(path, pagesize=letter)
    W, H = letter
    c.setFont("Helvetica", 7)
    c.drawString(40, H - 25, "December 8, 2006 CONGRESSIONAL RECORD - HOUSE H9012")
    cols = [40, 40 + 180, 40 + 360]
    for k, x in enumerate(cols):
        y = H - 60
        for i in range(60):
            c.drawString(x, y, f"col{k + 1}line{i:02d} alpha beta gamma delta eps")
            y -= 10
    c.save()


def test_us():
    print("\nUS column parser, repair, regexes, selection")
    import us_rebuild as U
    if U.pdfplumber is None:
        check("pdfplumber installed", False)
    else:
        tmp = tempfile.mkdtemp()
        try:
            p = os.path.join(tmp, "three.pdf")
            make_three_column_pdf(p)
            import pdfplumber
            with pdfplumber.open(p) as pdf:
                naive = pdf.pages[0].extract_text().splitlines()
            glued = sum(1 for ln in naive if "col1" in ln and "col2" in ln)
            check("naive extraction glues columns (reproduces the bug)", glued > 30, f"{glued} glued lines")
            pages = U.extract_pdf_columns(p)
            lines = pages[0]["lines"]
            order = [ln.split()[0] for ln in lines if ln.startswith("col")]
            expected = [f"col{k}line{i:02d}" for k in (1, 2, 3) for i in range(60)]
            check("gutter extraction reads column 1, then 2, then 3, top to bottom", order == expected,
                  f"first mismatch at {next((i for i, (a, b) in enumerate(zip(order, expected)) if a != b), None)}")
            check("no line mixes two columns", not any(ln.count("col") > 1 for ln in lines))
            check("page header kept separately with its date", C.first_long_date(pages[0]["header"]) == "2006-12-08")
        finally:
            shutil.rmtree(tmp)
    U._DICT = {"blessing", "especially", "examined", "engineers", "million", "bless", "held", "those", "the", "is",
               "in", "form", "inform", "therapist", "the", "rapist", "speaker", "speak"}
    fixed = U.dehyphenate(["giving of Your bless", "ing upon all who have any need, espe", "cially those held",
                           "The Chair has ex", "amined the Journal", "donated to $20 mil-", "lion for", "put it in",
                           "form today", "the", "rapist said"])
    joined = " ".join(fixed)
    check("OCR breaks repaired: blessing, especially, examined, million",
          all(w in joined for w in ("blessing", "especially", "examined", "$20 million")), joined)
    check("two real words are never merged (in / form, the / rapist)",
          "inform" not in joined and "therapist" not in joined, joined)
    rx = C.us_bill_mention_re("hr", 2068)
    check("OCR '<H.R. 2068' and '(H.R. 2068)' match", rx.search("the bill <H.R. 2068") and rx.search("(H.R.2068)"))
    check("H.R. 20680 does not match H.R. 2068", not rx.search("H.R. 20680"))
    check("'U.S. 35' is not Senate bill S. 35", not C.us_bill_mention_re("s", 35).search("under 42 U.S. 35 and"))
    check("parse_us_bill variants", C.parse_us_bill("H.R. 6164") == ("hr", 6164) and C.parse_us_bill("hr6164") ==
          ("hr", 6164) and C.parse_us_bill("S. 3546") == ("s", 3546) and C.parse_us_bill("H.Res. 12") == ("hres", 12))
    head = U.caps_blocks(U.dehyphenate(["some text", "CERTAIN FORMER FLIGHT EN", "GINEERS OF WESTERN",
                                        "Mr. SENSENBRENNER. Mr. Speaker, I ask", "unanimous consent"]))
    check("multi-line ALL CAPS heading joined and repaired", head[-1][0] == "CERTAIN FORMER FLIGHT ENGINEERS OF WESTERN",
          head[-1][0])

    b = {"type": "hr", "number": 6111}
    units = {
        "2006-12-09": [],
        "2006-12-08": [
            {"id": "g1", "day": "2006-12-08", "title": "PRAYER", "text": "The Chaplain offered the following prayer"},
            {"id": "g2", "day": "2006-12-08", "title": "GENERAL LEAVE", "text": "on H.R. 6111 and H.R. 6111"},
            {"id": "g3", "day": "2006-12-08", "title": "PROVIDING FOR CONSIDERATION OF H.R. 6111",
             "text": "H. Res. 1099 providing for consideration of H.R. 6111 H.R. 6111"},
            {"id": "g4", "day": "2006-12-08", "title": "TAX RELIEF AND HEALTH CARE ACT OF 2006",
             "text": "Mr. THOMAS. Mr. Speaker, I move to suspend the rules and pass the bill (H.R. 6111)"},
            {"id": "g5", "day": "2006-12-08", "title": "TAX RELIEF AND HEALTH CARE ACT OF 2006--Continued",
             "text": "Mr. RANGEL. Mr. Speaker, the physicians payment fix matters."},
            {"id": "g6", "day": "2006-12-08", "title": "HONORING A HOMETOWN HERO", "text": "Mr. Speaker, I rise"}],
    }
    chosen, excluded = U.select_units(units, b)
    got = sorted((u["id"], m) for u, m in chosen)
    check("vote stamped 2006-12-09 finds the Dec 8 legislative day debate",
          got == [("g4", "bill_number"), ("g5", "title_hash")], str(got))
    check("GENERAL LEAVE and the rule debate excluded", {e["id"] for e in excluded} == {"g2", "g3"}, str(excluded))


# --------------------------------------------------------------------------- sentences and scores

def test_sentences_scores():
    print("\nSentence splitting and score keys")
    import build_sentences_v3 as S
    s = S.split_sentences("Hon. Mr. Elston moved second reading of Bill 94. The bill (H.R. 6164) passed. "
                          "M. le Pr\u00e9sident, je vous remercie. It is done.")
    check("no split inside Hon. Mr., H.R., M.", len(s) == 4, str(s))
    import compute_scores_v3 as K
    check("bill key recovered from sentence_id", K.bill_of({"sentence_id": "ON|33-1-Bill94|1986-01-14|p3|s2"}) ==
          "33-1-Bill94")
    check("bill key taken from triple field when present", K.bill_of({"bill_key": "QC-x", "sentence_id": "a"}) == "QC-x")
    check("health lexicon flags Health Care Accessibility, not Municipal Act",
          C.health_hits("Health Care Accessibility Act") and not C.health_hits(
              "An Act to amend certain Statutes of Ontario Consequent upon Enactment of the Municipal Act"))
    check("'soins' does not match inside 'besoins'", not C.health_hits("les besoins des municipalit\u00e9s"))


if __name__ == "__main__":
    test_language()
    test_ontario_anchors()
    test_ontario_assign()
    test_quebec()
    test_us()
    test_sentences_scores()
    n_fail = sum(1 for _, ok in RESULTS if not ok)
    print(f"\n{len(RESULTS) - n_fail} passed, {n_fail} failed")
    sys.exit(1 if n_fail else 0)
