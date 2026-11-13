"""export_steps.py [--jur us|ontario|quebec|all]   Plain CSV files for each step of the full run, for sharing.

  cd ~/MiscellaneousProjects/legislative-health-factuality && source venv/bin/activate
  python3 scripts/step3_claims/export_steps.py

Reads the chunks in outputs/full/<legislature>/ (it can be run while the full run is still going; it exports
whatever is finished) and writes to outputs/full/exports/<legislature>/:

  step1_sentences.csv   one row per sentence: id, bill, date, language, text, and whether the parsers worked
  step2_units.csv       one row per discourse unit: which sentence, where it starts and ends, its words
  step2_relations.csv   one row per discourse relation between units: the label and which side is the main part
  step3_claims.csv      one row per claim, in words: subject, verb, object, kind (asserted, embedded, reported),
                        negated, hedged, and where a borrowed subject came from

Every file has sentence_id, so the files join to each other and to the bills (bill_key). Nothing here uses Spotlight
or DBpedia: the claims are the words as spoken. step3 needs the claims step (run_full_corpus.py --claims) first."""
import argparse, csv, json, os, time
from pathlib import Path

PROJECT = Path.cwd() if (Path.cwd() / "data").exists() else Path.home() / "MiscellaneousProjects" / "legislative-health-factuality"
OUT = PROJECT / "outputs" / "full"
JUR = {"us": "US House", "ontario": "Ontario", "quebec": "Quebec"}

ap = argparse.ArgumentParser()
ap.add_argument("--jur", default="all", choices=["all"] + list(JUR))
A = ap.parse_args()


def say(m):
    print(time.strftime("%H:%M:%S"), m, flush=True)


class Table:
    # a CSV written under a temporary name and renamed when complete
    def __init__(self, path, columns):
        self.path, self.tmp, self.n = path, path.with_name(path.name + ".tmp"), 0
        path.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(self.tmp, "w", encoding="utf-8", newline="")
        self.w = csv.writer(self.f)
        self.w.writerow(columns)

    def row(self, values):
        self.w.writerow(["" if v is None else v for v in values])
        self.n += 1

    def close(self):
        self.f.close()
        os.replace(self.tmp, self.path)


def units_text(ids):
    return " ".join(str(i) for i in ids)


def export(j):
    src, dst = OUT / j, OUT / "exports" / j
    parses = sorted(src.glob("parses_[0-9]*.json"))
    claims = sorted(src.glob("claims_[0-9]*.json"))
    if not parses:
        say(f"{j}: nothing parsed yet")
        return
    # step 1: the sentences, from the parse chunks
    t1 = Table(dst / "step1_sentences.csv", ["sentence_id", "legislature", "bill_key", "date", "lang", "words", "parsed", "discourse_units", "text"])
    for pf in parses:
        for r in json.load(open(pf, encoding="utf-8"))["rows"]:
            ok = str(r.get("disc_native_status", "")).startswith("ok") and bool(r.get("trees"))
            edus = (r.get("disc_native") or {}).get("edus") or []
            t1.row([r["sentence_id"], JUR[j], r.get("bill_key"), r.get("date"), r["lang"], len(r["text"].split()),
                    "yes" if ok else "no", len(edus), r["text"]])
    t1.close()
    # steps 2 and 3: the units, the relations and the claims, from the claims chunks
    t2 = Table(dst / "step2_units.csv", ["sentence_id", "unit", "start", "end", "unit_text", "claims_in_unit"])
    t3 = Table(dst / "step2_relations.csv", ["sentence_id", "from_units", "to_units", "relation", "parser_label", "main_part", "from_text", "to_text"])
    t4 = Table(dst / "step3_claims.csv", ["sentence_id", "legislature", "bill_key", "date", "lang", "unit", "subject", "verb", "object",
                                          "kind", "negated", "hedged", "subject_borrowed_from", "how_it_was_read"])
    for cf in claims:
        for r in json.load(open(cf, encoding="utf-8"))["rows"]:
            sid = r["sentence_id"]
            for u in r["units"]:
                t2.row([sid, u["unit"], u.get("start"), u.get("end"), u["text"], len(u.get("lines", []))])
            for c in r.get("connections", []):
                t3.row([sid, units_text(c.get("from_units", [])), units_text(c.get("to_units", [])), c.get("relation"),
                        c.get("parser_label"), c.get("main"), c.get("from_text"), c.get("to_text")])
            for ln in r["lines"]:
                t4.row([sid, JUR[j], r.get("bill_key"), r.get("date"), r["lang"], ln.get("unit"), ln.get("subject"), ln.get("verb"),
                        ln.get("object"), ln.get("kind"), "yes" if ln.get("negated") else "no", "yes" if ln.get("hedged") else "no",
                        ln.get("subject_from"), ln.get("how")])
    for t in (t2, t3, t4):
        t.close()
    say(f"{j}: {t1.n} sentences from {len(parses)} parsed chunks; {t2.n} units, {t3.n} relations and {t4.n} claims from {len(claims)} claims chunks")
    say(f"   written to {dst}")


if __name__ == "__main__":
    for j in (list(JUR) if A.jur == "all" else [A.jur]):
        export(j)
