#!/usr/bin/env python3
"""
patch_us_sections.py   (edits scripts/step1_debate_text/us_rebuild.py; keeps a backup; changes no data)

Replaces the segment step of us_rebuild.py with the rule in us_sections.py: text belongs to a
bill only from the Record's own line that brings that bill before the House, and runs until a
line that brings up another measure, a one-minute speech or special order, or a procedural
break. Other measures' debates and procedural items are taken out only when two independent
checks agree; speeches, printed bill text, roll-call lists and vehicle days are tagged, not
deleted. Also writes data/us/v3/section_hand_checks.json (titles read by hand on Sept 29 as a
bill's own debate, and the vehicle days) if it does not exist yet.

Run from the project folder:   python3 scripts/step1_debate_text/patch_us_sections.py
"""
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
P = HERE / "us_rebuild.py"
NEW = HERE / "us_sections_cmd_segment.py"
OLD_MD5 = "575a276ea44d5fc750e2eff6145e6bcc"

if not (HERE / "us_sections.py").exists() or not NEW.exists():
    sys.exit("us_sections.py and us_sections_cmd_segment.py must be in scripts/step1_debate_text next to this file. Nothing changed.")
s = P.read_text(encoding="utf-8")
ROUND1_MD5 = "dbc2f99ac4e60c6157e4bf94396cc8b9"   # the Oct 2 afternoon version of the patched segment step
ROUND2_MD5 = "f110bae9090a71b14f2f664d48c74f80"   # the Oct 2 evening version (round 2)
ROUND3_MD5 = "ffe723acbd9fc85c11f873c12628d0ac"   # the Oct 2 night version (round 3)
ROUND4_MD5 = "9ca3c37b6ee5e54b3585c3f31e2b3508"   # the Oct 3 version (round 4)
NEW_TEXT = NEW.read_text(encoding="utf-8")
if "PATCHED_SECTIONS5_2026_10_03" in s:
    print("us_rebuild.py already has this patch; nothing to do.")
else:
    if "PATCHED_SECTIONS4_2026_10_03" in s:         # round 4 is in place: replace its segment step only
        a, b = s.find("def _section_inputs(plan):"), s.find("def cmd_verify():")
        expect = ROUND4_MD5
        new = NEW_TEXT[NEW_TEXT.find("def _section_inputs(plan):"):].rstrip() + "\n\n\n"
    elif "PATCHED_SECTIONS3_2026_10_02" in s:       # round 3 is in place: replace its segment step only
        a, b = s.find("def _section_inputs(plan):"), s.find("def cmd_verify():")
        expect = ROUND3_MD5
        new = NEW_TEXT[NEW_TEXT.find("def _section_inputs(plan):"):].rstrip() + "\n\n\n"
    elif "PATCHED_SECTIONS2_2026_10_02" in s:       # round 2 is in place: replace its segment step only
        a, b = s.find("def _section_inputs(plan):"), s.find("def cmd_verify():")
        expect = ROUND2_MD5
        new = NEW_TEXT[NEW_TEXT.find("def _section_inputs(plan):"):].rstrip() + "\n\n\n"
    elif "PATCHED_SECTIONS_2026_10_02" in s:        # round 1 is in place
        a, b = s.find("def _section_inputs(plan):"), s.find("def cmd_verify():")
        expect = ROUND1_MD5
        new = NEW_TEXT.rstrip() + "\n\n\n"
    else:
        a, b = s.find("def cmd_segment():"), s.find("def cmd_verify():")
        expect = OLD_MD5
        new = NEW_TEXT.rstrip() + "\n\n\n"
    if a < 0 or b < 0:
        sys.exit("us_rebuild.py does not have the expected segment step; nothing changed.")
    if hashlib.md5(s[a:b].encode()).hexdigest() != expect:
        sys.exit("The segment step in your us_rebuild.py is not a version this patch was written for. "
                 "Nothing changed. Send me scripts/step1_debate_text/us_rebuild.py.")
    backup = P.with_name("us_rebuild_before_sections_" + time.strftime("%Y%m%d-%H%M%S") + ".py")
    shutil.copy2(P, backup)
    P.write_text(s[:a] + new + s[b:], encoding="utf-8")
    print(f"Patched {P.relative_to(ROOT)} (backup: {backup.name})")

HAND = ROOT / "data" / "us" / "v3" / "section_hand_checks.json"
if not HAND.exists():
    own = {}
    for k, t in [
        ("111-HR3470", "NATIONALLY ENHANCING"), ("113-HR2668", "FAIRNESS FOR AMERICAN FAMILIES"),
        ("115-HR5797", "INDIVIDUALS IN MEDICAID"), ("111-HR5756", "TRAINING AND RESEARCH FOR AUTISM"),
        ("116-HR4764", "TIMELY REAUTHORIZATION"), ("117-HR941", "TIMELY REAUTHORIZATION"),
        ("118-HR7213", "AUTISM COLLABORATION"), ("117-HR5487", "STILLBIRTH HEALTH"),
        ("114-HR5613", "CONTINUING ACCESS TO HOSPITALS"), ("117-S578", "FOOD ALLERGY SAFETY"),
        ("115-HR7217", "IMPROVING MEDICAID PROGRAMS"), ("111-HR3199", "EMERGENCY MEDIC TRANSITION"),
        ("114-HR5659", "EXPANDING SENIORS RECEIVING DIALYSIS"), ("116-HR3253", "EMPOWERING BENEFICIARIES"),
        ("115-S3029", "PREMATURITY RESEARCH"), ("109-HR864", "SOBER TRUTH"), ("106-HR2498", "CARDIAC ARREST SURVIVAL"),
        ("111-HR1256", "FAMILY SMOKING PREVENTION"), ("114-HR3762", "RESTORING AMERICANS"),
        ("116-HR1425", "STATE HEALTH CARE PREMIUM"), ("108-HR1", "MEDICARE PRESCRIPTION DRUG AND MODERNIZATION"),
        ("110-HR6331", "MEDICARE IMPROVEMENTS FOR PATIENTS"), ("101-HR3968", "ORGAN TRANSPLANT"),
        ("100-S1158", "NATIONAL HEALTH SERVICE CORPS"), ("104-S641", "RYAN WHITE"),
        ("104-S641", "CONFERENCE REPORT ON S. 641"), ("104-HR3103", "HEALTH COVERAGE AVAILABILITY"),
        ("101-HR3607", "MEDICARE CATASTROPHIC COVERAGE REPEAL"), ("101-HR3607", "MEDICARE CATASTROPHIC COVERAGE REFORM"),
        ("110-HR3963", "CHILDREN'S HEALTH INSURANCE"), ("108-HR1", "MOTION TO INSTRUCT CONFEREES ON H.R. 1"),
        ("104-HR2425", "MEDICARE PRESERVATION ACT"), ("109-HRES802", "ENCOURAGING ALL ELIGIBLE"),
        ("102-HR6182", "MAMMOGRAPHY"), ("112-HR1216", "REPEALING MANDATORY FUNDING"), ("117-HR1667", "DR. LORNA BREEN"),
        ("106-HRES535", "SENSE OF THE HOUSE CONCERNING"),
    ]:
        own.setdefault(k, []).append(t)
    HAND.write_text(json.dumps({
        "_about": "Checks made by reading the Record by hand. own_debate_titles: Record item titles that are the "
                  "bill's own debate under its short title or acronym (read Sept 29). vehicle_days: days a bill "
                  "number carried a different, non-health measure through the House (question 9; tagged, not "
                  "removed).",
        "own_debate_titles": own,
        "vehicle_days": [["111-HR3590", "2009-10-08", "Service Members Home Ownership Tax Act of 2009; the Senate "
                          "later used H.R. 3590 for the Affordable Care Act"],
                         ["110-HR1424", "2008-10-03", "Emergency Economic Stabilization Act of 2008 (the bank "
                          "rescue), passed on H.R. 1424, the mental health parity bill, which it includes as "
                          "Division C"]],
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {HAND.relative_to(ROOT)}")

# round 3: hand checks added to an existing file (nothing already in it is changed)
ADD_JOINT = [["111-HR3590", "2010-03-21", "SENATE AMENDMENTS TO H.R. 3590"],
             ["111-HR4872", "2010-03-21", "SENATE AMENDMENTS TO H.R. 3590"]]
ADD_VEHICLE = [["117-S610", "2021-12-07", "Protecting Medicare and American Farmers from Sequester Cuts Act, passed on S. 610 "
                "(the Senate number of the Dr. Lorna Breen bill; the House text is H.R. 1667)"]]
hand = json.loads(HAND.read_text(encoding="utf-8"))
changed = False
hand.setdefault("joint_debates", [])
for j in ADD_JOINT:
    if j not in hand["joint_debates"]:
        hand["joint_debates"].append(j)
        changed = True
have_v = {(v[0], v[1]) for v in hand.get("vehicle_days", [])}
for v in ADD_VEHICLE:
    if (v[0], v[1]) not in have_v:
        hand.setdefault("vehicle_days", []).append(v)
        changed = True
if changed:
    hand["_about"] = hand.get("_about", "") + (" joint_debates: Record items read by hand as one debate on two bills "
                                              "(the text counts for both)." if "joint_debates:" not in hand.get("_about", "") else "")
    HAND.write_text(json.dumps(hand, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"added round-3 hand checks to {HAND.relative_to(ROOT)}")

sys.path.insert(0, str(HERE))
import importlib  # noqa: E402
import us_sections as SEC  # noqa: E402
U = importlib.import_module("us_rebuild")
assert "PATCHED_SECTIONS5_2026_10_03" in P.read_text(encoding="utf-8")
assert SEC.consideration("The SPEAKER pro tempore. Pursuant to clause 8 of rule XX, this 15- minute vote on passage of the bill will be "
                         "followed by a 5-minute vote on the motion to suspend the rules and pass H.R. 627.") is None
assert SEC.consideration("Mr. WAXMAN. Mr. Speaker, I ask unanimous consent that it be in order to take from the Speaker's table "
                         "the Senate bill (S. 1) to amend the Public Health Service Act")[1] == ("s", 1)
assert SEC.rule_names("it shall be in order without intervention of any point of order to consider in the House the bill "
                      "(H.R. 4954) to amend") == {("hr", 4954)}
assert SEC.consideration("Mr. TIBERI. Mr. Speaker, I move to suspend the rules and pass the bill (H.R. 876) to amend")[1] == ("hr", 876)
assert SEC.consideration("Mr. X. Mr. Speaker, I hope the leadership will call up H.R. 3 soon.") is None
assert SEC.consideration("Mr. GOSS. Mr. Speaker, by direction of the Committee on Rules, I call up House Resolution 155 "
                         "and ask for its immediate consideration.")[0] == "rule_call"
assert SEC.MEMBER.match("Mr. McDERMOTT. Mr. Speaker, I yield")
assert SEC.MEMBER.match("Ms. MILLENDER-McDONALD. Mr. Speaker, I rise")
assert SEC.consideration("Mr. PALLONE. Madam Speaker, pursuant to House Resolution 403, I call up", "the bill (H.R. 1629) to amend")[1] == ("hr", 1629)
assert SEC.consideration("The SPEAKER pro tempore. Pursuant to clause 8 of rule XX, this 15-minute vote will be followed by 5-minute votes on the motions to suspend the rules and pass H.R. 5161") is None
# round 5
assert SEC.consideration("in order to take from the Speaker's table the bill (H.R.", "1388) to reauthorize and reform the national service laws,",
                         "Resolved, That upon the adoption of this resolution it shall be") is None
assert SEC.consideration("Mr. WAXMAN. Mr. Speaker, I ask unanimous consent to take from the Speaker's table the Senate bill (S. 1569) to amend",
                         "", "The SPEAKER pro tempore. The gentleman is recognized.")[1] == ("s", 1569)
assert SEC.consideration("Upon adoption of this resolution the Committee on Rules shall be discharged from further consideration of the "
                         "resolution (H. Res. 99) and it shall be laid on the table.") is None
assert SEC.consideration("Mr. WAXMAN. Mr. Speaker, I ask unanimous consent that the Committee on Energy and Commerce be discharged from "
                         "further consideration of the Senate bill (S. 1569) to amend the Act")[1] == ("s", 1569)
assert SEC.is_request("Mr. WAXMAN. Mr. Speaker, I ask unanimous consent that all Members may have 5 legislative days in which to revise "
                      "and extend their remarks and include extraneous material on the bill now under consideration, H.R. 3869.")
assert not SEC.is_debate_speech("Mr. WAXMAN. Mr. Speaker, I ask unanimous consent that all Members may have 5 legislative days in which to "
                                "revise and extend their remarks and include extraneous material on the bill now under consideration, H.R. "
                                "3869, the Minority Health Improvement Act of 1994, which the committee reported last month.")
assert SEC.is_debate_speech("Mr. PALLONE. Mr. Speaker, I rise in strong support of this bill because it helps millions of children get the "
                            "coverage they need, and I want to thank the chairman and ranking member for their work on this bipartisan "
                            "legislation over many months of hearings.")
print("Checks passed.")
