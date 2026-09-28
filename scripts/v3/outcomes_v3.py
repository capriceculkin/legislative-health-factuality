#!/usr/bin/env python3
"""
outcomes_v3.py
One outcome table for all three jurisdictions, keyed by the predications'
bill_key. Every outcome records its source and what it was checked against.

Reference (ground truth) wherever it exists: the legislature's own bill page,
downloaded by fetch_official_status.py.

  Ontario  36th Parliament on: OLA bill status page.
           Before 1995: ontario_fsob_votes.json, else the Hansard (a THIRD
           READINGS heading, "read a third time", or Royal Assent in the bill's
           own debate text). FSOB and the Hansard method are each scored
           against the OLA pages, and each is used only if it agrees >= 95%.
  Quebec   Assemblee nationale bill page ("Date de la sanction"), checked
           against quebec_vote_outcomes_combined.json.
  US       Outcome = passed the House. Voteview passage-type roll call first;
           else Congress.gov House action (voice votes; used only if it agrees
           with Voteview >= 95%); else plan.json. became_law from Congress.gov.

Writes data/v3_outcomes.json, outputs/audit/outcomes_report.txt and
outputs/audit/outcome_spotcheck.csv (random bills with their official page, to click).
Run from project root:  python3 scripts/v3/outcomes_v3.py
"""
import csv, datetime as dt, html as htmlmod, json, random, re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_JSON = ROOT / "data" / "v3_outcomes.json"
AUD = ROOT / "outputs" / "audit"
AUD.mkdir(parents=True, exist_ok=True)
STATUS = ROOT / "data" / "v3_status_cache"
AGREE_MIN, MIN_N = 0.95, 30
TODAY = dt.date.today()
lines, spot = [], []


def say(s=""):
    print(s)
    lines.append(str(s))


def load(p, default=None):
    p = ROOT / p
    if not p.exists():
        say(f"  (not found: {p.relative_to(ROOT)})")
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def page_text(path):
    raw = path.read_text(encoding="utf-8", errors="ignore")
    raw = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", raw)
    return re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()


PASS_WORDS = ("passed", "carried", "agreed", "adopt", "royal assent", "sanction", "enacted", "became law")
FAIL_WORDS = ("not agreed", "failed", "lost", "defeated", "negativ", "died", "mort", "withdrawn", "retir", "rejected", "not passed")


def passed_flag(raw):
    t = str(raw or "").strip().lower()
    if not t:
        return None
    if any(w in t for w in FAIL_WORDS):
        return 0
    if any(w in t for w in PASS_WORDS):
        return 1
    return None


def pred_keys(j):
    p = ROOT / "data" / "dbpedia_pipeline" / j / "predications_v3.json"
    with open(p, encoding="utf-8") as f:
        return {r.get("bill_key") for r in json.load(f)}


def rate(pairs):
    """pairs: list of (a, b) with both not None. Returns (agree, n, share)."""
    n = len(pairs)
    a = sum(x == y for x, y in pairs)
    return a, n, (a / n if n else 0.0)


def crosstab(pairs, la, lb):
    t = Counter(pairs)
    return ", ".join(f"{la}={a} {lb}={b}: {n}" for (a, b), n in sorted(t.items(), key=str))


result = {"us": {}, "ontario": {}, "quebec": {}}
# outcomes checked by hand on the official page (with what the page says and when it was checked)
HAND = {(h["jurisdiction"], h["bill_key"]): h for h in (load("data/v3_hand_checks.json", []) or [])}

# ======================================================================= ONTARIO
say("=" * 72 + "\nONTARIO\n" + "=" * 72)
fsob = load("data/canada/ontario/ontario_fsob_votes.json", {})
fs = {}
for sk, sd in fsob.items():
    for r in sd.get("records", []):
        n = str(r.get("bill_number", "")).strip()
        if n.isdigit():
            fs[f"{sk}-Bill{int(n)}"] = r
master = load("data/canada/ontario/v3/bills_master.json", {})
segs = load("data/canada/ontario/v3/hansard_segments_v3.json", {})

# sessions still running: any Hansard debate in the last 365 days
last = defaultdict(str)
for k, v in master.items():
    for d in v.get("anchor_dates") or []:
        last[k.rsplit("-Bill", 1)[0]] = max(last[k.rsplit("-Bill", 1)[0]], str(d))
live_on = {s for s, d in last.items() if d >= (TODAY - dt.timedelta(days=365)).isoformat()}
say(f"sessions still running (debate within a year): {sorted(live_on) or 'none'}")


def ola_status(path):
    """Parse an OLA bill status page. Returns (flag, description)."""
    t = page_text(path)
    if "Royal Assent received" in t:
        return 1, "OLA: Royal Assent received"
    # the Third Reading row itself carried ("Third Reading Carried on division", or the newer
    # "Third Reading Vote Carried"); NOT "Ordered for Third Reading" followed by the next row
    if re.search(r"(?<!for )Third Reading\s+(?:Vote\s+)?Carried", t):
        return 1, "OLA: third reading carried"
    # the stage name nearest the "Lost" (no other stage name in between)
    m = re.search(r"(First|Second|Third) Reading(?:(?!(?:First|Second|Third) Reading).){0,90}?\b(Lost|Negatived|Defeated)\b", t)
    if m:
        return 0, f"OLA: {m.group(1).lower()} reading {m.group(2).lower()}"
    if "First Reading" in t:
        return None, "OLA: did not reach third reading (session still running)"
    return None, "OLA: status table not found on page"


def ola_died_or_pending(bk, flag, desc):
    if flag is None and desc.startswith("OLA: did not reach") and bk.rsplit("-Bill", 1)[0] not in live_on:
        return 0, "OLA: did not reach third reading before the session ended (died)"
    return flag, desc


def hansard_status(bk):
    """Third reading or Royal Assent found in the bill's own Hansard paragraphs."""
    days = segs.get(bk) or {}
    if not days:
        return None, ""
    for d, paras in days.items():
        for p in paras:
            topic = str(p.get("topic", "")).upper()
            text = str(p.get("text", ""))
            if ("THIRD READING" in topic and "ORDERED" not in topic) or \
                    re.search(r"\bread a third time\b|\broyal assent\b", text, re.I):
                return 1, f"Hansard: third reading / royal assent on {d}"
    if bk.rsplit("-Bill", 1)[0] in live_on:
        return None, "Hansard: no third reading yet (session still running)"
    return 0, "Hansard: no third reading found before the session ended"


official = {}
for p in sorted((STATUS / "ontario").glob("*.html")) if (STATUS / "ontario").exists() else []:
    bk = p.stem
    official[bk] = ola_died_or_pending(bk, *ola_status(p))
n404 = len(list((STATUS / "ontario").glob("*.404"))) if (STATUS / "ontario").exists() else 0
cls = Counter(v[1].split(" (")[0] for v in official.values())
say(f"OLA pages parsed: {len(official)} (404s: {n404}); results: {dict(cls)}")
unparsed = [k for k, v in official.items() if "not found on page" in v[1]]
ola_ok = bool(official) and len(unparsed) <= 0.05 * len(official)
say(f"OLA parser {'ACCEPTED' if ola_ok else 'NOT ACCEPTED'}: {len(unparsed)} pages with no readable status table "
    f"(limit 5%). e.g. {unparsed[:5]}")

# score FSOB and Hansard against the OLA pages
fs_pairs = [(passed_flag(fs[k].get("outcome")), official[k][0]) for k in official
            if k in fs and official[k][0] is not None and passed_flag(fs[k].get("outcome")) is not None]
hs_pairs = [(hansard_status(k)[0], official[k][0]) for k in official
            if official[k][0] is not None and hansard_status(k)[0] is not None]
fa, fn, fr = rate(fs_pairs)
ha, hn, hr = rate(hs_pairs)
say(f"FSOB vs OLA page: {fa}/{fn} agree ({fr:.1%}). [{crosstab(fs_pairs, 'fsob', 'ola')}]")
say(f"Hansard vs OLA page: {ha}/{hn} agree ({hr:.1%}). [{crosstab(hs_pairs, 'hansard', 'ola')}]")
use_fs = fr >= AGREE_MIN and fn >= MIN_N
use_hs = hr >= AGREE_MIN and hn >= MIN_N
if ola_ok and len(official) >= MIN_N:
    if fn < MIN_N:
        say(f"  FSOB overlaps the OLA pages on only {fn} bills (< {MIN_N}); FSOB not used without evidence")
    if hn < MIN_N:
        say(f"  Hansard method overlaps the OLA pages on only {hn} bills (< {MIN_N}); not used without evidence")
else:
    # OLA pages not fetched yet: the only reference available is FSOB itself
    say("  OLA pages not fetched (or unreadable): FSOB is used as-is, Hansard method scored against FSOB")
    hf_pairs = [(hansard_status(k)[0], passed_flag(r.get("outcome"))) for k, r in fs.items()
                if hansard_status(k)[0] is not None and passed_flag(r.get("outcome")) is not None]
    a2, n2, r2 = rate(hf_pairs)
    say(f"(no OLA pages to score against) Hansard vs FSOB: {a2}/{n2} ({r2:.1%}). "
        f"[{crosstab(hf_pairs, 'hansard', 'fsob')}]")
    use_fs, use_hs = True, (r2 >= AGREE_MIN and n2 >= MIN_N)
say(f"use FSOB: {use_fs}; use Hansard method: {use_hs}")
dis_fs = sorted(k for k in official if k in fs and official[k][0] is not None
                and passed_flag(fs[k].get("outcome")) not in (None, official[k][0]))
if dis_fs:
    say(f"bills where FSOB and the OLA page disagree ({len(dis_fs)}), first 15: {dis_fs[:15]}")

# FSOB's "outcome" is the LAST recorded vote (a carried second reading counts as carried),
# so it is not a bill-passage measure. Two other readings of the same file are scored
# against the OLA pages instead, and used for bills with no OLA page only if they agree:
#   (a) royal_assent field filled -> passed, empty -> not passed
#   (b) bill absent from FSOB for a session FSOB covers -> not passed
fs_sessions = {k.rsplit("-Bill", 1)[0] for k in fs}


def fs_ra_flag(bk):
    r = fs.get(bk)
    if r is None:
        return None, ""
    ra = str(r.get("royal_assent") or "").strip()
    return (1, f"FSOB: royal assent {ra}") if ra else (0, "FSOB: no royal assent recorded")


def fs_absent_flag(bk):
    sess = bk.rsplit("-Bill", 1)[0]
    if bk in fs or sess not in fs_sessions or sess in live_on:
        return None, ""
    return 0, "FSOB: bill not in the final-stages file for its session"


ra_pairs = [(fs_ra_flag(k)[0], official[k][0]) for k in official
            if official[k][0] is not None and fs_ra_flag(k)[0] is not None]
ab_pairs = [(fs_absent_flag(k)[0], official[k][0]) for k in official
            if official[k][0] is not None and fs_absent_flag(k)[0] is not None]
ra_a, ra_n, ra_r = rate(ra_pairs)
ab_a, ab_n, ab_r = rate(ab_pairs)
say(f"FSOB royal-assent field vs OLA page: {ra_a}/{ra_n} agree ({ra_r:.1%}). [{crosstab(ra_pairs, 'fsob_ra', 'ola')}]")
say(f"FSOB 'bill absent = not passed' vs OLA page: {ab_a}/{ab_n} agree ({ab_r:.1%}). [{crosstab(ab_pairs, 'absent', 'ola')}]")
use_ra = ra_r >= AGREE_MIN and ra_n >= MIN_N
use_ab = ab_r >= AGREE_MIN and ab_n >= MIN_N
say(f"for bills with no OLA page: use FSOB royal-assent field: {use_ra}; use FSOB absence rule: {use_ab}")

for bk in set(master) | set(fs) | set(official):
    o_flag, o_desc = official.get(bk, (None, ""))
    f_rec = fs.get(bk)
    f_flag = passed_flag(f_rec.get("outcome")) if f_rec else None
    h_flag, h_desc = hansard_status(bk)
    checks = []
    ra_flag, ra_desc = fs_ra_flag(bk)
    hc = HAND.get(("ontario", bk))
    if hc and o_flag is not None and hc.get("passed") == o_flag:
        checks.append(f"OLA page checked by hand {hc.get('checked', '')}: {hc.get('official', '')}"
                      + (f"; FSOB royal-assent field is wrong for this bill ({ra_desc})" if ra_flag not in (None, o_flag) else ""))
    elif ra_flag is not None and o_flag is not None:
        checks.append(f"FSOB royal-assent field {'agrees' if ra_flag == o_flag else 'DISAGREES'} ({ra_desc})")
    if h_flag is not None and o_flag is not None:
        checks.append("Hansard text agrees" if h_flag == o_flag else
                      "Hansard text differs (only debate days are in the text; undebated stages are missed)")
    if ola_ok and o_flag is not None:
        rec = (o_flag, o_desc, "OLA bill status page")
    elif ola_ok and o_desc and "running" in o_desc:
        rec = (None, o_desc, "OLA bill status page")
    elif use_ra and fs_ra_flag(bk)[0] is not None:
        rec = (fs_ra_flag(bk)[0], fs_ra_flag(bk)[1], "ontario_fsob_votes.json (royal assent field)")
    elif use_ab and fs_absent_flag(bk)[0] is not None:
        rec = (0, fs_absent_flag(bk)[1], "ontario_fsob_votes.json (bill absent)")
    elif use_fs and f_flag is not None:
        rec = (f_flag, str(f_rec.get("outcome")), "ontario_fsob_votes.json")
    elif use_hs and h_flag is not None:
        rec = (h_flag, h_desc, "Hansard third reading / royal assent")
    else:
        rec = (None, o_desc or h_desc or "", "")
    result["ontario"][bk] = {"outcome_raw": rec[1], "passed": rec[0], "source": rec[2],
                             "outcome_date": (f_rec or {}).get("royal_assent", ""),
                             "all_votes": (f_rec or {}).get("vote_method", ""), "check": "; ".join(checks)}
    if bk in official:
        m = re.match(r"^(\d+)-(\d+)-Bill(\d+)$", bk)
        result["ontario"][bk]["official_url"] = (f"https://www.ola.org/en/legislative-business/bills/"
                                                 f"parliament-{m.group(1)}/session-{m.group(2)}/bill-{m.group(3)}")

# ======================================================================= QUEBEC
say("\n" + "=" * 72 + "\nQUEBEC\n" + "=" * 72)
URL_RE = re.compile(r"projet-loi-(\d+)-(\d+-\d+)\.html")
health = load("data/canada/quebec_bills/quebec_health_bills_combined.json", [])
qv = {}


def add_outcomes(data, label):
    n0 = len(qv)
    items = data.items() if isinstance(data, dict) else enumerate(data or [])
    for k, v in items:
        rec = v if isinstance(v, dict) else {"outcome": v}
        url = k if isinstance(k, str) and "assnat" in k else (rec.get("bill_url") or rec.get("url") or "")
        m = URL_RE.search(url or "")
        sess = rec.get("session") or (m.group(2) if m else "")
        num = str(rec.get("bill_number") or (m.group(1) if m else "")).strip()
        if sess and num.isdigit():
            qv[f"{sess}-Bill{int(num)}"] = {"url": url, "raw": rec.get("outcome") or "",
                                            "date": rec.get("assent_date") or rec.get("vote_date") or "", "src": label}
    say(f"{label}: {len(qv) - n0} bills")


add_outcomes(load("data/canada/quebec_bills/quebec_vote_outcomes_combined.json", {}), "quebec_vote_outcomes_combined.json")
add_outcomes(load("data/canada/quebec_bills/quebec_pre1994_vote_outcomes.json", {}), "quebec_pre1994_vote_outcomes.json")
say(f"file outcome values: {dict(Counter(str(v['raw']) for v in qv.values()))}")
qidx = load("data/canada/quebec_assembly/v3/segments_index.json", []) or []
qlast = defaultdict(str)
for e in qidx:
    qlast[e.get("sitting_session", "")] = max(qlast[e.get("sitting_session", "")], str(e.get("date", "")))
cut8 = (TODAY - dt.timedelta(days=365)).strftime("%Y%m%d")
live_qc = {s for s, d in qlast.items() if d >= cut8}
say(f"sessions still running (sitting within a year): {sorted(live_qc) or 'none'}")


def assnat_status(path, bk):
    t = page_text(path)
    m = re.search(r"Date de la sanction\s*:\s*(\d{1,2}(?:er)?\s+\S+\s+\d{4})", t)
    if m:
        return 1, f"Assnat: sanctionné le {m.group(1)}"
    # final "Adoption" stage only, never "Adoption du principe"
    if re.search(r"\bAdoption\b(?! du principe)\s+Séance.{0,160}?étape a été franchie", t):
        return 1, "Assnat: adopté (sanction non affichée)"
    if "Présentation" not in t:
        return None, "Assnat: stages not found on page"
    if bk.rsplit("-Bill", 1)[0] in live_qc:
        return None, "Assnat: not adopted yet (session still running)"
    return 0, "Assnat: not adopted before the session ended (died)"


q_off = {}
for p in sorted((STATUS / "quebec").glob("*.html")) if (STATUS / "quebec").exists() else []:
    q_off[p.stem] = assnat_status(p, p.stem)
say(f"Assnat pages parsed: {len(q_off)}; results: {dict(Counter(v[1].split(' le ')[0] for v in q_off.values()))}")
q_unparsed = [k for k, v in q_off.items() if "not found" in v[1]]
q_ok = bool(q_off) and len(q_unparsed) <= 0.05 * len(q_off)
pairs = [(passed_flag(qv[k]["raw"]), q_off[k][0]) for k in q_off
         if k in qv and passed_flag(qv[k]["raw"]) is not None and q_off[k][0] is not None]
qa, qn, qr = rate(pairs)
say(f"Assnat parser {'ACCEPTED' if q_ok else 'NOT ACCEPTED'} ({len(q_unparsed)} unreadable). "
    f"outcome file vs Assnat page: {qa}/{qn} agree ({qr:.1%}) [{crosstab(pairs, 'file', 'assnat')}]")
blank_vs_page = Counter(q_off[k][1].split(" le ")[0] for k in q_off if k in qv and not qv[k]["raw"])
say(f"bills with a BLANK outcome in the file, per the Assnat page: {dict(blank_vs_page)}")

by_url = {v["url"]: k for k, v in qv.items() if v["url"]}
for e in health:
    n = str(e.get("bill_number", "")).strip()
    if not n.isdigit():
        continue
    bk = f"{e.get('session', '')}-Bill{int(n)}"
    k_num = bk if bk in qv else None
    k_url = by_url.get(e.get("bill_url", ""))
    checks = []
    if k_num and k_url:
        checks.append("file joins agree (URL and session/number)" if k_num == k_url else f"DISAGREE: URL gives {k_url}")
    f = qv.get(k_num or k_url or "", {})
    f_flag = passed_flag(f.get("raw"))
    o_flag, o_desc = q_off.get(bk, (None, ""))
    if f_flag is not None and o_flag is not None:
        if f_flag == o_flag:
            checks.append("outcome file agrees")
        elif f_flag == 1 and o_flag == 0:
            checks.append("outcome file says passed (not used: it counts a carried earlier vote; the "
                          "Assemblee nationale page shows no sanction)")
        else:
            checks.append("outcome file DISAGREES")
    if q_ok and (o_flag is not None or "running" in o_desc):
        rec = (o_flag, o_desc, "Assemblee nationale bill page")
    elif f_flag is not None:
        rec = (f_flag, f.get("raw"), f.get("src"))
    else:
        rec = (None, o_desc or "", "")
    result["quebec"][bk] = {"outcome_raw": rec[1], "passed": rec[0], "source": rec[2], "outcome_date": f.get("date", ""),
                            "all_votes": "", "check": "; ".join(checks), "official_url": e.get("bill_url", "")}

# ======================================================================= US
say("\n" + "=" * 72 + "\nUS\n" + "=" * 72)
plan = load("data/us/v3/plan.json", [])
by = defaultdict(list)
for e in plan:
    by[e["bill_key"]].append(e)
PASSAGE = re.compile(r"passage|pass the bill|pass,? as amended|suspend the rules and pass|conference report|"
                     r"concur in the senate amendment|agree to the senate amendment|agreeing to the senate amendment|"
                     r"agreeing to the resolution|agree to the resolution|suspend the rules and agree|"
                     r"agreeing to the concurrent resolution|agree to the concurrent resolution", re.I)
RULE_DESC = re.compile(r"providing for (?:the )?consideration|waiving (?:all )?points of order", re.I)
# applied to vote_question only; word boundaries so "Suspend the Rules and Pass" is NOT excluded
NOT_PASSAGE = re.compile(r"\brecommit|\bto table\b|\bthe motion to table\b|previous question|\badjourn|"
                         r"\bresolution providing\b|\bquorum\b|\bjournal\b", re.I)
vv = defaultdict(list)
vv_day = defaultdict(list)       # (congress, date) -> every roll call that day
vv_path = ROOT / "data/us/voteview/house_rollcalls_1985_present.csv"
if vv_path.exists():
    with open(vv_path, encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            b = re.sub(r"[^A-Z0-9]", "", (r.get("bill_number") or "").upper())
            vv[(str(r.get("congress", "")).strip(), b, (r.get("date") or "")[:10])].append(r)
            vv_day[(str(r.get("congress", "")).strip(), (r.get("date") or "")[:10])].append(r)
tally = Counter()


def bill_ref_re(raw_bill):
    """'HR1327' -> matches 'H.R. 1327', 'HR 1327', 'H.R.1327' (not 'H.R. 13270')."""
    m = re.match(r"([A-Z]+)(\d+)$", raw_bill)
    if not m:
        return None
    letters, n = m.groups()
    return re.compile(r"\b" + r"\.?\s?".join(letters) + r"\.?\s?" + n + r"\b", re.I)
# Congress.gov bill actions (fetch_official_status.py us-congress): covers voice votes,
# which have no roll call. Legacy (pre-1995) and current action wording both handled.
CG_PASS = re.compile(r"Passed/agreed to in House|\bPassed House\b|Measure passed House|"
                     r"\bagreed to (?:in|by) (?:the )?House\b|Resolution agreed to in House|"
                     r"Conference report agreed to in House|House agreed to (?:the )?(?:Senate amendment|conference report)|"
                     r"House (?:agreed|concurred) (?:in|to) (?:the )?Senate amendment", re.I)
CG_FAIL = re.compile(r"Failed of passage/not agreed to in House|Failed of passage in House|Failed to pass House|"
                     r"not agreed to in House", re.I)
CG_LAW = re.compile(r"Became Public Law|Became Private Law", re.I)
# lines in a bill's action list that are about something else: the rule (H.Res.) under
# which it was considered, or an amendment to it ("Rule H. Res. 385 passed House.")
CG_OTHER = re.compile(r"\bRule\b.{0,40}H\.?\s?Res|providing for (?:the )?consideration|\bH\.?\s?Amdt|"
                      r"\bAmendment \(A\d|On agreeing to the .{0,80}amendment|amendment .{0,60}(?:agreed|failed)", re.I)
cg = {}
cg_dir = STATUS / "us"
for p in sorted(cg_dir.glob("*.actions.json")) if cg_dir.exists() else []:
    bk = p.name[:-len(".actions.json")]
    try:
        acts = json.loads(p.read_text(encoding="utf-8")).get("actions") or []
    except ValueError:
        continue
    texts = [str(a.get("text", "")) for a in acts]
    law = any(CG_LAW.search(t) for t in texts)
    bp = cg_dir / f"{bk}.bill.json"
    if bp.exists():
        try:
            law = law or bool((json.loads(bp.read_text(encoding="utf-8")).get("bill") or {}).get("laws"))
        except ValueError:
            pass
    own = [t for t in texts if not CG_OTHER.search(t) or re.search(r"Senate amendment", t, re.I)]
    hp = [t for t in own if CG_PASS.search(t) and not CG_FAIL.search(t)]
    hf = [t for t in own if CG_FAIL.search(t)]
    flag = 1 if hp else (0 if hf else None)
    cg[bk] = {"flag": flag, "law": law, "n_actions": len(acts),
              "text": (hp or hf or [""])[0][:200]}
if cg:
    say(f"Congress.gov action files: {len(cg)}; readable (1+ actions): {sum(v['n_actions'] > 0 for v in cg.values())}; "
        f"House passed {sum(v['flag'] == 1 for v in cg.values())}, House failed {sum(v['flag'] == 0 for v in cg.values())}, "
        f"no House floor outcome {sum(v['flag'] is None for v in cg.values())}; became law {sum(v['law'] for v in cg.values())}")
else:
    say("Congress.gov actions not fetched (python3 scripts/v3/fetch_official_status.py us-congress)")
us_rows = {}
CG_TYPES = {"hr": "house-bill", "s": "senate-bill", "hres": "house-resolution", "hjres": "house-joint-resolution",
            "hconres": "house-concurrent-resolution", "sres": "senate-resolution", "sjres": "senate-joint-resolution",
            "sconres": "senate-concurrent-resolution"}
for bk, votes in by.items():
    votes = sorted(votes, key=lambda v: v.get("vote_date", ""))
    have = [v for v in votes if (v.get("result") or "").strip()]
    final = have[-1] if have else votes[-1]
    raw = (final.get("result") or "").strip()
    flag = passed_flag(raw)
    # passage-type roll calls on the plan's vote dates
    hits = []
    for v in votes:
        rb = re.sub(r"[^A-Z0-9]", "", str(v.get("raw_bill", "")).upper())
        for r in vv.get((str(v.get("congress", "")), rb, v.get("vote_date", "")), []):
            q = f"{r.get('vote_question', '')} {r.get('vote_desc', '')}"
            if PASSAGE.search(q) and not NOT_PASSAGE.search(r.get("vote_question", "")):
                hits.append(r)
    by_desc = False
    if not hits:
        # older roll calls often have no bill_number; accept one only if its own
        # description names this bill and it is a passage-type question
        for v in votes:
            rx = bill_ref_re(re.sub(r"[^A-Z0-9]", "", str(v.get("raw_bill", "")).upper()))
            if rx is None:
                continue
            for r in vv_day.get((str(v.get("congress", "")), v.get("vote_date", "")), []):
                desc = f"{r.get('vote_desc', '')} {r.get('dtl_desc', '')}"
                q = f"{r.get('vote_question', '')} {r.get('vote_desc', '')}"
                if rx.search(desc) and PASSAGE.search(q) and not NOT_PASSAGE.search(r.get("vote_question", "")) \
                        and not RULE_DESC.search(desc):
                    hits.append(r)
                    by_desc = True
    plan_flag, plan_raw = flag, raw
    vflags = [passed_flag(h.get("vote_result")) for h in hits]
    v_flag = (1 if 1 in vflags else (0 if 0 in vflags else None)) if hits else None
    vdesc = "; ".join(f"{h.get('vote_question', '')}: {h.get('vote_result', '')}" for h in hits)[:300]
    c = cg.get(bk, {})
    us_rows[bk] = {"plan": plan_flag, "vv": v_flag, "cg": c.get("flag"), "plan_raw": plan_raw, "vdesc": vdesc,
                   "by_desc": by_desc, "cg_text": c.get("text", ""), "law": c.get("law") if c else None,
                   "final": final, "votes": votes}
    if v_flag is None:
        tally["no passage roll call"] += 1
    elif plan_flag is None:
        tally["plan blank"] += 1
    elif plan_flag == v_flag:
        tally["agree"] += 1
    else:
        tally[f"disagree (plan {plan_raw})"] += 1

# how well does each source agree with the others (House passage)?
pv = [(r["plan"], r["vv"]) for r in us_rows.values() if r["plan"] is not None and r["vv"] is not None]
cv = [(r["cg"], r["vv"]) for r in us_rows.values() if r["cg"] is not None and r["vv"] is not None]
pc = [(r["plan"], r["cg"]) for r in us_rows.values() if r["plan"] is not None and r["cg"] is not None]
for name, pairs, la, lb in (("plan.json vs Voteview", pv, "plan", "vv"), ("Congress.gov vs Voteview", cv, "cg", "vv"),
                            ("plan.json vs Congress.gov", pc, "plan", "cg")):
    a, n, r_ = rate(pairs)
    say(f"{name}: {a}/{n} agree ({r_:.1%}). [{crosstab(pairs, la, lb)}]")
cg_ok = rate(cv)[2] >= AGREE_MIN and rate(cv)[1] >= MIN_N
say(f"Congress.gov accepted as a source (>= {AGREE_MIN:.0%} agreement with Voteview on >= {MIN_N} bills): {cg_ok}")
say("Outcome = passed the House. Order: Voteview passage roll call (the recorded vote itself); "
    "else Congress.gov House action (voice votes) if accepted; else plan.json.")

for bk, r in us_rows.items():
    checks = []
    if r["vv"] is not None:
        flag, raw = r["vv"], ("Passed" if r["vv"] else "Failed") + " (roll call)"
        source = "voteview passage roll call" + (" (matched by description)" if r["by_desc"] else "")
        if r["cg"] is not None:
            checks.append(f"Congress.gov {'agrees' if r['cg'] == r['vv'] else 'DISAGREES'}: {r['cg_text'][:120]}")
        if r["plan"] is not None and r["plan"] != r["vv"]:
            checks.append(f"plan.json says {r['plan_raw']} (not used: differs from the official vote record)")
        checks.append(f"voteview: {r['vdesc']}")
    elif cg_ok and r["cg"] is not None:
        flag, raw, source = r["cg"], r["cg_text"][:120], "Congress.gov House action"
        checks.append("voice vote or no roll call: Congress.gov House action only")
        if r["plan"] is not None and r["plan"] != r["cg"]:
            checks.append(f"plan.json says {r['plan_raw']} (not used: differs from the official vote record)")
    elif r["plan"] is not None:
        flag, raw, source = r["plan"], r["plan_raw"], "plan.json"
        if r["cg"] is not None:
            checks.append(f"Congress.gov {'agrees' if r['cg'] == r['plan'] else 'DISAGREES'}: {r['cg_text'][:120]}")
        else:
            checks.append("no second source (no passage roll call, no Congress.gov action)")
    else:
        flag, raw, source = None, "", ""
        checks.append("no result in any source")
    m_ = re.match(r"^(\d+)-([A-Z]+)(\d+)$", bk)
    cg_url = ""
    if m_ and m_.group(2).lower() in CG_TYPES:
        c_ = int(m_.group(1))
        suf = "th" if 10 <= c_ % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(c_ % 10, "th")
        cg_url = f"https://www.congress.gov/bill/{c_}{suf}-congress/{CG_TYPES[m_.group(2).lower()]}/{m_.group(3)}/all-actions"
    result["us"][bk] = {"official_url": cg_url, "outcome_raw": raw, "passed": flag, "source": source,
                        "outcome_date": r["final"].get("vote_date", ""),
                        "became_law": {True: "YES", False: "no", None: ""}[r["law"]],
                        "all_votes": "; ".join(f"{v.get('vote_date', '')}: {(v.get('result') or '').strip() or 'no result'}"
                                               f" ({v.get('source', '')})" for v in r["votes"]),
                        "check": "; ".join(checks)}
say(f"plan.json vs Voteview passage roll calls: {dict(tally)}")
dis_us = sorted(k for k, v in result["us"].items() if "DISAGREES" in v["check"].split("voteview:")[0])
if dis_us:
    say(f"disagreements, first 10: " + "; ".join(f"{k} [{result['us'][k]['outcome_raw']}] {result['us'][k]['check'][:120]}"
                                                 for k in dis_us[:10]))

# ======================================================================= coverage + spot check
say("\n" + "=" * 72 + "\nBILLS WITH PREDICATIONS\n" + "=" * 72)
random.seed(7)
for j in ("us", "ontario", "quebec"):
    pk = pred_keys(j)
    t = result[j]
    have = [k for k in pk if t.get(k, {}).get("passed") is not None]
    pend = [k for k in pk if "running" in str(t.get(k, {}).get("outcome_raw", ""))]
    say(f"{j}: {len(have)} of {len(pk)} have pass/fail (passed {sum(t[k]['passed'] == 1 for k in have)}, "
        f"not passed {sum(t[k]['passed'] == 0 for k in have)}); pending {len(pend)}; "
        f"no outcome {len(pk) - len(have) - len(pend)}")
    say(f"   by source: {dict(Counter(t[k]['source'] for k in have))}")
    for k in random.sample(sorted(have), min(10, len(have))):
        spot.append({"jurisdiction": j, "bill_key": k, "passed": t[k]["passed"], "outcome": t[k]["outcome_raw"],
                     "source": t[k]["source"], "check": t[k]["check"], "official_url": t[k].get("official_url", "")})

with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=1)
(AUD / "outcomes_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
with open(AUD / "outcome_spotcheck.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(spot[0].keys()) if spot else ["bill_key"])
    w.writeheader()
    w.writerows(spot)
say(f"\nWrote {OUT_JSON.relative_to(ROOT)}, outputs/audit/outcomes_report.txt, outputs/audit/outcome_spotcheck.csv")
