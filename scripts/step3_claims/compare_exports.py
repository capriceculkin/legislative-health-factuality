"""compare_exports.py MINE THEIRS [--jur us|ontario|quebec|all] [--out FOLDER]

Compares two sets of step exports (the folders export_steps.py writes) sentence by sentence, so a replication can
be checked against the original run. Reads only; it writes a report only when --out is given.

  python3 scripts/step3_claims/compare_exports.py outputs/full/exports ~/Downloads/caprice_exports
  python3 scripts/step3_claims/compare_exports.py outputs/full/exports ~/Downloads/caprice_exports --jur ontario --out outputs/compare

MINE and THEIRS each hold one folder per legislature (us, ontario, quebec) with step1_sentences.csv,
step2_units.csv, step2_relations.csv and step3_claims.csv. A legislature missing from either side is skipped.

The full run is long, so the two sides may have finished different numbers of chunks. Only the sentences present on
both sides are compared, and the report says how many sentences each side has and how many are shared.

For every shared sentence it checks, step by step:
  step 1  the same text, language and word count
  step 2  the same discourse units (start, end, text) and the same relations (units, relation, main part)
  step 3  the same claims (unit, subject, verb, object, kind, negated, hedged), in the same order
A sentence counts as the same at a step only when everything listed for that step matches exactly."""
import argparse, csv, sys, time
from collections import defaultdict
from pathlib import Path

LEGS = ["us", "ontario", "quebec"]
FILES = {
    "step1": ("step1_sentences.csv", ["text", "lang", "words"]),
    "step2_units": ("step2_units.csv", ["unit", "start", "end", "unit_text"]),
    "step2_relations": ("step2_relations.csv", ["from_units", "to_units", "relation", "main_part"]),
    "step3": ("step3_claims.csv", ["unit", "subject", "verb", "object", "kind", "negated", "hedged"]),
}

csv.field_size_limit(10 ** 9)


def say(m):
    print(time.strftime("%H:%M:%S"), m, flush=True)


def read(path, cols):
    # sentence_id -> list of rows (each row a tuple of the compared columns), in file order
    out = defaultdict(list)
    with open(path, encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        missing = [c for c in ["sentence_id"] + cols if c not in (r.fieldnames or [])]
        if missing:
            sys.exit(f"{path} has no column {', '.join(missing)}. Is it an export from export_steps.py?")
        for row in r:
            out[row["sentence_id"]].append(tuple(row[c] for c in cols))
    return out


def compare(leg, mine, theirs, report):
    a_dir, b_dir = mine / leg, theirs / leg
    if not (a_dir.is_dir() and b_dir.is_dir()):
        say(f"{leg}: skipped (no folder on {'both sides' if not a_dir.is_dir() and not b_dir.is_dir() else 'one side'})")
        return None
    # the sentences file decides which sentences each side has
    a1 = read(a_dir / FILES["step1"][0], FILES["step1"][1])
    b1 = read(b_dir / FILES["step1"][0], FILES["step1"][1])
    shared = sorted(set(a1) & set(b1))
    say(f"{leg}: {len(a1):,} sentences on the first side, {len(b1):,} on the second, {len(shared):,} shared")
    result = {"legislature": leg, "first": len(a1), "second": len(b1), "shared": len(shared)}
    for step, (name, cols) in FILES.items():
        a = a1 if step == "step1" else read(a_dir / name, cols)
        b = b1 if step == "step1" else read(b_dir / name, cols)
        same = 0
        for sid in shared:
            if a.get(sid, []) == b.get(sid, []):
                same += 1
            else:
                report.append([leg, step, sid, " || ".join(" | ".join(x) for x in a.get(sid, [])),
                               " || ".join(" | ".join(x) for x in b.get(sid, []))])
        rows_a = sum(len(a.get(s, [])) for s in shared)
        rows_b = sum(len(b.get(s, [])) for s in shared)
        say(f"   {step:16s} same in {same:,} of {len(shared):,} sentences ({rows_a:,} rows vs {rows_b:,} rows)")
        result[step] = same
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mine", type=Path)
    ap.add_argument("theirs", type=Path)
    ap.add_argument("--jur", default="all", choices=["all"] + LEGS)
    ap.add_argument("--out", type=Path, help="folder for differences.csv and summary.csv")
    A = ap.parse_args()
    report, results = [], []
    for leg in (LEGS if A.jur == "all" else [A.jur]):
        r = compare(leg, A.mine, A.theirs, report)
        if r:
            results.append(r)
    if not results:
        sys.exit("Nothing was compared. Check the two folder paths.")
    all_same = all(r[s] == r["shared"] for r in results for s in FILES)
    say("RESULT: every shared sentence is the same at every step" if all_same
        else f"RESULT: {len(report):,} sentence-steps differ; the first ten are below")
    for row in report[:10]:
        say(f"   {row[0]} {row[1]} {row[2]}\n      first:  {row[3][:300]}\n      second: {row[4][:300]}")
    if A.out:
        A.out.mkdir(parents=True, exist_ok=True)
        with open(A.out / "differences.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["legislature", "step", "sentence_id", "first_side", "second_side"])
            w.writerows(report)
        with open(A.out / "summary.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["legislature", "sentences_first", "sentences_second", "shared"] + list(FILES))
            for r in results:
                w.writerow([r["legislature"], r["first"], r["second"], r["shared"]] + [r[s] for s in FILES])
        say(f"wrote {A.out / 'differences.csv'} and {A.out / 'summary.csv'}")
    sys.exit(0 if all_same else 1)


if __name__ == "__main__":
    main()
