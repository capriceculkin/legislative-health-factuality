"""hand_check_score.py FILLED.xlsx KEY.json

A person's check of the claim sample (docs/hand_check_sample.xlsx, filled in) set beside the two AI readers' verdicts
(outputs/edu/hand_check_sample_key.json, kept apart so the person does not see them). Prints the share of claims the
person marks right (with a 95% Wilson interval), by legislature, and how often the person agrees with each reader and
with the readers' joint verdict (with Cohen's kappa).
    python3 scripts/v6/hand_check_score.py docs/hand_check_sample.xlsx outputs/edu/hand_check_sample_key.json"""
import collections
import json
import math
import sys

from openpyxl import load_workbook


def wilson(x, n, z=1.96):
    if not n:
        return "n/a"
    p = x / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return f"{100 * (c - h):.0f} to {100 * (c + h):.0f}"


def kappa(pairs):
    pairs = [(a, b) for a, b in pairs if a in ("right", "wrong") and b in ("right", "wrong")]
    n = len(pairs)
    if not n:
        return None, 0
    po = sum(a == b for a, b in pairs) / n
    pa = sum(a == "right" for a, _ in pairs) / n
    pb = sum(b == "right" for _, b in pairs) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0, n


def norm(v):
    v = (str(v or "")).strip().lower()
    return {"yes": "right", "y": "right", "right": "right", "no": "wrong", "n": "wrong", "wrong": "wrong"}.get(v, "unsure" if v else "")


ws = load_workbook(sys.argv[1], data_only=True)["Claims"]
key = {k["n"]: k for k in json.load(open(sys.argv[2], encoding="utf-8"))}
hand = {}
for row in ws.iter_rows(min_row=2, values_only=True):
    if row[0] is None:
        continue
    hand[int(row[0])] = (norm(row[8]), row[2])
done = {n: v for n, v in hand.items() if v[0]}
print(f"claims marked: {len(done)} of {len(hand)}")
judged = [n for n, v in done.items() if v[0] in ("right", "wrong")]
right = sum(1 for n in judged if done[n][0] == "right")
print(f"marked right by the person: {right}/{len(judged)} ({100 * right / max(1, len(judged)):.0f}%, 95% interval {wilson(right, len(judged))})")
for leg in ("US House", "Ontario", "Quebec"):
    ns = [n for n in judged if done[n][1] == leg]
    r = sum(1 for n in ns if done[n][0] == "right")
    print(f"   {leg:<9} {r}/{len(ns)} ({100 * r / max(1, len(ns)):.0f}%)")
for who in ("reading_A", "reading_B", "both"):
    k, n = kappa([(done[x][0], key[x][who]) for x in judged])
    agree = sum(1 for x in judged if done[x][0] == key[x][who])
    print(f"agreement with {who.replace('_', ' ')}: {agree}/{len(judged)}" + (f"; Cohen's kappa {k:.2f} on {n} claims both marked right or wrong" if k is not None else ""))
both = collections.Counter((key[x]["both"], done[x][0]) for x in judged)
print("readers' joint verdict against the person:", dict(both))
