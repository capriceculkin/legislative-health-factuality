#!/usr/bin/env python3
"""
fix_outcome_fix9.py   (edits data/v3_hand_checks.json and scripts/step1_debate_text/outcomes_v3.py; keeps backups)

33-1 Bill 55 (Prescription Drug Cost Regulation Act, 1985) is marked passed from the final-stages file's
"royal assent December 6". That cannot be this bill: its second reading was debated on January 13, 1986. The 1st
session's last sitting in the Hansard is February 12, 1986; the same bill was reintroduced in the 2nd session as
Bill 55 and received royal assent on July 10, 1986 (33-2 Bill 55, which is passed in the data). A hand check
records 33-1 Bill 55 as not passed, and outcomes_v3.py now lets a hand check decide when the bill has no OLA page
(before, a hand check was used only to annotate an OLA page reading).
"""
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / "scripts" / "step1_debate_text" / "outcomes_v3.py").exists():
    ROOT = Path.home() / "MiscellaneousProjects" / "legislative-health-factuality"
HC = ROOT / "data" / "v3_hand_checks.json"
OV = ROOT / "scripts" / "step1_debate_text" / "outcomes_v3.py"
stamp = time.strftime("%Y%m%d-%H%M%S")

checks = json.load(open(HC, encoding="utf-8")) if HC.exists() else []
if not any(c.get("jurisdiction") == "ontario" and c.get("bill_key") == "33-1-Bill55" for c in checks):
    if HC.exists():
        shutil.copy2(HC, HC.with_name(f"v3_hand_checks_before_fix9_{stamp}.json"))
    checks.append({
        "jurisdiction": "ontario", "bill_key": "33-1-Bill55", "passed": 0, "checked": "2026-10-06",
        "official": "Prescription Drug Cost Regulation Act, 1985: second reading debated January 13, 1986 (Hansard); "
                    "the 1st session's last sitting is February 12, 1986; reintroduced in the 2nd session as Bill 55, "
                    "royal assent July 10, 1986 (33-2 Bill 55). The final-stages file's 'royal assent December 6' "
                    "for 33-1 Bill 55 precedes its second reading and is not this bill.",
        "url": "https://www.ola.org/en/legislative-business/house-documents/parliament-33/session-1/1986-01-13/hansard"})
    HC.write_text(json.dumps(checks, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("data/v3_hand_checks.json: 33-1 Bill 55 recorded as not passed")
else:
    print("data/v3_hand_checks.json already has 33-1 Bill 55")

s = OV.read_text(encoding="utf-8")
MARK = "PATCHED_HAND_OUTCOME_2026_10_06"
if MARK not in s:
    OLD = '    if ola_ok and o_flag is not None:\n        rec = (o_flag, o_desc, "OLA bill status page")\n'
    NEW = ('    if hc and o_flag is None and hc.get("passed") in (0, 1):   # ' + MARK + ': no OLA page; checked by hand\n'
           '        rec = (hc["passed"], "checked by hand: " + str(hc.get("official", "")), "checked by hand against the official record")\n'
           '    elif ola_ok and o_flag is not None:\n        rec = (o_flag, o_desc, "OLA bill status page")\n')
    if s.count(OLD) != 1:
        sys.exit("outcomes_v3.py is not in the expected form; nothing changed there. Send this output to Claude.")
    shutil.copy2(OV, OV.with_name(f"outcomes_v3_before_fix9_{stamp}.py"))
    s = s.replace(OLD, NEW)
    compile(s, str(OV), "exec")
    OV.write_text(s, encoding="utf-8")
    print("scripts/step1_debate_text/outcomes_v3.py: a hand check decides when there is no OLA page")
else:
    print("scripts/step1_debate_text/outcomes_v3.py already patched")
