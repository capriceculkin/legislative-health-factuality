#!/usr/bin/env python3
"""
us_sections.py   (used by us_rebuild.py segment; can also be imported on its own)   ROUND6_2026_10_03

Decides which paragraphs of the Congressional Record belong to a bill, by the Record's own
procedural lines, the US version of the rule used for Ontario.

THE RULE
  Text belongs to a bill only from a line that brings THAT bill before the House:
     "I move to suspend the rules and pass the bill (H.R. 876)"
     "I call up the conference report on the bill (H.R. 1)"
     "the Chair declares the House in the Committee of the Whole House on the state of the Union
      for the consideration of the bill, H.R. 3762"
     "the House resolved itself into the Committee of the Whole ... for the further consideration
      of the bill (H.R. 5142)"
     "having had under consideration the bill (H.R. 3)", motions to instruct or recommit,
     taking a bill from the Speaker's table, discharge with immediate consideration,
     "submitted the following conference report and statement on the bill (H.R. 1)"
  and runs until a line that brings up ANOTHER measure, a one-minute speech or special order,
  or a procedural break (prayer, adjournment, recess, committee reports, messages).
  In the daily edition (1994 on) each Record item has a title, and later items with the same
  title on the same day continue the same debate (a postponed vote, the debate resumed).

WHAT HAPPENS TO TEXT THE OLD METHOD HAD KEPT FOR THE BILL
  debate     the bill's own consideration (kept)
  speech     one-minute speeches, special orders and morning-hour speeches that mention the bill
             (kept and tagged; whether they count is question 8)
  removed    another measure's debate, but ONLY when two independent checks agree:
               A  the Record's own line brings up that other measure (quoted in the report), and
               D  the text names the other measure at least as often as this bill (or this bill
                  at most once), and
               B  the Record item's title does not name this bill or its titles, or
               C  Congress.gov lists no House floor action on this bill that day (or the day
                  before or after)
             and procedural items (committee report lists, discharge notices, enrollment
             corrections) with no line bringing up this bill and no member speaking 40+ words
  held       anything else (kept in the data, tagged, listed with its text for a look)
  When Congress.gov lists House debate on the bill that day (or the day before or after, if that day
  does not already hold the bill's own debate) and no line brings the bill up, a piece that names the
  bill is held rather than taken out, unless the Record's own line gives it to another measure that is
  in the data that day (the text stays under that bill-day) or it is a procedural item by its title.

INSIDE THE TEXT THAT IS KEPT, two more tags (the paragraphs stay in the files; the
choices file decides whether their sentences count):
  printed    text printed in the Record but not spoken: the bill or amendment text after
             "The text of the bill is as follows:", "The Clerk read as follows:",
             conference reports and joint statements, until the next member or the Chair speaks
  votelist   roll-call name lists ("[Roll No. 123]", "YEAS--230", ...)
"""
import re
from collections import Counter, defaultdict

# ----------------------------------------------------------------------------- measures
_TYPES = [("hconres", r"H\.\s?Con\.\s?Res"), ("hjres", r"H\.\s?J\.\s?Res"), ("hres", r"H\.\s?Res"),
          ("hr", r"H\.\s?R"), ("sconres", r"S\.\s?Con\.\s?Res"), ("sjres", r"S\.\s?J\.\s?Res"),
          ("sres", r"S\.\s?Res"), ("s", r"S\.")]
# "(H.R. 876)", "<H.R. 4238)", "CH.R. 5142>" (scanned pages read "(" as "C" or "<")
MEAS = re.compile(r"(?:(?<![A-Za-z.])|(?<=[\s(]C))(?:" + "|".join(f"(?P<{k}>{p})" for k, p in _TYPES)
                  + r")\.?\s?(?P<num>\d{1,5})\b")
MEAS2 = re.compile(r"\b(House|Senate)\s+(Joint\s+|Concurrent\s+)?Resolution\s+(?:No\.\s*)?(\d{1,5})\b")
_M2 = {("House", ""): "hres", ("House", "Joint"): "hjres", ("House", "Concurrent"): "hconres",
       ("Senate", ""): "sres", ("Senate", "Joint"): "sjres", ("Senate", "Concurrent"): "sconres"}


def measures(s):
    """[(start, (type, number))] for every measure named in s, in order."""
    out = [(m.start(), (next(k for k, _ in _TYPES if m.group(k)), int(m.group("num")))) for m in MEAS.finditer(s)]
    out += [(m.start(), (_M2[(m.group(1), (m.group(2) or "").strip())], int(m.group(3)))) for m in MEAS2.finditer(s)]
    return sorted(out)


def key_of(btype, number):
    return (str(btype).lower(), int(number))


def label(k):
    names = {"hr": "H.R.", "s": "S.", "hres": "H.Res.", "hjres": "H.J.Res.", "hconres": "H.Con.Res.",
             "sres": "S.Res.", "sjres": "S.J.Res.", "sconres": "S.Con.Res."}
    return f"{names.get(k[0], k[0])} {k[1]}" if k else ""


def count_measure(s, k):
    return sum(1 for _, m in measures(s) if m == k)


# ----------------------------------------------------------------------------- lines
W = r"\s+"
CONS = [  # (name, formula, characters after it in which the measure must appear)
    ("suspend", re.compile(r"suspend(?:ing)?\s+the\s+rules\s+and\s+(?:pass(?:ing)?|agree(?:ing)?\s+to|"
                           r"concur(?:ring)?\s+in)", re.I), 110),
    ("call_up", re.compile(r"\bI\s+(?:hereby\s+)?call\s+up\b", re.I), 110),
    ("cow", re.compile(r"(?:declares\s+the\s+House\s+in|resolved\s+itself\s+into)\s+the\s+Committee\s+of\s+the\s+"
                       r"Whole\s+House\s+on\s+the\s+state\s+of\s+the\s+Union,?\s+for\s+the\s+(?:further\s+)?"
                       r"consideration\s+of", re.I), 70),
    ("cow_report", re.compile(r"having\s+had\s+under\s+consideration", re.I), 70),
    ("speakers_table", re.compile(r"(?:take|call(?:\s+up)?)\s+from\s+the\s+Speaker'?s\s+table", re.I), 90),
    ("discharge", re.compile(r"be\s+discharged\s+from\s+(?:the\s+)?further\s+consideration\s+of", re.I), 70),
    ("immediate", re.compile(r"consent\s+(?:for|to)\s+the\s+immediate\s+consideration\s+(?:in\s+the\s+House\s+)?of", re.I), 70),
    # round 3: lines read in the round-2 report that bring a measure up and were not recognized
    ("in_order", re.compile(r"Pursuant\s+to\s+House\s+Resolution\s+\d+,?\s+it\s+is\s+now\s+in\s+order\s+to\s+(?:debate|consider)",
                            re.I), 160),
    ("conf_uc", re.compile(r"consent\s+that\s+it\s+(?:now\s+)?be\s+in\s+order\s+to\s+(?:proceed\s+(?:immediately\s+)?to\s+)?"
                           r"consider\s+the\s+conference\s+report\s+(?:on|to\s+accompany)", re.I), 70),
    ("vote_on", re.compile(r"unfinished\s+business\s+is\s+the\s+(?:(?:vote|question)\s+on\s+(?:the\s+)?(?:passage\s+of|"
                           r"motion\s+to\s+recommit\s+(?:on|of)|adoption\s+of|agreeing\s+to)|question\s+whether\s+the\s+House,?\s+"
                           r"on\s+reconsideration,?\s+will\s+pass)", re.I), 70),
    ("offer_res", re.compile(r"\bI\s+offer\s+(?:a|the)\s+(?:privileged\s+)?(?:concurrent\s+|joint\s+)?resolution", re.I), 40),
    ("instruct", re.compile(r"(?:offer|have)\s+a\s+(?:privileged\s+)?motion\s+to\s+instruct|motion\s+to\s+instruct\s+"
                            r"(?:conferees|managers)\s+on", re.I), 140),
    ("instruct2", re.compile(r"moves\s+that\s+the\s+managers\s+on\s+the\s+part\s+of\s+the\s+House", re.I), 220),
    ("recommit", re.compile(r"\bmoves\s+to\s+recommit", re.I), 90),
    ("concur", re.compile(r"move\s+that\s+the\s+House\s+(?:concur|agree|recede|insist|disagree)\s+(?:in|to|from)\s+the\s+"
                          r"Senate\s+amendments?(?:\s+numbered\s+[\d,\sand]+)?\s+to", re.I), 60),
    ("veto", re.compile(r"veto\s+message\s+(?:of|from)\s+the\s+President\s+on\s+the", re.I), 50),
    ("veto_return", re.compile(r"returning\s+herewith\s+without\s+my\s+approval", re.I), 40),
    ("called", re.compile(r"The\s+Clerk\s+called\s+the", re.I), 60),
    ("further", re.compile(r"\bfurther\s+consideration\s+of", re.I), 45),
    ("conf_filing", re.compile(r"submitted\s+the\s+following\s+conference\s+report\s+and\s+statement\s+on", re.I), 70),
    ("resume", re.compile(r"(?:the\s+House\s+resumed|unfinished\s+business\s+is)\s+(?:the\s+)?(?:further\s+)?"
                          r"consideration\s+of", re.I), 70),
]
_QUICK = re.compile(r"suspend|call|consideration|Speaker'?s\s+table|instruct|recommit|conference\s+report|veto|Senate\s+amendment|"
                    r"without\s+my\s+approval|in\s+order\s+to|unfinished\s+business|\boffer\s+(?:a|the)\s", re.I)
_KEYS = {"suspend": ("suspend",), "call_up": ("call up",), "cow": ("committee of the whole",), "cow_report": ("having had",),
         "speakers_table": ("speaker's table", "speaker\u2019s table", "speakers table"), "discharge": ("discharged",), "immediate": ("immediate consideration",), "instruct": ("instruct",),
         "instruct2": ("managers",), "recommit": ("recommit",), "veto": ("veto",), "concur": ("senate amendment",), "veto_return": ("without my approval",), "called": ("clerk called",),
         "further": ("further consideration",), "conf_filing": ("conference report",),
         "resume": ("resumed consideration", "resumed the consideration", "resumed further", "unfinished business is"),
         "in_order": ("now in order to",), "conf_uc": ("conference report",), "vote_on": ("unfinished business is the",),
         "offer_res": ("resolution",)}
STRONG = {"veto_return", "called", "rule_call", "concur", "suspend", "call_up", "cow", "cow_report", "speakers_table", "discharge", "conf_filing", "veto",
          "in_order", "conf_uc", "vote_on", "offer_res"}


_CUT = re.compile(r";|(?<![A-Z])(?<!Res)(?<!Con)(?<!Mr)(?<!Mrs)(?<!Ms)(?<!No)(?<!Dr)(?<!Jr)(?<!St)\.\s+[A-Z]")


_DURING = re.compile(r"[(\[<]during\s+[^)\]>]{0,200}[)\]>]", re.I)
# a line that says a measure MAY be brought up later, not that it is brought up now:
# "it shall be in order to take from the Speaker's table the bill", "to entertain motions to suspend the rules"
_NOT_NOW = re.compile(r"entertain\s+(?:a\s+)?motions?|\bshall\s+be\s+in\s+order\b|\bbe\s+in\s+order\s+at\s+any\s+time\b", re.I)
_NOT_NOW_SUSPEND = re.compile(r"entertain\s+a\s+motion|in\s+order\s+(?:at\s+any\s+time\s+)?(?:for|to)\b", re.I)   # round 2, suspend only
# a Chair's list of the votes still to come: "will be followed by 5-minute votes on ... the motions to suspend the
# rules and pass H.R. 5161" names the measures to be voted on later, it does not bring them up
_LATER = re.compile(r"followed\s+by\s+(?:an?\s+)?(?:\d+-\s?minute\s+)?votes?\s+on|votes?\s+on\s+the\s+following\s+motions", re.I)
# round 5: a paragraph that ends without closing its sentence continues on the next one. Resolution text in the
# daily edition is printed one line per paragraph ("it shall be" / "in order to take from the Speaker's table the
# bill (H.R." / "1388) to reauthorize ..."), so the words before a formula may sit on the line above.
_SENTENCE_END = re.compile(r"[.!?:;][\"'”’)\]]*\s*$")
# rule text that discharges a committee ("the Committee on Rules shall be discharged from further consideration of")
_SHALL_END = re.compile(r"\bshall\s*$", re.I)


def consideration(par, tail="", prev=""):
    """(formula, (type, number)) when the paragraph brings a measure before the House. A call-up by
    direction of the Committee on Rules is formula 'rule_call' (the rule, not the bill). tail is the start of
    the next paragraph: scanned pages sometimes break a line like "I call up" / "the bill (H.R. 1629)" into
    two paragraphs, so when the formula ends a paragraph its measure may be read from the next one. prev is
    the paragraph before: when it does not end its sentence, the words just before a formula near the start of
    this paragraph are read from it (round 5)."""
    if not _QUICK.search(par):
        return None
    par = _DURING.sub(" ", par)                       # "(during the Motion to Instruct on H.R. 1308)"
    joined = par + " " + _DURING.sub(" ", tail[:300]) if tail else par
    lead_in = ""
    if prev and prev.strip() and not _SENTENCE_END.search(prev.strip()):
        lead_in = _DURING.sub(" ", prev.strip()[-240:]) + " "

    def back(m, n):
        """the n characters before the formula, reaching into the previous line when it continues there"""
        if lead_in and m.start() < n:
            return (lead_in + par[:m.start()])[-n:]
        return par[max(0, m.start() - n): m.start()]
    low = par.lower()
    best = None
    for name, rx, span in CONS:
        if not any(k in low for k in _KEYS[name]):
            continue
        for m in rx.finditer(par):
            before = back(m, 70)
            if name not in ("in_order", "conf_uc") and _NOT_NOW.search(before):
                continue                              # "it shall be in order to take from the Speaker's table ..."
            if name == "suspend" and _NOT_NOW_SUSPEND.search(before):
                continue
            if name == "discharge" and _SHALL_END.search(before):
                continue                              # rule text: "the Committee ... shall be discharged from"
            if name == "further" and re.search(r"shall\s+be\s+discharged\s+from\s*$", before, re.I):
                continue                              # rule text: "the Committee ... shall be discharged from"
            # round 6: the Chair's own line "the Committee on Energy and Commerce is discharged from further
            # consideration of the Senate bill (S. 974)" does bring the bill up (99-S974, 1986-01-30); round 5
            # skipped every "discharged from further consideration" and gave that debate to H.R. 4055
            if name in ("suspend", "vote_on") and _LATER.search(back(m, 200)):
                continue
            for n_src, src in enumerate((par, joined) if tail else (par,)):
                if n_src == 1 and len(par) - m.end() > 80:
                    break                             # the formula does not end this paragraph
                window = src[m.end(): m.end() + span]
                cut = _CUT.search(window)                      # stay in the same sentence
                window = window[: cut.start()] if cut else window
                found = measures(window)
                if found:
                    if best is None or m.start() < best[0]:
                        best = (m.start(), name, found[0][1])
                    break
    if best is None:
        return None
    name, meas = best[1], best[2]
    if name == "call_up" and meas[0] == "hres" and re.search(r"Committee\s+on\s+Rules", par, re.I):
        name = "rule_call"
    return name, meas


SIMILAR = re.compile(r"similar\s+(?:House|Senate)\s+(?:bill|joint\s+resolution|concurrent\s+resolution|resolution)|"
                     r"in\s+lieu\s+(?:thereof\s+)?(?:the\s+)?(?:provisions|text|language)\s+of", re.I)


def companion_refs(par):
    """Measures named as the companion: 'A similar House bill (H.R. 1872) was laid on the table',
    'insert in lieu thereof the provisions of H.R. 1872'."""
    if "similar" not in par.lower() and "lieu" not in par.lower():
        return set()
    out = set()
    for m in SIMILAR.finditer(par):
        found = measures(par[m.end(): m.end() + 40])
        if found:
            out.add(found[0][1])
    return out


ONE_MIN = re.compile(r"asked\s+and\s+was\s+given\s+permission\s+to\s+address\s+the\s+House\s+for\s+(?:1|l|I|one)\s+minute",
                     re.I)
SPECIAL = re.compile(r"Under\s+the\s+Speaker'?s\s+announced\s+policy\s+of|Under\s+(?:a|the)\s+previous\s+order\s+of\s+the\s+"
                     r"House,?\s+the\s+(?:gentle(?:man|woman)|following\s+Members?)", re.I)
MORNING = re.compile(r"^The\s+SPEAKER\s+pro\s+tempore\.\s+(?:The\s+Chair\s+recognizes\s+the\s+gentle(?:man|woman)\s+from\s+"
                     r"[^;]{2,80}?\s+for\s+5\s+minutes|Pursuant\s+to\s+the\s+order\s+of\s+the\s+House\s+of\s+[^.]{4,30},\s+"
                     r"the\s+Chair\s+will\s+now\s+recognize\s+Members\s+from\s+lists|"
                     # round 3: each morning-hour speaker ("... the gentleman from California (Mr. Rohrabacher) is
                     # recognized during morning-hour debate for 5 minutes")
                     r"Pursuant\s+to\s+the\s+order\s+of\s+the\s+House\s+of\s+[^.]{4,30},\s+the\s+(?:gentle(?:man|woman)|Member)\s+"
                     r"from\s+[^;]{2,80}?\s+is\s+recognized\s+(?:during\s+morning[\s-]+hour\s+debates?\s+)?for\s+5\s+minutes)")


def _has(p, keys):
    low = p.lower()
    return any(k in low for k in keys)


def is_one_min_or_special(p):
    return _has(p, ("permission to address", "announced policy", "previous order")) and bool(ONE_MIN.search(p) or SPECIAL.search(p))


def is_boundary(p):
    return _has(p, ("prayer", "clause", "message", "unanimous consent", "adjourn", "recess", "laid before", "enrolled",
                    "journal")) and bool(BOUNDARY.search(p))


def is_print_start(p):
    return _has(p, ("as follows", "amendment", "be it enacted", "resolved, that", "submitted the following", "laid before")) \
        and bool(PRINT_START.search(p))


def is_vote_start(p):
    return _has(p, ("roll", "yeas", "nays", "ayes", "noes", "not voting", "present")) and bool(VOTE_START.search(p))


SIXTY = re.compile(r"^The\s+SPEAKER\s+pro\s+tempore(?:\s*[(\[<][^)\]>]{0,60}[)\]>])?\.\s+(?:Under\s+[^;]{0,120}?,\s+)?"
                   r"the\s+(?:gentle(?:man|woman)|Member)\s+from\s+[^;]{2,80}?\s+is\s+recognized\s+for\s+(?:60|30)\s+minutes", re.I)


def speech_marker(par, early=False):
    if is_one_min_or_special(par):
        return True
    return bool(early and par.startswith("The SPEAKER pro tempore") and (MORNING.search(par) or SIXTY.search(par)))


BOUNDARY = re.compile(
    r"offered\s+the\s+following\s+prayer|^Under\s+clause\s+\d+\s+of\s+rule\s+[XVIL]+,?\s+(?:reports?|bills?|public|private|"
    r"executive|memorials|petitions|sponsors|the\s+following|messages?)|^A\s+(?:further\s+)?message\s+from\s+the\s+"
    r"(?:Senate|President)|^By\s+unanimous\s+consent,\s+(?:leave\s+of\s+absence|permission\s+to\s+address)|"
    r"move[sd]?\s+that\s+the\s+House\s+do\s+now\s+adjourn|declares\s+the\s+House\s+in\s+recess|"
    r"the\s+House\s+stood\s+adjourned|^The\s+SPEAKER(?:\s+pro\s+tempore)?\s+laid\s+before\s+the\s+House\s+the\s+following|"
    r"found\s+truly\s+enrolled|has\s+examined\s+the\s+Journal\s+of\s+the\s+last\s+day", re.I)

_UP = "A-ZÀ-Þ"
# surnames as the Record prints a speaker: McDERMOTT, DeLAURO, DelBENE, DesJARLAIS, AuCOIN, MILLENDER-McDONALD
_SUR = r"(?:Mc|Mac|De|Del|Des|Di|Du|La|Le|Au)?[" + _UP + r"][" + _UP + r"']+"
MEMBER = re.compile(r"^(?:Mr|Mrs|Ms|Miss|Dr)\.\s+(?:de\s+la\s+|de\s+|van\s+|von\s+)?(?:[" + _UP + r"][A-Za-zÀ-ÿ'\-]*\s+){0,3}?"
                    + _SUR + r"(?:-" + _SUR + r")*(?:\s+of\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)?"
                    r"\s*(?:[(\[<][^)\]>]{0,200}[)\]>])?\.\s")
CHAIR = re.compile(r"^The\s+(?:Acting\s+|ACTING\s+)?(?:SPEAKER|CHAIRMAN|CHAIRWOMAN|CHAIR|PRESIDING\s+OFFICER)(?:\s+pro\s+tempore)?"
                   r"(?:\s*[(\[<][^)\]>]{0,60}[)\]>])?\.\s")
VOCATIVE = re.compile(r"\b(?:Mr\.|Madam)\s+(?:Speaker|Chair(?:man|woman)?)\b")

PRINT_START = re.compile(
    r"(?:text\s+of\s+the\s+[^:]{0,140}?\s+(?:is|are|was|were)|Clerk\s+read(?:\s+the\s+[^.:]{0,90}?,?)?|"
    r"(?:amendments?|motion|resolution|bill|substitute)\s+(?:is|are|was|were))\s+as\s+follows\s*[:.]?\s*$|"
    r"^(?:The\s+)?(?:Senate|House)\s+amendments?(?:\s+(?:to|in)\s+[^.]{0,90})?\s*:$|"
    r"^Be\s+it\s+enacted\s+by\s+the\s+Senate\s+and\s+House|^Resolved,\s+That\b|"
    r"submitted\s+the\s+following\s+conference\s+report\s+and\s+statement|"
    r"laid\s+before\s+the\s+House\s+the\s+following\s+(?:veto\s+)?message", re.I)
VOTE_START = re.compile(r"^\[?\s*Roll\s+No\.\s*\d+\s*\]?$|^(?:YEAS|NAYS|AYES|NOES|NOT\s+VOTING|ANSWERED\s+\W{0,3}PRESENT\W{0,3})"
                        r"\s*[-—–]{1,2}\s*\d+|there\s+were\s*[-—–]{1,2}\s*(?:yeas|ayes)\s+\d+.{0,120}as\s+follows",
                        re.I)
VOTE_END = re.compile(r"^(?:So\s+(?:the|\(two-thirds)|The\s+result\s+of\s+the\s+vote)", re.I)

PROC_EXTRA = re.compile(r"^(CONSTITUTIONAL AUTHORITY STATEMENT|REPORTS? OF COMMITTEES? ON (PUBLIC|PRIVATE) BILLS|"
                        r"ANNOUNCEMENT BY (THE )?(COMMITTEE ON RULES|CHAIR|CHAIRMAN|SPEAKER)|AMENDMENT PROCESS FOR|"
                        r"TIME LIMITATIONS? OF REFERRED|AUTHORIZING (THE )?(SPEAKER|CLERK)|REPORT ON RESOLUTION|"
                        r"DISCHARGE OF COMMITTEE|SUBMISSION OF|CORRECTING ENROLLMENT|DIRECTING THE CLERK)")

# round 5: the speaker's name starts "Mr." / "Ms." etc., and the old pattern stopped at that first period, so it
# never matched a request and every unanimous-consent request of 40+ words counted as a member speaking
# round 5: daily-edition item titles that are procedural whatever is said in them (not "ANNOUNCEMENT BY THE CHAIR", under
# which a debate can go on in the same item)
PROC_BY_TITLE = re.compile(r"^(CONSTITUTIONAL AUTHORITY STATEMENT|REPORTS? OF COMMITTEES? ON (PUBLIC|PRIVATE) BILLS|"
                           r"ANNOUNCEMENT BY (THE )?COMMITTEE ON RULES|AMENDMENT PROCESS FOR|TIME LIMITATIONS? OF REFERRED|"
                           r"AUTHORIZING (THE )?(SPEAKER|CLERK)|REPORT ON RESOLUTION|DISCHARGE OF COMMITTEE|SUBMISSION OF|"
                           r"CORRECTING ENROLLMENT|DIRECTING THE CLERK)")

_REQUEST = re.compile(r"^(?:(?:Mr|Mrs|Ms|Miss|Dr)\.\s+)?[^.]{1,80}?\.\s+(?:Mr\.|Madam)\s+(?:Speaker|Chair(?:man|woman)?|President),\s+"
                      r"(?:I\s+(?:ask\s+unanimous\s+consent|move|offer|demand|reserve|call\s+up)|by\s+direction\s+of|pursuant\s+to)",
                      re.I)


def is_request(p):
    """A unanimous-consent request, motion or call-up, short enough not to hold a speech after it."""
    return bool(_REQUEST.match(p)) and len(p.split()) < 120


def is_debate_speech(p, cons="?"):
    """A member speaking 40+ words that are not a motion, a call-up or a unanimous-consent request."""
    if not MEMBER.match(p) or len(p.split()) < 40 or is_request(p):
        return False
    return (consideration(p) if cons == "?" else cons) is None


SEPARATOR = re.compile(r"^[_\-=\s]{5,}$")

STOP = set("that this with from have been which their there about into other such under shall more purposes provide "
           "provides amend amendment title united states section sections code public law laws year years certain "
           "respect relating related american".split())


def toks(s):
    return {w for w in re.findall(r"[a-z]{4,}", str(s or "").lower()) if w not in STOP and w not in ("bill", "act")}


def norm_title(t):
    t = (t or "").upper().replace("--CONTINUED", " ").replace("CONTINUED", " ")
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", t)).strip()


def words(s):
    return len(str(s).split())


# ----------------------------------------------------------------------------- one day
_DAY = {}


def unit_order(u):
    m = re.search(r"-pt(\d+)-Pg([HSE])(\d+)(?:-(\d+))?$", u["id"])
    if m:
        return (int(m.group(1)), int(m.group(3)), int(m.group(4) or 1), u["id"])
    m = re.search(r"-block(\d+)$", u["id"])
    if m:
        return (0, int(m.group(1)), 0, u["id"])
    return (9, 0, 0, u["id"])


def _is_heading(p):
    letters = [ch for ch in p if ch.isalpha()]
    return 4 <= len(p) <= 160 and len(letters) >= 4 and sum(ch.isupper() for ch in letters) / len(letters) >= 0.9 \
        and not MEMBER.match(p) and not CHAIR.match(p)


# headings inside printed bill text, which are not Record item headings
STATUTE_HEAD = re.compile(r"^(?:SEC(?:TION)?\.?\s|Sec\.\s|TITLE\s+[IVXLC\d]+\b|SUBTITLE\s|Subtitle\s|PART\s+[A-Z\d]|CHAPTER\s|DIVISION\s|"
                          r"\(?[a-z0-9]{1,4}\)\s)")


# sub-headings the daily edition prints as their own items in the middle of a debate
SUBHEAD = re.compile(r"^(ANNOUNCEMENT BY THE (ACTING )?(CHAIR|CHAIRMAN|CHAIRWOMAN|SPEAKER PRO TEMPORE)|PARLIAMENTARY INQUIR|"
                     r"POINT OF ORDER|SEQUENTIAL VOTES POSTPONED|RECORDED VOTE|MOTION TO RECOMMIT|"
                     r"AMENDMENT (NO \d+ )?OFFERED BY|AMENDMENTS EN BLOC|IN THE COMMITTEE OF THE WHOLE)")


def analyze_day(day, units, is_proc_title, generic=frozenset()):
    """Label every paragraph of one day's House units, in Record order. Returns (units in order,
    {unit id: [label per paragraph]}, title_map). A label is
    {"state": ("M", key) | ("speech",) | (None,), "origin": how the state was set, "cons": key brought
     up on this line or None, "formula", "sub": ""|"printed"|"votelist", "member40", "companions"}"""
    sig = (day, tuple(u["id"] for u in units))
    if sig in _DAY:
        return _DAY[sig]
    units = sorted(units, key=unit_order)
    daily = any(u.get("source") == "daily_edition" for u in units)

    def proc(nt):
        return bool(is_proc_title(nt) or PROC_EXTRA.search(nt))

    info, speech_units = {}, set()
    for u in units:
        nt = norm_title(u.get("title", ""))
        ps = u["paragraphs"]
        cons = [consideration(p, ps[i + 1] if i + 1 < len(ps) else "", ps[i - 1] if i > 0 else "") for i, p in enumerate(ps)]
        if proc(nt):                         # schedule colloquies and notices: only formal lines count
            cons = [c if c and c[0] in STRONG else None for c in cons]
        first_cons = next((i for i, c in enumerate(cons) if c), None)
        early = next((i for i, p in enumerate(u["paragraphs"][:8]) if speech_marker(p, early=daily)), None)
        if daily and PROC_BY_TITLE.search(nt):
            early = None                     # round 5: a Rules announcement given as a one-minute is still an announcement
        if early is not None and (first_cons is None or early < first_cons):
            speech_units.add(u["id"])
            if daily:                        # a one-minute or special-order item never brings up a bill
                cons = [None] * len(cons)
        info[u["id"]] = cons
    by_title = defaultdict(set)
    for u in units:
        nt = norm_title(u.get("title", ""))
        if not nt or proc(nt) or nt in generic or u["id"] in speech_units:
            continue
        for c in info[u["id"]]:
            if c and c[0] not in ("rule_call", "vote_on"):   # the rule debate shares the bill's title; a vote is not a debate
                by_title[nt].add(c[1])
    title_map = {t: next(iter(v)) for t, v in by_title.items() if len(v) == 1}
    labels = {}
    state, origin = (None,), ""
    for u in units:
        nt = norm_title(u.get("title", ""))
        paras, cons = u["paragraphs"], info[u["id"]]
        first_cons = next((i for i, c in enumerate(cons) if c), None)
        if u["id"] in speech_units:
            state, origin = ("speech",), "speech"
        elif nt in title_map:
            state, origin = ("M", title_map[nt]), "title"
        elif daily and SUBHEAD.search(nt) and state[0] == "M":
            origin = "carry"                 # a sub-heading printed as its own item inside the debate
        elif daily or proc(nt):
            state, origin = (None,), ""
        elif state[0] is not None:
            origin = "carry"                 # scanned pages: a heading may be missing or misread
        lead = first_cons is not None and first_cons <= 4 and state[0] is None
        no_speech = daily and bool(PROC_BY_TITLE.search(nt))
        out = []
        for i, p in enumerate(paras):
            c = cons[i]
            if c and c[0] == "vote_on" and state[0] == "M":
                c = None                     # round 4: a vote announced in the middle of a debate does not end it
            if c:
                state, origin = ("M", c[1]), "cons"
            elif is_one_min_or_special(p) and not no_speech:
                state, origin = ("speech",), "speech"
            elif is_boundary(p):
                state, origin = (None,), "boundary"
            st, og = state, origin
            if lead and i < first_cons:
                st, og = ("M", cons[first_cons][1]), "lead"
            out.append({"state": st, "origin": og, "cons": c[1] if c else None, "formula": c[0] if c else "",
                        "sub": "", "member40": is_debate_speech(p, c), "companions": companion_refs(p)})
        for i in range(1, len(paras)):
            ci = out[i]["cons"]
            if ci and out[i - 1]["state"] != ("M", ci) and _is_heading(paras[i - 1]):
                out[i - 1]["state"], out[i - 1]["origin"] = ("M", ci), "lead"
        labels[u["id"]] = out
    # printed text and roll-call lists: they run until a member or the Chair speaks
    for u in units:
        printed = vote = False
        for p, lab in zip(u["paragraphs"], labels[u["id"]]):
            speaker = bool(MEMBER.match(p) or CHAIR.match(p))
            if (lab["cons"] and lab["formula"] not in ("conf_filing", "veto_return")) or is_boundary(p) \
                    or is_one_min_or_special(p):
                printed = vote = False
            if printed and speaker:
                printed = False
            if vote and speaker and not VOTE_END.search(p):
                vote = False
            if is_print_start(p):
                printed = True
            if is_vote_start(p):
                vote, printed = True, False
            if vote:
                lab["sub"] = "votelist"
                if VOTE_END.search(p):
                    vote = False
            elif printed:
                lab["sub"] = "printed"
    res = (units, labels, title_map)
    if len(_DAY) > 40:
        _DAY.clear()
    _DAY[sig] = res
    return res


# the other chamber's bill of the same kind (a companion is introduced in each chamber)
_CROSS = {("hr", "s"), ("s", "hr"), ("hjres", "sjres"), ("sjres", "hjres")}

_RULE_FOR = re.compile(r"consideration\s+of|in\s+order\s+(?:[^.;]{0,80}?\s)?to\s+consider|take\s+from\s+the\s+Speaker'?s\s+table", re.I)


def rule_names(text):
    """Measures a rule resolution provides for ('... for consideration of the bill (H.R. 3) ...')."""
    out = set()
    for m in _RULE_FOR.finditer(text):
        out |= {k for _, k in measures(text[m.end(): m.end() + 130])}
    return out


# ----------------------------------------------------------------------------- one bill
def refine(b, units_by_day, chosen, bill_rx, is_proc_title, generic=frozenset(), bill_titles=(), floor_days=None,
           own_prefixes=(), vehicle_days=(), debate_days=None, plan_keys=frozenset(), rules_of_bill=frozenset(), joint=(),
           plan_days=None):
    """b: plan row; units_by_day: {day: all House units}; chosen: [(unit, method)] from the old
    selection (may be empty); bill_rx: compiled pattern for this bill's number; floor_days: dates of
    any House floor action on this bill on Congress.gov, debate_days: dates of House floor DEBATE on it
    (both None when there is no action list); own_prefixes: titles read by hand as this bill's own
    debate; plan_keys: (congress, type, number) of every bill in the data; rules_of_bill: numbers of
    the H. Res. rules Congress.gov lists for this bill; plan_days: {(congress, type, number): days the
    segment step reads for that bill} (round 5).
    Returns {day: {"paras": [(order, unit_id, idx, text, tag)], "removed": [...], "held": [...],
                   "added": n, "units": {uid: title}, "no_debate": bool, "notes": [...]}}."""
    import datetime as _dt
    me = key_of(b["type"], b["number"])
    congress = str(b.get("congress", ""))
    chosen_ids = {(u["day"], u["id"]) for u, _ in chosen}
    analyses, brought = {}, defaultdict(set)
    for day, units in units_by_day.items():
        if not units:
            continue
        units_sorted, labels, title_map = analyze_day(day, units, is_proc_title, generic)
        analyses[day] = (units_sorted, labels, title_map)
        for u in units_sorted:
            brought[norm_title(u.get("title", ""))] |= {l["cons"] for l in labels[u["id"]]
                                                        if l["cons"] and l["formula"] not in ("rule_call", "vote_on")}
    learned = {t for t, ms in brought.items() if ms == {me} and t}
    title_toks = [toks(t) for t in bill_titles if t]
    plan_days = plan_days or {}
    # round 5: days on which this bill's own debate is in the text read here (a line brings it up and a member
    # speaks 40+ words in it)
    own_days = {d for d, (us_, labs_, _) in analyses.items()
                if any(l["state"] == ("M", me) and l["origin"] in ("cons", "title", "lead") and l["member40"]
                       for u_ in us_ for l in labs_[u_["id"]])}

    def near(day, days):
        if days is None:
            return None
        d0 = _dt.date.fromisoformat(day)
        return any(abs((_dt.date.fromisoformat(x) - d0).days) <= 1 for x in days)

    def debate_missing(day):
        """Congress.gov lists House debate on this bill that day, or the day before or after when that day's
        Record (as read here) does not already hold the bill's own debate (round 5). The day before or after
        was allowed because the Record and Congress.gov can date a late sitting differently; it no longer keeps
        another bill's text when the debate Congress.gov lists is in the data on the other day."""
        if debate_days is None:
            return None
        d0 = _dt.date.fromisoformat(day)
        return any(x == day or (abs((_dt.date.fromisoformat(x) - d0).days) == 1 and x not in own_days)
                   for x in debate_days)

    def head_is_me(heading, title_map):
        nt = norm_title(heading)
        if nt in title_map and title_map[nt] != me:
            return False                     # the Record's items under this title bring up another measure
        tt = toks(nt)
        return bool(bill_rx.search(heading or "")) or nt in learned \
            or any(nt.startswith(norm_title(x)) for x in own_prefixes) \
            or any(tt and len(tt & t2) >= 0.5 * len(tt) for t2 in title_toks)

    out = {}
    for day, (units_sorted, labels, title_map) in analyses.items():
        keep, held, cand, notes = [], [], defaultdict(list), []
        added, unit_titles = 0, {}
        floor_near, debate_near = near(day, floor_days), near(day, debate_days)
        debate_gap = debate_missing(day)
        units_by_id = {u["id"]: (order, u) for order, u in enumerate(units_sorted)}
        # companions: measures the Record names as passed in lieu of this bill, or of which this bill is the companion
        comp = set()
        for u in units_sorted:
            for lab in labels[u["id"]]:
                if lab["companions"] and lab["state"] == ("M", me):
                    comp |= lab["companions"] - {me}
                elif lab["companions"] and lab["state"][0] == "M" and me in lab["companions"]:
                    comp.add(lab["state"][1])
        for order, u in enumerate(units_sorted):
            uid, nt = u["id"], norm_title(u.get("title", ""))
            was_chosen = (day, uid) in chosen_ids
            for i, (p, lab) in enumerate(zip(u["paragraphs"], labels[uid])):
                if SEPARATOR.match(p):
                    continue                             # the line between Record items
                st = lab["state"]
                if st == ("M", me):
                    if not was_chosen and lab["origin"] not in ("cons", "title", "lead"):
                        continue                         # never add text reached only by carrying over
                    added += not was_chosen
                    keep.append((order, uid, i, p, "debate", lab["sub"]))
                    unit_titles[uid] = u.get("title", "")
                elif not was_chosen:
                    continue
                elif st == ("speech",):
                    keep.append((order, uid, i, p, "speech", lab["sub"]))
                    unit_titles[uid] = u.get("title", "")
                elif st[0] == "M":
                    cand[(uid, "other", st[1])].append((order, i, p, lab))
                elif is_proc_title(nt) or PROC_EXTRA.search(nt) or lab["origin"] == "boundary":
                    cand[(uid, "procedural", None)].append((order, i, p, lab))
                else:
                    cand[(uid, "unexplained", None)].append((order, i, p, lab))
        to_remove = []
        # round 3: inside one Record item, a heading that is this bill's, after another measure's debate, starts this
        # bill's own text again (a scanned block can hold two debates when a heading was not read as one)
        # round 4: only in scanned blocks (the daily edition already splits items by title), never on a heading inside
        # printed bill text ("SEC. 3. ...", "TITLE I--..."), and only on a heading that is clearly this bill's: its number,
        # a title read by hand, or at least 80% of the words of its own title
        def own_heading_line(p, lab):
            if lab["sub"] == "printed" or STATUTE_HEAD.match(p) or not _is_heading(p):
                return False
            nt_h = norm_title(p)
            if nt_h in title_map and title_map[nt_h] != me:
                return False
            tt = toks(nt_h)
            return bool(bill_rx.search(p)) or any(nt_h.startswith(norm_title(x)) for x in own_prefixes) \
                or any(len(t2) >= 2 and len(tt & t2) >= 0.8 * len(t2) for t2 in title_toks)
        for key in [k for k in cand if k[1] == "other"]:
            items = sorted(cand[key], key=lambda x: (x[0], x[1]))
            order0, u0 = units_by_id[key[0]]
            if u0.get("source") == "daily_edition":
                continue
            line_pos = next((n for n, (_, _, _, l) in enumerate(items) if l["cons"] == key[2]), -1)
            split = next((n for n in range(line_pos + 1, len(items))
                          if own_heading_line(items[n][2], items[n][3])
                          and bill_rx.search(" ".join(p for _, _, p, _ in items[n:]))), None)
            if split is not None:
                cand[key] = items[:split]
                cand[(key[0], "own_heading", key[2])] = items[split:]
        joint_titles = [norm_title(t) for d, t in joint if d == day]
        removed_titles = {}                      # item title -> measure, for pieces taken out by the Record's own line
        order_kinds = {"other": 0, "procedural": 1, "own_heading": 1, "unexplained": 2}
        for (uid, kind, other), items in sorted(cand.items(), key=lambda kv: (order_kinds[kv[0][1]], units_by_id[kv[0][0]][0])):
            if not items:
                continue
            order, u = units_by_id[uid]
            text = " ".join(p for _, _, p, _ in items)
            nt = norm_title(u.get("title", ""))
            ev = {"unit": uid, "title": u.get("title", ""), "kind": kind, "measure": label(other),
                  "paragraphs": len(items), "words": words(text), "first": text[:300], "url": u.get("url", ""),
                  "idx": [i for _, i, _, _ in items], "mentions_this_bill": len(bill_rx.findall(text))}
            lines = [p[:250] for _, _, p, _ in items if measures(p)][:5]
            tag_keep = "held"
            if joint_titles and any(nt.startswith(j) for j in joint_titles):
                ok, tag_keep, why = False, "debate", "a joint debate on this bill and another, read by hand (section_hand_checks.json)"
            elif kind == "own_heading":
                ok, why = False, "after a heading that is this bill's, inside the same Record item"
            elif kind == "other":
                line_lab = next(((p, l) for _, _, p, l in items if l["cons"] == other), None)
                if line_lab is None:                     # the line is in an earlier item with this title
                    line_lab = next(((pp, ll) for uu in units_sorted for pp, ll in zip(uu["paragraphs"], labels[uu["id"]])
                                     if ll["cons"] == other), None)
                line, formula = (line_lab[0], line_lab[1]["formula"]) if line_lab else (None, "")
                kb = len(bill_rx.findall(text))
                km = count_measure(text, other)
                # the heading over this text: the item title (daily edition), or the nearest heading line
                # above it inside a scanned block (a scanned block can hold several debates)
                heading = u.get("title", "")
                if u.get("source") != "daily_edition":
                    first_i = min(i for _, i, _, _ in items)
                    hh = [u["paragraphs"][j] for j in range(first_i, -1, -1) if _is_heading(u["paragraphs"][j])]
                    heading = hh[0] if hh else heading
                local = any(l["origin"] in ("cons", "title", "lead") for _, _, _, l in items)
                A, B, C, D = line is not None, not head_is_me(heading, title_map), floor_near is False, (kb <= 1 or km >= kb)
                in_plan_other = (congress,) + other in plan_keys
                desc = ""
                if line:
                    pos = next((st for st, k in measures(line) if k == other), None)
                    desc = line[pos: pos + 300] if pos is not None else ""
                td, title_share, title_hits = toks(desc), 0.0, 0
                for t2 in title_toks:
                    if len(t2) >= 2 and len(td & t2) / len(t2) > title_share:
                        title_share, title_hits = len(td & t2) / len(t2), len(td & t2)
                is_rule = other[0] == "hres" and (formula == "rule_call" or other[1] in rules_of_bill)
                rule_for_me = is_rule and me in rule_names(text)
                # round 5: the other measure's own bill-day on this day is in the data (its refine reads this day), and
                # every paragraph here reached it from its own line or item title, so the text is kept there
                other_day = day in plan_days.get((congress,) + other, ())
                direct = all(l["origin"] in ("cons", "title", "lead") for _, _, _, l in items)
                # round 5: the item title (or heading) is this bill's own title, and the other measure is the other
                # chamber's bill: a same-titled companion (H.R. 3869 for S. 1569, May 23, 1994)
                tt_head = toks(norm_title(heading))
                head_share = max([len(tt_head & t2) / len(t2) for t2 in title_toks if len(t2) >= 3] or [0.0])
                cross = (me[0], other[0]) in _CROSS
                ev.update({"other_in_data_that_day": other_day, "heading_title_share": round(head_share, 2)})
                ev.update({"line": (line or "")[:300], "heading": heading[:120], "mentions_this_bill": kb,
                           "mentions_other": km, "A_line_brings_up_other": A, "B_heading_not_this_bill": B,
                           "C_no_house_floor_action": C if floor_days is not None else "no Congress.gov action list",
                           "D_other_named_as_often": D, "local_line": local,
                           "rule_for_this_bill": rule_for_me,
                           "rule_on_congress_gov": other[1] in rules_of_bill if other[0] == "hres" else ""})
                if rule_for_me:
                    ok, tag_keep, why = False, "rule", "the rule that brings this bill up (tagged rule)"
                elif not in_plan_other and title_share >= 0.9 and title_hits >= 4:
                    # round 4: the line's description is this bill's own official title, under another number that is
                    # not in the data (a misprint, as "H.R. 436" for H.R. 45 on May 16, 2013, or a same-titled companion)
                    ok, tag_keep, why = False, "companion", (f"the line names {label(other)} but describes it with this "
                                                             f"bill's own title (a misprinted number or a same-titled "
                                                             f"companion; tagged companion)")
                elif other in comp:
                    in_data = (congress,) + other in plan_keys
                    ev["companion_in_data"] = in_data
                    if in_data and A:
                        ok, why = True, ""
                        ev["why_removed"] = (f"companion {label(other)} is in the data, and this text stays there "
                                             f"under its own bill-day")
                    else:
                        ok, tag_keep, why = False, "companion", (f"the House debated its companion {label(other)} and "
                                                                 f"passed this bill in its place (tagged companion)")
                elif not in_plan_other and cross and head_share >= 0.8:
                    ok, tag_keep, why = False, "companion", (f"the Record item's title is this bill's own title and its line "
                                                             f"brings up {label(other)}, the other chamber's bill under that "
                                                             f"title, which is not in the data (tagged companion, round 5)")
                else:
                    ok = A and (B or C) and (local or D)
                    why = ("" if ok else "no line found that brings up the other measure" if not A else
                           "the heading is this bill's and Congress.gov shows House action on it that day" if not (B or C)
                           else "carried over from an earlier debate and this bill is named more often")
                    # round 3: the Record's own formal line, inside this piece, brings up the other measure, and the
                    # piece names it at least twice and at least twice as often as this bill. Then a heading that
                    # resembles this bill's title, or House action on this bill the same day, does not make it this
                    # bill's text. (A misprinted number in a call-up line names the "other" measure only once.)
                    line_here = any(l["cons"] == other for _, _, _, l in items)
                    strong_line = formula in STRONG or bool(line and CHAIR.match(line))
                    maybe_companion = not in_plan_other and title_share >= 0.6     # round 4: kept as before (held)
                    if A and line_here and strong_line and km >= 2 and (kb == 0 or km >= 2 * kb) and not maybe_companion:
                        ev["strong"] = True
                        if not ok:
                            ok = True
                            ev["why_removed"] = (f"the Record's own line brings up {label(other)} here, and the text names "
                                                 f"it {km} times against {kb} for this bill (round 3)")
                        if u.get("source") == "daily_edition" and nt:
                            removed_titles.setdefault(nt, other)
                if ok and A and other_day and direct:
                    ev["elsewhere"] = True
            elif kind == "procedural":
                brings_me = any(l["cons"] == me for _, _, _, l in items)
                voc = any(VOCATIVE.search(p) for _, _, p, _ in items)
                kb_p = ev["mentions_this_bill"]
                # round 5: a member SPEAKS in it only with 40+ words addressed to the Chair that are not a request
                # ("Mr. Speaker, I ask unanimous consent ..."); a daily-edition item whose title is a fixed procedural
                # title (constitutional authority statement, report on a resolution, announcement, enrollment
                # correction ...) is procedural by its title
                speaking = any(len(p.split()) >= 40 and VOCATIVE.search(p) and not is_request(p) for _, _, p, _ in items)
                title_proc = u.get("source") == "daily_edition" and bool(PROC_BY_TITLE.search(nt))
                # round 4: a long procedural stretch (enrolled-bill lists, adjournment) that names this bill at most twice
                # is not its debate even when a member addresses the Chair somewhere in it
                ok = not brings_me and (title_proc or not speaking or (kb_p <= 2 and ev["words"] >= 5000))
                why = "" if ok else "a member speaks 40+ words in it that are not a request"
                ev["member_addresses_chair"] = voc
                ev["member_speaks"] = speaking
                ev["member_paragraphs"] = [p[:240] for _, _, p, _ in items if is_debate_speech(p)][:3]
                ev["paragraphs_naming_bill"] = [p[:240] for _, _, p, _ in items if bill_rx.search(p)][:3]
                round4_ok = not brings_me and (not voc or (kb_p <= 2 and ev["words"] >= 5000))
                if ok and title_proc:
                    ev["strong"] = ev["title_proc"] = True     # the guard below never holds it
                    if not round4_ok:
                        ev["why_removed"] = "a procedural Record item by its title, with no line that brings this bill up (round 5)"
                elif ok and not round4_ok:
                    ev["why_removed"] = ("procedural; the only words addressed to the Chair are requests or under 40 words "
                                         "(round 5)")
            else:
                kb = len(bill_rx.findall(text))
                found = [k for _, k in measures(text) if k != me]
                others, distinct = len(found), len(set(found))
                ok = kb <= 3 and others >= max(5, 10 * kb) and debate_near is False   # needs an action list
                ev.update({"mentions_this_bill": kb, "mentions_other_measures": others, "distinct_other_measures": distinct})
                why = "" if ok else ("no line in the Record brings up any measure here, and it is not a speech or a "
                                     "procedural item")
                # round 3: a list that disposes of many measures at once (the Boyle-Turton omnibus names 30 or more)
                if not ok and kb <= 3 and distinct >= 15:
                    ok, ev["strong"] = True, True
                    ev["why_removed"] = f"a list naming {distinct} other measures and this bill {kb} times (round 3)"
                # round 3: a later Record item with the same title as an item taken out above, with no line of its own
                # and not naming this bill, is the same other debate continued (the daily edition splits long debates)
                elif not ok and kb == 0 and nt and nt in removed_titles and me not in brought.get(nt, set()):
                    ok, ev["strong"] = True, True
                    ev["measure"] = label(removed_titles[nt])
                    ev["why_removed"] = (f"continues the debate on {label(removed_titles[nt])} under the same item title, "
                                         f"and does not name this bill (round 3)")
            ev["why_held"] = why
            if ok:
                to_remove.append((ev, items, uid))
            else:
                for order2, i, p, lab in items:
                    keep.append((order2, uid, i, p, tag_keep, lab["sub"]))
                unit_titles[uid] = u.get("title", "")
                if tag_keep == "held":
                    held.append({**ev, "why": why, "text": text[:600], "lines": lines})
                else:
                    notes.append({**ev, "tag": tag_keep, "why": why})
        has_debate = any(x[4] in ("debate", "companion") for x in keep)
        if to_remove and not has_debate and debate_gap:
            # Congress.gov lists House DEBATE on this bill that day (or the day before or after, when that day does not
            # hold the bill's own debate), but no line here brings it up: the real debate may be missing, so a piece is
            # kept (held) when it could be this bill's, that is when it names this bill or sits under this bill's
            # heading. Round 3: a piece the Record's own line gives to another measure, or that never names this bill
            # under another heading, still goes. Round 5: so does a piece whose measure is in the data that day (its
            # text stays there) and a procedural item by its title.
            stay = []
            for ev, items, uid in to_remove:
                could_be_mine = ev.get("mentions_this_bill", 0) >= 1 or ev.get("B_heading_not_this_bill") is False
                if ev.get("strong") or ev.get("elsewhere") or not could_be_mine:
                    reason = ("a procedural Record item by its title" if ev.get("title_proc")
                              else "the Record's own line in this piece brings up another measure" if ev.get("strong")
                              else f"{ev.get('measure')} is in the data that day and keeps this text under its own bill-day"
                              if ev.get("elsewhere") else "the piece never names this bill and sits under another heading")
                    r5 = ev.get("title_proc") or (ev.get("elsewhere") and not ev.get("strong"))
                    if "(round " not in str(ev.get("why_removed", "")):
                        ev["why_removed"] = (f"{reason}; taken out although Congress.gov lists House debate on this bill "
                                             f"that day or the day before or after ({'round 5' if r5 else 'round 3'})")
                    stay.append((ev, items, uid))
                    continue
                for order2, i, p, lab in items:
                    keep.append((order2, uid, i, p, "held", lab["sub"]))
                unit_titles[uid] = ev["title"]
                held.append({**ev, "why": "Congress.gov lists House debate on this bill that day, no line in the Record "
                             "brings it up, and this piece names the bill or sits under its heading", "text": ev["first"]})
            to_remove = stay
        elif to_remove and not has_debate and debate_near and not debate_gap:
            for ev, items, uid in to_remove:          # round 5: what round 4 would have held here, and why it goes now
                could_be_mine = ev.get("mentions_this_bill", 0) >= 1 or ev.get("B_heading_not_this_bill") is False
                if could_be_mine and not ev.get("strong") and "(round " not in str(ev.get("why_removed", "")):
                    ev["why_removed"] = ("Congress.gov lists House debate on this bill only on the day before or after, and "
                                         "the Record of that day holds the bill's own debate (round 5)")
        removed = [ev for ev, _, _ in to_remove]
        if (b["bill_key"], day) in set(vehicle_days):
            keep = [(o, uid, i, p, "vehicle" if t == "debate" else t, s) for o, uid, i, p, t, s in keep]
        keep.sort(key=lambda x: (x[0], x[2]))
        rows, seen = [], set()
        for o, uid, i, p, t, s in keep:
            if (uid, i) not in seen:
                seen.add((uid, i))
                rows.append((o, uid, i, p, t + ("+" + s if s else "")))
        spoken = any(t in ("debate", "vehicle", "companion") and is_debate_speech(p) for _, _, _, p, t in rows)
        if rows or removed:
            out[day] = {"paras": rows, "removed": removed, "held": held, "added": added, "units": unit_titles,
                        "no_debate": bool(rows) and not spoken, "notes": notes}
    return out
